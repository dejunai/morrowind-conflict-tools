#!/usr/bin/env python3
"""vortex_tidy.py - tidy the mods in Vortex's Morrowind staging folder.

For each mod folder in Vortex's Morrowind staging folder (from Vortex's settings, or --staging):

  * Game folders stay where they are: meshes, textures, icons, sound, music, bookart, splash, fonts,
    video, distantland; and support folders: MWSE, MGE3, shaders (MGE XE's XEshaders), grass, mcpatch.
    Plugins (.esp/.esm/.omwaddon), .bsa archives and MWSE's *-metadata.toml files at the root stay too.
    So do the folders this script makes or keeps: Docs, Extras, OpenMW, and the Off folder of every mod
    (everything the tools set aside, in ONE layout - Off\\<plugin>\\<reason>\\<path>, see docs\\dev\\OFF-LAYOUT.md;
    older layouts in it are migrated, below). An Off folder at the top of the staging folder is never touched.
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
    Off\\<plugin>\\normal maps\\ (never deployed): vanilla Morrowind with MGE XE doesn't use them (only OpenMW
    does). If a model names one, mwdialog_check.py --fix puts a flat stand-in normal map in its place, so
    the game shows no missing-texture warnings. Only normal maps whose diffuse texture exists move (tx_wall.dds
    for tx_wall_n.dds: beside it, at the same path under textures\\ in any mod in staging, loose in Data Files,
    or in a BSA there). One with no diffuse anywhere stays where it is, untouched and without a stand-in; if
    nothing uses it, mwdialog_check --full's unused-asset purge takes it out later. The exception: a file
    whose path says "normal map(s)" in any spelling (an add-on normal-map pack, for OpenMW) moves either way, and the plan notes
    the pack as not applicable to classic Morrowind.
  * MGE XE grass plugins (only statics and cells, nearly all grass/groundcover) go to Grass\\, where MGE
    XE's distant land generator reads them; the game itself never loads them.
  * OpenMW-only content goes to Off\\<plugin>\\OpenMW\\ (never deployed): *.omwscripts files and the scripts, l10n,
    animations and playlists folders; an OpenMW\\ folder an earlier run made at the root is moved there too.
  * The Off layout: <plugin> is the mod's first plugin's name (else its first .omwscripts' stem, as omw2mwse names
    it, else the mod's name), <reason> one of a fixed list (docs\\dev\\OFF-LAYOUT.md: broken, ascii, unused assets...).
    Every older layout in a mod's Off folder is moved into it in the same plan and journal (so --undo reverses
    it): loose files directly in Off\\, Off\\<reason>\\<plugin>\\ (MWManager's and the older tools' spellings are
    mapped to the new reason names), Off\\OpenMW\\<mod>\\, Off\\<path>. A name taken is never overwritten (" (2)"),
    omw2mwse's own output (listed in its manifest) is never moved, and what is not recognised stays, with one NOTE.
    A file whose path is over MAX_PATH (259), or would be after the move, is never moved (it would only get
    worse): it is listed in Off\\<plugin>\\max_path_too_long.txt, one path per line relative to the mod's folder
    (refreshed, never duplicated; --undo puts back what was there).
  * An OpenMW-only mod (OpenMW scripts - an *.omwscripts file at its root, in OpenMW\\ or set aside under Off\\ -
    and no MWSE Lua of its own) is converted for MWSE instead: --apply runs the OpenMW converter, omw2mwse
    --convert-omwscripts=<mode> <mod> --json (found on PATH or beside these tools; normal by default;
    --convert-omwscripts=hardcode for the other mode, with --accept-hardcode-conversions; --no-convert-omwscripts for
    neither), which lays the mod out itself, so nothing else in it moves that run; the plan shows a dry-run
    preview. A conflict (exit 4) or other failure is one WARNING line, the run goes on, and the mod is treated as
    not convertible (below). A mod with real MWSE Lua (a .lua under MWSE\\ that omw2mwse didn't generate) is
    MWSE-first: its OpenMW files go to Off\\<plugin>\\OpenMW\\ as above and are never converted. An OpenMW-only mod that
    is not converted (no converter, a failed or blocked conversion, --no-convert-omwscripts) has its ENTIRE
    package moved to Off\\<plugin name>\\OpenMW\\ (omw2mwse's own place and name: the first .omwscripts' stem, e.g.
    Off\\wildlife_attacks_npc\\OpenMW\\) - plugins, scripts, data folders, Docs\\, Screenshots\\ - so the staging root
    keeps only Off\\ (and Vortex's marker file) and that is all it deploys; an Off\\OpenMW\\<mod>\\ folder from an
    earlier tidy run is moved there too (and merged with what is there); --undo puts each file back. Without the converter: one WARNING line.
    The converter declares the Python it needs (requires-python in its pyproject.toml, or requiresPython in its --json;
    current omw2mwse is 3.9+). Tidy probes the Python that would run it and, when that is older than the declared minimum
    (or, if nothing is declared, older than 3.11), treats the converter as missing - one WARNING, and the mod's whole
    package goes to Off\\<plugin>\\OpenMW\\.
    The plan shows what the converter would do (its dry run): the verdict with any partly implemented OpenMW API
    the mod uses beside it, each hard-coded value it would make a setting and where each plugin goes, and an
    "omw2mwse check" digest of that preview, of every file in the mod folder and of the converter itself (version,
    path, Python, the hashes of its files). --apply works it out again and refuses when the digest changed (a
    sidecar edit, a changed source file, another converter), and checks the converter once more before running it.
    Before omw2mwse writes anything, --apply records a recovery intent beside the journal (every file of the mod
    with its hash; a copy of each file the converter will overwrite or remove); a run that stopped part-way is put
    back exactly by the next --apply or --undo (the plan warns), or, when that can't be exact, nothing is changed.
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
    A mod whose original author asked to be left out of conversion is not converted: omw2mwse writes nothing (not
    even a manifest) and answers verdict blocked (exit 0). Tidy treats it like any blocked mod (the whole package to
    Off\\<plugin name>\\OpenMW\\, untouched) with one WARNING line in plain words telling the user to contact the
    original mod author; where the converter found the request is never shown or logged. A reason of any other shape
    is shown as text and never stops tidy, and a missing manifest is fine.
  * A bugreports\\ folder tidy made during a run that is empty at the end of it (--apply, a dry run or --undo)
    is removed again; one that was already there, or has anything in it, stays.
  * Everything else (screenshots, FOMOD option folders, meta.ini, .bak files...) goes to
    Extras\\<mod name>\\, where <mod name> is the folder name without Vortex's Nexus id, version and
    download stamp ("MUSE 2.02-46200-2-02-1593543300" -> "MUSE").

Mods that install into the game folder instead of Data Files (an .exe, .dll or a "Data Files" folder at
their root, like MGE XE) are left alone, and so is every mod on the blacklist: the Morrowind Code Patch and
NIFZER0EDIT built in, plus the folder names in vortex_tidy_blacklist.txt (one per line, wildcards allowed).
If that file is missing it is created with the built-in patterns and *Breezify*; an existing file is never
overwritten or added to.

  * MWSE Lua mods (MWSE\\mods\\...\\*.lua) are checked by mwdialog_luafix.py for bad habits that pass a syntax
    check (absurd priorities, polling every frame, one-shot handlers that never unregister, unguarded ref.data,
    infoFilter reading text, re-registering on every load, log spam...). The plan lists them; --apply patches
    the safe ones in place (hard links stay; the LuaJIT checker must compile the result; originals kept in
    <backups folder>\\luafix), --undo puts them back. --no-lua skips this, --lua-only does only this.

  * Broken asset files the asset check can't repair (empty, not the format their name says, truncated, a model
    the game crashes on, an MP3 with no audio) go to <mod>\\Off\\<plugin>\\broken\\<path>, and a small valid
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
everything back. Deploy in Vortex afterwards, so the game folder matches (Purging before applying is good
practice, not needed: Vortex removes the moved files on that Deploy).
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
import posixpath
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_backup as MB                     # noqa: E402
import mwdialog_planfile as PF                   # noqa: E402
import mwdialog_offlayout as OL                  # noqa: E402
import mwdialog_paths as MP                      # noqa: E402
import mwdialog_version                            # noqa: E402
import mwdialog_report as MR                     # noqa: E402
import mwdialog_staged as MS                     # noqa: E402
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
# (beside the tools; wildcards allowed, matched against the mod's folder name, case doesn't matter)
BLACKLIST = ["Morrowind Code Patch*", "MCP beta*", "NIFZER0EDIT*"]
BLACKLIST_EXTRA = ["*Breezify*"]          # generated into the starter file, not hardcoded
BLACKLIST_FILE = MP.state_path(HERE, "vortex_tidy_blacklist.txt")


def blacklist_starter_text():
    """The file written when vortex_tidy_blacklist.txt is missing: the built-in patterns and *Breezify*."""
    lines = [
        "; vortex_tidy blacklist: mods it never touches. One mod folder name per line; * and ? work.",
        "; Created when the file is missing; an existing file is never overwritten or added to.",
    ]
    return "\n".join(lines + BLACKLIST + BLACKLIST_EXTRA) + "\n"


def blacklist(create=True):
    """The blacklist patterns. If vortex_tidy_blacklist.txt is missing and create is true, it is written with
    the built-in patterns and *Breezify*; an existing file is never overwritten or added to."""
    pats = list(BLACKLIST)
    if not os.path.exists(BLACKLIST_FILE):
        if not create:
            return pats + list(BLACKLIST_EXTRA)
        try:
            folder = os.path.dirname(os.path.abspath(BLACKLIST_FILE))
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(BLACKLIST_FILE, "x", encoding="utf-8") as f:
                f.write(blacklist_starter_text())
        except FileExistsError:
            pass
        except OSError:
            return pats + list(BLACKLIST_EXTRA)
    try:
        for line in open(BLACKLIST_FILE, encoding="utf-8-sig", errors="replace"):
            line = line.strip()
            if line and not line.startswith((";", "#")):
                pats.append(line)
    except OSError:
        pass
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


def _spelled(base, *names):
    """base\\names..., each level in the spelling the folder already has (a new one: as given)."""
    for n in names:
        base = os.path.join(base, existing(base, n) if os.path.isdir(base) else n)
    return base


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
OWNER = {}             # mod folder -> its Off\\<plugin> folder name in this plan (mwdialog_offlayout.owner_name)
MIG_NOTES = {}         # mod folder -> what the Off migration left alone (one NOTE per mod)
LIST_TEXT = {}         # normcased path of a max_path_too_long.txt -> the text --apply writes (None: removes it)
LIST_WRITE = "write the list of %d path(s) too long for Windows (MAX_PATH %d): those files were not moved"
LIST_REMOVE = "remove the list: no path is too long any more"
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
    """Every diffuse-capable texture there is: in each mod in the staging folder (not Off\\) and in its BSAs, and
    in the base game's BSAs (Morrowind/Tribunal/Bloodmoon.bsa: the one read-only look at Data Files before deploy,
    mwdialog_staged). Built once per staging folder."""
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
    bsas = MS.StagedData(staging, HERE, mods=roots).bsas()
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
        dst = os.path.join(package_dir(pname), rel)
        if os.path.isdir(src) and (os.path.isdir(dst) or dst.lower() in taken):     # a folder is merged, not renamed
            for x in sorted(os.listdir(src)):
                move(os.path.join(src, x), pname, os.path.join(rel, x))
            moves.append((src, None, "remove the emptied folder"))
            return
        moves.append((src, free_path(dst, taken), why))

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
        pname = package_name(folder) if _has_omwscripts(folder) else root_name   # one owner per mod
        for x in sorted(os.listdir(folder)):
            move(os.path.join(folder, x), pname, x)
        moves.append((folder, None, "remove the emptied folder"))
    if legacy:
        moves.append((os.path.join(off, existing(off, "OpenMW")), None, "remove the emptied folder"))
    OWNER[mod_dir] = root_name
    mig = OL.plan_migration(mod_dir, root_name, taken=taken, skip_openmw=True)   # the rest of Off\\: its layouts
    if mig.notes:
        MIG_NOTES[mod_dir] = mig.notes
    return moves + mig.moves


def plan_mod(mod_dir):
    """[(source, destination, reason)] for one mod, or a str saying why it's left alone."""
    entries = os.listdir(mod_dir)
    low = {e.lower() for e in entries}
    if "data files" in low or any(os.path.splitext(e)[1].lower() in GAME_ROOT_EXT for e in entries
                                  if os.path.isfile(os.path.join(mod_dir, e))):
        return "installs into the game folder (exe/dll/Data Files at its root)"
    name = mod_name(os.path.basename(mod_dir))
    owner = OWNER[mod_dir] = OL.owner_name(mod_dir, fallback=name)      # <plugin> of Off\\<plugin>\\<reason>\\
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
    openmw = _spelled(off, owner, "OpenMW")           # Off\\<plugin>\\OpenMW\\
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
            move(os.path.join(mod_dir, old_openmw, x), os.path.join(openmw, x), "OpenMW-only -> Off\\<plugin>\\OpenMW\\")
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
                move(p, os.path.join(_spelled(off, owner, "normal maps"), rel), why)
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
    mig = OL.plan_migration(mod_dir, owner, taken=taken)          # older Off layouts -> Off\\<plugin>\\<reason>\\
    if mig.notes:
        MIG_NOTES[mod_dir] = mig.notes
    return moves + mig.moves


