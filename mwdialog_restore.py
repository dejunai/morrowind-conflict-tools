"""mwdialog_restore.py - putting things back: a plugin's newest backup, every backup, the dates a sort
changed, and clearing out backups nobody needs.
"""
from collections import defaultdict
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_text as MT  # noqa: E402
from mwdialog_backup import (  # noqa: E402
    backup_candidates, backup_index, index_dir)
from mwdialog_console import (  # noqa: E402
    print)
from mwdialog_patchfile import (  # noqa: E402
    PATCH_NAME)
from mwdialog_redundant import (  # noqa: E402
    OUR_PATCHES)
from mwdialog_tes3 import (  # noqa: E402
    safe_write_bytes)


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
    """Delete backups of plugins that are gone, and keep only the most recent backup of the rest."""
    data_dir = args.data_dir
    lookup = backup_index(data_dir)
    groups = defaultdict(list)                       # plugin name lower -> [(n, backup path)]
    for low, path in lookup.items():
        m = CLEANUP_BAK_RE.match(low)
        if m and os.path.isfile(path):
            groups[m.group("plugin")].append((int(m.group("n") or 1), path))
    if not groups:
        print("No plugin backups (.bak) found.")
        return 0
    gone, old = [], []                               # backups to delete
    kept = {}
    for plugin, baks in groups.items():
        baks.sort()                                  # .bak, .bak2, .bak3 ...: highest number = most recent
        if plugin not in lookup:
            gone += [p for _n, p in baks]
        else:
            kept[plugin] = baks[-1][1]
            old += [p for _n, p in baks[:-1]]
    size = lambda paths: sum(os.path.getsize(p) for p in paths)
    print(f"{sum(len(b) for b in groups.values())} backup(s) of {len(groups)} plugin(s) in {data_dir}")
    if gone:
        print(f"\n  Plugin no longer in Data Files, so all its backups go ({len(gone)}, {size(gone) / 1048576:.1f} MB):")
        for p in sorted(gone, key=str.lower):
            print(f"    - {os.path.basename(p)}")
    if old:
        print(f"\n  Older backups of plugins that are still here ({len(old)}, {size(old) / 1048576:.1f} MB); "
              f"the most recent one is kept:")
        by_plugin = defaultdict(list)
        for p in old:
            by_plugin[CLEANUP_BAK_RE.match(os.path.basename(p).lower()).group("plugin")].append(p)
        for plugin in sorted(by_plugin):
            print(f"    - {os.path.basename(lookup[plugin])}: {len(by_plugin[plugin])} older, "
                  f"keeping {os.path.basename(kept[plugin])}")
    doomed = gone + old
    if not doomed:
        print("  Nothing to clean up: each plugin has a single backup.")
        return 0
    print("\n  Note: --restore-all puts plugins back to their OLDEST backup. After this, that is the most "
          "recent one kept here, not the original.")
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
    """Put every plugin back to its OLDEST backup (the original) and remove all its backups."""
    lookup = backup_index(data_dir)
    groups = defaultdict(list)                     # plugin path -> [(n, backup path)]
    for low, path in lookup.items():
        m = BAK_RE.match(low)
        if m and m.group("plugin") in lookup and m.group("plugin") not in [x.lower() for x in OUR_PATCHES]:
            groups[lookup[m.group("plugin")]].append((int(m.group("n") or 1), path))
    if not groups:
        print("No plugin backups found.")
        return 0
    print("These plugins will be put back to their original (oldest) backup, and all their backups removed:")
    for path, baks in sorted(groups.items(), key=lambda kv: kv[0].lower()):
        baks.sort()
        print(f"  {os.path.basename(path)}  <- {os.path.basename(baks[0][1])}"
              + (f"  (also removing {len(baks) - 1} newer backup(s))" if len(baks) > 1 else ""))
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
        oldest = baks[0][1]
        try:
            st = os.stat(oldest)                   # copy2 kept the plugin's original date on it
            with open(oldest, "rb") as f:
                data = f.read()
            safe_write_bytes(path, data, keep_times=st)     # in place, so hard links (Vortex) stay intact
            with open(path, "rb") as f:
                if f.read() != data:
                    raise OSError("the restored copy doesn't match the backup; backups kept")
            for _n, b in baks:
                os.remove(b)
            done += 1
            lines.append(f"{os.path.basename(path)}: restored from {os.path.basename(oldest)}, {len(baks)} backup(s) removed")
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
    undo = os.path.join(game_dir, DATES_UNDO_FILE)
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
    with open(undo, "w", encoding="utf-8") as f:
        f.write("".join("==== " + b for b in blocks[:-1]))
    print(f"Restored the dates of {n} plugin(s) from the sort of {last[0].strip()}.")
    return 0
