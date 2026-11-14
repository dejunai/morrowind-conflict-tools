"""Master mismatch guard: is a plugin (usually a compatibility patch) built for the master that is installed?

A patch made for another mod with the same file name, or for an older/newer version of the same mod, loads
without complaint; its edits just point at records that aren't there. The signals, strongest first:

  1. reference resolution (primary): of the IDs the plugin overrides or names (inventory, scripts, spells,
     factions, journal/topic names and objects in its scripts, INFO PNAM/NNAM links, cell references into the
     master) that belong to the master - found in it, or missing but carrying the master's ID prefix -
     how many don't resolve. References an earlier --fix/--clean already removed as "doesn't exist" are read
     back from the fix logs, so cleaning doesn't erase the evidence.
  2. the master size the plugin was saved against - only when it is the ORIGINAL header value: recorded in
     mwdialog_master_sizes.json the first time a mismatch is seen (before --fix syncs it), read from the
     "synced the size recorded for ..." lines in mwdialog_fixes.log / mwdialog_backup\\fixes.archive.txt, or
     taken from the plugin as downloaded (Vortex download archive), when the header has been rewritten.

Verdicts per (plugin, master): "matches", "other version" (most of it lines up; a few references the master no
longer has) or "different mod" (confidence >= DIFFERENT_AT). When the plugin was saved against a master of
exactly the installed size, the verdict is at most "other version" unless the misses are overwhelming: at
least SAME_SIZE_OVERWHELMING (90%) of the references into the master don't resolve, and at least
SAME_SIZE_MIN_MISSES (8) of them (a cell-reference error counts as 3). For "different mod" mwdialog_check
does not sync the header size or strip the dead references (it warns instead), and --disable-mismatched takes
the plugin out of the load order. Log parses and archive reads are cached in mwdialog_mastercheck_cache.json."""
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import time
import zipfile
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_paths as MP  # noqa: E402
import mwdialog_tes3 as T  # noqa: E402
import mwdialog_text as MT  # noqa: E402
print = MT.printer()  # noqa: A001

DIFFERENT_AT = 0.75                      # confidence at or above which a master is called a different mod
SAME_SIZE_OVERWHELMING = 0.9             # same-size master: "different mod" only when at least this share of the
SAME_SIZE_MIN_MISSES = 8                 # references into it, and at least this many, don't resolve
ARCHIVE_CACHE_VERSION = 2                # "archives" entries: all IDs kept, key uses st_mtime_ns
SIZES_RECORD = "mwdialog_master_sizes.json"
CACHE_FILE = "mwdialog_mastercheck_cache.json"
FIX_LOGS = ("mwdialog_fixes.log", os.path.join("mwdialog_backup", "fixes.archive.txt"))
BASE_GAME = {"morrowind.esm", "tribunal.esm", "bloodmoon.esm"}
ARCHIVE_EXT = (".7z", ".zip", ".rar")
NOT_IDS = {"player", "", "self"}

# subrecords that name another record, per record type
REF_SUBS = {
    "NPC_": ("RNAM", "CNAM", "ANAM", "BNAM", "KNAM", "SCRI", "NPCS"),
    "CREA": ("SCRI", "NPCS"),
    "CONT": ("SCRI",),
    "LEVI": ("INAM",), "LEVC": ("CNAM",),
    "INFO": ("ONAM", "RNAM", "CNAM", "FNAM"),
    **{t: ("SCRI", "ENAM") for t in ("ARMO", "CLOT", "WEAP", "BOOK", "MISC", "ALCH", "APPA", "LOCK", "PROB",
                                       "REPA", "LIGH", "INGR", "ACTI", "DOOR")},
}
SCRIPT_CMD_RE = re.compile(
    r"(?i)\b(?:GetJournalIndex|Journal|SetJournalIndex|AddItem|RemoveItem|GetItemCount|PlaceAtPC|PlaceAtMe|"
    r"PlaceItem|PlaceItemCell|StartScript|StopScript|ScriptRunning|AddTopic|AddSpell|RemoveSpell|GetSpell|"
    r"Equip|GetDeadCount|GetDistance|PCJoinFaction|GetPCRank|ModPCFacRep|AiFollow|AiEscort)\s*,?\s*"
    r"(\"[^\"\r\n]+\"|[A-Za-z_][\w.\-']*)")
