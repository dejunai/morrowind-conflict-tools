"""--fix: an edit to a master reference an updated master renumbered is pointed at the master's current reference to
the same object; an interior the master renamed is renamed in the plugin too; what can't be matched is removed."""
import os
import struct

from conftest import m, misc, plugin, rec, sub, z


def cell(name, *refs):
    return rec("CELL", sub("NAME", z(name)) + sub("DATA", struct.pack("<Iii", 1, 0, 0)) + b"".join(refs))


def ref(frmr, obj, x=0.0):
    return sub("FRMR", struct.pack("<I", frmr)) + sub("NAME", z(obj)) + sub("DATA", struct.pack("<6f", x, 0, 0, 0, 0, 0))


def setup(tmp_path, master_cell, patch_cell):
    g = tmp_path / "Morrowind"
    df = g / "Data Files"
    df.mkdir(parents=True)
    (g / "Morrowind.ini").write_text("[Game Files]\n")
    plugin(df / "Morrowind.esm", [], [misc("gold_001")])
    plugin(df / "Fooland.esm", [("Morrowind.esm", os.path.getsize(df / "Morrowind.esm"))],
           [misc("zz_chair"), misc("zz_table"), master_cell])
    plugin(df / "Patch.esp", [("Morrowind.esm", os.path.getsize(df / "Morrowind.esm")),
                              ("Fooland.esm", os.path.getsize(df / "Fooland.esm"))], [patch_cell])
    m.main([str(df), "--plugins", "Morrowind.esm", "Fooland.esm", "Patch.esp", "--no-vortex",
            "--no-archive-lookup", "--fix", "--yes", "--fix-log", str(g / "mwdialog_fixes.log")])
    body = next(b for _o, t, _f, b in m.iter_records((df / "Patch.esp").read_bytes()) if t == "CELL")
    subs = list(m.iter_subs(body))
    return ([m.cstr(d) for n, d in subs if n == "NAME"][0],
            [struct.unpack_from("<I", d)[0] for n, d in subs if n == "FRMR"])


def test_a_renumbered_reference_is_pointed_at_the_same_object(tmp_path):
    name, frmrs = setup(tmp_path, cell("Hall", ref(5, "zz_chair"), ref(6, "zz_table", x=500)),
                        cell("Hall", ref((2 << 24) | 3, "zz_chair", x=10)))
    assert (name, frmrs) == ("Hall", [(2 << 24) | 5])


def test_an_edit_with_no_match_nearby_is_removed(tmp_path):
    name, frmrs = setup(tmp_path, cell("Hall", ref(5, "zz_chair", x=900)),
                        cell("Hall", ref((2 << 24) | 3, "zz_chair", x=10)))
    assert frmrs == []


def test_an_interior_the_master_renamed_is_renamed_in_the_plugin(tmp_path):
    name, frmrs = setup(tmp_path, cell("New Hall", ref(7, "zz_chair")),
                        cell("Old Hall", ref((2 << 24) | 7, "zz_chair", x=10)))
    assert (name, frmrs) == ("New Hall", [(2 << 24) | 7])
