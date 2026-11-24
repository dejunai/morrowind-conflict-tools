"""mwdialog_restore.py - putting things back: a plugin's newest backup, every backup, the dates a sort
changed, and clearing out backups nobody needs.
"""
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_text as MT  # noqa: E402
import mwdialog_tes3 as _T  # noqa: E402
from mwdialog_backup import (  # noqa: E402
    backup_candidates, backup_path, index_dir)
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


def run_clean_up(args):
    """Delete the backups between each plugin's original (the oldest) and its newest. A plugin that isn't in
    Data Files keeps all of its backups: while Vortex is purged that is every plugin."""
    data_dir = args.data_dir
    doomed = []
    for name, path in sorted(index_dir(data_dir).items()):
        if not name.endswith((".esp", ".esm", ".omwaddon")):
            continue
        baks = backup_candidates(path)              # oldest first
        if len(baks) > 2:
            print(f"    - {os.path.basename(path)}: {len(baks) - 2} in between; keeping the oldest and the newest")
            doomed += baks[1:-1]
    if not doomed:
        print("  Nothing to clean up: no plugin has backups between its oldest and its newest.")
        return 0
    if args.dry_run:
        print("\nDry run: no files were deleted.")
        return 0
    if not args.yes:
        if not sys.stdin.isatty():
            print("\nNot running interactively; add --yes to delete them.")
            return 1
        if input(f"\nDelete {len(doomed)} backup file(s)? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Nothing deleted.")
            return 0
    freed, done, lines = 0, 0, []
    for p in doomed:
        try:
            n = os.path.getsize(p)
            os.remove(p)
            freed += n
            done += 1
            lines.append(f"deleted backup {os.path.basename(p)}")
        except OSError as e:
            print(f"  {os.path.basename(p)}: NOT deleted ({e})")
    with MT.open_log(args.fix_log, "a", encoding="utf-8") as f:
        import datetime
        f.write(f"\n==== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} clean-up ====\n")
        f.write("".join(l + "\n" for l in lines))
    print(f"\nDeleted {done} backup file(s), {freed / 1048576:.1f} MB freed. Logged to {args.fix_log}.")
    return 0


def restore_all(data_dir, assume_yes, fix_log):
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