ARROW_RE = re.compile(r"(\"[^\"\r\n]+\"|[A-Za-z_][\w.\-']*)\s*->")
PREFIX_RE = re.compile(r"^([a-z][a-z0-9]{1,5})_")
LOG_STAMP_RE = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\s+")
LOG_PLUGIN_RE = re.compile(r"^(?P<p>[^:\r\n]+?\.(?:esp|esm|omwaddon)):\s", re.I)
SYNC_RE = re.compile(r"synced the size recorded for '(?P<m>[^']+)' \((?P<a>\d+) -> (?P<b>\d+)\)")
MISSING_RE = re.compile(r"'(?P<id>[^']+)'(?:,)?\s*(?:which\s+)?(?:doesn't|does not) exist\b[^\r\n]*->")
REFGONE_RE = re.compile(r"in master '(?P<m>[^']+)', which no longer exists there")
ADDED_RE = re.compile(r"added master (?P<m>.+?\.(?:esp|esm))(?: removed)? \(", re.I)


# ---------------------------------------------------------------------------------------------- plugin facts

def _subs(body):
    """Subrecords of one record; after a bad subrecord size, the ones read before it."""
    out = []
    try:
        for x in T.iter_subs(body):
            out.append(x)
    except T.FormatError:
        pass
    return out


def header_masters(data):
    """[(master name, size the plugin was saved against or None)] from the TES3 header."""
    out = []
    try:
        _off, tag, _flags, body = next(T.iter_records(data))
    except (StopIteration, T.FormatError):
        return []
    if tag != "TES3":
        return []
    for n, v in _subs(body):
        if n == "MAST":
            out.append([T.cstr(v), None])
        elif n == "DATA" and out and out[-1][1] is None and len(v) >= 8:
            out[-1][1] = struct.unpack_from("<Q", v)[0]
    return [tuple(x) for x in out]


def script_ids(text):
    ids = set()
    for line in text.splitlines():
        line = line.split(";", 1)[0]
        if not line.strip():
            continue
        for mo in SCRIPT_CMD_RE.finditer(line):
            ids.add(mo.group(1).strip('"').strip().lower())
        for mo in ARROW_RE.finditer(line):
            ids.add(mo.group(1).strip('"').strip().lower())
    return {i for i in ids if i not in NOT_IDS and not re.fullmatch(r"[\d.\-]+", i)}


def plugin_facts(data):
    """What a plugin defines and what it names: {"defs": set, "refs": set, "dials": set,
    "links": [(topic, info id)], "info_topic": {info id: topic}}; ids lowercase."""
    defs, refs, dials, links = set(), set(), set(), []
    topic = None

    def one(tag, body):
        nonlocal topic, refs
        if tag == "TES3":
            return
        subs = _subs(body)
        if tag == "DIAL":
            topic = next((T.cstr(v).lower() for n, v in subs if n == "NAME"), None)
            if topic:
                dials.add(topic)
            return
        if tag == "INFO":
            for n, v in subs:
                if n == "INAM":
                    defs.add(T.cstr(v).lower())
                elif n in ("PNAM", "NNAM") and T.cstr(v):
                    links.append((topic, T.cstr(v).lower()))
                elif n == "BNAM":
                    refs |= script_ids(T.cstr(v))
        elif tag == "SCPT":
            for n, v in subs:
                if n == "SCHD":
                    defs.add(T.cstr(v[:32]).lower())
                elif n == "SCTX":
                    refs |= script_ids(T.cstr(v))
        elif tag not in ("CELL", "LAND", "PGRD", "GMST", "SKIL", "MGEF", "TES3"):
            nm = next((T.cstr(v).lower() for n, v in subs if n == "NAME"), None)
            if nm:
                defs.add(nm)
        for n, v in subs:
            if n in REF_SUBS.get(tag, ()):
                refs.add(T.cstr(v).lower())
            elif n in ("NPCO", "CNTO") and tag in ("NPC_", "CREA", "CONT") and len(v) >= 5:
                refs.add(T.cstr(v[4:]).lower())

    records = T.iter_records(data)
    while True:                       # a bad record size ends the walk: nothing after it can be found
        try:
            _off, tag, _flags, body = next(records)
        except (StopIteration, T.FormatError):
            break
        try:
            one(tag, body)
        except (T.FormatError, struct.error, ValueError, IndexError):
            continue                  # one unreadable record doesn't hide the rest of the plugin
    refs = {r for r in refs if r and r not in NOT_IDS}
    return {"defs": defs, "refs": refs, "dials": dials, "links": links}


