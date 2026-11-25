"""Shared path helpers: no hardcoded absolute paths.

The game root is the parent of the "Data Files" folder given on the command line; without one, the first folder
holding Morrowind.ini among: the working folder, its parent, this script's parent (Morrowind\\conflict-tools\\)
and this script's folder (an older install at the game root). Vortex's Morrowind staging
and download folders come from Vortex's own settings (%APPDATA%\\Vortex). CLI flags override.
Recorded paths are stored relative to one of those bases, with a tag (staging:/downloads:/game:).
Readers still accept an older absolute path and convert it the next time the record is written.
"""
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

GAME_ID = "morrowind"
TAGS = ("staging", "downloads", "game")
DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")

# LevelDB / JSON keys Vortex uses for these paths
_DL_KEY = b"settings###downloads###path"
_INST_KEY = b"settings###mods###installPath"
_INST_GAME_KEY = b"settings###mods###installPath###"  # + game id


class VortexPathError(Exception):
    """Vortex settings could not be read, or the resolved folder is missing. args[0] is the message."""

    def __init__(self, message, kind=None, tried=None, reason=None):
        super().__init__(message)
        self.kind = kind
        self.tried = list(tried or [])
        self.reason = reason


class ToolNotFoundError(Exception):
    """An optional external tool (7-Zip) was needed and was not found."""


_RUN_LOCKS = {}                          # lock file -> handle held by this process
_DELEGATED_LOCKS = set()                 # locks inherited from an MWManager parent; this process owns no byte
# MWManager's workflow_safety.mutation_lock folder and naming: the tools and the GUI shut each other out, and no
# lock file lands in the game folder (its rollback check counts extra files)
GAME_LOCK_DIR = os.path.join(tempfile.gettempdir(), "mwmanager-locks")


TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
PLANS_DIR = os.path.join(TOOL_DIR, "plans")                # vortex_tidy's and luafix's plans (written, then applied)


GENERATED_DIR = os.path.join(TOOL_DIR, "generated")       # the tools' own files, when installed in the game


def state_path(base, name):
    """Where the tools keep `name` (a record, cache, journal, log, report or rules file). Installed in the game
    (<game>\\conflict-tools\\) and asked for the game folder: conflict-tools\\generated\\<name>; a copy still in the
    game folder from before is moved there the first time. Any other folder (the tools run from elsewhere,
    MWManager, a test's game) is used as given."""
    if os.path.isabs(name) or os.path.normcase(os.path.abspath(base)) != os.path.normcase(os.path.dirname(TOOL_DIR)):
        return os.path.join(base, name)
    new, old = os.path.join(GENERATED_DIR, name), os.path.join(base, name)
    os.makedirs(GENERATED_DIR, exist_ok=True)
    if not os.path.exists(new) and os.path.exists(old):
        os.replace(old, new)
    return new
LUA_TOOLS_DIR = os.path.join(TOOL_DIR, "lua tools")        # the suite's MWSE Lua mods, laid out as in Data Files


def is_game_dir(folder):
    """A Morrowind folder: it holds Morrowind.ini (any case)."""
    try:
        return any(n.lower() == "morrowind.ini" for n in os.listdir(folder))
    except OSError:
        return False


def find_game_dir(cwd=None):
    """The Morrowind folder when no "Data Files" was given (see the module docstring), or None."""
    cwd = os.path.abspath(cwd or os.getcwd())
    for folder in (cwd, os.path.dirname(cwd), os.path.dirname(TOOL_DIR), TOOL_DIR):
        if is_game_dir(folder):
            return folder
    return None


def default_data_dir():
    """<game>\\Data Files of find_game_dir(), or None."""
    game = find_game_dir()
    return os.path.join(game, "Data Files") if game else None


def tool_dirs(game_dir=None):
    """Where bundled programs (texconv, tools\\7z, tools\\luajit) are looked for: the game folder, then this
    script's folder."""
    out = []
    for d in (game_dir, TOOL_DIR):
        if d and os.path.normcase(os.path.abspath(d)) not in {os.path.normcase(os.path.abspath(o)) for o in out}:
            out.append(d)
    return out


def find_program(name, game_dir=None):
    """<name>.exe bundled in these scripts' tools\\ (checked first), beside the scripts, or in the game folder
    (or its tools\\), else on PATH; None if missing."""
    for d in [TOOL_DIR] + [d for d in tool_dirs(game_dir) if d != TOOL_DIR]:
        for p in (os.path.join(d, "tools", name + ".exe"), os.path.join(d, name + ".exe")):
            if os.path.isfile(p):
                return p
    return shutil.which(name)


def find_texconv(game_dir=None):
    return find_program("texconv", game_dir)


