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


def test_auto_merge_sees_a_filter_its_new_position_loses(tmp_path):
    """--auto-merge moves a plugin to the merge's place: a cell a plugin between them blanks is lost to it."""
    from mwdialog_cellorder import lost_cell_filter
    from mwdialog_redundant import plugin_profile
    plugins = order(tmp_path, ("Lamps.esp", [ext_cell("Fatleg's Camp")]),
                    ("Patch.esp", [info("Fatleg's Camp")]),
                    ("Alchemy.esp", [ext_cell("")]),
                    ("Last.esp", []))
    profs = [plugin_profile(p) for _n, p in plugins]
    assert profs[1]["filters"] == {"fatleg's camp"}
    hist = {}
    for i, pr in enumerate(profs):
        for k, nm in pr["cell_names"].items():
            hist.setdefault(k, []).append((i, nm))
    assert lost_cell_filter(profs[1]["filters"], hist, 3) == ("fatleg's camp", 2, "")
    assert lost_cell_filter(profs[1]["filters"], hist, 1) is None           # where it is now: fine
    assert lost_cell_filter(profs[1]["filters"], hist, 3, skip={2}) is None  # the blanker is merged too
    hist[("e", 5, 7)].append((3, "fatleg's camp"))                          # named again before the merge
    assert lost_cell_filter(profs[1]["filters"], hist, 3) is None


def test_report_names_the_merged_input_a_lost_filter_comes_from(tmp_path):
    import mwdialog_check as m
    plugins = order(tmp_path, ("Lamps.esp", [ext_cell("Fatleg's Camp")]),
                    ("Alchemy.esp", [ext_cell("Some Farm")]),
                    ("AutoMerge.esp", [info("Fatleg's Camp")]))
    src = tmp_path / "Julan Patch.esp"
    plugin(src, [], [info("Fatleg's Camp")])
    r = m.Report()
    w = m.World(r)
    w.merge_inputs = {"automerge.esp": [("Julan Patch.esp", str(src))]}
    for n, p in plugins:
        w.load_plugin(p, n)
    w._check_load_time_cells()
    msgs = [x for x in r.issues if "Fatleg" in str(x)]
    assert msgs and "it comes from Julan Patch.esp, merged into AutoMerge.esp" in str(msgs[0])


def test_fix_names_a_cell_a_later_esp_blanks_again(tmp_path):
    """Blanking a cell's name is a bug: the blanking .esp gets the name back (a master or an earlier blank don't)."""
    import mwdialog_check as m
    plugins = order(tmp_path, ("Base.esm", [ext_cell("")]),
                    ("Early.esp", [ext_cell("")]),
                    ("Lamps.esp", [ext_cell("Fatleg's Camp")]),
                    ("Patch.esp", [info("Fatleg's Camp")]),
                    ("Alchemy.esp", [ext_cell("  ")]),
                    ("Sounds.esp", [ext_cell("")]))
    r = m.Report()
    w = m.World(r)
    for n, p in plugins:
        w.load_plugin(p, n)
    w._check_load_time_cells()
    w._restore_blanked_cells()
    fixes = {fx["plugin"]: fx["set"] for fx in w.item_fixes if fx["tag"] == "CELL"}
    assert fixes == {"Alchemy.esp": {"NAME": "Fatleg's Camp"}, "Sounds.esp": {"NAME": "Fatleg's Camp"}}
    assert not [x for x in r.issues if "not found when this plugin loads" in x[4]]


def test_cell_conflicts_compare_exterior_names_but_not_blanks():
    """Two plugins naming a cell differently is a --cell-conflicts question (load order decides); a blank
    name is a bug --fix repairs, and an interior's name is its identity."""
    import mwdialog_check as m
    ext = lambda nm: [("NAME", z(nm)), ("DATA", struct.pack("<Iii", 0, 5, 7))]
    assert m._cell_settings(ext("Fatleg's Camp"))["NAME"] == "Fatleg's Camp"
    assert "NAME" not in m._cell_settings(ext("  "))
    assert "NAME" not in m._cell_settings([("NAME", z("Hall")), ("DATA", struct.pack("<Iii", 1, 0, 0))])
