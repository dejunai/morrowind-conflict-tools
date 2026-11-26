r"""mwdialog_offlayout.py - the one place and the one layout for what these tools set aside:

    <staged mod folder>\Off\<plugin>\<reason>\<path the file had in the mod>

Off is never deployed by the managers (Vortex deploys everything in staging, so each mod keeps its own Off tree
and the per-plugin folder tells the files of different mods apart). docs\OFF-LAYOUT.md is the specification;
this module is its code: the reason names, the owner (<plugin>) rule, the migration of the older layouts and
the MAX_PATH guard that vortex_tidy, mwdialog_generated and mwdialog_assets share. Python 3.9+.
"""
import json
import os
import re

MAX_PATH_CHARS = 259                  # longest full path a program without long-path support can open
LIST_NAME = "max_path_too_long.txt"   # Off\<plugin>\<this>: files tools did not move because of MAX_PATH

# (reason, what is in it): the fixed list. Written exactly like this (case matters for the tools' output;
# matching is case-insensitive). Every older spelling maps to one of these (LEGACY).
REASONS = (
    ("OpenMW", "OpenMW-only content (scripts, l10n, a whole OpenMW package) that Morrowind cannot use"),
    ("normal maps", "normal-map textures; only OpenMW uses them"),
    ("broken", "an asset that can't be repaired (empty, wrong format, truncated, crashes the game); "
               "a stand-in took its place"),
    ("orphaned animations", "animation files whose model exists nowhere"),
    ("unused assets", "textures and sounds nothing refers to, and empty files"),
    ("ascii", "a file whose name has non-standard (non-ASCII) characters; the original under its old name"),
    ("shortened paths", "the original of a file whose too-long path was shortened (or that was edited to name "
                        "the short path)"),
    ("converted sounds", "the original of a sound that was converted or repaired"),
    ("converted textures", "the original of a texture that was converted or reduced"),
    ("converted splash screens", "the original of a splash screen that was converted"),
    ("fixed text keys", "the original of an animation or model whose text keys were fixed"),
    ("fixed texture paths", "the original of a model whose texture paths were fixed"),
    ("plugin repairs", "a plugin as it was before a tool changed it (masters added, header or dead references "
                       "fixed)"),
    ("repaired originals", "the original of a file a tool changed, when no more specific reason applies"),
    ("lua repairs", "a Lua file as it was before a tool patched it"),
    ("disabled plugins", "plugin files (and their archives) put aside by hand or by a tool so they don't load"),
    ("superseded plugins", "plugin files a newer install replaced"),
    ("duplicate omwaddon", "an .omwaddon kept because its .esp name was already taken"),
    ("redundant splash sources", "splash images a better copy made redundant"),
    ("executables", "programs, libraries and scripts a mod shipped; never deployed into Data Files"),
    ("packaging metadata", "installer and packaging files that are not part of the mod"),
    ("packed into bsa", "loose files that were packed into a BSA archive"),
    ("unused fomod options", "plugin choices of FOMOD options that were not installed"),
    ("replaced files", "files an install replaced"),
    ("protected textures", "textures kept when an install would have replaced them"),
    ("altered assets", "files a plugin deployed that changed afterwards, kept instead of deleted"),
)
_CANON = {n.lower(): n for n, _m in REASONS}

