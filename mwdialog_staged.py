"""mwdialog_staged.py - the pre-deploy rule: tidy, luafix and the OpenMW converter handoff work on STAGED files only
(Vortex's staging folder or MWManager's). Nothing is read from or written to Data Files before the final deploy step
(deploy.py, Vortex's or MWManager's own deploy, and --play's runtime Morrowind.ini / load-order writes), with the
read-only exceptions below. Rule by dej (dejunai).

A run that works on staging calls begin(staging, game_dir) (a context manager: staged_run). While it is active:

  * check_write(path) raises DataFilesWriteError for any path inside the game's Data Files folder.
  * Every write over an existing staged file goes through replace_bytes (a new file, then os.replace), never through
    the old file's handle. Vortex deploys by hard link, so a staged file and its Data Files copy are often the same
    file; writing through it would change Data Files too. Replacing it breaks the link instead: Data Files keeps the
    old bytes until the next deploy puts the new ones there.
  * detach_tree(folder) breaks every hard link in a staged mod folder up front (before a program we don't control,
    like omw2mwse, writes into it).

Read-only exceptions (READ_EXCEPTIONS): the base game's own files, which ship in Data Files and are never staged:
Morrowind.bsa, Tribunal.bsa, Bloodmoon.bsa (dummy sources and the BSA indexes), Morrowind.esm / Tribunal.esm /
Bloodmoon.esm, the game's own loose Video and Fonts files (only ones that are not hard links, i.e. not deployed by
Vortex), and MWSE\\config\\mwguard.json (the user's in-game luafix settings; written by the game, never staged), and everything under MWSE\\logs\\ (vortex_tidy.py
--pack-report COPIES it into a scrubbed bug-report archive: a read only, nothing is changed, moved or deleted there).
Anything else under Data Files is looked up in the staged mod folders (and the suite's lua tools, which --play
deploys) instead.

Python 3.9+.
"""
import os

CORE_BSAS = ("morrowind.bsa", "tribunal.bsa", "bloodmoon.bsa")
CORE_MASTERS = ("morrowind.esm", "tribunal.esm", "bloodmoon.esm")
CORE_LOOSE_DIRS = ("video", "fonts")
CONFIG_EXCEPTIONS = ("mwse\\config\\mwguard.json",)
PACK_REPORT_READS = ("mwse\\logs\\",)          # vortex_tidy.py --pack-report copies these (reads only; mwdialog_report)
READ_EXCEPTIONS = CORE_BSAS + CORE_MASTERS + tuple(d + "\\*" for d in CORE_LOOSE_DIRS) + CONFIG_EXCEPTIONS


class DataFilesWriteError(OSError):
    """A write into Data Files was attempted before the deploy step."""


_STATE = {"staging": [], "data": []}      # normcased absolute folders while a staged run is active


def _key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path))).rstrip("\\/")


def _real(path):
    """The real path (symlinks and junctions followed), normcased: an alias compares equal to what it points at."""
    try:
        p = os.path.realpath(os.fspath(path))
    except (OSError, ValueError):
        p = os.path.abspath(os.fspath(path))
    if p.startswith("\\\\?\\"):
        p = p[4:]
    return os.path.normcase(p).rstrip("\\/")


def _forms(path):
    """The path as given and as it really is (both normcased): a guard checks both, so neither a junction INTO
    Data Files nor a Data Files entry that is a symlink out of it slips through."""
    return {_key(path), _real(path)}


def _under_key(p, b):
    return p == b or p.startswith(b + os.sep)


def _under(path, base):
    return any(_under_key(p, base) for p in _forms(path))


INIT_MODE = "init"                # MWManager's tidy --init: the core install, never staged, may act on Data Files
CORE_MODE = "core"                # after a successful MWSE update: luafix --core-only may write Data Files\\MWSE\\core only
CORE_WRITE = "mwse\\core"         # relative to Data Files, normcased
GAME_MARKERS = ("morrowind.ini", "morrowind.exe")


def _is_game_folder(folder):
    try:
        names = {n.lower() for n in os.listdir(folder)}
    except OSError:
        return False
    if names & set(GAME_MARKERS):
        return True
    return os.path.isfile(os.path.join(folder, "Data Files", "Morrowind.esm"))


