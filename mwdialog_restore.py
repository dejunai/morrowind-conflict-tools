"""mwdialog_restore.py - putting things back: a plugin's newest backup, every backup, the dates a sort
changed, and clearing out backups nobody needs.
"""
import hashlib
import json
import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_text as MT  # noqa: E402
import mwdialog_tes3 as _T  # noqa: E402
from mwdialog_backup import (  # noqa: E402
    backup_candidates, backup_path, index_dir)
from mwdialog_state import (  # noqa: E402
    read_disabled, read_merge_rebuild, read_merge_record, read_redundant)
from mwdialog_console import (  # noqa: E402
    print)
from mwdialog_patchfile import (  # noqa: E402
    PATCH_NAME)
from mwdialog_redundant import (  # noqa: E402
    OUR_PATCHES)
from mwdialog_tes3 import (  # noqa: E402
    safe_write_bytes)
import mwdialog_paths as MP  # noqa: E402


def restore_backups(names, data_dir):
    """Put the newest mwdialog_check backup back over each plugin, keeping its original date."""
    lookup = index_dir(data_dir)
    code = 0
    for n in names:
        path = lookup.get(n.lower())
        if not path:
            print(f"  {n}: not found in Data Files")
            code = 1
            continue
        existing = backup_candidates(path)
        if not existing:
            print(f"  {n}: no backup found")
            code = 1
            continue
        bak = existing[-1]                       # highest number = most recent backup
        st = os.stat(bak)                        # copy2 kept the plugin's original date on it
        with open(bak, "rb") as f:
            data = f.read()
        try:
            safe_write_bytes(path, data, keep_times=st)     # in place, so hard links (Vortex) stay intact
            with open(path, "rb") as f:
                ok = f.read() == data
        except OSError as e:
            print(f"  {n}: NOT restored ({e}); the backup {os.path.basename(bak)} is kept")
            code = 1
            continue
        if not ok:
            print(f"  {n}: restored copy doesn't match {os.path.basename(bak)}; the backup is kept")
            code = 1
            continue
        os.remove(bak)
        print(f"  {n}: restored from {os.path.basename(bak)} (backup removed)")
    return code


BAK_RE = re.compile(r"^(?P<plugin>.+\.(?:esp|omwaddon))\.bak(?P<n>\d*)$", re.I)

CLEANUP_BAK_RE = re.compile(r"^(?P<plugin>.+\.(?:esp|esm|omwaddon))\.bak(?P<n>\d*)$", re.I)


PLUGIN_EXTS = (".esp", ".esm", ".omwaddon")
# folders the tools use to park plugins or assets that must not be deployed
PARK_DIR_NAMES = frozenset({
    "grass", "off", "extras", "docs", "openmw", "bugreports", "mcpatch",
})
# generated plugins the tools may set aside as backups only (OUR_PATCHES + AutoMerge)
SET_ASIDE_NAMES = {x.lower() for x in OUR_PATCHES} | {"mwdialog_check automerge.esp"}
CLEANUP_JOURNAL = "mwdialog_cleanup_journal.jsonl"
CLEANUP_OFF_FEATURE = "cleanup"


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _add_plugin_file(present, path):
    name = os.path.basename(path)
    if name.lower().endswith(PLUGIN_EXTS):
        present.add(name.lower())


def _scan_dir_for_plugins(folder, present, recursive=False):
    """Add plugin basenames under folder. False if the folder could not be listed fully."""
    try:
        entries = os.listdir(folder)
    except OSError:
        return False
    ok = True
    for fn in entries:
        path = os.path.join(folder, fn)
        try:
            if os.path.isfile(path):
                _add_plugin_file(present, path)
            elif recursive and os.path.isdir(path):
                if not _scan_dir_for_plugins(path, present, True):
                    ok = False
        except OSError:
            ok = False
    return ok


def _scan_park_tree(root, present):
    """Scan known park folders directly under root."""
    try:
        entries = os.listdir(root)
    except OSError:
        return False
    ok = True
    for fn in entries:
        if fn.lower() in PARK_DIR_NAMES:
            if not _scan_dir_for_plugins(os.path.join(root, fn), present, recursive=True):
                ok = False
    return ok