def find_mwrecompile(game_dir=None, explicit=None):
    """MWRecompile.exe: --mwrecompile, the MWRECOMPILE environment variable, tools\\MWRecompile\\ (a release drop
    with its licence and source), then find_program's places. None if missing."""
    for p in (explicit, os.environ.get("MWRECOMPILE")):
        if p:
            return p if os.path.isfile(p) else None
    for d in [TOOL_DIR] + [d for d in tool_dirs(game_dir) if d != TOOL_DIR]:
        p = os.path.join(d, "tools", "MWRecompile", "MWRecompile.exe")
        if os.path.isfile(p):
            return p
    return find_program("MWRecompile", game_dir)


def deploy_lua_tools(data_dir, src=None, backup_dir=None):
    """Bring Data Files up to date with the suite's Lua mods in lua tools\\ (laid out like Data Files), where
    every edit to them is made. A file Data Files lacks is copied in. A deployed file that differs from its
    lua tools copy is replaced when lua tools' copy is the newer one; the deployed one goes to backup_dir
    first (default <backups>\\lua deploy\\<date>). A deployed copy newer than lua tools' is left alone and
    listed: an edit made there belongs in lua tools. MWSE\\config\\ holds the player's settings: only a
    missing file is copied there. Returns {"copied", "updated", "newer", "retired", "backup"}: paths relative
    to Data Files ("retired": files in Data Files\\MWSE\\mods\\mwsuite that lua tools no longer has, only
    listed)."""
    src = src or LUA_TOOLS_DIR
    res = {"copied": [], "updated": [], "newer": [], "retired": [], "backup": None}
    have = set()
    for root, dirs, files in os.walk(src):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for fn in sorted(files):
            s = os.path.join(root, fn)
            rel = os.path.relpath(s, src)
            have.add(os.path.normcase(rel))
            dest = os.path.join(data_dir, rel)
            if not os.path.exists(dest):
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(s, dest)
                res["copied"].append(rel)
                continue
            if os.path.normcase(rel).startswith(os.path.normcase(os.path.join("MWSE", "config")) + os.sep):
                continue                                  # the player's settings
            if _same_bytes(s, dest):
                continue
            if os.path.getmtime(s) <= os.path.getmtime(dest):
                res["newer"].append(rel)
                continue
            if res["backup"] is None:
                import mwdialog_backup
                res["backup"] = backup_dir or os.path.join(
                    mwdialog_backup.backup_root(os.path.dirname(os.path.abspath(data_dir))), "lua deploy",
                    time.strftime("%Y%m%d-%H%M%S"))
            bak = os.path.join(res["backup"], rel)
            os.makedirs(os.path.dirname(bak), exist_ok=True)
            shutil.copy2(dest, bak)
            tmp = dest + ".mwdeploy.tmp"
            shutil.copy2(s, tmp)
            os.replace(tmp, dest)                         # a new file: a Vortex hardlink is not written through
            res["updated"].append(rel)
    suite = os.path.join(data_dir, "MWSE", "mods", "mwsuite")
    for root, dirs, files in os.walk(suite):
        for fn in sorted(files):
            rel = os.path.relpath(os.path.join(root, fn), data_dir)
            if os.path.normcase(rel) not in have:
                res["retired"].append(rel)
    return res


def _same_bytes(a, b):
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read() == fb.read()


def _tool_lock_file():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "mwdialog.lock")


