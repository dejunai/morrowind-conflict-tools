"""--fix (Cell Fixes): someone left over water because a later mod took away what they stood on is moved to footing
beside it, and only then (a dock rebuilt a little to the side left a fisherman on the seabed)."""
import json
import struct
import types

import pytest

from conftest import m, plugin, rec, sub, z
from mwdialog_footing import nif_triangles, RESCUE_DATA
from nif_fixture import deck

X, Y = 2000.0, 2000.0


def land(height):
    return rec("LAND", sub("INTV", struct.pack("<ii", 0, 0))
               + sub("VHGT", struct.pack("<f", height / 8.0) + bytes(4225 + 3)))


def cell(*refs):
    return rec("CELL", sub("NAME", z("")) + sub("DATA", struct.pack("<Iii", 0, 0, 0)) + b"".join(refs))


def ref(index, oid, x, y, height):
    return sub("FRMR", struct.pack("<I", index)) + sub("NAME", z(oid)) + \
        sub("DATA", struct.pack("<6f", x, y, height, 0.0, 0.0, 0.0))


def npc(health):
    data = bytearray(52)
    struct.pack_into("<H", data, 38, health)
    return rec("NPC_", sub("NAME", z("fisher")) + sub("NPDT", bytes(data)))


def run(tmp_path, *new_docks, seabed=-100, deletes=True, health=50, unreadable=False, dry_run=False):
    """The fisher (placed on a dock 88 high over the seabed) after a mod deletes that dock and builds new_docks."""
    data = tmp_path / "Data Files"
    (data / "Meshes").mkdir(parents=True)
    (data / "Meshes" / "dock.nif").write_bytes(deck(128, 88))
    (data / "Meshes" / "new.nif").write_bytes(deck(128, 67))
    (data / "Meshes" / "bad.nif").write_bytes(b"not a model")
    size = len(plugin(data / "Master.esm", [], [
        rec("STAT", sub("NAME", z("dock")) + sub("MODL", z("dock.nif"))),
        rec("STAT", sub("NAME", z("new_dock")) + sub("MODL", z("new.nif"))),
        rec("STAT", sub("NAME", z("odd")) + sub("MODL", z("bad.nif"))),
        land(seabed), cell(ref(1, "dock", X, Y, 0.0))]))
    plugin(data / "People.esp", [("Master.esm", size)], [npc(health), cell(ref(1, "fisher", X, Y, 88.0))])
    changes = [sub("FRMR", struct.pack("<I", (1 << 24) | 1)) + sub("NAME", z("dock"))
               + sub("DELE", struct.pack("<I", 0))] if deletes else []
    changes += [ref(i + 1, "new_dock", X + dx, Y, 0.0) for i, dx in enumerate(new_docks)]
    if unreadable:
        changes.append(ref(9, "odd", X + 50, Y, 0.0))
    if changes:
        plugin(data / "Docks.esp", [("Master.esm", size)], [cell(*changes)])
    order = ["Master.esm", "People.esp"] + (["Docks.esp"] if changes else [])
    (tmp_path / "Morrowind.ini").write_text("[Game Files]\n" + "".join(f"GameFile{i}={n}\n" for i, n in enumerate(order)))
    m.write_load_order(str(tmp_path), order, "test")
    args = types.SimpleNamespace(data_dir=str(data), dry_run=dry_run, ini=str(tmp_path / "Morrowind.ini"),
                                 fix_log="fix.log", fix=False)
    m.fix_cell_winners(args, [(n, str(data / n)) for n in order])
    moved = None
    if (data / m.CELL_WINNER_PATCH).exists():
        for _o, t, _f, body in m.iter_records((data / m.CELL_WINNER_PATCH).read_bytes()):
            if t != "CELL":
                continue
            _head, pers, _n0, temp = m.split_cell(body)
            for blk in pers + temp:
                d = dict(blk)
                if "DATA" in d and m.cstr(d["NAME"]) == "fisher":
                    moved = struct.unpack_from("<3f", d["DATA"])
    path = data / "MWSE" / "config" / RESCUE_DATA
    return moved, json.loads(path.read_text()) if path.exists() else None


