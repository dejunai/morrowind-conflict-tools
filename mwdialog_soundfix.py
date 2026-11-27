"""mwdialog_soundfix.py - --soundfix: scripts that only start a sound while GetSoundPlaying says it isn't playing
restart it every frame wherever the engine answers 0 (as it does on this install for object sounds). They are
rewritten to keep their own state and recompiled with MWRecompile into 'mwdialog_check - MWSoundFix.esp'.

Version 1 of GROK_RECOMPILE_SOUND_SCRIPTS_PLAN.MD (v4):
  * a loop (PlayLoopSound3D*) under `GetSoundPlaying X == 0` becomes a flag: started once, re-armed on a game load
    (the MWSF_Epoch global, bumped by the mwsoundfix MWSE helper) and, in flag mode, when its reference becomes
    active again (the helper zeroes the flags this module lists in mwsoundfix_data.json). --soundfix-loop-mode
    restart also stops and restarts it on a cell change, for an install without MWSE;
  * a one-shot (PlaySound*, 3D or 2D) under the same guard becomes a timer: it may play again one frame before
    its length / pitch has passed;
  * a `GetSoundPlaying X` that asks whether it IS playing reads the flag or timer, and every StopSound of it
    clears them; a play of the sound anywhere else in the script sets them;
  * the fidelity gate: a script is only patched when its unchanged source recompiles to exactly the bytecode it
    ships with (MWRecompile's "unchanged"). Anything else - and anything the rules can't prove safe - is left as
    it is, still guarded by mwsoundguard, and listed in the report with the reason.
The originals are never edited. Nothing is saved in the game beyond the new locals and MWSF_Epoch.
"""
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_paths as MP  # noqa: E402
from mwdialog_tes3 import (  # noqa: E402
    cstr, dec, enc, first_sub, iter_records, iter_subs, pack_sub, read_header_masters, read_plugin_bytes,
    write_plugin_bytes)

SOUNDFIX_NAME = "mwdialog_check - MWSoundFix.esp"
DATA_JSON = "mwsoundfix_data.json"                  # Data Files\MWSE\config\, read by mwsuite.mwsoundfix
REPORT_FILE = "mwdialog_soundfix_report.txt"
EPOCH = "MWSF_Epoch"
MIN_ONESHOT = 0.10                                  # seconds: the shortest replay interval written
PLAYS = ("playloopsound3dvp", "playloopsound3d", "playsound3dvp", "playsound3d", "playsoundvp", "playsound")
_SND = r'"[^"]*"|[^\s,;()"]+'
_REF = r'(?:("[^"]*"|[A-Za-z0-9_\-.\']+)\s*->\s*)?'
PLAY_RE = re.compile(r"^\s*" + _REF + r"(" + "|".join(PLAYS) + r")\b\s*,?\s*(" + _SND + r")(.*)$", re.I)
STOP_RE = re.compile(r"^\s*" + _REF + r"StopSound\b\s*,?\s*(" + _SND + r")\s*$", re.I)
GSP_RE = re.compile(r"^\s*" + _REF + r"GetSoundPlaying\b\s*,?\s*(" + _SND + r")\s*(?:(==|!=|<=|>=|<|>|=)\s*(-?\d+(?:\.\d*)?))?\s*$", re.I)
COND_RE = re.compile(r"^(\s*)(if|elseif)\b(.*)$", re.I)
DECL_RE = re.compile(r"^\s*(short|long|float)\b", re.I)
NUM_RE = re.compile(r"^-?(\d+\.?\d*|\.\d+)$")


class Skip(Exception):
    """This script is left as it is (class X); the message says why."""


def split_comment(line):
    """(code, comment) with the comment starting at the first ';' outside quotes ('' if none)."""
    q = False
    for i, c in enumerate(line):
        if c == '"':
            q = not q
        elif c == ";" and not q:
            return line[:i], line[i:]
    return line, ""


def _unquote(s):
    return (s or "").strip().strip('"').strip().lower()