# older spellings (lower case) -> reason. Includes the names the conflict tools used as "features" and the
# human-readable ones MWManager used.
LEGACY = {
    "openmw": "OpenMW", "openmw-addon-duplicate": "duplicate omwaddon",
    "damaged assets": "broken",
    "orphaned": "orphaned animations", "orphan": "orphaned animations",
    "unused": "unused assets",
    "names": "ascii", "non-ascii": "ascii", "reprocessed filenames": "ascii",
    "longpaths": "shortened paths", "long paths": "shortened paths",
    "sound": "converted sounds", "reprocessed sounds": "converted sounds",
    "textures": "converted textures", "reprocessed textures": "converted textures",
    "splash screens": "converted splash screens",
    "text keys": "fixed text keys", "reprocessed unix line joins": "fixed text keys",
    "texture paths": "fixed texture paths", "reprocessed texture paths": "fixed texture paths",
    "added masters": "plugin repairs", "cell references": "plugin repairs",
    "reprocessed plugin headers": "plugin repairs", "original plugin headers": "plugin repairs",
    "plugin-repair": "plugin repairs", "plugin-repairs": "plugin repairs",
    "converted": "repaired originals", "repair": "repaired originals",
    "luarepair": "lua repairs", "luarepairs": "lua repairs",
    "splash": "redundant splash sources",
    "bsa packed": "packed into bsa", "bsa-pack": "packed into bsa",
    "fomod option plugin choices": "unused fomod options",
    "replaced": "replaced files",
}
# a game or support folder: what is below it is a path in the mod (the layouts without a reason)
GAME_TOPS = {"meshes", "textures", "icons", "sound", "sounds", "music", "bookart", "splash", "fonts", "video",
             "distantland", "mwse", "mge3", "shaders", "grass", "mcpatch"}
PLUGIN_EXT = (".esp", ".esm", ".omwaddon", ".omwgame")
EXEC_EXT = {".exe", ".dll", ".bat", ".cmd", ".pl", ".py", ".ps1", ".sh", ".asi", ".jar"}
FALLBACK_NAME = "OpenMWMod"
MANIFEST = "omw2mwse-manifest.json"
REPAIRED = "repaired originals"


def reason_for(name):
    """The reason a name (any spelling, any case) stands for; ValueError when it is none of them."""
    low = (name or "").strip().lower()
    if low in _CANON:
        return _CANON[low]
    if low in LEGACY:
        return LEGACY[low]
    raise ValueError("not an Off reason: %r" % (name,))


def is_reason(name):
    try:
        reason_for(name)
        return True
    except ValueError:
        return False


def is_canonical(name):
    """The name is one of the fixed reasons (case doesn't matter), not an older spelling."""
    return (name or "").strip().lower() in _CANON


def sanitize(name):
    """The converter's mod_name_for rule: everything but letters, digits, _ and - removed."""
    return re.sub(r"[^A-Za-z0-9_\-]", "", name or "") or FALLBACK_NAME


def _list(d):
    try:
        return os.listdir(d)
    except OSError:
        return []


def _isdir(p):
    return os.path.isdir(xp(p))


def _isfile(p):
    return os.path.isfile(xp(p))


def xp(p):
    r"""p with Windows' \\?\ prefix when it is long, so it can still be opened; unchanged elsewhere."""
    if os.name != "nt" or len(p) < 240 or p.startswith("\\\\?\\"):
        return p
    return "\\\\?\\" + os.path.abspath(p)


def plain(p):
    return p[4:] if p.startswith("\\\\?\\") else p


def too_long(path):
    """The full path has more characters than Windows' MAX_PATH leaves (259)."""
    return len(plain(os.path.abspath(path))) > MAX_PATH_CHARS


def off_dir(mod_dir):
    r"""<mod>\Off in the spelling the folder has (a new one: "Off")."""
    for e in _list(mod_dir):
        if e.lower() == "off" and _isdir(os.path.join(mod_dir, e)):
            return os.path.join(mod_dir, e)
    return os.path.join(mod_dir, "Off")


def _sorted_names(names):
    return sorted(names, key=os.path.normcase)       # as pathlib orders Paths on this system, like the converter


def canonical_owners(mod_dir):
    r"""The folders under <mod>\Off already in the layout: only reason folders (and the MAX_PATH list) in them."""
    off = off_dir(mod_dir)
    out = []
    for x in _sorted_names(_list(off)):
        px = os.path.join(off, x)
        if not _isdir(px):
            continue
        kids = _list(px)
        dirs = [k for k in kids if _isdir(os.path.join(px, k))]
        files = [k for k in kids if k not in dirs]
        if dirs and all(is_canonical(k) for k in dirs) and all(f == LIST_NAME for f in files):
            out.append(x)
    return out


