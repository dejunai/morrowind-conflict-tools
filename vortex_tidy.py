#!/usr/bin/env python3
"""vortex_tidy.py - tidy the mods in Vortex's Morrowind staging folder.

For each mod folder in the staging folder (G:\\Vortex Mods\\morrowind):

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
    "G:\\Vortex Mods\\morrowind - deleted by vortex_tidy", so --undo can bring it back).
  * Normal maps (textures\\...\\*_n / *_nm / *_normal / *_nrm, .dds/.tga/.bmp) all go to
    Off\\normal maps\\<mod name>\\ (never deployed): vanilla Morrowind with MGE XE doesn't use them (only OpenMW
    does). If a model names one, mwdialog_check.py --fix puts a flat stand-in normal map in its place, so
    the game shows no missing-texture warnings. One with no diffuse texture beside it (tx_wall.dds for
    tx_wall_n.dds) is still moved, with a warning in the plan and in --apply's output: check it really is
    a normal map (--undo puts it back).
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

It only shows the plan unless you pass --apply. Every move is written to a journal, and --undo puts
everything back. Purge in Vortex before applying, and Deploy afterwards, so the game folder matches.

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

STAGING = r"G:\Vortex Mods\morrowind"
HERE = os.path.dirname(os.path.abspath(__file__))
JOURNAL = os.path.join(HERE, "vortex_tidy_journal.jsonl")
PLAN = os.path.join(HERE, "vortex_tidy_plan.txt")

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
NO_DIFFUSE_WARNING = "no matching diffuse texture beside it, check it's really a normal map; --undo puts it back"


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
            # OpenMW does), so every one goes to Off\normal maps\<mod>\, which is never deployed. If a model
            # names one, mwdialog_check.py --fix puts a flat stand-in normal map in its place (no
            # "tex not found" warnings). One with no diffuse texture beside it still moves, with a warning:
            # it may be a real texture whose name only looks like a normal map's (--undo puts it back).
            for p in files_under(src):
                stem = os.path.splitext(os.path.basename(p))[0].lower()
                if os.path.splitext(p)[1].lower() not in (".dds", ".tga", ".bmp") or not NORMAL_MAP.search(stem):
                    continue
                rel = os.path.relpath(p, mod_dir)
                why = "normal map (not used without OpenMW)"
                if not has_diffuse_sibling(p):
                    why += f"; WARNING: {NO_DIFFUSE_WARNING}"
                    NOTES.append(f"{os.path.basename(mod_dir)}\\{rel}: {NO_DIFFUSE_WARNING}")
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
DELETED = os.path.join(os.path.dirname(STAGING.rstrip("\\")), "morrowind - deleted by vortex_tidy")


def deleted_dir(staging):
    """Where deleted mods go: beside the staging folder in use (--staging), "<its name> - deleted by
    vortex_tidy"; for the default staging folder that is DELETED, as before."""
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
    and delete it if you want: it goes to DELETED (outside the staging folder), so it can come back.
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


def run_plan(args):
    mods = sorted(d for d in os.listdir(args.staging) if os.path.isdir(os.path.join(args.staging, d))
                  and d.lower() != "off")                       # your own Off folder is never touched
    if args.only:
        mods = [d for d in mods if any(fnmatch.fnmatch(d.lower(), pat.lower()) for pat in args.only)]
    lines, all_moves, skipped, touched = [], [], [], 0
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
        lines.append(f"\n{d}   [{mod_name(d)}]")
        for src, dst, why in res:
            rs = os.path.relpath(src, os.path.join(args.staging, d))
            if dst is None:
                lines.append(f"    remove empty  {rs}")
            else:
                lines.append(f"    {rs}  ->  {os.path.relpath(dst, os.path.join(args.staging, d))}   ({why})")
        all_moves += res
    head = [f"vortex_tidy plan, {time.strftime('%Y-%m-%d %H:%M')}: {len(mods)} mod(s), {touched} to change, "
            f"{sum(1 for m in all_moves if m[1])} move(s); {len(skipped)} left alone"]
    for d, why in skipped:
        head.append(f"  left alone: {d} ({why})")
    for note in NOTES:
        head.append(f"  NOTE: {note}")
    for mod_dir, (addons, scripts) in sorted(REVIEW.items()):
        head.append(f"  NEEDS A LOOK (OpenMW-only: {', '.join(addons)}, no .esp, scripts {', '.join(scripts)}): "
                    f"{os.path.basename(mod_dir)} - --apply stops at it and offers to delete it")
    with open(PLAN, "w", encoding="utf-8") as f:
        f.write("\n".join(head + lines) + "\n")
    print("\n".join(head))
    print("\n".join(lines[:200]))
    if len(lines) > 200:
        print(f"... ({len(lines) - 200} more lines in {PLAN})")
    print(f"\nFull plan: {PLAN}")
    return all_moves


