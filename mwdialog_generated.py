"""mwdialog_generated.py - files --fix puts in Data Files or changes there: stand-ins for missing assets,
reduced textures, the kept originals, and taking them out again.
"""
from collections import Counter
import hashlib
import os
import re
import shutil
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_paths as MP  # noqa: E402
from mwdialog_backup import (  # noqa: E402
    BACKUP_DIR)
from mwdialog_console import (  # noqa: E402
    print)
from mwdialog_datatree import (  # noqa: E402
    GENERATED_RECORD, asset_owner_folder, hard_link_names)
from mwdialog_media import (  # noqa: E402
    dds_reduce, stand_in_bytes)
from mwdialog_state import (  # noqa: E402
    read_generated_record, record_bases, write_generated_record)
from mwdialog_tes3 import (  # noqa: E402
    safe_write_bytes)


def off_dest(mod, feature, plugin, rel):
    """<mod folder>\\Off\\<feature>\\<plugin name>\\<rel>: where an original goes when <feature> (the part of
    these tools that did it: sound, textures, broken, unused...) changes or takes it out. Off is never
    deployed. plugin: the mod's plugin (its name without the extension), or the mod's own name."""
    if plugin:
        name = os.path.splitext(os.path.basename(plugin))[0]
    else:
        own = sorted(e for e in os.listdir(mod) if e.lower().endswith((".esp", ".esm"))) if os.path.isdir(mod) else []
        name = os.path.splitext(own[0])[0] if own else \
            re.split(r"-\d+-|\s+\d{4,}\s", os.path.basename(mod.rstrip("\\/")))[0].strip()
    return os.path.join(mod, "Off", feature, name, rel)