def _grass_plugin_names(game_dir):
    """Basenames of plugins MGE XE lists as generator-only grass."""
    out = set()
    toml = os.path.join(game_dir, "mgeXE.toml")
    try:
        text = open(toml, "r", encoding="utf-8", errors="replace").read()
    except OSError:
        return out
    m = re.search(r"^\s*grass_plugins\s*=\s*\[(.*?)\]", text, re.S | re.M)
    if not m:
        return out
    for q in re.findall(r"'([^']+)'|\"([^\"]+)\"", m.group(1)):
        p = q[0] or q[1]
        out.add(os.path.basename(p).lower())
    return out


def _record_plugin_names(game_dir):
    """Plugins the tools have recorded as merged, disabled, redundant, or a generated set-aside."""
    names = set(SET_ASIDE_NAMES)
    rec = read_merge_record(game_dir)
    for merged, ins in rec.items():
        names.add(merged.lower())
        names.update(i.lower() for i in ins)
    names.update(n.lower() for n in read_disabled(game_dir))
    names.update(n.lower() for n in read_redundant(game_dir)[0])
    for merged, ins in read_merge_rebuild(game_dir).items():
        names.add(merged.lower())
        names.update(i.lower() for i in ins)
    names.update(_grass_plugin_names(game_dir))
    return names


def _staging_scan(args, data_dir, present):
    """Add plugin basenames found in this game's Vortex staging.

    Returns False when staging was expected but could not be read (presence is uncertain).
    Uses args.vortex_dir when set, else hard-link detection from this Data Files only
    (not the machine-wide Vortex settings, so a test game is not mixed with a real install).
    --no-vortex skips the scan and reports uncertain: a purge would otherwise look like
    every plugin had been uninstalled.
    """
    if getattr(args, "no_vortex", False):
        return False
    cli = getattr(args, "vortex_dir", None)
    path = None
    if cli:
        path = os.path.abspath(cli)
        if not os.path.isdir(path):
            return False
    else:
        try:
            from mwdialog_generated import find_vortex_root
            path = find_vortex_root(data_dir)
        except Exception:
            return True
        if not path:
            return True
    return _scan_dir_for_plugins(path, present, recursive=True)


def installed_or_parked(args, data_dir, game_dir):
    """({lowercase names of plugins that are installed or parked}, uncertain).

    uncertain: the inventory could not be completed, so a missing plugin must not be
    treated as gone.
    """
    present = set()
    ok = True
    if not _scan_dir_for_plugins(data_dir, present, recursive=False):
        ok = False
    if not _scan_park_tree(data_dir, present):
        ok = False
    if not _scan_park_tree(game_dir, present):
        ok = False
    try:
        present |= _record_plugin_names(game_dir)
    except (OSError, UnicodeError, ValueError):
        ok = False
    if not _staging_scan(args, data_dir, present):
        ok = False
    return present, not ok


def _iter_bak_files(folder, out, skip_off_at=None):
    """Collect .bak backups under folder. skip_off_at: a folder whose Off\\ child is skipped
    (already-shelved backups under the backups folder)."""
    try:
        names = os.listdir(folder)
    except OSError:
        return False
    ok = True
    skip = os.path.normcase(os.path.abspath(skip_off_at)) if skip_off_at else None
    here = os.path.normcase(os.path.abspath(folder))
    for fn in names:
        path = os.path.join(folder, fn)
        try:
            if os.path.isdir(path):
                if skip is not None and here == skip and fn.lower() == "off":
                    continue
                if not _iter_bak_files(path, out, skip_off_at=skip_off_at):
                    ok = False
            elif CLEANUP_BAK_RE.match(fn):
                out.append(path)
        except OSError:
            ok = False
    return ok