def _no_parens(s):
    """The text without ( and ) outside quotes."""
    out, q = [], False
    for c in s:
        if c == '"':
            q = not q
        if q or c not in "()":
            out.append(c)
    return "".join(out)


def guard_kind(cond):
    """(ref, sound, 'off' | 'on') for a condition that only asks GetSoundPlaying, else None. 'off' = asks whether
    it is NOT playing (== 0, < 1, != 1, <= 0); 'on' = whether it is (bare, == 1, != 0, > 0, >= 1)."""
    m = GSP_RE.match(_no_parens(cond))
    if not m:
        return None
    ref, snd, op, val = _unquote(m.group(1)), _unquote(m.group(2)), m.group(3), m.group(4)
    if op is None:
        return ref, snd, "on"
    v = float(val)
    if (op in ("==", "=") and v == 0) or (op == "<" and v == 1) or (op == "!=" and v == 1) or (op == "<=" and v == 0):
        return ref, snd, "off"
    if (op in ("==", "=") and v == 1) or (op == "!=" and v == 0) or (op == ">" and v == 0) or (op == ">=" and v == 1):
        return ref, snd, "on"
    return None


def structure(codes):
    """For each line: its block level, and for an if/elseif line the index where its branch ends (the next
    elseif/else/endif of the same if). Raises Skip on unbalanced blocks."""
    level, ends, stack = [0] * len(codes), {}, []     # stack of [kind, open branch line]
    for i, code in enumerate(codes):
        w = code.strip().split(None, 1)
        kw = w[0].lower() if w else ""
        kw = re.match(r"[a-z]*", kw).group(0)
        if kw == "if":
            level[i] = len(stack)
            stack.append(["if", i])
        elif kw in ("elseif", "else", "endif", "endwhile") and not stack:
            level[i] = 0                              # matches nothing: the CS compiles it as a plain statement
        elif kw in ("elseif", "else"):
            if not stack or stack[-1][0] != "if":
                raise Skip(f"line {i + 1}: '{kw}' without 'if'")
            ends[stack[-1][1]] = i
            level[i] = len(stack) - 1
            stack[-1][1] = i
        elif kw == "endif":
            if not stack or stack[-1][0] != "if":
                raise Skip(f"line {i + 1}: 'endif' without 'if'")
            ends[stack[-1][1]] = i
            stack.pop()
            level[i] = len(stack)
        elif kw == "while":
            level[i] = len(stack)
            stack.append(["while", i])
        elif kw == "endwhile":
            if not stack or stack[-1][0] != "while":
                raise Skip(f"line {i + 1}: 'endwhile' without 'while'")
            stack.pop()
            level[i] = len(stack)
        else:
            level[i] = len(stack)
    if stack:
        raise Skip("an 'if' or 'while' is never closed")
    return level, ends


def play_args(kind, rest):
    """The literal pitch of a play (1.0 for the non-VP forms), or None if it isn't a plain number."""
    if not kind.endswith("vp"):
        return 1.0
    parts = [p for p in re.split(r"[\s,]+", split_comment(rest)[0].strip()) if p]
    if len(parts) < 2 or not all(NUM_RE.match(p) for p in parts[:2]):
        return None
    return float(parts[1])


