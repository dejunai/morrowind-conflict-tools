"""--fix (Cell Fixes): an object two unrelated mods both put in the same spot is deleted from the earlier mod
in the patch (what mwcollide hides in the game), listed, and brought back once the later mod leaves."""
import struct
import types

from conftest import m, plugin, rec, sub, z


def _cell(*refs):
    return rec("CELL", sub("NAME", z("Test Room")) + sub("DATA", struct.pack("<Iii", 1, 0, 0)) + b"".join(refs))


def _ref(index, oid, x=0.0):
    return sub("FRMR", struct.pack("<I", index)) + sub("NAME", z(oid)) + \
        sub("DATA", struct.pack("<6f", x, 0.0, 0.0, 0.0, 0.0, 0.0))


def _setup(tmp_path, c_moves_a=False):
    data = tmp_path / "Data Files"
    data.mkdir()
    size = len(plugin(data / "Master.esm", [], [_cell()]))
    a_size = len(plugin(data / "A.esp", [("Master.esm", size)], [_cell(_ref(1, "misc_bottle"))]))
    plugin(data / "B.esp", [("Master.esm", size)], [_cell(_ref(1, "misc_bottle", x=3.0))])
    order = ["Master.esm", "A.esp", "B.esp"]
    if c_moves_a:                                   # a mod built on A moves A's bottle
        plugin(data / "C.esp", [("Master.esm", size), ("A.esp", a_size)], [_cell(_ref((2 << 24) | 1, "misc_bottle", x=9.0))])
        order.append("C.esp")
    _order(tmp_path, order)
    args = types.SimpleNamespace(data_dir=str(data), dry_run=False, ini=str(tmp_path / "Morrowind.ini"),
                                 fix_log="fix.log", fix=False)
    return data, args, order


def _order(tmp_path, order):
    (tmp_path / "Morrowind.ini").write_text("[Game Files]\n" + "".join(f"GameFile{i}={n}\n" for i, n in enumerate(order)))
    m.write_load_order(str(tmp_path), order, "test")


def _deleted(data):
    out = data / m.CELL_WINNER_PATCH
    if not out.exists():
        return []
    raw = out.read_bytes()
    masters = m.plugin_masters(raw)
    found = []
    for _o, tag, _f, body in m.iter_records(raw):
        if tag != "CELL":
            continue
        head, pers, _n0, temp = m.split_cell(body)
        for blk in pers + temp:
            if any(s == "DELE" for s, _d in blk):
                v = struct.unpack_from("<I", blk[0][1])[0]
                found.append((masters[(v >> 24) - 1], v & 0xFFFFFF))
    return found


def test_the_earlier_mods_doubled_copy_is_deleted_and_listed(tmp_path):
    data, args, order = _setup(tmp_path)
    m.fix_cell_winners(args, [(n, str(data / n)) for n in order])
    assert _deleted(data) == [("A.esp", 1)]
    rows = [ln for ln in (tmp_path / m.DOUBLED_DELETED_FILE).read_text().splitlines() if not ln.startswith(";")]
    assert rows == ["test room\tmisc_bottle\tA.esp\tB.esp\tmisc_bottle"]


def test_a_copy_another_mod_changes_is_left_alone(tmp_path):
    data, args, order = _setup(tmp_path, c_moves_a=True)
    m.fix_cell_winners(args, [(n, str(data / n)) for n in order])
    assert _deleted(data) == []


def test_it_comes_back_when_the_winning_mod_leaves(tmp_path):
    data, args, order = _setup(tmp_path)
    m.fix_cell_winners(args, [(n, str(data / n)) for n in order])
    _order(tmp_path, ["Master.esm", "A.esp"])
    assert m.release_lost_doubles(args) == 1
    assert _deleted(data) == []
    assert m.release_lost_doubles(args) == 0
