#!/usr/bin/env python3
"""vortex_tidy.py - tidy the mods in Vortex's Morrowind staging folder.

For each mod folder in Vortex's Morrowind staging folder (from Vortex's settings, or --staging):

  * Game folders stay where they are: meshes, textures, icons, sound, music, bookart, splash, fonts,
    video, distantland; and support folders: MWSE, MGE3, shaders (MGE XE's XEshaders), grass, mcpatch.
    Plugins (.esp/.esm/.omwaddon), .bsa archives and MWSE's *-metadata.toml files at the root stay too.
    So do the folders this script makes or keeps: Docs, Extras, OpenMW, and your Off folders (plugins and
    files you put aside to disable them), which are never moved, renamed or looked inside - in a mod or at
    the top of the staging folder.
  * Images at the root (.jpg, .png, .gif, .bmp, .webp) go to Screenshots\\, renamed "<mod name> - <file>";
    a mod's own Screenshots folder stays, and its pictures get the same prefix.
  * Documents at the root (readme.txt, changelog.md, manual.pdf...) go to Docs\\, renamed
    "<mod name> - <file name>", so they can't overwrite each other's readme.txt when deployed.
    Documents already in Docs\\ that don't say which mod they're from get the prefix too.
  * A root folder holding a mod's readme - one named after one of its plugins or the mod (the
    "<mod>\\<plugin name>\\readme.txt" layout), or one holding nothing but documents - becomes part of
    Docs\\: its documents are renamed the same way; anything else in it goes to Extras.
  * An .omwaddon with no .esp/.esm beside it: with no OpenMW scripts (no *.omwscripts, no scripts folder)
    it is renamed .esp, so Morrowind can load it. With scripts, the mod needs OpenMW: the plan flags it,
    and --apply stops at it, lets you open its folder, and offers to delete it (it is moved to
    "<staging> - deleted by vortex_tidy" beside the staging folder, so --undo can bring it back).
  * Normal maps (textures\\...\\*_n / *_nm / *_normal / *_nrm, .dds/.tga/.bmp) all go to
    Off\\normal maps\\<mod name>\\ (never deployed): vanilla Morrowind with MGE XE doesn't use them (only OpenMW
    does). If a model names one, mwdialog_check.py --fix puts a flat stand-in normal map in its place, so
    the game shows no missing-texture warnings. Only normal maps whose diffuse texture exists move (tx_wall.dds
    for tx_wall_n.dds: beside it, at the same path under textures\\ in any mod in staging, loose in Data Files,
    or in a BSA there). One with no diffuse anywhere stays where it is, untouched and without a stand-in; if
    nothing uses it, mwdialog_check --full's unused-asset purge takes it out later. The exception: a file
    whose path says "normal map(s)" in any spelling (an add-on normal-map pack, for OpenMW) moves either way, and the plan notes
    the pack as not applicable to classic Morrowind.
  * MGE XE grass plugins (only statics and cells, nearly all grass/groundcover) go to Grass\\, where MGE
    XE's distant land generator reads them; the game itself never loads them.
  * OpenMW-only content goes to Off\\OpenMW\\<mod name>\\ (never deployed): *.omwscripts files and the scripts, l10n,
    animations and playlists folders; an OpenMW\\ folder an earlier run made at the root is moved there too.
  * An OpenMW-only mod (OpenMW scripts - an *.omwscripts file at its root, in OpenMW\\ or set aside under Off\\ -
    and no MWSE Lua of its own) is converted for MWSE instead: --apply runs the OpenMW converter, omw2mwse
    --convert-omwscripts=<mode> <mod> --json (found on PATH or beside these tools; hardcode by default, with
    --accept-hardcode-conversions; --convert-omwscripts=normal for the other mode, --no-convert-omwscripts for
    neither), which lays the mod out itself, so nothing else in it moves that run; the plan shows a dry-run
    preview. A conflict (exit 4) or other failure is one WARNING line, the run goes on, and the mod is treated as
    not convertible (below). A mod with real MWSE Lua (a .lua under MWSE\\ that omw2mwse didn't generate) is
    MWSE-first: its OpenMW files go to Off\\OpenMW\\ as above and are never converted. An OpenMW-only mod that
    is not converted (no converter, a failed or blocked conversion, --no-convert-omwscripts) has its ENTIRE
    package moved to Off\\<plugin name>\\OpenMW\\ (omw2mwse's own place and name: the first .omwscripts' stem, e.g.
    Off\\wildlife_attacks_npc\\OpenMW\\) - plugins, scripts, data folders, Docs\\, Screenshots\\ - so the staging root
    keeps only Off\\ (and Vortex's marker file) and that is all it deploys; an Off\\OpenMW\\<mod>\\ folder from an
    earlier tidy run is moved there too; --undo puts each file back. Without the converter: one WARNING line.
    --undo reverses a conversion: it journals what omw2mwse reported, deletes
    the files omw2mwse wrote (its manifest's list, each only if it still has the hash the manifest gives; an edited
    one stays, with one WARNING line) and puts the original package from Off\\<Mod>\\OpenMW\\ back at its
    original paths. The shared MWSE\\lib\\omwcompat runtime goes only when no converted mod is left in staging or
    Data Files. The converter gets --title and --author from Vortex's mod info when it has them. omw2mwse's
    verdict is read from its JSON: blocked (it cannot run, but the converter still writes an active loader and
    exits 0) is not shipped - the output is undone at once, the mod is treated as not convertible, its whole
    package goes to Off\\<plugin name>\\OpenMW\\ as above, one WARNING line, and the plan says so up front; partial counts as
    converted, with one NOTE. Plugins are never renamed or enabled by tidy: omw2mwse renames .omwaddon/.omwgame
    to .esp/.esm itself (originals stay under Off\\). omw2mwse also places plugins itself and reports each in
    mods[].plugins[] of its JSON (else plugins in omw2mwse-manifest.json): placement root (enabled by default),
    extras (Extras\\<Mod>\\) or off (Off\\<Mod>\\OpenMW\\), status required, undetermined or obsolete, path, reason.
    Tidy never moves, renames or enables a plugin and never reads readmes or FOMOD text for this: at --apply it
    prints one NOTE per non-root plugin (where it went, the converter's reason). An older converter's boolean
    optional (true) counts as not-root; a manifest with no plugins key falls back to a scan for root plugins with
    no .omwaddon/.omwgame source. plugin-rename-clash alerts get a NOTE too.
  * A bugreports\\ folder tidy made during a run that is empty at the end of it (--apply, a dry run or --undo)
    is removed again; one that was already there, or has anything in it, stays.
  * Everything else (screenshots, FOMOD option folders, meta.ini, .bak files...) goes to
    Extras\\<mod name>\\, where <mod name> is the folder name without Vortex's Nexus id, version and
    download stamp ("MUSE 2.02-46200-2-02-1593543300" -> "MUSE").

Mods that install into the game folder instead of Data Files (an .exe, .dll or a "Data Files" folder at
their root, like MGE XE) are left alone, and so is every mod on the blacklist: the Morrowind Code Patch and
NIFZER0EDIT built in, plus the folder names in vortex_tidy_blacklist.txt (one per line, wildcards allowed).

  * MWSE Lua mods (MWSE\\mods\\...\\*.lua) are checked by mwdialog_luafix.py for bad habits that pass a syntax
    check (absurd priorities, polling every frame, one-shot handlers that never unregister, unguarded ref.data,
    infoFilter reading text, re-registering on every load, log spam...). The plan lists them; --apply patches
    the safe ones in place (hard links stay; the LuaJIT checker must compile the result; originals kept in
    <backups folder>\\luafix), --undo puts them back. --no-lua skips this, --lua-only does only this.

  * Broken asset files the asset check can't repair (empty, not the format their name says, truncated, a model
    the game crashes on, an MP3 with no audio) go to <mod>\\Off\\broken\\<plugin>\\<path>, and a small valid
    file of the same format takes their place, so what names them still finds a file. Made in code: a 4x4
    placeholder texture (DDS, TGA, BMP, PNG; an 8x8 JPEG; a 32x32 icon under icons\\), silence (WAV, MP3). A
    model (NIF) gets the game's Dwemer coin, read out of Morrowind.bsa, so the gap is easy to spot; with
    --no-coins (or no coin in Morrowind.bsa, which the plan says, with a warning that the core game files were
    altered: once per run, at the end of the output and of the plan) an empty, invisible model made in code. Any
    other type (.kf, .bik, .fnt, .tex...) gets a copy of a core game file of that type
    (Morrowind/Tribunal/Bloodmoon.bsa, or the game's own loose Video and Fonts files): the one at the same path
    if there is one, else one no active plugin (nor Morrowind.ini) names, cached in vortex_tidy_dummy_sources.json.
    <original>.tidy-dummy beside the kept original marks the dummy, so a later run leaves it alone. A broken
    model another mod or a BSA also has is only moved out (Deploy lets that copy win); a type with no dummy
    either way is left as it is, which the plan says.

It only shows the plan unless you pass --apply. Every move is written to a journal, and --undo puts
everything back. Purge in Vortex before applying, and Deploy afterwards, so the game folder matches.
Asset repairs are undone the same way: before a mod's files are repaired, every file the repairs can change
(the file, a same-named file beside it, the mod's plugins and bug reports) is copied to
<backups folder>\\tidy\\<run>\\assets\\<mod folder>\\ and journaled with its SHA-256; --undo puts each
original back at its own path (in place, file dates as they were) and removes the files the repairs made
(repaired copies under new names, the Off\\ copies, a new bug report). It does not reverse a repair: it brings
back the file as it was. One --undo undoes the whole last --apply (repairs, then Lua patches, then moves); a
missing or altered original, or a file changed since the --apply, stops it before anything is changed
(--undo --force overwrites changed files, never without a matching original).
--apply enacts only the plan you reviewed: it works the plan out again (moves, Lua patches, asset repairs -
all listed in plans/vortex_tidy_plan.txt; --lua-only: its Lua section) and refuses, changing nothing, when the
actions differ from the plan file: the new plan is written for review and the old one kept as
vortex_tidy_plan.prev.txt. No plan file (or a blank one) also refuses: run plan mode first.
Afterwards vortex_tidy_plan.txt is blanked (only a "# applied
..." line: a second --apply does nothing until plan mode is run again), or cut down to what was NOT applied.
Copies of the plan as reviewed and as enacted go to <backups folder>\\tidy\\<run>\\. --undo uses the journal only.

    python vortex_tidy.py                      (plan for every mod; nothing is changed)
    python vortex_tidy.py --only "MUSE*"       (plan for some mods; wildcards allowed)
    python vortex_tidy.py --apply              (do it)
    python vortex_tidy.py --undo               (put back everything the last --apply changed)
"""
import fnmatch
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_backup as MB                     # noqa: E402
import mwdialog_planfile as PF                   # noqa: E402
import mwdialog_paths as MP                      # noqa: E402
import mwdialog_text as MT                       # noqa: E402
print = MT.printer()                             # noqa: A001

HERE = MP.find_game_dir() or os.path.dirname(os.path.abspath(__file__))   # the game folder (see mwdialog_paths)
JOURNAL = MP.state_path(HERE, "vortex_tidy_journal.jsonl")
PLAN = MP.state_path(MP.PLANS_DIR, "vortex_tidy_plan.txt")
AUDIT_ROOT = os.path.join(MB.backup_root(HERE), "tidy")     # a copy of each enacted plan, per --apply run
LUA_HEAD = "LUA CHECK"
ASSET_HEAD = "ASSET CHECK"

GAME_DIRS = {"meshes", "textures", "icons", "sound", "music", "bookart", "splash", "fonts", "video",
             "distantland"}
SUPPORT_DIRS = {"mwse", "mge3", "shaders", "grass", "mcpatch"}
OUR_DIRS = {"docs", "extras", "openmw", "off", "bugreports"}
OPENMW_DIRS = {"scripts", "l10n", "playlists", "animations"}
NORMAL_MAP = re.compile(r"_(n|nm|normal|nrm)$")


def is_grass_plugin(path):
    """An MGE XE groundcover plugin (read by the distant land generator from Data Files\\Grass, never loaded
    as a game plugin): only statics/activators and cells, and most of those objects are grass (model under grass\\, or an id /
    model that says grass or groundcover)."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return False
    p, tags, stats, grassy = 0, set(), 0, 0
    while p + 16 <= len(data):
        tag = data[p:p + 4]
        size = struct.unpack_from("<I", data, p + 4)[0]
        body = data[p + 16:p + 16 + size]
        if tag != b"TES3":
            tags.add(tag)
        if tag in (b"STAT", b"ACTI"):
            stats += 1
            q, name, modl = 0, b"", b""
            while q + 8 <= len(body):
                sn, sz = body[q:q + 4], struct.unpack_from("<I", body, q + 4)[0]
                if sn == b"NAME":
                    name = body[q + 8:q + 8 + sz].lower()
                elif sn == b"MODL":
                    modl = body[q + 8:q + 8 + sz].lower().replace(b"/", b"\\")
                q += 8 + sz
            if modl.endswith(b"editormarker.nif\0") or modl.endswith(b"editormarker.nif"):
                stats -= 1                          # invisible markers (hidden objects) say nothing either way
            elif modl.startswith(b"grass\\") or any(w in name + modl for w in (b"grass", b"groundcover", b"_gc_")):
                grassy += 1
        p += 16 + size
    return bool(stats) and tags <= {b"STAT", b"ACTI", b"CELL"} and grassy >= max(1, stats * 0.6)
KEEP_FILE_EXT = {".esp", ".esm", ".omwaddon", ".omwgame", ".bsa"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}   # screenshots (not .dds/.tga: textures)
DOC_EXT = {".txt", ".md", ".pdf", ".rtf", ".doc", ".docx", ".odt", ".html", ".htm", ".nfo"}
DOC_DIR_NAMES = {"doc", "docs", "documentation", "readme", "readmes", "manual", "manuals", "info"}
GAME_ROOT_EXT = {".exe", ".dll", ".asi"}          # the mod installs into the game folder: leave it alone
# mods never touched: the defaults below plus one pattern per line in vortex_tidy_blacklist.txt
# (in the game folder; wildcards allowed, matched against the mod's folder name, case doesn't matter)
BLACKLIST = ["Morrowind Code Patch*", "MCP beta*", "NIFZER0EDIT*"]
BLACKLIST_FILE = MP.state_path(HERE, "vortex_tidy_blacklist.txt")


def blacklist(create=True):
    """The blacklist patterns. create: write the commented starter file when there is none (not in a plan-only
    run, which changes nothing)."""
    pats = list(BLACKLIST)
    if not os.path.exists(BLACKLIST_FILE):
        if not create:
            return pats
        try:
            with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
                f.write("; vortex_tidy blacklist: mods it never touches. One mod folder name per line; * and ? work.\n"
                        "; Morrowind Code Patch and NIFZER0EDIT are built in. Add tools and other odd layouts here.\n")
        except OSError:
            pass
    else:
        for line in open(BLACKLIST_FILE, encoding="utf-8", errors="replace"):
            line = line.strip()
            if line and not line.startswith((";", "#")):
                pats.append(line)
    return pats

VORTEX_FILES = {"__folder_managed_by_vortex"}

# Vortex folder names: "Name-12345-1-2-1612345678", "Name-12345-1-2", "Name-12345",
# and the newer "Name 12345 1.2 2026-08-25T04-10Z AbCd1234"
NEW_STYLE = re.compile(r"^(?P<name>.+?) \d{2,7} \S+ \d{4}-\d\d-\d\dT\d\d-\d\dZ \w{6,10}$")
OLD_STYLE = re.compile(r"^(?P<name>.+?)-\d{2,7}(?:-[0-9A-Za-z.]+)*$")
VERSION_TAIL = re.compile(r"(?:[ _-]+v?\d+(?:[._]\d+)+[a-z]?|[ _-]+v\d+[a-z]?)$", re.I)
BAD_CHARS = re.compile(r'[<>:"/\\|?*]')


def mod_name(folder):
    """The mod's name without Vortex's Nexus id, version and download stamp."""
    m = NEW_STYLE.match(folder) or OLD_STYLE.match(folder)
    name = m.group("name") if m else folder
    for _ in range(2):                              # "Foo 1.2 v3" -> "Foo"
        name = VERSION_TAIL.sub("", name).strip()
    name = BAD_CHARS.sub("_", name).rstrip(" .")    # Windows names can't end in a dot or space
    return name or folder


def has_prefix(fn):
    return " - " in os.path.splitext(fn)[0]


def is_doc(fn):
    return os.path.splitext(fn)[1].lower() in DOC_EXT


def existing(root, wanted):
    """The actual spelling of a root folder (Docs/docs), or the wanted one if there is none yet."""
    for e in os.listdir(root):
        if e.lower() == wanted.lower() and os.path.isdir(os.path.join(root, e)):
            return e
    return wanted


def free_path(path, taken):
    """`path`, or "name (2).ext" ... if it exists or another move in this plan already goes there."""
    base, ext = os.path.splitext(path)
    n, cand = 2, path
    while os.path.exists(cand) or cand.lower() in taken:
        cand = f"{base} ({n}){ext}"
        n += 1
    taken.add(cand.lower())
    return cand


def files_under(path):
    for base, dirs, fns in os.walk(path):
        dirs[:] = [d for d in dirs if d.lower() != "off"]      # an Off folder anywhere is left as it is
        for fn in fns:
            yield os.path.join(base, fn)


NOTES = []             # plan-wide warnings (shown at the top of the plan, and again by --apply)
NO_DIFFUSE_WARNING = "no matching diffuse texture anywhere, check it's really a normal map; --undo puts it back"
# 'Normal Maps' / 'normal_map' / 'NormalMap' / 'normal.maps' folder or mod: an add-on normal-map pack
NORMAL_PACK_RE = re.compile(r"(?i)(?<![a-z])normal[\s_\-.]*maps?(?![a-z])")
ORPHAN_NORMALS = []    # (mod folder, path in it) of normal maps left in place: no diffuse texture anywhere
NORMAL_PACKS = {}      # mod folder -> normal maps moved from its "normal maps" paths
_TEX_INDEX = {}        # staging folder -> (set of texture paths without extension, set of base names)


def _tex_key(rel):
    """'textures\\tx\\wall.dds' / 'tx/wall.tga' -> 'tx\\wall' (lowercase, no extension, under textures\\)."""
    r = rel.replace("/", "\\").lower().lstrip("\\")
    if r.startswith("textures\\"):
        r = r[9:]
    return os.path.splitext(r)[0]


def texture_index(staging):
    """Every diffuse-capable texture there is: in each mod in the staging folder (not Off\\), loose in Data Files
    and in its BSAs (the game folder's Data Files). Built once per staging folder."""
    key = os.path.abspath(staging)
    if key in _TEX_INDEX:
        return _TEX_INDEX[key]
    paths = set()
    roots = []
    try:
        roots = [os.path.join(staging, d) for d in os.listdir(staging) if os.path.isdir(os.path.join(staging, d))
                 and d.lower() != "off"]
    except OSError:
        pass
    data_dir = os.path.join(HERE, "Data Files")
    if os.path.isdir(data_dir):
        roots.append(data_dir)
    for root in roots:
        try:
            tex = next((e for e in os.listdir(root) if e.lower() == "textures"), None)
        except OSError:
            continue
        if not tex:
            continue
        for p in files_under(os.path.join(root, tex)):
            if os.path.splitext(p)[1].lower() in (".dds", ".tga", ".bmp"):
                paths.add(_tex_key(os.path.relpath(p, os.path.join(root, tex))))
    try:
        bsas = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.lower().endswith(".bsa")]
    except OSError:
        bsas = []
    if bsas:
        m, _ah = _tool_modules()
        for b in bsas:
            try:
                for pth in (m.bsa_file_names(b) if m else ()):
                    if pth.lower().startswith("textures/") and pth.lower().endswith((".dds", ".tga", ".bmp")):
                        paths.add(_tex_key(pth))
            except Exception:                      # a damaged BSA: its textures just don't count
                continue
    _TEX_INDEX[key] = (paths, {p.rsplit("\\", 1)[-1] for p in paths})
    return _TEX_INDEX[key]