def rewrite(text, length_of, loop_mode="flag"):
    """(new text, groups) for one script's source, or raises Skip. groups: [{var, kind, ref, sounds}], kind
    'loop' or 'timer'. length_of(sound id lower) -> seconds or None."""
    if "mwsf" in text.lower():
        raise Skip("already uses mwsf* names (patched before, or a clash)")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    codes = [split_comment(ln)[0] for ln in lines]
    level, ends = structure(codes)

    # 1. the groups: each guard that asks whether a sound is NOT playing, with the plays inside its branch
    groups, by_key, guards = [], {}, []
    for i, code in enumerate(codes):
        m = COND_RE.match(code)
        g = m and guard_kind(m.group(3))
        if not g or g[2] != "off":
            continue
        ref, snd, _ = g
        end = ends.get(i)
        if end is None:
            raise Skip(f"line {i + 1}: guard without an end")
        plays = []
        for j in range(i + 1, end):
            p = PLAY_RE.match(codes[j])
            if p:
                if _unquote(p.group(1)) != ref:
                    raise Skip(f"line {j + 1}: plays on another reference than its guard checks")
                plays.append((j, p.group(2).lower(), _unquote(p.group(3)), play_args(p.group(2).lower(), p.group(4))))
        if not plays:
            continue
        loops = {k.startswith("playloop") for _j, k, _s, _p in plays}
        if len(loops) > 1:
            raise Skip(f"line {i + 1}: one guard starts both a loop and a one-shot")
        key = (ref, snd)
        grp = by_key.get(key)
        if grp is None:
            grp = {"ref": ref, "sounds": {snd}, "kind": "loop" if loops == {True} else "timer", "guards": []}
            by_key[key] = grp
            groups.append(grp)
        elif grp["kind"] != ("loop" if loops == {True} else "timer"):
            raise Skip(f"line {i + 1}: '{snd}' is used both as a loop and a one-shot")
        grp["guards"].append(i)
        grp["sounds"].update(s for _j, _k, s, _p in plays)
        guards.append((i, ref, snd, plays))
    if not groups:
        raise Skip("no play under a GetSoundPlaying-is-0 test")
    played = [(g["ref"], s) for g in groups for s in g["sounds"]]
    if len(played) != len(set(played)):
        # nested guards ("if A == 0 / if B == 0 / play A or B") share sounds: give every played sound its own
        # state, which is what GetSoundPlaying itself answers. A tested sound this script never plays has no
        # state to read, so that case stays left alone.
        groups, by_key = [], {}
        for i, ref, _snd, plays in guards:
            for _j, k, s, _p in plays:
                kind = "loop" if k.startswith("playloop") else "timer"
                grp = by_key.get((ref, s))
                if grp is None:
                    grp = by_key[(ref, s)] = {"ref": ref, "sounds": {s}, "kind": kind, "guards": []}
                    groups.append(grp)
                elif grp["kind"] != kind:
                    raise Skip(f"'{s}' is used both as a loop and a one-shot")
        for i, ref, snd, _plays in guards:
            if (ref, snd) not in by_key:
                raise Skip(f"line {i + 1}: nested guards test '{snd}', which this script never plays")
            by_key[(ref, snd)]["guards"].append(i)
    for n, grp in enumerate(groups, 1):
        grp["var"] = f"mwsfOn{n}" if grp["kind"] == "loop" else f"mwsfT{n}"

    def group_of(ref, snd):
        hits = [g for g in groups if g["ref"] == ref and snd in g["sounds"]]
        if len(hits) > 1:
            raise Skip(f"'{snd}' belongs to more than one guarded group")
        return hits[0] if hits else None

    # 2. edits per line: (replacement for the line, lines before it, lines after it)
    before, after, replace = {}, {}, {}
    for i, code in enumerate(codes):
        indent = re.match(r"\s*", lines[i]).group(0)
        m = COND_RE.match(code)
        g = m and guard_kind(m.group(3))
        if g:
            grp = group_of(g[0], g[1])
            if grp:
                if grp["kind"] == "loop":
                    test = f"( {grp['var']} == 0 )" if g[2] == "off" else f"( {grp['var']} == 1 )"
                else:
                    test = f"( {grp['var']} <= 0 )" if g[2] == "off" else f"( {grp['var']} > 0 )"
                comment = split_comment(lines[i])[1].strip()
                note = f"; MWSoundFix: was {m.group(3).strip()}" + (f"  {comment}" if comment else "")
                replace[i] = f"{m.group(1)}{m.group(2)} {test}    {note}"
            continue
        p = PLAY_RE.match(code)
        if p:
            grp = group_of(_unquote(p.group(1)), _unquote(p.group(3)))
            if grp is None:
                continue
            refpfx = code[:code.lower().index(p.group(2).lower())].strip()
            if grp["kind"] == "loop":
                if loop_mode == "restart":
                    before.setdefault(i, []).append(f"{indent}{refpfx}StopSound {p.group(3)}    ; MWSoundFix: never two copies")
                after.setdefault(i, []).append(f"{indent}set {grp['var']} to 1    ; MWSoundFix")
            else:
                pitch = p and play_args(p.group(2).lower(), p.group(4))
                length = length_of(_unquote(p.group(3)))
                if pitch is None or pitch <= 0:
                    raise Skip(f"line {i + 1}: the pitch isn't a plain number")
                if not length:
                    raise Skip(f"line {i + 1}: no length known for '{_unquote(p.group(3))}'")
                d = max(MIN_ONESHOT, round(length / pitch, 4))
                after.setdefault(i, []).append(
                    f"{indent}set {grp['var']} to ( {d:.4f} - GetSecondsPassed )    ; MWSoundFix: {length:.2f} s / pitch {pitch:g}, one frame early")
            continue
        s = STOP_RE.match(code)
        if s:
            grp = group_of(_unquote(s.group(1)), _unquote(s.group(2)))
            if grp:
                after.setdefault(i, []).append(f"{indent}set {grp['var']} to 0    ; MWSoundFix")
    for grp in groups:
        for i in grp["guards"]:
            if i not in replace:
                raise Skip(f"line {i + 1}: guard not rewritten")

    # 3. declarations and the block at the top, after the author's declarations and before the first statement
    begin = next((i for i, c in enumerate(codes) if re.match(r"^\s*begin\b", c, re.I)), None)
    if begin is None:
        raise Skip("no 'Begin' line")
    decls = [i for i, c in enumerate(codes) if DECL_RE.match(c)]
    first = next((i for i in range(begin + 1, len(codes)) if codes[i].strip() and not DECL_RE.match(codes[i])), None)
    if first is None:
        raise Skip("no statements")
    at = (max(decls) if decls else begin) + 1
    if decls and max(decls) > first:
        # our locals go after the author's last one (so theirs keep their places); that only works when nothing
        # before it uses ours, and no 'return' before it can skip the re-arm block
        used = sorted(set(replace) | set(before) | set(after))
        if used and used[0] < at:
            raise Skip("declares variables after statements that test or play the sound")
        if any(re.match(r"^\s*return\b", codes[i], re.I) for i in range(first, at)):
            raise Skip("declares variables after a 'return'")
    top = ["", "short mwsfEp    ; MWSoundFix (mwdialog_check --soundfix): MWSF_Epoch last seen"]
    for g in groups:
        what = ", ".join(f'"{s}"' for s in sorted(g["sounds"]))
        top.append(f"short {g['var']}    ; MWSoundFix: 1 = {what} loop running" if g["kind"] == "loop" else
                   f"float {g['var']}    ; MWSoundFix: seconds until {what} may play again")
    top += ["if ( mwsfEp != MWSF_Epoch )    ; MWSoundFix: re-arm after a game load", "\tset mwsfEp to MWSF_Epoch"]
    top += [f"\tset {g['var']} to 0" for g in groups]
    top.append("endif")
    loops = [g for g in groups if g["kind"] == "loop"]
    if loop_mode == "restart" and loops:
        top += ["if ( CellChanged == 1 )    ; MWSoundFix: restart mode: re-arm after a cell change"]
        top += [f"\tset {g['var']} to 0" for g in loops]
        top.append("endif")
    for g in groups:
        if g["kind"] == "timer":
            top += [f"if ( {g['var']} > 0 )", f"\tset {g['var']} to ( {g['var']} - GetSecondsPassed )", "endif"]
    top.append("")

    out = []
    for i, ln in enumerate(lines):
        if i == at:
            out += top
        out += before.get(i, [])
        out.append(replace.get(i, ln))
        out += after.get(i, [])
    return nl.join(out), [{"var": g["var"], "kind": g["kind"], "ref": g["ref"], "sounds": sorted(g["sounds"])}
                          for g in groups]


