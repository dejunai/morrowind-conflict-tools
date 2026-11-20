"""Tidy's asset check repairs a plugin's CELL references MGE XE's distant land generator chokes on: an XSCL after
the reference's DATA (Tamriel Rebuilt - Yet Another Border Fix.esp), and one reference placed identically in two
exterior cells, one of them not the cell its position is in (TR_Mainland.esm: ex_cave_entrance_wg_01, FRMR 0x03B13D,
in (27,-24) as well as (27,-26))."""
import os
import struct

from conftest import m, plugin, rec, sub, z

import mwdialog_assets as ah


def exterior(x, y, refs):
    return rec("CELL", sub("NAME", z("")) + sub("DATA", struct.pack("<Iii", 0, x, y)) + b"".join(refs))


def ref(index, name, px, py, scale_last=False):
    data = sub("DATA", struct.pack("<6f", px, py, 0, 0, 0, 0))
    scale = sub("XSCL", struct.pack("<f", 1.5))
    return sub("FRMR", struct.pack("<I", index)) + sub("NAME", z(name)) + (data + scale if scale_last else scale + data)


def subs_of(data, x, y):
    for off, tag, _f, body in m.iter_records(data):
        subs = list(m.iter_subs(body, off))
        if tag == "CELL" and next(d for n, d in subs if n == "DATA")[4:12] == struct.pack("<ii", x, y):
            return [n for n, _d in subs]


def test_tidy_moves_late_scales_and_drops_the_misplaced_copy(tmp_path):
    mod = tmp_path / "staging" / "Border Fix"
    mod.mkdir(parents=True)
    path = mod / "Border Fix.esp"
    door = ref(0x03B13D, "ex_cave_entrance_wg_01", 227365.625, -207674.969)
    plugin(path, [], [exterior(11, -57, [ref(8103, "flora_tree_gl_08", 90200.0, -466000.0, scale_last=True)]),
                      exterior(27, -24, [door]), exterior(27, -26, [door])])
    os.utime(path, (1000000000, 1000000000))                 # the plugin's date: its place in the load order
    issues, fixes = ah.check_folder(str(mod), m, str(tmp_path / "Data Files"))
    cell = [f for f in fixes if f[0] == "cellrefs"]
    assert cell and cell[0][3] == {"xscl": 1, "dupes": 1}, issues
    done, skipped = ah.apply_folder(str(mod), cell, m, str(tmp_path), "Border Fix")
    assert (done, skipped) == (1, [])
    data = path.read_bytes()
    assert subs_of(data, 11, -57) == ["NAME", "DATA", "FRMR", "NAME", "XSCL", "DATA"]
    assert "FRMR" not in subs_of(data, 27, -24) and "FRMR" in subs_of(data, 27, -26)
    assert os.stat(path).st_mtime == 1000000000
    kept = [os.path.join(b, f) for b, _d, fs in os.walk(mod / "Off") for f in fs]
    assert len(kept) == 1 and kept[0].endswith("Border Fix.esp")
    assert ah.cell_ref_repairs(data, m)[1:] == (0, 0, 0)


def test_copies_that_differ_are_left_for_review(tmp_path):
    a = ref(0x0100, "door_a", 227365.625, -207674.969)
    b = ref(0x0100, "door_b", 227365.625, -207674.969)
    path = tmp_path / "X.esp"
    plugin(path, [], [exterior(27, -24, [a]), exterior(27, -26, [b])])
    data = path.read_bytes()
    assert ah.cell_ref_repairs(data, m) == (data, 0, 0, 1)
