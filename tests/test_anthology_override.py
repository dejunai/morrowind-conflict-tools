"""Cell Fixes: what mods made for land a later mod moved elsewhere put there goes with it."""
import struct
import types

import pytest

from conftest import m, plugin, rec, sub, z
import mwdialog_anthology_override as A

CELL = 8192


def land_at(gx, gy, height):
    return rec("LAND", sub("INTV", struct.pack("<ii", gx, gy))
               + sub("VHGT", struct.pack("<f", height / 8.0) + bytes(4225 + 3)))


def cell_at(gx, gy, *refs):
    return rec("CELL", sub("NAME", z("")) + sub("DATA", struct.pack("<Iii", 0, gx, gy)) + b"".join(refs))


def ref(index, oid, x, y, height):
    return sub("FRMR", struct.pack("<I", index)) + sub("NAME", z(oid)) + \
        sub("DATA", struct.pack("<6f", x, y, height, 0.0, 0.0, 0.0))


def run(tmp_path, cells=8, stray=False):
    """Mover.esp sinks Master's island (cells (0..cells-1, 0)) and puts it down 2 cells east, 1 north.
    People.esp (made for the old island) and Aware.esp (made for the moved one) each put a rock on cell (3, 0).
    stray: Mover also raises cell (12, 5), and Other.esp reshapes (10, 4) where People put a rock too."""
    data = tmp_path / "Data Files"
    data.mkdir(parents=True)
    heights = [40 + 8 * i for i in range(cells)]
    size = len(plugin(data / "Master.esm", [], [
        rec("STAT", sub("NAME", z("rock")) + sub("MODL", z("rock.nif")))]
        + [land_at(i, 0, h) for i, h in enumerate(heights)] + [land_at(10, 4, 30)]))
    mover = plugin(data / "Mover.esp", [("Master.esm", size)],
                   [land_at(i, 0, -100) for i in range(cells)] + [land_at(i + 2, 1, h) for i, h in enumerate(heights)]
                   + ([land_at(12, 5, 200)] if stray else []))
    x, y = 3 * CELL + 2000.0, 2000.0
    plugin(data / "People.esp", [("Master.esm", size)], [cell_at(3, 0, ref(1, "rock", x, y, heights[3]))]
           + ([cell_at(10, 4, ref(2, "rock", 10 * CELL + 2000.0, 4 * CELL + 2000.0, 30))] if stray else []))
    plugin(data / "Aware.esp", [("Master.esm", size), ("Mover.esp", len(mover))],
           [cell_at(3, 0, ref(1, "rock", x + 500, y, heights[3]))])
    order = ["Master.esm", "Mover.esp", "People.esp", "Aware.esp"]
    if stray:
        plugin(data / "Other.esp", [("Master.esm", size)], [land_at(10, 4, 34)])
        order.append("Other.esp")
    (tmp_path / "Morrowind.ini").write_text("[Game Files]\n" + "".join(f"GameFile{i}={n}\n" for i, n in enumerate(order)))
    m.write_load_order(str(tmp_path), order, "test")
    args = types.SimpleNamespace(data_dir=str(data), dry_run=False, ini=str(tmp_path / "Morrowind.ini"),
                                 fix_log="fix.log", fix=False)
    m.fix_cell_winners(args, [(n, str(data / n)) for n in order])
    patch = data / m.CELL_WINNER_PATCH
    moved = [dict(blk) for _o, t, _f, body in m.iter_records(patch.read_bytes()) if t == "CELL"
             for part in m.split_cell(body)[1::2] for blk in part if blk[0][0] == "MVRF"] if patch.exists() else []
    return moved, (x, y, heights[3])


def test_a_mods_objects_follow_the_land_it_was_made_for(tmp_path):
    moved, (x, y, h) = run(tmp_path)
    (d,) = moved                                  # People's rock; Aware's stays
    assert struct.unpack("<ii", d["CNDT"]) == (5, 1) and d["MVRF"] == d["FRMR"]
    assert struct.unpack_from("<3f", d["DATA"]) == pytest.approx((x + 2 * CELL, y + CELL, h))


def test_land_the_mover_did_not_sink_keeps_its_objects(tmp_path):
    moved, _p = run(tmp_path, stray=True)
    assert [struct.unpack("<ii", d["CNDT"]) for d in moved] == [(5, 1)]


def test_a_small_move_is_only_followed_when_known(tmp_path, monkeypatch):
    assert run(tmp_path / "unknown", cells=4)[0] == []
    monkeypatch.setattr(A, "KNOWN_MOVES", {(2, 1): frozenset({"mover.esp"})})
    assert len(run(tmp_path / "known", cells=4)[0]) == 1


def test_a_mod_listed_as_made_for_the_moved_land_stays(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "MADE_FOR_MOVED", frozenset({"people.esp"}))
    assert run(tmp_path)[0] == []