# ----------------------------------------------------------------------------------------- sounds and lengths

class SoundLengths:
    """Length in seconds of a sound ID's file: mwsoundguard's cache when the file is unchanged, the loose file,
    then the BSAs (bytes copied to a temporary file to measure). None when it can't be measured."""

    def __init__(self, data_dir, plugins, bsas):
        import mwdialog_soundcache as SC
        self.SC, self.data_dir, self.bsas, self.memo = SC, data_dir, list(bsas or []), {}
        self.files = SC.winning_sounds(plugins)
        self.ffprobe = SC.find_ffprobe()
        try:
            with open(os.path.join(data_dir, "MWSE", "config", SC.CACHE_NAME), encoding="utf-8") as f:
                self.cache = json.load(f).get("sounds") or {}
        except (OSError, ValueError, AttributeError):
            self.cache = {}

    def __call__(self, sound_id):
        if sound_id in self.memo:
            return self.memo[sound_id]
        self.memo[sound_id] = got = self._measure(sound_id)
        return got

    def _measure(self, sound_id):
        fn = self.files.get(sound_id)
        if not fn:
            return None
        loose = os.path.join(self.data_dir, "Sound", *fn.replace("/", "\\").split("\\"))
        if os.path.isfile(loose):
            st, c = os.stat(loose), self.cache.get(sound_id)
            if isinstance(c, dict) and c.get("size") == st.st_size and c.get("mtime_ns") == str(st.st_mtime_ns):
                return c.get("length")
            try:
                return self.SC.sound_duration(loose, self.ffprobe)
            except (OSError, ValueError):
                return None
        from mwdialog_bsa import bsa_index
        want = ("sound\\" + fn.replace("/", "\\")).lower()
        for b in self.bsas:
            try:
                hit = bsa_index(b).get(want)
            except Exception:                      # a damaged archive: try the next one
                continue
            if hit:
                off, size = hit
                with open(b, "rb") as f:
                    f.seek(off)
                    data = f.read(size)
                fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(fn)[1] or ".wav")
                try:
                    with os.fdopen(fd, "wb") as f:
                        f.write(data)
                    return self.SC.sound_duration(tmp, self.ffprobe)
                except (OSError, ValueError):
                    return None
                finally:
                    os.remove(tmp)
        return None