def write_root_problem(path, game_dir=None, data_dir=None, mode="tidy"):
    """Why `path` must not be a write target before deploy ("" when it may): Data Files, the game folder, or
    anything inside either, compared by real path (symlinks and junctions followed) and ignoring case, so an alias
    is refused like the folder itself. data_dir/game_dir name the install when known; any folder above the target
    named "Data Files" or holding the game (Morrowind.ini / Morrowind.exe / Data Files\\Morrowind.esm) counts too.
    mode INIT_MODE ("init", MWManager's tidy --init: the core install is never staged, and it lets a user start
    without a purge) is a full exemption. mode CORE_MODE ("core", tidy --after-mwse-update) allows only
    Data Files\\MWSE\\core (the files luafix --core-only patches); everything else is still refused. The same
    rule as MWManager's workflow_safety.require_staging_write_root
    (6590bbd), and stricter: anywhere under the game folder is refused, not just the folder itself."""
    if mode == INIT_MODE:
        return ""
    if mode == CORE_MODE and _is_core_rel(path, data_dir, game_dir):
        return ""
    forms = _forms(path)
    if data_dir:
        for b in _forms(data_dir):
            if any(_under_key(p, b) for p in forms):
                return f"it is Data Files or inside it ({data_dir})"
    if game_dir and _is_game_folder(game_dir):
        for b in _forms(game_dir):
            if any(_under_key(p, b) for p in forms):
                return f"it is the game folder or inside it ({game_dir})"
    for p in sorted(forms):
        d = p
        while True:
            if os.path.basename(d) == "data files":
                return f"it is a Data Files folder or inside one ({d})"
            if _is_game_folder(d):
                return f"it is a game folder or inside one ({d})"
            up = os.path.dirname(d)
            if up == d:
                break
            d = up
    return ""


def require_write_root(path, game_dir=None, data_dir=None, mode="tidy", what="tidy"):
    """write_root_problem, raising DataFilesWriteError (with a message for the user) instead; returns the real path."""
    why = write_root_problem(path, game_dir, data_dir, mode)
    if why:
        raise DataFilesWriteError(f"{what} refuses to write to {path}: {why}. Before deploy {what} works on "
                                  f"Vortex's or MWManager's staging folder only; Data Files and the game folder "
                                  f"change only at the deploy step (or with tidy --init).")
    return os.path.realpath(os.fspath(path))


def begin(staging, game_dir=None, data_dir=None):
    """Start a staged run: `staging` (a folder or a list of folders) is where writes go; the game's Data Files
    (data_dir, else <game_dir>\\Data Files) is guarded. Nested begin() calls add to the active sets."""
    for s in ([staging] if isinstance(staging, (str, os.PathLike)) else list(staging or ())):
        k = _key(s)
        if k not in _STATE["staging"]:
            _STATE["staging"].append(k)
    dd = data_dir or (os.path.join(game_dir, "Data Files") if game_dir else None)
    if dd:
        for k in _forms(dd):
            if k not in _STATE["data"]:
                _STATE["data"].append(k)


def end():
    _STATE["staging"].clear()
    _STATE["data"].clear()


class staged_run:
    """with staged_run(staging, game_dir): ... (begin, then end on the way out)."""

    def __init__(self, staging, game_dir=None, data_dir=None):
        self.args = (staging, game_dir, data_dir)
        self.saved = None

    def __enter__(self):
        self.saved = {k: list(v) for k, v in _STATE.items()}
        begin(*self.args)
        return self

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            _STATE[k][:] = v
        return False


def active():
    return bool(_STATE["staging"] or _STATE["data"])


def in_staging(path):
    return any(_under(path, s) for s in _STATE["staging"])


def in_data_files(path, data_dir=None):
    """True for a path inside a guarded Data Files folder (or inside data_dir when given)."""
    bases = _forms(data_dir) if data_dir else _STATE["data"]
    forms = _forms(path)
    return any(_under_key(p, b) for p in forms for b in bases)


def is_read_exception(path, data_dir):
    """True for one of the documented read-only base-game files (see the module docstring) under data_dir."""
    if not data_dir or not in_data_files(path, data_dir):
        return False
    rel = os.path.relpath(os.path.abspath(path), os.path.abspath(data_dir)).replace("/", "\\").lower()
    if rel in CORE_BSAS or rel in CORE_MASTERS or rel in CONFIG_EXCEPTIONS:
        return True
    if any((rel + "\\").startswith(p) for p in PACK_REPORT_READS):
        return True
    top = rel.split("\\", 1)[0]
    if top in CORE_LOOSE_DIRS:
        try:
            return os.stat(path).st_nlink <= 1
        except OSError:
            return True                       # not there: nothing is read
    return False


def _is_core_rel(path, data_dir=None, game_dir=None):
    """True when `path` is Data Files\\MWSE\\core or a file under it (the --core-only write target)."""
    bases = list(_forms(data_dir) if data_dir else _STATE["data"])
    if game_dir and not bases:
        bases.extend(_forms(os.path.join(game_dir, "Data Files")))
    for b in bases:
        for p in _forms(path):
            if _under_key(p, b):
                rel = p[len(b):].lstrip("\\/")
                if rel == CORE_WRITE or rel.startswith(CORE_WRITE + "\\"):
                    return True
    return False


_CORE_OK = False                  # True inside allow_core_writes(): check_write lets MWSE\\core through


class allow_core_writes:
    """Temporarily allow writes under Data Files\\MWSE\\core (luafix --core-only after a successful MWSE
    update). Every other Data Files write is still refused while a staged run is active."""

    def __enter__(self):
        global _CORE_OK
        self.prev = _CORE_OK
        _CORE_OK = True
        return self

    def __exit__(self, *exc):
        global _CORE_OK
        _CORE_OK = self.prev
        return False