_PROFILE_MEMO = {}


def master_profile(path, memo=None, refresh=False):
    """IDs a master defines (objects, scripts, topics, response ids) and its main ID prefixes. Memoised by
    path, size and mtime_ns; refresh=True reads the file again."""
    if memo is None:
        memo = _PROFILE_MEMO
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (os.path.normcase(os.path.abspath(path)), st.st_size, st.st_mtime_ns)
    if key in memo and not refresh:
        return memo[key]
    try:
        data = T.read_plugin_bytes(path)
    except OSError:
        return None
    facts = plugin_facts(data)
    ids = facts["defs"] | facts["dials"]
    pref = Counter(mo.group(1) for i in ids for mo in [PREFIX_RE.match(i)] if mo)
    total = max(1, len(ids))
    top = {p for p, c in pref.items() if c >= 3 and c / total >= 0.05}
    memo[key] = {"ids": ids, "dials": facts["dials"], "prefixes": top}
    return memo[key]


def prefix_of(i):
    mo = PREFIX_RE.match(i)
    return mo.group(1) if mo else None


# -------------------------------------------------------------------------------------------------- caching

def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_json(path, obj):
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=1, sort_keys=True)
        os.replace(tmp, path)
    except OSError:
        pass


# The cache names files: the fix logs it parsed ("logs" keys), the download archives it read ("archives" keys,
# "<path>|<size>|<mtime_ns>|<plugin>", and each copy's "archive") and the archive a verdict came from
# ("from_archive"). On disk they are stored like the other records: game:/staging:/downloads: plus a path relative
# to that folder (mwdialog_paths.store_path). In memory they are absolute, as the code compares them. Older
# absolute entries are read as they are and stored tagged on the next save; a path under none of the folders is
# kept as it is (and named once); a tag whose folder isn't known this run is left as it is.

def _cache_paths(cache, conv_key, conv_val):
    """A copy of the cache with every path it holds passed through conv_key (dictionary keys) / conv_val."""
    out = dict(cache)
    if isinstance(cache.get("logs"), dict):
        out["logs"] = {conv_key(k): v for k, v in cache["logs"].items()}
    if isinstance(cache.get("archives"), dict):
        arcs = {}
        for k, copies in cache["archives"].items():
            parts = k.rsplit("|", 3)                 # a Windows path can't hold "|"; nor can a plugin name
            if len(parts) == 4:
                k = "|".join([conv_key(parts[0])] + parts[1:])
            if isinstance(copies, list):
                copies = [dict(c, archive=conv_val(c["archive"])) if isinstance(c, dict) and c.get("archive")
                          else c for c in copies]
            arcs[k] = copies
        out["archives"] = arcs
    if isinstance(cache.get("verdicts"), dict):
        out["verdicts"] = {k: (dict(v, from_archive=conv_val(v["from_archive"]))
                               if isinstance(v, dict) and v.get("from_archive") else v)
                           for k, v in cache["verdicts"].items()}
    return out


def load_cache(path, bases):
    """mwdialog_mastercheck_cache.json with its paths absolute (tagged ones resolved against `bases`)."""
    def val(p):
        return MP.resolve_stored(p, bases, missing_ok=True)

    def key(p):
        r = val(p)
        return os.path.normcase(r) if MP.is_abs_path(r) else r
    cache = _load_json(path)
    return _cache_paths(cache, key, val) if isinstance(cache, dict) else {}


def save_cache(path, cache, bases):
    """Write the cache with its paths tagged. Returns the paths under none of `bases` (kept as they are)."""
    outside = []

    def val(p):
        s = MP.store_path(p, bases)
        if MP.is_abs_path(s) and s not in outside:
            outside.append(s)
        return s
    _save_json(path, _cache_paths(cache, val, val))
    return outside


def read_sizes_record(game_dir):
    return _load_json(os.path.join(game_dir, SIZES_RECORD))


