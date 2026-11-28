"""mwperformers_data.json: the interiors with performers (an NPC whose model or script names a performer, the rule
mwperformers uses in game), from each reference's last version in the load order."""
import json
import types

from conftest import _load, plugin, rec, sub, z

CM = _load("mwdialog_cellmods")


def npc(id_, model="base_anim.nif", script=None):
    body = sub("NAME", z(id_)) + sub("MODL", z(model))
    if script:
        body += sub("SCRI", z(script))
    return rec("NPC_", body)


def test_performers_are_found_by_model_or_script_and_a_deleted_one_is_left_out(tmp_path):
    data = tmp_path / "Data Files"
    data.mkdir()
    plugin(str(data / "Bards.esp"), [], [npc("lute_guy", "am\\am_bard2.nif"), npc("singer", script="DM_Bard_script"),
                                         npc("guard", script="guard_script"), npc("drummer", "am\\drum.nif")])
    order = [("Bards.esp", str(data / "Bards.esp"))]
    inn = ("i", "balmora, eight plates")
    ref_hist = {
        inn: {
            1: [(0, "bards.esp", "Lute_Guy", (10.4, 20.6, 30.0), 1.0, False)],
            2: [(0, "bards.esp", "singer", (1, 2, 3), 1.0, False)],
            3: [(0, "bards.esp", "guard", (5, 5, 5), 1.0, False)],
            4: [(0, "bards.esp", "drummer", (7, 7, 7), 1.0, False),
                (1, "later.esp", "drummer", (7, 7, 7), 1.0, True)],          # a later plugin deletes him
        },
        ("e", -3, -2): {5: [(0, "bards.esp", "singer", (0, 0, 0), 1.0, False)]},   # exteriors are not listed
    }
    cells = CM.performers_by_interior(order, ref_hist, {inn: "Balmora, Eight Plates"})
    assert list(cells) == ["balmora, eight plates"]
    assert [(e["id"], e["pos"]) for e in cells["balmora, eight plates"]] == [("lute_guy", [10, 21, 30]),
                                                                             ("singer", [1, 2, 3])]
    args = types.SimpleNamespace(data_dir=str(data))
    assert CM.write_performer_data(args, order, ref_hist, {inn: "Balmora, Eight Plates"}) == 2
    written = json.loads((data / "MWSE" / "config" / CM.PERFORMERS_DATA).read_text(encoding="utf-8"))
    assert written["count"] == 2 and list(written["cells"]) == ["balmora, eight plates"]