def diffuse_exists(path, tex_root, staging):
    """The texture a normal map belongs to exists somewhere: beside it, at the same path under textures\\
    (any mod, Data Files, a BSA), or by name (textures are found by name when a model's path is off)."""
    if has_diffuse_sibling(path):
        return True
    key = NORMAL_MAP.sub("", _tex_key(os.path.relpath(path, tex_root)))
    paths, names = texture_index(staging)
    return key in paths or key.rsplit("\\", 1)[-1] in names


def has_diffuse_sibling(path):
    """True when the texture a normal map belongs to sits beside it: the same stem without the normal-map
    suffix (tx_wall.dds for tx_wall_n.dds), as .dds, .tga or .bmp, in the same folder."""
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    diffuse = NORMAL_MAP.sub("", stem)
    try:
        names = os.listdir(os.path.dirname(path))
    except OSError:
        return False
    return any(os.path.splitext(x)[0].lower() == diffuse and os.path.splitext(x)[1].lower() in (".dds", ".tga", ".bmp")
               for x in names)


def package_name(folder):
    """The name omw2mwse gives the OpenMW package in `folder` (its mod_name_for, copied so the two always agree):
    the stem of the first *.omwscripts there (sorted as pathlib sorts them), else the folder's own name, with
    everything but letters, digits, _ and - removed; "OpenMWMod" when nothing is left."""
    import pathlib
    oms = sorted(pathlib.Path(folder).glob("*.omwscripts"))
    base = oms[0].stem if oms else pathlib.Path(folder).name
    return re.sub(r"[^A-Za-z0-9_\-]", "", base) or "OpenMWMod"


def _has_omwscripts(folder):
    try:
        return any(x.lower().endswith(".omwscripts") and os.path.isfile(os.path.join(folder, x))
                   for x in os.listdir(folder))
    except OSError:
        return False


def whole_package_moves(mod_dir, entries, name=None):
    """The moves of an OpenMW-only mod that is not converted (omw2mwse missing, failed, judged it blocked, or
    --no-convert-omwscripts): its ENTIRE package goes to Off\\<plugin name>\\OpenMW\\ - omw2mwse's own place for
    the original package, named the way it names it (package_name) - plugins, scripts, data folders, tidy's
    own Docs\\ and Screenshots\\ - so the staging root keeps only Off\\ (and Vortex's own marker file) and that
    is all the mod deploys. The root package is named after the first .omwscripts at the mod root, else the one in
    an OpenMW\\ folder, else the package already set aside under Off\\<name>\\OpenMW\\ (so leftovers join it).
    An Off\\OpenMW\\<name>\\ folder an earlier tidy run made is moved to its Off\\<plugin name>\\OpenMW\\ too.
    Left where they are: Off\\ itself, Vortex's marker file and omw2mwse-generated output (it is removed, not
    shipped). An OpenMW\\ folder an earlier run made at the root is unpacked there (not nested). --undo puts every
    file back from the journal (older journals included: a move is a move)."""
    off = os.path.join(mod_dir, existing(mod_dir, "Off"))
    off_dirs = []                                     # (folder, its package name) under Off\, converter layout
    legacy = []                                       # Off\OpenMW\<x>\: where tidy used to put packages
    if os.path.isdir(off):
        for x in sorted(os.listdir(off)):
            px = os.path.join(off, x)
            if not os.path.isdir(px):
                continue
            if x.lower() == "openmw":
                legacy += [os.path.join(px, y) for y in sorted(os.listdir(px)) if os.path.isdir(os.path.join(px, y))]
                continue
            for y in sorted(os.listdir(px)):
                if y.lower() == "openmw" and os.path.isdir(os.path.join(px, y)):
                    off_dirs.append((os.path.join(px, y), x))
    old_openmw = next((e for e in entries if e.lower() == "openmw" and os.path.isdir(os.path.join(mod_dir, e))), None)
    old_path = os.path.join(mod_dir, old_openmw) if old_openmw else None
    if _has_omwscripts(mod_dir):
        root_name = package_name(mod_dir)
    elif old_path and _has_omwscripts(old_path):
        root_name = package_name(old_path)
    elif off_dirs:
        root_name = off_dirs[0][1]
    elif legacy:
        root_name = package_name(legacy[0])
    else:
        root_name = package_name(mod_dir)
    why = "OpenMW-only mod that is not converted: whole package -> Off\\<plugin>\\OpenMW\\"
    moves, taken = [], set()

    def package_dir(pname):
        pd = os.path.join(off, pname)
        return os.path.join(pd, existing(pd, "OpenMW") if os.path.isdir(pd) else "OpenMW")

    def move(src, pname, rel):
        moves.append((src, free_path(os.path.join(package_dir(pname), rel), taken), why))

    for e in sorted(entries):
        el, src = e.lower(), os.path.join(mod_dir, e)
        if el == "off" or el in VORTEX_FILES:
            continue
        if os.path.isdir(src) and el == "openmw":
            for x in sorted(os.listdir(src)):
                move(os.path.join(src, x), root_name, x)
            moves.append((src, None, "remove the emptied folder"))
            continue
        if os.path.isdir(src) and el == "mwse" and any(MP.omw_generated(p) for p in files_under(src)):
            continue                                     # omw2mwse's own output: removed by its undo, never moved
        move(src, root_name, e)
    for folder in legacy:                                 # migration: Off\OpenMW\<x>\ -> Off\<plugin>\OpenMW\
        pname = package_name(folder)
        for x in sorted(os.listdir(folder)):
            move(os.path.join(folder, x), pname, x)
        moves.append((folder, None, "remove the emptied folder"))
    if legacy:
        moves.append((os.path.join(off, existing(off, "OpenMW")), None, "remove the emptied folder"))
    return moves


def plan_mod(mod_dir):
    """[(source, destination, reason)] for one mod, or a str saying why it's left alone."""
    entries = os.listdir(mod_dir)
    low = {e.lower() for e in entries}
    if "data files" in low or any(os.path.splitext(e)[1].lower() in GAME_ROOT_EXT for e in entries
                                  if os.path.isfile(os.path.join(mod_dir, e))):
        return "installs into the game folder (exe/dll/Data Files at its root)"
    name = mod_name(os.path.basename(mod_dir))
    oms = openmw_only(mod_dir, entries)              # OpenMW-only (no MWSE Lua): omw2mwse converts it
    if oms:
        if CONVERTER["mode"] and CONVERTER["cmd"]:   # it lays the mod out itself, so nothing else moves now
            CONVERT[mod_dir] = oms
            return []
        if CONVERTER["mode"]:
            CONVERTER["missed"] = CONVERTER.get("missed", 0) + 1     # not found
        return whole_package_moves(mod_dir, entries)                 # not converted: all of it goes to Off\
    plugins = {os.path.splitext(e)[0].lower() for e in entries if os.path.splitext(e)[1].lower() in KEEP_FILE_EXT}
    # an OpenMW plugin (.omwaddon) and no Morrowind plugin: with no OpenMW scripts it is an ordinary plugin
    # in OpenMW's file name, so it becomes an .esp; with scripts, it needs OpenMW: you decide (REVIEW)
    addons = [e for e in entries if e.lower().endswith(".omwaddon") and os.path.isfile(os.path.join(mod_dir, e))]
    has_mw_plugin = any(os.path.splitext(e)[1].lower() in (".esp", ".esm") for e in entries)
    rename_addons = []
    if addons and not has_mw_plugin:
        scripts = openmw_scripts(mod_dir, entries)
        converted = omw_converted(mod_dir)
        if converted:                                # omw2mwse owns these copies: renaming them is its call
            CONVERTED[mod_dir] = (addons, converted)
        elif scripts:
            REVIEW[mod_dir] = (addons, scripts)
        else:
            rename_addons = addons
    else:
        rename_addons = []
    docs = os.path.join(mod_dir, existing(mod_dir, "Docs"))
    shots = os.path.join(mod_dir, existing(mod_dir, "Screenshots"))
    extras = os.path.join(mod_dir, existing(mod_dir, "Extras"), name)
    off = os.path.join(mod_dir, existing(mod_dir, "Off"))
    openmw = os.path.join(off, existing(off, "OpenMW") if os.path.isdir(off) else "OpenMW", name)
    moves, taken = [], set()

    def move(src, dst, why):
        dst = free_path(dst, taken)
        moves.append((src, dst, why))

    def named(fn):                                   # already says which mod it's from
        return has_prefix(fn) or fn.lower().startswith(name.lower())

    def doc_dest(src, rel=None):
        fn = os.path.basename(src)
        new = fn if named(fn) else f"{name} - {fn}"
        return os.path.join(docs, os.path.dirname(rel) if rel else "", new)

    for e in sorted(entries):
        if os.path.splitext(e)[1].lower() == ".esp" and os.path.isfile(os.path.join(mod_dir, e)) \
                and is_grass_plugin(os.path.join(mod_dir, e)):
            move(os.path.join(mod_dir, e), os.path.join(mod_dir, existing(mod_dir, "Grass"), e),
                 "MGE XE grass plugin -> Grass\\ (read by MGE's distant land generator, not loaded by the game)")
    old_openmw = next((e for e in entries if e.lower() == "openmw" and os.path.isdir(os.path.join(mod_dir, e))), None)
    if old_openmw:                                   # where earlier runs put it: into Off\OpenMW\ now
        for x in sorted(os.listdir(os.path.join(mod_dir, old_openmw))):
            move(os.path.join(mod_dir, old_openmw, x), os.path.join(openmw, x), "OpenMW-only -> Off\\OpenMW\\")
    for e in rename_addons:
        move(os.path.join(mod_dir, e), os.path.join(mod_dir, os.path.splitext(e)[0] + ".esp"),
             "OpenMW plugin without scripts: renamed .esp so Morrowind can load it")
    for e in sorted(entries):
        src = os.path.join(mod_dir, e)
        el, ext = e.lower(), os.path.splitext(e)[1].lower()
        if os.path.isfile(src):
            if el in VORTEX_FILES or ext in KEEP_FILE_EXT or (ext == ".toml" and el.endswith("-metadata.toml")) \
                    or el.endswith(".bugreport.txt"):          # our own bug reports stay at the root
                continue
            if ext == ".omwscripts":
                move(src, os.path.join(openmw, e), "OpenMW scripts file")
            elif ext in IMAGE_EXT:
                move(src, os.path.join(shots, e if named(e) else f"{name} - {e}"), "image at the root")
            elif is_doc(e):
                move(src, doc_dest(src), "document at the root")
            else:
                move(src, os.path.join(extras, e), "not game data")
            continue
        if el == "textures":
            # normal maps (*_n, *_nm, *_normal, *_nrm): vanilla Morrowind + MGE XE never uses them (only
            # OpenMW does), so one whose diffuse texture exists goes to Off\normal maps\<mod>\, which is never
            # deployed. If a model names one, mwdialog_check.py --fix puts a flat stand-in normal map in its
            # place (no "tex not found" warnings). One with no diffuse anywhere stays put (no stand-in either):
            # it may be a real texture whose name only looks like a normal map's, and if nothing uses it
            # --full's unused-asset purge removes it. A "normal maps" path (an add-on normal-map pack) moves
            # regardless.
            staging = os.path.dirname(os.path.abspath(mod_dir))
            for p in files_under(src):
                stem = os.path.splitext(os.path.basename(p))[0].lower()
                if os.path.splitext(p)[1].lower() not in (".dds", ".tga", ".bmp") or not NORMAL_MAP.search(stem):
                    continue
                rel = os.path.relpath(p, mod_dir)
                why = "normal map (not used without OpenMW)"
                pack = bool(NORMAL_PACK_RE.search(os.path.join(os.path.basename(mod_dir), rel)))
                if not diffuse_exists(p, src, staging):
                    if not pack:
                        ORPHAN_NORMALS.append((os.path.basename(mod_dir), rel))
                        continue
                    why += f"; WARNING: {NO_DIFFUSE_WARNING}"
                if pack:
                    why += "; from a normal-map add-on pack (OpenMW only)"
                    NORMAL_PACKS[os.path.basename(mod_dir)] = NORMAL_PACKS.get(os.path.basename(mod_dir), 0) + 1
                move(p, os.path.join(mod_dir, "Off", "normal maps", name, rel), why)
            continue
        if el in GAME_DIRS or el in SUPPORT_DIRS:
            continue
        if el == "screenshots":                             # kept, like Docs: prefix what isn't yet
            for fn in sorted(os.listdir(src)):
                p = os.path.join(src, fn)
                if os.path.isfile(p) and fn.lower() not in VORTEX_FILES and not named(fn):
                    move(p, os.path.join(src, f"{name} - {fn}"), "screenshot without the mod's name")
            continue
        if el == "docs":                                    # prefix what isn't yet (top level only)
            for fn in sorted(os.listdir(src)):
                p = os.path.join(src, fn)
                if os.path.isfile(p) and fn.lower() not in VORTEX_FILES and not named(fn):
                    move(p, os.path.join(src, f"{name} - {fn}"), "document in Docs without the mod's name")
            continue
        if el in OUR_DIRS:
            continue
        if el in OPENMW_DIRS:
            move(src, os.path.join(openmw, e), "OpenMW-only folder")
            continue
        inside = [p for p in files_under(src) if os.path.basename(p).lower() not in VORTEX_FILES]
        named_for = el in plugins or el == name.lower() or el in DOC_DIR_NAMES
        all_docs = bool(inside) and all(is_doc(p) for p in inside)
        if named_for and any(is_doc(p) for p in inside) or all_docs:
            for p in inside:
                rel = os.path.relpath(p, src)
                if is_doc(p):
                    move(p, doc_dest(p, rel), f"readme folder '{e}' -> Docs")
                else:
                    move(p, os.path.join(extras, e, rel), f"non-document in readme folder '{e}'")
            moves.append((src, None, "remove the emptied folder"))
            continue
        move(src, os.path.join(extras, e), "not a game folder")
    return moves


REVIEW = {}            # mod folder -> (its .omwaddon files, the OpenMW scripts that make it OpenMW-only)
CONVERTED = {}         # mod folder -> (its .omwaddon files, the omw2mwse-generated folders in it): left as they are
CONVERT = {}           # OpenMW-only mod folder -> its .omwscripts files: --apply hands it to omw2mwse
PREVIEW = {}           # converted-to-be mod folder -> (ok, summary line) of omw2mwse's dry run
BLOCKED_PLAN = []      # warning texts: mods omw2mwse's dry run judged blocked (they get the usual Off\\ move)
CONVERT_MODES = ("hardcode", "normal")          # omw2mwse's own --convert-omwscripts modes
CONVERT_ACTION = "convert with omw2mwse"
CONVERTER = {"mode": None, "cmd": None, "env": None, "why": ""}   # set by main(): the mode, how to run it
CONVERTER_HOME = os.path.dirname(os.path.abspath(__file__))       # where sibling copies are looked for
CONVERTER_TIMEOUT = 600

def deleted_dir(staging):
    """Where deleted mods go: beside the staging folder in use, "<its name> - deleted by vortex_tidy"."""
    staging = os.path.abspath(staging).rstrip("\\/")
    return os.path.join(os.path.dirname(staging), os.path.basename(staging) + " - deleted by vortex_tidy")


def omw_converted(mod_dir):
    """The mod folders under <mod>\\MWSE\\mods that the OpenMW converter (omw2mwse) generated, recognised by its
    markers (mwdialog_paths.omw_generated_dir: its manifest, or a loader with its header or omwcompat use), as
    paths relative to the mod; [] for a mod nothing converted."""
    mods = os.path.join(mod_dir, existing(mod_dir, "MWSE"), "mods")
    found = []
    if not os.path.isdir(mods):
        return found
    for base, dirs, _fs in os.walk(mods):
        keep = []
        for d in sorted(dirs):
            if MP.omw_generated_dir(os.path.join(base, d)):
                found.append(os.path.relpath(os.path.join(base, d), mod_dir))
            else:
                keep.append(d)
        dirs[:] = keep
    return found


def _openmw_package_scripts(p, label):
    """*.omwscripts and a scripts folder directly in an OpenMW package folder p (label: its path in the mod)."""
    out = []
    try:
        names = sorted(os.listdir(p))
    except OSError:
        return out
    for x in names:
        if x.lower().endswith(".omwscripts") or (x.lower() == "scripts" and os.path.isdir(os.path.join(p, x))):
            out.append(os.path.join(label, x) + ("\\" if os.path.isdir(os.path.join(p, x)) else ""))
    return out


def has_mwse_lua(mod_dir):
    """True when the mod has real MWSE Lua: a .lua file anywhere under its MWSE folder that the OpenMW converter
    did not generate (its mods and its omwcompat runtime, recognised by their markers, don't count). A mod with
    it is MWSE-first: its OpenMW scripts go to Off\\ and are never converted."""
    root = os.path.join(mod_dir, existing(mod_dir, "MWSE"))
    if not os.path.isdir(root):
        return False
    for base, dirs, fns in os.walk(root):
        dirs[:] = [d for d in dirs if not (MP.omw_generated_dir(os.path.join(base, d))
                                           or MP.omw_runtime_path(os.path.join(base, d)))]
        if any(fn.lower().endswith(".lua") and not MP.omw_runtime_path(os.path.join(base, fn)) for fn in fns):
            return True
    return False


def openmw_only(mod_dir, entries):
    """The .omwscripts files of a mod that is OpenMW-only and not converted yet ([] otherwise): it has OpenMW
    scripts (an *.omwscripts file at its root, in OpenMW\\ or set aside under Off\\), no real MWSE Lua
    (has_mwse_lua) and no omw2mwse output (omw_converted)."""
    oms = [s for s in openmw_scripts(mod_dir, entries) if s.lower().endswith(".omwscripts")]
    if not oms or omw_converted(mod_dir) or has_mwse_lua(mod_dir):
        return []
    return oms