def note_original_sizes(game_dir, size_mismatch):
    """Keep the size each plugin's header recorded for a master the first time it differs from the installed
    master - before --fix syncs it, so the original value survives the rewrite."""
    if not size_mismatch:
        return
    path = os.path.join(game_dir, SIZES_RECORD)
    rec = _load_json(path)
    changed = False
    for plugin, master, expected, actual in size_mismatch:
        ent = rec.setdefault(plugin.lower(), {"plugin": plugin, "masters": {}})
        if master.lower() not in ent["masters"]:
            ent["masters"][master.lower()] = {"master": master, "original": expected, "installed": actual,
                                              "seen": time.strftime("%Y-%m-%d %H:%M:%S")}
            changed = True
    if changed:
        _save_json(path, rec)


# ------------------------------------------------------------------------------------------------ fix logs

def _empty_log_facts():
    return {"syncs": {}, "missing": {}, "refgone": {}, "added": {}}


def _merge_line(facts, line):
    line = LOG_STAMP_RE.sub("", line.rstrip("\r\n"))
    mo = LOG_PLUGIN_RE.match(line)
    if not mo:
        return
    p = mo.group("p").strip().lower()
    rest = line[mo.end():]
    s = SYNC_RE.search(rest)
    if s:
        ent = facts["syncs"].setdefault(p, {})
        m = s.group("m").lower()
        if m not in ent:                        # the oldest sync holds the original header value
            ent[m] = [int(s.group("a")), int(s.group("b"))]
        else:
            ent[m][1] = int(s.group("b"))
        return
    g = REFGONE_RE.search(rest)
    if g:
        ent = facts["refgone"].setdefault(p, {})
        ent[g.group("m").lower()] = ent.get(g.group("m").lower(), 0) + 1
        return
    a = ADDED_RE.search(rest)
    if a and rest.startswith("added master"):
        lst = facts["added"].setdefault(p, [])
        if a.group("m").lower() not in lst:
            lst.append(a.group("m").lower())
        return
    x = MISSING_RE.search(rest)
    if x:
        lst = facts["missing"].setdefault(p, [])
        i = x.group("id").lower()
        if i not in lst and len(lst) < 500:
            lst.append(i)


def _merge_facts(into, more):
    for p, ms in more["syncs"].items():
        ent = into["syncs"].setdefault(p, {})
        for m, ab in ms.items():
            ent.setdefault(m, ab)
    for p, ids in more["missing"].items():
        lst = into["missing"].setdefault(p, [])
        lst += [i for i in ids if i not in lst]
    for p, ms in more["refgone"].items():
        ent = into["refgone"].setdefault(p, {})
        for m, c in ms.items():
            ent[m] = ent.get(m, 0) + c
    for p, ms in more["added"].items():
        lst = into["added"].setdefault(p, [])
        lst += [x for x in ms if x not in lst]


KEYWORDS = (b"synced the size", b"exist", b"added master")


def parse_log(path, cached=None):
    """Stream-parse one fix log; only lines with the key phrases are decoded. An unchanged start of file and a
    grown size continue from the cached offset (the archive is append-only); a rotated log (its head cut off)
    is parsed again from the start."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    with open(path, "rb") as f:
        first = f.read(4096)
        head = hashlib.sha1(first).hexdigest()
        facts, start = _empty_log_facts(), 0
        hl = (cached or {}).get("headlen", 0)
        if cached and hashlib.sha1(first[:hl]).hexdigest() == cached.get("head") and len(first) >= hl \
                and cached.get("offset", 0) <= st.st_size:
            facts, start = cached["facts"], cached["offset"]
            if start == st.st_size:
                return dict(cached, head=head, headlen=len(first))
        f.seek(start)
        offset = start
        pending = None                          # a dated line plus any wrap() continuation lines
        def _flush(blob):
            if any(k in blob for k in KEYWORDS):
                _merge_line(facts, blob.decode("utf-8", "replace"))
        for raw in f:
            if not raw.endswith(b"\n"):          # a line still being written: next time
                if pending is not None:
                    _flush(pending)
                    pending = None
                break
            offset += len(raw)
            if pending is not None and raw[:1] in (b" ", b"\t"):
                piece = raw.lstrip().rstrip(b"\r\n")
                nl = b"\r\n" if pending.endswith(b"\r\n") else b"\n"
                pending = pending.rstrip(b"\r\n") + b" " + piece + nl
                continue
            if pending is not None:
                _flush(pending)
            pending = raw
        if pending is not None:
            _flush(pending)
    return {"head": head, "headlen": len(first), "offset": offset, "size": st.st_size, "facts": facts}


def log_facts(game_dir, cache, extra_logs=()):
    """Everything the fix logs say, merged: oldest sync per (plugin, master), removed references, ..."""
    logs = cache.setdefault("logs", {})
    out = _empty_log_facts()
    for rel in list(FIX_LOGS) + list(extra_logs):
        path = rel if os.path.isabs(rel) else os.path.join(game_dir, rel)
        key = os.path.normcase(os.path.abspath(path))
        res = parse_log(path, logs.get(key))
        if res is None:
            continue
        logs[key] = res
    # archive first (older entries), then the live log
    for key in sorted(logs, key=lambda k: 0 if k.endswith("fixes.archive.txt") else 1):
        _merge_facts(out, logs[key]["facts"])
    return out


# ---------------------------------------------------------------------------------------- download archives

def vortex_settings_downloads():
    """Vortex's download folder from its settings, or None. Kept as a thin wrapper around mwdialog_paths."""
    try:
        return MP.resolve_downloads(required=False)
    except MP.VortexPathError:
        return None


