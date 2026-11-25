"""CR-12: --fix (Cell Fixes) puts a loose item down when a mod its plugin doesn't know took away what it stood on
(the Seyda Neen bucket: Ports Of Vvardenfell deletes the chargen dock and lays its own 24 units lower; the bucket,
placed by a plugin that knows only the vanilla dock, was left hanging). Exteriors only."""
import struct
import types

import pytest

from conftest import m, plugin, rec, sub, z
from nif_fixture import deck

X, Y = 2000.0, 2000.0
DECK = 34.1                                      # the dock's deck over its origin
OLD_DOCK, NEW_DOCK, BUCKET = 73.8, 49.4, 107.9   # as in the game: the bucket sat on the vanilla deck (73.8 + 34.1)


def cell(*refs):
    return rec("CELL", sub("NAME", z("")) + sub("DATA", struct.pack("<Iii", 0, 0, 0)) + b"".join(refs))


def ref(index, oid, x, y, height):
    return sub("FRMR", struct.pack("<I", index)) + sub("NAME", z(oid)) + \
        sub("DATA", struct.pack("<6f", x, y, height, 0.0, 0.0, 0.0))


def land(height):
    return rec("LAND", sub("INTV", struct.pack("<ii", 0, 0))
               + sub("VHGT", struct.pack("<f", height / 8.0) + bytes(4225 + 3)))


def run(tmp_path, new_dock=NEW_DOCK, unreadable=False, dry_run=False):
    data = tmp_path / "Data Files"
    (data / "Meshes").mkdir(parents=True)
    (data / "Meshes" / "dock.nif").write_bytes(deck(256, DECK))
    (data / "Meshes" / "bad.nif").write_bytes(b"not a model")
    size = len(plugin(data / "Master.esm", [], [
        rec("STAT", sub("NAME", z("ex_de_docks_center")) + sub("MODL", z("dock.nif"))),
        rec("STAT", sub("NAME", z("ex_de_docks_centerb")) + sub("MODL", z("dock.nif"))),
        rec("STAT", sub("NAME", z("odd")) + sub("MODL", z("bad.nif"))),
        rec("MISC", sub("NAME", z("misc_com_bucket_01")) + sub("MODL", z("bucket.nif"))),
        land(-200), cell(ref(1, "ex_de_docks_center", X, Y, OLD_DOCK))]))
    plugin(data / "Squat.esp", [("Master.esm", size)], [cell(ref(264, "misc_com_bucket_01", X + 10, Y, BUCKET))])
    changes = [sub("FRMR", struct.pack("<I", (1 << 24) | 1)) + sub("NAME", z("ex_de_docks_center"))
               + sub("DELE", struct.pack("<I", 0)), ref(2, "ex_de_docks_centerb", X, Y, new_dock)]
    if unreadable:
        changes.append(ref(3, "odd", X + 300, Y, 0.0))
    plugin(data / "Ports.esp", [("Master.esm", size)], [cell(*changes)])
    order = ["Master.esm", "Ports.esp", "Squat.esp"]
    (tmp_path / "Morrowind.ini").write_text("[Game Files]\n" + "".join(f"GameFile{i}={n}\n" for i, n in enumerate(order)))
    m.write_load_order(str(tmp_path), order, "test")
    args = types.SimpleNamespace(data_dir=str(data), dry_run=dry_run, ini=str(tmp_path / "Morrowind.ini"),
                                 fix_log="fix.log", fix=False)
    m.fix_cell_winners(args, [(n, str(data / n)) for n in order])
    found = None
    if (data / m.CELL_WINNER_PATCH).exists():
        for _o, t, _f, body in m.iter_records((data / m.CELL_WINNER_PATCH).read_bytes()):
            if t != "CELL":
                continue
            _head, pers, _n0, temp = m.split_cell(body)
            for blk in pers + temp:
                d = dict(blk)
                if "DATA" in d and m.cstr(d["NAME"]) == "misc_com_bucket_01":
                    found = struct.unpack_from("<6f", d["DATA"]), struct.unpack_from("<I", d["FRMR"])[0]
    return found


def test_the_bucket_is_put_down_on_the_lower_dock(tmp_path, capsys):
    (pos, frmr) = run(tmp_path)
    assert pos[0] == pytest.approx(X + 10) and pos[1] == pytest.approx(Y)
    assert pos[2] == pytest.approx(NEW_DOCK + DECK + 0.5, abs=0.01)          # about 84: on Ports' deck at 83.5
    assert frmr & 0xFFFFFF == 264 and frmr >> 24 >= 1                          # Squat.esp's own reference
    out = " ".join(capsys.readouterr().out.split())
    assert "Floating items: 1 put down" in out and "misc_com_bucket_01" in out


def test_an_item_still_resting_is_left_alone(tmp_path):
    assert run(tmp_path, new_dock=OLD_DOCK + 1.0) is None


def test_an_item_over_water_or_beside_an_unreadable_model_is_left(tmp_path, capsys):
    assert run(tmp_path, new_dock=-60.0) is None                               # the deck is under water now
    assert "is under water" in " ".join(capsys.readouterr().out.split())
    assert run(tmp_path / "b", unreadable=True) is None
    assert "model can't be read" in " ".join(capsys.readouterr().out.split())