def test_moved_onto_the_dock_built_beside_the_lost_one(tmp_path):
    moved, data = run(tmp_path, 160.0)
    x, y, height = moved
    assert X + 32 <= x <= X + 128 and abs(y - Y) < 64 and height == pytest.approx(70.0)
    assert [n["id"] for n in data["npcs"]] == ["fisher"]
    assert data["npcs"][0]["cell"] == "#0,0" and data["npcs"][0]["from"] == [2000, 2000, 88]


def test_moved_further_out_when_nothing_is_close_by(tmp_path):
    moved, data = run(tmp_path, 600.0)
    x, y, height = moved
    assert X + 400 <= x <= X + 700 and abs(y - Y) < 64 and height == pytest.approx(70.0)
    assert [n["id"] for n in data["npcs"]] == ["fisher"] and data["left"] == []


def test_only_reported_without_dry_footing_anywhere_near(tmp_path):
    moved, data = run(tmp_path)
    assert moved is None and data["npcs"] == []
    assert len(data["left"]) == 1 and "no dry footing" in data["left"][0]


def test_moved_off_land_a_later_mod_sank(tmp_path):
    data = tmp_path / "Data Files"
    (data / "Meshes").mkdir(parents=True)
    (data / "Meshes" / "new.nif").write_bytes(deck(128, 67))
    size = len(plugin(data / "Master.esm", [], [
        rec("STAT", sub("NAME", z("new_dock")) + sub("MODL", z("new.nif"))),
        land(40), cell(ref(1, "new_dock", X + 900, Y, 0.0))]))
    plugin(data / "People.esp", [("Master.esm", size)], [npc(50), cell(ref(1, "fisher", X, Y, 40.0))])
    plugin(data / "Sea.esp", [("Master.esm", size)], [land(-100)])
    order = ["Master.esm", "People.esp", "Sea.esp"]
    (tmp_path / "Morrowind.ini").write_text("[Game Files]\n" + "".join(f"GameFile{i}={n}\n" for i, n in enumerate(order)))
    m.write_load_order(str(tmp_path), order, "test")
    args = types.SimpleNamespace(data_dir=str(data), dry_run=False, ini=str(tmp_path / "Morrowind.ini"),
                                 fix_log="fix.log", fix=False)
    m.fix_cell_winners(args, [(n, str(data / n)) for n in order])
    rescue = json.loads((data / "MWSE" / "config" / RESCUE_DATA).read_text())
    assert rescue["left"] == [] and [n["id"] for n in rescue["npcs"]] == ["fisher"]
    x, y, height = rescue["npcs"][0]["to"]
    assert X + 700 <= x <= X + 1000 and abs(y - Y) <= 128 and height == 70


