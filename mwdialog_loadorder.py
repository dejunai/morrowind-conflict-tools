"""mwdialog_loadorder.py - where the load order lives: Morrowind.ini's [Game Files], mwdialog_load_order.txt,
and the mlox-style rule files (parsing only; the sort itself is in mwdialog_check).
"""
from collections import Counter, defaultdict
import glob
import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_text as MT  # noqa: E402
import mwdialog_tes3 as _T  # noqa: E402
from mwdialog_backup import (  # noqa: E402
    bak_home, index_dir)
from mwdialog_tes3 import (  # noqa: E402
    MW_ERRORS, safe_write_bytes)
print = MT.printer()  # noqa: A001


def sort_vanilla(paths):
    """Masters first, then plugins, each by modification date."""
    def key(p):
        is_master = p.lower().endswith(".esm")
        try:
            mt = os.path.getmtime(p)
        except OSError:
            mt = 0
        return (0 if is_master else 1, mt, os.path.basename(p).lower())
    return sorted(paths, key=key)


INI_SECTION_LIMIT = 32767      # Windows' profile-section functions (used by Vortex) stop at this many chars


def game_files_overflow(names):
    """Where a [Game Files] list stops fitting in a 32,767-character ini section:
    (total characters, index of the first entry that is cut, or None if it fits)."""
    total, cut = 0, None
    for i, n in enumerate(names):
        total += len(f"GameFile{i}={n}") + 1
        if cut is None and total > INI_SECTION_LIMIT:
            cut = i
    return total, cut


def warn_overflow(names, indent="  "):
    total, cut = game_files_overflow(names)
    if cut is None:
        return
    print(f"{indent}WARNING: this plugin list is {total:,} characters, over Windows' {INI_SECTION_LIMIT:,}-character "
          f"limit for an ini section.")
    print(f"{indent}  Vortex rewrites Morrowind.ini through that limit: it cuts the list in the middle of entry "
          f"#{cut} ('{names[cut]}') and drops the {len(names) - cut - 1} after it.")
    print(f"{indent}  Fewer plugins is the only way round it: --auto-merge can fold small ones together "
          f"(about {total - INI_SECTION_LIMIT:,} characters need to go).")


LOAD_ORDER_FILE = "mwdialog_load_order.txt"   # our plugin list; Morrowind.ini gets it when a run changes it, and at --play


def ini_game_files(ini):
    try:
        return [v for k, v in read_ini_sections(ini).get("game files", []) if k.lower().startswith("gamefile")]
    except OSError:
        return []


def default_ini(args):
    return args.ini or os.path.join(os.path.dirname(os.path.abspath(args.data_dir)), "Morrowind.ini")


def read_load_order(args):
    """The active plugins, from mwdialog_load_order.txt. The first time, it is made from Morrowind.ini."""
    game_dir = os.path.dirname(os.path.abspath(args.data_dir))
    path = os.path.join(game_dir, LOAD_ORDER_FILE)
    if os.path.isfile(path):
        out = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith(";"):
                    out.append(s)
        return out
    ini = default_ini(args)
    if not os.path.isfile(ini):
        return None
    names = ini_game_files(ini)
    write_load_order(game_dir, names, "made from Morrowind.ini")
    print(f"Created {LOAD_ORDER_FILE} from Morrowind.ini's [Game Files] ({len(names)} plugins). From now on this "
          f"file is the load order; Morrowind.ini only gets it when --play starts the game.", file=sys.stderr)
    return names


LOAD_ORDER_WRITTEN = set()          # game folders whose load order file this run changed


