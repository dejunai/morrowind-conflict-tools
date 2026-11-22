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


def test_only_reported_without_footing_close_by(tmp_path):
    moved, data = run(tmp_path, 600.0)
    assert moved is None and data["npcs"] == []
    assert len(data["left"]) == 1 and "no footing" in data["left"][0]


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


def test_the_model_reader_follows_the_games_collision_rules():
    assert len(nif_triangles(deck(64, 10))) == 2
    assert len(nif_triangles(deck(64, 10, root=b"RootCollisionNode"))) == 2
    assert len(nif_triangles(deck(64, 10, node_name=b"NiTriShape"))) == 2
    assert nif_triangles(deck(64, 10, root=b"AvoidNode")) == []
    assert nif_triangles(deck(64, 10, extra_text=b"NCO")) == []
    assert nif_triangles(b"not a model") is None
    assert nif_triangles(deck(64, 10)[:120]) is None
