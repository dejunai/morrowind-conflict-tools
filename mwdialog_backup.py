"""mwdialog_backup.py - where backups of plugins and record files go, and finding the newest or the
original one again.
"""
import os
import re


def index_dir(d):
    out = {}
    try:
        for fn in os.listdir(d):
            out.setdefault(fn.lower(), os.path.join(d, fn))
    except OSError:
        pass
    return out


BACKUP_DIR = "mwdialog_backup"                 # every backup these tools make goes in <game folder>\\here


def game_dir_of(path):
    """The game folder a path is in (the one holding Data Files / Morrowind.ini), else the path's folder."""
    d = os.path.dirname(os.path.abspath(path))
    probe = d
    while True:
        if os.path.isdir(os.path.join(probe, "Data Files")) or os.path.isfile(os.path.join(probe, "Morrowind.ini")):
            return probe
        up = os.path.dirname(probe)
        if up == probe:
            return d
        probe = up


def bak_home(path):
    """Where a backup of `path` goes: <game folder>\\mwdialog_backup\\<its path under the game folder>
    (Data Files\\X.esp -> mwdialog_backup\\Data Files\\X.esp); the folder is made. Add the suffix."""
    path = os.path.abspath(path)
    game = game_dir_of(path)
    rel = os.path.relpath(path, game)
    if rel.startswith(".."):
        rel = os.path.basename(path)
    home = os.path.join(game, BACKUP_DIR, rel)
    os.makedirs(os.path.dirname(home), exist_ok=True)
    return home


def backup_candidates(path):
    """Every backup of `path`, oldest first: the backup folder's (.bak, .bak2...), and, before them, any
    an earlier version left next to the file."""
    out = []
    for base in (path, os.path.join(game_dir_of(path), BACKUP_DIR, os.path.relpath(os.path.abspath(path),
                                                                                   game_dir_of(path)))):
        folder, stem = os.path.split(base)
        try:
            names = os.listdir(folder or ".")
        except OSError:
            continue
        pat = re.compile(re.escape(stem) + r"\.bak(\d*)$", re.IGNORECASE)
        found = []
        for fn in names:                             # no upper limit: .bak100 and later count too
            m = pat.match(fn)
            if m and (m.group(1) == "" or int(m.group(1)) >= 2):
                found.append((int(m.group(1) or 1), os.path.join(folder, fn)))
        out += [c for _n, c in sorted(found)]
    return out


def backup_path(path):
    """A new backup name for `path`, in the backup folder: .bak, then .bak2, .bak3... (highest = newest)."""
    base = bak_home(path)
    taken = backup_candidates(path)
    n = 1 + max([1] + [int(re.search(r"\.bak(\d*)$", c, re.IGNORECASE).group(1) or 1) for c in taken]) if taken else 1
    return base + ".bak" if n == 1 else f"{base}.bak{n}"


def backup_index(data_dir):
    """index_dir(data_dir) plus the plugin backups in the backup folder (name lower -> path)."""
    lookup = dict(index_dir(data_dir))
    home = os.path.join(game_dir_of(os.path.join(os.path.abspath(data_dir), "x")), BACKUP_DIR,
                        os.path.basename(os.path.abspath(data_dir)))
    if os.path.isdir(home):
        for fn in os.listdir(home):
            if ".bak" in fn.lower():
                lookup.setdefault(fn.lower(), os.path.join(home, fn))
    return lookup


def chain_tail(world, topic_key, exclude_source):
    """Last response of a topic among files other than `exclude_source`."""
    t = world.topics.get(topic_key)
    if t is None:
        return ""
    others = [i for i in t.infos.values() if not i.deleted and i.source.lower() != exclude_source]
    pointed = {i.prev.lower() for i in others if i.prev}
    tails = [i for i in others if i.id.lower() not in pointed]
    return tails[-1].id if tails else ""
