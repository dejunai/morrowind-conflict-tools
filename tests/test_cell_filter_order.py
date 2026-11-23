"""--sort: a plugin whose dialogue filters on a cell only another .esp names loads after it, and before a
plugin that then blanks the cell's name (the game: "Cell 'Fatleg's Camp' not found")."""
import struct

from conftest import plugin, rec, sub, z
from mwdialog_cellorder import cell_filter_rules


def ext_cell(name, x=5, y=7):
    return rec("CELL", sub("NAME", z(name)) + sub("DATA", struct.pack("<Iii", 0, x, y)))


def info(cell):
    return rec("DIAL", sub("NAME", z("Greeting 1")) + sub("DATA", b"\x01")) + \
        rec("INFO", sub("INAM", z("1")) + sub("PNAM", z("")) + sub("NNAM", z("")) + sub("ANAM", z(cell)))


def order(tmp_path, *specs):
    out = []
    for name, records in specs:
        plugin(tmp_path / name, [], records)
        out.append((name, str(tmp_path / name)))
    return out


def pairs(rules):
    return [tuple(r[1]) for r in rules]


def test_after_the_esp_naming_the_cell_and_before_one_blanking_it(tmp_path):
    plugins = order(tmp_path, ("Patch.esp", [info("Fatleg's Camp")]),
                    ("Lamps.esp", [ext_cell("Fatleg's Camp")]),
                    ("Sounds.esp", [ext_cell("")]))
    assert pairs(cell_filter_rules(plugins)) == [("Lamps.esp", "Patch.esp"), ("Patch.esp", "Sounds.esp")]


def test_no_rule_for_a_cell_a_master_names_or_a_region(tmp_path):
    plugins = order(tmp_path, ("Base.esm", [ext_cell("Fatleg's Camp"), rec("REGN", sub("NAME", z("r"))
                                                                            + sub("FNAM", z("Ascadian Isles")))]),
                    ("Patch.esp", [info("Fatleg's Camp"), info("Ascadian Isles")]),
                    ("Lamps.esp", [ext_cell("Fatleg's Camp")]))
    assert cell_filter_rules(plugins) == []


def test_named_again_later_keeps_the_blanker_before_it(tmp_path):
    plugins = order(tmp_path, ("Lamps.esp", [ext_cell("Camp")]), ("Sounds.esp", [ext_cell("")]),
                    ("Again.esp", [ext_cell("Camp")]), ("Patch.esp", [info("Camp")]))
    assert pairs(cell_filter_rules(plugins)) == [("Again.esp", "Patch.esp"), ("Sounds.esp", "Again.esp")]


def test_before_every_later_blanker_not_only_the_first(tmp_path):
    plugins = order(tmp_path, ("Patch.esp", [info("Camp")]), ("Lamps.esp", [ext_cell("Camp")]),
                    ("Critters.esp", [ext_cell("")]), ("Alchemy.esp", [ext_cell("")]))
    assert pairs(cell_filter_rules(plugins)) == [("Lamps.esp", "Patch.esp"), ("Patch.esp", "Critters.esp"),
                                                 ("Patch.esp", "Alchemy.esp")]