def _converter_cmd(path):
    """The command line that runs the converter at path: an .exe/.cmd/.bat as it is, a Python script (the
    bin\\omw2mwse launcher, omw2mwse.py) with this Python."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".exe", ".com", ".cmd", ".bat"):
        return [path]
    try:
        with open(path, "rb") as f:
            head = f.read(128)
    except OSError:
        head = b""
    if ext == ".py" or (head.startswith(b"#!") and b"python" in head.split(b"\n", 1)[0]):
        return [sys.executable, path]
    return [path]


def find_converter(home=None):
    """(command, env, where) for omw2mwse, or (None, None, "") when it isn't there. Looked for on PATH, then as
    a sibling tool beside these tools (in this folder, its tools\\ folder or the folder above), as an
    omw2mwse(.exe/.cmd/.bat/.py) file, a converter checkout's bin\\omw2mwse, or the omw2mwse Python package
    (run as python -m omw2mwse). No fixed paths."""
    names = ("omw2mwse.exe", "omw2mwse.cmd", "omw2mwse.bat", "omw2mwse.py", "omw2mwse")
    for d in os.environ.get("PATH", "").split(os.pathsep):   # by hand: .py and a bare launcher aren't in PATHEXT
        for name in names:
            p = os.path.join(d.strip('"'), name) if d else ""
            if p and os.path.isfile(p):
                return _converter_cmd(p), None, p
    home = home or CONVERTER_HOME
    for d in (home, os.path.join(home, "tools"), os.path.dirname(home)):
        for rel in ("omw2mwse.exe", "omw2mwse.cmd", "omw2mwse.bat", "omw2mwse.py", "omw2mwse",
                    os.path.join("omw2mwse", "bin", "omw2mwse"), os.path.join("openmw-mwse", "bin", "omw2mwse")):
            p = os.path.join(d, rel)
            if os.path.isfile(p):
                return _converter_cmd(p), None, p
        pkg = os.path.join(d, "omw2mwse")
        if os.path.isfile(os.path.join(pkg, "__main__.py")) and os.path.isfile(os.path.join(pkg, "cli.py")):
            env = dict(os.environ)
            env["PYTHONPATH"] = d + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
            return [sys.executable, "-m", "omw2mwse"], env, pkg
    return None, None, ""


def setup_converter(mode):
    """main(): mode None (--no-convert-omwscripts) or one of CONVERT_MODES; finds the converter."""
    CONVERTER.update(mode=mode, cmd=None, env=None, why="")
    if mode:
        CONVERTER["cmd"], CONVERTER["env"], CONVERTER["why"] = find_converter()


_VORTEX_INFO = {}       # mod folder name -> what Vortex knows (read once per run)


def vortex_info(mod_dir):
    """{"title", "author"} Vortex knows for a staging mod folder (read-only; {} when it can't be read or knows
    nothing): omw2mwse credits them in the MCM page, notices and metadata."""
    key = os.path.basename(mod_dir)
    if key not in _VORTEX_INFO:
        try:
            _VORTEX_INFO[key] = MP.vortex_mod_info(key) or {}
        except Exception:                             # noqa: BLE001 - no info is not an error
            _VORTEX_INFO[key] = {}
    return _VORTEX_INFO[key]


def run_converter(mod_dir, mode, dry_run=False):
    """Run omw2mwse --convert-omwscripts=<mode> <mod_dir> --json (hardcode: --accept-hardcode-conversions, as
    tidy runs it without a prompt; --apply already asked), with --title/--author when Vortex has them.
    (exit code, parsed JSON or None, error text)."""
    argv = list(CONVERTER["cmd"]) + [f"--convert-omwscripts={mode}", mod_dir, "--json"]
    if mode == "hardcode":
        argv.append("--accept-hardcode-conversions")
    info = vortex_info(mod_dir)
    for opt in ("title", "author"):
        if info.get(opt):
            argv += ["--" + opt, info[opt]]
    if dry_run:
        argv.append("--dry-run")
    try:
        r = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=CONVERTER["env"],
                           timeout=CONVERTER_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as e:
        return None, None, f"could not run omw2mwse ({e})"
    out = r.stdout.decode("utf-8", "replace")
    data = None
    try:
        data = json.loads(out)
    except ValueError:
        i = out.find("{")
        if i >= 0:
            try:
                data = json.loads(out[i:])
            except ValueError:
                data = None
    err = r.stderr.decode("utf-8", "replace").strip()
    if not isinstance(data, dict):
        data = None
    return r.returncode, data, (err.splitlines()[-1] if err else "")


def _converter_problem(data, err):
    """The first error/conflict message in a converter result, for a one-line warning."""
    for m in (data or {}).get("mods") or []:
        for c in m.get("conflicts") or []:
            return f"{c.get('path')}: {c.get('reason')}"
        if m.get("message"):
            return str(m["message"])
    for al in (data or {}).get("alerts") or []:
        if al.get("level") == "error":
            return str(al.get("message"))
    return err or "no details"


def converter_summary(code, data, err):
    """(ok, one line) for a converter result. Exit 0: what it did; 4: a conflict (nothing written for that mod);
    3: hard-code conversion refused; 2/other: an error."""
    if code is None:
        return False, err
    if data is None:
        return False, f"omw2mwse exit {code}, no JSON result" + (f" ({err})" if err else "")
    if code == 4:
        return False, f"conflict, nothing written for it: {_converter_problem(data, err)}"
    if code == 3:
        return False, f"hard-code conversion refused, nothing written for it: {_converter_problem(data, err)}"
    if code != 0:
        return False, f"omw2mwse error (exit {code}): {_converter_problem(data, err)}"
    bits = []
    for m in data.get("mods") or []:
        blockers = sum(1 for al in m.get("alerts") or [] if al.get("code") == "blocker")
        b = f"{m.get('name')} {m.get('status')}, verdict {m.get('verdict')}"
        if blockers:
            b += f", {blockers} blocker(s)"
        if m.get("rewrites"):
            b += f", {len(m['rewrites'])} hard-coded value(s) as settings"
        bits.append(b)
    what = "; ".join(bits) or "nothing to convert"
    return True, what + ("" if data.get("dryRun") else (" (changed)" if data.get("changed") else " (unchanged)"))


def convert_lines(d, oms, mode):
    """The plan lines of one OpenMW-only mod handed to the converter (an action --apply compares)."""
    return [f"\n{d}   [{mod_name(d)}]",
            f"    {CONVERT_ACTION} ({mode}): OpenMW-only, no MWSE Lua ({', '.join(oms)})"]


def blocked_reason(entry):
    """For a converter result entry with verdict "blocked": 'N blocker(s), first: <message>'."""
    bl = [al for al in entry.get("alerts") or [] if al.get("code") == "blocker"]
    first = f", first: {bl[0].get('message')}" if bl else ""
    return f"{len(bl)} blocker(s){first}"


def preview_verdicts(data):
    """[(mod name, verdict, entry)] of a converter result's ok mods."""
    return [(m.get("name"), m.get("verdict"), m) for m in (data or {}).get("mods") or []
            if m.get("status") == "ok"]


def unconverted_moves(mod_dir):
    """The usual plan_mod moves of a mod, as if it were not going to be converted (blocked by omw2mwse: its
    OpenMW files go to Off\\<plugin name>\\OpenMW\\, the whole package: see whole_package_moves)."""
    saved = CONVERTER["mode"]
    CONVERTER["mode"] = None
    try:
        res = plan_mod(mod_dir)
    finally:
        CONVERTER["mode"] = saved
    return res if isinstance(res, list) else []


def converter_plugins(entry, manifest_path=None):
    """The plugins omw2mwse reports for one mod: [{name, source, sourceRel, kind, placement, status, path, reason}]
    (0.2.2: optional instead of placement/status/path) from its JSON entry ("plugins"), else from its manifest
    ("plugins"); None when neither has the key (an older omw2mwse)."""
    got = entry.get("plugins") if isinstance(entry, dict) else None
    if not isinstance(got, list) and manifest_path:
        try:
            with open(manifest_path, encoding="utf-8") as f:
                got = json.load(f).get("plugins")
        except (OSError, ValueError, AttributeError):
            got = None
    return [p for p in got if isinstance(p, dict) and p.get("name")] if isinstance(got, list) else None


def plugin_notes(mname, plugins):
    """One NOTE text per plugin omw2mwse did not leave at the Data Files root, with the converter's reason. The
    converter places the files itself (omw2mwse 0.2.3: placement root | extras | off, status required |
    undetermined | obsolete, path relative to the mod); only placement root is enabled by default. Tidy never
    moves, renames or enables a plugin, and never reads readmes or FOMOD text for this. An older converter's
    boolean "optional" (true) counts as not-root. An entry with neither field counts as root: no note."""
    out = []
    for p in plugins or []:
        place = str(p.get("placement") or "").lower()
        why = p.get("reason") or "no reason given"
        if not place and p.get("optional") is True:         # omw2mwse 0.2.2: optional, no placement
            out.append(f"{mname}: {p['name']} is optional ({why}): tidy leaves it where it is and never enables it; "
                       f"enable it in Vortex only if you want that option")
        elif place and place != "root":
            where = p.get("path") or p["name"]
            status = p.get("status") or "unknown"
            out.append(f"{mname}: {p['name']} was placed by omw2mwse at {where} (placement {place}, status "
                       f"{status}; {why}): it is not enabled by default, and tidy does not move, rename or "
                       f"enable it")
    return out


def shipped_plugins(files):
    """FALLBACK for a manifest with no "plugins" key (an older omw2mwse): root plugins (.esp/.esm) in its file
    list that the converter did not make from an .omwaddon/.omwgame (no such file under its Off package): the
    package shipped them itself."""
    keys = {k.replace("\\", "/") for k in files or {}}
    low = {k.lower() for k in keys}
    out = []
    for k in sorted(keys):
        stem, ext = os.path.splitext(k)
        if "/" in k or ext.lower() not in (".esp", ".esm"):
            continue
        src = ".omwaddon" if ext.lower() == ".esp" else ".omwgame"
        if not any(x.endswith("/" + stem.lower() + src) and x.startswith("off/") for x in low):
            out.append(k)
    return out


def _rel_in(mod_dir, p):
    """p (a path the converter printed: relative to the mod, or absolute) as a '/'-separated path relative to
    mod_dir; '' for the mod folder itself."""
    if not p:
        return ""
    if os.path.isabs(p):
        p = os.path.relpath(os.path.realpath(p), os.path.realpath(mod_dir))
    p = p.replace("\\", "/").strip("/")
    return "" if p == "." else p


def conversion_op(mod_dir, entry, mode):
    """The undo record of one converted mod in a converter result (an entry of its JSON "mods"): where its
    original package was (relocatedFrom, or source when it was not moved), where omw2mwse keeps it now (off),
    the folder and manifest it wrote, and the files the manifest lists, with their hashes."""
    name = entry.get("name")
    off = _rel_in(mod_dir, entry.get("off") or entry.get("source"))
    frm = _rel_in(mod_dir, entry.get("relocatedFrom") if entry.get("relocatedFrom") is not None
                  else entry.get("source"))
    tree = "MWSE/mods/mwsuite/openmw/" + str(name)
    for g in omw_converted(mod_dir):
        if os.path.basename(g) == name:
            tree = g.replace("\\", "/")
    files = _manifest_files(os.path.join(mod_dir, *(tree.split("/") + [MP.OMW_MANIFEST])))
    return {"omw_convert": mod_dir, "name": name, "mode": mode, "from": frm, "off": off, "tree": tree,
            "relocated": sorted(entry.get("relocated") or []), "files": files or {}}


def journal_conversions(staging, ops, head_extra):
    """Append the undo records of a conversion to the journal, on disk before anything else happens."""
    head = {"run": time.strftime("%Y-%m-%d %H:%M:%S"), "staging": staging}
    head.update(head_extra or {})
    with open(JOURNAL, "a", encoding="utf-8") as j:
        j.write(json.dumps(head) + "\n")
        for op in ops:
            j.write(json.dumps(op) + "\n")
        j.flush()
        os.fsync(j.fileno())


def _undo_now(op, staging):
    """Undo a conversion at once (omw2mwse's verdict was blocked). True when it is undone."""
    cstate = {"mods": 0, "removed": 0, "restored": 0, "defer": [], "names": set(), "staging": staging}
    ok = undo_conversion(op, staging, cstate)
    finish_conversions(cstate)
    return ok


def convert_apply(staging, mods, mode, head_extra=None):
    """--apply: run the converter on each OpenMW-only mod and journal what it changed (for --undo). A conflict
    (exit 4) or any other failure gets one WARNING line and the run goes on. A mod omw2mwse judges blocked
    (verdict "blocked": it exits 0 and still writes an active loader) is not shipped: its output is undone at
    once and its whole package goes to Off\\<plugin name>\\OpenMW\\, with one WARNING line; "partial" is converted,
    with one NOTE. Returns the mod folders not converted."""
    left = []
    for mod_dir in mods:
        code, data, err = run_converter(mod_dir, mode)
        ok, line = converter_summary(code, data, err)
        name = os.path.basename(mod_dir)
        ops, blocked, notes = [], [], []
        for mname, verdict, m in preview_verdicts(data):
            if data.get("dryRun") or not (m.get("changed") or m.get("relocated")):
                continue
            op = conversion_op(mod_dir, m, mode)
            if verdict == "blocked":
                blocked.append((mname, op, blocked_reason(m)))
                continue
            ops.append(op)
            if verdict == "partial":
                notes.append(f"{mname} is only partly supported by omw2mwse (verdict partial): converted anyway")
            for al in m.get("alerts") or []:
                if al.get("code") == "plugin-rename-clash":
                    notes.append(f"{mname}: {al.get('message')}; tidy leaves it there and never enables it")
            plugins = converter_plugins(m, os.path.join(mod_dir, *(op["tree"].split("/") + [MP.OMW_MANIFEST])))
            if plugins is not None:
                notes += plugin_notes(mname, plugins)
            else:                                    # older omw2mwse: no plugins list, so the manifest's files
                ship = shipped_plugins(op["files"])
                if ship:
                    notes.append(f"{mname} also has plugin(s) at its root that omw2mwse did not make from an "
                                 f".omwaddon/.omwgame ({', '.join(ship)}): tidy does not rename or enable them; "
                                 f"enable one in Vortex only if you want that option")
        if ops:                                      # also from a result with a conflict in another mod
            journal_conversions(staging, ops, head_extra)
        if ok:
            print(f"  converted {name} with omw2mwse ({mode}): {line}")
        else:
            moves = unconverted_moves(mod_dir)
            print(f"  WARNING: omw2mwse could not convert {name}: {line}; not converted, "
                  + ("its whole package goes to Off\\<plugin>\\OpenMW\\" if moves else "left as it is"))
            if moves:
                apply(moves, staging, None, head_extra)
            else:
                left.append(mod_dir)
        for note in notes:
            print(f"  NOTE: {note}")
        for mname, op, why in blocked:
            if _undo_now(op, staging):
                print(f"  WARNING: omw2mwse says {mname} cannot run ({why}): not converted, conversion undone, "
                      f"its whole package goes to Off\\<plugin>\\OpenMW\\")
                moves = unconverted_moves(mod_dir)
                if moves:
                    apply(moves, staging, None, head_extra)
            else:
                print(f"  WARNING: omw2mwse says {mname} cannot run ({why}), and its output could not be undone")
                left.append(mod_dir)
    return left


def openmw_scripts(mod_dir, entries):
    """The OpenMW Lua scripts a mod has: *.omwscripts files and scripts folders, at its root, in OpenMW\\, or in
    an original package set aside under Off\\ (Off\\<mod>\\OpenMW\\, where omw2mwse keeps it, or
    Off\\OpenMW\\<mod>\\, where earlier tidy runs put it): no scripts at the root does not mean none."""
    found = []
    for e in entries:
        p = os.path.join(mod_dir, e)
        if e.lower().endswith(".omwscripts"):
            found.append(e)
        elif os.path.isdir(p) and e.lower() == "scripts":
            found.append(e + "\\")
        elif os.path.isdir(p) and e.lower() == "openmw":
            for x in os.listdir(p):
                if x.lower().endswith(".omwscripts") or (x.lower() == "scripts" and os.path.isdir(os.path.join(p, x))):
                    found.append(os.path.join(e, x) + ("\\" if os.path.isdir(os.path.join(p, x)) else ""))
        elif os.path.isdir(p) and e.lower() == "off":
            try:
                subs = sorted(os.listdir(p))
            except OSError:
                subs = []
            for x in subs:
                px = os.path.join(p, x)
                if not os.path.isdir(px):
                    continue
                if x.lower() == "openmw":                  # Off\OpenMW\<mod>\
                    for y in sorted(os.listdir(px)):
                        if os.path.isdir(os.path.join(px, y)):
                            found += _openmw_package_scripts(os.path.join(px, y), os.path.join(e, x, y))
                for y in sorted(os.listdir(px)):           # Off\<mod>\OpenMW\
                    if y.lower() == "openmw" and os.path.isdir(os.path.join(px, y)) and x.lower() != "openmw":
                        found += _openmw_package_scripts(os.path.join(px, y), os.path.join(e, x, y))
    return found


def review(staging, moves, assume_keep=False):
    """Mods with an .omwaddon, no .esp/.esm and OpenMW scripts don't work in Morrowind. Show each, let you look,
    and delete it if you want: it goes to deleted_dir(staging) (beside the staging folder), so it can come back.
    Returns the moves without those of deleted mods, and the deletions (journaled like moves)."""
    gone = []
    for mod_dir, (addons, scripts) in sorted(REVIEW.items()):
        name = os.path.basename(mod_dir)
        print("\n" + "!" * 70)
        print(f"OpenMW-only mod: {name}")
        print("  OpenMW plugin(s); no .esp or .esm:")
        print(MT.bullets(addons, indent="  "))
        print("  OpenMW scripts:")
        print(MT.bullets(scripts, indent="  "))
        print("  It needs OpenMW's Lua scripting, so in Morrowind it would do little or nothing (or break).")
        if assume_keep or not sys.stdin.isatty():
            print("  Kept (not asked: --yes). Remove it in Vortex if you don't want it.")
            continue
        while True:
            ans = input("  [o] open the folder to look   [d] delete this mod   [k] keep it   > ").strip().lower()
            if ans == "o":
                try:
                    os.startfile(mod_dir)
                except (AttributeError, OSError) as e:
                    print(f"  could not open it: {e}")
                continue
            if ans in ("d", "k", ""):
                break
        if ans != "d":
            print("  Kept.")
            continue
        sure = input(f"  Delete '{name}' from the staging folder? Type yes: ").strip().lower()
        if sure != "yes":
            print("  Kept.")
            continue
        dst = os.path.join(deleted_dir(staging), name)
        gone.append((mod_dir, dst, "OpenMW-only mod deleted (moved out of the staging folder)"))
        moves = [m for m in moves if not m[0].startswith(mod_dir + os.sep) and m[0] != mod_dir]
        print(f"  Will be moved to {dst}. Then remove '{mod_name(name)}' in Vortex too.")
    return moves, gone


def move_lines(d, res, staging):
    """The plan lines of one mod's moves (d: its folder name)."""
    out = [f"\n{d}   [{mod_name(d)}]"]
    base = os.path.join(staging, d)
    for src, dst, why in res:
        rs = os.path.relpath(src, base)
        if dst is None:
            out.append(f"    remove empty  {rs}")
        else:
            out.append(f"    {rs}  ->  {os.path.relpath(dst, base)}   ({why})")
    return out


def moves_as_lines(moves, staging):
    """Plan lines for a list of moves (grouped by mod folder, in order)."""
    out, groups = [], {}
    for mv in moves:
        rel = os.path.relpath(mv[0], staging)
        d = rel.split(os.sep)[0] if not rel.startswith("..") else os.path.dirname(mv[0])
        groups.setdefault(d, []).append(mv)
    for d, res in groups.items():
        out += move_lines(d, res, staging) if not os.path.isabs(d) else \
            [f"\n{d}"] + [f"    {a}  ->  {b}   ({w})" for a, b, w in res]
    return out