def _first_stem(folder, exts):
    names = _sorted_names(e for e in _list(folder) if os.path.splitext(e)[1].lower() in exts
                          and _isfile(os.path.join(folder, e)))
    return os.path.splitext(names[0])[0] if names else None


def computed_owner(mod_dir, hint=None, fallback=None):
    """<plugin> by the rule, ignoring what is in Off: the stem of the mod's first plugin at its root (.esp/.esm,
    sorted); else the stem of its first .omwscripts (the converter's mod_name_for), else .omwaddon/.omwgame;
    else the first plugin put aside in Off; else `hint`; else the mod's name (`fallback`, else the folder name).
    Always sanitised the way the converter does it."""
    stem = _first_stem(mod_dir, (".esp", ".esm")) or _first_stem(mod_dir, (".omwscripts",)) \
        or _first_stem(mod_dir, (".omwaddon", ".omwgame"))
    if not stem:
        off = off_dir(mod_dir)
        stem = _first_stem(off, PLUGIN_EXT)
        if not stem:
            for x in _sorted_names(_list(off)):
                if _isdir(os.path.join(off, x)):
                    stem = _first_stem(os.path.join(off, x), PLUGIN_EXT)
                    if stem:
                        break
    if not stem and hint:
        stem = os.path.splitext(os.path.basename(hint))[0] if hint.lower().endswith(PLUGIN_EXT) else hint
    if not stem:
        stem = fallback or os.path.basename(os.path.normpath(mod_dir))
    return sanitize(stem)


def owner_name(mod_dir, hint=None, fallback=None):
    """The <plugin> folder name for this mod: the one already in the layout when exactly one is (or the
    computed one is among them), else the computed one (computed_owner)."""
    want = computed_owner(mod_dir, hint, fallback)
    have = canonical_owners(mod_dir)
    for h in have:
        if h.lower() == want.lower():
            return h
    return have[0] if len(have) == 1 else want


def off_path(mod_dir, reason, rel="", hint=None, fallback=None):
    r"""<mod>\Off\<plugin>\<reason>\<rel>."""
    p = os.path.join(off_dir(mod_dir), owner_name(mod_dir, hint, fallback), reason_for(reason))
    return os.path.join(p, rel) if rel else p


def reason_dirs(mod_dir, reason):
    r"""Every folder under <mod>\Off that holds this reason's files: Off\<plugin>\<reason> and, from the older
    layouts, Off\<reason spellings>\<plugin>. [(folder, rel prefix lists)] - just the folders."""
    want = reason_for(reason)
    off = off_dir(mod_dir)
    out = []
    for x in _list(off):
        px = os.path.join(off, x)
        if not _isdir(px):
            continue
        if x.lower() in _CANON or x.lower() in LEGACY:
            if reason_for(x) == want:                       # Off\<reason>\<plugin>\...
                out += [os.path.join(px, y) for y in _list(px) if _isdir(os.path.join(px, y))]
            continue
        for y in _list(px):                                 # Off\<plugin>\<reason>\...
            if is_reason(y) and reason_for(y) == want and _isdir(os.path.join(px, y)):
                out.append(os.path.join(px, y))
    return out


def find_original(mod_dir, rel, skip=("broken", "orphaned animations", "unused assets")):
    """A copy of <rel> that a tool kept in this mod's Off tree (any layout, any reason but the `skip` ones
    that hold moved-out files rather than originals), or None."""
    off = off_dir(mod_dir)
    for x in _list(off):
        px = os.path.join(off, x)
        if not _isdir(px):
            continue
        if _isfile(os.path.join(px, rel)):                  # the oldest layout: Off\<rel> or Off\<plugin>\<rel>
            return os.path.join(px, rel)
        for y in _list(px):
            py = os.path.join(px, y)
            if not _isdir(py):
                continue
            if x.lower() in _CANON or x.lower() in LEGACY:
                if reason_for(x) not in skip and _isfile(os.path.join(py, rel)):   # Off\<reason>\<plugin>\<rel>
                    return os.path.join(py, rel)
            elif is_reason(y) and reason_for(y) not in skip and _isfile(os.path.join(py, rel)):
                return os.path.join(py, rel)                                      # Off\<plugin>\<reason>\<rel>
    return None