def apply(moves, staging):
    done = 0
    with open(JOURNAL, "a", encoding="utf-8") as j:
        j.write(json.dumps({"run": time.strftime("%Y-%m-%d %H:%M:%S"), "staging": staging}) + "\n")
        for src, dst, why in moves:
            try:
                if dst is None:
                    for base, dirs, fns in os.walk(src, topdown=False):   # only empty folders go
                        if not os.listdir(base):
                            os.rmdir(base)
                            j.write(json.dumps({"rmdir": base}) + "\n")
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                os.rename(src, dst)          # same drive: a rename, so Vortex's hard links keep their file
                j.write(json.dumps({"src": src, "dst": dst}) + "\n")
                j.flush()
                done += 1
                if NO_DIFFUSE_WARNING in why:
                    print(f"  WARNING: moved {src} -> {dst}: {NO_DIFFUSE_WARNING}")
            except OSError as e:
                print(f"  could not move {src}: {e}", file=sys.stderr)
    print(f"Moved {done} item(s). Journal: {JOURNAL} (--undo puts them back). Now Deploy in Vortex.")


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


def run_assets(args, do_apply):
    """The asset check on each mod's own files: textures (DX10/BC7, over 2048, no mipmaps, uncompressed,
    not a power of two, truncated), models (not Morrowind's format, Unix line endings in animation text
    keys, absolute texture paths), sounds (stereo, odd rates, 24/32-bit or non-PCM WAV, big MP3 tags),
    empty files, non-ASCII names. Repairs are made in place (Data Files' hard links stay); originals go to
    <mod>\\Off\\<plugin>\\<path>."""
    m, ah = _tool_modules()
    if m is None:
        print("\n(asset check skipped: mwdialog_check.py / mwdialog_assets.py not found next to vortex_tidy.py)")
        return
    game_dir = os.path.dirname(os.path.abspath(__file__))
    mods = sorted(d for d in os.listdir(args.staging) if os.path.isdir(os.path.join(args.staging, d))
                  and d.lower() != "off")
    if args.only:
        mods = [d for d in mods if any(fnmatch.fnmatch(d.lower(), pat.lower()) for pat in args.only)]
    pats = blacklist(create=do_apply) + (args.skip or [])
    data_dir = os.path.join(game_dir, "Data Files")
    bsa_meshes = set()
    if not os.path.isdir(data_dir):
        print(f"\n(note: no Data Files folder next to vortex_tidy.py ({data_dir}): an animation's model in "
              f"another mod or a BSA can't be found, so more files may be reported)")
    try:
        names = os.listdir(data_dir)
    except OSError:
        names = []
    for fn in names:
        if fn.lower().endswith(".bsa"):
            try:
                for pth in m.bsa_file_names(os.path.join(data_dir, fn)):
                    if pth.startswith("meshes/"):
                        bsa_meshes.add(pth[7:].replace("/", "\\"))
            except (OSError, ValueError, struct.error, getattr(m, "FormatError", ValueError)) as e:
                print(f"  (couldn't read {fn}: {e})")
    print("\n" + "=" * 70 + "\nASSET CHECK (each mod's own files)\n" + "=" * 70)
    total_fix = total_issue = 0
    for d in mods:
        if any(fnmatch.fnmatch(d.lower(), pt.lower()) for pt in pats):
            continue
        root = os.path.join(args.staging, d)
        try:
            issues, fixes = ah.check_folder(root, m, data_dir, bsa_meshes)
        except Exception as e:                      # one odd mod never stops the rest
            print(f"  {d}: check failed ({e})")
            continue
        if not issues:
            if do_apply:                              # clean now: drop an old tidy section
                bdir = os.path.join(root, "bugreports")
                for e in (os.listdir(bdir) if os.path.isdir(bdir) else ()):
                    if e.lower().endswith(".bugreport.txt"):
                        ah.update_bug_report(os.path.join(bdir, e), "vortex_tidy (files)", [], [])
            continue
        total_issue += len(issues)
        total_fix += len(fixes)
        print(f"\n{d}")
        for sev, rel, msg in issues[:12]:
            print(f"    {sev:5} {rel}: {msg}")
        if len(issues) > 12:
            print(f"    ... and {len(issues) - 12} more")
        plug = next((os.path.splitext(e)[0] for e in sorted(os.listdir(root))
                     if os.path.splitext(e)[1].lower() in (".esp", ".esm")), mod_name(d))
        if do_apply:
            plug_file = next((e for e in sorted(os.listdir(root))
                              if os.path.splitext(e)[1].lower() in (".esp", ".esm")), None)
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
        if do_apply and fixes:
            done, skipped = ah.apply_folder(root, fixes, m, game_dir, plug)
            print(f"    -> {done} file(s) repaired (originals in Off\\{plug}\\)"
                  + (f"; {len(skipped)} skipped, e.g. {skipped[0]}" if skipped else ""))
    print(f"\n  {total_issue} asset issue(s), {total_fix} repairable"
          + ("" if do_apply else " (run with --apply to repair them)"))