def backup_asset_original(data_dir, rel, plugin=None, feature="converted", track_new=True):
    """Before an asset file is replaced: keep the original in <its Vortex mod folder>\\Off\\<feature>\\<plugin
    name>\\<rel> (Off is never deployed). Not from Vortex: <game folder>\\asset_originals\\<feature>\\<rel>.
    An original kept already (here, or where earlier versions put it: Off\\<plugin name>\\<rel>) is never
    replaced. But when the file now there is neither that original nor a repair these tools made of it (a mod
    update put a new file there), it is kept too, next to the first one with a date added
    (<name>.YYYYMMDD-HHMMSS<ext>); track_new=False keeps only the first one, as before.
    Returns the path that holds the file's current original."""
    current = os.path.join(data_dir, rel)
    keep = keep_new_original if track_new else (lambda b, _cur: b)
    mod, owner_plugin = asset_owner_folder(data_dir, rel)
    if mod:
        dest = off_dest(mod, feature, plugin or owner_plugin, rel)
        old = os.path.join(mod, "Off", os.path.splitext(os.path.basename(plugin or owner_plugin or ""))[0], rel)
        if (plugin or owner_plugin) and os.path.exists(old):
            return keep(old, current)
        off = os.path.join(mod, "Off")
        for f in (os.listdir(off) if os.path.isdir(off) else ()):          # any feature kept it already
            for d in (os.listdir(os.path.join(off, f)) if os.path.isdir(os.path.join(off, f)) else ()):
                if os.path.exists(os.path.join(off, f, d, rel)) and f.lower() not in ("broken", "orphaned", "unused"):
                    return keep(os.path.join(off, f, d, rel), current)
    else:
        dest = os.path.join(os.path.dirname(os.path.abspath(data_dir)), BACKUP_DIR, "asset_originals", feature, rel)
    if not os.path.exists(dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(current, dest)
        _ASSET_BACKUP_OF[os.path.normcase(os.path.abspath(current))] = dest
        return dest
    return keep(dest, current)


_ASSET_BACKUP_OF = {}          # normcase(abspath(asset)) -> the kept original its repairs are recorded with

REPAIRED_SIDECAR = ".repaired.sha256"


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _repaired_hashes(backup):
    try:
        with open(backup + REPAIRED_SIDECAR, encoding="ascii", errors="ignore") as f:
            return {ln.strip() for ln in f if ln.strip()}
    except OSError:
        return set()


def keep_new_original(backup, current):
    """`backup` keeps an original of `current`. If `current` is neither that original, nor a repair these
    tools wrote (recorded in <backup>.repaired.sha256), nor an original dated earlier, it is a new original
    (a mod update): keep a copy as <backup name>.YYYYMMDD-HHMMSS<ext> beside it. Returns the path holding
    current's original (the dated copy, or `backup`)."""
    _ASSET_BACKUP_OF[os.path.normcase(os.path.abspath(current))] = backup
    try:
        h = _sha256_file(current)
        if h == _sha256_file(backup) or h in _repaired_hashes(backup):
            return backup
        root, ext = os.path.splitext(backup)
        folder, stem = os.path.split(root)
        pat = re.compile(re.escape(stem) + r"\.\d{8}-\d{6}" + re.escape(ext) + "$", re.IGNORECASE)
        for fn in sorted(os.listdir(folder)):
            if pat.match(fn) and _sha256_file(os.path.join(folder, fn)) == h:
                return os.path.join(folder, fn)
        dated = f"{root}.{time.strftime('%Y%m%d-%H%M%S')}{ext}"
        k = 2
        while os.path.exists(dated):
            dated = f"{root}.{time.strftime('%Y%m%d-%H%M%S')}-{k}{ext}"
            k += 1
        shutil.copy2(current, dated)
        return dated
    except OSError:
        return backup


def replace_asset_in_place(path, data):
    """Write new contents into the existing file (checked temp copy first, then copied over in place): a
    Vortex hard link stays a hard link, so the mod folder's copy gets the same repair. The repair's hash is
    recorded next to the file's kept original, so a later run can tell a repair from a new original."""
    data = bytes(data)
    safe_write_bytes(path, data)
    backup = _ASSET_BACKUP_OF.get(os.path.normcase(os.path.abspath(path)))
    if backup and os.path.exists(backup):
        try:
            with open(backup + REPAIRED_SIDECAR, "a", encoding="ascii") as f:
                f.write(hashlib.sha256(data).hexdigest() + "\n")
        except OSError:
            pass


def reduce_textures(data_dir, game_dir, items, log):
    """Shrink each texture to TEXTURE_MAX_EDGE by dropping its largest mipmap levels. A Vortex-deployed
    file (a hard link) is replaced by a new file, so the staging folder keeps the full-size one; any
    other file is moved to mwdialog_fullsize_textures first. Recorded for --restore-textures."""
    done, saved = [], 0
    rec_path = os.path.join(game_dir, REDUCED_RECORD)
    for full, _rel, _w, _h, size in items:
        rel = os.path.relpath(full, data_dir)        # under Data Files (Textures\\...), as the record keeps it
        try:
            with open(full, "rb") as f:
                data = f.read()
            new, dims = dds_reduce(data)
            if new is None:
                continue
            links = hard_link_names(full) if os.stat(full).st_nlink > 1 else []
            if links:
                kind, keep = "link", links[0]
            else:
                kind, keep = "backup", os.path.join(game_dir, FULLSIZE_DIR, rel)
                os.makedirs(os.path.dirname(keep), exist_ok=True)
                shutil.move(full, keep)
            tmp = full + ".mwdtmp"
            with open(tmp, "wb") as f:
                f.write(new)
            os.replace(tmp, full)                    # a new file: a hard link's other copy is untouched
            done.append((rel, kind, keep))
            saved += len(data) - len(new)
            log.append(("Data Files", f"texture '{rel}' was {dims[0]}x{dims[1]}",
                        f"reduced to {dims[2]}x{dims[3]} (original kept in {'Vortex staging' if kind == 'link' else FULLSIZE_DIR})"))
        except (OSError, struct.error) as e:
            log.append(("Data Files", f"texture '{rel}'", f"NOT reduced ({e})"))
    if done:
        new_rec = not os.path.exists(rec_path)
        with open(rec_path, "a", encoding="utf-8") as f:
            if new_rec:
                f.write("; Textures mwdialog_check.py --fix reduced to 2048. One per line: path under Data Files,\n"
                        "; 'link' (the original is the Vortex staging file named) or 'backup' (moved there).\n"
                        "; --restore-textures puts the originals back.\n")
            bases = record_bases(game_dir)
            for rel, kind, keep in done:
                f.write(f"{rel}\t{kind}\t{MP.store_path(keep, bases)}\n")
    return len(done), saved


def run_restore_textures(args):
    """--restore-textures: put back the full-size textures --fix reduced (re-linking Vortex's copy)."""
    data_dir = os.path.abspath(args.data_dir)
    rec_path = os.path.join(os.path.dirname(data_dir), REDUCED_RECORD)
    try:
        with open(rec_path, "r", encoding="utf-8") as f:
            rows = [l.rstrip("\r\n").split("\t") for l in f if l.strip() and not l.startswith(";")]
    except OSError:
        print("--restore-textures: no reduced textures recorded.")
        return 0
    back, missing = 0, []
    for row in rows:
        if len(row) < 3:
            continue
        rel, kind, keep = row[0], row[1], row[2]
        keep = MP.resolve_stored(keep, record_bases(os.path.dirname(data_dir)))
        dest = os.path.join(data_dir, rel)
        if not os.path.exists(keep):
            missing.append(rel)
            continue
        if args.dry_run:
            print(f"  would restore {rel} from {keep}")
            continue
        if os.path.exists(dest):
            os.remove(dest)
        if kind == "link":
            try:
                os.link(keep, dest)                   # the same hard link Vortex made
            except OSError:
                shutil.copy2(keep, dest)
        else:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(keep, dest)
        back += 1
    if not args.dry_run:
        os.remove(rec_path)
        print(f"  Restored {back} full-size texture(s)."
              + (f" {len(missing)} original(s) no longer exist and were skipped, e.g. {missing[0]}" if missing else ""))
    return 0


def find_vortex_root(data_dir, tries=40):
    """Vortex deploys by hard links: another name of a deployed file is <staging>\\<mod>\\<file>.
    Returns the staging folder (most common answer over a few linked plugins), or None."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.FindFirstFileNameW.restype = wintypes.HANDLE
    k32.FindFirstFileNameW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR]
    k32.FindNextFileNameW.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR]
    k32.FindClose.argtypes = [wintypes.HANDLE]
    votes = Counter()
    seen = 0
    for fn in os.listdir(data_dir):
        p = os.path.join(data_dir, fn)
        if not fn.lower().endswith((".esp", ".esm")):
            continue
        try:
            if os.stat(p).st_nlink < 2:
                continue
        except OSError:
            continue
        seen += 1
        if seen > tries:
            break
        names = []
        buf = ctypes.create_unicode_buffer(1024)
        n = wintypes.DWORD(1024)
        h = k32.FindFirstFileNameW(p, 0, ctypes.byref(n), buf)
        if h in (None, wintypes.HANDLE(-1).value):
            continue
        names.append(buf.value)
        while True:
            n = wintypes.DWORD(1024)
            if not k32.FindNextFileNameW(h, ctypes.byref(n), buf):
                break
            names.append(buf.value)
        k32.FindClose(h)
        drive = os.path.splitdrive(os.path.abspath(p))[0]
        here = os.path.normcase(os.path.abspath(p))
        for nm in names:
            full = os.path.normcase(drive + nm)
            if full != here and full.endswith(os.sep + fn.lower()):
                votes[os.path.dirname(os.path.dirname(drive + nm))] += 1
    return votes.most_common(1)[0][0] if votes else None


FOLLOWUP_RE = re.compile(r"(?i)(?:(?<=[\s_\-(\[])|^)(patch|revamp(ed)?|improved|edit(ed)?|fix(ed|es)?|tweaks?|add-?on|"
                         r"remaster(ed)?|rebalance|redux|reworked|update[d]?|compat(ibility)?|replacer|integrated|"
                         r"version|v\d[\d._]*|\d+\.\d+[\d.]*)(?=$|[\s_\-)\]])")


def original_mod_guess(plugin):
    """'Concept Art Hlaalu Balconies - Balmora.esp' style follow-ups: the part before the edit words."""
    base = os.path.splitext(plugin)[0]
    m = FOLLOWUP_RE.search(base)
    if not m and " - " not in base:
        return None
    cut = base[:m.start()] if m else base.split(" - ")[0]
    cut = re.sub(r"[(\[][^)\]]*$", "", cut)            # an unclosed "(RP" left by the cut
    cut = re.sub(r"[\s_\-()\[\]]+$", "", cut).strip()
    return cut if cut and cut.lower() != base.lower() else None


REDUCED_RECORD = "mwdialog_reduced_textures.txt"

FULLSIZE_DIR = "mwdialog_fullsize_textures"


def write_generated(data_dir, game_dir, items, log):
    """Create the silent stand-in files (never over an existing file); record them for --remove-generated."""
    rec_path = os.path.join(game_dir, GENERATED_RECORD)
    made = []
    owner = {}
    for item in items:
        rel, why, source = (item + (None,))[:3]
        owner[rel.lower()] = item[3] if len(item) > 3 and item[3] else ""
        full = os.path.join(data_dir, rel)
        if os.path.exists(full):
            continue
        os.makedirs(os.path.dirname(full), exist_ok=True)
        if source and os.sep + ".orphaned" + os.sep in source.lower():
            os.replace(source, full)                       # a move back, not a new file: not recorded
            log.append(("Data Files", f"'{rel}' ({why}) had been moved to .Orphaned", "moved it back"))
            continue
        if source and os.path.basename(source).lower().startswith("mwdialog_dummy"):
            shutil.copy2(source, full)                     # a stand-in model under the name the record expects
            log.append(("Data Files", f"'{rel}' is needed by {why} but doesn't exist",
                        f"put a copy of {os.path.basename(source)} there (the plugin is unchanged)"))
        elif source:
            shutil.copy2(source, full)
            log.append(("Data Files", f"'{rel}' ({why}) wasn't deployed", f"copied it from {source}"))
        else:
            with open(full, "wb") as f:
                f.write(stand_in_bytes(rel))
            what = ("a placeholder model (coin)" if rel.lower().endswith(".nif") else
                    "a placeholder icon" if rel.lower().replace("/", "\\").startswith("icons\\") else
                    "a placeholder texture" if rel.lower().endswith(".dds") else "a silent stand-in")
            log.append(("Data Files", f"'{rel}' is needed by {why} but doesn't exist", f"created {what}"))
        made.append(rel)
    if made:
        entries = read_generated_record(rec_path)          # earlier runs' files, with the plugin each was for
        for rel in made:
            try:
                size = str(os.path.getsize(os.path.join(data_dir, rel)))
            except OSError:
                size = ""
            entries[rel.lower()] = (rel, size, owner.get(rel.lower(), ""))
        write_generated_record(rec_path, entries)
    return made


def run_remove_generated(args):
    """--remove-generated: delete the silent stand-in files --fix created."""
    data_dir = os.path.abspath(args.data_dir)
    rec_path = os.path.join(os.path.dirname(data_dir), GENERATED_RECORD)
    try:
        with open(rec_path, "r", encoding="utf-8") as f:
            rels = [l.rstrip("\r\n").split("\t") for l in f if l.strip() and not l.startswith((";", "["))]
    except OSError:
        print("--remove-generated: nothing recorded.")
        return 0
    gone, kept = 0, []
    for parts in {p[0].lower(): p for p in rels}.values():
        rel, size = parts[0].strip(), (int(parts[1]) if len(parts) > 1 and parts[1].strip().isdigit() else None)
        full = os.path.join(data_dir, rel)
        if not os.path.isfile(full):
            continue
        if size is not None and os.path.getsize(full) != size:
            kept.append(rel)                   # replaced since (a mod or a restore put the real file there)
            continue
        if args.dry_run:
            print(f"  would delete {rel}")
        else:
            os.remove(full)
            gone += 1
    if kept:
        print(f"  Left {len(kept)} file(s) alone: they changed since --fix made them (now the real files), "
              f"e.g. {kept[0]}")
    if not args.dry_run:
        os.remove(rec_path)
        print(f"  Deleted {gone} silent stand-in file(s).")
    return 0