def write_load_order(game_dir, order, note=""):
    """Save the plugin list (the previous one is kept as .bak). Returns the backup's name."""
    LOAD_ORDER_WRITTEN.add(os.path.abspath(game_dir))
    path = os.path.join(game_dir, LOAD_ORDER_FILE)
    bak = bak_home(path) + ".bak"
    if os.path.isfile(path):
        shutil.copy2(path, bak)
    lines = [f"; {LOAD_ORDER_FILE}: the active plugins, in load order (mwdialog_check.py keeps this list;",
             "; Morrowind.ini's [Game Files] is written from it when a run that changed it ends, and by --play).",
             f"; Last changed {time.strftime('%Y-%m-%d %H:%M')}" + (f" by {note}" if note else "") + ". One plugin per line.",
             ""] + list(order)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return os.path.basename(bak)


def truncated_game_files(args):
    """If Morrowind.ini's [Game Files] list was cut at the 32,767-character section limit, return
    (last listed name, the plugin file it was cut from or None, number of entries); otherwise None."""
    if getattr(args, "plugins", None) or getattr(args, "openmw_cfg", None):
        return None
    if os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(args.data_dir)), LOAD_ORDER_FILE)):
        return None                              # our own list is the load order now, not Morrowind.ini
    ini = default_ini(args)
    if not os.path.isfile(ini):
        return None
    names = ini_game_files(ini)
    if not names:
        return None
    total, _cut = game_files_overflow(names)
    if total < INI_SECTION_LIMIT - 64:           # nowhere near the limit: not cut
        return None
    files = {k: p for k, p in index_dir(args.data_dir).items() if k.endswith((".esp", ".esm"))}
    last = names[-1]
    if last.lower() not in files:                # cut in the middle of a name
        longer = [p for k, p in files.items() if k.startswith(last.lower())]
        return last, (os.path.basename(longer[0]) if len(longer) == 1 else None), len(names)
    # ends on a whole name (the half entry dropped too): compare with a recent list this tool backed up;
    # a full-size list that is only a part of an earlier, longer one (whose extra plugins still exist) was cut
    if total < INI_SECTION_LIMIT - 300:
        return None
    baks = sorted(glob.glob(glob.escape(ini) + ".mwdialog-*.bak") + glob.glob(glob.escape(bak_home(ini))
                  + ".mwdialog-*.bak"), key=os.path.getmtime, reverse=True)
    low = [n.lower() for n in names]
    for b in baks[:5]:
        try:
            old = [v for k, v in read_ini_sections(b).get("game files", []) if k.lower().startswith("gamefile")]
        except OSError:
            continue
        if len(old) > len(names) and set(low) <= {n.lower() for n in old}:
            missing = [n for n in old if n.lower() not in set(low) and n.lower() in files]
            if missing:
                return last, None, len(names)
    return None


def read_ini_sections(path):
    sections = defaultdict(list)
    cur = None
    with open(path, "r", encoding=_T.ENC, errors="replace") as f:
        for line in f:
            s = line.strip()
            if s.startswith("[") and s.endswith("]"):
                cur = s[1:-1].strip().lower()
            elif cur and "=" in s and not s.startswith(";"):
                k, v = s.split("=", 1)
                sections[cur].append((k.strip(), v.strip()))
    return sections


def set_game_files(ini, order, note):
    """Save `order` as the load order (mwdialog_load_order.txt next to Morrowind.ini). Returns the backup name."""
    return write_load_order(os.path.dirname(os.path.abspath(ini)), order, note)


def write_ini_game_files(ini, order):
    """Rewrite Morrowind.ini's [Game Files] with `order` (backup first). Returns the backup name."""
    raw = open(ini, "rb").read()
    text = raw.decode(_T.ENC, MW_ERRORS)
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    start = end = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            if start is not None and end is None:
                end = i
            if s[1:-1].strip().lower() == "game files":
                start, end = i, None
    if start is not None and end is None:
        end = len(lines)
    body = [f"GameFile{i}={n}" for i, n in enumerate(order)]
    if start is None:
        new_lines = lines + ["", "[Game Files]"] + body
    else:
        new_lines = lines[:start + 1] + body + ([""] if end < len(lines) else []) + lines[end:]
    base = bak_home(ini)
    original = base + ".mwdialog-original.bak"        # the ini as it was before these tools first changed it
    if not os.path.exists(original):
        with open(original, "wb") as f:
            f.write(raw)
    backup = base + ".mwdialog-play.bak"              # the latest previous version (same name as before)
    with open(backup, "wb") as f:
        f.write(raw)
    stamped = f"{base}.mwdialog-{time.strftime('%Y%m%d-%H%M%S')}.bak"   # and a dated one, never replaced
    if not os.path.exists(stamped):
        with open(stamped, "wb") as f:
            f.write(raw)
    safe_write_bytes(ini, (nl.join(new_lines) + nl).encode(_T.ENC, MW_ERRORS))
    return os.path.basename(stamped)