# ----------------------------------------------------------------------------------------------- the plugin

def raw_record(tag, body, flags=0):
    return tag.encode("ascii") + struct.pack("<III", len(body), 0, flags) + body


def with_source(raw, text):
    """The SCPT record with its source (SCTX) replaced."""
    body = raw[16:]
    subs = [pack_sub("SCTX", enc(text)) if n == "SCTX" else pack_sub(n, d) for n, d in iter_subs(body)]
    return raw_record("SCPT", b"".join(subs), struct.unpack_from("<I", raw, 12)[0])


def epoch_global():
    return raw_record("GLOB", pack_sub("NAME", enc(EPOCH) + b"\0") + pack_sub("FNAM", b"s")
                      + pack_sub("FLTV", struct.pack("<f", 0.0)))


def plugin_bytes(masters, records, description):
    """A TES3 plugin: header (author mwdialog_check, masters with their sizes), then `records` (raw bytes)."""
    hedr = (struct.pack("<fI", 1.3, 0) + b"mwdialog_check".ljust(32, b"\0")
            + enc(description)[:255].ljust(256, b"\0") + struct.pack("<I", len(records)))
    subs = [pack_sub("HEDR", hedr)]
    for name, mpath in masters:
        subs += [pack_sub("MAST", enc(name) + b"\0"), pack_sub("DATA", struct.pack("<Q", os.path.getsize(mpath)))]
    hb = b"".join(subs)
    return b"TES3" + struct.pack("<III", len(hb), 0, 0) + hb + b"".join(records)


def winning_scripts(plugins):
    """{script id lower: (plugin name, raw record, source text)} of the scripts that win, our patch left out."""
    out = {}
    for name, path in plugins:
        if name.lower() == SOUNDFIX_NAME.lower():
            continue
        for _off, tag, flags, body in iter_records(read_plugin_bytes(path)):
            if tag != "SCPT":
                continue
            schd = first_sub(body, b"SCHD")
            if not schd:
                continue
            sid = cstr(schd[:32]).lower()
            if flags & 0x20:
                out.pop(sid, None)
                continue
            out[sid] = (name, raw_record("SCPT", body, flags), dec(first_sub(body, b"SCTX") or b""))
    return out