def _hold(path, key=None):
    if path in _RUN_LOCKS:
        return True
    handle = open(path, "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0, os.SEEK_END)
            if not handle.tell():
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        try:
            inherited = json.loads(os.environ.get("MWMANAGER_DELEGATED_LOCKS", "{}"))
            handle.seek(1)               # byte zero is locked; MWManager writes its delegation token after it
            owner = json.loads(handle.read())
            delegated = bool(key and owner.get("token") and inherited.get(key) == owner["token"])
        except (OSError, ValueError, AttributeError):
            delegated = False
        if not delegated:
            handle.close()
            return False
        _DELEGATED_LOCKS.add(path)
    _RUN_LOCKS[path] = handle
    return True


def acquire_run_lock():
    """Hold mwdialog.lock (beside these tools) until this process ends, so two runs of mwdialog_check.py /
    vortex_tidy.py cannot overwrite each other's plan and record files. Free again inside the same process
    (the tools call each other). False when another process holds it."""
    return _hold(_tool_lock_file())


def acquire_game_lock(game_dir):
    """Hold the game's lock, so another copy of these tools or a job in MWManager can't write to that game at the
    same time. Free again inside the same process. False when another process holds it."""
    key = os.path.normcase(str(Path(game_dir).resolve()))
    os.makedirs(GAME_LOCK_DIR, exist_ok=True)
    path = os.path.join(GAME_LOCK_DIR, hashlib.sha256(key.encode()).hexdigest() + ".lock")
    if not _hold(path, key):
        return False
    if path not in _DELEGATED_LOCKS:
        _RUN_LOCKS[path].truncate(1)         # no MWManager job token left to read: this holder delegates to nobody
    return True


def release_game_locks():
    """Let go of every game's lock (the tools' own is held until the process ends)."""
    own = _tool_lock_file()
    for path in [p for p in _RUN_LOCKS if p != own]:
        _RUN_LOCKS.pop(path).close()
        _DELEGATED_LOCKS.discard(path)


RUN_LOCKED_MESSAGE = ("Another Morrowind tool or MWManager is still working on this "
                      "game. Let it finish, then run this again.")


def is_abs_path(path):
    """True for a POSIX/Windows absolute path, including a drive-letter path on a non-Windows host."""
    if not path:
        return False
    return os.path.isabs(path) or bool(DRIVE_RE.match(path))


def _normkey(path):
    p = (path or "").replace("/", "\\").rstrip("\\")
    if len(p) == 2 and p[1] == ":":
        p += "\\"
    return p.lower()


def _is_under(path, base):
    a, b = _normkey(path), _normkey(base)
    return a == b or a.startswith(b + "\\")


def _rel_to(path, base):
    """path relative to base, using backslashes (the record format), preserving path case."""
    p = path.replace("/", "\\")
    b = base.replace("/", "\\").rstrip("\\")
    if _normkey(p) == _normkey(b):
        return ""
    # same length prefix as the normalised base; walk by segments to stay case-accurate
    ps, bs = p.split("\\"), b.split("\\")
    i = 0
    while i < len(ps) and i < len(bs) and ps[i].lower() == bs[i].lower():
        i += 1
    if i != len(bs):
        return os.path.relpath(path, base).replace("/", "\\")
    return "\\".join(ps[i:])


def vortex_appdata():
    """%APPDATA%\\Vortex, or None when APPDATA is unset."""
    app = os.environ.get("APPDATA")
    if not app:
        return None
    return os.path.join(app, "Vortex")


def vortex_search_dirs():
    """Folders we look in for Vortex settings, in order (may or may not exist)."""
    root = vortex_appdata()
    if not root:
        return []
    return [
        os.path.join(root, "state.v2"),
        os.path.join(root, "state"),
        os.path.join(root, "temp", "state_backups_full"),
    ]


def as_local(path):
    """Separators converted to this OS's, so a path from Vortex (often backslash) can be tested with isdir."""
    if not path:
        return path
    return os.path.normpath(path.replace("/", os.sep).replace("\\", os.sep))


def _expand(path, game_id=GAME_ID, userdata=None):
    if not path or not isinstance(path, str):
        return path
    if userdata is None:
        userdata = vortex_appdata() or ""
    return (path.replace("{USERDATA}", userdata)
                .replace("{userdata}", userdata)
                .replace("{game}", game_id)
                .replace("{GAME}", game_id))


def _json_string(raw):
    try:
        return json.loads(b'"' + raw + b'"')
    except (ValueError, TypeError):
        try:
            return json.loads(raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else raw)
        except (ValueError, TypeError):
            return None


# ------------------------------------------------------------------ Vortex state.v2 (LevelDB), read-only
# A small LevelDB + Snappy reader, so no native module is needed. Files are only opened for reading; a file Vortex
# holds open without sharing (its live .log while it runs) is skipped. Vortex compacts its write-ahead log into
# sorted tables (.ldb) when it starts: there keys are prefix-compressed and blocks Snappy-compressed, so a raw
# byte search for "settings###mods###installPath" finds nothing and only a real table read gets the settings.
_LDB_MAGIC = bytes.fromhex("57fb808b247547db")
_LDB_LOG_BLOCK = 32768


def _varint(data, pos):
    result = shift = 0
    while True:
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
        if shift > 63:
            raise ValueError("bad varint")


def _snappy_decompress(data):
    """Raw (unframed) Snappy, as LevelDB stores a compressed block."""
    length, pos = _varint(data, 0)
    out = bytearray()
    n = len(data)
    while pos < n:
        tag = data[pos]
        pos += 1
        kind = tag & 3
        if kind == 0:
            size = tag >> 2
            if size >= 60:
                extra = size - 59
                size = int.from_bytes(data[pos:pos + extra], "little")
                pos += extra
            size += 1
            out += data[pos:pos + size]
            pos += size
            continue
        if kind == 1:
            size = ((tag >> 2) & 7) + 4
            offset = ((tag >> 5) << 8) | data[pos]
            pos += 1
        elif kind == 2:
            size = (tag >> 2) + 1
            offset = int.from_bytes(data[pos:pos + 2], "little")
            pos += 2
        else:
            size = (tag >> 2) + 1
            offset = int.from_bytes(data[pos:pos + 4], "little")
            pos += 4
        if offset <= 0 or offset > len(out):
            raise ValueError("bad snappy copy offset")
        start = len(out) - offset
        if offset >= size:
            out += out[start:start + size]
        else:                                           # an overlapping copy repeats its own output
            for i in range(size):
                out.append(out[start + i])
    if len(out) != length:
        raise ValueError("snappy length mismatch")
    return bytes(out)


def _ldb_block_entries(block):
    if len(block) < 4:
        return
    restarts = int.from_bytes(block[-4:], "little")
    end = len(block) - 4 - 4 * restarts
    pos, key = 0, b""
    while pos < end:
        shared, pos = _varint(block, pos)
        unshared, pos = _varint(block, pos)
        vlen, pos = _varint(block, pos)
        key = key[:shared] + block[pos:pos + unshared]
        pos += unshared
        yield key, block[pos:pos + vlen]
        pos += vlen


def _ldb_read_block(data, offset, size):
    raw, kind = data[offset:offset + size], data[offset + size]
    return _snappy_decompress(raw) if kind == 1 else raw


def _ldb_table_entries(data):
    """(user key, sequence, value or None for a deletion) from one sorted table (.ldb/.sst)."""
    if len(data) < 48 or data[-8:] != _LDB_MAGIC:
        return
    footer = data[-48:]
    _m, pos = _varint(footer, 0)
    _m, pos = _varint(footer, pos)
    index_off, pos = _varint(footer, pos)
    index_size, pos = _varint(footer, pos)
    for _last, handle in _ldb_block_entries(_ldb_read_block(data, index_off, index_size)):
        off, hp = _varint(handle, 0)
        size, _hp = _varint(handle, hp)
        for ikey, value in _ldb_block_entries(_ldb_read_block(data, off, size)):
            if len(ikey) < 8:
                continue
            tag = int.from_bytes(ikey[-8:], "little")
            yield ikey[:-8], tag >> 8, (value if tag & 0xFF == 1 else None)


def _ldb_log_entries(data):
    """(user key, sequence, value or None) from a write-ahead log; a torn tail is skipped."""
    records, pending, pos = [], b"", 0
    while pos + 7 <= len(data):
        left = _LDB_LOG_BLOCK - pos % _LDB_LOG_BLOCK
        if left < 7:
            pos += left
            continue
        length = int.from_bytes(data[pos + 4:pos + 6], "little")
        kind = data[pos + 6]
        chunk = data[pos + 7:pos + 7 + length]
        pos += 7 + length
        if len(chunk) < length:
            break
        if kind == 1:
            records.append(chunk)
        elif kind == 2:
            pending = chunk
        elif kind == 3:
            pending += chunk
        elif kind == 4:
            records.append(pending + chunk)
            pending = b""
    for record in records:
        if len(record) < 12:
            continue
        seq, count = int.from_bytes(record[:8], "little"), int.from_bytes(record[8:12], "little")
        p, batch = 12, []
        try:
            for i in range(count):
                kind = record[p]
                p += 1
                klen, p = _varint(record, p)
                key = record[p:p + klen]
                p += klen
                value = None
                if kind == 1:
                    vlen, p = _varint(record, p)
                    value = record[p:p + vlen]
                    p += vlen
                batch.append((key, seq + i, value))
        except (IndexError, ValueError):
            continue
        yield from batch


def read_leveldb_prefix(folder, prefix):
    """{key bytes: value bytes} for every live key starting with `prefix` in a LevelDB folder; the newest
    sequence number wins and a deletion hides the key. Read-only; unreadable or damaged files are skipped."""
    newest = {}
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return {}
    for n in names:
        low = n.lower()
        if not low.endswith((".ldb", ".sst", ".log")):
            continue
        try:
            with open(os.path.join(folder, n), "rb") as f:
                data = f.read()
        except OSError:
            continue
        try:
            entries = _ldb_log_entries(data) if low.endswith(".log") else _ldb_table_entries(data)
            for key, seq, value in entries:
                if key.startswith(prefix) and seq >= newest.get(key, (-1, None))[0]:
                    newest[key] = (seq, value)
        except (ValueError, IndexError):
            continue
    return {k: v for k, (_s, v) in newest.items() if v is not None}


def _leveldb_settings(folder, game_id):
    """(downloads, staging template) from Vortex's settings keys, read as a real LevelDB."""
    live = read_leveldb_prefix(folder, b"settings###")

    def val(key):
        raw = live.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None

    dl = val(_DL_KEY)
    st = val(_INST_GAME_KEY + game_id.encode("ascii"))
    if not st:
        whole = val(_INST_KEY)
        if isinstance(whole, dict):
            st = whole.get(game_id)
        elif isinstance(whole, str):
            st = whole
    return (dl if isinstance(dl, str) and dl else None), (st if isinstance(st, str) and st else None)


def _scan_leveldb_dir(folder, game_id):
    """Downloads path and Morrowind installPath from a Vortex LevelDB folder: a real read first, then the older
    raw byte search for anything still missing."""
    try:
        dl, st = _leveldb_settings(folder, game_id)
    except Exception:  # noqa: BLE001 - a reader bug must not stop the raw search
        dl = st = None
    if not (dl and st):
        rdl, rst = _scan_leveldb_raw(folder, game_id)
        dl, st = dl or rdl, st or rst
    return dl, st


def _scan_leveldb_raw(folder, game_id):
    """Best-effort raw byte search of LevelDB .ldb/.log files (finds keys stored whole: the log, or an
    uncompressed table's restart entries)."""
    downloads = staging_tmpl = None
    try:
        names = os.listdir(folder)
    except OSError:
        return None, None
    files = []
    for n in names:
        low = n.lower()
        if low.endswith((".log", ".ldb")) or n.upper() in {"LOG", "LOG.OLD"}:
            files.append(os.path.join(folder, n))
    files.sort(key=os.path.getmtime, reverse=True)
    inst_pat = re.compile(
        re.escape(_INST_KEY) + rb".{0,24}?(\{(?:[^{}]|\{[^{}]*\}){0,4000}\})", re.S)
    inst_game_pat = re.compile(
        re.escape(_INST_GAME_KEY + game_id.encode("ascii")) + rb".{0,24}?\"((?:[^\"\\]|\\.){1,500})\"", re.S)
    dl_pat = re.compile(
        re.escape(_DL_KEY) + rb".{0,24}?\"((?:[^\"\\]|\\.){1,500})\"", re.S)
    for fn in files:
        try:
            data = open(fn, "rb").read()
        except OSError:
            continue
        if downloads is None:
            hits = dl_pat.findall(data)
            if hits:
                v = _json_string(hits[-1])
                if v:
                    downloads = v
        if staging_tmpl is None:
            gm = inst_game_pat.findall(data)
            if gm:
                v = _json_string(gm[-1])
                if v:
                    staging_tmpl = v
        if staging_tmpl is None:
            m = inst_pat.search(data)
            if m:
                try:
                    obj = json.loads(m.group(1))
                except ValueError:
                    obj = None
                if isinstance(obj, dict) and obj.get(game_id):
                    staging_tmpl = obj[game_id]
                elif isinstance(obj, str):
                    staging_tmpl = obj
        if downloads and staging_tmpl:
            break
    return downloads, staging_tmpl


def _from_state_obj(data, game_id):
    if not isinstance(data, dict):
        return None, None
    settings = data.get("settings")
    if not isinstance(settings, dict):
        settings = (data.get("persistent") or {}).get("settings") or {}
    if not isinstance(settings, dict):
        return None, None
    dl = (settings.get("downloads") or {}).get("path") if isinstance(settings.get("downloads"), dict) else None
    inst = (settings.get("mods") or {}).get("installPath") if isinstance(settings.get("mods"), dict) else None
    staging = None
    if isinstance(inst, dict):
        staging = inst.get(game_id)
    elif isinstance(inst, str):
        staging = inst
    return dl, staging


def _scan_json_backup_dir(folder, game_id):
    try:
        names = [n for n in os.listdir(folder) if n.lower().endswith(".json")]
    except OSError:
        return None, None
    files = [os.path.join(folder, n) for n in names]
    files.sort(key=os.path.getmtime, reverse=True)
    for fn in files:
        try:
            with open(fn, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError, UnicodeError):
            continue
        dl, st = _from_state_obj(data, game_id)
        if dl or st:
            return dl, st
    return None, None


_SETTINGS_MEMO = {}


def read_vortex_settings(game_id=GAME_ID, refresh=False):
    """_read_vortex_settings, once per run and %APPDATA% (staging and downloads both ask). Only an answer that
    names a folder is kept, so a later call tries again after a failure; refresh=True reads Vortex again."""
    key = (game_id, os.environ.get("APPDATA"))
    info = None if refresh else _SETTINGS_MEMO.get(key)
    if info is None:
        info = _read_vortex_settings(game_id)
        if info.get("downloads_tmpl") or info.get("staging_tmpl"):
            _SETTINGS_MEMO[key] = info
        else:
            _SETTINGS_MEMO.pop(key, None)
    return {k: list(v) if isinstance(v, list) else v for k, v in info.items()}


def clear_vortex_settings_cache():
    """Forget what read_vortex_settings read (a long-running caller, after Vortex's settings changed)."""
    _SETTINGS_MEMO.clear()


def _read_vortex_settings(game_id=GAME_ID):
    """Read Vortex's download path and Morrowind install/staging path templates.

    Returns dict: downloads_tmpl, staging_tmpl, tried (folders looked at), reason (if nothing useful).
    Templates may still contain {game} / {USERDATA}; expand with _expand.
    """
    tried = []
    reason = None
    root = vortex_appdata()
    if not root:
        return {"downloads_tmpl": None, "staging_tmpl": None, "tried": [],
                "reason": "%APPDATA% is not set (Vortex stores its settings in %APPDATA%\\Vortex)."}
    if not os.path.isdir(root):
        return {"downloads_tmpl": None, "staging_tmpl": None, "tried": [root],
                "reason": f"Vortex AppData folder not found: {root}"}
    downloads = staging = None
    for folder in vortex_search_dirs():
        tried.append(folder)
        if not os.path.isdir(folder):
            continue
        base = os.path.basename(folder).lower()
        if base in {"state.v2", "state"}:
            d, s = _scan_leveldb_dir(folder, game_id)
        else:
            d, s = _scan_json_backup_dir(folder, game_id)
        downloads = downloads or d
        staging = staging or s
        if downloads and staging:
            break
    if not downloads and not staging:
        reason = ("Vortex's settings were found but they do not name a downloads path or a "
                  f"Morrowind staging (installPath.{game_id}) folder."
                  if any(os.path.isdir(p) for p in tried) else
                  "No Vortex state database or settings backup could be read in: " + "; ".join(tried))
    return {"downloads_tmpl": downloads, "staging_tmpl": staging, "tried": tried, "reason": reason}


def _format_error(kind, flag, tried, reason):
    label = {"staging": "staging folder", "downloads": "download folder"}[kind]
    lines = [
        f"Could not determine Vortex's Morrowind {label}.",
        "",
        "Looked for Vortex settings in:",
    ]
    if tried:
        lines.extend(f"  {p}" for p in tried)
    else:
        lines.append("  (no Vortex folders to search: %APPDATA% is not set)")
    if reason:
        lines.append(f"Reason: {reason}")
    lines.append("")
    lines.append(f"Pass {flag} to set the {label} explicitly.")
    return "\n".join(lines)


STAGING_MARKER = "__vortex_staging_folder"
DOWNLOADS_MARKER = "__vortex_downloads_folder"
VORTEX_PATHS_RECORD = "vortex_paths.json"     # in GENERATED_DIR: the last staging/download folders that resolved


def _marker(folder, name):
    """The JSON in Vortex's marker file `name` inside `folder` ({} when it holds no JSON), or None if absent."""
    fn = os.path.join(folder, name)
    if not os.path.isfile(fn):
        return None
    try:
        with open(fn, "rb") as f:
            data = json.loads(f.read(4096).decode("utf-8", "replace") or "{}")
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def is_vortex_staging(folder, game_id=GAME_ID):
    """True when `folder` carries Vortex's staging marker for this game."""
    m = _marker(folder, STAGING_MARKER) if folder else None
    return m is not None and m.get("game", game_id) == game_id


def is_vortex_downloads(folder):
    """True when `folder` (a game's download folder) or its parent carries Vortex's downloads marker."""
    if not folder:
        return False
    return any(_marker(f, DOWNLOADS_MARKER) is not None for f in (folder, os.path.dirname(folder)))


def _paths_record():
    """The remembered-folders record, or None when the tools have no generated folder (tests, a bare checkout)."""
    return os.path.join(GENERATED_DIR, VORTEX_PATHS_RECORD) if os.path.isdir(GENERATED_DIR) else None


def _remembered(kind):
    fn = _paths_record()
    if not fn:
        return None
    try:
        with open(fn, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    v = data.get(kind) if isinstance(data, dict) else None
    return v if isinstance(v, str) and v else None


def _remember(kind, path):
    """Keep a folder that resolved (only one Vortex's marker vouches for), so a later run finds it even when
    Vortex's settings can't be read. Written only when it changes; never touches Vortex's files."""
    fn = _paths_record()
    ok = is_vortex_staging(path) if kind == "staging" else is_vortex_downloads(path)
    if not fn or not ok:
        return
    try:
        with open(fn, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    if data.get(kind) == path:
        return
    data[kind] = path
    try:
        tmp = fn + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, fn)
    except OSError:
        pass


def _marker_fallback(kind, game_id=GAME_ID):
    """A folder Vortex's own marker file vouches for, when its settings can't be read: the one remembered from
    an earlier run, then Vortex's default location (%APPDATA%\\Vortex\\<game>\\mods, ...\\downloads\\<game>)."""
    root = vortex_appdata()
    cands = [_remembered(kind)]
    if root:
        cands.append(os.path.join(root, game_id, "mods") if kind == "staging"
                     else os.path.join(root, "downloads", game_id))
    for c in cands:
        if not c or not os.path.isdir(c):
            continue
        if (is_vortex_staging(c, game_id) if kind == "staging" else is_vortex_downloads(c)):
            return os.path.abspath(c)
    return None


def resolve_staging(cli=None, required=True, game_id=GAME_ID):
    """The Morrowind staging folder. `cli` (e.g. --staging) wins when given.

    When `required` and the folder cannot be determined (or does not exist), raises VortexPathError.
    Otherwise returns None.
    """
    if cli:
        path = os.path.abspath(cli)
        if os.path.isdir(path):
            _remember("staging", path)
            return path
        if required:
            raise VortexPathError(
                f"Staging folder not found: {path}\nPass --staging DIR to set it explicitly.",
                kind="staging", tried=[path], reason=f"the folder does not exist: {path}")
        return None
    info = read_vortex_settings(game_id)
    tmpl = info.get("staging_tmpl")
    path = as_local(_expand(tmpl, game_id)) if tmpl else None
    if path and os.path.isdir(path):
        path = os.path.abspath(path)
        _remember("staging", path)
        return path
    found = _marker_fallback("staging", game_id)
    if found:
        return found
    if not required:
        return None
    if path and not os.path.isdir(path):
        reason = f"Vortex's staging folder does not exist: {path}"
    else:
        reason = info.get("reason") or "Vortex settings have no Morrowind installPath."
    raise VortexPathError(
        _format_error("staging", "--staging DIR", info.get("tried") or vortex_search_dirs(), reason),
        kind="staging", tried=info.get("tried"), reason=reason)


def resolve_downloads(cli=None, required=True, game_id=GAME_ID):
    """The Morrowind download folder. `cli` (e.g. --vortex-downloads / --downloads) wins when given."""
    if cli:
        path = os.path.abspath(cli)
        if os.path.isdir(path):
            _remember("downloads", path)
            return path
        # a path that already includes the game leaf, or its parent
        if required:
            raise VortexPathError(
                f"Download folder not found: {path}\n"
                f"Pass --vortex-downloads DIR (or --downloads DIR) to set it explicitly.",
                kind="downloads", tried=[path], reason=f"the folder does not exist: {path}")
        return None
    info = read_vortex_settings(game_id)
    tmpl = info.get("downloads_tmpl")
    path = as_local(_expand(tmpl, game_id)) if tmpl else None
    # Vortex's path usually already contains {game}; also try joining 'morrowind' if needed
    cands = []
    if path:
        cands.append(path)
        if os.path.basename(path).lower() != game_id:
            cands.append(os.path.join(path, game_id))
    for c in cands:
        if c and os.path.isdir(c):
            c = os.path.abspath(c)
            _remember("downloads", c)
            return c
    found = _marker_fallback("downloads", game_id)
    if found:
        return found
    if not required:
        return None
    if path and not any(os.path.isdir(c) for c in cands if c):
        reason = f"Vortex's download folder does not exist: {path}"
    else:
        reason = info.get("reason") or "Vortex settings have no downloads path."
    raise VortexPathError(
        _format_error("downloads", "--vortex-downloads DIR (or --downloads DIR)",
                      info.get("tried") or vortex_search_dirs(), reason),
        kind="downloads", tried=info.get("tried"), reason=reason)


def path_bases(game_dir, staging=None, downloads=None):
    """{tag: absolute folder} for any base that was given."""
    out = {}
    if game_dir:
        out["game"] = os.path.abspath(game_dir)
    if staging:
        out["staging"] = os.path.abspath(staging)
    if downloads:
        out["downloads"] = os.path.abspath(downloads)
    return out


def store_path(path, bases):
    """Store `path` as 'tag:relative' under the longest matching base. Absolute paths that do not
    sit under a base are returned unchanged (the reader still accepts them). Already-tagged values
    are re-resolved and re-stored so a write migrates them."""
    if not path:
        return path
    resolved = resolve_stored(path, bases, missing_ok=True)
    if not is_abs_path(resolved):
        # still relative and untagged, and we couldn't resolve it
        return path
    best = None
    for tag, base in (bases or {}).items():
        if not base or tag not in TAGS:
            continue
        if _is_under(resolved, base):
            score = len(_normkey(base))
            if best is None or score > best[0]:
                best = (score, tag, _rel_to(resolved, base))
    if best:
        return f"{best[1]}:{best[2]}"
    return resolved


def resolve_stored(stored, bases, missing_ok=False):
    """Turn a stored path (tag:rel, or an older absolute path) into an absolute path.

    If the tag's base is missing and missing_ok is False, raises VortexPathError.
    """
    if not stored:
        return stored
    stored = stored.strip()
    tag, sep, rest = stored.partition(":")
    if sep and tag.lower() in TAGS:
        base = (bases or {}).get(tag.lower())
        if not base:
            if missing_ok:
                return stored
            raise VortexPathError(
                f"Cannot resolve {tag}:{rest}: the {tag} folder is not known. "
                f"Pass --staging / --vortex-downloads, or fix Vortex settings.",
                kind=tag.lower())
        rest = rest.replace("/", os.sep).replace("\\", os.sep)
        return os.path.normpath(os.path.join(base, rest))
    return stored


def rewrite_original_meta(meta, bases):
    """Rewrite the 'original: PATH' field inside an added-masters metadata string."""
    if not meta:
        return meta
    parts = [x.strip() for x in str(meta).split(";")]
    out = []
    for p in parts:
        if p.lower().startswith("original:"):
            orig = p.split(":", 1)[1].strip()
            out.append(f"original: {store_path(orig, bases)}" if orig else p)
        else:
            out.append(p)
    return "; ".join(out)


def original_from_meta(meta):
    """The original: path in an added-masters metadata string, or ''."""
    for p in (x.strip() for x in str(meta or "").split(";")):
        if p.lower().startswith("original:"):
            return p.split(":", 1)[1].strip()
    return ""


def convert_added_masters(rec, bases):
    """A copy of the added-masters dict with original: fields stored as tagged relative paths."""
    out = {}
    for patch, mods in (rec or {}).items():
        inner = {}
        for mod, meta in (mods or {}).items():
            inner[mod] = rewrite_original_meta(meta, bases)
        out[patch] = inner
    return out


def convert_reduced_row(rel, kind, keep, bases):
    return rel, kind, store_path(keep, bases)


def find_7z(game_dir=None, required=False):
    """7-Zip: tools\\7z\\ (next to these scripts, then <game>), then PATH (shutil.which('7z')).

    No registry lookup and no hardcoded Program Files paths. When `required` and nothing is
    found, raises ToolNotFoundError with a clear message.
    """
    tried_tools = []
    for base in tool_dirs(game_dir):
        for rel in (os.path.join("tools", "7z", "7z.exe"),
                    os.path.join("tools", "7z", "7z"),
                    os.path.join("tools", "7z.exe"),
                    os.path.join("tools", "7z")):
            p = os.path.join(base, rel)
            tried_tools.append(p)
            if os.path.isfile(p):
                return p
    found = shutil.which("7z")
    if found and os.path.isfile(found):
        return found
    if not required:
        return None
    lines = [
        "Could not find 7-Zip (7z).",
    ]
    if tried_tools:
        lines.append("Looked in:")
        lines.extend(f"  {p}" for p in tried_tools)
    lines.append("and on PATH (shutil.which('7z')).")
    lines.append("Place 7z.exe and 7z.dll in tools\\7z\\, or install 7-Zip and add it to PATH.")
    raise ToolNotFoundError("\n".join(lines))


def luajit_candidates(game_dir, explicit=None):
    """Paths to try for a LuaJIT / luac executable, in order (existing or not)."""
    exe = "luajit.exe" if os.name == "nt" else "luajit"
    cands = []
    if explicit:
        cands.append(explicit)
    if game_dir:
        cands.append(os.path.join(game_dir, "tools", "luajit", exe))
        if os.name == "nt":
            cands.append(os.path.join(game_dir, "tools", "luajit", "luajit"))
        cands.append(os.path.join(game_dir, exe))
    if not game_dir or os.path.normcase(os.path.abspath(game_dir)) != os.path.normcase(TOOL_DIR):
        cands.append(os.path.join(TOOL_DIR, "tools", "luajit", exe))
    return cands


def describe_luajit_search(game_dir):
    root = game_dir or "<game>"
    exe = "luajit.exe" if os.name == "nt" else "luajit"
    return (f"Looked in {os.path.join(root, 'tools', 'luajit', exe)}, then on PATH. "
            f"Pass --luajit PATH to use a specific binary, or --no-syntax-check to rely on the parser alone.")
