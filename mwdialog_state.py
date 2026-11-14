"""mwdialog_state.py - the small record files the tools keep beside themselves (merged plugins, disabled
plugins, conflict answers, cell winners, redundant plugins, generated files, added masters): reading and writing.
"""
from collections import OrderedDict, defaultdict
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_paths as MP  # noqa: E402
import mwdialog_text as MT  # noqa: E402
import mwdialog_tes3 as _T  # noqa: E402
from mwdialog_backup import (  # noqa: E402
    backup_path)
from mwdialog_tes3 import (  # noqa: E402
    MW_ERRORS, safe_write_bytes)
print = MT.printer()  # noqa: A001

NORMAL_MAP_RE = re.compile(r"_nm?\.(dds|tga|bmp)$", re.I)


def read_generated_record(rec_path):
    """{path lower: (path, size, plugin)} from GENERATED_RECORD ("[plugin]" lines start each plugin's files)."""
    out, plugin = {}, ""
    if not os.path.exists(rec_path):
        return out
    for line in open(rec_path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\r\n")
        if not line.strip() or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            plugin = line[1:-1]
            if plugin.startswith("normal maps") or plugin.startswith("earlier runs"):
                plugin = ""
            continue
        parts = line.split("\t")
        rel = parts[0].strip()
        out[rel.lower()] = (rel, parts[1].strip() if len(parts) > 1 else "", plugin)
    return out


def write_generated_record(rec_path, entries):
    """GENERATED_RECORD grouped by the plugin that needs each file; normal maps (_n/_nm: Morrowind itself
    never draws them) in one group at the end."""
    groups, normals = defaultdict(list), []
    for rel, size, plugin in entries.values():
        (normals if NORMAL_MAP_RE.search(rel) else groups[plugin]).append((rel, size))
    with open(rec_path, "w", encoding="utf-8") as f:
        f.write("; Files mwdialog_check.py --fix put in Data Files: copies of files found in Vortex mod folders but\n"
                "; never deployed, silent stand-ins for sounds and music, and placeholder textures, under the plugin\n"
                "; that needs them (indented: path<TAB>size). --remove-generated deletes them.\n")
        for plugin in sorted(groups, key=lambda p: (p == "", p.lower())):
            f.write(f"[{plugin or 'earlier runs (plugin not recorded)'}]\n")
            for rel, size in sorted(groups[plugin], key=lambda t: t[0].lower()):
                f.write(f"  {rel}\t{size}\n" if size else f"  {rel}\n")
        if normals:
            f.write("[normal maps - Morrowind itself never draws these; placeholders only stop the missing-file "
                    "warnings]\n")
            for rel, size in sorted(normals, key=lambda t: t[0].lower()):
                f.write(f"  {rel}\t{size}\n" if size else f"  {rel}\n")


CELL_WINNER_PATCH = "mwdialog_check Cell Fixes.esp"

MERGE_RECORD = "mwdialog_merged.txt"


def read_merge_record(game_dir):
    """{merged plugin: [input plugins]} from mwdialog_merged.txt."""
    rec, cur = OrderedDict(), None
    try:
        with open(os.path.join(game_dir, MERGE_RECORD), "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith(";"):
                    continue
                if s.startswith("[") and s.endswith("]"):
                    cur = rec.setdefault(s[1:-1], [])
                elif cur is not None:
                    cur.append(s)
    except OSError:
        pass
    return rec


def write_merge_record(game_dir, rec):
    lines = ["; Plugins merged by mwdialog_check.py. Each [section] is a merged plugin; the names under it",
             "; are the plugins it replaces. --add-all-esp and --sort leave those out while the merged",
             "; plugin exists. --unmerge NAME (or --unmerge with no name for all) puts them back.", ""]
    for out, ins in rec.items():
        lines.append(f"[{out}]")
        lines += ins
        lines.append("")
    path = os.path.join(game_dir, MERGE_RECORD)
    if not rec:
        if os.path.exists(path):
            os.remove(path)
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


DISABLED_RECORD = "mwdialog_disabled.txt"


def read_disabled(game_dir):
    """{plugin: reason} for plugins --fix turned off (doubled with another plugin)."""
    out = OrderedDict()
    try:
        with open(os.path.join(game_dir, DISABLED_RECORD), "r", encoding="utf-8") as f:
            for line in f:
                s = line.rstrip("\r\n")
                if not s.strip() or s.lstrip().startswith(";"):
                    continue
                name, _, why = s.partition("\t")
                out[name.strip()] = why.strip()
    except OSError:
        pass
    return out


def write_disabled(game_dir, rec):
    path = os.path.join(game_dir, DISABLED_RECORD)
    if not rec:
        if os.path.exists(path):
            os.remove(path)
        return
    lines = ["; Plugins mwdialog_check.py --fix turned off because another active plugin already places the",
             "; same objects in the same spots (two versions of one mod). --add-all-esp leaves them out.",
             "; --reenable NAME (or --reenable with no name for all) turns them back on. One per line: name<TAB>reason", ""]
    lines += [f"{n}\t{w}" for n, w in rec.items()]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def merged_away(game_dir, data_dir):
    """Lowercase names of plugins replaced by a merged plugin that still exists."""
    out = set()
    for merged, ins in read_merge_record(game_dir).items():
        if os.path.exists(os.path.join(data_dir, merged)):
            out |= {i.lower() for i in ins}
    return out


CONFLICT_BLACKLIST_FILE = "mwdialog_check.conflict.blacklist.txt"

CONFLICT_BLACKLIST_DEFAULT = """; mwdialog_check.conflict.blacklist.txt - plugins that never take part in cell conflicts and
; always lose: they are left out of --cell-conflicts (no report, no question), and --sort loads each one
; as early as its masters allow (.esm among the masters, .esp right after the .esm files), so every
; other mod's version wins, and mwcollide hides its object where two sit on top of each other.
; One plugin per line (wildcards * ? allowed). Don't list a compatibility patch: it must load after the
; mods it patches.
OAAB_Saplings.esm
"""


def read_conflict_blacklist(game_dir, create=True):
    """Lowercase patterns from mwdialog_check.conflict.blacklist.txt (made with the defaults the first time)."""
    path = os.path.join(game_dir, CONFLICT_BLACKLIST_FILE)
    if not os.path.exists(path):
        if not create:
            return []
        try:
            with open(path, "w", encoding="cp1252", newline="\r\n") as f:
                f.write(CONFLICT_BLACKLIST_DEFAULT)
        except OSError:
            return []
    out = []
    for line in open(path, encoding="cp1252", errors="replace"):
        line = line.split(";", 1)[0].strip()
        if line:
            out.append(line.lower())
    return out


def conflict_blacklisted(name, pats):
    import fnmatch as _fn
    low = name.lower()
    return any(_fn.fnmatch(low, p_) for p_ in pats)


CONFLICT_RULES_HEADER = "; ---- added by --cell-conflicts"

CONFLICT_RULE_NOTE = re.compile(r"^;\s*(?:keep .+ winning|make .+ win) where they conflict\s*$", re.I)


def split_conflict_rules(text):
    """(the rules file without what earlier --cell-conflicts runs added, [(first, second)] those runs added).
    What a run adds is a '; ---- added by --cell-conflicts ...' header and two-plugin [Order] rules ending in
    '; keep X winning / make X win where they conflict'. Those rules are recognised wherever they are, with or
    without their header above them; a rule you lengthened (more than two plugins) is yours and stays."""
    lines = text.splitlines()
    keep, old, i = [], [], 0
    while i < len(lines):
        st = lines[i].strip()
        if st.startswith(CONFLICT_RULES_HEADER):
            i += 1
            continue
        blk = [l.strip() for l in lines[i:i + 4]]
        if (len(blk) == 4 and blk[0].lower() == "[order]" and blk[1] and blk[2]
                and not blk[1].startswith((";", "[")) and not blk[2].startswith((";", "["))
                and CONFLICT_RULE_NOTE.match(blk[3])):
            old.append((blk[1], blk[2]))
            i += 4
            while keep and not keep[-1].strip():         # no stack of blank lines where it was
                keep.pop()
            continue
        keep.append(lines[i])
        i += 1
    return "\n".join(keep).rstrip() + "\n", old


CONFLICT_ANSWERS_FILE = "mwdialog_conflict_answers.json"


def read_conflict_answers(game_dir):
    """{"a.esp|b.esp" (sorted, lower): {"do": "order"|"cell"|"off"|"skip", "plugin": winner or the one
    turned off, "when": ...}}: what you answered for each pair in earlier --cell-conflicts sessions."""
    try:
        with open(os.path.join(game_dir, CONFLICT_ANSWERS_FILE), encoding="utf-8") as f:
            d = json.load(f)
        return d.get("answers", {}) if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def write_conflict_answers(game_dir, answers):
    path = os.path.join(game_dir, CONFLICT_ANSWERS_FILE)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"about": "your answers in mwdialog_check --cell-conflicts, offered as the default next time "
                            "(Enter takes it). Delete an entry, or the file, to be asked fresh.",
                   "answers": dict(sorted(answers.items()))}, f, indent=1)
    os.replace(tmp, path)