def main():
    ap = argparse.ArgumentParser(description="Tidy the mods in Vortex's Morrowind staging folder.")
    ap.add_argument("--staging", default=STAGING, help=f"the staging folder (default {STAGING})")
    ap.add_argument("--only", nargs="+", metavar="PATTERN", help="only these mod folders (wildcards allowed)")
    ap.add_argument("--skip", nargs="+", metavar="PATTERN",
                    help="leave these mod folders alone this time too (to always skip one, add it to "
                         "vortex_tidy_blacklist.txt)")
    ap.add_argument("--apply", action="store_true", help="make the changes (without it, only the plan is shown)")
    ap.add_argument("--yes", action="store_true", help="with --apply: don't ask first")
    ap.add_argument("--undo", action="store_true", help="put back everything the last --apply moved")
    ap.add_argument("--no-assets", action="store_true", help="skip the asset check of each mod's files")
    args = ap.parse_args()
    if args.undo:
        return undo()
    if not os.path.isdir(args.staging):
        print(f"Staging folder not found: {args.staging}", file=sys.stderr)
        return 2
    moves = run_plan(args)
    if not args.apply:
        if not args.no_assets:
            run_assets(args, False)
        print("\nNothing changed. Purge in Vortex, run again with --apply, then Deploy.")
        return 0
    moves, gone = review(args.staging, moves, assume_keep=args.yes)
    if not moves and not gone:
        print("Nothing to move.")
        if not args.no_assets:
            run_assets(args, True)
        return 0
    what = f"{sum(1 for m in moves if m[1])} move(s)" + (f" and delete {len(gone)} mod(s)" if gone else "")
    if not args.yes and input(f"\nApply {what}? Purge in Vortex first. [y/N] ").strip().lower() not in ("y", "yes"):
        print("Nothing changed.")
        return 0
    apply(gone + moves, args.staging)
    if not args.no_assets:
        run_assets(args, True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