def relocated(path):
    r"""Where a file under an older Off layout is now: `path` as an older tool recorded it
    (<mod>\Off\<reason>\<plugin>\<rel>, <mod>\Off\<plugin>\<rel>) mapped to <mod>\Off\<plugin>\<reason>\<rel>,
    or None when that isn't there either. Used by records that hold such paths (--restore-unused)."""
    parts = os.path.normpath(path).split(os.sep)
    low = [p.lower() for p in parts]
    if "off" not in low:
        return None
    i = len(low) - 1 - low[::-1].index("off")
    mod = os.sep.join(parts[:i])
    if not mod or i + 2 > len(parts):
        return None
    if low[i + 1] in _CANON or low[i + 1] in LEGACY:
        reason, tail = reason_for(parts[i + 1]), parts[i + 3:]       # skip the plugin folder
    else:
        reason, tail = REPAIRED, parts[i + 2:]
    if not tail:
        return None
    for d in reason_dirs(mod, reason):
        cand = os.path.join(d, *tail)
        if _isfile(cand):
            return cand
    return None


# ------------------------------------------------------------------ the MAX_PATH guard

def guard_moves(moves, mod_dir):
    """(moves, offenders): the moves with every one that would touch a path over MAX_PATH taken out. A file whose
    own path or whose new path is too long stays where it is and is listed (its path relative to `mod_dir`). A
    folder move with such a file inside is split into the moves of what is in it. Moves that remove an empty
    folder (dst None) and writes (src == dst) pass."""
    out, bad = [], set()

    def holds_unmoved(folder):
        here = os.path.normcase(os.path.abspath(folder)) + os.sep
        return any(os.path.normcase(os.path.abspath(os.path.join(mod_dir, b))).startswith(here) for b in bad)

    def files_of(d):
        for base, _dirs, fns in os.walk(xp(d)):
            for fn in fns:
                yield os.path.join(plain(base), fn)

    def handle(src, dst, why):
        if _isdir(src):
            offending = any(too_long(f) or too_long(os.path.join(dst, os.path.relpath(f, src)))
                            for f in files_of(src)) or too_long(dst)
            if not offending:
                out.append((src, dst, why))
                return
            for e in sorted(_list(xp(src))):
                handle(os.path.join(src, e), os.path.join(dst, e), why)
            if not holds_unmoved(src):
                out.append((src, None, "remove the emptied folder"))
        elif too_long(src) or too_long(dst):
            bad.add(os.path.relpath(src, mod_dir))
        else:
            out.append((src, dst, why))

    for src, dst, why in moves:
        if dst is None:
            if not holds_unmoved(src):                                   # a folder still holding an unmoved file stays
                out.append((src, dst, why))
        elif src == dst:
            out.append((src, dst, why))
        else:
            handle(src, dst, why)
    return out, bad


def list_path(mod_dir, owner):
    return os.path.join(off_dir(mod_dir), owner, LIST_NAME)


def read_list(path):
    try:
        with open(xp(path), encoding="utf-8") as f:
            return [ln.strip() for ln in f.read().splitlines() if ln.strip()]
    except OSError:
        return []


def list_text(rels):
    """The list's contents: one path per line, relative to the mod's staged folder, backslashes, no repeats,
    sorted without regard to case; "" for nothing."""
    uniq = {}
    for r in rels:
        r = r.replace("/", "\\")
        uniq.setdefault(r.lower(), r)
    return "".join(uniq[k] + "\n" for k in sorted(uniq))