def masters_for(owners, plugins):
    """The owner plugins and every master they need, in load order: [(name, path)]."""
    pos = {n.lower(): i for i, (n, _p) in enumerate(plugins)}
    path_of = {n.lower(): (n, p) for n, p in plugins}
    want, todo = set(), [o.lower() for o in owners]
    while todo:
        n = todo.pop()
        if n in want or n not in path_of:
            continue
        want.add(n)
        todo += [m.lower() for m in read_header_masters(path_of[n][1])]
    return [path_of[n] for n in sorted(want, key=lambda n: pos[n])]


def run_mwrecompile(exe, data_dir, plugin, report, out=None):
    """{script id lower: (status, messages)} from MWRecompile's report. Raises RuntimeError on a usage/file error."""
    cmd = [exe, plugin, "-k", "-q", "-d", data_dir, "--report", report] + (["-o", out, "--no-backup"] if out else ["-n"])
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if r.returncode not in (0, 1) or not os.path.isfile(report):
        raise RuntimeError(f"MWRecompile failed (exit {r.returncode}): {(r.stderr or r.stdout).strip()[-600:]}")
    rows = {}
    with open(report, encoding="utf-8", errors="replace") as f:
        next(f, None)
        for line in f:
            parts = line.rstrip("\r\n").split("\t")
            if len(parts) >= 2:
                rows[parts[0].lower()] = (parts[1], parts[7] if len(parts) > 7 else "")
    return rows


# ---------------------------------------------------------------------------------------------- the command

def build(args, plugins, bsas, exe):
    """Scan, rewrite, gate and compile. Returns (records for the patch, masters, patched, skipped):
    patched {id: info}, skipped {id: (owner, reason)}."""
    data_dir = os.path.abspath(args.data_dir)
    mode = getattr(args, "soundfix_loop_mode", None) or "flag"
    lengths = SoundLengths(data_dir, plugins, bsas)
    scripts = winning_scripts(plugins)
    plans, skipped = {}, {}
    for sid, (owner, raw, text) in scripts.items():
        low = text.lower()
        if "getsoundplaying" not in low or not any(p in low for p in PLAYS):
            continue
        try:
            new, groups = rewrite(text, lengths, mode)
            plans[sid] = (owner, raw, new, groups)
        except Skip as e:
            if "no play under" not in str(e):
                skipped[sid] = (owner, str(e))
    if not plans:
        return [], [], {}, skipped
    masters = masters_for({o for o, _r, _n, _g in plans.values()}, plugins)
    with tempfile.TemporaryDirectory(prefix="mwsoundfix-") as tmp:
        # the fidelity gate: the unchanged source must give back the shipped bytecode
        stage = os.path.join(tmp, "gate.esp")
        write_plugin_bytes(stage, plugin_bytes(masters, [r for _o, r, _n, _g in plans.values()], "MWSoundFix gate"))
        rows = run_mwrecompile(exe, data_dir, stage, os.path.join(tmp, "gate.tsv"))
        for sid in list(plans):
            status, msg = rows.get(sid, ("missing", ""))
            if status != "unchanged":
                why = ("its source doesn't compile: " + msg) if status == "ERROR" else \
                      "its source doesn't recompile to the bytecode it ships with (stale source, or a compiler difference)"
                skipped[sid] = (plans.pop(sid)[0], why.strip())
        if not plans:
            return [], masters, {}, skipped
        # the rewritten scripts, compiled with MWSF_Epoch defined beside them
        stage = os.path.join(tmp, "patch.esp")
        out = os.path.join(tmp, "compiled.esp")
        write_plugin_bytes(stage, plugin_bytes(masters, [epoch_global()] + [with_source(r, n) for _o, r, n, _g in plans.values()],
                                               "MWSoundFix stage"))
        rows = run_mwrecompile(exe, data_dir, stage, os.path.join(tmp, "patch.tsv"), out)
        records, patched = [epoch_global()], {}
        compiled = {}
        for _off, tag, flags, body in iter_records(read_plugin_bytes(out)):
            if tag == "SCPT":
                compiled[cstr(first_sub(body, b"SCHD")[:32]).lower()] = raw_record("SCPT", body, flags)
        for sid, (owner, _raw, _new, groups) in plans.items():
            status, msg = rows.get(sid, ("missing", ""))
            if status != "recompiled" or sid not in compiled:
                skipped[sid] = (owner, f"the rewritten script didn't compile ({status}): {msg}".strip())
                continue
            records.append(compiled[sid])
            patched[sid] = {"owner": owner, "groups": groups}
    return records, masters, patched, skipped