def run_plan(args):
    mods = sorted(d for d in os.listdir(args.staging) if os.path.isdir(os.path.join(args.staging, d))
                  and d.lower() != "off")                       # your own Off folder is never touched
    if args.only:
        mods = [d for d in mods if any(fnmatch.fnmatch(d.lower(), pat.lower()) for pat in args.only)]
    lines, all_moves, skipped, touched = [], [], [], 0
    ORPHAN_NORMALS.clear()
    NORMAL_PACKS.clear()
    CONVERTED.clear()
    CONVERT.clear()
    _VORTEX_INFO.clear()
    PREVIEW.clear()
    del BLOCKED_PLAN[:]
    CONVERTER["missed"] = 0
    _TEX_INDEX.clear()
    pats = blacklist(create=bool(getattr(args, "apply", False))) + (args.skip or [])
    for d in mods:
        hit = next((pt for pt in pats if fnmatch.fnmatch(d.lower(), pt.lower())), None)
        if hit:
            skipped.append((d, f"blacklisted ({hit})"))
            continue
        res = plan_mod(os.path.join(args.staging, d))
        if isinstance(res, str):
            skipped.append((d, res))
            continue
        full = os.path.join(args.staging, d)
        if full in CONVERT:
            code, data, err = run_converter(full, CONVERTER["mode"], dry_run=True)   # a preview: nothing is written
            blocked = [(n, blocked_reason(m)) for n, v, m in preview_verdicts(data) if v == "blocked"]
            if blocked:                              # omw2mwse would write an active loader that can't work
                del CONVERT[full]
                BLOCKED_PLAN.append(f"{d}: omw2mwse says {blocked[0][0]} cannot run ({blocked[0][1]}): not converted, "
                                    f"its whole package goes to Off\\<plugin>\\OpenMW\\")
                res = unconverted_moves(full)
            else:
                PREVIEW[full] = converter_summary(code, data, err)
                for n, v, _m in preview_verdicts(data):
                    if v == "partial":
                        NOTES.append(f"{d}: omw2mwse verdict partial for {n}: it will be converted, only partly "
                                     f"supported")
                touched += 1
                lines += convert_lines(d, CONVERT[full], CONVERTER["mode"])
                continue
        if not res:
            continue
        touched += 1
        lines += move_lines(d, res, args.staging)
        all_moves += res
    head = [f"vortex_tidy plan, {time.strftime('%Y-%m-%d %H:%M')}: {len(mods)} mod(s), {touched} to change, "
            f"{sum(1 for m in all_moves if m[1])} move(s); {len(skipped)} left alone"]
    for d, why in skipped:
        head.append(f"  - left alone: {d} ({why})")
    if CONVERTER.get("missed"):                      # one line: the converter isn't there
        head.append(f"  - WARNING: omw2mwse (the OpenMW converter) was not found on PATH or beside these tools: "
                    f"{CONVERTER['missed']} OpenMW-only mod(s) get their whole package moved to Off\\<plugin>\\OpenMW\\ instead")
    for text in BLOCKED_PLAN:
        head.append(f"  - WARNING: {text}")
    for mod_dir in sorted(CONVERT):                  # the preview (dry run); notes, not actions
        ok, line = PREVIEW[mod_dir]
        head.append(f"  - {'omw2mwse preview' if ok else 'WARNING: omw2mwse preview'} for "
                    f"{os.path.basename(mod_dir)} ({CONVERTER['mode']}): {line}"
                    + ("" if ok else "; if --apply cannot convert it either, its whole package goes to Off\\<plugin>\\OpenMW\\"))
    for d, n in sorted(NORMAL_PACKS.items()):
        NOTES.append(f"{d}: a normal-map add-on pack ({n} normal map(s) under a 'normal maps' path) - not "
                     f"applicable to classic Morrowind (only OpenMW uses normal maps); consider removing it in Vortex")
    if ORPHAN_NORMALS:
        NOTES.append(f"{len(ORPHAN_NORMALS)} normal map(s) with no diffuse texture anywhere left in place (no "
                     f"stand-in); mwdialog_check --full's unused-asset purge removes the unused ones")
    for mod_dir, (addons, gen) in sorted(CONVERTED.items()):
        NOTES.append(f"{os.path.basename(mod_dir)}: converted by omw2mwse ({', '.join(gen)}); its "
                     f"{', '.join(addons)} (no .esp beside it) stays as it is - current omw2mwse installs the .esp "
                     f"itself and keeps the original under Off\\, so this is an older conversion's copy: re-run omw2mwse "
                     f"(--convert-omwscripts) rather than renaming it here")
    for note in NOTES:
        head.append(f"  - NOTE: {note}")
    for d, rel in ORPHAN_NORMALS[:50]:
        lines.append(f"  - left in place (no diffuse texture anywhere): {d}\\{rel}")
    for mod_dir, (addons, scripts) in sorted(REVIEW.items()):
        head.append(f"  - NEEDS A LOOK (OpenMW-only: {', '.join(addons)}, no .esp, scripts {', '.join(scripts)}): "
                    f"{os.path.basename(mod_dir)} - --apply stops at it and offers to delete it")
    args._moves_text = "\n".join(head + lines) + "\n"
    if getattr(args, "_write_plan", True):
        PF.write_atomic(PLAN, args._moves_text)
    print("\n".join(head))
    print("\n".join(lines[:200]))
    if len(lines) > 200:
        print(f"... ({len(lines) - 200} more lines in {PLAN})")
    print(f"\nFull plan: {PLAN}")
    return all_moves


def apply(moves, staging, progress=None, head_extra=None):
    """Make the moves, journaling each. progress (a list) gets the index of every move done, as it is done,
    so an interrupted run knows what is left. Returns the moves that failed."""
    done, failed = 0, []
    head = {"run": time.strftime("%Y-%m-%d %H:%M:%S"), "staging": staging}
    head.update(head_extra or {})
    with open(JOURNAL, "a", encoding="utf-8") as j:
        j.write(json.dumps(head) + "\n")
        j.flush()
        for i, (src, dst, why) in enumerate(moves):
            try:
                if dst is None:
                    for base, dirs, fns in os.walk(src, topdown=False):   # only empty folders go
                        if not os.listdir(base):
                            os.rmdir(base)
                            j.write(json.dumps({"rmdir": base}) + "\n")
                            j.flush()
                    if progress is not None:
                        progress.append(i)
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                # journaled (on disk) before the move: a crash between the two never leaves a move --undo can't see
                j.write(json.dumps({"src": src, "dst": dst}) + "\n")
                j.flush()
                os.fsync(j.fileno())
                os.rename(src, dst)          # same drive: a rename, so Vortex's hard links keep their file
                done += 1
                if progress is not None:
                    progress.append(i)
                if NO_DIFFUSE_WARNING in why:
                    print(f"  WARNING: moved {src} -> {dst}: {NO_DIFFUSE_WARNING}")
            except OSError as e:
                print(f"  could not move {src}: {e}", file=sys.stderr)
                failed.append((src, dst, why))
    print(f"Moved {done} item(s). Journal: {JOURNAL} (--undo puts them back). Now Deploy in Vortex.")
    return failed


def _read_journal_runs():
    """The journal as [{"head", "ops"}], oldest first (unreadable lines skipped)."""
    runs, cur = [], None
    with open(JOURNAL, encoding="utf-8") as jf:
        journal_lines = jf.read().splitlines()
    for line in journal_lines:
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:                            # a line cut short when an --apply was interrupted
            print(f"  (skipped an unreadable journal line: {line[:80]!r})", file=sys.stderr)
            continue
        if "run" in rec:
            cur = {"head": rec, "ops": []}
            runs.append(cur)
        elif cur is not None:
            cur["ops"].append(rec)
    return runs


def _last_apply(runs):
    """Pop the runs of the last --apply off `runs`: its moves, Lua patches and asset repairs are journaled under
    one head each, all with the same "apply" id. An older journal without the id: just the last head."""
    group = [runs.pop()]
    key = group[0]["head"].get("apply")
    while key and runs and runs[-1]["head"].get("apply") == key:
        group.insert(0, runs.pop())
    return group


def _luafix_preflight(ops, force):
    """Why the journaled Lua patches (mods' files and MWSE's core files alike) can't all be put back, or []."""
    if not ops:
        return []
    lf = _luafix()
    if lf is None:
        return ["mwdialog_luafix.py could not be loaded, so the Lua files it patched can't be put back"]
    out = []
    for op in ops:
        p = op["luafix"]
        try:
            with open(p, "rb") as f:
                cur = lf.sha(f.read())
        except OSError as e:
            out.append(f"{p}: can't be read ({e})")
            continue
        if cur == op.get("before"):
            continue
        if cur != op.get("after") and not force:
            out.append(f"{p}: changed since it was patched (--undo --force puts the original back anyway)")
            continue
        try:
            with open(op["backup"], "rb") as f:
                ok = lf.sha(f.read()) == op.get("before")
        except OSError:
            out.append(f"{p}: its original is missing (was kept at {op['backup']})")
            continue
        if not ok:
            out.append(f"{p}: its kept original ({op['backup']}) is not the file that was patched")
    return out