def downloads_dir(args=None, required=False):
    """The Morrowind Vortex download folder. CLI --vortex-downloads / --downloads wins; otherwise
    Vortex's own setting. No hardcoded fallback."""
    cli = getattr(args, "vortex_downloads", None) if args else None
    return MP.resolve_downloads(cli=cli, required=required)


def find_7z(game_dir=None, required=False):
    """7-Zip: PATH (shutil.which('7z')), then <game>\\tools\\7z. No registry, no Program Files paths."""
    return MP.find_7z(game_dir=game_dir, required=required)


def archives_for(dl, mod_folder):
    """Download archives named like the Vortex staging folder (Vortex names the folder after the archive)."""
    if not dl or not mod_folder:
        return []
    try:
        names = os.listdir(dl)
    except OSError:
        return []
    low = mod_folder.lower()
    exact = [n for n in names if n.lower().endswith(ARCHIVE_EXT) and os.path.splitext(n)[0].lower() == low]
    if exact:
        return [os.path.join(dl, n) for n in exact]
    stem = re.split(r"-\d{3,}-", mod_folder)[0].lower()       # "Mod Name-12345-1-0-..." -> "mod name"
    return [os.path.join(dl, n) for n in names if n.lower().endswith(ARCHIVE_EXT) and n.lower().startswith(stem)]


def plugins_in_archive(archive, plugin_name, game_dir=None):
    """[(entry name, bytes)] for every copy of `plugin_name` in the archive (several option folders may
    have one)."""
    want = plugin_name.lower()
    out = []
    if archive.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(archive) as z:
                for e in z.namelist():
                    if e.replace("\\", "/").rsplit("/", 1)[-1].lower() == want:
                        out.append((e, z.read(e)))
            return out
        except (OSError, zipfile.BadZipFile):
            pass
    need = archive.lower().endswith((".7z", ".rar"))
    exe = find_7z(game_dir, required=need)
    if not exe:
        return out
    try:
        listing = subprocess.run([exe, "l", "-slt", "-ba", archive], capture_output=True, timeout=300).stdout
    except (OSError, subprocess.SubprocessError):
        return out
    for line in listing.decode("utf-8", "replace").splitlines():
        if line.startswith("Path = "):
            e = line[7:].strip()
            if e.replace("\\", "/").rsplit("/", 1)[-1].lower() == want:
                try:
                    data = subprocess.run([exe, "e", "-so", archive, e], capture_output=True, timeout=600).stdout
                except (OSError, subprocess.SubprocessError):
                    continue
                if data[:4] == b"TES3":
                    out.append((e, data))
    return out