def write_report(game_dir, patched, skipped, mode, dry_run):
    path = MP.state_path(game_dir, REPORT_FILE)
    lines = [f"; {REPORT_FILE}: mwdialog_check --soundfix ({time.strftime('%Y-%m-%d %H:%M')}"
             + (", dry run: nothing installed" if dry_run else "") + f"; loop mode {mode})",
             f"; {len(patched)} script(s) rewritten into {SOUNDFIX_NAME}; {len(skipped)} left as they are "
             "(still guarded by mwsoundguard).", "", "REWRITTEN"]
    for sid, info in sorted(patched.items(), key=lambda kv: (kv[1]["owner"].lower(), kv[0])):
        what = "; ".join(f"{g['kind']} {', '.join(g['sounds'])}" + (f" on {g['ref']}" if g["ref"] else "")
                         for g in info["groups"])
        lines.append(f"  {info['owner']}\t{sid}\t{what}")
    lines += ["", "LEFT AS THEY ARE (class X)"]
    for sid, (owner, why) in sorted(skipped.items(), key=lambda kv: (kv[1][0].lower(), kv[0])):
        lines.append(f"  {owner}\t{sid}\t{why}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def _code_digest():
    """A short digest of this module: the MWSE helper and --fix can tell a patch built by older rules."""
    import hashlib
    with open(os.path.abspath(__file__), "rb") as f:
        return hashlib.sha1(f.read().replace(b"\r\n", b"\n")).hexdigest()[:12]


def soundfix_is_stale(data_dir):
    """True when mwsoundfix_data.json was written by a different version of this module (the plugin then
    holds the old rules' choices: rerun --soundfix)."""
    try:
        with open(os.path.join(data_dir, "MWSE", "config", DATA_JSON), encoding="utf-8") as f:
            return json.load(f).get("code") != _code_digest()
    except (OSError, ValueError, AttributeError):
        return False


def _load_order_with(args, add):
    """Put the patch in the load order (just before the Multipatch, else last), or take it out."""
    from mwdialog_loadorder import read_load_order, set_game_files
    cur = read_load_order(args) or []
    rest = [n for n in cur if n.lower() != SOUNDFIX_NAME.lower()]
    if add:
        at = next((i for i, n in enumerate(rest) if n.lower() == "mwdialog_check multipatch.esp"), len(rest))
        new = rest[:at] + [SOUNDFIX_NAME] + rest[at:]
    else:
        new = rest
    if new != cur:
        game_dir = os.path.dirname(os.path.abspath(args.data_dir))
        set_game_files(args.ini or os.path.join(game_dir, "Morrowind.ini"), new, "--soundfix")
        return True
    return False


def run_soundfix(args, plugins, bsas, standalone=True):
    """--soundfix (and the --fix step). Returns an exit code: 0 done, 1 nothing to do / skipped, 2 failed."""
    data_dir = os.path.abspath(args.data_dir)
    game_dir = os.path.dirname(data_dir)
    print("\n" + "=" * 70 + "\nSOUND SCRIPTS (--soundfix)\n" + "=" * 70)
    exe = MP.find_mwrecompile(game_dir, getattr(args, "mwrecompile", None))
    if not exe:
        print("  MWRecompile.exe not found (tools\\MWRecompile\\, --mwrecompile, or MWRECOMPILE): skipped.")
        return 2 if standalone else 1
    mode = getattr(args, "soundfix_loop_mode", None) or "flag"
    dry = bool(args.dry_run or getattr(args, "soundfix_report", False))
    sf_t0 = time.time()
    try:
        records, masters, patched, skipped = build(args, plugins, bsas, exe)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as e:
        print(f"  NOT built: {e}")
        return 2
    report = write_report(game_dir, patched, skipped, mode, dry)
    print(f"  {len(patched)} script(s) rewritten, {len(skipped)} left as they are (report: {os.path.basename(report)})")
    if dry:
        print("  Dry run: nothing installed.")
        print(f"[{int(time.time() - sf_t0)}s] Sound-script patch: report only")
        return 0
    path = os.path.join(data_dir, SOUNDFIX_NAME)
    data_path = os.path.join(data_dir, "MWSE", "config", DATA_JSON)
    if not patched:
        return undo(args, quiet=True) or 1
    import mwdialog_backup as MB
    st = os.stat(path) if os.path.exists(path) else None
    if st:
        shutil.copy2(path, MB.backup_path(path))
    desc = f"MWSoundFix: {len(patched)} sound scripts rewritten to keep their own state; generated, do not edit"
    write_plugin_bytes(path, plugin_bytes(masters, records, desc), keep_times=st)
    if st is None:
        from mwdialog_patchfile import next_free_date
        when = next_free_date(data_dir, SOUNDFIX_NAME)
        if when:
            os.utime(path, (when, when))
    os.makedirs(os.path.dirname(data_path), exist_ok=True)
    data = {"version": 1, "plugin": SOUNDFIX_NAME, "loopMode": mode, "built": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "scripts": {sid: {"owner": i["owner"], "loopFlags": [g["var"] for g in i["groups"] if g["kind"] == "loop"],
                              "repairs": [("loop: " if g["kind"] == "loop" else "one-shot: ") + ", ".join(g["sounds"])
                                          + (f" (on {g['ref']})" if g["ref"] else "") for g in i["groups"]]}
                        for sid, i in sorted(patched.items())},       # repairs: shown in its MCM page
            # left as they are, with the reason: mwsoundguard quotes it when one of them runs away, so a log line
            # says why the recompile didn't take it (and a stale patch shows as "built by older code")
            "skipped": {sid: {"owner": o, "why": w} for sid, (o, w) in sorted(skipped.items())},
            "code": _code_digest()}
    tmp = data_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, data_path)
    moved = _load_order_with(args, True)
    print(f"  {SOUNDFIX_NAME}: written ({len(records) - 1} script(s))" + ("; added to the load order" if moved else ""))
    print(f"  {DATA_JSON}: written for the mwsoundfix MWSE helper")
    print(f"[{int(time.time() - sf_t0)}s] Sound-script patch: {len(patched)} script(s) rewritten, "
          f"{len(skipped)} left as they are")
    return 0


def undo(args, quiet=False):
    """--soundfix-undo: take the patch out (backed up first), with its helper data and its load-order entry."""
    data_dir = os.path.abspath(args.data_dir)
    path = os.path.join(data_dir, SOUNDFIX_NAME)
    data_path = os.path.join(data_dir, "MWSE", "config", DATA_JSON)
    done = []
    if args.dry_run:
        print(f"  Dry run: would remove {SOUNDFIX_NAME} and {DATA_JSON}.")
        return 0
    if os.path.exists(path):
        import mwdialog_backup as MB
        shutil.copy2(path, MB.backup_path(path))
        os.remove(path)
        done.append(SOUNDFIX_NAME)
    if os.path.exists(data_path):
        os.remove(data_path)
        done.append(DATA_JSON)
    if _load_order_with(args, False):
        done.append("its load-order entry")
    if done or not quiet:
        print("  --soundfix-undo: removed " + (", ".join(done) if done else "nothing (not installed)"))
    return 0