def _plugin_path_from_bak(bak, data_dir, game_dir, roots):
    """The plugin path a backup belongs to (the file it would restore)."""
    m = CLEANUP_BAK_RE.match(os.path.basename(bak))
    if not m:
        return None
    plugin = m.group("plugin")
    for root in roots:
        try:
            rel = os.path.relpath(bak, root)
        except ValueError:
            continue
        if rel.startswith(".."):
            continue
        parts = rel.replace("\\", "/").split("/")
        if parts and parts[0].lower() == "legacy":
            parts = parts[1:]
        if parts and parts[0].lower() == "off":
            return None
        if not parts:
            continue
        plugin_rel = "/".join(parts[:-1] + [plugin]) if len(parts) > 1 else plugin
        return os.path.join(game_dir, plugin_rel.replace("/", os.sep))
    return os.path.join(os.path.dirname(bak), plugin)


def discover_plugin_backups(data_dir, game_dir):
    """{lowercase plugin name: (canonical plugin path, backups oldest first)}.
    Returns (groups, scan_ok)."""
    from mwdialog_backup import BACKUP_DIR, backup_root

    roots = [backup_root(game_dir)]
    old = os.path.join(game_dir, BACKUP_DIR)
    if os.path.normcase(os.path.abspath(old)) != os.path.normcase(os.path.abspath(roots[0])):
        roots.append(old)
    baks = []
    ok = True
    if not _iter_bak_files(data_dir, baks):
        ok = False
    for root in roots:
        if os.path.isdir(root) and not _iter_bak_files(root, baks, skip_off_at=root):
            ok = False
    paths_for = {}
    try:
        for fn in os.listdir(data_dir):
            if fn.lower().endswith(PLUGIN_EXTS):
                paths_for.setdefault(fn.lower(), set()).add(os.path.join(data_dir, fn))
    except OSError:
        ok = False
    for bak in baks:
        m = CLEANUP_BAK_RE.match(os.path.basename(bak))
        if not m:
            continue
        plugin_path = _plugin_path_from_bak(bak, data_dir, game_dir, roots)
        if plugin_path is None:
            continue
        paths_for.setdefault(m.group("plugin").lower(), set()).add(plugin_path)
    groups = {}
    for name, candidates in paths_for.items():
        data_dir_n = os.path.normcase(os.path.abspath(data_dir))
        canon = None
        for p in sorted(candidates, key=lambda x: os.path.normcase(x)):
            if os.path.normcase(os.path.abspath(os.path.dirname(p))) == data_dir_n:
                canon = p
                break
        if canon is None:
            canon = sorted(candidates, key=lambda x: os.path.normcase(x))[0]
        found, seen = [], set()
        for p in [canon] + [c for c in candidates if os.path.normcase(c) != os.path.normcase(canon)]:
            for b in backup_candidates(p):
                key = os.path.normcase(os.path.abspath(b))
                if key not in seen:
                    seen.add(key)
                    found.append(b)
        groups[name] = (canon, found)
    return groups, ok


def off_backup_dest(path, game_dir):
    """Where to shelve a backup: <backups>\\Off\\cleanup\\<path relative to the backups folder or game>."""
    from mwdialog_backup import BACKUP_DIR, backup_root

    path = os.path.abspath(path)
    roots = [backup_root(game_dir), os.path.join(game_dir, BACKUP_DIR), game_dir]
    rel = None
    for root in roots:
        try:
            cand = os.path.relpath(path, os.path.abspath(root))
        except ValueError:
            continue
        if not cand.startswith(".."):
            rel = cand
            break
    if rel is None:
        rel = os.path.basename(path)
    dest = os.path.join(backup_root(game_dir), "Off", CLEANUP_OFF_FEATURE, rel)
    if not os.path.exists(dest):
        return dest
    try:
        if _sha256_file(dest) == _sha256_file(path):
            return dest
    except OSError:
        pass
    root, ext = os.path.splitext(dest)
    n = 2
    while os.path.exists(dest):
        dest = "%s-%d%s" % (root, n, ext)
        n += 1
    return dest


def cleanup_journal_path(game_dir):
    return MP.state_path(game_dir, CLEANUP_JOURNAL)