CELL_WINNERS_FILE = "mwdialog_cell_winners.txt"


def read_cell_winners(game_dir):
    """{interior name lower: (name, winner, loser)} chosen in --cell-conflicts."""
    path = os.path.join(game_dir, CELL_WINNERS_FILE)
    out = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8", errors="replace"):
            parts = line.rstrip("\r\n").split("\t")
            if line.startswith(";") or len(parts) < 3:
                continue
            out[parts[0].strip().lower()] = (parts[0].strip(), parts[1].strip(), parts[2].strip())
    return out


def write_cell_winners(game_dir, entries):
    path = os.path.join(game_dir, CELL_WINNERS_FILE)
    if not entries:
        if os.path.exists(path):
            os.replace(path, backup_path(path))
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write("; interiors two mods rebuilt, and whose version is used (chosen in --cell-conflicts; --fix builds\n"
                f"; {CELL_WINNER_PATCH} from this; --full starts over without it)\n"
                "; interior<TAB>winning plugin<TAB>losing plugin\n")
        for _k, (cell, w, l) in sorted(entries.items()):
            f.write(f"{cell}\t{w}\t{l}\n")


REDUNDANT_RECORD = "mwdialog_redundant.txt"


def read_redundant(game_dir):
    """(OrderedDict {plugin turned off: (kept plugin, why)}, {frozenset(a, b) you chose to keep both of})."""
    off, both = OrderedDict(), set()
    try:
        with open(os.path.join(game_dir, REDUNDANT_RECORD), "r", encoding="utf-8") as f:
            for line in f:
                s = line.rstrip("\r\n")
                if not s.strip() or s.lstrip().startswith(";"):
                    continue
                parts = s.split("\t")
                if parts[0] == "off" and len(parts) >= 3:
                    off[parts[1].strip()] = (parts[2].strip(), parts[3].strip() if len(parts) > 3 else "")
                elif parts[0] == "both" and len(parts) >= 3:
                    both.add(frozenset((parts[1].strip().lower(), parts[2].strip().lower())))
    except OSError:
        pass
    return off, both