def undo(force=False):
    """--undo: put back everything the last --apply did, newest first: the asset repairs (each original back at
    its own path, the files the repairs made removed), the Lua patches (in place), then the moves. Asset and
    Lua originals are checked first (present, the same hash as when kept; the file not changed since, unless
    force): if any can't be put back, nothing is changed and the reason is printed. What could not be put back
    stays in the journal, so --undo can try again."""
    if not os.path.exists(JOURNAL):
        print("Nothing to undo (no journal).")
        return 1
    runs = _read_journal_runs()
    if not runs:
        print("Nothing to undo.")
        return 1
    group = _last_apply(runs)
    aops = [op for r in group for op in r["ops"] if _is_asset_op(op)]
    lops = [op for r in group for op in r["ops"] if "luafix" in op]
    aplan = _asset_undo_plan(aops)
    problems = _asset_preflight(aplan, force) + _luafix_preflight(lops, force)
    if problems:
        print("--undo changed nothing: these can't be put back as they were before vortex_tidy --apply:",
              file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        print("The journal is unchanged. Put the missing originals back (an asset's original may also still be in "
              "its mod's Off\\ folder), or --undo --force to overwrite files changed since.", file=sys.stderr)
        return 1
    back = 0
    cstate = {"mods": 0, "removed": 0, "restored": 0, "defer": [], "names": set(), "staging": None}
    conv_failed = set()                               # omw2mwse conversions came last in the --apply: first out
    for r in reversed(group):
        for op in reversed(r["ops"]):
            if "omw_convert" in op and not undo_conversion(op, r["head"].get("staging"), cstate):
                conv_failed.add(id(op))
    restored, removed, afailed = _asset_undo(aplan, aops, force) if aops else (0, 0, [])
    keep_assets = bool(afailed)                       # every asset op stays for another try (putting back is idempotent)
    out_runs = []
    for r in reversed(group):
        left = []                                     # ops not undone: kept in the journal for another try
        for op in reversed(r["ops"]):
            if _is_asset_op(op):
                if keep_assets:
                    left.append(op)
                continue
            if "luafix" in op:                        # a Lua file mwdialog_luafix patched in place (MWSE core too)
                lf = _luafix()
                ok, msg = lf.restore_op(op, force) if lf else (False, f"{op['luafix']}: mwdialog_luafix.py not found")
                if ok:
                    back += 1
                else:
                    print("  " + msg, file=sys.stderr)
                    left.append(op)
                continue
            if "omw_convert" in op:                   # undone above; one that could not be stays for another try
                if id(op) in conv_failed:
                    left.append(op)
                continue
            try:
                if "rmdir" in op:
                    os.makedirs(op["rmdir"], exist_ok=True)
                elif os.path.exists(op["dst"]):
                    if os.path.exists(op["src"]):
                        print(f"  not put back (something is at {op['src']} already): {op['dst']}", file=sys.stderr)
                        left.append(op)
                        continue
                    os.makedirs(os.path.dirname(op["src"]), exist_ok=True)
                    os.rename(op["dst"], op["src"])
                    back += 1
                elif os.path.exists(op["src"]):
                    back += 1                         # journaled, but the move itself never happened
                else:
                    print(f"  not put back (no longer there): {op['dst']}", file=sys.stderr)
                    left.append(op)
            except OSError as e:
                print(f"  could not put back {op.get('dst')}: {e}", file=sys.stderr)
                left.append(op)
        top = r["head"].get("staging")            # an old journal without it: no folder is removed
        top = os.path.normcase(os.path.abspath(top)) if top else None
        for d in {os.path.dirname(op["dst"]) for op in r["ops"] if "dst" in op} if top else ():   # emptied folders
            try:
                # only folders inside the staging folder: never the staging folder itself or anything above it
                while d and os.path.normcase(os.path.abspath(d)).startswith(top + os.sep) \
                        and os.path.isdir(d) and not os.listdir(d):
                    os.rmdir(d)
                    d = os.path.dirname(d)
            except OSError:
                pass
        if left:
            out_runs.insert(0, {"head": r["head"], "ops": list(reversed(left))})
    finish_conversions(cstate)                        # the shared runtime, once every mod of the run is undone
    runs.extend(out_runs)
    tmp = JOURNAL + ".tmp"
    with open(tmp, "w", encoding="utf-8") as j:
        for r in runs:
            j.write(json.dumps(r["head"]) + "\n")
            for op in r["ops"]:
                j.write(json.dumps(op) + "\n")
    os.replace(tmp, JOURNAL)
    if back or not cstate["mods"]:
        print(f"Put back {back} item(s) moved or patched by the run of {group[-1]['head']['run']}. "
              f"Deploy in Vortex again.")
    if cstate["mods"]:
        print(f"omw2mwse conversions undone: {cstate['mods']} mod(s), {cstate['removed']} generated file(s) removed, "
              f"{cstate['restored']} original(s) put back. Deploy in Vortex again.")
    if aops:
        print(f"Asset repairs: {restored} original(s) put back at their own path, {removed} file(s) the repairs made "
              f"removed.")
    n_left = sum(len(r["ops"]) for r in out_runs)
    if n_left:
        print(f"{n_left} item(s) could not be put back (listed above); they stay in the journal "
              f"({JOURNAL}), so --undo can try them again.")
        return 1
    return 0


# ---------------------------------------------------------------- omw2mwse conversions, for --undo
# --apply journals each conversion as it is made ("omw_convert": where the original package was, where omw2mwse
# keeps it, the manifest's file list with hashes). --undo then (1) puts the original package back from
# Off\<Mod>\OpenMW\ at its original paths (a file already there with the same content just lets the Off copy go;
# a different one is kept, with a WARNING), (2) deletes what omw2mwse wrote, taken from its manifest
# (omw2mwse-manifest.json, else the copy journaled at convert time, else whatever carries its markers plus the
# mod's MWSE\config\omwcompat_<Mod>.json): a file whose hash is no longer the manifest's was edited, so it stays,
# with one WARNING line; never a path of the original package, never anything under the Off package; the manifest
# goes last and only if nothing stayed, (3) removes the emptied folders and (4) the shared MWSE\lib\omwcompat
# runtime once no converted mod is left in staging or Data Files. Running it again finds nothing to do.

def _manifest_files(path):
    """{relative path: sha256} from an omw2mwse-manifest.json, or None when it is missing or unreadable."""
    try:
        with open(path, encoding="utf-8") as f:
            files = json.load(f).get("files")
    except (OSError, ValueError, AttributeError):
        return None
    return files if isinstance(files, dict) else None


def _inside(base, rel):
    """base + the '/'-separated rel, or None when rel is empty, absolute or climbs out of base."""
    parts = [x for x in re.split(r"[\\/]+", rel or "") if x]
    if not parts or os.path.isabs(rel) or any(x == ".." or ":" in x for x in parts):
        return None
    return os.path.join(base, *parts)


def _prune_empty(path, top):
    """Remove path (a folder) and its parents while they are empty, never top or anything above it."""
    top = _nk(top)
    d = path
    try:
        while d and _nk(d).startswith(top + os.sep) and os.path.isdir(d) and not os.listdir(d):
            os.rmdir(d)
            d = os.path.dirname(d)
    except OSError:
        pass


def _warn(msg):
    print("  WARNING: " + msg, file=sys.stderr)


def _off_files(off_abs):
    out = []
    for base, _ds, fns in os.walk(off_abs):
        for fn in sorted(fns):
            p = os.path.join(base, fn)
            out.append((os.path.relpath(p, off_abs), p))
    return sorted(out)


def undo_conversion(op, staging, cstate):
    """Undo one journaled conversion (see above). True when done (also when files stayed with a WARNING);
    False when it could not be done at all (it stays in the journal for another try)."""
    mod_dir = op["omw_convert"]
    name = op.get("name") or os.path.basename(mod_dir)
    if not os.path.isdir(mod_dir):
        print(f"  not undone (the mod folder is gone): {mod_dir}", file=sys.stderr)
        return False
    cstate["staging"] = cstate["staging"] or staging
    cstate["names"].add(name)
    touched = []                                      # folders to tidy up afterwards
    kept = False
    try:
        off_abs = _inside(mod_dir, op.get("off"))
        frm = op.get("from") or ""
        frm_abs = _inside(mod_dir, frm) if frm else mod_dir
        moved_off = bool(off_abs and frm_abs and _nk(off_abs) != _nk(frm_abs))
        originals = set()
        if moved_off and os.path.isdir(off_abs):      # (1) the original package, back at its own paths
            for rel, src in _off_files(off_abs):
                dst = _inside(frm_abs, rel.replace(os.sep, "/"))
                if dst is None:
                    continue
                originals.add(_nk(dst))
                if not os.path.exists(dst):
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    os.rename(src, dst)
                    cstate["restored"] += 1
                    touched.append(os.path.dirname(src))
                elif _sha256(dst) == _sha256(src):
                    os.remove(src)                    # a copy of what is already in place
                    touched.append(os.path.dirname(src))
                else:
                    _warn(f"kept {src}: {dst} is there already and differs")
                    kept = True
        files = _manifest_files(os.path.join(mod_dir, *(op["tree"].split("/") + [MP.OMW_MANIFEST]))) \
            or op.get("files") or None
        gen = []                                      # (path, expected hash or None)
        if files:                                     # (2) what omw2mwse wrote, by its own record
            for rel, h in sorted(files.items()):
                p = _inside(mod_dir, rel)
                if p is None or _nk(p) in originals or (off_abs and (_nk(p) + os.sep).startswith(_nk(off_abs) + os.sep)):
                    continue
                gen.append((p, h))
        else:                                         # no record left: what carries omw2mwse's markers
            tree = _inside(mod_dir, op["tree"])
            if tree and MP.omw_generated_dir(tree):
                for base, _ds, fns in os.walk(tree):
                    gen += [(os.path.join(base, fn), None) for fn in fns]
            cfg = os.path.join(mod_dir, "MWSE", "config", f"omwcompat_{name}.json")
            if os.path.isfile(cfg):
                gen.append((cfg, None))
            lib = os.path.join(mod_dir, "MWSE", "lib")
            for base, _ds, fns in (os.walk(lib) if os.path.isdir(lib) else ()):
                gen += [(os.path.join(base, fn), None) for fn in fns
                        if MP.omw_runtime_path(os.path.join(base, fn))]
        for p, h in gen:
            if not os.path.isfile(p) or _nk(p) in originals:
                continue
            if h and _sha256(p) != h:
                _warn(f"kept {p}: it changed since omw2mwse wrote it")
                kept = True
            elif MP.omw_runtime_path(p):
                cstate["defer"].append((p, h, mod_dir))
            else:
                os.remove(p)
                cstate["removed"] += 1
                touched.append(os.path.dirname(p))
        man = os.path.join(mod_dir, *(op["tree"].split("/") + [MP.OMW_MANIFEST]))
        if not kept and os.path.isfile(man):
            os.remove(man)
            touched.append(os.path.dirname(man))
    except OSError as e:
        print(f"  could not undo the conversion of {name}: {e}", file=sys.stderr)
        return False
    for d in set(touched):                            # (3) emptied folders, inside the mod only
        _prune_empty(d, mod_dir)
    cstate["mods"] += 1
    return True


def converted_elsewhere(staging, names, data_files):
    """True when a converted mod (its MWSE\\mods folder holds omw2mwse output) is left in any mod folder of
    staging, or in Data Files, other than a deployed copy of one of `names` (the mods just undone)."""
    def scan(mods_dir, skip_names):
        for base, dirs, _fs in os.walk(mods_dir):
            keep = []
            for d in dirs:
                if MP.omw_generated_dir(os.path.join(base, d)):
                    if d not in skip_names:
                        return True
                else:
                    keep.append(d)
            dirs[:] = keep
        return False
    if staging and os.path.isdir(staging):
        for m in sorted(os.listdir(staging)):
            md = os.path.join(staging, m)
            if os.path.isdir(md) and m.lower() != "off":
                mods = os.path.join(md, existing(md, "MWSE"), "mods")
                if os.path.isdir(mods) and scan(mods, ()):
                    return True
    dm = os.path.join(data_files, "MWSE", "mods")
    return os.path.isdir(dm) and scan(dm, names)


def finish_conversions(cstate):
    """--undo, after every conversion of the run: the shared runtime (MWSE\\lib\\omwcompat*) goes from the mods
    it was deferred in, unless a converted mod is left in staging or Data Files."""
    if not cstate["defer"]:
        return
    if converted_elsewhere(cstate["staging"], cstate["names"], os.path.join(HERE, "Data Files")):
        return
    for p, h, mod_dir in cstate["defer"]:
        try:
            if not os.path.isfile(p):
                continue
            if h and _sha256(p) != h:
                _warn(f"kept {p}: it changed since omw2mwse wrote it")
                continue
            os.remove(p)
            cstate["removed"] += 1
            _prune_empty(os.path.dirname(p), mod_dir)
        except OSError as e:
            print(f"  could not remove {p}: {e}", file=sys.stderr)


# ---------------------------------------------------------------- asset repairs: the originals, for --undo
# Before a mod's asset repairs (and the tidy section of its bug report) are made, every file they can change is
# copied to <backups folder>\tidy\<run>\assets\<mod folder>\<path in the mod> and journaled with its hash; after
# them the mod folder is compared with how it was: each changed file gets its new hash, each new file (repaired
# copies under new names, the mod's own Off\ copies, a new bug report) is listed as made by the run. --undo puts
# each original back at its own path (in place, so a Vortex hard link stays one; file times as they were) and
# removes the files the run made. It never "reverses" a repair: the kept original is the file as it was.
ASSET_BACKUP_DIR = "assets"
ASSET_OPS = ("asset", "asset_after", "asset_created", "asset_mkdir", "asset_unbacked", "asset_lp_record")


def _is_asset_op(op):
    return any(k in op for k in ASSET_OPS)


def _xp(p):
    """p with Windows' \\\\?\\ prefix when it is long (so it can still be opened); unchanged elsewhere."""
    if os.name != "nt" or len(p) < 240 or p.startswith("\\\\?\\"):
        return p
    return "\\\\?\\" + os.path.abspath(p)


def _unxp(p):
    return p[4:] if p.startswith("\\\\?\\") else p


def _nk(p):
    return os.path.normcase(os.path.abspath(_unxp(p)))


def _sha256(path):
    h = hashlib.sha256()
    with open(_xp(path), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _tree_state(root):
    """({key: (path, size, mtime_ns)} of every file under root, {key: path} of its folders)."""
    files, dirs = {}, {}
    for base, ds, fns in os.walk(_xp(root)):
        base = _unxp(base)
        for d in ds:
            p = os.path.join(base, d)
            dirs[_nk(p)] = p
        for fn in fns:
            p = os.path.join(base, fn)
            try:
                st = os.stat(_xp(p))
            except OSError:
                continue
            files[_nk(p)] = (p, st.st_size, st.st_mtime_ns)
    return files, dirs


def _lp_module():
    import mwdialog_longpaths
    return mwdialog_longpaths


def _repair_candidates(root, fixes, lp_plan, lpm=None):
    """Every existing file one mod's repairs can change or replace: each repaired file and the files beside it
    with the same name (a .dds becoming .tga, a .wav becoming .mp3...), an ASCII rename's new path, the mod's
    plugins (renames and short paths are written into them), its bug reports, the repair notes beside its
    Off\\ originals, and for short paths the moved files and the models naming them."""
    root = os.path.abspath(root)
    out = set()

    def add(p):
        p = os.path.abspath(_unxp(p))
        if os.path.isfile(_xp(p)):
            out.add(p)

    def with_siblings(p):
        add(p)
        d, b = os.path.split(os.path.abspath(_unxp(p)))
        stem = os.path.splitext(b)[0].lower()
        try:
            names = os.listdir(_xp(d))
        except OSError:
            return
        for n in names:
            if os.path.splitext(n)[0].lower() == stem:
                add(os.path.join(d, n))

    for kind, full, _rel, job in fixes:
        with_siblings(full)
        if kind == "ascii" and isinstance(job, str):
            with_siblings(os.path.join(root, job))
    try:
        names = os.listdir(_xp(root))
    except OSError:
        names = []
    for e in names:
        if os.path.splitext(e)[1].lower() in (".esp", ".esm", ".omwaddon"):
            add(os.path.join(root, e))
        elif e.lower() == "bugreports":
            for base, _ds, fns in os.walk(_xp(os.path.join(root, e))):
                for fn in fns:
                    add(os.path.join(_unxp(base), fn))
        elif e.lower() == "off":
            for base, _ds, fns in os.walk(_xp(os.path.join(root, e))):
                for fn in fns:
                    if fn.lower().endswith((".repaired.sha256", DUMMY_MARK)):
                        add(os.path.join(_unxp(base), fn))
    if lp_plan:
        fs = (lambda r: r.replace("\\", os.sep).replace("/", os.sep))
        pairs = {}
        for lp in lp_plan:
            for rel in [lp["orig"], lp["short"]] + [x for t in (lp.get("twins") or []) for x in t]:
                add(os.path.join(root, fs(rel)))
            pairs[lp["orig"].replace("/", "\\").strip().lower().lstrip("\\")] = lp["short"]
        mroot = next((os.path.join(root, d) for d in names if d.lower() == "meshes"), None)
        for base, _ds, fns in (os.walk(_xp(mroot)) if mroot else ()):
            for fn in fns:
                if not fn.lower().endswith(".nif"):
                    continue
                nf = os.path.join(_unxp(base), fn)
                try:
                    with open(_xp(nf), "rb") as f:
                        data = f.read()
                    hit = lpm is None or bool(lpm.rewrite_nif_textures(data, pairs)[0])
                except Exception:                     # can't tell: keep it to be safe
                    hit = True
                if hit:
                    add(nf)
    return out


class AssetJournal:
    """Keeps, for --undo, the original of every file one mod's asset repairs change (see above). Inactive (does
    nothing) without a run folder for the originals (args._audit, set by --apply)."""

    def __init__(self, args, staging=None):
        self.audit = getattr(args, "_audit", None) if args is not None else None
        self.head = {"run": time.strftime("%Y-%m-%d %H:%M:%S"), "what": "assets",
                     "staging": staging or getattr(args, "staging", None)}
        self.head.update(getattr(args, "_journal_extra", None) or {})
        self.started = False

    def _write(self, recs):
        if not recs:
            return
        if not self.started:
            recs = [self.head] + recs
            self.started = True
        os.makedirs(os.path.dirname(os.path.abspath(JOURNAL)), exist_ok=True)
        with open(JOURNAL, "a", encoding="utf-8") as j:
            for r in recs:
                j.write(json.dumps(r) + "\n")
            j.flush()
            os.fsync(j.fileno())

    def begin(self, folder, root, candidates):
        """Copy each candidate to the run's originals folder (read back and compared) and journal it, before
        anything is changed. Raises OSError when an original can't be kept: then the mod must not be repaired."""
        if not self.audit:
            return None
        root = os.path.abspath(root)
        files, dirs = _tree_state(root)
        bdir = os.path.join(self.audit, ASSET_BACKUP_DIR, folder)
        recs, kept = [], {}
        for p in sorted(candidates):
            rel = os.path.relpath(p, root)
            if rel == os.pardir or rel.startswith(os.pardir + os.sep):
                rel = os.path.join("_outside", os.path.splitdrive(p)[1].lstrip("\\/"))
            bak = os.path.join(bdir, rel)
            k = 2
            while os.path.exists(_xp(bak)):           # the queue repairs a mod a second time: keep both
                bak = os.path.join(bdir + f".{k}", rel)
                k += 1
            os.makedirs(_xp(os.path.dirname(bak)), exist_ok=True)
            shutil.copy2(_xp(p), _xp(bak))
            h = _sha256(p)
            if _sha256(bak) != h:
                raise OSError(f"the copy of {p} reads back different")
            recs.append({"asset": p, "backup": bak, "before": h, "mtime_ns": os.stat(_xp(p)).st_mtime_ns,
                         "mod": folder})
            kept[_nk(p)] = (p, h, bak)
        self._write(recs)
        return {"folder": folder, "root": root, "files": files, "dirs": dirs, "kept": kept}

    def end(self, tok, lp_plan=()):
        """Journal what the repairs did to the mod folder: new hashes, new files and folders."""
        if tok is None:
            return
        files, dirs = _tree_state(tok["root"])
        recs = [{"asset_mkdir": p} for k, p in sorted(dirs.items(), key=lambda kv: len(kv[0]))
                if k not in tok["dirs"]]
        for k, (p, _size, _mt) in sorted(files.items()):
            if k in tok["files"] or k in tok["kept"]:
                continue
            try:
                recs.append({"asset_created": p, "sha": _sha256(p)})
            except OSError as e:
                recs.append({"asset_created": p, "sha": None})
                print(f"  (could not read {p}: {e})", file=sys.stderr)
        for k, (p, h, bak) in sorted(tok["kept"].items()):
            if k not in files:
                recs.append({"asset_after": p, "after": None})
                continue
            try:
                h2 = _sha256(p)
            except OSError:
                h2 = "?"
            if h2 == h:
                recs.append({"asset_after": p, "unchanged": True})
            else:
                recs.append({"asset_after": p, "after": h2})
        for k, (p, size, mt) in sorted(tok["files"].items()):
            if k in tok["kept"]:
                continue
            now = files.get(k)
            if now is None or now[1:] != (size, mt):
                print(f"  WARNING: {p} was changed by a repair without its original kept; --undo can't put it back",
                      file=sys.stderr)
                recs.append({"asset_unbacked": p})
        mod = os.path.basename(os.path.normpath(tok["root"]))
        recs += [{"asset_lp_record": lp["orig"], "mod": mod} for lp in (lp_plan or ())]
        self._write(recs)
        self._drop_unchanged(tok, recs)

    @staticmethod
    def _drop_unchanged(tok, recs):
        """Originals of files the repairs left as they were are not needed: removed again (never the journal)."""
        same = {_nk(r["asset_after"]) for r in recs if r.get("unchanged")}
        for k in same:
            bak = tok["kept"][k][2]
            try:
                os.remove(_xp(bak))
                d = os.path.dirname(bak)
                while os.path.isdir(_xp(d)) and not os.listdir(_xp(d)):
                    os.rmdir(_xp(d))
                    d = os.path.dirname(d)
            except OSError:
                pass


def _asset_undo_plan(ops):
    """{key: {"path", "orig": None (no file there before the run) or (sha, backup, mtime_ns), "state": the hash the
    run left (None: no file; "?": unknown, the run stopped), "touched"}} from one --apply's asset ops, in journal
    order. A file journaled twice (the queue repairs a mod again) keeps its first original."""
    plan = {}
    for op in ops:
        if "asset" in op:
            k = _nk(op["asset"])
            e = plan.get(k)
            if e is None:
                e = plan[k] = {"path": op["asset"], "orig": (op["before"], op["backup"], op.get("mtime_ns")),
                               "touched": False}
            e["state"], e["pending"] = "?", op["before"]          # until its after line says what happened
        elif "asset_after" in op:
            e = plan.get(_nk(op["asset_after"]))
            if e is None:
                continue
            if op.get("unchanged"):
                e["state"] = e.get("pending")
            else:
                e["state"], e["touched"] = op.get("after"), True
        elif "asset_created" in op:
            k = _nk(op["asset_created"])
            e = plan.setdefault(k, {"path": op["asset_created"], "orig": None})
            e["state"], e["touched"] = op.get("sha"), True
    for e in plan.values():
        if e["state"] == "?":
            e["touched"] = True                       # the run stopped before saying: put the original back
    return plan


def _current(path):
    """The file's hash, or None when there is no file."""
    return _sha256(path) if os.path.isfile(_xp(path)) else None


def _asset_preflight(plan, force):
    """Why the asset originals can't all be put back, or []. Nothing is changed."""
    out = []
    for e in plan.values():
        if not e["touched"]:
            continue
        p = e["path"]
        try:
            cur = _current(p)
        except OSError as ex:
            out.append(f"{p}: can't be read ({ex})")
            continue
        if e["orig"] is None:                         # made by the run: removed, unless changed since
            if cur is not None and e["state"] not in (cur, "?", None) and not force:
                out.append(f"{p}: made by the repairs, but changed since (--undo --force removes it anyway)")
            continue
        before, bak, _mt = e["orig"]
        if cur == before:
            continue                                  # as it was already
        if e["state"] != "?" and cur != e["state"] and not force:
            out.append(f"{p}: changed since it was repaired (--undo --force puts the original back anyway)")
            continue
        try:
            ok = _sha256(bak) == before
        except OSError:
            out.append(f"{p}: its original is missing (was kept at {bak})")
            continue
        if not ok:
            out.append(f"{p}: its kept original ({bak}) has a different hash than the file had")
    return out


def _put_back(path, bak, before, mtime_ns):
    with open(_xp(bak), "rb") as f:
        data = f.read()
    if hashlib.sha256(data).hexdigest() != before:
        raise OSError(f"its kept original ({bak}) has a different hash than the file had")
    if os.path.isfile(_xp(path)):
        with open(_xp(path), "r+b") as f:             # in place: a Vortex hard link stays one
            f.seek(0)
            f.write(data)
            f.truncate()
            f.flush()
            os.fsync(f.fileno())
    else:
        os.makedirs(_xp(os.path.dirname(path)), exist_ok=True)
        with open(_xp(path), "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    if _sha256(path) != before:
        raise OSError("it reads back different after writing")
    if mtime_ns:                                      # a plugin's date is its place in the load order
        os.utime(_xp(path), ns=(mtime_ns, mtime_ns))


def _asset_undo(plan, ops, force):
    """Put the asset originals back (after _asset_preflight): the files the run made go first, then each original
    goes back to its own path, then the folders the run made (if empty) and its short-path records. Returns
    (originals put back, files removed, [paths that failed])."""
    restored = removed = 0
    failed = []
    for e in plan.values():
        if not e["touched"] or e["orig"] is not None:
            continue
        p = e["path"]
        try:
            cur = _current(p)
            if cur is None:
                continue
            if e["state"] not in (cur, "?", None) and not force:
                raise OSError("changed since the repairs made it")
            os.remove(_xp(p))
            removed += 1
        except OSError as ex:
            print(f"  could not remove {p}: {ex}", file=sys.stderr)
            failed.append(p)
    for e in plan.values():
        if not e["touched"] or e["orig"] is None:
            continue
        p = e["path"]
        before, bak, mt = e["orig"]
        try:
            if _current(p) == before:
                continue
            _put_back(p, bak, before, mt)
            restored += 1
        except OSError as ex:
            print(f"  could not put back {p}: {ex}", file=sys.stderr)
            failed.append(p)
    for d in sorted({op["asset_mkdir"] for op in ops if "asset_mkdir" in op}, key=len, reverse=True):
        try:
            if os.path.isdir(_xp(d)) and not os.listdir(_xp(d)):
                os.rmdir(_xp(d))
        except OSError:
            pass
    for op in ops:
        if "asset_unbacked" in op:
            print(f"  not put back (its original was not kept): {op['asset_unbacked']}", file=sys.stderr)
    lp = [op for op in ops if "asset_lp_record" in op]
    if lp:
        try:
            lpm = _lp_module()
            rec = lpm.Record(HERE)
            drop = {(lpm.norm(op["asset_lp_record"]), (op.get("mod") or "").lower()) for op in lp}
            keep = [x for x in rec.moves if not (x.get("by") == "tidy"
                                                  and (lpm.norm(x["orig"]), (x.get("mod") or "").lower()) in drop)]
            if len(keep) != len(rec.moves):
                rec.moves = keep
                rec.save()
        except Exception as ex:                       # the files are back; only the record is stale
            print(f"  (mwdialog_longpaths.json not updated: {ex}; mwdialog_check --longpaths-undo may list moves "
                  f"that are undone already)", file=sys.stderr)
    return restored, removed, failed


def _luafix():
    """mwdialog_luafix.py from this folder, or None."""
    try:
        import mwdialog_luafix
        return mwdialog_luafix
    except Exception as e:
        print(f"(mwdialog_luafix.py could not be loaded: {e})", file=sys.stderr)
        return None


CORE_KEY = "MWSE core (Data Files\\MWSE\\core)"   # lua_check()'s entry for MWSE's own core files


def lua_check(args):
    """mwdialog_luafix on each mod's MWSE Lua files (nothing written): {"reps", "merged", "body" (the plan's Lua
    section), "n_ok", "checker"}, or None when mwdialog_luafix.py is missing."""
    lf = _luafix()
    if lf is None:
        return None
    game_dir = HERE
    data_dir = os.path.join(game_dir, "Data Files")
    mods = sorted(d for d in os.listdir(args.staging) if os.path.isdir(os.path.join(args.staging, d))
                  and d.lower() != "off")
    if args.only:
        mods = [d for d in mods if any(fnmatch.fnmatch(d.lower(), pat.lower()) for pat in args.only)]
    pats = blacklist(create=bool(args.apply)) + (args.skip or [])
    cfg = lf.load_config(game_dir, data_dir)
    checker = lf.find_checker(getattr(args, "luajit", None), game_dir)
    print("\n" + "=" * 70 + "\nLUA CHECK (each mod's MWSE Lua files)\n" + "=" * 70)
    print(f"  syntax check: {checker.name if checker else 'NONE (no LuaJIT/luac found: nothing is patched; ' + MP.describe_luajit_search(game_dir) + ')'}")
    out, total, reps = [], {}, []
    for d in mods:
        if any(fnmatch.fnmatch(d.lower(), pt.lower()) for pt in pats):
            continue
        root = os.path.join(args.staging, d)
        if not os.path.isdir(os.path.join(root, "MWSE")) and not any(
                e.lower() == "mwse" for e in os.listdir(root)):
            continue
        try:
            rep = lf.check_paths([root], cfg, False, checker, getattr(args, "lua_level", "high"), data_dir,
                                 True, False, game_dir, log_scope=getattr(args, "lua_log", None))
        except Exception as e:                        # one odd mod never stops the rest
            print(f"  {d}: Lua check failed ({e})")
            continue
        lines, counts = lf.format_report(rep, indent="    ")
        for k, v in counts.items():
            total[k] = total.get(k, 0) + v
        if lines:
            out.append(f"\n{d}")
            out += lines
        reps.append((d, rep))
    # MWSE's own core files a Known Bugs rule names (KB3, KB4: the MCM's ExclusionsPage). MWSE's updater puts
    # them straight into Data Files, so they are checked there and patched in place, unless a staged mod ships
    # MWSE itself (then that mod's copy was checked above and Data Files holds a link to it).
    staged_core = {os.path.relpath(p, os.path.join(args.staging, d, "MWSE")).replace("\\", "/").lower()
                   for d in mods for p in lf.known_core_files(os.path.join(args.staging, d, "MWSE"))}
    core = [p for p in lf.known_core_files(os.path.join(data_dir, "MWSE"))
            if os.path.relpath(p, os.path.join(data_dir, "MWSE")).replace("\\", "/").lower() not in staged_core]
    if core:
        try:
            rep = lf.check_paths(core, cfg, False, checker, getattr(args, "lua_level", "high"), data_dir,
                                 True, False, game_dir, log_scope=getattr(args, "lua_log", None))
            lines, counts = lf.format_report(rep, indent="    ")
            for k, v in counts.items():
                total[k] = total.get(k, 0) + v
            if lines:
                out.append("\n" + CORE_KEY)
                out += lines
            reps.append((CORE_KEY, rep))
        except Exception as e:
            print(f"  MWSE core: Lua check failed ({e})")
    n_ok = sum(1 for _d, r in reps for e in r.files.values() if e.get("patch") and e["patch"]["ok"])
    print("\n".join(out[:300]))
    if len(out) > 300:
        print(f"    ... ({len(out) - 300} more lines in {PLAN})")
    print("\n  Lua findings by rule:")
    print("\n".join(lf.summary_lines(total, "    ")) or "    none")
    try:
        import mwdialog_assets as ah
        ah.shared_cache(game_dir).flush()
    except Exception:
        pass
    merged = lf.Report()
    for _d, rep in reps:
        merged.files.update(rep.files)
    print(f"  {n_ok} Lua file(s) to patch" + ("" if args.apply else " (run with --apply)"))
    return {"reps": reps, "merged": merged, "body": "\n".join(out + lf.summary_lines(total)), "n_ok": n_ok,
            "checker": checker, "done": [], "lf": lf}


def lua_pending(lres):
    """Plan lines (per mod) of the Lua patches not written yet."""
    if not lres:
        return []
    out = []
    for d, rep in lres["reps"]:
        ls = lres["lf"].pending_lines(rep, lres["done"], "    ")
        if ls:
            out += [f"\n{d}"] + ls
    return out


def lua_apply(args, lres):
    """Write the verified Lua patches lua_check() found (the reviewed ones), in place; originals in
    <backups folder>\\luafix, journaled here so --undo puts them back. A file changed since the check is refused."""
    if not lres or not lres["n_ok"]:
        return
    if lres["checker"] is None:
        print("  not patching Lua: no syntax checker (LuaJIT / luac) found")
        return
    if not args.yes and input(f"\nPatch {lres['n_ok']} Lua file(s) in place? [y/N] ").strip().lower() not in \
            ("y", "yes"):
        print("  Lua files not changed.")
        return
    lf = lres["lf"]
    written, refused = lf.apply_report(lres["merged"], journal=JOURNAL, head_extra=dict(
        {"staging": args.staging, "lua": True}, **getattr(args, "_journal_extra", {})), done=lres["done"])
    for p, why in refused:
        print(f"    not patched: {os.path.relpath(p, args.staging)}: {why}")
    import mwdialog_assets as ah
    refused_map = dict(refused)
    for d, rep in lres["reps"]:
        lines = lf.known_bug_report_lines(rep, lres["done"], refused_map)
        if not lines:
            continue
        if d == CORE_KEY:                             # MWSE's own files: no mod folder to hold a bug report
            print("\n".join("    " + x for x in lines))
            continue
        root = os.path.join(args.staging, d)
        head = [f"Bug report for {mod_name(d)}", f"Mod: {mod_name(d)}",
                f"Generated {time.strftime('%Y-%m-%d %H:%M')} by vortex_tidy.",
                "Paths are relative to the mod's folder (Data Files)."]
        ah.update_bug_report(os.path.join(root, "bugreports", mod_name(d) + ".bugreport.txt"),
                             "vortex_tidy (Lua known bugs)", head, lines)
    print(f"  patched {written} Lua file(s) (journal {JOURNAL}; --undo puts them back)")


def _tool_modules():
    """mwdialog_check.py and mwdialog_assets.py from this folder (the asset checks live there)."""
    import importlib.util
    here = os.path.dirname(os.path.abspath(__file__))
    mods = []
    for name in ("mwdialog_check", "mwdialog_assets"):
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "__file__", None):
            mods.append(mod)                          # loaded already: one copy (one set of caches)
            continue
        path = os.path.join(here, name + ".py")
        if not os.path.exists(path):
            return None, None
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod                        # before running it: the other module imports it by name
        try:
            spec.loader.exec_module(mod)
        except BaseException:
            sys.modules.pop(name, None)
            raise
        mods.append(mod)
    return mods[0], mods[1]


def asset_action_lines(ent):
    """The plan's action lines for one mod's asset repairs (what --apply does to its files)."""
    out = []
    for kind, _full, rel, job in ent["fixes"]:
        j = json.dumps(job, sort_keys=True) if isinstance(job, (dict, list)) else ("" if job is None else str(job))
        out.append(f"repair {kind} {rel}" + (f" {j}" if j else ""))
    for lp in ent["lp_plan"]:
        tw = len(lp.get("twins") or [])
        out.append(f"shorten {lp['orig']} -> {lp['short']}" + (f" (+{tw} twin(s))" if tw else ""))
    return out


# ---------------------------------------------------------------- broken assets: the original to Off\, a dummy in place
# A file the asset check finds broken (empty, not the format its name says, truncated, a model the game crashes
# on, an MP3 with no audio) can't be repaired: the original goes to <mod>\Off\broken\<plugin>\<path> (where the
# asset tools already keep broken originals) and a small valid file of the same format takes its place, so the
# plugins and models naming it still find one. Beside the kept original, <original>.tidy-dummy records the
# dummy's path and SHA-256: a later run knows the file at that path is tidy's dummy (while it is unchanged) and
# neither reports it nor replaces it again. Like every repair, it is journaled: --undo puts the original back and
# removes the dummy's Off copy and its mark.
DUMMY_MARK = ".tidy-dummy"


def _rk(rel):
    return rel.replace("/", "\\").strip("\\").lower()


def _placeholder_bgra(rel):
    """The colour mwdialog_media's placeholder textures use: a flat normal map for *_n / *_nm..., black for
    glow, reflection and specular maps (so they add nothing), plain grey otherwise."""
    stem = os.path.splitext(os.path.basename(rel.replace("\\", "/")).lower())[0]
    if stem.endswith(("_nm", "_n", "_normal", "_nrm")):
        return (255, 128, 128, 255)
    if stem.endswith(("_glow", "_g", "_ref", "_spec", "_s", "_em", "_lum")):
        return (0, 0, 0, 255)
    return (128, 128, 128, 255)


def dummy_tga(rel):
    """A 4x4 uncompressed 24-bit TGA in the placeholder colour."""
    b, g, r, _a = _placeholder_bgra(rel)
    head = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, 4, 4, 24, 0)
    return head + bytes((b, g, r)) * 16


def dummy_bmp(rel):
    """A 4x4 24-bit BMP in the placeholder colour (rows of 12 bytes: no padding needed)."""
    b, g, r, _a = _placeholder_bgra(rel)
    px = bytes((b, g, r)) * 16
    return (struct.pack("<2sIHHI", b"BM", 54 + len(px), 0, 0, 54)
            + struct.pack("<IiiHHIIiiII", 40, 4, 4, 1, 24, 0, len(px), 2835, 2835, 0, 0) + px)


def dummy_png(rel):
    """A 4x4 8-bit RGB PNG in the placeholder colour."""
    import zlib
    b, g, r, _a = _placeholder_bgra(rel)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    rows = b"".join(b"\0" + bytes((r, g, b)) * 4 for _ in range(4))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def dummy_dds(rel):
    """A 4x4 uncompressed DDS in the placeholder colour (as mwdialog_media's placeholder_dds)."""
    w = h = 4
    head = struct.pack("<4sIIIIIII44sIIIIIIIIIIIII", b"DDS ", 124, 0x100F, h, w, w * 4, 0, 0, bytes(44),
                       32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000, 0x1000, 0, 0, 0, 0)
    return head + bytes(_placeholder_bgra(rel)) * (w * h)


def dummy_icon():
    """A 32x32 inventory icon (as mwdialog_media's placeholder_icon): a grey square with a red "!", so a missing
    icon is visible."""
    w = h = 32
    head = struct.pack("<4sIIIIIII44sIIIIIIIIIIIII", b"DDS ", 124, 0x100F, h, w, w * 4, 0, 0, bytes(44),
                       32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000, 0x1000, 0, 0, 0, 0)
    px = bytearray()
    for y in range(h):
        for x in range(w):
            edge = x in (0, w - 1) or y in (0, h - 1)
            bar = 13 <= x <= 18 and 4 <= y <= 20 and not (y >= 17 and x in (13, 18))
            dot = 13 <= x <= 18 and 23 <= y <= 27
            px += bytes((40, 40, 210, 255)) if bar or dot else \
                bytes((60, 60, 60, 255)) if edge else bytes((110, 110, 110, 255))
    return head + bytes(px)


def dummy_jpg(rel):
    """An 8x8 greyscale baseline JPEG, flat, in the placeholder colour's brightness: one block whose only
    coefficient is its DC term (quantisation 1), with one-code Huffman tables."""
    b, g, r, _a = _placeholder_bgra(rel)
    dc = 8 * (int(round(0.299 * r + 0.587 * g + 0.114 * b)) - 128)    # a flat block's DC term is 8x its level
    cat = abs(dc).bit_length()
    bits = "0"                                                         # the DC table's one code: category `cat`
    if cat:
        bits += format(dc if dc > 0 else dc + (1 << cat) - 1, f"0{cat}b")
    bits += "0"                                                        # the AC table's one code: end of block
    bits += "1" * (-len(bits) % 8)
    scan = bytearray()
    for i in range(0, len(bits), 8):
        scan.append(int(bits[i:i + 8], 2))
        if scan[-1] == 0xFF:
            scan.append(0)                                             # byte stuffing

    def seg(marker, body):
        return struct.pack(">BBH", 0xFF, marker, len(body) + 2) + body

    def dht(cls, sym):
        return seg(0xC4, bytes((cls << 4,)) + bytes((1,)) + bytes(15) + bytes((sym,)))
    return (b"\xff\xd8" + seg(0xDB, b"\0" + b"\1" * 64)
            + seg(0xC0, struct.pack(">BHHB", 8, 8, 8, 1) + b"\x01\x11\x00")
            + dht(0, cat) + dht(1, 0)
            + seg(0xDA, b"\x01\x01\x00\x00\x3f\x00") + bytes(scan) + b"\xff\xd9")


def dummy_wav():
    """0.2 s of silence: 22,050 Hz mono 16-bit PCM."""
    rate, n = 22050, 4410
    data = bytes(2 * n)
    return (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + b"data" + struct.pack("<I", len(data)) + data)


def dummy_mp3():
    """Silence: 8 MPEG-1 Layer III frames (128 kbit/s, 44.1 kHz, 417 bytes each) whose side information is all
    zero - no audio data, so every frame decodes as silence."""
    return (b"\xff\xfb\x90\x64" + bytes(413)) * 8


NIF_HEAD = b"NetImmerse File Format, Version 4.0.0.2\n"


def dummy_nif():
    """The smallest model the game loads: a NIF 4.0.0.2 with one empty NiNode (no name links, identity transform,
    no properties, children or effects) as its root. It draws nothing - the asset tools treat a lone empty node
    as made so on purpose."""
    def s(t):
        return struct.pack("<I", len(t)) + t
    node = (s(b"NiNode") + s(b"vortex_tidy dummy") + struct.pack("<ii", -1, -1) + struct.pack("<H", 0)
            + struct.pack("<3f", 0, 0, 0) + struct.pack("<9f", 1, 0, 0, 0, 1, 0, 0, 0, 1) + struct.pack("<f", 1)
            + struct.pack("<3f", 0, 0, 0) + struct.pack("<IIII", 0, 0, 0, 0))   # properties, bbox, children, effects
    return NIF_HEAD + struct.pack("<II", 0x04000002, 1) + node + struct.pack("<Ii", 1, 0)


GENERATED = {".dds": "a 4x4 placeholder texture", ".tga": "a 4x4 placeholder TGA", ".bmp": "a 4x4 placeholder BMP",
             ".png": "a 4x4 placeholder PNG", ".jpg": "an 8x8 placeholder JPEG", ".jpeg": "an 8x8 placeholder JPEG",
             ".wav": "a silent WAV", ".mp3": "a silent MP3", ".nif": "an empty, invisible model (one empty node)"}

# Models: by default a missing or broken mesh gets the game's Dwemer coin (the stand-in mwdialog_check --fix uses,
# read out of the core Morrowind.bsa), so the gap is easy to spot in the game without its giant error marker.
# --no-coins (NO_COINS) uses the empty, invisible model made in code instead; so does a game without the coin in
# its Morrowind.bsa, and the plan says so. The plan line says which ({"dummy": "coin"} or "empty"), so --apply
# refuses a plan made in the other mode. Either kind is marked the same way (.tidy-dummy, by its SHA-256), so a
# later run in the other mode leaves the dummies already there alone.
NO_COINS = False
COIN_NIF = "meshes\\m\\misc_dwrv_coin00.nif"
COIN_WHAT = "the game's Dwemer coin (misc_dwrv_coin00.nif from Morrowind.bsa)"
NO_COIN_NOTE = "the Dwemer coin isn't in Morrowind.bsa here"


# Core game files tidy looks for by name and expects as shipped: Morrowind.bsa itself, the coin in it and the
# .kf stand-in in it. One that is missing or changed is collected here (CORE_MISSING: key -> [what is wrong,
# [what tidy did instead]]) and shown once per run as a warning that the core files were altered (core_warning,
# printed at the end of the run and written at the end of the plan file). It never stops anything. Tribunal.bsa
# and Bloodmoon.bsa are optional sources (a copy may come from them when there): never warned about. Without a
# Data Files folder at all tidy is simply not in a game folder: not warned about either (assets_check notes it).
CORE_MISSING = {}
CORE_WARN_HEAD = "WARNING: THE CORE MORROWIND GAME FILES HAVE BEEN ALTERED"


def _core_missing(key, what, instead):
    if os.path.isdir(_data_dir()):
        got = CORE_MISSING.setdefault(key, [what, []])
        if instead not in got[1]:
            got[1].append(instead)


def core_warning():
    """The core-files warning (lines, no trailing newline), or [] when nothing core was found missing."""
    if not CORE_MISSING:
        return []
    bar = "!" * 78
    out = [bar, CORE_WARN_HEAD, ""]
    for what, instead in CORE_MISSING.values():
        out += [f"  - {what}", f"    ({'; '.join(instead)})"]
    out += ["",
            "  The game's own archives must stay exactly as shipped: mods override them, they never replace",
            "  them. A modified, replaced or missing core file can break the game and every mod built on it,",
            "  in ways no tool can detect. vortex_tidy carried on (nothing was blocked), but you should restore",
            "  the original files now: in Steam, right-click Morrowind > Properties > Installed Files > Verify",
            "  integrity of game files (GOG Galaxy: Manage installation > Verify / Repair), or reinstall the",
            "  game's original Morrowind.bsa. Then run vortex_tidy again.",
            bar]
    return out


def print_core_warning():
    lines = core_warning()
    if lines:
        print("\n" + "\n".join(lines))


def coin_nif():
    """The Dwemer coin model out of the core Morrowind.bsa (nothing written anywhere), or None (and the core
    files warning: the coin is a known core file)."""
    import mwdialog_bsa as BSA
    bsa = os.path.join(_data_dir(), "Morrowind.bsa")
    instead = "broken models get the empty, invisible model instead of the Dwemer coin"
    if not os.path.isfile(bsa):
        _core_missing("Morrowind.bsa", "Morrowind.bsa is missing from Data Files", instead)
        return None
    try:
        entry = BSA.bsa_index(bsa).get(COIN_NIF)
        if entry is None:
            _core_missing(COIN_NIF, f"{COIN_NIF} is not in Morrowind.bsa", instead)
            return None
        with open(bsa, "rb") as f:
            f.seek(entry[0])
            b = f.read(entry[1])
    except (OSError, ValueError, struct.error, BSA.FormatError) as e:
        _core_missing("Morrowind.bsa", f"Morrowind.bsa can't be read ({e})", instead)
        return None
    if len(b) == entry[1] and b.startswith(NIF_HEAD):
        return b
    _core_missing(COIN_NIF, f"{COIN_NIF} in Morrowind.bsa is not a Morrowind model any more", instead)
    return None


def nif_dummy(kind=None):
    """(bytes, what, kind "coin"/"empty") of a model dummy: kind None follows NO_COINS (the coin, else - or
    without one in Morrowind.bsa - the empty model); "coin" is the coin or (None, why, "coin")."""
    want = kind or ("empty" if NO_COINS else "coin")
    if want == "coin":
        b = coin_nif()
        if b is not None:
            return b, COIN_WHAT, "coin"
        if kind == "coin":
            return None, f"{NO_COIN_NOTE} any more", "coin"
        return dummy_nif(), f"{GENERATED['.nif']}, as {NO_COIN_NOTE}", "empty"
    return dummy_nif(), GENERATED[".nif"], "empty"


def generate_dummy(rel):
    """(bytes, what) of a dummy made in code for rel's type, or None."""
    ext = os.path.splitext(rel)[1].lower()
    if ext == ".dds" and _rk(rel).startswith("icons\\"):
        return dummy_icon(), "a 32x32 placeholder icon"
    make = {".dds": dummy_dds, ".tga": dummy_tga, ".bmp": dummy_bmp, ".png": dummy_png, ".jpg": dummy_jpg,
            ".jpeg": dummy_jpg, ".wav": lambda r: dummy_wav(), ".mp3": lambda r: dummy_mp3(),
            ".nif": lambda r: dummy_nif()}.get(ext)
    return (make(rel), GENERATED[ext]) if make else None


# A type no dummy can be made for in code (.kf animations, .bik videos, .fnt/.tex fonts...) gets a copy of a core
# game file of that type: from Morrowind.bsa, Tribunal.bsa, Bloodmoon.bsa, or core loose files in Data Files (the
# Video and Fonts folders; a file Vortex deployed, a hard link, never counts). First choice: the core file at the
# same path (the one the mod replaces); then one nothing uses (its name appears in none of the active plugins nor
# in Morrowind.ini); for a .kf then the small animation the asset tools always used (xin_dagoth_bridge00.kf);
# then any core file of the type. Each type's pick is cached in vortex_tidy_dummy_sources.json until the plugins,
# Morrowind.ini or the archives change. Nothing is copied out ahead of time and no dummy file is shipped.
CORE_BSAS = ("Morrowind.bsa", "Tribunal.bsa", "Bloodmoon.bsa")
CORE_LOOSE_DIRS = ("video", "fonts")
KF_FALLBACK = "meshes\\i\\xin_dagoth_bridge00.kf"
DUMMY_SOURCES = "vortex_tidy_dummy_sources.json"


def _data_dir():
    return os.path.join(HERE, "Data Files")


def _ini_plugins(game_dir):
    """The plugins Morrowind.ini loads ([Game Files] GameFileN=), or None without an ini."""
    try:
        with open(os.path.join(game_dir, "Morrowind.ini"), encoding="cp1252", errors="replace") as f:
            text = f.read()
    except OSError:
        return None
    out, on = [], False
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("["):
            on = s.lower() == "[game files]"
        elif on and s.lower().startswith("gamefile") and "=" in s:
            out.append(s.split("=", 1)[1].strip())
    return out


def _reference_files(staging):
    """The files whose text says what the game uses: Morrowind.ini, the active plugins in Data Files (every
    plugin there without an ini) and every staged mod's plugins (which may be active once deployed)."""
    data = _data_dir()
    out = [os.path.join(HERE, "Morrowind.ini")]
    names = _ini_plugins(HERE)
    try:
        listing = os.listdir(data)
    except OSError:
        listing = []
    if names is None:
        names = [e for e in listing if os.path.splitext(e)[1].lower() in (".esm", ".esp")]
    out += [os.path.join(data, n) for n in names]
    for d in (os.listdir(staging) if staging and os.path.isdir(staging) else ()):
        md = os.path.join(staging, d)
        if os.path.isdir(md):
            out += [os.path.join(md, e) for e in os.listdir(md) if os.path.splitext(e)[1].lower() in (".esm", ".esp")]
    return [p for p in out if os.path.isfile(p)]


def _stat_sig(paths):
    rows = []
    for p in paths:
        try:
            st = os.stat(p)
            rows.append([os.path.normcase(p), st.st_size, st.st_mtime_ns])
        except OSError:
            pass
    return hashlib.sha1(json.dumps(sorted(rows)).encode()).hexdigest()


def _core_candidates(ext):
    """[(kind "bsa"/"loose", archive or "", path under Data Files, offset, size)] of the core files of a type."""
    import mwdialog_bsa as BSA
    data, out = _data_dir(), []
    instead = f"a {ext} dummy is copied from the other core files, if any"
    for name in CORE_BSAS:
        p = os.path.join(data, name)
        if not os.path.isfile(p):
            if name == "Morrowind.bsa":
                _core_missing(name, "Morrowind.bsa is missing from Data Files", instead)
            continue
        try:
            idx = BSA.bsa_index(p)
        except (OSError, ValueError, struct.error, BSA.FormatError) as e:
            if name == "Morrowind.bsa":
                _core_missing(name, f"Morrowind.bsa can't be read ({e})", instead)
            continue
        if name == "Morrowind.bsa" and ext == ".kf" and KF_FALLBACK not in idx:
            _core_missing(KF_FALLBACK, f"{KF_FALLBACK} is not in Morrowind.bsa",
                          "a .kf dummy is copied from the other core animations, if any")
        out += [("bsa", name, n, off, size) for n, (off, size) in sorted(idx.items()) if n.endswith(ext) and size > 0]
    for top in (os.listdir(data) if os.path.isdir(data) else ()):
        if top.lower() not in CORE_LOOSE_DIRS:
            continue
        for dp, _ds, fns in os.walk(os.path.join(data, top)):
            for fn in sorted(fns):
                if not fn.lower().endswith(ext):
                    continue
                p = os.path.join(dp, fn)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                if st.st_nlink == 1 and st.st_size > 0:        # a Vortex-deployed file is a hard link: not core
                    out.append(("loose", "", os.path.relpath(p, data).lower(), 0, st.st_size))
    return out


def _read_core(c):
    kind, bsa, rel, off, size = c
    data = _data_dir()
    if kind == "bsa":
        with open(os.path.join(data, bsa), "rb") as f:
            f.seek(off)
            b = f.read(size)
    else:
        with open(os.path.join(data, rel), "rb") as f:
            b = f.read()
    if len(b) != size:
        raise OSError(f"{rel}: read {len(b)} of {size} bytes")
    return b


def _core_label(c, how):
    kind, bsa, rel, _off, _size = c
    name = rel.replace("\\", "/").rsplit("/", 1)[-1]
    return f"a copy of the game's {name} ({bsa if kind == 'bsa' else 'Data Files'}; {how})"


def _used(c, ext, text):
    stem = os.path.splitext(c[2].replace("/", "\\").split("\\")[-1])[0].lower()
    if ext == ".kf" and stem.startswith("x"):
        stem = stem[1:]                               # x<model>.kf plays for <model>.nif
    return stem.encode("cp1252", "replace") in text


_REF_TEXT = {}


def _reference_text(files):
    key = _stat_sig(files)
    if key not in _REF_TEXT:
        parts = []
        for p in files:
            try:
                with open(p, "rb") as f:
                    parts.append(f.read().lower())
            except OSError:
                pass
        _REF_TEXT.clear()
        _REF_TEXT[key] = b"\n".join(parts)
    return _REF_TEXT[key]


def core_dummy(rel, staging=None):
    """(bytes, what) of a core game file to stand in for a broken file at rel, or None (see above)."""
    ext = os.path.splitext(rel)[1].lower()
    if not ext:
        return None
    cands = _core_candidates(ext)
    if not cands:
        return None
    k = _rk(rel)
    for c in cands:                                   # the core file the mod's file replaces
        if c[2].replace("/", "\\").lower() == k:
            return _read_core(c), _core_label(c, "the original this file replaces")
    files = _reference_files(staging)
    sig = hashlib.sha1((_stat_sig(files) + _stat_sig([os.path.join(_data_dir(), n) for n in CORE_BSAS])).encode()
                       ).hexdigest()
    cache_path = MP.state_path(HERE, DUMMY_SOURCES)
    try:
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    hit = cache.get(ext) if isinstance(cache, dict) else None
    if isinstance(hit, dict) and hit.get("sig") == sig:
        c = next((x for x in cands if list(x[:3]) == hit.get("pick")), None)
        if c is not None:
            try:
                b = _read_core(c)
                if _sha256_bytes(b) == hit.get("sha"):
                    return b, _core_label(c, hit.get("how", "cached choice"))
            except OSError:
                pass
    text = _reference_text(files)
    pick = how = None
    unused = sorted((c for c in cands if not _used(c, ext, text)), key=lambda c: (c[4], c[2]))
    if unused:
        pick, how = unused[0], "nothing in your plugins uses it"
    elif ext == ".kf":
        pick = next((c for c in cands if c[2] == KF_FALLBACK), None)
        how = "the small animation the asset tools use as a stand-in"
    if pick is None:
        pick, how = sorted(cands, key=lambda c: (c[4], c[2]))[0], "no unused one was found, so a used one"
    b = _read_core(pick)
    cache[ext] = {"sig": sig, "pick": list(pick[:3]), "sha": _sha256_bytes(b), "how": how}
    try:
        os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
        with open(cache_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=1, sort_keys=True)
        os.replace(cache_path + ".tmp", cache_path)
    except OSError:
        pass                                          # only the cache: the pick stands
    return b, _core_label(pick, how)


def dummy_bytes(rel, m=None, staging=None, nif=None):
    """(bytes, what it is) of the dummy for a broken file at rel, or (None, why there is none): a model gets the
    coin or the empty model (nif_dummy; nif: the kind the plan named), another type one made in code when it
    can be (GENERATED), else a copy of a core game file. m is not used (kept for callers)."""
    if os.path.splitext(rel)[1].lower() == ".nif":
        return nif_dummy(nif)[:2]
    got = generate_dummy(rel)
    if got:
        return got
    ext = os.path.splitext(rel)[1].lower()
    try:
        got = core_dummy(rel, staging)
    except OSError as e:
        return None, f"no dummy for {ext} files: the core game file couldn't be read ({e})"
    if got:
        return got
    return None, (f"no dummy for {ext or 'extension-less'} files: none can be made in code and the game data has "
                  f"no core file of that type to copy (it would need a dummy shipped with the tools)")


def _sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def tidy_dummies(root):
    """{path key: sha} of the files in the mod that are tidy's dummies, unchanged since they were put there."""
    base = os.path.join(root, "Off", "broken")
    out = {}
    for dp, _ds, fns in (os.walk(_xp(base)) if os.path.isdir(_xp(base)) else ()):
        for fn in fns:
            if not fn.endswith(DUMMY_MARK):
                continue
            try:
                with open(os.path.join(dp, fn), encoding="utf-8") as f:
                    mark = json.load(f)
                p = os.path.join(root, mark["rel"].replace("\\", os.sep))
                if os.path.isfile(_xp(p)) and _sha256(p) == mark["sha"]:
                    out[_rk(mark["rel"])] = mark["sha"]
            except (OSError, ValueError, KeyError, TypeError):
                continue
    return out


def _copy_elsewhere(rel, root, data_dir, bsa_meshes):
    """True when another copy of the model at rel is there to win once this mod's is out of the way: in
    another staged mod, loose in Data Files (not this mod's own deployed link) or in a BSA there."""
    k = _rk(rel)
    if k.startswith("meshes\\") and bsa_meshes and k[7:] in {x.lower() for x in bsa_meshes}:
        return True
    mine = os.path.join(root, rel)
    staging = os.path.dirname(os.path.abspath(root))
    places = [os.path.join(staging, d) for d in (os.listdir(staging) if os.path.isdir(staging) else ())
              if os.path.normcase(d) != os.path.normcase(os.path.basename(os.path.abspath(root)))]
    places += [data_dir] if data_dir else []
    for base in places:
        p = os.path.join(base, rel)
        if os.path.isfile(p):
            try:
                if os.path.exists(mine) and os.path.samefile(p, mine):
                    continue
            except OSError:
                pass
            return True
    return False


def apply_dummy_rule(root, m, ah, data_dir, bsa_meshes, issues, fixes, stats=None):
    """The asset check's findings with the dummy rule applied (see above): broken files get a "dummy" fix (the
    plan says what goes in their place); a broken model another copy can stand in for keeps the old way (moved
    out, Deploy lets the other copy win); a type with no safe dummy is left as it is and said so; tidy's own
    dummies, and a stand-in already in place of a broken model, are left alone. Returns (issues, fixes)."""
    mine = tidy_dummies(root)
    out, notes, drop = [], {}, set(mine)
    for fix in fixes:
        kind, full, rel, job = fix
        k = _rk(rel)
        if k in mine:
            continue                                  # tidy's dummy: not broken, not to be replaced
        if kind == "broken" or (kind == "brokenout" and job != "stand-in"):
            if kind == "brokenout" and _copy_elsewhere(rel, root, data_dir, bsa_meshes):
                out.append(fix)                       # another copy wins once this one is out
                continue
            b, what = dummy_bytes(rel, m, os.path.dirname(os.path.abspath(root)))
            if b is None:
                if kind == "brokenout":
                    out.append(fix)
                    notes[k] = f"moved to Off\\...\\broken\\ with no dummy in its place: {what}"
                else:
                    notes[k] = f"left as it is: {what}"
                    if stats is not None:
                        stats.setdefault("no_dummy", set()).add(os.path.splitext(rel)[1].lower() or "(none)")
                continue
            why = job if isinstance(job, str) else json.dumps(job, sort_keys=True)
            job = {"why": why}
            if os.path.splitext(rel)[1].lower() == ".nif":
                job["dummy"] = nif_dummy()[2]
                if job["dummy"] == "empty" and not NO_COINS and stats is not None:
                    stats["no_coin"] = True
            out.append(("dummy", full, rel, job))
            notes[k] = f"moved to Off\\...\\broken\\, {what} put in its place (a dummy, so what names it finds a file)"
            if kind == "brokenout":
                bm = getattr(ah, "BROKEN_MODELS", None)
                if isinstance(bm, list):
                    bm[:] = [(r, f"in {os.path.basename(os.path.normpath(root))}: vortex_tidy --apply moves it to "
                                 f"Off\\...\\broken\\ and puts a stand-in model in its place") if _rk(r) == k else (r, w)
                             for r, w in bm]
        elif kind == "brokenout":                     # job "stand-in": one is in place of a broken model already
            if _copy_elsewhere(rel, root, data_dir, bsa_meshes):
                out.append(fix)
            else:
                drop.add(k)                           # what the dummy rule wants: it stays
        else:
            out.append(fix)
    new_issues = []
    for sev, rel, msg in issues:
        k = _rk(rel)
        if k in drop:
            continue
        if k in notes:
            msg = msg.split(" -> ")[0] + " -> " + notes[k]
        new_issues.append((sev, rel, msg))
    if stats is not None and mine:
        stats["dummies"] = stats.get("dummies", 0) + len(mine)
    return new_issues, out


def make_dummies(root, dfixes, m, plug, renamed=None):
    """Put each broken file's original in <mod>\\Off\\broken\\<plugin>\\<path> (a different file there already: a
    dated name beside it), write its dummy in place (a Vortex hard link stays one) and mark it. Returns (done,
    [skipped notes])."""
    done, skipped = 0, []
    for _kind, full, rel, job in dfixes:
        if not os.path.isfile(_xp(full)) and renamed and full in renamed:
            rel = renamed[full]                       # renamed to its ASCII name by this run
            full = os.path.join(root, rel)
        b, what = dummy_bytes(rel, m, os.path.dirname(os.path.abspath(root)),
                              job.get("dummy") if isinstance(job, dict) else None)   # the kind the plan named
        if b is None:
            skipped.append(f"{rel} ({what})")
            continue
        try:
            h = _sha256(full)
            dest = m.off_dest(root, "broken", plug, rel)
            if os.path.exists(_xp(dest)) and _sha256(dest) != h:
                stem, ext = os.path.splitext(dest)
                dest, n = f"{stem}.{time.strftime('%Y%m%d-%H%M%S')}{ext}", 2
                while os.path.exists(_xp(dest)):
                    dest, n = f"{stem}.{time.strftime('%Y%m%d-%H%M%S')}-{n}{ext}", n + 1
            if not os.path.exists(_xp(dest)):
                os.makedirs(_xp(os.path.dirname(dest)), exist_ok=True)
                shutil.copy2(_xp(full), _xp(dest))
            if _sha256(dest) != h:
                raise OSError(f"the copy in {dest} reads back different")
            m.replace_asset_in_place(full, b)
            if _sha256(full) != _sha256_bytes(b):
                raise OSError("the dummy reads back different")
            with open(_xp(dest + DUMMY_MARK), "w", encoding="utf-8") as f:
                json.dump({"rel": rel, "sha": _sha256_bytes(b), "original": h, "dummy": what,
                           "by": "vortex_tidy", "when": time.strftime("%Y-%m-%d %H:%M:%S")}, f)
            done += 1
        except OSError as e:
            skipped.append(f"{rel} ({e})")
    return done, skipped


def assets_check_mod(root, m, ah, data_dir, bsa_meshes, game_dir, stats):
    issues, fixes = ah.check_folder(root, m, data_dir, bsa_meshes, stats=stats)
    issues, fixes = apply_dummy_rule(root, m, ah, data_dir, bsa_meshes, issues, fixes, stats)
    lp_plan = []
    try:                                              # paths too long once deployed (Windows' 259 characters)
        lp_issues, lp_plan = m.longpaths_module().check_mod(root, data_dir, m, game_dir)
        issues = lp_issues + issues
    except Exception as e:
        print(f"  {os.path.basename(root)}: long-path check failed ({e})")
    return {"issues": issues, "fixes": fixes, "lp_plan": lp_plan}


def _bsa_meshes(m, data_dir):
    out = set()
    try:
        names = os.listdir(data_dir)
    except OSError:
        names = []
    for fn in names:
        if fn.lower().endswith(".bsa"):
            try:
                for pth in m.bsa_file_names(os.path.join(data_dir, fn)):
                    if pth.startswith("meshes/"):
                        out.add(pth[7:].replace("/", "\\"))
            except (OSError, ValueError, struct.error, getattr(m, "FormatError", ValueError)) as e:
                print(f"  (couldn't read {fn}: {e})")
    return out


def assets_check(args):
    """The asset check on each mod's own files: textures (DX10/BC7, over 2048, no mipmaps - only those
    the mod's own world models draw -, uncompressed, not a power of two, truncated), models (not Morrowind's
    format, Unix line endings in animation text keys, absolute texture paths), sounds (stereo, odd rates,
    24/32-bit or non-PCM WAV, big MP3 tags), empty files, non-ASCII names, paths too long once deployed.
    Nothing is changed: {"mods": {folder: {...}}, "body": the plan's ASSET CHECK section, "keys": Counter of
    the repair actions}, or None when the asset modules are missing."""
    m, ah = _tool_modules()
    if m is None:
        print("\n(asset check skipped: mwdialog_check.py / mwdialog_assets.py not found next to vortex_tidy.py)")
        return None
    CORE_MISSING.clear()                              # once per run: what this check (and its --apply) finds
    game_dir = HERE
    mods = sorted(d for d in os.listdir(args.staging) if os.path.isdir(os.path.join(args.staging, d))
                  and d.lower() != "off")
    if args.only:
        mods = [d for d in mods if any(fnmatch.fnmatch(d.lower(), pat.lower()) for pat in args.only)]
    pats = blacklist(create=bool(args.apply)) + (args.skip or [])
    data_dir = os.path.join(game_dir, "Data Files")
    if not os.path.isdir(data_dir):
        print(f"\n(note: no Data Files folder next to vortex_tidy.py ({data_dir}): an animation's model in "
              f"another mod or a BSA can't be found, so more files may be reported)")
    bsa_meshes = _bsa_meshes(m, data_dir)
    print("\n" + "=" * 70 + "\nASSET CHECK (each mod's own files)\n" + "=" * 70)
    total_fix = total_issue = 0
    res = {"mods": {}, "m": m, "ah": ah, "data_dir": data_dir, "bsa": bsa_meshes, "game_dir": game_dir,
           "stats": {}, "done": set(), "body": ""}
    body = []
    for d in mods:
        if any(fnmatch.fnmatch(d.lower(), pt.lower()) for pt in pats):
            continue
        root = os.path.join(args.staging, d)
        try:
            ent = assets_check_mod(root, m, ah, data_dir, bsa_meshes, game_dir, res["stats"])
        except Exception as e:                      # one odd mod never stops the rest
            print(f"  {d}: check failed ({e})")
            continue
        ent["root"] = root
        res["mods"][d] = ent
        issues = ent["issues"]
        if not issues:
            continue
        acts = asset_action_lines(ent)
        total_issue += len(issues)
        total_fix += len(acts)
        print(f"\n{d}")
        for sev, rel, msg in issues[:12]:
            print(f"    {sev:5} {rel}: {msg}")
        if len(issues) > 12:
            print(f"    ... and {len(issues) - 12} more")
        body.append(f"\n{d}")
        body += [f"    {a}" for a in acts]
        body += [f"      issue: {sev} {rel}: {msg}" for sev, rel, msg in issues]
    summary = f"  {total_issue} asset issue(s), {total_fix} repairable"
    n_dummy = sum(1 for ent in res["mods"].values() for f in ent["fixes"] if f[0] == "dummy")
    if n_dummy:
        summary += (f"; {n_dummy} broken file(s) to move to Off\\...\\broken\\ with a dummy put in each one's "
                    f"place")
    n_nif = sum(1 for ent in res["mods"].values() for f in ent["fixes"]
                if f[0] == "dummy" and isinstance(f[3], dict) and "dummy" in f[3])
    if n_nif:
        summary += ("; models get " + ("the empty, invisible model (--no-coins)" if NO_COINS else
                                       f"the empty, invisible model: {NO_COIN_NOTE}" if res["stats"].get("no_coin")
                                       else "the Dwemer coin (--no-coins: an empty, invisible model)"))
    print(f"\n{summary}" + ("" if args.apply else " (run with --apply to repair them)"))
    st = res["stats"]
    if st.get("dummies"):
        print(f"  {st['dummies']} dummy file(s) vortex_tidy put in place of broken ones left alone (originals in "
              f"Off\\...\\broken\\; --undo puts them back)")
    if st.get("no_dummy"):
        print(f"  broken files left as they are, no safe dummy for: {', '.join(sorted(st['no_dummy']))}")
    if st.get("mips_skipped"):
        print(f"  {st['mips_skipped']} texture(s) without mipmaps left alone: no world model of their own "
              f"mod draws them (menu / MCM / icon / effect pictures, or a texture pack; mwdialog_check's asset "
              f"check judges texture packs against the models that are deployed). Patterns: "
              f"{ah.MIP_EXEMPT_RECORD}")
    res["body"] = "\n".join(body + [summary])
    _prune_asset_cache(args, res)
    return res


def _prune_asset_cache(args, res):
    # the per-mod records in the asset cache: files a checked mod no longer has, and (all mods checked) mods
    # that are gone, are dropped; then everything is written
    try:
        ah = res["ah"]
        cache = ah.shared_cache(res["game_dir"])
        present = None if args.only else {d.lower() for d in os.listdir(args.staging)
                                          if os.path.isdir(os.path.join(args.staging, d))}
        ah.prune_tidy(cache, {d.lower() for d in res["mods"]}, present)
        cache.flush()
    except Exception as e:                          # never stop tidy for its cache
        print(f"  (asset cache not tidied: {e})")


def assets_pending(ares):
    """Plan lines of the reviewed asset repairs not done yet."""
    if not ares:
        return []
    out = []
    for d, ent in ares["mods"].items():
        acts = [a for a in asset_action_lines(ent) if (d, a) not in ares["done"]]
        acts += [a for qd, a in ares.get("queued", ()) if qd == d and (d, a) not in ares["done"]]
        if acts:
            out += [f"\n{d}"] + [f"    {a}" for a in acts]
    return out


def _only(ent, lines):
    """ent's fixes and long-path moves whose plan line is in lines."""
    return ([f for f, a in zip(ent["fixes"], asset_action_lines(dict(ent, lp_plan=[]))) if a in lines],
            [lp for lp, a in zip(ent["lp_plan"], asset_action_lines(dict(ent, fixes=[]))) if a in lines])


def assets_apply(args, ares, moved_mods=()):
    """Make the asset repairs assets_check() listed (the reviewed ones). A mod whose files the moves of this
    run touched is checked again first: the reviewed repairs that still apply are made, reviewed lines the
    moves made obsolete (old paths) are dropped, and repairs that only show up after the moves (new paths,
    or files moved into a checked folder) are queued. When every mod is done, the queue - and only the
    queue - is processed. Originals go to <mod>\\Off\\<plugin>\\<path>, and (for --undo) every file a mod's
    repairs can change is first kept in <backups folder>\\tidy\\<run>\\assets (see AssetJournal): a mod whose
    originals can't be kept is not repaired."""
    if not ares:
        return
    m, ah, game_dir = ares["m"], ares["ah"], ares["game_dir"]
    aj = AssetJournal(args)
    queue = []
    for d, ent in ares["mods"].items():
        root = ent["root"]
        wanted = set(asset_action_lines(ent))
        if d in moved_mods:
            try:
                now = assets_check_mod(root, m, ah, ares["data_dir"], ares["bsa"], game_dir, {})
            except Exception as e:
                print(f"  {d}: check failed ({e})")
                continue
            new = set(asset_action_lines(now))
            for a in wanted - new:                    # its file is no longer there: the moves settled it
                ares["done"].add((d, a))
            if new - wanted:
                queue.append((d, root, now, new - wanted))
            fixes, lp_plan = _only(now, wanted)
            work = dict(now, fixes=fixes, lp_plan=lp_plan)
        else:
            work = ent
        issues, fixes, lp_plan = work["issues"], work["fixes"], work["lp_plan"]
        if not issues:                                # clean now: drop an old tidy section
            bdir = os.path.join(root, "bugreports")
            reports = [os.path.join(bdir, e) for e in (os.listdir(bdir) if os.path.isdir(bdir) else ())
                       if e.lower().endswith(".bugreport.txt")]
            if reports:
                tok = _journal_begin(aj, d, root, reports)
                if tok is False:
                    continue
                try:
                    for p in reports:
                        ah.update_bug_report(p, "vortex_tidy (files)", [], [])
                finally:
                    aj.end(tok)
            continue
        if not fixes and not lp_plan:
            continue
        plug_file = next((e for e in sorted(os.listdir(root))
                          if os.path.splitext(e)[1].lower() in (".esp", ".esm")), None)
        plug = os.path.splitext(plug_file)[0] if plug_file else mod_name(d)
        subject, head = ah.package_bug_report_subject(root, m, mod_name(d))
        lines = ah.package_asset_bug_lines(issues)
        if lines:
            lines += ["", "(The mod's copy was repaired on this PC; originals kept in Off\\.)"]
        tok = _journal_begin(aj, d, root, _repair_candidates(root, fixes, lp_plan, _lpm_of(m, lp_plan)))
        if tok is False:
            continue
        try:
            ah.update_bug_report(ah.package_bug_report_path(root, subject), "vortex_tidy (files)", head, lines)
            _repair(ares, d, root, fixes, lp_plan, plug)
        finally:
            aj.end(tok, lp_plan)
    if queue:
        print(f"\nQueue: {sum(len(q[3]) for q in queue)} repair(s) found after the moves")
    for d, root, now, lines in queue:
        fixes, lp_plan = _only(now, lines)
        plug_file = next((e for e in sorted(os.listdir(root))
                          if os.path.splitext(e)[1].lower() in (".esp", ".esm")), None)
        print(f"  {d}: {len(lines)} queued repair(s)")
        tok = _journal_begin(aj, d, root, _repair_candidates(root, fixes, lp_plan, _lpm_of(m, lp_plan)))
        if tok is False:
            continue
        try:
            _repair(ares, d, root, fixes, lp_plan, os.path.splitext(plug_file)[0] if plug_file else mod_name(d))
        finally:
            aj.end(tok, lp_plan)
        ares["queued"] = ares.get("queued", []) + [(d, a) for a in sorted(lines) if (d, a) not in ares["done"]]


def _lpm_of(m, lp_plan):
    """The short-path module (to tell which models a short path rewrites), or None (then all are kept)."""
    if not lp_plan:
        return None
    try:
        return m.longpaths_module()
    except Exception:
        return None


def _journal_begin(aj, d, root, candidates):
    """aj.begin(); False (after saying why) when the originals can't be kept, so the mod is left as it is."""
    try:
        return aj.begin(d, root, candidates)
    except OSError as e:
        print(f"  {d}: NOT repaired: its original files could not be kept for --undo ({e})")
        return False


def _repair(ares, d, root, fixes, lp_plan, plug):
    """Make one mod's repairs and mark each one that worked in ares["done"]."""
    m, ah, game_dir = ares["m"], ares["ah"], ares["game_dir"]
    if lp_plan:
        lpm = m.longpaths_module()
        n = lpm.apply_mod(root, lp_plan, m, game_dir, plug, log=print)
        for lp, a in zip(lp_plan, asset_action_lines({"fixes": [], "lp_plan": lp_plan})):
            if os.path.exists(os.path.join(root, lpm.fs(lp["short"]) if hasattr(lpm, "fs") else lp["short"])):
                ares["done"].add((d, a))
        print(f"    -> {n} file(s) moved to a short path (listed in mwdialog_longpaths.json; "
              f"mwdialog_check --longpaths-undo puts them back)")
        gone = {lp["orig"].lower() for lp in lp_plan} | {t[0].lower() for lp in lp_plan for t in lp["twins"]}
        fixes = [f for f in fixes if f[2].replace("/", "\\").lower() not in gone]   # moved: next run
    dfixes = [f for f in fixes if f[0] == "dummy"]
    renamed = {f[1]: f[3] for f in fixes if f[0] == "ascii" and isinstance(f[3], str)}
    fixes = [f for f in fixes if f[0] != "dummy"]
    if fixes:
        done, skipped = ah.apply_folder(root, fixes, m, game_dir, plug)
        for f, a in zip(fixes, asset_action_lines({"fixes": fixes, "lp_plan": []})):
            if not any(sk.startswith(f[2] + " (") for sk in skipped):
                ares["done"].add((d, a))
        print(f"    -> {done} file(s) repaired (originals in Off\\{plug}\\)"
              + (f"; {len(skipped)} skipped, e.g. {skipped[0]}" if skipped else ""))
    if dfixes:
        done, skipped = make_dummies(root, dfixes, m, plug, renamed)
        for f, a in zip(dfixes, asset_action_lines({"fixes": dfixes, "lp_plan": []})):
            if not any(sk.startswith(renamed.get(f[1], f[2]) + " (") or sk.startswith(f[2] + " (") for sk in skipped):
                ares["done"].add((d, a))
        print(f"    -> {done} broken file(s) moved to Off\\broken\\{plug}\\, a dummy put in each one's place"
              + (f"; {len(skipped)} skipped, e.g. {skipped[0]}" if skipped else ""))


def main():
    MT.install()
    ap = MT.parser(description="Tidy the mods in Vortex's Morrowind staging folder.")
    ap.add_argument("--staging", default=None, metavar="DIR",
                    help="Vortex Morrowind staging folder (default: Vortex's own setting)")
    ap.add_argument("--only", nargs="+", metavar="PATTERN", help="only these mod folders (wildcards allowed)")
    ap.add_argument("--skip", nargs="+", metavar="PATTERN",
                    help="leave these mod folders alone this time too (to always skip one, add it to "
                         "vortex_tidy_blacklist.txt)")
    ap.add_argument("--apply", action="store_true", help="make the changes (without it, only the plan is shown)")
    ap.add_argument("--yes", action="store_true", help="with --apply: don't ask first")
    ap.add_argument("--undo", action="store_true",
                    help="put back everything the last --apply changed: the moves, the Lua patches, the "
                         "original of every file an asset repair changed, at its own path, and an omw2mwse "
                         "conversion (its generated files removed, the original package put back)")
    ap.add_argument("--force", action="store_true",
                    help="with --undo: put originals back even over files changed since the --apply")
    ap.add_argument("--no-assets", action="store_true", help="skip the asset check of each mod's files")
    ap.add_argument("--no-lua", action="store_true", help="skip the Lua check (mwdialog_luafix)")
    ap.add_argument("--lua-only", action="store_true", help="only the Lua check: no moves, no asset check")
    ap.add_argument("--lua-level", choices=("high", "medium"), default="high",
                    help="which Lua findings --apply patches (default high)")
    ap.add_argument("--luajit", help="the LuaJIT (or luac) the Lua check compiles with")
    ap.add_argument("--lua-log", choices=("flagged", "all", "off"),
                    help="which mods the Lua check gives the log shim: flagged (default), all, off")
    ap.add_argument("--no-reduce-textures", action="store_true", help="don't reduce textures larger than 2048")
    ap.add_argument("--no-reduce-splash", action="store_true",
                    help="don't reduce splash screens wider than 2048 (they are still made 24-bit RLE TGA)")
    ap.add_argument("--no-coins", action="store_true",
                    help="a broken or missing model gets an empty, invisible model instead of the game's Dwemer "
                         "coin (the default, so the gap is easy to spot)")
    ap.add_argument("--convert-omwscripts", nargs="?", const="hardcode", default="hardcode", choices=CONVERT_MODES,
                    metavar="MODE",
                    help="OpenMW-only mods (OpenMW scripts, no MWSE Lua) are converted for MWSE by omw2mwse, found "
                         "on PATH or beside these tools, in this mode: hardcode (the default; hard-coded values "
                         "become MCM settings) or normal. Mods with MWSE Lua are never converted: their OpenMW "
                         "files go to Off\\OpenMW\\. An OpenMW-only mod that is not converted gets its whole "
                         "package moved to Off\\<plugin name>\\OpenMW\\")
    ap.add_argument("--no-convert-omwscripts", dest="convert_omwscripts", action="store_const", const=None,
                    help="don't convert: OpenMW-only mods get their whole package moved to Off\\<plugin name>\\OpenMW\\")
    args = ap.parse_args()
    setup_converter(args.convert_omwscripts)
    global NO_COINS
    NO_COINS = args.no_coins
    if args.no_reduce_textures or args.no_reduce_splash:
        m, ah = _tool_modules()
        if ah is not None:
            ah.keep_full_size(m, args.no_reduce_textures, args.no_reduce_splash)
    if not (MP.acquire_run_lock()
            and (not os.path.isdir(os.path.join(HERE, "Data Files")) or MP.acquire_game_lock(HERE))):
        print(MP.RUN_LOCKED_MESSAGE, file=sys.stderr)
        return 1
    if args.undo:                                     # works from the journal; the plan file plays no part
        before = {st: bugreport_folders(st) for st in (_journal_stagings() if os.path.exists(JOURNAL) else [])}
        try:
            return undo(args.force)
        finally:
            remove_empty_bugreports(before)
    try:
        args.staging = MP.resolve_staging(cli=args.staging, required=True)
    except MP.VortexPathError as e:
        print(str(e), file=sys.stderr)
        return 2
    src = "--staging" if any(a == "--staging" or a.startswith("--staging=") for a in sys.argv[1:]) else "Vortex settings"
    print(f"Vortex staging: {args.staging}  (from {src})")
    CORE_MISSING.clear()
    before = {args.staging: bugreport_folders(args.staging)}
    try:
        if not args.apply:
            return plan_main(args)
        return apply_main(args)
    finally:
        remove_empty_bugreports(before)
        print_core_warning()                          # once per run, last, whatever happened


def compose(moves_text, lua_body=None, asset_body=None):
    """The plan file: the moves part, then the LUA CHECK and ASSET CHECK sections (when there)."""
    t = (moves_text or "").rstrip("\n") + "\n"
    if lua_body is not None:
        t += f"\n{LUA_HEAD}\n" + lua_body.rstrip("\n") + "\n"
    if asset_body is not None:
        t += f"\n{ASSET_HEAD}\n" + asset_body.rstrip("\n") + "\n"
    return t


def _lua_only_base(text):
    """For --lua-only: the parts of a pending plan file that are not the Lua section (kept as they are)."""
    if PF.state(PLAN) != "pending":
        return f"vortex_tidy plan (Lua only), {time.strftime('%Y-%m-%d %H:%M')}\n", None
    sec = PF.sections(text)
    return sec.get("moves", ""), sec.get(ASSET_HEAD)


def fresh_plan(args):
    """Work the plan out (nothing changed, nothing written): (text, parts compared, moves, lua, assets)."""
    if args.lua_only:
        lres = lua_check(args)
        base, abody = _lua_only_base(PF.read(PLAN))
        return compose(base, lres["body"] if lres else "", abody), [LUA_HEAD], [], lres, None
    args._write_plan = False
    moves = run_plan(args)
    lres = None if args.no_lua else lua_check(args)
    ares = None if args.no_assets else assets_check(args)
    parts = ["moves"] + ([] if args.no_lua else [LUA_HEAD]) + ([] if args.no_assets else [ASSET_HEAD])
    text = compose(args._moves_text, None if args.no_lua else (lres["body"] if lres else ""),
                   None if args.no_assets else (ares["body"] if ares else ""))
    warn = core_warning()
    if warn:                                          # "#" lines: not actions, so --apply compares the same
        text += "\n" + "\n".join("# " + ln if ln else "#" for ln in warn) + "\n"
    return text, parts, moves, lres, ares


def plan_main(args):
    text, _parts, moves, lres, ares = fresh_plan(args)
    PF.write_atomic(PLAN, text)
    print(f"\nFull plan: {PLAN}")
    if moves or REVIEW or CONVERT or (lres and lres["n_ok"]) or assets_pending(ares):
        print("\nNothing changed. Purge in Vortex, review the plan, run again with --apply, then Deploy.")
    else:
        print("\nNothing to fix.")
    return 0


def apply_main(args):
    """--apply enacts the plan you reviewed and nothing else: the plan is worked out again and must list the
    same actions as the plan file (moves, Lua patches, asset repairs; --lua-only: the Lua section only), or
    nothing is done - the new plan is written for review and the old one kept as vortex_tidy_plan.prev.txt.
    Afterwards the plan file is blanked, or cut down to what was not applied, atomically, with copies of the
    plan as reviewed and as enacted in <backups folder>\\tidy\\<run>\\."""
    reviewed = PF.read(PLAN)
    parts = [LUA_HEAD] if args.lua_only else \
        ["moves"] + ([] if args.no_lua else [LUA_HEAD]) + ([] if args.no_assets else [ASSET_HEAD])
    if PF.state(PLAN) != "pending" or not PF.has_any_actions(reviewed, parts):
        print(PF.no_plan_message(PLAN, "vortex_tidy.py" + (" --lua-only" if args.lua_only else "")))
        return 2
    text, parts, moves, lres, ares = fresh_plan(args)
    added, removed = PF.compare(reviewed, text, parts)
    if added or removed:
        PF.refuse_mismatch(PLAN, text, added, removed, "vortex_tidy.py" + (" --lua-only" if args.lua_only else ""))
        return 2
    print("\nThe plan matches the one you reviewed.")
    audit = os.path.join(AUDIT_ROOT, time.strftime("%Y%m%d-%H%M%S"))
    # "apply": one id for every journal head of this --apply (moves, Lua, assets), so one --undo undoes them all
    args._journal_extra = {"plan_copy": os.path.join(audit, "plan_enacted.txt"),
                           "apply": f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-{time.time_ns()}"}
    args._audit = audit                               # asset repairs keep their originals in <audit>\\assets
    sec = PF.sections(reviewed)
    keep = {k: v for k, v in sec.items() if k not in parts and PF.has_any_actions(v)}   # not enacted: stays
    st = {"moves": [], "progress": [], "lua": lres, "assets": ares, "keep": keep, "started": False,
          "finished": False, "text": text, "convert": [], "convert_left": []}
    if not args.lua_only:
        moves, gone = review(args.staging, moves, assume_keep=args.yes)
        conv = sorted(CONVERT)
        if moves or gone or conv:
            what = f"{sum(1 for m in moves if m[1])} move(s)" + (f" and delete {len(gone)} mod(s)" if gone else "") \
                + (f" and convert {len(conv)} OpenMW-only mod(s) with omw2mwse ({CONVERTER['mode']})" if conv else "")
            if not args.yes and input(f"\nApply {what}? Purge in Vortex first. [y/N] ").strip().lower() not in \
                    ("y", "yes"):
                print("Nothing changed.")
                return 0
        else:
            print("Nothing to move.")
        st["moves"] = gone + moves
        st["convert"] = st["convert_left"] = conv
    left = []
    try:
        st["started"] = True
        if st["moves"]:
            apply(st["moves"], args.staging, st["progress"], args._journal_extra)
        lua_apply(args, lres)
        moved_mods = {os.path.relpath(st["moves"][i][0], args.staging).split(os.sep)[0] for i in st["progress"]}
        assets_apply(args, ares, moved_mods)
        if st["convert"]:                            # last: it lays those mods out itself
            st["convert_left"] = convert_apply(args.staging, st["convert"], CONVERTER["mode"],
                                              args._journal_extra)
        st["finished"] = True
    finally:
        left = _finish_plan(args, st, reviewed, audit)
    return 0 if not left else 1


def _left_lines(args, st):
    done = set(st["progress"])
    out = []
    if "moves" in st["keep"]:
        out += [ln for ln in st["keep"]["moves"].splitlines() if not ln.startswith("#")]
    out += moves_as_lines([m for i, m in enumerate(st["moves"]) if i not in done], args.staging)
    for mod_dir in st.get("convert_left") or []:     # not converted (failed, or the run stopped first)
        out += convert_lines(os.path.basename(mod_dir), CONVERT.get(mod_dir, []), CONVERTER["mode"])
    lua = lua_pending(st["lua"]) or ([st["keep"][LUA_HEAD]] if LUA_HEAD in st["keep"] else [])
    if lua:
        out += ["", LUA_HEAD] + lua
    ast = assets_pending(st["assets"]) or ([st["keep"][ASSET_HEAD]] if ASSET_HEAD in st["keep"] else [])
    if ast:
        out += ["", ASSET_HEAD] + ast
    return out


def _finish_plan(args, st, reviewed, audit):
    if not st["started"]:
        return []
    left = _left_lines(args, st)
    note = "" if st["finished"] else "the run was interrupted; anything not listed here was applied"
    PF.finish(PLAN, "vortex_tidy.py" + (" --lua-only" if args.lua_only else ""), left, audit, reviewed,
              st["text"], note)
    return left


# ---------------------------------------------------------------- empty bugreports\ folders
# A mod's bugreports\ folder is made when a bug report is written, and update_bug_report deletes a report left
# with no sections but not its folder. Whatever makes one, tidy never leaves one behind: at the end of every run
# (plan, --apply, --undo) a mod's bugreports\ folder that is empty and that tidy made (absent when the run
# began) or emptied (it held files then) is removed. One that was already empty is not ours and stays.

def bugreport_folders(staging):
    """{path of a mod's bugreports folder: True when it holds anything} for every mod folder in staging."""
    out = {}
    try:
        mods = os.listdir(staging)
    except OSError:
        return out
    for d in mods:
        md = os.path.join(staging, d)
        try:
            names = os.listdir(md) if os.path.isdir(md) else ()
        except OSError:
            continue
        for e in names:
            p = os.path.join(md, e)
            if e.lower() == "bugreports" and os.path.isdir(p):
                try:
                    out[p] = bool(os.listdir(p))
                except OSError:
                    pass
    return out


def remove_empty_bugreports(before):
    """before: {staging: bugreport_folders(staging) at the start of the run}. Removes what the rule above says."""
    for staging, was in before.items():
        for p, has in bugreport_folders(staging).items():
            if not has and was.get(p) is not False:
                try:
                    os.rmdir(p)
                except OSError:
                    pass


def _journal_stagings():
    """The staging folders named by the journal's runs (what an --undo can touch)."""
    out = []
    try:
        for r in _read_journal_runs():
            st = r["head"].get("staging")
            if st and os.path.isdir(st) and st not in out:
                out.append(st)
    except OSError:
        pass
    return out


def _main_with_notice():
    try:
        return main()
    finally:
        ah = sys.modules.get("mwdialog_assets")
        if ah is not None:
            ah.broken_models_notice()


if __name__ == "__main__":
    sys.exit(_main_with_notice())
