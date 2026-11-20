r"""An MGE XE grass plugin in the load order is left out of every run (sort, cell conflicts, Cell Fixes, --fix):
the game never loads it; MGE XE's distant land generator reads it from Data Files\Grass."""
from conftest import m, plugin, rec, sub, z


def test_a_grass_plugin_is_left_out_and_others_are_kept(tmp_path):
    grass = tmp_path / "Rem-TOTSP.esp"
    plugin(grass, [], [rec("STAT", sub("NAME", z("tuft_01")) + sub("MODL", z(r"grass\tuft01.nif")))])
    normal = tmp_path / "Patch.esp"
    plugin(normal, [], [rec("STAT", sub("NAME", z("crate")) + sub("MODL", z(r"o\crate.nif")))])
    npc = tmp_path / "Npc.esp"
    plugin(npc, [], [rec("NPC_", sub("NAME", z("bob")))])
    kept, dropped = m.drop_grass_plugins([str(grass), str(normal), str(npc)])
    assert dropped == [str(grass)]                  # its model is under grass\, not its name
    assert kept == [str(normal), str(npc)]