def write_redundant(game_dir, off, both, names=None):
    path = os.path.join(game_dir, REDUNDANT_RECORD)
    if not off and not both:
        if os.path.exists(path):
            os.remove(path)
        return
    names = names or {}
    lines = [f"; {REDUNDANT_RECORD}: what --redundant decided about plugins that do the same job as another.",
             "; off<TAB>plugin<TAB>kept plugin<TAB>why: turned off (--add-all-esp leaves it out; it comes back on by",
             ";   itself when the kept plugin is gone). --redundant-undo NAME (or no name: all) turns it back on.",
             "; both<TAB>A<TAB>B: you chose to keep both; --redundant doesn't ask about the pair again",
             ";   (--redundant-undo with no name forgets these too). --full keeps all of this.", ""]
    lines += [f"off\t{n}\t{k}\t{w}" for n, (k, w) in off.items()]
    for pair in sorted(both, key=sorted):
        a, b = sorted(pair)
        lines.append(f"both\t{names.get(a, a)}\t{names.get(b, b)}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


MERGE_REBUILD_RECORD = "mwdialog_merge_rebuild.txt"


def read_merge_rebuild(game_dir):
    """{merged plugin: [inputs turned off by --redundant]} for merges that must be rebuilt without them."""
    out = OrderedDict()
    try:
        with open(os.path.join(game_dir, MERGE_REBUILD_RECORD), encoding="utf-8") as f:
            for line in f:
                s_ = line.rstrip("\r\n")
                if s_.strip() and not s_.startswith(";"):
                    merged, _, ins = s_.partition("\t")
                    out[merged.strip()] = [i for i in ins.split("|") if i]
    except OSError:
        pass
    return out


def mark_merge_rebuild(game_dir, add):
    rec = read_merge_rebuild(game_dir)
    for merged, ins in add.items():
        rec.setdefault(merged, [])
        rec[merged] += [i for i in ins if i not in rec[merged]]
    write_merge_rebuild(game_dir, rec)


def write_merge_rebuild(game_dir, rec):
    path = os.path.join(game_dir, MERGE_REBUILD_RECORD)
    if not rec:
        if os.path.exists(path):
            os.remove(path)
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write("; Merged plugins that still contain a plugin --redundant turned off. --auto-merge (and --full)\n"
                "; rebuild them without it; --unmerge doesn't bring it back. merged<TAB>input|input\n")
        for merged, ins in rec.items():
            f.write(f"{merged}\t{'|'.join(ins)}\n")


RULES_FILE = "mwdialog_check.rules.txt"

ADDED_MASTERS_RECORD = "mwdialog_added_masters.json"


def read_added_masters(game_dir):
    """{patch: {mod: when}} for masters --sort added to patches."""
    try:
        with open(os.path.join(game_dir, ADDED_MASTERS_RECORD), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


PROMOTED_START = ";; ==== content rules promoted to masters (written by mwdialog_check --sort; don't edit) ===="

PROMOTED_END = ";; ==== end of promoted content rules ===="


def record_bases(game_dir, args=None):
    """staging/downloads/game folders used to store and resolve tagged record paths."""
    if args is None:                              # this run's arguments: mwdialog_check._main keeps them there
        args = getattr(sys.modules.get("mwdialog_check"), "TOP_ARGS", None)
    return MP.path_bases(
        game_dir,
        staging=getattr(args, "vortex_dir", None) if args else None,
        downloads=getattr(args, "vortex_downloads", None) if args else None,
    )


def write_added_masters(game_dir, rec):
    bases = record_bases(game_dir)
    if bases:
        rec = MP.convert_added_masters(rec, bases)
    with open(os.path.join(game_dir, ADDED_MASTERS_RECORD), "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in rec.items() if v}, f, indent=1, sort_keys=True)
    try:
        note_promoted_rules(game_dir, rec)
    except OSError as e:
        print(f"  (could not note the promoted rules in {RULES_FILE}: {e})")


def note_promoted_rules(game_dir, rec):
    """Keep a comment block at the end of the rules file listing each content rule that became a master
    (patch, the mod it now lists, when, why, where its original went). Comments only: the sort ignores them;
    the block is rewritten each time, and a master taken out again drops off it."""
    path = os.path.join(game_dir, RULES_FILE)
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return
    nl = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode(_T.ENC, MW_ERRORS)
    lines = text.splitlines()
    if PROMOTED_START in lines:
        a = lines.index(PROMOTED_START)
        b = lines.index(PROMOTED_END, a) + 1 if PROMOTED_END in lines[a:] else len(lines)
        while a > 0 and not lines[a - 1].strip():
            a -= 1
        lines = lines[:a] + lines[b:]
    block = []
    items = sorted(((p, m, v) for p, ms in rec.items() for m, v in (ms or {}).items()), key=lambda x: x[0].lower())
    if items:
        block = ["", PROMOTED_START,
                 ";; Each was an [Order] rule found from what the patch changes; the patch now lists the mod as a",
                 ";; master, so it always loads after it. A rule of yours putting the patch first takes the master",
                 ";; out again (the original plugin is kept where 'original' says)."]
        for p, m, v in items:
            parts = [x.strip() for x in str(v).split(";")]
            when = parts[0]
            why = next((x[4:].strip() for x in parts if x.startswith("why:")), "content rule")
            orig = next((x[9:].strip() for x in parts if x.startswith("original:")), "")
            block.append(f";;   {p}  +master  {m}   ({why}; {when})")
            if orig:
                block.append(f";;       original: {orig}")
        block.append(PROMOTED_END)
    new = nl.join(lines).rstrip() + nl + (nl.join(block) + nl if block else "")
    if new.encode(_T.ENC, MW_ERRORS) != raw:
        safe_write_bytes(path, new.encode(_T.ENC, MW_ERRORS))
