"""Shared helpers. The modules under test come from MW_SRC (default: the fixed scripts, one folder up);
MW_SRC=/workspace/uploads/morrowind runs the same tests against the originals."""
import importlib.util
import os
import re
import struct
import sys

import pytest

SRC = os.environ.get("MW_SRC", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def fold(text):
    """Collapse wrap() newlines and hanging indent so a phrase can be looked for in output."""
    return re.sub(r"\s+", " ", text or "")

if SRC not in sys.path:
    sys.path.insert(0, SRC)


def _load(name):
    if name in sys.modules and getattr(sys.modules[name], "__file__", "").startswith(SRC):
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, os.path.join(SRC, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


m = _load("mwdialog_check")
ah = _load("mwdialog_assets")
vt = _load("vortex_tidy")


def patch_everywhere(monkeypatch, name, value, raising=True):
    """Replace `name` on mwdialog_check and on every mwdialog_* module that holds it. mwdialog_check
    imports the moved names back, so patching it alone does not reach code that now lives in the smaller
    modules (mwdialog_datatree, mwdialog_console...)."""
    hit = False
    for modname, mod in list(sys.modules.items()):
        if mod is None or not (modname == "mwdialog_check" or modname.startswith("mwdialog_")):
            continue
        if name in vars(mod):
            monkeypatch.setattr(mod, name, value)
            hit = True
    if not hit:
        monkeypatch.setattr(m, name, value, raising=raising)


def sub(n, d):
    return n.encode() + struct.pack("<I", len(d)) + d


def z(s):
    return (s.encode("cp1252") if isinstance(s, str) else s) + b"\0"


def rec(tag, body, flags=0):
    return tag.encode() + struct.pack("<III", len(body), 0, flags) + body


def tes3(masters=(), count=0, desc=b""):
    hedr = struct.pack("<fI", 1.3, 0) + b"t".ljust(32, b"\0") + desc.ljust(256, b"\0") + struct.pack("<I", count)
    b = sub("HEDR", hedr)
    for name, size in masters:
        b += sub("MAST", z(name)) + sub("DATA", struct.pack("<Q", size))
    return rec("TES3", b)


def plugin(path, masters, records, count=None):
    data = tes3(masters, len(records) if count is None else count) + b"".join(records)
    with open(path, "wb") as f:
        f.write(data)
    return data


def misc(id_, value=1, name="Thing"):
    return rec("MISC", sub("NAME", z(id_)) + sub("MODL", z("m\\misc.nif")) + sub("FNAM", z(name))
               + sub("MCDT", struct.pack("<fii", 1.0, value, 0)))


def lev(ents, name=b"l_list", flags=1, chance=0):
    body = (sub("NAME", name + b"\0") + sub("DATA", struct.pack("<I", flags)) + sub("NNAM", bytes([chance]))
            + sub("INDX", struct.pack("<I", len(ents)))
            + b"".join(sub("INAM", z(e)) + sub("INTV", struct.pack("<H", 1)) for e in ents))
    return body


def hedr_count(path):
    with open(path, "rb") as f:
        data = f.read()
    h = m.first_sub(next(m.iter_records(data))[3], b"HEDR")
    return struct.unpack_from("<I", h, 296)[0]


def records_of(path):
    with open(path, "rb") as f:
        return list(m.iter_records(f.read()))


class _Tes3conv:
    """The optional tes3conv converter for golden tests (see tes3diff.py): plugins to JSON records and a normalized
    record-level diff as text."""

    def __init__(self, tes3diff, exe):
        self.T, self.exe = tes3diff, exe

    def records(self, plugin_path):
        return self.T.to_records(str(plugin_path), self.exe)

    def diff(self, old_path, new_path, limit=0):
        lines, counts = self.T.diff_plugins(str(old_path), str(new_path), self.exe, limit)
        return "\n".join(lines + ["Summary: " + self.T.summary(counts)])

    def write(self, records, out_path):
        return self.T.write_plugin(records, str(out_path), self.exe)


@pytest.fixture(scope="session")
def tes3conv():
    """tes3conv (Greatness7, MIT, pinned v0.4.1) found through tes3diff.find_tes3conv: TES3CONV, PATH, then an
    untracked dev tools folder. Optional: a test that uses it skips when it is not found, or when tes3diff.py is not
    vendored (MWManager). A program that is not the pinned release gets a warning."""
    import warnings
    if not os.path.isfile(os.path.join(SRC, "tes3diff.py")):
        pytest.skip("tes3diff.py is a repository-only dev tool, not vendored here")
    t = _load("tes3diff")
    exe = t.find_tes3conv()
    if exe is None:
        pytest.skip("tes3conv not found (optional: set TES3CONV, or see 'Developer Tools' in the README)")
    t.checked(exe, warn=lambda msg: warnings.warn(msg))
    return _Tes3conv(t, exe)


@pytest.fixture(autouse=True)
def _fresh_caches():
    if hasattr(m, "_READ_CACHE"):
        m._READ_CACHE.clear()
    getattr(m, "_BSA_MEMO", {}).clear()
    yield
    if hasattr(ah, "close_caches"):
        ah.close_caches()              # each test's asset cache is written and closed with it
    getattr(m, "_BSA_MEMO", {}).clear()


@pytest.fixture(autouse=True)
def _no_real_locks(tmp_path, monkeypatch):
    """The tools' own lock and the game's are the user's: tests run while Tidy does, and never hold it up."""
    paths = sys.modules["mwdialog_paths"]
    if not hasattr(paths, "GAME_LOCK_DIR"):
        yield                                  # MW_SRC points at scripts from before the game lock
        return
    monkeypatch.setitem(paths._RUN_LOCKS, paths._tool_lock_file(), None)
    monkeypatch.setattr(paths, "GAME_LOCK_DIR", str(tmp_path / "game-locks"))
    yield
    paths.release_game_locks()


@pytest.fixture(autouse=True)
def _no_local_rename_map(tmp_path, monkeypatch):
    """tools\\Translation.txt is this machine's: a test sees only the map it writes at tmp_path."""
    monkeypatch.setattr(sys.modules["mwdialog_patchfile"], "TD_MAP", str(tmp_path / "Translation.txt"), raising=False)


@pytest.fixture(autouse=True)
def _play_hash_record_in_tmp(tmp_path, monkeypatch):
    """mwdialog_hashes keeps the --play hash record beside the tools for a game they are not installed in, and a
    test's game is one: each test gets its own folder for it instead (never the checkout's generated\\)."""
    monkeypatch.setenv("MWDIALOG_PLAY_HASHES_DIR", str(tmp_path / "play-hashes"))


@pytest.fixture(autouse=True)
def _dummy_standins_in_tmp(tmp_path, monkeypatch):
    """The stand-in files copied out of a test's Morrowind.bsa go to the test's folder, never to the repository's
    generated\\dummy (tests of the default place delete this variable)."""
    monkeypatch.setenv("MWDIALOG_DUMMY_DIR", str(tmp_path / "dummy-standins"))


@pytest.fixture(autouse=True)
def _plan_audit_in_tmp(tmp_path, monkeypatch):
    """Plan-file audit copies of --apply runs never land in the source tree."""
    monkeypatch.setattr(vt, "AUDIT_ROOT", str(tmp_path / "audit"))
    lfm = sys.modules.get("mwdialog_luafix")
    if lfm is not None:
        monkeypatch.setattr(lfm, "PLAN_FILE", str(tmp_path / "luafix_plan.txt"))
        monkeypatch.setattr(lfm, "KNOWN_BUG_REPORT", str(tmp_path / "luafix_known_bugs.txt"))
