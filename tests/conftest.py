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
def _plan_audit_in_tmp(tmp_path, monkeypatch):
    """Plan-file audit copies of --apply runs never land in the source tree."""
    monkeypatch.setattr(vt, "AUDIT_ROOT", str(tmp_path / "audit"))
    lfm = sys.modules.get("mwdialog_luafix")
    if lfm is not None:
        monkeypatch.setattr(lfm, "PLAN_FILE", str(tmp_path / "luafix_plan.txt"))
