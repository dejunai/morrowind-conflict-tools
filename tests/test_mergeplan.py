"""Merge recommendations (mwdialog_mergeplan): a merge takes its last input's place, so nothing outside it
may load in between and change what an input changes; cells, door exits and leveled lists stay apart."""
import struct

from conftest import _load, sub, z, rec, plugin, misc, lev

mp = _load("mwdialog_mergeplan")
MW = [("Morrowind.esm", 0)]


def cell(name, door_to=None):
    body = sub("NAME", z(name)) + sub("DATA", struct.pack("<Iii", 1, 0, 0))
    if door_to:
        body += (sub("FRMR", struct.pack("<I", 1)) + sub("NAME", z("door_x"))
                 + sub("DODT", struct.pack("<6f", door_to[0] * 8192 + 100, door_to[1] * 8192 + 100, 0, 0, 0, 0)))
    return rec("CELL", body)


def plan(tmp_path, plugins):
    """plugins: [(name, records)] after Morrowind.esm, in load order."""
    (tmp_path / "Data Files").mkdir()
    order = [("Morrowind.esm", str(tmp_path / "Morrowind.esm"))]
    plugin(order[0][1], [], [misc("shared")])
    for name, records in plugins:
        path = str(tmp_path / name)
        plugin(path, MW, records)
        order.append((name, path))
    return mp.recommend(order, str(tmp_path / "Data Files"), str(tmp_path))


def groups(p):
    return [g["inputs"] for g in p["groups"]]


def test_lua_names_only_from_what_mwse_loads(tmp_path):
    rd = _load("mwdialog_redundant")
    mwse = tmp_path / "MWSE"
    for rel, text in (("mods/Live/main.lua", 'tes3.isModActive("Live.esp")'),
                      ("config/Live.json", '{"p": "LiveCfg.esp"}'),
                      ("config/Gone.json", '{"p": "GoneCfg.esp"}'),
                      ("config/mwfloatfix_data.json", '{"p": "Suite.esp"}'),
                      ("backups/mods/Old/main.lua", '"Backup.esp"')):
        (mwse / rel).parent.mkdir(parents=True, exist_ok=True)
        (mwse / rel).write_text(text)
    assert rd.lua_named_plugins(str(tmp_path)) == {"live.esp", "livecfg.esp"}


def test_merge_stays_before_a_plugin_that_changes_an_input(tmp_path):
    p = plan(tmp_path, [("A.esp", [misc("shared", 5)]), ("B.esp", [misc("b")]),
                        ("Z.esm", [misc("shared", 9)]), ("C.esp", [misc("c")]), ("D.esp", [misc("d")])])
    assert groups(p) == [["A.esp", "B.esp"], ["C.esp", "D.esp"]]
    assert p["groups"][0]["replaces"] == "B.esp"


def stat(id_, model="a.nif"):
    return rec("STAT", sub("NAME", z(id_)) + sub("MODL", z(model)))


def test_later_plugin_inside_the_merge_does_not_block(tmp_path):
    """A and C change the same static: merged together they keep their order, so C still wins."""
    p = plan(tmp_path, [("A.esp", [stat("s1")]), ("B.esp", [misc("b")]), ("C.esp", [stat("s1", "c.nif")])])
    assert groups(p) == [["A.esp", "B.esp", "C.esp"]]


def test_shared_cells_and_door_exits_stay_apart(tmp_path):
    p = plan(tmp_path, [("E.esp", [cell("Cave")]), ("F.esp", [cell("Cave")]), ("G.esp", [cell("Other")]),
                        ("H.esp", [cell("Den", (3, 4))]), ("I.esp", [cell("Lair", (3, 4))])])
    assert groups(p) == [["F.esp", "G.esp", "H.esp"]]
    assert "before F.esp" in p["left_out"]["E.esp"]


def test_shared_leveled_list_leaves_the_later_plugin_out(tmp_path):
    p = plan(tmp_path, [("L1.esp", [rec("LEVI", lev(["a"]))]), ("L2.esp", [rec("LEVI", lev(["b"]))]),
                        ("M.esp", [misc("m")])])
    assert "L2.esp" not in {n for g in groups(p) for n in g}
    assert "L1.esp" in p["left_out"]["L2.esp"]