REVIEW = {}            # mod folder -> (its .omwaddon files, the OpenMW scripts that make it OpenMW-only)
CONVERTED = {}         # mod folder -> (its .omwaddon files, the omw2mwse-generated folders in it): left as they are
CONVERT = {}           # OpenMW-only mod folder -> its .omwscripts files: --apply hands it to omw2mwse
PREVIEW = {}           # converted-to-be mod folder -> (ok, summary line) of omw2mwse's dry run
PREVIEW_CHECK = {}     # converted-to-be mod folder -> {"digest", "identity", "lines"}: what --apply is bound to
BLOCKED_PLAN = []      # warning texts: mods omw2mwse's dry run judged blocked (they get the usual Off\\ move)
CONVERT_MODES = ("normal", "hardcode")          # omw2mwse's own --convert-omwscripts modes
CONVERT_DEFAULT = "normal"                      # what ships: end users get this unless they pass --convert-omwscripts=hardcode
_CONVERT_UNSET = object()                       # argparse: --convert-omwscripts was not given
CONVERT_ACTION = "convert with omw2mwse"
CONVERTER = {"mode": None, "cmd": None, "env": None, "why": "", "python": ""}   # set by main(): the mode, how to run it
CONVERTER_MIN_PYTHON = (3, 11)    # fallback when the converter declares no minimum (an older copy without pyproject or
                                  # requiresPython). Current omw2mwse declares 3.9+; these tools stay 3.9+.
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