def original_from_archive(plugin_name, installed_data, mod_folder, dl, cache, game_dir=None):
    """The plugin as downloaded: {"archive", "entry", "masters": [(name, size)], "refs": [...], "defs": [...]}
    or None. The copy whose records best match the installed file wins (a copy sharing fewer IDs with it than it
    differs by is not used). Cached by archive size and mtime_ns, every ID kept; entries from an older cache
    layout (cache["archives_version"] other than ARCHIVE_CACHE_VERSION) are dropped and read again."""
    if cache.get("archives_version") != ARCHIVE_CACHE_VERSION:
        cache["archives"] = {}
        cache["archives_version"] = ARCHIVE_CACHE_VERSION
    arcs = cache.setdefault("archives", {})
    inst = plugin_facts(installed_data)
    best = None
    for arc in archives_for(dl, mod_folder):
        try:
            st = os.stat(arc)
        except OSError:
            continue
        key = f"{os.path.normcase(arc)}|{st.st_size}|{st.st_mtime_ns}|{plugin_name.lower()}"
        copies = arcs.get(key)
        if copies is None:
            copies = []
            for entry, data in plugins_in_archive(arc, plugin_name, game_dir=game_dir):
                f = plugin_facts(data)
                copies.append({"archive": arc, "entry": entry, "masters": header_masters(data),
                               "refs": sorted(f["refs"]), "defs": sorted(f["defs"]),
                               "links": [list(x) for x in f["links"]]})
            arcs[key] = copies
        for c in copies:
            defs = set(c["defs"])
            score = len(defs & inst["defs"]) - len(defs ^ inst["defs"])
            if score < 0:
                continue
            if best is None or score > best[0]:
                best = (score, c)
    return best[1] if best else None


# ------------------------------------------------------------------------------------------------ verdicts

_STEM_RE = {}


def candidate_masters(plugin, declared, loaded, original_mod_guess=None):
    """{master name: why}: masters in the header, plus loaded plugins the file name says it patches
    ('X - Y Compatibility Patch.esp' -> X.esp and Y.esp)."""
    out = {}
    for n in declared:
        if n.lower() not in BASE_GAME:
            out[n] = "listed as a master"
    stem = os.path.splitext(plugin)[0].lower()
    for n in loaded:
        s = os.path.splitext(n)[0].lower()
        if n.lower() == plugin.lower() or n.lower() in BASE_GAME or len(s) < 5 or n in out:
            continue
        pat = _STEM_RE.get(s)                     # one compiled pattern per plugin name, not one per pair
        if pat is None:
            pat = _STEM_RE[s] = re.compile(r"(?<![a-z0-9])" + re.escape(s) + r"(?![a-z0-9])")
        if pat.search(stem):
            out[n] = "named in the file name"
    return out


def assess(facts, profile, defined_anywhere, removed=(), refgone=0, cell_ref_errors=False,
           original_size=None, installed_size=None):
    """(confidence that the plugin was made for a different mod, kind, details)."""
    ids, top = profile["ids"], profile["prefixes"]
    hits, misses = set(), set()
    own = facts["defs"]
    for d in own:                                     # records it overrides from the master
        if d in ids:
            hits.add(d)
    for r in facts["refs"] | set(removed):
        if r in own:
            continue
        if r in ids:
            hits.add(r)
        elif r not in defined_anywhere and prefix_of(r) in top:
            misses.add(r)
    for t, link in facts["links"]:
        if t in profile["dials"] and link not in own:
            (hits if link in ids else misses if link not in defined_anywhere else set()).add(link)
    n_miss = len(misses) + refgone + (3 if cell_ref_errors else 0)
    total = len(hits) + n_miss
    size_note = None
    if original_size is not None and installed_size is not None:
        size_note = "same size" if original_size == installed_size else "other size"
    if total == 0:
        conf, kind = (0.5, "no ties") if facts["defs"] or facts["refs"] else (0.0, "no ties")
    else:
        ratio = n_miss / total
        conf = ratio * min(1.0, total / 4)            # little evidence: less sure either way
        if size_note == "other size" and ratio > 0:
            conf = min(0.97, conf + 0.1)
        if size_note == "same size" and not (ratio >= SAME_SIZE_OVERWHELMING and n_miss >= SAME_SIZE_MIN_MISSES):
            conf = min(conf, round(DIFFERENT_AT - 0.01, 2))   # saved against this very file: a few misses are bugs
        kind = "different mod" if conf >= DIFFERENT_AT else ("other version" if n_miss else "matches")
    return round(conf, 2), kind, {"hits": len(hits), "misses": sorted(misses)[:20], "refgone": refgone,
                                  "cell_ref_errors": bool(cell_ref_errors), "size": size_note,
                                  "total": total}


_STAGING_INDEX = {}