def off_copy(mod_dir, rel, owner):
    r"""The absolute path of the Off copy of `rel` (relative to the mod) in the one layout: a path already under
    Off\ is mapped the way the migration would move it; a path still in the mod is Off\<plugin>\OpenMW\<rel>
    (where the converter puts a set-aside copy). Used to keep a max_path_too_long.txt line when the source is
    short but the Off path would be too long."""
    parts = os.path.normpath(rel.replace("/", os.sep)).split(os.sep)
    if not parts or parts == ["."]:
        return None
    root = os.path.join(off_dir(mod_dir), owner)
    if parts[0].lower() != "off":
        return os.path.join(root, "OpenMW", *parts)

    def loose_why(name):
        ext = os.path.splitext(name)[1].lower()
        if ext in PLUGIN_EXT or ext == ".bsa":
            return "disabled plugins"
        if ext == ".omwscripts":
            return "OpenMW"
        if ext in EXEC_EXT:
            return "executables"
        return None

    rest = parts[1:]
    if not rest:
        return None
    head, tail = rest[0], rest[1:]
    hl = head.lower()
    if not tail:
        why = loose_why(head)
        return os.path.join(root, why, head) if why else None
    if hl in _CANON or hl in LEGACY:                 # Off\<reason>\<plugin>\<path>
        return os.path.join(root, reason_for(head), *(tail[1:] if len(tail) > 1 else tail))
    if hl == "openmw":                               # Off\OpenMW\<mod>\<path>
        return os.path.join(root, "OpenMW", *(tail[1:] if len(tail) > 1 else tail))
    if hl in GAME_TOPS:                              # Off\<path>
        return os.path.join(root, REPAIRED, *rest)
    nxt, more = tail[0], tail[1:]
    nl = nxt.lower()
    if not more:
        why = loose_why(nxt)
        if why:
            return os.path.join(root, why, nxt)
        if is_reason(nxt):
            return os.path.join(root, reason_for(nxt))
        return None
    if nl in GAME_TOPS:                              # Off\<name>\<path>
        return os.path.join(root, REPAIRED, nxt, *more)
    if is_reason(nxt):                               # Off\<name>\<reason>\... (already canonical when name is owner)
        return os.path.join(root, reason_for(nxt), *more)
    return None


def still_listed(mod_dir, rel, owner):
    """True when a max_path_too_long.txt line should stay: the file is still there, and either its own path
    or its Off copy (off_copy) is too long."""
    src = os.path.join(mod_dir, rel.replace("/", os.sep))
    if not _isfile(src):
        return False
    if too_long(src):
        return True
    dest = off_copy(mod_dir, rel, owner)
    return dest is not None and too_long(dest)


def list_update(mod_dir, owner, offenders):
    """(path, text) to write, (path, None) to remove, or None for no change: the list is the offenders found now
    plus the earlier ones still there whose own path or Off copy is still too long; written only when its text
    would differ."""
    path = list_path(mod_dir, owner)
    had = _isfile(path)
    old = read_list(path) if had else []
    keep = [r for r in old if still_listed(mod_dir, r, owner)]
    text = list_text(list(offenders) + keep)
    if not text:
        return (path, None) if had else None
    if had:
        try:
            with open(xp(path), encoding="utf-8") as f:
                if f.read().replace("\r\n", "\n") == text:
                    return None
        except OSError:
            pass
    return (path, text)


# ------------------------------------------------------------------ the migration of the older layouts