RULE_TAG = re.compile(r"^\[(order|nearstart|nearend|exact|note|conflict|requires|patch|version)\b[^\]]*\]?",
                      re.I)


def name_matcher(entry):
    """A filename pattern from a rule (mlox wildcards) -> compiled regex, or None for a plain name."""
    if not any(c in entry for c in "*?") and "<ver>" not in entry.lower():
        return None
    out, i = "", 0
    while i < len(entry):
        if entry[i:i + 5].lower() == "<ver>":
            out += r"[_v]?\d+(?:[-_.]?\d+)*[a-z]?"
            i += 5
            continue
        c = entry[i]
        out += ".*" if c == "*" else "." if c == "?" else re.escape(c)
        i += 1
    return re.compile(out + r"\Z", re.I)


BAD_RULE_ENTRIES = []                            # (rules file, line number, entry) of entries that aren't plugins

PLUGIN_EXTS = (".esp", ".esm", ".omwaddon")


def rule_entry_ok(entry):
    """An entry must name a plugin: end in .esp/.esm/.omwaddon, or in a wildcard that can match one."""
    e = entry.strip().lower()
    return e.endswith(PLUGIN_EXTS) or e.endswith(("*", "?")) or re.search(r"\.es[pm]\??$|\.es\?$", e) is not None


def parse_rules(path, text=None):
    """[(kind, [entries], source line)] for Order/NearStart/NearEnd/Exact rules; counts of the others.
    An entry that can't be a plugin (say 'something.txt') is left out and listed in BAD_RULE_ENTRIES."""
    rules, ignored = [], Counter()
    if text is None:
        try:
            with open(path, "r", encoding="cp1252", errors="replace") as f:
                text = f.read()
        except OSError:
            return rules, ignored
    lines = text.splitlines()
    kind, entries, start = None, [], 0

    def flush():
        if kind in ("order", "nearstart", "nearend", "exact") and entries:
            rules.append((kind, list(entries), f"{os.path.basename(path)}:{start}"))

    for no, raw in enumerate(lines, 1):
        m = RULE_TAG.match(raw)
        if m:
            flush()
            kind, entries, start = m.group(1).lower(), [], no
            if kind not in ("order", "nearstart", "nearend", "exact"):
                ignored[kind] += 1
            continue
        if kind not in ("order", "nearstart", "nearend", "exact"):
            continue
        line = raw.split(";", 1)[0].strip()
        if not line or line.startswith("@"):
            continue
        if line.startswith("["):              # an mlox expression or unknown rule: ends this one
            flush()
            kind, entries = None, []
            continue
        if not rule_entry_ok(line):
            key = (path, no, line)
            if key not in BAD_RULE_ENTRIES:
                BAD_RULE_ENTRIES.append(key)
            continue
        entries.append(line)
    flush()
    return rules, ignored


def rule_entry_lines(lines, tag_line):
    """Line indexes (0-based) of the plugin entries of the rule whose tag is on 1-based line tag_line,
    found the same way parse_rules reads them; and the index of its last line."""
    out = []
    for i in range(tag_line, len(lines)):
        raw = lines[i].rstrip("\r\n")
        if RULE_TAG.match(raw):
            break
        line = raw.split(";", 1)[0].strip()
        if not line or line.startswith("@"):
            continue
        if line.startswith("["):
            break
        out.append(i)
    return out
