"""--fix (Cell Fixes, reshaped land): an object follows the land that's used, but is never taken from above the
sea to below it (NPCs on docks and whole towns went to the seabed that way)."""
import struct
import types

import pytest

from conftest import m, plugin, rec, sub, z
from nif_fixture import deck


def land(height):
    return rec("LAND", sub("INTV", struct.pack("<ii", 0, 0))
               + sub("VHGT", struct.pack("<f", height / 8.0) + bytes(4225 + 3)))


def cell(*refs):
    return rec("CELL", sub("NAME", z("")) + sub("DATA", struct.pack("<Iii", 0, 0, 0)) + b"".join(refs))


def ref(index, oid, height, extra=b""):
    return sub("FRMR", struct.pack("<I", index)) + sub("NAME", z(oid)) + extra + \
        sub("DATA", struct.pack("<6f", 1000.0, 1000.0, height, 0.0, 0.0, 0.0))


def shifted(tmp_path, tag, height, was, now, arrival=None, deck_at=None):
    """Where Cell Fixes puts an object placed at `height` on land `was` high, when a later mod makes it `now`:
    (the object's z, the door arrival's z), None for one left alone."""
    data = tmp_path / "Data Files"
    data.mkdir()
    body = sub("NAME", z("thing"))
    if deck_at is not None:
        (data / "Meshes").mkdir()
        (data / "Meshes" / "deck.nif").write_bytes(deck(128, deck_at))
        body += sub("MODL", z("deck.nif"))
    size = len(plugin(data / "Master.esm", [], [rec(tag, body), land(was)]))
    order = ["Master.esm", "A.esp"]
    if arrival is None:
        plugin(data / "A.esp", [("Master.esm", size)], [cell(ref(1, "thing", height))])
    else:                                          # Cell Fixes follows a door once it has led indoors
        dodt = sub("DODT", struct.pack("<6f", 1000.0, 1000.0, arrival, 0.0, 0.0, 0.0))
        asize = len(plugin(data / "A.esp", [("Master.esm", size)],
                           [cell(ref(1, "thing", height, dodt + sub("DNAM", z("Inn"))))]))
        plugin(data / "Out.esp", [("Master.esm", size), ("A.esp", asize)],
               [cell(ref((2 << 24) | 1, "thing", height, dodt))])
        order.append("Out.esp")
    plugin(data / "Land.esp", [("Master.esm", size)], [land(now)])
    order.append("Land.esp")
    (tmp_path / "Morrowind.ini").write_text("[Game Files]\n" + "".join(f"GameFile{i}={n}\n" for i, n in enumerate(order)))
    m.write_load_order(str(tmp_path), order, "test")
    args = types.SimpleNamespace(data_dir=str(data), dry_run=False, ini=str(tmp_path / "Morrowind.ini"),
                                 fix_log="fix.log", fix=False)
    m.fix_cell_winners(args, [(n, str(data / n)) for n in order])
    out = data / m.CELL_WINNER_PATCH
    if not out.exists():
        return None, None
    for _o, t, _f, body in m.iter_records(out.read_bytes()):
        if t != "CELL":
            continue
        _head, pers, _n0, temp = m.split_cell(body)
        for blk in pers + temp:
            d = dict(blk)
            return (struct.unpack_from("<6f", d["DATA"])[2],
                    struct.unpack_from("<6f", d["DODT"])[2] if "DODT" in d else None)
    return None, None


@pytest.mark.parametrize("tag, height, was, now", [
    ("NPC_", 81, -232, -360),                      # on a dock, the seabed lowered: was put at -47
    ("NPC_", 4407, 4392, -1104),                   # a town another mod's old land drowns
    ("CREA", -40, -40, -240),                      # wading: was put over its head
    ("STAT", 8, 0, -120),
])
def test_nothing_is_lowered_from_above_the_sea_to_below_it(tmp_path, tag, height, was, now):
    z_now, _ = shifted(tmp_path, tag, height, was, now)
    assert z_now is None or z_now == height


def test_a_platform_is_not_sunk_though_its_origin_is_in_the_water(tmp_path):
    z_now, _ = shifted(tmp_path, "STAT", -120, -120, -1736, deck_at=382)
    assert z_now is None


def test_a_model_wholly_under_water_still_follows_the_land(tmp_path):
    z_now, _ = shifted(tmp_path, "STAT", -120, -120, -400, deck_at=20)
    assert z_now == pytest.approx(-400)


def test_a_reference_moved_to_another_cell_is_not_put_back(tmp_path):
    data = tmp_path / "Data Files"
    data.mkdir()
    size = len(plugin(data / "Master.esm", [], [rec("STAT", sub("NAME", z("thing"))), land(-100)]))
    asize = len(plugin(data / "A.esp", [("Master.esm", size)], [cell(ref(1, "thing", -100))]))
    key = struct.pack("<I", (2 << 24) | 1)
    moved = sub("MVRF", key) + sub("CNDT", struct.pack("<ii", 1, 0)) + sub("FRMR", key) + sub("NAME", z("thing")) + \
        sub("DATA", struct.pack("<6f", 9000.0, 1000.0, 11.0, 0.0, 0.0, 0.0))
    plugin(data / "Mover.esp", [("Master.esm", size), ("A.esp", asize)], [cell(moved)])
    plugin(data / "Land.esp", [("Master.esm", size)], [land(-300)])
    order = ["Master.esm", "A.esp", "Mover.esp", "Land.esp"]
    (tmp_path / "Morrowind.ini").write_text("[Game Files]\n" + "".join(f"GameFile{i}={n}\n" for i, n in enumerate(order)))
    m.write_load_order(str(tmp_path), order, "test")
    args = types.SimpleNamespace(data_dir=str(data), dry_run=False, ini=str(tmp_path / "Morrowind.ini"),
                                 fix_log="fix.log", fix=False)
    m.fix_cell_winners(args, [(n, str(data / n)) for n in order])
    assert not (data / m.CELL_WINNER_PATCH).exists()


@pytest.mark.parametrize("tag, height, was, now", [
    ("STAT", 500, 480, 200),                       # still dry
    ("STAT", -300, -304, -504),                    # was under water already
    ("NPC_", -8, -8, -48),                         # wading, and not out of its depth
])
def test_objects_still_follow_the_land_otherwise(tmp_path, tag, height, was, now):
    z_now, _ = shifted(tmp_path, tag, height, was, now)
    assert z_now == pytest.approx(height + now - was)


def test_a_door_does_not_start_to_arrive_under_water(tmp_path):
    _, arrives = shifted(tmp_path, "DOOR", 40, 40, -200, arrival=48)
    assert arrives in (None, 48)