def test_follows_the_island_a_later_mod_moved(tmp_path):
    def land_at(gx, gy, height):
        return rec("LAND", sub("INTV", struct.pack("<ii", gx, gy))
                   + sub("VHGT", struct.pack("<f", height / 8.0) + bytes(4225 + 3)))
    data = tmp_path / "Data Files"
    (data / "Meshes").mkdir(parents=True)
    size = len(plugin(data / "Master.esm", [], [land_at(0, 0, 40)]))
    plugin(data / "People.esp", [("Master.esm", size)], [npc(50), cell(ref(1, "fisher", X, Y, 40.0))])
    plugin(data / "Island.esp", [("Master.esm", size)], [land_at(0, 0, -100), land_at(2, 1, 40)])
    plugin(data / "Tweak.esp", [("Master.esm", size)], [land_at(2, 1, 48)])
    order = ["Master.esm", "People.esp", "Island.esp", "Tweak.esp"]
    (tmp_path / "Morrowind.ini").write_text("[Game Files]\n" + "".join(f"GameFile{i}={n}\n" for i, n in enumerate(order)))
    m.write_load_order(str(tmp_path), order, "test")
    args = types.SimpleNamespace(data_dir=str(data), dry_run=False, ini=str(tmp_path / "Morrowind.ini"),
                                 fix_log="fix.log", fix=False)
    m.fix_cell_winners(args, [(n, str(data / n)) for n in order])
    blocks = [blk for _o, t, _f, body in m.iter_records((data / m.CELL_WINNER_PATCH).read_bytes()) if t == "CELL"
              for part in m.split_cell(body)[1::2] for blk in part]
    (blk,) = blocks
    d = dict(blk)
    assert blk[0][0] == "MVRF" and struct.unpack("<ii", d["CNDT"]) == (2, 1) and d["MVRF"] == d["FRMR"]
    assert struct.unpack_from("<3f", d["DATA"]) == pytest.approx((X + 2 * 8192, Y + 8192, 51.0))


def test_a_model_that_cannot_be_read_means_no_move(tmp_path):
    moved, data = run(tmp_path, 160.0, unreadable=True)
    assert moved is None and "can't be read" in data["left"][0]


@pytest.mark.parametrize("change", [
    {"deletes": False},                            # still standing on it
    {"seabed": 60},                                # dry ground
    {"health": 0},                                 # a body
])
def test_others_are_left_alone(tmp_path, change):
    moved, data = run(tmp_path, 160.0, **change)
    assert moved is None and data["npcs"] == []


def test_a_dry_run_writes_nothing(tmp_path):
    assert run(tmp_path, 160.0, dry_run=True) == (None, None)


def test_dry_run_does_not_replace_moved_pieces_report(tmp_path, capsys):
    data = tmp_path / "Data Files"
    data.mkdir()
    def interior(*refs):
        return rec("CELL", sub("NAME", z("House")) + sub("DATA", struct.pack("<Iii", 1, 0, 0))
                   + b"".join(refs))
    size = len(plugin(data / "Master.esm", [], [
        rec("STAT", sub("NAME", z("table"))),
        rec("STAT", sub("NAME", z("candle"))),
        interior(ref(1, "table", 0, 0, 0))]))
    plugin(data / "People.esp", [("Master.esm", size)], [interior(ref(1, "candle", 10, 0, 0))])
    plugin(data / "Mover.esp", [("Master.esm", size)], [interior(ref((1 << 24) | 1, "table", 300, 0, 0))])
    order = ["Master.esm", "People.esp", "Mover.esp"]
    m.write_load_order(str(tmp_path), order, "test")
    report = tmp_path / m.CELL_FIXES_REPORT
    report.write_text("existing report", encoding="utf-8")
    args = types.SimpleNamespace(data_dir=str(data), dry_run=True, ini=str(tmp_path / "Morrowind.ini"),
                                 fix_log="fix.log", fix=False)
    m.fix_cell_winners(args, [(n, str(data / n)) for n in order])
    assert "Moved pieces: 1 object(s)" in capsys.readouterr().out
    assert report.read_text(encoding="utf-8") == "existing report"
    assert not (data / m.CELL_WINNER_PATCH).exists()


def test_the_model_reader_follows_the_games_collision_rules():
    assert len(nif_triangles(deck(64, 10))) == 2
    assert len(nif_triangles(deck(64, 10, root=b"RootCollisionNode"))) == 2
    assert len(nif_triangles(deck(64, 10, node_name=b"NiTriShape"))) == 2
    assert nif_triangles(deck(64, 10, root=b"AvoidNode")) == []
    assert nif_triangles(deck(64, 10, extra_text=b"NCO")) == []
    assert nif_triangles(b"not a model") is None
    assert nif_triangles(deck(64, 10)[:120]) is None