def _read_cleanup_runs(journal):
    runs, cur = [], None
    with open(journal, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                print("  (skipped an unreadable journal line: %r)" % (line[:80],), file=sys.stderr)
                continue
            if "run" in rec:
                cur = {"head": rec, "ops": []}
                runs.append(cur)
            elif cur is not None:
                cur["ops"].append(rec)
    return runs


def _write_cleanup_runs(journal, runs):
    tmp = journal + ".tmp"
    with open(tmp, "w", encoding="utf-8") as j:
        for r in runs:
            j.write(json.dumps(r["head"]) + "\n")
            for op in r["ops"]:
                j.write(json.dumps(op) + "\n")
    os.replace(tmp, journal)


def _journal_moves(journal, moves):
    """Append one clean-up run: moves is [(src, dest, sha256)]. Journaled before the caller relies on it."""
    os.makedirs(os.path.dirname(os.path.abspath(journal)), exist_ok=True)
    with open(journal, "a", encoding="utf-8") as j:
        j.write(json.dumps({"run": time.strftime("%Y-%m-%d %H:%M:%S"), "what": "clean-up"}) + "\n")
        for src, dest, digest in moves:
            j.write(json.dumps({"src": src, "dest": dest, "sha256": digest}) + "\n")
        j.flush()
        os.fsync(j.fileno())


def _restore_shelved(op):
    """Put one shelved backup back. (True, msg) or (False, why)."""
    src, dest, digest = op["src"], op["dest"], op["sha256"]
    try:
        if not os.path.exists(dest):
            if os.path.exists(src):
                try:
                    if _sha256_file(src) == digest:
                        return True, "%s: already back" % src
                except OSError:
                    pass
            return False, "%s: the Off copy is missing" % dest
        got = _sha256_file(dest)
    except OSError as e:
        return False, "%s: %s" % (dest, e)
    if got != digest:
        return False, "%s: changed since it was moved (not put back)" % dest
    if os.path.exists(src):
        try:
            if _sha256_file(src) == digest:
                os.remove(dest)
                return True, "%s: already back" % src
        except OSError:
            pass
        return False, "%s: a different file is already there (not overwritten)" % src
    try:
        os.makedirs(os.path.dirname(src), exist_ok=True)
        shutil.move(dest, src)
    except OSError as e:
        return False, "%s: not put back (%s)" % (src, e)
    return True, "%s: put back" % src


def run_clean_up_undo(args):
    """Put back the backups the last --clean-up moved to Off\\cleanup."""
    game_dir = os.path.dirname(os.path.abspath(args.data_dir))
    journal = cleanup_journal_path(game_dir)
    if not os.path.exists(journal):
        print("Nothing to undo (no clean-up journal).")
        return 1
    runs = _read_cleanup_runs(journal)
    if not runs:
        print("Nothing to undo.")
        return 1
    last = runs.pop()
    left, n, lines = [], 0, []
    for op in reversed(last["ops"]):
        ok, msg = _restore_shelved(op)
        print("  " + msg)
        if ok:
            n += 1
            lines.append(msg)
        else:
            left.append(op)
    if left:
        runs.append({"head": last["head"], "ops": list(reversed(left))})
    _write_cleanup_runs(journal, runs)
    with MT.open_log(args.fix_log, "a", encoding="utf-8") as f:
        f.write("\n==== %s clean-up-undo ====\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        f.write("".join(l + "\n" for l in lines))
    print("Put back %d backup(s) moved by the clean-up of %s." % (n, last["head"].get("run", "?")))
    return 1 if left else 0


def run_clean_up(args):
    """Delete the backups between each installed or parked plugin's oldest and newest. Delete every
    backup of a plugin that is no longer installed anywhere and not parked (disabled, merged,
    redundant, a generated patch set aside, Off\\, Grass\\, Extras\\, or Vortex staging). When that
    cannot be determined, move those backups to <backups>\\Off\\cleanup\\ (same relative names) and
    journal the moves so --clean-up-undo can put them back."""
    data_dir = args.data_dir
    game_dir = os.path.dirname(os.path.abspath(data_dir))
    present, uncertain = installed_or_parked(args, data_dir, game_dir)
    groups, scan_ok = discover_plugin_backups(data_dir, game_dir)
    if not scan_ok:
        uncertain = True

    in_between = []          # (label, paths to delete)
    orphans = []             # (label, all bak paths) confirmed gone
    shelved = []             # (label, all bak paths) cannot confirm gone

    for name, (path, baks) in sorted(groups.items()):
        if not baks:
            continue
        label = os.path.basename(path)
        if name in present:
            if len(baks) > 2:
                print("    - %s: %d in between; keeping the oldest and the newest" % (label, len(baks) - 2))
                in_between.append((label, baks[1:-1]))
        elif uncertain:
            print("    - %s: %d backup(s); cannot confirm the plugin is gone, would move them to Off\\cleanup\\"
                  % (label, len(baks)))
            shelved.append((label, baks))
        else:
            print("    - %s: no longer installed or parked; %d backup(s) would be deleted" % (label, len(baks)))
            orphans.append((label, baks))

    doomed = [p for _n, paths in in_between for p in paths] + [p for _n, paths in orphans for p in paths]
    if not doomed and not shelved:
        print("  Nothing to clean up: no in-between backups, no orphans, nothing to move to Off.")
        return 0

    if orphans:
        print("\n  Orphans (plugin gone; every backup would be deleted):")
        for label, baks in orphans:
            print("    - %s (%d)" % (label, len(baks)))
    if shelved:
        print("\n  Uncertain (cannot confirm gone; backups would be moved to Off\\cleanup\\):")
        for label, baks in shelved:
            print("    - %s (%d)" % (label, len(baks)))

    if args.dry_run:
        print("\nDry run: no files were deleted or moved.")
        return 0
    if not args.yes:
        if not sys.stdin.isatty():
            print("\nNot running interactively; add --yes to delete or move them.")
            return 1
        bits = []
        if doomed:
            bits.append("delete %d backup file(s)" % len(doomed))
        if shelved:
            bits.append("move %d backup file(s) to Off\\cleanup\\"
                        % sum(len(b) for _n, b in shelved))
        if input("\n%s? [y/N] " % " and ".join(bits)).strip().lower() not in ("y", "yes"):
            print("Nothing deleted or moved.")
            return 0

    freed, done, lines = 0, 0, []
    for p in doomed:
        try:
            n = os.path.getsize(p)
            os.remove(p)
            freed += n
            done += 1
            lines.append("deleted backup %s" % os.path.basename(p))
        except OSError as e:
            print("  %s: NOT deleted (%s)" % (os.path.basename(p), e))

    moves = []
    for label, baks in shelved:
        for p in baks:
            try:
                digest = _sha256_file(p)
                dest = off_backup_dest(p, game_dir)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                if os.path.normcase(os.path.abspath(p)) != os.path.normcase(os.path.abspath(dest)):
                    if os.path.exists(dest) and _sha256_file(dest) == digest:
                        os.remove(p)
                    else:
                        shutil.move(p, dest)
                moves.append((os.path.abspath(p), os.path.abspath(dest), digest))
                lines.append("moved backup %s -> %s" % (p, dest))
                print("  %s: moved to %s" % (os.path.basename(p), dest))
            except OSError as e:
                print("  %s: NOT moved (%s)" % (os.path.basename(p), e))
    if moves:
        try:
            _journal_moves(cleanup_journal_path(game_dir), moves)
        except OSError as e:
            print("  (could not write the clean-up journal: %s)" % e, file=sys.stderr)

    with MT.open_log(args.fix_log, "a", encoding="utf-8") as f:
        f.write("\n==== %s clean-up ====\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        if orphans:
            f.write("orphans (every backup deleted):\n")
            for label, baks in orphans:
                f.write("  %s (%d)\n" % (label, len(baks)))
        if shelved:
            f.write("uncertain (moved to Off\\cleanup\\):\n")
            for label, baks in shelved:
                f.write("  %s (%d)\n" % (label, len(baks)))
        f.write("".join(l + "\n" for l in lines))
    parts = ["Deleted %d backup file(s), %.1f MB freed" % (done, freed / 1048576.0)]
    if moves:
        parts.append("moved %d to Off\\cleanup\\" % len(moves))
    print("\n%s. Logged to %s." % ("; ".join(parts), args.fix_log))
    return 0


def restore_all(data_dir, assume_yes, fix_log, dry_run=False):
    """Put every plugin back to its OLDEST backup (the original). What is replaced is backed up first and no
    backup is removed: the file there may be a newer version of the mod (--restore NAME brings it back)."""
    ours = {x.lower() for x in OUR_PATCHES}
    groups = {}                                    # plugin path -> its backups, oldest first
    lookup = index_dir(data_dir)
    for name, path in lookup.items():
        if name.endswith((".esp", ".omwaddon")) and name not in ours:
            baks = backup_candidates(path)
            if baks:
                groups[path] = baks
    if not groups:
        print("No plugin backups found.")
        return 0
    print("These plugins will be put back to their original (oldest) backup; what is there now is backed up first:")
    for path, baks in sorted(groups.items(), key=lambda kv: kv[0].lower()):
        print(f"  {os.path.basename(path)}  <- {os.path.basename(baks[0])}")
    patch = lookup.get(PATCH_NAME.lower())
    if patch:
        print(f"\n'{PATCH_NAME}' is left as it is; the next --fix rebuilds it from scratch.")
    if dry_run:
        print("(dry run: nothing changed)")
        return 0
    if not assume_yes:
        if not sys.stdin.isatty():
            print("\nNot running interactively; add --yes to restore.")
            return 1
        if input(f"\nRestore {len(groups)} plugin(s)? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Nothing changed.")
            return 0
    done, lines = 0, []
    for path, baks in groups.items():
        oldest = baks[0]
        try:
            st = os.stat(oldest)                   # copy2 kept the plugin's original date on it
            with open(oldest, "rb") as f:
                data = f.read()
            with open(path, "rb") as f:
                now = f.read()
            if now == data:
                continue
            bak = backup_path(path)
            shutil.copy2(path, bak)
            safe_write_bytes(path, data, keep_times=st)     # in place, so hard links (Vortex) stay intact
            with open(path, "rb") as f:
                if f.read() != data:
                    raise OSError("the restored copy doesn't match the backup")
            done += 1
            lines.append(f"{os.path.basename(path)}: restored from {os.path.basename(oldest)} "
                         f"(what was there: {os.path.basename(bak)})")
        except OSError as e:
            print(f"  {os.path.basename(path)}: NOT restored ({e})")
    with MT.open_log(fix_log, "a", encoding="utf-8") as f:
        import datetime
        f.write(f"\n==== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} restore-all ====\n")
        f.write("".join(l + "\n" for l in lines))
    print(f"Restored {done} plugin(s) to their originals.")
    return 0


DATES_UNDO_FILE = "mwdialog_loadorder_undo.txt"


def restore_dates(args):
    game_dir = os.path.dirname(os.path.abspath(args.data_dir))
    undo = MP.state_path(game_dir, DATES_UNDO_FILE)
    try:
        with open(undo, "r", encoding="utf-8") as f:
            blocks = f.read().split("==== ")
    except OSError:
        print("No saved dates to restore.")
        return 1
    blocks = [b for b in blocks if b.strip()]
    if not blocks:
        print("No saved dates to restore.")
        return 1
    last = blocks[-1].splitlines()
    lookup = index_dir(args.data_dir)
    n = 0
    for line in last[1:]:
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].lower() in lookup:
            os.utime(lookup[parts[0].lower()], ns=(int(parts[1]), int(parts[2])))
            n += 1
    with _T.atomic_open(undo, encoding="utf-8") as f:
        f.write("".join("==== " + b for b in blocks[:-1]))
    print(f"Restored the dates of {n} plugin(s) from the sort of {last[0].strip()}.")
    return 0