def _staging_index(vortex_root, refresh=False):
    """filename lower -> first mod folder that has that file at its top level. Built once per root;
    refresh=True lists the staging folder again."""
    root = os.path.normcase(os.path.abspath(vortex_root))
    idx = None if refresh else _STAGING_INDEX.get(root)
    if idx is not None:
        return idx
    idx = {}
    try:
        for d in os.scandir(vortex_root):
            if not d.is_dir():
                continue
            try:
                for x in os.scandir(d.path):
                    if x.is_file():
                        idx.setdefault(x.name.lower(), d.name)
            except OSError:
                continue
    except OSError:
        idx = {}
    _STAGING_INDEX[root] = idx
    return idx


def clear_caches():
    """Forget the staging index and the master profiles read this run (a long-running caller, after mods or
    the staging folder changed). The on-disk mwdialog_mastercheck_cache.json is not touched."""
    _STAGING_INDEX.clear()
    _PROFILE_MEMO.clear()


def staging_folder_of(path, vortex_root, mw):
    """The Vortex mod folder a deployed plugin came from (hard link, else a file of that name in staging)."""
    root = os.path.normcase(os.path.abspath(vortex_root)) if vortex_root else None
    try:
        for other in mw.hard_link_names(path):
            o = os.path.normcase(os.path.abspath(other))
            if root and o.startswith(root + os.sep):
                return os.path.relpath(o, root).split(os.sep)[0]
    except Exception:
        pass
    if vortex_root and os.path.isdir(vortex_root):
        return _staging_index(vortex_root).get(os.path.basename(path).lower())
    return None


def check(world, mw, args=None):
    """Judge every .esp's masters (listed or named); report; returns {(plugin lower, master lower): verdict}.
    Called from World.check before the header checks."""
    r = world.r
    data_dir = getattr(world, "args_data_dir", None)
    if not data_dir:
        return {}
    game_dir = os.path.dirname(os.path.abspath(data_dir))
    note_original_sizes(game_dir, world.size_mismatch)
    vortex_root = getattr(getattr(world, "vortex", None), "root", None) or getattr(args, "vortex_dir", None)
    dl = None if getattr(args, "no_archive_lookup", False) else downloads_dir(args, required=False)
    bases = MP.path_bases(game_dir, staging=vortex_root, downloads=dl or getattr(args, "vortex_downloads", None))
    cache_path = os.path.join(game_dir, CACHE_FILE)
    cache = load_cache(cache_path, bases)
    fix_log = getattr(args, "fix_log", None)
    extra = [fix_log] if fix_log and os.path.isabs(fix_log) else ([os.path.join(game_dir, fix_log)]
                                                                     if fix_log else [])
    logs = log_facts(game_dir, cache, [e for e in extra if os.path.basename(e) != FIX_LOGS[0]
                                       or os.path.dirname(os.path.abspath(e)) != game_dir])
    sizes = read_sizes_record(game_dir)
    evidence = cache.setdefault("evidence", {})
    defined = set(world.all_ids) | set(world.topics) | set(world.info_home)
    names = {n: os.path.basename(world.paths[n]) if n in world.paths else n for n in world.loaded}
    loaded = [names[n] for n in world.loaded]
    verdicts = {}
    for plugin_l in world.loaded:
        plugin = names.get(plugin_l, plugin_l)
        path = world.paths.get(plugin_l)
        if not path or not plugin_l.endswith(".esp") or mw.is_our_patch(plugin):
            continue
        declared = world.masters.get(plugin_l, [])
        cands = candidate_masters(plugin, declared, [x for x in loaded if x.lower() != plugin_l])
        if not cands:
            continue
        try:
            data = T.read_plugin_bytes(path)
        except OSError:
            continue
        facts = plugin_facts(data)
        hdr = {n.lower(): s for n, s in header_masters(data)}
        removed = logs["missing"].get(plugin_l, [])
        rewritten = plugin_l in logs["syncs"] or plugin_l in logs["added"]
        original = None                                   # the downloaded copy, when the header was rewritten
        for master, why in cands.items():
            ml = master.lower()
            mpath = world.paths.get(ml)
            prof = master_profile(mpath) if mpath else None
            if prof is None:
                continue
            inst_size = world.file_sizes.get(ml)
            orig, src = None, None
            if ml in logs["syncs"].get(plugin_l, {}):
                orig, src = logs["syncs"][plugin_l][ml][0], "fix log"
            elif ml in sizes.get(plugin_l, {}).get("masters", {}):
                orig, src = sizes[plugin_l]["masters"][ml]["original"], SIZES_RECORD
            elif ml in hdr and ml not in [x.lower() for x in logs["added"].get(plugin_l, [])] and not rewritten:
                orig, src = hdr[ml], "header"
            f2, rm = facts, removed
            if dl and (rewritten or orig is None) and original is None:
                folder = staging_folder_of(path, vortex_root, mw)
                original = original_from_archive(plugin, data, folder, dl, cache, game_dir=game_dir) or False
            if original:
                om = {n.lower(): s for n, s in original["masters"]}
                if orig is None or src == "header":
                    if ml in om:
                        orig, src = om[ml], "download archive"
                f2 = {"defs": facts["defs"], "refs": facts["refs"] | set(original["refs"]),
                      "dials": facts["dials"], "links": facts["links"] + [tuple(x) for x in original["links"]]}
                rm = list(removed)
            # references seen missing on earlier runs (a --fix since may have removed them from the file)
            seen = evidence.get(f"{plugin_l}|{ml}", [])
            rm = list(rm) + [x for x in seen if x not in rm]
            conf, kind, info = assess(f2, prof, defined, rm, logs["refgone"].get(plugin_l, {}).get(ml, 0),
                                      (plugin_l, ml) in world.ref_error_masters, orig, inst_size)
            v = {"plugin": plugin, "master": master, "why": why, "confidence": conf, "kind": kind,
                 "original_size": orig, "size_source": src, "installed_size": inst_size,
                 "from_archive": (original or {}).get("archive") if original else None, **info}
            verdicts[(plugin_l, ml)] = v
            if info["misses"]:
                evidence[f"{plugin_l}|{ml}"] = sorted(set(seen) | set(info["misses"]))[:500]
            _report(r, v)
    cache["verdicts"] = {f"{p}|{m}": v for (p, m), v in verdicts.items() if v["kind"] != "matches"}
    outside = save_cache(cache_path, cache, bases)
    if outside:
        print(f"  {CACHE_FILE}: {len(outside)} path(s) under none of the game, staging and download folders, kept "
              f"as they are, e.g. {outside[0]}", file=sys.stderr)
    return verdicts