def check_write(path):
    """Raise DataFilesWriteError when a staged run is active and `path` is inside Data Files, except
    Data Files\\MWSE\\core while allow_core_writes() is active."""
    if _STATE["data"] and in_data_files(path):
        if _CORE_OK and _is_core_rel(path):
            return
        raise DataFilesWriteError(f"{path}: refusing to write into Data Files before deploy "
                                  f"(tidy and luafix work on staged files only)")


def replace_bytes(path, data, keep_times=None):
    """Write data as a NEW file at path (path.ctstmp, flushed, read back, then os.replace): a hard link to Data
    Files is broken, never written through. keep_times: a stat result whose dates are put back."""
    check_write(path)
    data = bytes(data)
    tmp = os.fspath(path) + ".ctstmp"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        with open(tmp, "rb") as f:
            if f.read() != data:
                raise OSError(f"{tmp}: read back differently from what was written")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    if keep_times is not None:
        os.utime(path, ns=(keep_times.st_atime_ns, keep_times.st_mtime_ns))


def must_replace(path):
    """True when a write over the existing file at path has to replace it (a staged run is active and the file is
    in staging), instead of writing through its handle."""
    return active() and in_staging(path) and os.path.exists(path)


def detach(path):
    """Give a hard-linked staged file its own copy (same bytes and dates), so nothing written to it later reaches
    the other links (Data Files). Returns True when a link was broken."""
    try:
        st = os.stat(path)
    except OSError:
        return False
    if st.st_nlink <= 1:
        return False
    with open(path, "rb") as f:
        data = f.read()
    replace_bytes(path, data, keep_times=st)
    return True


def detach_tree(folder):
    """detach() every hard-linked file under folder; the number of links broken."""
    n = 0
    for base, _dirs, files in os.walk(folder):
        for fn in files:
            if detach(os.path.join(base, fn)):
                n += 1
    return n


class StagedData:
    """What tidy and luafix look things up in instead of Data Files: the staged mod folders (not Off\\), then any
    extra folders (the suite's lua tools, which --play deploys). data_dir is the game's Data Files path, used only
    for its path length (long paths) and the documented read exceptions; game_dir is the Morrowind folder."""

    def __init__(self, staging, game_dir=None, extra=(), mods=None):
        self.staging = os.path.abspath(staging) if staging else None
        self.game_dir = os.path.abspath(game_dir) if game_dir else None
        self.data_dir = os.path.join(self.game_dir, "Data Files") if self.game_dir else None
        if mods is None:
            mods = []
            if self.staging and os.path.isdir(self.staging):
                mods = [os.path.join(self.staging, d) for d in sorted(os.listdir(self.staging))
                        if d.lower() != "off" and os.path.isdir(os.path.join(self.staging, d))]
        self.roots = [os.path.abspath(m) for m in mods] + [os.path.abspath(e) for e in extra if e and os.path.isdir(e)]

    def __repr__(self):
        return f"StagedData({self.staging!r}, {len(self.roots)} root(s))"

    def find(self, rel):
        """The first staged file at rel (a path under Data Files, any case on case-insensitive systems), or None."""
        for r in self.roots:
            p = os.path.join(r, rel)
            if os.path.isfile(p):
                return p
        return None

    def exists(self, rel):
        return self.find(rel) is not None

    def plugins(self):
        """[(name, path)] of every plugin (.esp/.esm) at the root of a staged mod."""
        out = []
        for r in self.roots:
            try:
                names = sorted(os.listdir(r))
            except OSError:
                continue
            out += [(n, os.path.join(r, n)) for n in names if n.lower().endswith((".esp", ".esm"))]
        return out

    def bsas(self):
        """[path] of every .bsa at the root of a staged mod, then the base game's (read-only exception)."""
        out = []
        for r in self.roots:
            try:
                out += [os.path.join(r, n) for n in sorted(os.listdir(r)) if n.lower().endswith(".bsa")]
            except OSError:
                continue
        return out + self.core_bsas()

    def core_bsas(self):
        if not self.data_dir:
            return []
        return [p for p in (os.path.join(self.data_dir, n) for n in ("Morrowind.bsa", "Tribunal.bsa", "Bloodmoon.bsa"))
                if os.path.isfile(p)]


def roots_of(data):
    """Lookup folders for `data`: a StagedData's roots, or [data] for a plain Data Files path (deploy-time use)."""
    if isinstance(data, StagedData):
        return list(data.roots)
    return [data] if data else []


def game_dir_of(data):
    if isinstance(data, StagedData):
        return data.game_dir
    return os.path.dirname(os.path.abspath(data)) if data else None


def data_path_of(data):
    """The Data Files path (a string, for path lengths and the read exceptions), for either kind."""
    if isinstance(data, StagedData):
        return data.data_dir
    return data
