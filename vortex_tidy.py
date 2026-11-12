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
    mwdialog_backup\\luafix), --undo puts them back. --no-lua skips this, --lua-only does only this.

It only shows the plan unless you pass --apply. Every move is written to a journal, and --undo puts
everything back. Purge in Vortex before applying, and Deploy afterwards, so the game folder matches.
--apply enacts only the plan you reviewed: it works the plan out again (moves, Lua patches, asset repairs -
all listed in vortex_tidy_plan.txt; --lua-only: its Lua section) and refuses, changing nothing, when the
actions differ from the plan file: the new plan is written for review and the old one kept as
vortex_tidy_plan.prev.txt. No plan file (or a blank one) also refuses: run plan mode first.
Afterwards vortex_tidy_plan.txt is blanked (only a "# applied
..." line: a second --apply does nothing until plan mode is run again), or cut down to what was NOT applied.
Copies of the plan as reviewed and as enacted go to mwdialog_backup\\tidy\\<run>\\. --undo uses the journal only.

    python vortex_tidy.py                      (plan for every mod; nothing is changed)
    python vortex_tidy.py --only "MUSE*"       (plan for some mods; wildcards allowed)
    python vortex_tidy.py --apply              (do it)
    python vortex_tidy.py --undo               (put back everything the last --apply moved)
"""
import argparse
import fnmatch
import json
import os
import re
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_planfile as PF                   # noqa: E402
import mwdialog_paths as MP                      # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
JOURNAL = os.path.join(HERE, "vortex_tidy_journal.jsonl")
PLAN = os.path.join(HERE, "vortex_tidy_plan.txt")
AUDIT_ROOT = os.path.join(HERE, "mwdialog_backup", "tidy")     # a copy of each enacted plan, per --apply run
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
    import struct
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
KEEP_FILE_EXT = {".esp", ".esm", ".omwaddon", ".bsa"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}   # screenshots (not .dds/.tga: textures)
DOC_EXT = {".txt", ".md", ".pdf", ".rtf", ".doc", ".docx", ".odt", ".html", ".htm", ".nfo"}
DOC_DIR_NAMES = {"doc", "docs", "documentation", "readme", "readmes", "manual", "manuals", "info"}
GAME_ROOT_EXT = {".exe", ".dll", ".asi"}          # the mod installs into the game folder: leave it alone
# mods never touched: the defaults below plus one pattern per line in vortex_tidy_blacklist.txt
# (next to this script; wildcards allowed, matched against the mod's folder name, case doesn't matter)
BLACKLIST = ["Morrowind Code Patch*", "MCP beta*", "NIFZER0EDIT*"]
BLACKLIST_FILE = os.path.join(HERE, "vortex_tidy_blacklist.txt")


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
    and in its BSAs (Data Files next to this script). Built once per staging folder."""
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


def plan_mod(mod_dir):
    """[(source, destination, reason)] for one mod, or a str saying why it's left alone."""
    entries = os.listdir(mod_dir)
    low = {e.lower() for e in entries}
    if "data files" in low or any(os.path.splitext(e)[1].lower() in GAME_ROOT_EXT for e in entries
                                  if os.path.isfile(os.path.join(mod_dir, e))):
        return "installs into the game folder (exe/dll/Data Files at its root)"
    name = mod_name(os.path.basename(mod_dir))
    plugins = {os.path.splitext(e)[0].lower() for e in entries if os.path.splitext(e)[1].lower() in KEEP_FILE_EXT}
    # an OpenMW plugin (.omwaddon) and no Morrowind plugin: with no OpenMW scripts it is an ordinary plugin
    # in OpenMW's file name, so it becomes an .esp; with scripts, it needs OpenMW: you decide (REVIEW)
    addons = [e for e in entries if e.lower().endswith(".omwaddon") and os.path.isfile(os.path.join(mod_dir, e))]
    has_mw_plugin = any(os.path.splitext(e)[1].lower() in (".esp", ".esm") for e in entries)
    rename_addons = []
    if addons and not has_mw_plugin:
        scripts = openmw_scripts(mod_dir, entries)
        if scripts:
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

def deleted_dir(staging):
    """Where deleted mods go: beside the staging folder in use, "<its name> - deleted by vortex_tidy"."""
    staging = os.path.abspath(staging).rstrip("\\/")
    return os.path.join(os.path.dirname(staging), os.path.basename(staging) + " - deleted by vortex_tidy")


def openmw_scripts(mod_dir, entries):
    """The OpenMW Lua scripts a mod has: *.omwscripts files and scripts folders, at its root or in OpenMW\\."""
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
        print(f"  OpenMW plugin(s): {', '.join(addons)}; no .esp or .esm")
        print(f"  OpenMW scripts: {', '.join(scripts)}")
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


def split_plan(text):
    """(the moves part, the Lua part) of a plan file's text."""
    t = text or ""
    i = t.find("\n" + LUA_HEAD + "\n")
    return (t, "") if i < 0 else (t[:i], t[i + 1:])


def has_actions(part):
    """Does a plan part list anything to do (indented action lines, not comments or notes)?"""
    return any(ln.startswith("    ") and ln.strip() and not ln.lstrip().startswith("#")
               for ln in (part or "").splitlines())


def run_plan(args):
    mods = sorted(d for d in os.listdir(args.staging) if os.path.isdir(os.path.join(args.staging, d))
                  and d.lower() != "off")                       # your own Off folder is never touched
    if args.only:
        mods = [d for d in mods if any(fnmatch.fnmatch(d.lower(), pat.lower()) for pat in args.only)]
    lines, all_moves, skipped, touched = [], [], [], 0
    ORPHAN_NORMALS.clear()
    NORMAL_PACKS.clear()
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
        if not res:
            continue
        touched += 1
        lines += move_lines(d, res, args.staging)
        all_moves += res
    head = [f"vortex_tidy plan, {time.strftime('%Y-%m-%d %H:%M')}: {len(mods)} mod(s), {touched} to change, "
            f"{sum(1 for m in all_moves if m[1])} move(s); {len(skipped)} left alone"]
    for d, why in skipped:
        head.append(f"  left alone: {d} ({why})")
    for d, n in sorted(NORMAL_PACKS.items()):
        NOTES.append(f"{d}: a normal-map add-on pack ({n} normal map(s) under a 'normal maps' path) - not "
                     f"applicable to classic Morrowind (only OpenMW uses normal maps); consider removing it in Vortex")
    if ORPHAN_NORMALS:
        NOTES.append(f"{len(ORPHAN_NORMALS)} normal map(s) with no diffuse texture anywhere left in place (no "
                     f"stand-in); mwdialog_check --full's unused-asset purge removes the unused ones")
    for note in NOTES:
        head.append(f"  NOTE: {note}")
    for d, rel in ORPHAN_NORMALS[:50]:
        lines.append(f"  left in place (no diffuse texture anywhere): {d}\\{rel}")
    for mod_dir, (addons, scripts) in sorted(REVIEW.items()):
        head.append(f"  NEEDS A LOOK (OpenMW-only: {', '.join(addons)}, no .esp, scripts {', '.join(scripts)}): "
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
        for i, (src, dst, why) in enumerate(moves):
            try:
                if dst is None:
                    for base, dirs, fns in os.walk(src, topdown=False):   # only empty folders go
                        if not os.listdir(base):
                            os.rmdir(base)
                            j.write(json.dumps({"rmdir": base}) + "\n")
                    if progress is not None:
                        progress.append(i)
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                os.rename(src, dst)          # same drive: a rename, so Vortex's hard links keep their file
                j.write(json.dumps({"src": src, "dst": dst}) + "\n")
                j.flush()
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


def undo():
    if not os.path.exists(JOURNAL):
        print("Nothing to undo (no journal).")
        return 1
    runs, cur = [], None
    for line in open(JOURNAL, encoding="utf-8"):
        rec = json.loads(line)
        if "run" in rec:
            cur = {"head": rec, "ops": []}
            runs.append(cur)
        elif cur is not None:
            cur["ops"].append(rec)
    if not runs:
        print("Nothing to undo.")
        return 1
    last = runs.pop()
    back = 0
    left = []                                         # ops not undone: kept in the journal for another try
    for op in reversed(last["ops"]):
        if "luafix" in op:                            # a Lua file mwdialog_luafix patched in place
            lf = _luafix()
            ok, msg = lf.restore_op(op) if lf else (False, f"{op['luafix']}: mwdialog_luafix.py not found")
            if ok:
                back += 1
            else:
                print("  " + msg, file=sys.stderr)
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
            else:
                print(f"  not put back (no longer there): {op['dst']}", file=sys.stderr)
                left.append(op)
        except OSError as e:
            print(f"  could not put back {op.get('dst')}: {e}", file=sys.stderr)
            left.append(op)
    for d in {os.path.dirname(op["dst"]) for op in last["ops"] if "dst" in op}:   # tidy emptied folders
        try:
            while d and os.path.isdir(d) and not os.listdir(d):
                os.rmdir(d)
                d = os.path.dirname(d)
        except OSError:
            pass
    if left:
        runs.append({"head": last["head"], "ops": list(reversed(left))})
    tmp = JOURNAL + ".tmp"
    with open(tmp, "w", encoding="utf-8") as j:
        for r in runs:
            j.write(json.dumps(r["head"]) + "\n")
            for op in r["ops"]:
                j.write(json.dumps(op) + "\n")
    os.replace(tmp, JOURNAL)
    print(f"Put back {back} item(s) moved by the run of {last['head']['run']}. Deploy in Vortex again.")
    if left:
        print(f"{len(left)} item(s) could not be put back (listed above); they stay in the journal "
              f"({JOURNAL}), so --undo can try them again.")
        return 1
    return 0


def _luafix():
    """mwdialog_luafix.py from this folder, or None."""
    try:
        import mwdialog_luafix
        return mwdialog_luafix
    except Exception as e:
        print(f"(mwdialog_luafix.py could not be loaded: {e})", file=sys.stderr)
        return None


def lua_check(args):
    """mwdialog_luafix on each mod's MWSE Lua files (nothing written): {"reps", "merged", "body" (the plan's Lua
    section), "n_ok", "checker"}, or None when mwdialog_luafix.py is missing."""
    lf = _luafix()
    if lf is None:
        return None
    game_dir = os.path.dirname(os.path.abspath(__file__))
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
    mwdialog_backup\\luafix, journaled here so --undo puts them back. A file changed since the check is refused."""
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


def assets_check_mod(root, m, ah, data_dir, bsa_meshes, game_dir, stats):
    issues, fixes = ah.check_folder(root, m, data_dir, bsa_meshes, stats=stats)
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
    game_dir = os.path.dirname(os.path.abspath(__file__))
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
    print(f"\n{summary}" + ("" if args.apply else " (run with --apply to repair them)"))
    st = res["stats"]
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
        if acts:
            out += [f"\n{d}"] + [f"    {a}" for a in acts]
    return out


def assets_apply(args, ares, moved_mods=()):
    """Make the asset repairs assets_check() listed (the reviewed ones) - nothing else. A mod whose files the
    moves of this run touched is checked again first, and only the reviewed repairs that still apply are
    made; the rest stay in the plan. Originals go to <mod>\\Off\\<plugin>\\<path>."""
    if not ares:
        return
    m, ah, game_dir = ares["m"], ares["ah"], ares["game_dir"]
    for d, ent in ares["mods"].items():
        root = ent["root"]
        wanted = set(asset_action_lines(ent))
        if d in moved_mods and wanted:
            try:
                now = assets_check_mod(root, m, ah, ares["data_dir"], ares["bsa"], game_dir, {})
            except Exception as e:
                print(f"  {d}: check failed ({e})")
                continue
            new = set(asset_action_lines(now))
            if new - wanted:
                print(f"  {d}: {len(new - wanted)} repair(s) appeared after the moves - not in the plan you "
                      f"reviewed, so not made (rerun plan mode)")
            now["fixes"] = [f for f, a in zip(now["fixes"], asset_action_lines(dict(now, lp_plan=[])))
                            if a in wanted]
            now["lp_plan"] = [lp for lp, a in zip(now["lp_plan"], asset_action_lines(dict(now, fixes=[])))
                              if a in wanted]
            now["root"] = root
            work = now
        else:
            work = ent
        issues, fixes, lp_plan = work["issues"], work["fixes"], work["lp_plan"]
        if not issues:                                # clean now: drop an old tidy section
            bdir = os.path.join(root, "bugreports")
            for e in (os.listdir(bdir) if os.path.isdir(bdir) else ()):
                if e.lower().endswith(".bugreport.txt"):
                    ah.update_bug_report(os.path.join(bdir, e), "vortex_tidy (files)", [], [])
            continue
        if not fixes and not lp_plan:
            continue
        plug_file = next((e for e in sorted(os.listdir(root))
                          if os.path.splitext(e)[1].lower() in (".esp", ".esm")), None)
        plug = os.path.splitext(plug_file)[0] if plug_file else mod_name(d)
        nid = ah.nexus_id(root)
        head = (ah.bug_report_header(os.path.join(root, plug_file), m, mod_folder=root) if plug_file else
                [f"Bug report for {mod_name(d)}", f"Mod: {mod_name(d)} (no plugin)",
                 f"Generated {time.strftime('%Y-%m-%d %H:%M')} by vortex_tidy.",
                 "Paths are relative to the mod's folder (Data Files)."])
        lines = [f"Problems in the mod's files: {len(issues)}"]
        lines += [f"  - {sev} {rel}: {msg}" for sev, rel, msg in issues]
        lines += ["", "(The mod's copy was repaired on this PC; originals kept in Off\\.)"]
        ah.update_bug_report(os.path.join(root, "bugreports", plug + (f" [Nexus {nid}]" if nid else "")
                                          + ".bugreport.txt"), "vortex_tidy (files)", head, lines)
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
        if fixes:
            done, skipped = ah.apply_folder(root, fixes, m, game_dir, plug)
            for f, a in zip(fixes, asset_action_lines({"fixes": fixes, "lp_plan": []})):
                if not any(sk.startswith(f[2] + " (") for sk in skipped):
                    ares["done"].add((d, a))
            print(f"    -> {done} file(s) repaired (originals in Off\\{plug}\\)"
                  + (f"; {len(skipped)} skipped, e.g. {skipped[0]}" if skipped else ""))


def main():
    ap = argparse.ArgumentParser(description="Tidy the mods in Vortex's Morrowind staging folder.")
    ap.add_argument("--staging", default=None, metavar="DIR",
                    help="Vortex Morrowind staging folder (default: Vortex's own setting)")
    ap.add_argument("--only", nargs="+", metavar="PATTERN", help="only these mod folders (wildcards allowed)")
    ap.add_argument("--skip", nargs="+", metavar="PATTERN",
                    help="leave these mod folders alone this time too (to always skip one, add it to "
                         "vortex_tidy_blacklist.txt)")
    ap.add_argument("--apply", action="store_true", help="make the changes (without it, only the plan is shown)")
    ap.add_argument("--yes", action="store_true", help="with --apply: don't ask first")
    ap.add_argument("--undo", action="store_true", help="put back everything the last --apply moved")
    ap.add_argument("--no-assets", action="store_true", help="skip the asset check of each mod's files")
    ap.add_argument("--no-lua", action="store_true", help="skip the Lua check (mwdialog_luafix)")
    ap.add_argument("--lua-only", action="store_true", help="only the Lua check: no moves, no asset check")
    ap.add_argument("--lua-level", choices=("high", "medium"), default="high",
                    help="which Lua findings --apply patches (default high)")
    ap.add_argument("--luajit", help="the LuaJIT (or luac) the Lua check compiles with")
    ap.add_argument("--lua-log", choices=("flagged", "all", "off"),
                    help="which mods the Lua check gives the log shim: flagged (default), all, off")
    args = ap.parse_args()
    if args.undo:
        return undo()                                 # works from the journal; the plan file plays no part
    try:
        args.staging = MP.resolve_staging(cli=args.staging, required=True)
    except MP.VortexPathError as e:
        print(str(e), file=sys.stderr)
        return 2
    src = "--staging" if any(a == "--staging" or a.startswith("--staging=") for a in sys.argv[1:]) else "Vortex settings"
    print(f"Vortex staging: {args.staging}  (from {src})")
    if not args.apply:
        return plan_main(args)
    return apply_main(args)


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
    return text, parts, moves, lres, ares


def plan_main(args):
    text, _parts, _moves, _l, _a = fresh_plan(args)
    PF.write_atomic(PLAN, text)
    print(f"\nFull plan: {PLAN}")
    print("\nNothing changed. Purge in Vortex, review the plan, run again with --apply, then Deploy.")
    return 0


def apply_main(args):
    """--apply enacts the plan you reviewed and nothing else: the plan is worked out again and must list the
    same actions as the plan file (moves, Lua patches, asset repairs; --lua-only: the Lua section only), or
    nothing is done - the new plan is written for review and the old one kept as vortex_tidy_plan.prev.txt.
    Afterwards the plan file is blanked, or cut down to what was not applied, atomically, with copies of the
    plan as reviewed and as enacted in mwdialog_backup\\tidy\\<run>\\."""
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
    args._journal_extra = {"plan_copy": os.path.join(audit, "plan_enacted.txt")}
    sec = PF.sections(reviewed)
    keep = {k: v for k, v in sec.items() if k not in parts and PF.has_any_actions(v)}   # not enacted: stays
    st = {"moves": [], "progress": [], "lua": lres, "assets": ares, "keep": keep, "started": False,
          "finished": False, "text": text}
    if not args.lua_only:
        moves, gone = review(args.staging, moves, assume_keep=args.yes)
        if moves or gone:
            what = f"{sum(1 for m in moves if m[1])} move(s)" + (f" and delete {len(gone)} mod(s)" if gone else "")
            if not args.yes and input(f"\nApply {what}? Purge in Vortex first. [y/N] ").strip().lower() not in \
                    ("y", "yes"):
                print("Nothing changed.")
                return 0
        else:
            print("Nothing to move.")
        st["moves"] = gone + moves
    left = []
    try:
        st["started"] = True
        if st["moves"]:
            apply(st["moves"], args.staging, st["progress"], args._journal_extra)
        lua_apply(args, lres)
        moved_mods = {os.path.relpath(st["moves"][i][0], args.staging).split(os.sep)[0] for i in st["progress"]}
        assets_apply(args, ares, moved_mods)
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


if __name__ == "__main__":
    sys.exit(main())
