"""--fix repairs CELL references MGE XE's distant land generator rejects: an XSCL after the reference's DATA
(Tamriel Rebuilt - Yet Another Border Fix.esp), and one reference placed identically in two exterior cells, one of
them not the cell its position is in (TR_Mainland.esm: ex_cave_entrance_wg_01, FRMR 0x03B13D, in (27,-24) as well as
(27,-26)). An .esp is repaired in place; an .esm is never edited and its misplaced copy is only reported: the game keeps one
reference per number, so an ESM-patch DELE for the other copy made the game warn 'Object reference
"ex_cave_entrance_wg_01" missing in master file' (Orethan Fields Region). Each finding goes in the plugin's bug
report."""
import os
import struct
import types

from conftest import m, plugin, rec, sub, z


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


DOOR = ref(0x03B13D, "ex_cave_entrance_wg_01", 227365.625, -207674.969)
TREE = ref(8103, "flora_tree_gl_08", 90200.0, -466000.0, scale_last=True)


def setup(tmp_path, name):
    data_dir = tmp_path / "Morrowind" / "Data Files"
    data_dir.mkdir(parents=True)
    path = data_dir / name
    plugin(path, [], [exterior(11, -57, [TREE]), exterior(27, -24, [DOOR]), exterior(27, -26, [DOOR])])
    os.utime(path, (1000000000, 1000000000))                 # the plugin's date: its place in the load order
    m.OWN_FIXES.clear()
    args = types.SimpleNamespace(data_dir=str(data_dir), dry_run=False, fix_log="fix.log")
    return data_dir, path, args


def test_an_esp_is_repaired_in_place_and_its_bug_report_says_so(tmp_path):
    _data_dir, path, args = setup(tmp_path, "Border Fix.esp")
    m.fix_cell_layouts(args, [(path.name, str(path))])
    data = path.read_bytes()
    assert subs_of(data, 11, -57) == ["NAME", "DATA", "FRMR", "NAME", "XSCL", "DATA"]
    assert "FRMR" not in subs_of(data, 27, -24) and "FRMR" in subs_of(data, 27, -26)
    assert os.stat(path).st_mtime == 1000000000
    assert m.late_scales(data)[1] == 0 and m.misplaced_duplicates(data) == ([], 0)
    texts = [t for _r, t in m.OWN_FIXES["Border Fix.esp"]]
    assert any("XSCL" in t for t in texts) and any("ex_cave_entrance_wg_01" in t for t in texts)
    assert not args._cell_deletes


def test_an_esm_is_not_edited_and_its_misplaced_copy_is_only_reported(tmp_path):
    _data_dir, path, args = setup(tmp_path, "TR_Mainland.esm")
    before = path.read_bytes()
    m.fix_cell_layouts(args, [(path.name, str(path))])
    assert path.read_bytes() == before
    assert not args._cell_deletes                                       # nothing for the ESM patch to delete
    assert [r for r, t in m.OWN_FIXES["TR_Mainland.esm"] if "XSCL" in t] == [False]     # reported, not changed
    [dup] = [(r, t) for r, t in m.OWN_FIXES["TR_Mainland.esm"] if "ex_cave_entrance_wg_01" in t]
    assert dup[0] is False and "(27, -24)" in dup[1] and "not changed" in dup[1]


def test_a_copy_another_plugin_changes_is_left_alone(tmp_path):
    data_dir, path, args = setup(tmp_path, "TR_Mainland.esm")
    other = data_dir / "Moves the door.esp"
    plugin(other, [("TR_Mainland.esm", path.stat().st_size)],
           [exterior(27, -24, [ref(0x0103B13D, "ex_cave_entrance_wg_01", 0.0, 0.0)])])
    m.fix_cell_layouts(args, [(path.name, str(path)), (other.name, str(other))])
    assert not args._cell_deletes
    assert any("Moves the door.esp changes that copy" in t for _r, t in m.OWN_FIXES["TR_Mainland.esm"])


def test_copies_that_differ_are_left_for_review(tmp_path):
    path = tmp_path / "X.esp"
    plugin(path, [], [exterior(27, -24, [ref(0x0100, "door_a", 227365.625, -207674.969)]),
                      exterior(27, -26, [ref(0x0100, "door_b", 227365.625, -207674.969)])])
    assert m.misplaced_duplicates(path.read_bytes()) == ([], 1)


def test_a_fix_run_puts_no_deletion_of_a_master_reference_in_the_esm_patch(tmp_path):
    g = tmp_path / "Morrowind"
    df = g / "Data Files"
    df.mkdir(parents=True)
    (g / "Morrowind.ini").write_text("[Game Files]\n")
    master = df / "TR_Mainland.esm"
    plugin(master, [], [exterior(27, -24, [DOOR]), exterior(27, -26, [DOOR])])
    m.OWN_FIXES.clear()
    m.main([str(df), "--plugins", master.name, "--no-vortex", "--no-archive-lookup", "--fix", "--yes",
            "--fix-log", str(g / "mwdialog_fixes.log")])
    deleted = []
    patch = df / m.PATCH_NAME
    for off, tag, _f, body in (m.iter_records(patch.read_bytes()) if patch.exists() else []):
        if tag == "CELL":
            subs = list(m.iter_subs(body, off))
            cell = struct.unpack_from("<ii", next(d for n, d in subs if n == "DATA"), 4)
            deleted += [(cell, struct.unpack("<I", d)[0]) for n, d in subs if n == "FRMR"] if any(
                n == "DELE" for n, _d in subs) else []
    assert deleted == []
    assert master.read_bytes().count(b"ex_cave_entrance_wg_01") == 2          # the master itself unchanged
    reports = [r.read_text(encoding="utf-8") for r in tmp_path.rglob("TR_Mainland*.bugreport.txt")]
    assert any("ex_cave_entrance_wg_01" in r and "not changed" in r for r in reports), reports   # for the author