def _report(r, v):
    p, m, pct = v["plugin"], v["master"], int(round(v["confidence"] * 100))
    size = ""
    if v["original_size"] is not None and v["installed_size"] is not None:
        size = (f"; it was saved against a {v['original_size']}-byte '{m}' ({v['size_source']}), the installed one is "
                f"{v['installed_size']} bytes")
    ex = ", ".join(v["misses"][:5])
    if v["kind"] == "different mod":
        r.add("WARN", p, "", "", f"made for a different '{m}' than the one installed (confidence {pct}%): "
                                 f"{v['total'] - v['hits']} of {v['total']} references into it don't resolve"
                                 + (f" ({ex})" if ex else "") + size
                                 + "; its header and dead references are left alone. Get the matching version, or "
                                   "take it out of the load order (--disable-mismatched)")
    elif v["kind"] == "other version":
        r.add("WARN", p, "", "",
              f"made for another version of '{m}' (confidence it is a different mod: {pct}%): "
              f"{v['total'] - v['hits']} of {v['total']} references into it are gone"
              + (f" ({ex})" if ex else "") + size + "; the rest lines up, so it stays enabled")
    elif v["kind"] == "no ties" and v["why"] == "listed as a master" and v["confidence"] >= 0.5:
        r.add("INFO", p, "", "", f"lists '{m}' as a master but none of its records override or name anything in it "
                                 f"(confidence it is a different mod: {pct}%)")


def mismatched(verdicts, threshold=DIFFERENT_AT):
    return {p for (p, _m), v in verdicts.items() if v["kind"] == "different mod" and v["confidence"] >= threshold}


def disable(game_dir, order, plugins, mw, fix_log=None):
    """Take `plugins` (lowercase names) out of the load order. Returns the names removed."""
    gone = [n for n in order if n.lower() in plugins]
    if not gone:
        return []
    mw.write_load_order(game_dir, [n for n in order if n.lower() not in plugins],
                        "made for a different master: " + ", ".join(gone))
    if fix_log:
        try:
            with open(fix_log if os.path.isabs(fix_log) else os.path.join(game_dir, fix_log), "a",
                      encoding="utf-8") as lf:
                for n in gone:
                    lf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {n}: taken out of the load order "
                             f"(made for a different master; --disable-mismatched)\n")
        except OSError:
            pass
    return gone
