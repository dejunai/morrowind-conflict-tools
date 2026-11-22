"""--fix flips an .esm master's reference only where nothing can need it persistent: no list of plugins."""
import argparse
import struct

import pytest

from conftest import m, plugin, rec, sub, z

BLOCK = sub("NAME", z("the_thing")) + sub("DATA", struct.pack("<6f", 0, 0, 0, 0, 0, 0))


def cell(*parts):
    return rec("CELL", sub("NAME", z("Room")) + sub("DATA", struct.pack("<Iii", 1, 0, 0)) + b"".join(parts))


def thing(flags=0):
    return rec("ACTI", sub("NAME", z("the_thing")) + sub("MODL", z("m.nif")), flags)


def script(text=b"", code=b""):
    body = sub("SCHD", b"user".ljust(32, b"\0") + struct.pack("<5I", 0, 0, 0, len(code), 0))
    return rec("SCPT", body + (sub("SCDT", code) if code else b"") + sub("SCTX", text))


CASES = {
    "nothing needs it": ([], [], "Any Name.esp", "Master.esm", True),
    "flagged by the plugin": ([thing(0x400)], [], "Any Name.esp", "Master.esm", False),
    "flagged by the master": ([], [thing(0x400)], "Any Name.esp", "Master.esm", False),
    "an arrow": ([script(b'"the_thing"->Disable')], [], "Any Name.esp", "Master.esm", False),
    "an argument": ([script(b'if ( GetDistance "The_Thing" <= 350 )')], [], "Any Name.esp", "Master.esm", False),
    "a dotted variable": ([script(b'set "the_thing".block to 1')], [], "Any Name.esp", "Master.esm", False),
    "compiled code only": ([script(code=b"\x01\x09the_thing\x02")], [], "Any Name.esp", "Master.esm", False),
    "a dialogue result": ([rec("INFO", sub("INAM", z("1")) + sub("BNAM", b"the_thing->Disable"))], [], "Any Name.esp",
                          "Master.esm", False),
    "no plugin is special": ([thing(0x400)], [], "Clean_Piran.esp", "Master.esm", False),
    "an .esp master is always followed": ([thing(0x400)], [], "Any Name.esp", "Master.esp", True),
}


@pytest.mark.parametrize("case", CASES)
def test_flip_rule(tmp_path, case):
    extra, master_extra, name, master, flips = CASES[case]
    df = tmp_path / "Data Files"
    df.mkdir()
    plugin(df / master, [], [thing()] + master_extra
           + [cell(sub("NAM0", struct.pack("<I", 1)), sub("FRMR", struct.pack("<I", 5)), BLOCK)])
    plugin(df / name, [(master, (df / master).stat().st_size)],
           extra + [cell(sub("FRMR", struct.pack("<I", (1 << 24) | 5)), BLOCK)])
    before = (df / name).read_bytes()
    n = m.fix_ref_groups(argparse.Namespace(data_dir=str(df), fix_log="fix.log", dry_run=False),
                         [(master, str(df / master)), (name, str(df / name))])
    assert n == int(flips)
    body = next(b for _o, t, _f, b in m.iter_records((df / name).read_bytes()) if t == "CELL")
    _head, pers, _n0, temp = m.split_cell(body)
    assert (len(pers), len(temp)) == ((0, 1) if flips else (1, 0))
    if not flips:
        assert (df / name).read_bytes() == before