def manifest_paths(mod_dir):
    """Absolute, case-folded paths of everything an omw2mwse manifest in this mod lists (files, plugin paths),
    and whether the mod holds converter output at all: files the converter places, never tidy's to move."""
    paths, found = set(), False
    mroot = None
    for e in _list(mod_dir):
        if e.lower() == "mwse" and _isdir(os.path.join(mod_dir, e)):
            mroot = os.path.join(mod_dir, e)
    bases = []
    if mroot:
        for sub in (("mods", "mwsuite", "openmw"), ("omw",)):
            b = mroot
            for s in sub:
                b = next((os.path.join(b, e) for e in _list(b) if e.lower() == s), None)
                if not b:
                    break
            if b:
                bases += [os.path.join(b, e) for e in _list(b) if _isdir(os.path.join(b, e))]
    for b in bases:
        mp = os.path.join(b, MANIFEST)
        if not _isfile(mp):
            continue
        found = True
        try:
            with open(xp(mp), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        rels = list((data.get("files") or {}).keys()) if isinstance(data, dict) else []
        for p in (data.get("plugins") or []) if isinstance(data, dict) else []:
            if isinstance(p, dict) and isinstance(p.get("path"), str):
                rels.append(p["path"])
        for r in rels:
            if isinstance(r, str):
                paths.add(os.path.normcase(os.path.abspath(os.path.join(mod_dir, r.replace("/", os.sep)))))
    return paths, found


class Migration(object):
    """What plan_migration found: moves [(src, dst, why)] and notes (what was left alone, and why)."""
    def __init__(self):
        self.moves = []
        self.notes = []


def plan_migration(mod_dir, owner, taken=None, skip_openmw=False):
    r"""The moves that bring every older layout under <mod>\Off into <mod>\Off\<owner>\<reason>\...:

      * loose files directly in Off\ (a plugin: disabled plugins; .omwscripts: OpenMW; a program: executables);
      * Off\<reason>\<plugin>\<path>, reasons by any older spelling (normal maps, broken, names, sound...);
      * Off\OpenMW\<mod>\<path> (skipped with skip_openmw: the whole-package move of an OpenMW-only mod does it);
      * Off\<path> and Off\<plugin>\<path> (the path starts at meshes\, textures\, sound\...): repaired originals;
      * Off\<name>\ holding plugin files, or older reason spellings, under any name: into the owner.
    A folder already in the layout (only reason folders in it) is never touched, whatever its name. What is
    none of these is left alone and noted. Nothing in an omw2mwse manifest (or the legacy Off\OpenMW\ folder of a
    mod holding converter output) is moved. Idempotent: what has moved is no longer a legacy layout."""
    mig = Migration()
    off = off_dir(mod_dir)
    if not _isdir(off):
        return mig
    taken = set() if taken is None else taken
    protected, converted = manifest_paths(mod_dir)
    canon = {c.lower() for c in canonical_owners(mod_dir)}
    root = os.path.join(off, owner)
    left = []

    def contains_protected(p):
        pn = os.path.normcase(os.path.abspath(p))
        return any(q == pn or q.startswith(pn + os.sep) for q in protected)

    dirs_to = {}                                             # folders moved whole: their new path -> where from

    def occupied(dst):
        """Something is, or after the planned moves will be, at dst (or below it, or it is inside a moved folder
        that holds the same name)."""
        low = dst.lower()
        if os.path.exists(xp(dst)) or low in taken or any(t.startswith(low + os.sep) for t in taken):
            return True
        for to, frm in dirs_to.items():
            if low.startswith(to + os.sep) and os.path.exists(xp(os.path.join(frm, dst[len(to) + 1:]))):
                return True
        return False

    def free(dst):
        base, ext = os.path.splitext(dst)
        n, cand = 2, dst
        while occupied(cand):
            cand = "%s (%d)%s" % (base, n, ext)
            n += 1
        taken.add(cand.lower())
        return cand

    def put(src, dst, why):
        pn = os.path.normcase(os.path.abspath(src))
        if pn in protected:
            return
        if _isdir(src):
            inside = any(dst.lower().startswith(to + os.sep) for to in dirs_to)
            if not occupied(dst) and not inside and not contains_protected(src):
                taken.add(dst.lower())
                dirs_to[dst.lower()] = src
                mig.moves.append((src, dst, why))
                return
            for e in sorted(_list(xp(src))):
                put(os.path.join(src, e), os.path.join(dst, e), why)
            mig.moves.append((src, None, "remove the emptied folder"))
        else:
            mig.moves.append((src, free(dst), why))

    def dest(reason, *parts):
        return os.path.join(root, reason, *parts)

    def loose_reason(name):
        ext = os.path.splitext(name)[1].lower()
        if ext in PLUGIN_EXT or ext == ".bsa":
            return "disabled plugins"
        if ext == ".omwscripts":
            return "OpenMW"
        if ext in EXEC_EXT:
            return "executables"
        return None

    def has_top(p):
        return any(k.lower() in GAME_TOPS and _isdir(os.path.join(p, k)) for k in _list(xp(p)))

    for x in sorted(_list(xp(off)), key=str.lower):
        px = os.path.join(off, x)
        xl = x.lower()
        rel = "Off\\" + x
        if not _isdir(px):
            if os.path.normcase(os.path.abspath(px)) in protected:
                continue
            why_r = loose_reason(x)
            if why_r:
                put(px, dest(why_r, x), "Off layout: loose file -> Off\\<plugin>\\%s\\" % why_r)
            else:
                left.append(rel)
            continue
        if xl in canon:
            continue
        if xl == "openmw":                                   # Off\OpenMW\<mod>\<path>
            if skip_openmw or converted:
                continue
            for y in sorted(_list(xp(px)), key=str.lower):
                py = os.path.join(px, y)
                if _isdir(py):
                    for z in sorted(_list(xp(py)), key=str.lower):
                        put(os.path.join(py, z), dest("OpenMW", z), "Off layout: Off\\OpenMW\\<mod>\\ -> Off\\<plugin>\\OpenMW\\")
                    mig.moves.append((py, None, "remove the emptied folder"))
                else:
                    put(py, dest("OpenMW", y), "Off layout: Off\\OpenMW\\<mod>\\ -> Off\\<plugin>\\OpenMW\\")
            mig.moves.append((px, None, "remove the emptied folder"))
            continue
        kids = sorted(_list(xp(px)), key=str.lower)
        first = len(mig.moves)
        if (xl in _CANON or xl in LEGACY) and (xl not in GAME_TOPS or (kids and all(
                _isdir(os.path.join(px, k)) and has_top(os.path.join(px, k)) for k in kids))):
            rsn = reason_for(x)                              # Off\<reason>\<plugin>\<path>
            why = "Off layout: Off\\%s\\<plugin>\\ -> Off\\<plugin>\\%s\\" % (x, rsn)
            for k in kids:
                pk = os.path.join(px, k)
                if _isdir(pk):
                    for z in sorted(_list(xp(pk)), key=str.lower):
                        put(os.path.join(pk, z), dest(rsn, z), why)
                    mig.moves.append((pk, None, "remove the emptied folder"))
                else:
                    put(pk, dest(rsn, k), why)
            mig.moves.append((px, None, "remove the emptied folder"))
            continue
        if xl in GAME_TOPS:                                  # Off\<path>: no plugin, no reason
            put(px, dest(REPAIRED, x), "Off layout: Off\\<path> -> Off\\<plugin>\\%s\\" % REPAIRED)
            continue
        for k in kids:                                       # Off\<name>\...
            pk = os.path.join(px, k)
            kl = k.lower()
            if k == LIST_NAME:
                continue
            if not _isdir(pk):
                why_r = loose_reason(k)
                if why_r:
                    put(pk, dest(why_r, k), "Off layout: Off\\<name>\\<file> -> Off\\<plugin>\\%s\\" % why_r)
                else:
                    left.append("Off\\%s\\%s" % (x, k))
            elif kl in GAME_TOPS:
                put(pk, dest(REPAIRED, k), "Off layout: Off\\<plugin>\\<path> -> Off\\<plugin>\\%s\\" % REPAIRED)
            elif is_reason(k):
                rsn = reason_for(k)
                if x.lower() == owner.lower() and rsn.lower() == kl:
                    continue                                 # already in the layout (case aside)
                put(pk, dest(rsn), "Off layout: Off\\<name>\\%s\\ -> Off\\<plugin>\\%s\\" % (k, rsn))
            else:
                left.append("Off\\%s\\%s" % (x, k))
        if len(mig.moves) > first:
            mig.moves.append((px, None, "remove the emptied folder"))
    if left:
        mig.notes.append("%d item(s) under Off\\ left where they are (not a layout these tools recognise), e.g. %s"
                         % (len(left), left[0]))
    return mig
