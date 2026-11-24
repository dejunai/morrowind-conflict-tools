"""mwdialog_backup.py - where backups of plugins and record files go, and finding the newest or the
original one again. The top of the backups folder holds one backup per file; older ones are in legacy\\.
"""
import os
import re
import time


def index_dir(d):
    out = {}
    try:
        for fn in os.listdir(d):
            out.setdefault(fn.lower(), os.path.join(d, fn))
    except OSError:
        pass
    return out


BACKUP_DIR = "mwdialog_backup"                 # backups in <game folder>\\here, when the tools aren't installed in it
INSTALL_BACKUP_DIR = "backups"                 # <game folder>\\conflict-tools\\here, when they are
LEGACY_DIR = "legacy"                          # every older backup of a file: the top keeps one per file
TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = None                                    # one folder for every game's backups, when set (MWManager)
OWN_BAK = re.compile(r"\.(bak\d*|mwdialog-.+\.bak)$", re.IGNORECASE)


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


def backup_root(game):
    """Where the backups for a game folder go: the install's own backups folder when the tools are installed
    in that game folder (Morrowind\\conflict-tools), else <game folder>\\mwdialog_backup."""
    if ROOT:
        return ROOT
    game = os.path.abspath(game)
    if os.path.normcase(os.path.dirname(TOOL_DIR)) == os.path.normcase(game):
        return os.path.join(TOOL_DIR, INSTALL_BACKUP_DIR)
    return os.path.join(game, BACKUP_DIR)


def _rel(path):
    path = os.path.abspath(path)
    game = game_dir_of(path)
    rel = os.path.relpath(path, game)
    return game, (os.path.basename(path) if rel.startswith("..") else rel)


def bak_home(path, legacy=False):
    """Where a backup of `path` goes: <backups>\\<its path under the game folder> (Data Files\\X.esp ->
    <backups>\\Data Files\\X.esp), or under <backups>\\legacy; the folder is made. Add the suffix."""
    game, rel = _rel(path)
    home = os.path.join(backup_root(game), *([LEGACY_DIR] if legacy else []), rel)
    os.makedirs(os.path.dirname(home), exist_ok=True)
    return home


def retire_backups(path):
    """Move every backup of `path` at the top of the backups folder into legacy, so the next one made is
    the only one there. Returns the base name for that next backup."""
    home = bak_home(path)
    folder, stem = os.path.split(home)
    pat = re.compile(re.escape(stem) + OWN_BAK.pattern, re.IGNORECASE)
    try:
        names = [fn for fn in os.listdir(folder) if pat.match(fn)]
    except OSError:
        names = []
    if names:
        legacy = os.path.dirname(bak_home(path, legacy=True))
        for fn in names:
            dest = os.path.join(legacy, fn)
            if os.path.exists(dest):           # a name used again (.mwdialog-play.bak): keep both
                stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(os.path.getmtime(os.path.join(folder, fn))))
                dest = os.path.join(legacy, f"{stem}.mwdialog-{stamp}-{fn[len(stem) + 1:]}")
            os.replace(os.path.join(folder, fn), dest)
    return home


def stamped_backup(path):
    """A new dated backup name for `path` (<name>.mwdialog-YYYYmmdd-HHMMSS.bak), the only one at the top."""
    return f"{retire_backups(path)}.mwdialog-{time.strftime('%Y%m%d-%H%M%S')}.bak"


def backup_candidates(path):
    """Every backup of `path`, oldest first: any an earlier version left next to the file or in
    <game folder>\\mwdialog_backup, then the backups folder's and its legacy's (.bak, .bak2...) by number."""
    game, rel = _rel(path)
    root = backup_root(game)
    groups = [[path]]
    old = os.path.join(game, BACKUP_DIR, rel)
    if os.path.normcase(os.path.join(root, rel)) != os.path.normcase(old):
        groups.append([old])
    groups.append([os.path.join(root, LEGACY_DIR, rel), os.path.join(root, rel)])
    out = []
    for bases in groups:
        found = []
        for base in bases:
            folder, stem = os.path.split(base)
            try:
                names = os.listdir(folder or ".")
            except OSError:
                continue
            pat = re.compile(re.escape(stem) + r"\.bak(\d*)$", re.IGNORECASE)
            for fn in names:                         # no upper limit: .bak100 and later count too
                m = pat.match(fn)
                if m and (m.group(1) == "" or int(m.group(1)) >= 2):
                    found.append((int(m.group(1) or 1), os.path.join(folder, fn)))
        out += [c for _n, c in sorted(found)]
    return out


def backup_path(path):
    """A new backup name for `path`, the only one at the top of the backups folder (older ones go to
    legacy): .bak, then .bak2, .bak3... (highest = newest)."""
    taken = backup_candidates(path)
    base = retire_backups(path)
    n = 1 + max([1] + [int(re.search(r"\.bak(\d*)$", c, re.IGNORECASE).group(1) or 1) for c in taken]) if taken else 1
    return base + ".bak" if n == 1 else f"{base}.bak{n}"


def chain_tail(world, topic_key, exclude_source):
    """Last response of a topic among files other than `exclude_source`."""
    t = world.topics.get(topic_key)
    if t is None:
        return ""
    others = [i for i in t.infos.values() if not i.deleted and i.source.lower() != exclude_source]
    pointed = {i.prev.lower() for i in others if i.prev}
    tails = [i for i in others if i.id.lower() not in pointed]
    return tails[-1].id if tails else ""
