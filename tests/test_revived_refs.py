"""--fix (Cell Fixes): an object one plugin deletes and a later plugin, not built on it, changes again stays deleted."""
import os
import struct
import types

from conftest import m, plugin, rec, sub, z


def _cell(*refs):
    return rec("CELL", sub("NAME", z("")) + sub("DATA", struct.pack("<Iii", 0, -2, -9)) + b"".join(refs))


def _ref(index, oid, deleted=False, x=0.0):
    body = sub("FRMR", struct.pack("<I", index)) + sub("NAME", z(oid))
    return body + (sub("DELE", struct.pack("<I", 0)) if deleted else
                   sub("DATA", struct.pack("<6f", x, 0.0, 0.0, 0.0, 0.0, 0.0)))


def _run(tmp_path, reviver_masters):
    data = tmp_path / "Data Files"
    data.mkdir()
    size = len(plugin(data / "Master.esm", [], [_cell(_ref(1, "ex_plat"))]))
    a_size = len(plugin(data / "A.esp", [("Master.esm", size)], [_cell(_ref((1 << 24) | 1, "ex_plat", deleted=True))]))
    masters = [("Master.esm", size)] + ([("A.esp", a_size)] if "A.esp" in reviver_masters else [])
    plugin(data / "B.esp", masters, [_cell(_ref((1 << 24) | 1, "ex_plat_sound", x=5.0))])
    order = ["Master.esm", "A.esp", "B.esp"]
    (tmp_path / "Morrowind.ini").write_text("[Game Files]\n" + "".join(f"GameFile{i}={n}\n" for i, n in enumerate(order)))
    args = types.SimpleNamespace(data_dir=str(data), dry_run=False, ini=str(tmp_path / "Morrowind.ini"),
                                 fix_log="fix.log")
    m.fix_cell_winners(args, [(n, str(data / n)) for n in order])
    out = data / m.CELL_WINNER_PATCH
    if not out.exists():
        return None
    return [body for _o, tag, _f, body in m.iter_records(out.read_bytes()) if tag == "CELL"]


def test_a_deletion_a_later_unaware_plugin_undoes_is_kept(tmp_path):
    cells = _run(tmp_path, reviver_masters=("Master.esm",))
    assert cells and b"DELE" in cells[0] and b"ex_plat_sound" in cells[0]


def test_a_plugin_built_on_the_deleter_may_bring_it_back(tmp_path):
    cells = _run(tmp_path, reviver_masters=("Master.esm", "A.esp"))
    assert not cells or not any(b"DELE" in c for c in cells)