def _version_of(text):
    """(major, minor) from "3.11", ">=3.11", "3.11+", ">=3.11.2,<4" ...; None when there is none."""
    m = re.search(r"(\d+)\.(\d+)", str(text or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def interpreter_version(cmd):
    """(major, minor) of the Python that `cmd` runs the converter with: this one when cmd starts with it, another
    python executable asked for its own version; None when it can't be known (an .exe/.cmd/.bat launcher)."""
    if not cmd:
        return None
    exe = cmd[0]
    if os.path.normcase(os.path.abspath(exe)) == os.path.normcase(os.path.abspath(sys.executable)):
        return tuple(sys.version_info[:2])
    if not os.path.basename(exe).lower().startswith(("python", "py.")) and os.path.basename(exe).lower() != "py":
        return None
    try:
        r = subprocess.run([exe, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return _version_of(r.stdout.decode("utf-8", "replace")) if r.returncode == 0 else None


def declared_python(where):
    """The minimum Python the converter declares: requires-python in a pyproject.toml in or above the folder
    `where` points into (up to three levels), else None. Current omw2mwse declares requires-python = ">=3.9"."""
    d = os.path.abspath(where) if where else ""
    d = d if os.path.isdir(d) else os.path.dirname(d)
    for _ in range(4):
        pp = os.path.join(d, "pyproject.toml")
        if d and os.path.isfile(pp):
            try:
                with open(pp, encoding="utf-8", errors="replace") as f:
                    m = re.search(r"^\s*requires-python\s*=\s*[\"']([^\"']+)[\"']", f.read(), re.M)
            except OSError:
                m = None
            if m and _version_of(m.group(1)):
                return _version_of(m.group(1))
        up = os.path.dirname(d)
        if up == d:
            break
        d = up
    return None


def converter_python_problem(cmd, where="", requires=None):
    """"" when the Python that would run the converter is new enough, else one sentence saying so. The minimum is
    what the converter declares (`requires`: the requiresPython field of its --json; else requires-python in its
    pyproject.toml), else CONVERTER_MIN_PYTHON. A launcher whose interpreter can't be told is not judged."""
    need = _version_of(requires) or declared_python(where) or CONVERTER_MIN_PYTHON
    have = interpreter_version(cmd)
    if have is None or have >= need:
        return ""
    return "omw2mwse needs Python %d.%d+, but it would run on Python %d.%d" % (need + have)


def convert_mode(chosen=_CONVERT_UNSET):
    """The omw2mwse mode tidy will run: `chosen` when it is one of CONVERT_MODES or None
    (--no-convert-omwscripts); when nothing was chosen, CONVERT_DEFAULT."""
    if chosen is not _CONVERT_UNSET:
        return chosen
    return CONVERT_DEFAULT


def setup_converter(mode):
    """main(): mode None (--no-convert-omwscripts) or one of CONVERT_MODES; finds the converter, and treats it as
    missing (CONVERTER["python"] says why) when the Python that would run it is too old."""
    CONVERTER.update(mode=mode, cmd=None, env=None, why="", python="")
    if mode:
        CONVERTER["cmd"], CONVERTER["env"], CONVERTER["why"] = find_converter()
        if CONVERTER["cmd"]:
            CONVERTER["python"] = converter_python_problem(CONVERTER["cmd"], CONVERTER["why"])
            if CONVERTER["python"]:
                CONVERTER["cmd"] = None


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


CONVERTER_INTERFACE = 1    # omw2mwse's tidy handoff (openmw-mwse docs/TIDY_INTERFACE.md, omw2mwse 0.3.1+)


def converter_target_problem(mod_dir):
    """Why omw2mwse must not be pointed at mod_dir ("" when it may): the pre-deploy rule (mwdialog_staged) - the
    converter only ever gets a staged mod folder, never Data Files or a game install, nor a folder inside one."""
    why = MS.write_root_problem(mod_dir, HERE, os.path.join(HERE, "Data Files"), mode="converter")
    if why:
        return why + " (the converter works on staged mod folders only)"
    d = os.path.realpath(mod_dir)
    while True:                                       # a loose master marks an install too
        if os.path.isfile(os.path.join(d, "Morrowind.esm")):
            return f"it is inside a game install or a Data Files folder ({d})"
        up = os.path.dirname(d)
        if up == d:
            return ""
        d = up


# ---- after the MWSE updater ----------------------------------------------------------------------------------------
# Our code never starts MWSE-Update.exe (MWManager does: mwmanager_mwse_core). A caller that ran it calls
# tidy_after_mwse_update() (or vortex_tidy.py --after-mwse-update EXIT_CODE --mwse-version-before TEXT) when it is
# done; tidy then runs only after a successful update. The rule (mwse_update_outcome):
#   * the updater did not start (exit code None) or exited non-zero  -> "failed": tidy is skipped;
#   * exit 0 but <game>\mwse-version.txt is missing or empty afterwards -> "failed" (nothing proves the update);
#   * exit 0 and mwse-version.txt is the same as before the updater ran -> "no-update": tidy is skipped;
#   * exit 0 and mwse-version.txt changed                                  -> "updated": only the MWSE core
#     patches are re-applied (luafix --core-only); no staged tidy run.
MWSE_VERSION_FILE = "mwse-version.txt"


def read_mwse_version(game_dir):
    """The build marker MWSE-Update.exe writes (<game>\\mwse-version.txt), stripped; "" when missing."""
    try:
        with open(os.path.join(game_dir, MWSE_VERSION_FILE), encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


def mwse_update_outcome(returncode, version_before, version_after):
    """("updated" | "failed" | "no-update", reason) for one run of MWSE-Update.exe (see the rule above)."""
    if returncode is None:
        return "failed", "the MWSE updater did not run"
    if returncode != 0:
        return "failed", f"the MWSE updater exited with code {returncode}"
    after, before = (version_after or "").strip(), (version_before or "").strip()
    if not after:
        return "failed", f"the MWSE updater exited 0 but {MWSE_VERSION_FILE} is missing or empty"
    if after == before:
        return "no-update", f"MWSE was already current ({after[:12]}): the updater changed nothing"
    return "updated", f"MWSE updated ({before[:12] or 'none'} -> {after[:12]})"


def morrowind_process_running():
    """True if Morrowind.exe appears to be running. Never tries to stop it."""
    if os.name != "nt":
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Morrowind.exe", "/NH"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return b"morrowind.exe" in (out or b"").lower()


def reapply_mwse_core(game_dir, log=print):
    """Dry-run first, then apply pending Known Bugs patches on Data Files\\MWSE\\core (luafix --core-only),
    with its usual backup and journal. Refuse (exit 2, nothing written) when Morrowind.exe is running.
    Writes under MWSE\\core are allowed (mwdialog_staged.allow_core_writes); every other Data Files write
    is still refused. Returns the luafix --core-only exit code (0 / 1 lock / 2 refused / 3 partial)."""
    if morrowind_process_running():
        log("Morrowind.exe is running; close it before MWSE core files are written. "
            "Nothing was killed and nothing was written.")
        return 2
    import mwdialog_luafix as lf
    try:
        game, data_dir = lf.core_data_dir(os.path.join(game_dir, "Data Files"))
    except ValueError as e:
        log(str(e))
        return 2
    if not (MP.acquire_run_lock() and MP.acquire_game_lock(game)):
        log(MP.RUN_LOCKED_MESSAGE)
        return 1
    checker = lf.find_checker(None, game)
    kw = dict(game_dir=game, checker=checker)
    with MS.staged_run([], game, data_dir):
        with MS.allow_core_writes():
            preview = lf.apply_core_known_bugs(data_dir, True, **kw)
            for line in lf.core_result_lines(preview, True):
                log(line)
            code = lf.core_exit_code(preview)
            if code:
                return code
            if not any(r.status == "applied" for r in preview):
                log("MWSE core patches already current; nothing written.")
                return 0
            results = lf.apply_core_known_bugs(data_dir, False, **kw)
            for line in lf.core_result_lines(results, False):
                log(line)
            return lf.core_exit_code(results)


def tidy_after_mwse_update(returncode, version_before, game_dir=None, log=print):
    """After the MWSE updater (mwse_update_outcome): on a successful update, re-apply only the MWSE core
    patches (reapply_mwse_core / luafix --core-only). No staged tidy, no converter, no other tidy function.
    On failure or no update, skip (exit 0, nothing written). Returns (outcome, reason, exit code or None
    when skipped)."""
    game = game_dir or HERE
    outcome, reason = mwse_update_outcome(returncode, version_before, read_mwse_version(game))
    if outcome != "updated":
        log(f"Tidy after the MWSE updater: skipped, {reason}.")
        return outcome, reason, None
    log(f"Tidy after the MWSE updater: {reason}; re-applying MWSE core patches (luafix --core-only).")
    return outcome, reason, reapply_mwse_core(game, log=log)


def converter_argv(mod_dir, mode, result_json, dry_run=False):
    """The omw2mwse call (TIDY_INTERFACE.md): --staged-root <staged mod> --result-json <temp file> [--dry-run],
    --mode, --accept-hardcode-conversions (tidy never prompts; --apply already asked) and --title/--author when
    Vortex has them. Never a Data Files path, never --no-runtime: the runtime is staged too."""
    argv = list(CONVERTER["cmd"]) + ["--staged-root", mod_dir, "--result-json", result_json, "--mode", mode]
    if mode == "hardcode":
        argv.append("--accept-hardcode-conversions")
    info = vortex_info(mod_dir)
    for opt in ("title", "author"):
        if info.get(opt):
            argv += ["--" + opt, info[opt]]
    if dry_run:
        argv.append("--dry-run")
    return argv


def converter_result(code, doc, mod_dir):
    """omw2mwse's result file (interface 1) in the shape the rest of tidy reads (its older --json output): (exit code,
    data). Exit 1 (blocked: nothing written) reads as a finished run whose mods are blocked, so tidy moves them to
    Off\\<plugin>\\OpenMW\\ itself; 2 is a conflict (4), hard-code conversions not accepted (3) or another failure (2);
    3 (refused target), 64 (usage) and 70 (internal) are errors. The interface's own lists ride along in each
    mod entry (written_files, removed_files, moved_files) for the --undo journal."""
    if not isinstance(doc, dict):
        return code, None
    errors = [e for e in doc.get("errors") or [] if isinstance(e, dict)]
    alerts = [{"level": "error", "code": e.get("code"), "message": e.get("message")} for e in errors]
    lists = {k: sorted(str(x) for x in doc.get(k) or []) for k in ("written_files", "removed_files", "moved_files")}
    mods = [m for m in doc.get("mods") or [] if isinstance(m, dict)]
    verdict = doc.get("verdict")
    if not mods and verdict in ("ready", "blocked"):
        mods = [{"name": package_name(mod_dir), "verdict": verdict, "blockers": doc.get("blockers") or [],
                 "excluded_by_author": doc.get("excluded_by_author")}]
    out_mods = []
    for m in mods:
        v = m.get("verdict") or verdict
        e = dict(m)
        e["verdict"] = v
        e["status"] = "ok" if v in ("ready", "blocked") else "error"
        bl = [str(x) for x in m.get("blockers") or (doc.get("blockers") if len(mods) == 1 else []) or []]
        e["alerts"] = [a for a in m.get("alerts") or [] if isinstance(a, dict)]      # any the converter adds
        seen = {a.get("message") for a in e["alerts"] if a.get("code") == "blocker"}
        e["alerts"] += [{"level": "error", "code": "blocker", "message": x} for x in bl if x not in seen]
        if m.get("excluded_by_author") or (len(mods) == 1 and doc.get("excluded_by_author")):
            e["reason"] = {"code": "author-opt-out"}      # never a file or a line (OPT_OUT_TEXT)
            e["alerts"] = []
        for k in ("written_files", "removed_files", "moved_files"):
            own = m.get(k)
            e[k] = sorted(str(x) for x in own) if isinstance(own, list) and len(mods) > 1 else lists[k]
        e["changed"] = bool(e["written_files"] or e["moved_files"] or e["removed_files"])
        e["relocated"] = list(e["moved_files"])
        if e["moved_files"] and "relocatedFrom" not in e:     # where the originals were: their common folder
            dirs = [p.split("/")[:-1] for p in e["moved_files"]]
            common = []
            for parts in zip(*dirs):
                if len(set(x.lower() for x in parts)) != 1:
                    break
                common.append(parts[0])
            e["relocatedFrom"] = "/".join(common)
        if not isinstance(e.get("plugins"), list):      # interface 1 lists no placements: read them off the plan
            e["planned_plugins"] = _planned_plugins(m.get("planned_files") or doc.get("planned_files") or [])
        out_mods.append(e)
    pending = doc.get("pendingRecovery") if isinstance(doc.get("pendingRecovery"), list) else []
    if code == 70 and not pending and recovery_journals(mod_dir):    # stopped part-way: its own journal says so
        pending = [{"mod": package_name(mod_dir), "stage": "internal error (exit 70)"}]
    data = {"tool": doc.get("tool"), "version": doc.get("version"), "interface": doc.get("interface"),
            "requiresPython": doc.get("requiresPython"), "dryRun": bool(doc.get("dry_run")),
            "changed": bool(lists["written_files"] or lists["moved_files"] or lists["removed_files"]),
            "verdict": verdict, "guards": doc.get("guards") or [], "runtime_version": doc.get("runtime_version"),
            "alerts": alerts, "mods": out_mods, "interfaceExit": code, "pendingRecovery": pending}
    data.update(lists)
    codes = {e.get("code") for e in errors}
    if code in (0, 1):
        return 0, data
    if code == 2:
        return (4 if "conflict" in codes else 3 if "hardcode-not-accepted" in codes else 2), data
    if code == 3 and not alerts:
        data["alerts"] = [{"level": "error", "code": "target-refused", "message": "omw2mwse refused the target"}]
    return (code if code not in (3, 4) else 2), data


def _planned_plugins(files):
    """[{name, placement, path, status, reason}] of the plugins (.esp/.esm) in a result's planned file list, outside
    Off/: at the staged root they are placement root, under Extras/ extras (interface 1 does not list placements)."""
    out = []
    for rel in sorted(str(x) for x in files or []):
        low = rel.lower()
        if not low.endswith((".esp", ".esm")) or low.startswith("off/"):
            continue
        place = "root" if "/" not in rel else ("extras" if low.startswith("extras/") else "subfolder")
        out.append({"name": rel.rsplit("/", 1)[-1], "placement": place, "path": rel, "status": "planned",
                    "reason": "from omw2mwse's planned files"})
    return out


def run_converter(mod_dir, mode, dry_run=False):
    """Run omw2mwse on one staged mod folder through its tidy interface (converter_argv) and read its result file
    (a temp file outside staging, Data Files and the game). (exit code, data in tidy's shape: converter_result,
    error text). Before a real run, every hard link in the mod folder is broken (mwdialog_staged.detach_tree), so
    nothing the converter writes there can reach Data Files."""
    why = converter_target_problem(mod_dir)
    if why:
        return None, None, f"not handed to omw2mwse: {why}"
    fd, result = tempfile.mkstemp(prefix="omw2mwse-result-", suffix=".json")
    os.close(fd)
    os.remove(result)                                 # omw2mwse writes it (atomically) itself
    try:
        if converter_target_problem(os.path.dirname(result)) or MS.in_staging(result) \
                or MP._is_under(result, os.path.abspath(mod_dir)):
            return None, None, f"no safe place for omw2mwse's result file ({result})"
        if not dry_run:
            MS.detach_tree(mod_dir)
        try:
            r = subprocess.run(converter_argv(mod_dir, mode, result, dry_run), stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env=CONVERTER["env"], timeout=CONVERTER_TIMEOUT)
        except (OSError, subprocess.SubprocessError) as e:
            return None, None, f"could not run omw2mwse ({e})"
        err = r.stderr.decode("utf-8", "replace").strip()
        doc = None
        try:
            with open(result, encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, ValueError):
            if "staged-root" in err or "unrecognized arguments" in err:
                err = "this omw2mwse is older than 0.3.1 (no --staged-root/--result-json): update the converter"
        code, data = converter_result(r.returncode, doc, mod_dir)
        return code, data, (err.splitlines()[-1] if err else "")
    finally:
        try:
            os.remove(result)
        except OSError:
            pass


def _converter_problem(data, err):
    """The first error/conflict message in a converter result, for a one-line warning."""
    for m in (data or {}).get("mods") or []:
        for c in m.get("conflicts") or []:
            return f"{c.get('path')}: {c.get('reason')}"
        if m.get("message"):
            return str(m["message"])
    for al in entry_alerts(data):
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
        blockers = sum(1 for al in entry_alerts(m) if al.get("code") == "blocker")
        b = f"{m.get('name')} {m.get('status')}, {readiness_text(m)}"
        if m.get("verdict") == "blocked" and not is_opt_out(m) and reason_text(m.get("reason")):
            b += f" ({reason_text(m.get('reason'))})"
        if blockers:
            b += f", {blockers} blocker(s)"
        if m.get("rewrites"):
            b += f", {len(m['rewrites'])} hard-coded value(s) as settings"
        bits.append(b)
    what = "; ".join(bits) or "nothing to convert"
    return True, what + ("" if data.get("dryRun") else (" (changed)" if data.get("changed") else " (unchanged)"))


def convert_lines(d, oms, mode, extra=()):
    """The plan lines of one OpenMW-only mod handed to the converter (actions --apply compares): the conversion,
    then (extra, from preview_check) the converter check digest, its hard-coded rewrites and plugin placements."""
    return [f"\n{d}   [{mod_name(d)}]",
            f"    {CONVERT_ACTION} ({mode}): OpenMW-only, no MWSE Lua ({', '.join(oms)})"] + list(extra)


# ---------------------------------------------------------------- binding --apply to the converter's preview
# The plan's conversion lines carry a digest of what the converter would do (its dry run's substantive JSON),
# of what it reads (every file of the mod folder, the mode, --title/--author) and of the converter itself (its
# version, path, the Python that runs it and the hashes of its files: the launcher, and for a checkout its
# package, runtime and sidecars). --apply works the plan out again, so a changed sidecar, source file or
# converter changes the digest line and the plan is refused (one REFUSED, nothing done); right before the real
# run the converter's own identity is checked once more. Volatile things (the absolute folder in the JSON, the
# "dir" and "dryRun" keys) are left out, so the same inputs always give the same digest.

CHECK_LABEL = "omw2mwse check"
_FP_SKIP_DIRS = {".git", "__pycache__", "tests", "docs", ".pytest_cache", ".ruff_cache", ".venv", "venv"}
_FP_CACHE = {}


def _converter_root(where):
    """The converter checkout `where` lies in (a folder up to three levels above it holding pyproject.toml and an
    omw2mwse package with cli.py within two levels), else None: a lone launcher or .exe is its own identity."""
    d = os.path.abspath(where) if where else ""
    d = d if os.path.isdir(d) else os.path.dirname(d)
    for _ in range(4):
        if d and os.path.isfile(os.path.join(d, "pyproject.toml")):
            for base, dirs, fns in os.walk(d):
                dirs[:] = [x for x in dirs if x not in _FP_SKIP_DIRS]
                if os.path.basename(base) == "omw2mwse" and "cli.py" in fns:
                    return d
                if base[len(d):].count(os.sep) >= 2:
                    dirs[:] = []
        up = os.path.dirname(d)
        if up == d:
            break
        d = up
    return None


def _files_digest(root, only=None):
    """SHA-256 over (relative path, content hash) of the files under root (or of the one file `only`), skipping
    VCS, caches, tests and docs (*.md): what the converter runs and reads, not what documents it."""
    h = hashlib.sha256()
    if only:
        h.update(b"file\0" + _sha256(only).encode())
        return h.hexdigest()
    for base, dirs, fns in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in _FP_SKIP_DIRS)
        for fn in sorted(fns):
            if fn.lower().endswith((".md", ".pyc", ".pyo")):
                continue
            p = os.path.join(base, fn)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            h.update(rel.encode("utf-8") + b"\0" + _sha256(p).encode() + b"\n")
    return h.hexdigest()


def converter_identity(cmd=None, where=None):
    """{"path", "python", "files"}: who would run the conversion. Cached per run (main() clears it)."""
    cmd = CONVERTER["cmd"] if cmd is None else cmd
    where = CONVERTER["why"] if where is None else where
    key = (tuple(cmd or ()), where)
    if key not in _FP_CACHE:
        root = _converter_root(where) if where else None
        try:
            if root:
                files = _files_digest(root)
            elif where and os.path.isdir(where):
                files = _files_digest(where)
            elif where and os.path.isfile(where):
                files = _files_digest(None, only=where)
            else:
                files = ""
        except OSError as e:
            files = f"unreadable: {e.__class__.__name__}"
        ver = interpreter_version(cmd) if cmd else None
        _FP_CACHE[key] = {"path": os.path.normcase(os.path.abspath(where)) if where else "",
                          "python": "%d.%d" % ver if ver else "", "files": files}
    return _FP_CACHE[key]


RECOVERY_DIR = ".omw2mwse-recovery"     # omw2mwse's own journal of an unfinished run: tidy never moves, sweeps or hashes it


def mod_inputs(mod_dir):
    """{relative path ('/'): SHA-256} of every file in a mod folder: what the converter reads (and, for the
    recovery intent, what the folder held before it ran). omw2mwse's recovery folder is left out."""
    out = {}
    for base, dirs, fns in os.walk(_xp(mod_dir)):
        dirs[:] = sorted(d for d in dirs if d.lower() != RECOVERY_DIR)
        for fn in fns:
            p = os.path.join(base, fn)
            out[os.path.relpath(_unxp(p), mod_dir).replace(os.sep, "/")] = _sha256(_unxp(p))
    return out


def _preview_substance(data, mod_dir):
    """The converter's dry-run JSON without what carries no meaning between two runs: the top-level "dir" and
    "dryRun", and the mod folder's absolute path inside any text (shown as <mod>); backslashes become '/'."""
    roots = {mod_dir, os.path.abspath(mod_dir), os.path.realpath(mod_dir)}
    variants = sorted({v for r in roots for v in (r, r.replace("\\", "/"), r.replace("/", "\\"))}, key=len,
                      reverse=True)

    def norm(x):
        if isinstance(x, dict):
            return {str(k): norm(v) for k, v in x.items()}
        if isinstance(x, list):
            return [norm(v) for v in x]
        if isinstance(x, str):
            for v in variants:
                if v:
                    x = re.sub(re.escape(v), "<mod>", x, flags=re.I)
            return x.replace("\\", "/")
        return x
    return norm({k: v for k, v in (data or {}).items() if k not in ("dir", "dryRun")})


def partial_api(entry, uses=False):
    """The partly implemented OpenMW APIs a converted mod uses, as "api xN" texts (uses: with its first use,
    "api xN (file:line)"): from the entry's "partialApis" (omw2mwse 64e2a6a: [{api, kind, count, uses: [{file,
    line}], missing}]), else "partialApi", else a "symbols" map ({name: {"status": "partial", "count"}}).
    Always [] for an author opt-out: nothing about such a mod's files is ever shown."""
    entry = entry if isinstance(entry, dict) else {}
    out = []
    if is_opt_out(entry):
        return out
    got = entry.get("partialApis") if isinstance(entry.get("partialApis"), list) else entry.get("partialApi")
    if isinstance(got, list):
        for x in got:
            if isinstance(x, dict) and (x.get("api") or x.get("symbol") or x.get("name")):
                n = x.get("count")
                t = str(x.get("api") or x.get("symbol") or x.get("name")) + (f" x{n}" if isinstance(n, int) and n > 1
                                                                            else "")
                first = [u for u in (x.get("uses") or []) if isinstance(u, dict) and u.get("file")][:1]
                if uses and first:
                    t += f" ({str(first[0]['file']).replace(chr(92), '/')}:{first[0].get('line', '?')})"
                out.append(t)
            elif isinstance(x, str) and x:
                out.append(x)
    elif isinstance(entry.get("symbols"), dict):
        for name, e in sorted(entry["symbols"].items()):
            if isinstance(e, dict) and e.get("status") == "partial":
                n = e.get("count")
                out.append(str(name) + (f" x{n}" if isinstance(n, int) and n > 1 else ""))
    return out


def readiness_text(entry):
    """'verdict <v>' with its partial API matches beside it (so a tester knows what to try), e.g. 'verdict ready
    (partial API: openmw.ui.showMessage x2, openmw.nearby.castRay)'."""
    v = f"verdict {entry.get('verdict')}"
    part = partial_api(entry)
    return v + (f" (partial API: {', '.join(part[:8])}" + (f", +{len(part) - 8} more" if len(part) > 8 else "")
                + ")" if part else "")


def preview_lines(data, mod_dir):
    """The reviewable lines of a converter preview, one per hard-coded rewrite and per plugin placement."""
    out = []
    for m in (data or {}).get("mods") or []:
        if not isinstance(m, dict) or m.get("status") != "ok":
            continue
        mname = m.get("name")
        for r in m.get("rewrites") or []:
            if isinstance(r, dict):
                where = f"{str(r.get('file') or '?').replace(os.sep, '/')}:{r.get('line', '?')}"
                out.append(f"    omw2mwse makes a setting of {mname}'s hard-coded value: {where} "
                           f"{r.get('name') or r.get('key') or '?'} = {r.get('literal', r.get('default', '?'))}")
        for pl in converter_plugins(m) or m.get("planned_plugins") or []:
            place = str(pl.get("placement") or ("off" if pl.get("optional") is True else "root"))
            path = str(pl.get("path") or pl["name"]).replace("\\", "/")
            out.append(f"    omw2mwse places {mname}'s plugin {pl['name']}: {place} ({pl.get('status') or 'unknown'}) "
                       f"at {path}")
    return out


def preview_check(data, mod_dir, mode):
    """{"digest", "identity", "lines"} for a converter preview: the digest --apply is bound to (see above) and
    the plan lines that carry it."""
    info = vortex_info(mod_dir)
    ident = converter_identity()
    body = {"mode": mode, "title": info.get("title") or "", "author": info.get("author") or "",
            "converter": dict(ident, version=str((data or {}).get("version") or "")),
            "inputs": mod_inputs(mod_dir), "preview": _preview_substance(data, mod_dir)}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    ver = (data or {}).get("version") or "?"
    lines = [f"    {CHECK_LABEL} {digest} (omw2mwse {ver}: its preview, the mod's files and the converter's own)"]
    return {"digest": digest, "identity": ident, "lines": lines + preview_lines(data, mod_dir)}


CHECK_REFUSED = ("The OpenMW converter's preview, the files it reads (a sidecar or a source file) or the converter "
                 "itself (a different version or copy) changed since the plan you reviewed")


# ---------------------------------------------------------------- recovery intent for a conversion
# Before omw2mwse writes anything, --apply records an intent (vortex_tidy_journal_intent.json beside the journal,
# flushed to disk): the mod folder, every file it holds with its SHA-256, its folders, the start time, and a
# hash-checked copy (in <backups folder>\tidy\<run>\convert\) of every existing file the converter's preview
# says it will overwrite or remove. When the converter returns and its undo record is journaled (or a blocked
# result undone), the intent is removed. An intent still there means the run stopped in between: the next
# --apply or --undo puts the folder back as the intent recorded it (kept copies restored, relocated originals
# moved back by hash, files that appeared since removed, new folders removed) and the plan says so. If that can't
# be done exactly, nothing is changed and the intent stays, with the reasons.

def _intent_path():
    return os.path.splitext(JOURNAL)[0] + "_intent.json"


def read_intent():
    try:
        with open(_intent_path(), encoding="utf-8") as f:
            got = json.load(f)
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) and got.get("mod") else None


def _write_intent(intent):
    p = _intent_path()
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(intent, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def _clear_intent():
    try:
        os.remove(_intent_path())
    except FileNotFoundError:
        pass


def begin_intent(mod_dir, staging, mode, preview, audit):
    """Record the intent of one conversion (see above) before the converter runs; returns it."""
    files = mod_inputs(mod_dir)
    dirs = []
    for base, ds, _fns in os.walk(_xp(mod_dir)):
        ds[:] = [d for d in ds if d.lower() != RECOVERY_DIR]
        dirs += [os.path.relpath(_unxp(os.path.join(base, d)), mod_dir).replace(os.sep, "/") for d in ds]
    planned = set()                                   # what it may overwrite or remove: its planned outputs,
    for m in (preview or {}).get("mods") or []:       # the MAX_PATH list beside its Off package, earlier output
        if isinstance(m, dict):
            planned |= {str(k).replace("\\", "/") for k in (m.get("files") or {})}
            off = str(m.get("off") or m.get("willRelocateTo") or m.get("source") or "").replace("\\", "/").strip("/")
            if off:
                planned.add(posixpath.join(posixpath.dirname(off), OL.LIST_NAME))
    for g in omw_converted(mod_dir):
        g = g.replace(os.sep, "/").rstrip("/") + "/"
        planned |= {k for k in files if k.lower().startswith(g.lower())}
    low = {k.lower(): k for k in files}
    kept = {}
    stamp = f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-{time.time_ns()}"
    keep_dir = os.path.join(audit or os.path.join(AUDIT_ROOT, stamp), "convert", os.path.basename(mod_dir))
    for rel in sorted(planned):
        rel = os.path.normpath(rel).replace(os.sep, "/")
        have = low.get(rel.lower())
        if not have:
            continue
        dst = os.path.join(keep_dir, *have.split("/"))
        os.makedirs(_xp(os.path.dirname(dst)), exist_ok=True)
        shutil.copyfile(_xp(os.path.join(mod_dir, *have.split("/"))), _xp(dst))
        if _sha256(dst) != files[have]:
            raise OSError(f"the kept copy of {have} did not hash-check")
        kept[have] = dst
    intent = {"intent": stamp, "mod": mod_dir, "staging": staging, "mode": mode, "started": time.time(),
              "files": files, "dirs": sorted(dirs), "kept": kept}
    _write_intent(intent)
    return intent


def _journal_has_intent(iid):
    try:
        with open(JOURNAL, encoding="utf-8") as f:
            return any(iid in ln and json.loads(ln).get("intent") == iid for ln in f if ln.strip())
    except (OSError, ValueError):
        return False


def reconcile_intent(intent, log=print, quiet=False):
    """Put a mod folder back as a pending intent recorded it (see above). True when done (the intent is
    removed); False when it can't be done exactly (nothing changed, the intent stays, the reasons printed).
    quiet: say nothing when the folder already is as recorded (the end of every conversion that journaled
    nothing)."""
    mod, iid = intent["mod"], intent.get("intent")
    name = os.path.basename(mod)
    if iid and _journal_has_intent(iid):              # the converter finished and its undo record is journaled
        _clear_intent()
        return True
    if os.path.isdir(mod) and recovery_journals(mod):   # the converter's own record first: it undoes its run
        ok, text = converter_rollback(mod)
        if text:
            log(f"{'  ' if quiet else ''}{'' if ok else 'WARNING: '}{name}: {text}")
    was, kept = intent.get("files") or {}, intent.get("kept") or {}
    now = mod_inputs(mod) if os.path.isdir(mod) else {}
    new = {r: h for r, h in now.items() if r not in was}
    restore, back, problems = [], [], []
    for rel, h in sorted(was.items()):
        cur = now.get(rel)
        if cur == h:
            continue
        if rel in kept:
            if not os.path.isfile(_xp(kept[rel])) or _sha256(kept[rel]) != h:
                problems.append(f"{rel}: its kept copy ({kept[rel]}) is missing or not the original")
            else:
                restore.append((kept[rel], rel))
            continue
        if cur is None:
            cands = sorted((r for r, x in new.items() if x == h), key=lambda r: (not r.lower().endswith("/" + rel.lower()), r))
            if cands:
                back.append((cands[0], rel))
                del new[cands[0]]
                continue
            problems.append(f"{rel}: gone, and no copy with its content is in the folder")
        else:
            problems.append(f"{rel}: changed, and no original was kept")
    stale = [r for r in new if os.path.getmtime(_xp(os.path.join(mod, *r.split("/")))) < intent.get("started", 0) - 2]
    for r in stale:
        problems.append(f"{r}: not there before the conversion, but older than it (not removed by tidy)")
    if problems:
        ind = "  " if quiet else ""
        log(f"{ind}WARNING: {name} could not be put back exactly as it was before omw2mwse ran; nothing was "
            f"changed and the recovery record stays ({_intent_path()}):")
        for p in problems[:20]:
            log(f"{ind}  {p}")
        return False
    for src, rel in back:
        dst = os.path.join(mod, *rel.split("/"))
        os.makedirs(_xp(os.path.dirname(dst)), exist_ok=True)
        os.replace(_xp(os.path.join(mod, *src.split("/"))), _xp(dst))
    for src, rel in restore:
        dst = os.path.join(mod, *rel.split("/"))
        os.makedirs(_xp(os.path.dirname(dst)), exist_ok=True)
        tmp = dst + ".tidytmp"
        shutil.copyfile(_xp(src), _xp(tmp))
        os.replace(_xp(tmp), _xp(dst))
    for rel in new:
        try:
            os.remove(_xp(os.path.join(mod, *rel.split("/"))))
        except FileNotFoundError:
            pass
    keep_dirs = {d.lower() for d in intent.get("dirs") or []}
    for base, ds, fns in os.walk(_xp(mod), topdown=False):
        rel = os.path.relpath(_unxp(base), mod).replace(os.sep, "/")
        if RECOVERY_DIR in rel.lower().split("/"):
            continue
        if rel != "." and rel.lower() not in keep_dirs and not os.listdir(base):
            os.rmdir(base)
    if recovery_journals(mod):
        log(f"{'  ' if quiet else ''}NOTE: {name}: omw2mwse's record of an unfinished run is still in "
            f"{', '.join(recovery_journals(mod))}; tidy leaves it alone (omw2mwse recover --rollback undoes it)")
    _clear_intent()
    if back or restore or new or not quiet:
        log(f"{'  ' if quiet else ''}{name}: put back as it was before omw2mwse ran: {len(back)} original(s) moved "
            f"back, {len(restore)} kept file(s) restored, {len(new)} file(s) it had written removed.")
    return True


def recovery_journals(mod_dir):
    """omw2mwse's journals of unfinished runs in a mod folder ('/'-relative paths): <MWSE>/mods/mwsuite/openmw/
    <Mod>/.omw2mwse-recovery/journal.json. Read-only: tidy never moves, sweeps or hashes that folder."""
    out = []
    base = os.path.join(mod_dir, existing(mod_dir, "MWSE"), "mods", "mwsuite", "openmw")
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return out
    for n in names:
        j = os.path.join(base, n, RECOVERY_DIR, "journal.json")
        if os.path.isfile(j):
            out.append(os.path.relpath(j, mod_dir).replace(os.sep, "/"))
    return out


def pending_recovery(data):
    """The unfinished omw2mwse runs a convert result reports (top-level "pendingRecovery": [{mod, stage, ...}])."""
    got = (data or {}).get("pendingRecovery") if isinstance(data, dict) else None
    return [x for x in got if isinstance(x, dict)] if isinstance(got, list) else []


def converter_rollback(mod_dir):
    """omw2mwse recover <mod> --rollback --json: the converter undoes its own unfinished runs from its recovery
    journal (originals back from Off, created files deleted, replaced ones restored from its backup). (ok, text).
    Nothing to do (no journal) is ok; no converter is not."""
    if not recovery_journals(mod_dir):
        return True, ""
    if not CONVERTER.get("cmd"):
        return False, "omw2mwse is not available to roll back its unfinished run"
    try:
        r = subprocess.run(list(CONVERTER["cmd"]) + ["recover", mod_dir, "--rollback", "--json"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=CONVERTER["env"],
                           timeout=CONVERTER_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"could not run omw2mwse recover ({e})"
    try:
        data = json.loads(r.stdout.decode("utf-8", "replace"))
    except ValueError:
        data = {}
    kept = [k for rb in (data.get("rolledBack") or []) if isinstance(rb, dict) for k in (rb.get("kept") or [])]
    if r.returncode or recovery_journals(mod_dir):
        return False, f"omw2mwse recover --rollback did not finish (exit {r.returncode})"
    return True, ("omw2mwse rolled back its unfinished run" + (f"; it kept {len(kept)} file(s) changed by hand"
                                                                 if kept else ""))


def pending_intent_line():
    """The plan's WARNING for a pending intent, or ""."""
    it = read_intent()
    if not it:
        return ""
    return (f"WARNING: an omw2mwse conversion of {os.path.basename(it['mod'])} was interrupted; --apply (or --undo) "
            f"first puts that folder back as it was, then stops so you can plan again")


def entry_alerts(entry):
    """The alerts of a converter result entry that are dicts (anything else in the list is ignored)."""
    got = entry.get("alerts") if isinstance(entry, dict) else None
    return [al for al in got if isinstance(al, dict)] if isinstance(got, list) else []


def reason_text(reason):
    """One short text for an entry's "reason": a dict {code, file, line, message} (author-opt-out, 8367f55) as
    'code at file:line', a plain string as it is, anything else shortened; "" when there is nothing. Never raises
    (any key may be missing or of any type)."""
    try:
        if isinstance(reason, dict):
            code, file_, line = reason.get("code"), reason.get("file"), reason.get("line")
            bits = []
            if code not in (None, ""):
                bits.append(str(code))
            if file_ not in (None, ""):
                bits.append("at " + str(file_) + (f":{line}" if line not in (None, "") else ""))
            elif line not in (None, ""):
                bits.append(f"at line {line}")
            if not bits and reason.get("message") not in (None, ""):
                bits.append(str(reason["message"]))
            return " ".join(bits)[:300]
        if reason is None or reason == "" or reason == [] or reason == {}:
            return ""
        return str(reason).strip()[:300]
    except Exception:                                # a reason of a shape nobody expects must not stop tidy
        return ""


OPT_OUT_TEXT = ("the original mod author has asked that this mod be excluded from mwsuite's conversion utility; "
                "contact the original mod author for details")


def is_opt_out(entry):
    """A converter entry whose mod author asked to be left out of conversion (reason.code "author-opt-out")."""
    r = entry.get("reason") if isinstance(entry, dict) else None
    return isinstance(r, dict) and r.get("code") == "author-opt-out"


def blocked_reason(entry):
    """For a converter result entry with verdict "blocked": its "reason" (a dict is shown as 'code at file:line'),
    and 'N blocker(s), first: <message>' when it has blocker alerts; 'no reason given' when it has neither. An
    author's request to be left out of conversion is only ever shown in plain words (OPT_OUT_TEXT): never the
    converter's code, file, line or message, so nobody is pointed at where to edit it."""
    entry = entry if isinstance(entry, dict) else {}
    if is_opt_out(entry):
        return OPT_OUT_TEXT
    parts = []
    why = reason_text(entry.get("reason"))
    if why:
        parts.append(why)
    bl = [al for al in entry_alerts(entry) if al.get("code") == "blocker"]
    if bl:
        parts.append(f"{len(bl)} blocker(s), first: {bl[0].get('message')}")
    return "; ".join(parts) or "no reason given"


def blocked_says(mname, entry):
    """The start of the one WARNING line about a blocked mod."""
    if is_opt_out(entry):
        return f"{mname}: {OPT_OUT_TEXT}"
    return f"omw2mwse says {mname} cannot run ({blocked_reason(entry)})"


def blocked_then(entry):
    """What joins the start of that line to 'not converted, ...'."""
    return "; " if is_opt_out(entry) else ": "


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
    files = _manifest_files(os.path.join(mod_dir, *(tree.split("/") + [MP.OMW_MANIFEST]))) or {}
    written = [str(x) for x in entry.get("written_files") or []]
    for rel in written:                              # the interface's own list (omw2mwse 0.3.1+): what it wrote
        p = _inside(mod_dir, rel)
        if p and rel not in files and os.path.isfile(p):
            files[rel] = _sha256(p)
    op = {"omw_convert": mod_dir, "name": name, "mode": mode, "from": frm, "off": off, "tree": tree,
          "relocated": sorted(entry.get("relocated") or []), "files": files}
    if "written_files" in entry:
        op.update(written=sorted(written), removed=sorted(str(x) for x in entry.get("removed_files") or []),
                  moved=sorted(str(x) for x in entry.get("moved_files") or []))
    return op


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


def convert_apply(staging, mods, mode, head_extra=None, audit=None):
    """--apply: run the converter on each OpenMW-only mod and journal what it changed (for --undo). A conflict
    (exit 4) or any other failure gets one WARNING line and the run goes on. A mod omw2mwse judges blocked
    (verdict "blocked": it exits 0 and still writes an active loader) is not shipped: its output is undone at
    once and its whole package goes to Off\\<plugin name>\\OpenMW\\, with one WARNING line; "partial" is converted,
    with one NOTE. Returns the mod folders not converted."""
    left = []
    for i, mod_dir in enumerate(mods):
        name = os.path.basename(mod_dir)
        bound = PREVIEW_CHECK.get(mod_dir)
        _FP_CACHE.clear()
        if bound and converter_identity() != bound["identity"]:      # the converter changed during this run
            print(f"  WARNING: {name}: {CHECK_REFUSED}; not converted, nothing was written for it")
            left.append(mod_dir)
            continue
        try:
            intent = begin_intent(mod_dir, staging, mode, bound and bound.get("data"), audit)
        except OSError as e:
            print(f"  WARNING: {name}: could not record the recovery intent ({e}); not converted")
            left.append(mod_dir)
            continue
        code, data, err = run_converter(mod_dir, mode)
        ok, line = converter_summary(code, data, err)
        if pending_recovery(data):                   # it stopped part-way and says so: not a finished conversion
            ok, line = False, (f"an unfinished run is pending ({', '.join(str(x.get('mod')) for x in pending_recovery(data))}"
                               f", stage {pending_recovery(data)[0].get('stage')})")
            data = None
        ops, blocked, notes = [], [], []
        verdicts = preview_verdicts(data)
        touched = bool(verdicts) and mod_inputs(mod_dir) != intent["files"]   # the folder says what was written too
        for mname, verdict, m in verdicts:
            if data.get("dryRun"):
                continue
            wrote = bool(m.get("changed") or m.get("relocated")) or (touched and len(verdicts) == 1)
            if verdict == "blocked":                  # also when nothing was written (an author opt-out writes nothing)
                blocked.append((mname, conversion_op(mod_dir, m, mode) if wrote else None, blocked_says(mname, m), m))
                continue
            if not wrote:
                continue
            op = conversion_op(mod_dir, m, mode)
            op["intent"] = intent["intent"]
            ops.append(op)
            if verdict == "partial":
                notes.append(f"{mname} is only partly supported by omw2mwse (verdict partial): converted anyway")
            if isinstance(m.get("resumed"), dict):
                notes.append(f"{mname}: omw2mwse finished an earlier run that had stopped at stage "
                             f"{m['resumed'].get('stage')}")
            for al in entry_alerts(m):
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
            _clear_intent()                          # the journal is the record now (--undo reverses it)
        state = {"open": not ops}

        def settle():
            """Nothing journaled: the folder must be as the intent recorded it (a failed or crashed run may have
            left files; a blocked one is undone by its own record first). True when it is."""
            if state["open"]:
                state["open"] = not reconcile_intent(intent, quiet=True)
            return not state["open"]
        if ok and verdicts and all(v == "blocked" for _n, v, _m in verdicts):
            pass                                     # nothing was converted: the WARNING below says so
        elif ok:
            print(f"  converted {name} with omw2mwse ({mode}): {line}")
        elif not settle():
            print(f"  WARNING: omw2mwse could not convert {name}: {line}; what it wrote could not be put back")
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
        for mname, op, says, m in blocked:
            if (op is None or _undo_now(op, staging)) and settle():   # no op: the converter wrote nothing
                print(f"  WARNING: {says}{blocked_then(m)}not converted, "
                      + ("conversion undone, " if op is not None else "nothing was written, ")
                      + "its whole package goes to Off\\<plugin>\\OpenMW\\")
                for al in entry_alerts(m):
                    if al.get("code") == "previous-output-present":
                        print(f"  NOTE: {mname}: output of an earlier conversion is still there; tidy leaves it as it is")
                moves = unconverted_moves(mod_dir)
                if moves:
                    apply(moves, staging, None, head_extra)
            else:
                print(f"  WARNING: {says}, and its output could not be undone")
                left.append(mod_dir)
        if not settle():                             # the intent stays for the next --apply or --undo
            print(f"  WARNING: stopped converting: {name} could not be put back as it was before omw2mwse ran "
                  f"(listed above); the next --apply or --undo tries again")
            left += [d for d in mods[i:] if d not in left]
            break
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
        elif src == dst:                                   # a max_path_too_long.txt list
            out.append(f"    {'write' if why.startswith('write') else 'remove'}  {rs}   ({why})")
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
    OWNER.clear()
    MIG_NOTES.clear()
    LIST_TEXT.clear()
    CONVERTED.clear()
    CONVERT.clear()
    _VORTEX_INFO.clear()
    PREVIEW.clear()
    PREVIEW_CHECK.clear()
    _FP_CACHE.clear()
    del BLOCKED_PLAN[:]
    CONVERTER["missed"] = 0
    _TEX_INDEX.clear()
    pats = blacklist() + (args.skip or [])
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
            late = converter_python_problem(CONVERTER["cmd"], CONVERTER["why"], (data or {}).get("requiresPython"))
            if late:                                 # the converter says what it needs (a newer omw2mwse): as missing
                CONVERTER["python"], CONVERTER["cmd"] = late, None
                CONVERTER["missed"] = CONVERTER.get("missed", 0) + 1
                del CONVERT[full]
                res = unconverted_moves(full)
                data = None
            if pending_recovery(data) or recovery_journals(full):
                NOTES.append(f"{d}: omw2mwse has an unfinished run here; --apply runs it again, which finishes it "
                             f"(if that fails too, omw2mwse rolls it back and tidy puts the folder back as it was)")
            blocked = [(n, blocked_says(n, m), blocked_then(m)) for n, v, m in preview_verdicts(data) if v == "blocked"]
            if late:
                pass
            elif blocked:                              # omw2mwse would write an active loader that can't work
                del CONVERT[full]
                BLOCKED_PLAN.append(f"{d}: {blocked[0][1]}{blocked[0][2]}not converted, "
                                    f"its whole package goes to Off\\<plugin>\\OpenMW\\")
                res = unconverted_moves(full)
            else:
                PREVIEW[full] = converter_summary(code, data, err)
                for n, v, m_ in preview_verdicts(data):
                    if v == "partial":
                        NOTES.append(f"{d}: omw2mwse verdict partial for {n}: it will be converted, only partly "
                                     f"supported")
                    if partial_api(m_):
                        NOTES.append(f"{d}: {n} uses OpenMW API that omwcompat only partly supports - test these in "
                                     f"game first: {', '.join(partial_api(m_, uses=True)[:12])}")
                chk = preview_check(data, full, CONVERTER["mode"]) if data is not None else None
                if chk:
                    chk["data"] = data
                    PREVIEW_CHECK[full] = chk
                touched += 1
                lines += convert_lines(d, CONVERT[full], CONVERTER["mode"], chk["lines"] if chk else ())
                continue
        res, too_long = OL.guard_moves(res, full)    # a path over MAX_PATH is never moved (it would get longer)
        listed = OL.list_update(full, OWNER.get(full) or OL.owner_name(full, fallback=mod_name(d)), too_long)
        if listed:
            LIST_TEXT[os.path.normcase(listed[0])] = listed[1]
            res = res + [(listed[0], listed[0], (LIST_WRITE % (sum(1 for ln in listed[1].splitlines() if ln), OL.MAX_PATH_CHARS))
                          if listed[1] else LIST_REMOVE)]
        if too_long:
            NOTES.append(f"{d}: {len(too_long)} file(s) not moved because their path is already too long (or the new "
                         f"one would be); they are listed in Off\\{OWNER.get(full, '<plugin>')}\\{OL.LIST_NAME}")
        for note in MIG_NOTES.pop(full, []):
            NOTES.append(f"{d}: {note}")
        if not res:
            continue
        touched += 1
        lines += move_lines(d, res, args.staging)
        all_moves += res
    head = [f"vortex_tidy plan, {time.strftime('%Y-%m-%d %H:%M')}: {len(mods)} mod(s), {touched} to change, "
            f"{sum(1 for m in all_moves if m[1])} move(s); {len(skipped)} left alone"]
    for d, why in skipped:
        head.append(f"  - left alone: {d} ({why})")
    if CONVERTER.get("missed") and CONVERTER.get("python"):    # one line: the converter can't run here
        head.append(f"  - WARNING: {CONVERTER['python']}, so it is not used: "
                    f"{CONVERTER['missed']} OpenMW-only mod(s) get their whole package moved to Off\\<plugin>\\OpenMW\\ instead")
    elif CONVERTER.get("missed"):                    # one line: the converter isn't there
        head.append(f"  - NOTE: {CONVERTER['missed']} OpenMW-only mod(s) get their whole package moved to "
                    f"Off\\<plugin>\\OpenMW\\: they need the optional OpenMW-to-MWSE converter, still in "
                    f"development and not installed. Every run looks at them again.")
    pend = pending_intent_line()
    if pend:
        head.append(f"  - {pend}")
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


def _read_text(path):
    try:
        with open(_xp(path), encoding="utf-8", newline="") as f:
            return f.read()
    except OSError:
        return None


def _put_text(path, text):
    """Make `path` hold `text` (None: remove it); the text's lines end the way Windows' do."""
    if text is None:
        try:
            os.remove(_xp(path))
        except FileNotFoundError:
            pass
        return
    os.makedirs(_xp(os.path.dirname(path)), exist_ok=True)
    with open(_xp(path), "w", encoding="utf-8", newline="") as f:
        f.write(text.replace("\r\n", "\n").replace("\n", "\r\n"))


def _write_list(j, path, progress, i):
    """Write (or remove) a max_path_too_long.txt, journaled first with what was there before."""
    after = LIST_TEXT.get(os.path.normcase(path))
    before = _read_text(path)
    j.write(json.dumps({"write": path, "before": before, "after": None if after is None else
                        after.replace("\n", "\r\n")}) + "\n")
    j.flush()
    os.fsync(j.fileno())
    _put_text(path, after)
    if progress is not None:
        progress.append(i)


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
                if src == dst:                                   # a max_path_too_long.txt list (written or removed)
                    _write_list(j, src, progress, i)
                    done += 1
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
    print(f"Moved {done} item(s). Journal: {JOURNAL} (--undo puts them back). Now Deploy in Vortex: it takes the moved files out of the game.")
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
    pend = read_intent()
    if pend and not reconcile_intent(pend):           # an interrupted conversion first: it was the last thing done
        print("--undo changed nothing else: the interrupted conversion above has to be put back first.",
              file=sys.stderr)
        return 1
    if not os.path.exists(JOURNAL):
        print("Nothing to undo (no journal)." if not pend else "Nothing else to undo (no journal).")
        return 1 if not pend else 0
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
            if "write" in op:                         # a max_path_too_long.txt: back to what it was (or removed)
                cur = _read_text(op["write"])
                if cur != op.get("after") and not force:
                    print(f"  not put back (changed since vortex_tidy wrote it; --undo --force overwrites): "
                          f"{op['write']}", file=sys.stderr)
                    left.append(op)
                    continue
                try:
                    _put_text(op["write"], op.get("before"))
                    back += 1
                except OSError as e:
                    print(f"  could not put back {op['write']}: {e}", file=sys.stderr)
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
        for d in {os.path.dirname(op["dst"] if "dst" in op else op["write"]) for op in r["ops"]
                  if "dst" in op or "write" in op} if top else ():   # emptied folders
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


def converted_elsewhere(staging, names, data_files=None):
    """True when a converted mod (its MWSE\\mods folder holds omw2mwse output) is left in any mod folder of
    staging. Data Files is not looked at before deploy (mwdialog_staged): data_files is only scanned when given
    (a deploy-time caller), for converted mods other than a deployed copy of one of `names`."""
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
    if not data_files:
        return False
    dm = os.path.join(data_files, "MWSE", "mods")
    return os.path.isdir(dm) and scan(dm, names)


def finish_conversions(cstate):
    """--undo, after every conversion of the run: the shared runtime (MWSE\\lib\\omwcompat*) goes from the mods
    it was deferred in, unless a converted mod is left in staging (Data Files is not read before deploy)."""
    if not cstate["defer"]:
        return
    if converted_elsewhere(cstate["staging"], cstate["names"]):
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
    if os.path.isfile(_xp(path)) and MS.must_replace(path):    # before deploy: a new file, never through a link
        MS.replace_bytes(_xp(path), data)
    elif os.path.isfile(_xp(path)):
        with open(_xp(path), "r+b") as f:             # in place (outside a staged run)
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
    # staged files only before deploy (mwdialog_staged): luafix looks things up in the staged mods and in the
    # suite's lua tools (what --play deploys), never in Data Files (except the documented read-only exceptions)
    data_dir = MS.StagedData(args.staging, game_dir, extra=(MP.LUA_TOOLS_DIR,))
    mods = sorted(d for d in os.listdir(args.staging) if os.path.isdir(os.path.join(args.staging, d))
                  and d.lower() != "off")
    if args.only:
        mods = [d for d in mods if any(fnmatch.fnmatch(d.lower(), pat.lower()) for pat in args.only)]
    pats = blacklist() + (args.skip or [])
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
    # MWSE's own core files a Known Bugs rule names (KB3, KB4: the MCM's ExclusionsPage) are checked and patched
    # here only when a staged mod ships MWSE itself (that mod's copy was checked above). MWSE's updater puts them
    # straight into Data Files, and nothing in Data Files is touched before deploy (mwdialog_staged): that copy
    # is left to the deploy step (mwdialog_luafix.py --core-only), and the plan says so.
    if os.path.isdir(os.path.join(data_dir.data_dir or "", "MWSE")):
        print("  MWSE core in Data Files: not checked or patched before deploy (KB3/KB4 core repairs are done at "
              "deploy: mwdialog_luafix.py --core-only)")
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
    """The files whose text says what the game uses: Morrowind.ini, the base game's masters it loads (Morrowind,
    Tribunal, Bloodmoon .esm: a read-only exception, mwdialog_staged) and every staged mod's plugins (which may be
    active once deployed). No other plugin in Data Files is read before deploy."""
    data = _data_dir()
    out = [os.path.join(HERE, "Morrowind.ini")]
    names = _ini_plugins(HERE)
    if names is None:
        names = ["Morrowind.esm", "Tribunal.esm", "Bloodmoon.esm"]
    out += [os.path.join(data, n) for n in names if n.lower() in MS.CORE_MASTERS]
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
    out = {}
    for base in OL.reason_dirs(root, "broken"):          # Off\\<plugin>\\broken (and the older Off\\broken\\<plugin>)
        for dp, _ds, fns in os.walk(_xp(base)):
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
    another staged mod or in a BSA (staged, or the base game's). Data Files' loose files are not looked at."""
    k = _rk(rel)
    if k.startswith("meshes\\") and bsa_meshes and k[7:] in {x.lower() for x in bsa_meshes}:
        return True
    mine = os.path.join(root, rel)
    staging = os.path.dirname(os.path.abspath(root))
    places = [os.path.join(staging, d) for d in (os.listdir(staging) if os.path.isdir(staging) else ())
              if os.path.normcase(d) != os.path.normcase(os.path.basename(os.path.abspath(root)))]
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
    """Put each broken file's original in <mod>\\Off\\<plugin>\\broken\\<path> (a different file there already: a
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
        lp_issues, lp_plan = m.longpaths_module().check_mod(root, MS.data_path_of(data_dir)
                                                            or os.path.join(game_dir, "Data Files"), m, game_dir)
        issues = lp_issues + issues
    except Exception as e:
        print(f"  {os.path.basename(root)}: long-path check failed ({e})")
    return {"issues": issues, "fixes": fixes, "lp_plan": lp_plan}


def _bsa_meshes(m, data_dir):
    """Paths under meshes\\ in the BSAs: a StagedData's (staged BSAs, then the base game's), else every BSA in a
    plain Data Files folder (a deploy-time caller)."""
    out = set()
    if isinstance(data_dir, MS.StagedData):
        paths = data_dir.bsas()
    else:
        try:
            paths = [os.path.join(data_dir, fn) for fn in os.listdir(data_dir) if fn.lower().endswith(".bsa")]
        except OSError:
            paths = []
    for path in paths:
        try:
            for pth in m.bsa_file_names(path):
                if pth.startswith("meshes/"):
                    out.add(pth[7:].replace("/", "\\"))
        except (OSError, ValueError, struct.error, getattr(m, "FormatError", ValueError)) as e:
            print(f"  (couldn't read {os.path.basename(path)}: {e})")
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
    pats = blacklist() + (args.skip or [])
    data_dir = MS.StagedData(args.staging, game_dir)          # staged files only before deploy (mwdialog_staged)
    if not os.path.isdir(data_dir.data_dir):
        print(f"\n(note: no Data Files folder next to vortex_tidy.py ({data_dir.data_dir}): an animation's model in "
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


def _lp_key(rel):
    return rel.replace("/", "\\").replace(os.sep, "\\").strip().lower().lstrip("\\")


def _follow_moves(root, fixes, lines, lp_plan, fs):
    """The repairs of files a long-path move just took to their short path, made there in the same run: each fix
    of a moved file (or of one of its animation twins) is pointed at the short path, keeping the plan line it was
    reviewed under (lines[i] is fixes[i]'s). The short path is what the mod deploys, so its original goes to
    Off\\<plugin>\\<reason>\\<short path> (a long original path there would be over MAX_PATH again). An ASCII
    rename of a moved file is settled by the move (short names are plain ASCII): it is only marked done. A file
    whose move failed keeps its repair for the next run (still listed). Returns (fixes, lines, settled lines)."""
    moved, gone = {}, set()
    for lp in lp_plan:
        pairs = [(lp["orig"], lp["short"])] + [tuple(t) for t in (lp.get("twins") or [])]
        here = os.path.exists(_xp(os.path.join(root, fs(lp["short"]))))
        for old, short in pairs:
            gone.add(_lp_key(old))
            if here:
                moved[_lp_key(old)] = short
    out, out_lines, settled = [], [], []
    for f, a in zip(fixes, lines):
        k = _lp_key(f[2])
        if k not in gone:
            out.append(f)
            out_lines.append(a)
        elif k in moved:
            if f[0] == "ascii":
                settled.append(a)
                continue
            rel = fs(moved[k])
            out.append((f[0], os.path.join(root, rel), rel) + tuple(f[3:]))
            out_lines.append(a)
    return out, out_lines, settled


def _repair(ares, d, root, fixes, lp_plan, plug):
    """Make one mod's repairs and mark each one that worked in ares["done"] (under the plan line it was reviewed
    as). Long-path moves come first; the repairs of the files they moved are made at the short path (see
    _follow_moves), so a file both too long and broken is fixed in one --apply."""
    m, ah, game_dir = ares["m"], ares["ah"], ares["game_dir"]
    lines = asset_action_lines({"fixes": fixes, "lp_plan": []})
    if lp_plan:
        lpm = m.longpaths_module()
        fs = lpm.fs if hasattr(lpm, "fs") else (lambda r: r.replace("\\", os.sep).replace("/", os.sep))
        n = lpm.apply_mod(root, lp_plan, m, game_dir, plug, log=print)
        for lp, a in zip(lp_plan, asset_action_lines({"fixes": [], "lp_plan": lp_plan})):
            if os.path.exists(_xp(os.path.join(root, fs(lp["short"])))):
                ares["done"].add((d, a))
        print(f"    -> {n} file(s) moved to a short path (listed in mwdialog_longpaths.json; "
              f"mwdialog_check --longpaths-undo puts them back)")
        fixes, lines, settled = _follow_moves(root, fixes, lines, lp_plan, fs)
        for a in settled:
            ares["done"].add((d, a))
    line_of = {id(f): a for f, a in zip(fixes, lines)}
    dfixes = [f for f in fixes if f[0] == "dummy"]
    renamed = {f[1]: f[3] for f in fixes if f[0] == "ascii" and isinstance(f[3], str)}
    fixes = [f for f in fixes if f[0] != "dummy"]
    if fixes:
        done, skipped = ah.apply_folder(root, fixes, m, game_dir, plug)
        for f in fixes:
            if not any(sk.startswith(f[2] + " (") for sk in skipped):
                ares["done"].add((d, line_of[id(f)]))
        print(f"    -> {done} file(s) repaired (originals in Off\\{plug}\\)"
              + (f"; {len(skipped)} skipped, e.g. {skipped[0]}" if skipped else ""))
    if dfixes:
        done, skipped = make_dummies(root, dfixes, m, plug, renamed)
        for f in dfixes:
            if not any(sk.startswith(renamed.get(f[1], f[2]) + " (") or sk.startswith(f[2] + " (") for sk in skipped):
                ares["done"].add((d, line_of[id(f)]))
        print(f"    -> {done} broken file(s) moved to Off\\<plugin>\\broken\\, a dummy put in each one's place"
              + (f"; {len(skipped)} skipped, e.g. {skipped[0]}" if skipped else ""))


def main():
    """vortex_tidy, as a staged run (mwdialog_staged): Data Files is guarded from the start (a write there is
    refused), and every write over a file in the staging folder replaces it, so a Vortex hard link into Data Files
    is broken, never written through. Data Files changes only at the final deploy."""
    with MS.staged_run([], HERE):
        return _main()


def _main():
    MT.install()
    ap = MT.parser(description="Tidy the mods in Vortex's Morrowind staging folder.")
    ap.add_argument("--version", action="version", version=mwdialog_version.version_label("vortex_tidy"))
    ap.add_argument("--staging", default=None, metavar="DIR",
                    help="Vortex Morrowind staging folder (default: Vortex's own setting)")
    ap.add_argument("--only", nargs="+", metavar="PATTERN", help="only these mod folders (wildcards allowed)")
    ap.add_argument("--skip", nargs="+", metavar="PATTERN",
                    help="leave these mod folders alone this time too (to always skip one, add it to "
                         "vortex_tidy_blacklist.txt; that file is created with the built-in patterns "
                         "and *Breezify* if it is missing, and an existing file is never overwritten)")
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
    ap.add_argument("--convert-omwscripts", nargs="?", const=CONVERT_DEFAULT, default=_CONVERT_UNSET,
                    choices=CONVERT_MODES, metavar="MODE",
                    help="OpenMW-only mods (OpenMW scripts, no MWSE Lua) are converted for MWSE if/when the optional, "
                         "very experimental OpenMW converter (in development, not included) is found on PATH or "
                         "beside these tools, in this mode: normal (the default) or hardcode (hard-coded "
                         "values become MCM settings). "
                         "Pass --convert-omwscripts=hardcode to pick hardcode. Mods with MWSE Lua are never "
                         "converted: their OpenMW files go to Off\\<plugin>\\OpenMW\\. An OpenMW-only mod that is "
                         "not converted gets its whole package moved to Off\\<plugin name>\\OpenMW\\")
    ap.add_argument("--no-convert-omwscripts", dest="convert_omwscripts", action="store_const", const=None,
                    help="don't convert: OpenMW-only mods get their whole package moved to Off\\<plugin name>\\OpenMW\\")
    ap.add_argument("--pack-report", action="store_true",
                    help="for a bug report: copy MWSE.log, Data Files\\MWSE\\logs\\ and conflict-tools\\generated\\ "
                         "(only those; read-only on the game), replace your folders and Windows user name with "
                         "<MORROWIND>, <STAGING>, <DOWNLOADS>, <USERPROFILE> and <USERNAME> in the copies, and "
                         "pack them with a scrub summary into conflict-tools\\reports\\conflict-tools-report-"
                         "<date>-<time>.zip. Prints that path (one line). Binary files are left out and listed")
    ap.add_argument("--after-mwse-update", type=int, metavar="EXIT_CODE",
                    help="for a caller that just ran MWSE-Update.exe (MWManager): its exit code. Only the MWSE "
                         "core patches are re-applied (luafix --core-only: a dry run, then apply, with its backup "
                         "and journal) when the update succeeded: exit 0 and mwse-version.txt changed from "
                         "--mwse-version-before. Morrowind.exe must be closed (nothing is killed). A failed "
                         "updater or no update: nothing is done (exit 0)")
    ap.add_argument("--mwse-version-before", default="", metavar="TEXT",
                    help="with --after-mwse-update: mwse-version.txt as it was before the updater ran")
    args = ap.parse_args()
    if args.pack_report:
        if args.apply or args.undo or args.lua_only or args.after_mwse_update is not None:
            ap.error("--pack-report stands alone (it only copies logs; it changes nothing)")
        return pack_report_main(args)
    if args.after_mwse_update is not None:
        if args.apply or args.undo or args.lua_only:
            ap.error("--after-mwse-update stands alone (it only re-applies MWSE core patches)")
        outcome, _why, rc = tidy_after_mwse_update(args.after_mwse_update, args.mwse_version_before)
        return 0 if rc is None else rc
    print(mwdialog_version.version_label("vortex_tidy"))
    if args.mwse_version_before:
        ap.error("--mwse-version-before goes with --after-mwse-update")
    setup_converter(convert_mode(args.convert_omwscripts))
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
        for st in before:
            if refuse_write_root(st):
                return 2
        MS.begin(list(before))
        try:
            return undo(args.force)
        finally:
            remove_empty_bugreports(before)
    try:
        args.staging = MP.resolve_staging(cli=args.staging, required=True)
    except MP.VortexPathError as e:
        print(str(e), file=sys.stderr)
        return 2
    if refuse_write_root(args.staging):
        return 2
    MS.begin(args.staging)
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


BROKEN_KINDS = {"dummy", "broken", "brokenout", "actorbox", "orphan", "unused"}   # set aside, not repaired


def summary_lines(args, moves, lres, ares, done=None):
    """The few lines tidy ends with, long after each section's own output has scrolled away: one count per kind
    of fix, planned (done None) or done (done: {"moves": applied moves, "lua": patched paths, "assets": (mod,
    plan line) set, "convert": converted mods})."""
    plan = done is None
    moved = [m for m in (moves if plan else done["moves"]) if m[1]]   # an emptied folder's removal isn't a fix
    acts = [a for ent in ares["mods"].values() for a in asset_action_lines(ent)] if ares and plan \
        else [a for _d, a in (done or {}).get("assets", ())]
    broken = sum(1 for a in acts if a.startswith("repair ") and a.split()[1] in BROKEN_KINDS)
    lua = lres["n_ok"] if lres and plan else len((done or {}).get("lua", ()))
    rows = [("Files to move" if plan else "Files moved", len(moved)),
            ("Assets to repair" if plan else "Assets repaired", len(acts) - broken),
            ("Broken assets to set aside" if plan else "Broken assets set aside", broken),
            ("Lua scripts to patch" if plan else "Lua scripts patched", lua)]
    conv = CONVERT if plan else done["convert"]
    if conv:
        rows.append(("OpenMW mods to convert" if plan else "OpenMW mods converted", len(conv)))
    if REVIEW:
        rows.append(("Mods that need a look", len(REVIEW)))
    w = max(len(k) for k, _n in rows)
    return ["", f"vortex_tidy summary ({'plan' if plan else 'done'}):"] + [f"  {k + ':':<{w + 1}} {n:>6,}"
                                                                          for k, n in rows]


def plan_main(args):
    text, _parts, moves, lres, ares = fresh_plan(args)
    PF.write_atomic(PLAN, text)
    print("\n".join(summary_lines(args, moves, lres, ares)))
    print(f"\nFull plan: {PLAN}")
    if moves or REVIEW or CONVERT or (lres and lres["n_ok"]) or assets_pending(ares):
        print("\nNothing changed. Review the plan, run again with --apply, then Deploy in Vortex.")
    else:
        print("\nNothing to fix.")
    return 0


def apply_main(args):
    """--apply enacts the plan you reviewed and nothing else: the plan is worked out again and must list the
    same actions as the plan file (moves, Lua patches, asset repairs; --lua-only: the Lua section only), or
    nothing is done - the new plan is written for review and the old one kept as vortex_tidy_plan.prev.txt.
    Afterwards the plan file is blanked, or cut down to what was not applied, atomically, with copies of the
    plan as reviewed and as enacted in <backups folder>\\tidy\\<run>\\."""
    pend = read_intent()
    if pend:                                          # an earlier --apply stopped inside a conversion
        reconcile_intent(pend)
        print("\nNothing else was done this run: run vortex_tidy again to plan, review, then --apply.")
        return 1
    reviewed = PF.read(PLAN)
    parts = [LUA_HEAD] if args.lua_only else \
        ["moves"] + ([] if args.no_lua else [LUA_HEAD]) + ([] if args.no_assets else [ASSET_HEAD])
    if PF.state(PLAN) != "pending" or not PF.has_any_actions(reviewed, parts):
        print(PF.no_plan_message(PLAN, "vortex_tidy.py" + (" --lua-only" if args.lua_only else "")))
        return 2
    text, parts, moves, lres, ares = fresh_plan(args)
    added, removed = PF.compare(reviewed, text, parts)
    if added or removed:
        print("\n".join(summary_lines(args, moves, lres, ares)))     # what the new plan holds
        if any(CHECK_LABEL in str(a) for a in list(added) + list(removed)):
            print(f"\n{CHECK_REFUSED}.")
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
            if not args.yes and input(f"\nApply {what}? [y/N] ").strip().lower() not in \
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
                                              args._journal_extra, audit)
        st["finished"] = True
    finally:
        left = _finish_plan(args, st, reviewed, audit)
    left_conv = set(st["convert_left"] or ())
    print("\n".join(summary_lines(args, moves, lres, ares, done={
        "moves": [st["moves"][i] for i in st["progress"]], "lua": (lres or {}).get("done") or [],
        "assets": (ares or {}).get("done") or set(), "convert": [m for m in st["convert"] if m not in left_conv]})))
    if left:
        print(f"  Not everything was done: what is left is in {PLAN}")
    return 0 if not left else 1


def _left_lines(args, st):
    done = set(st["progress"])
    out = []
    if "moves" in st["keep"]:
        out += [ln for ln in st["keep"]["moves"].splitlines() if not ln.startswith("#")]
    out += moves_as_lines([m for i, m in enumerate(st["moves"]) if i not in done], args.staging)
    for mod_dir in st.get("convert_left") or []:     # not converted (failed, or the run stopped first)
        out += convert_lines(os.path.basename(mod_dir), CONVERT.get(mod_dir, []), CONVERTER["mode"],
                             (PREVIEW_CHECK.get(mod_dir) or {}).get("lines", ()))
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


def pack_report_main(args, out_dir=None):
    """--pack-report (mwdialog_report): one scrubbed archive of the logs for a bug report; prints its path. A read
    of Data Files\\MWSE\\logs only (mwdialog_staged.PACK_REPORT_READS); nothing is written to Data Files.
    out_dir: a test or smoke run's own folder (no command-line option)."""
    if not MP.is_game_dir(HERE):
        print(f"No Morrowind folder found (looked at {HERE}); run this from the game folder.", file=sys.stderr)
        return 2
    found = [args.staging] if args.staging else []
    try:
        found.append(MP.resolve_staging(required=False))
    except (OSError, MP.VortexPathError):
        pass
    found += _journal_stagings() if os.path.exists(JOURNAL) else []
    stagings = []
    for st in found:
        if st and os.path.normcase(os.path.abspath(st)) not in [os.path.normcase(s) for s in stagings]:
            stagings.append(os.path.abspath(st))
    try:
        downloads = [MP.resolve_downloads(required=False)]
    except (OSError, MP.VortexPathError):
        downloads = []
    return MR.main(HERE, stagings, [d for d in downloads if d], out_dir=out_dir)


def refuse_write_root(staging):
    """True (and one message on stderr) when `staging` is Data Files, the game folder or inside either, real
    paths compared (mwdialog_staged.write_root_problem): tidy then stops before writing anything. Only MWManager's
    tidy --init may act on Data Files; this CLI has no such mode."""
    why = MS.write_root_problem(staging, HERE, os.path.join(HERE, "Data Files"), mode="tidy")
    if why:
        print(f"Not tidying {staging}: {why}. Tidy works on Vortex's or MWManager's staging folder before deploy; "
              f"Data Files and the game folder change only at the deploy step (or with tidy --init).", file=sys.stderr)
        return True
    return False


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
