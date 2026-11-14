"""Major masters with a documented place in the load order (built-in --sort rules)."""
import argparse
import os

from conftest import m, plugin, misc


def _game(tmp_path, names_masters):
    df = tmp_path / "Morrowind" / "Data Files"
    df.mkdir(parents=True)
    out = []
    for name, masters in names_masters:
        plugin(df / name, [(x, 1) for x in masters], [misc(name.split(".")[0].lower()[:20] + "_x")])
        out.append((name, str(df / name)))
    return df, out


LAYOUT = [("Morrowind.esm", []), ("Tribunal.esm", ["Morrowind.esm"]), ("Bloodmoon.esm", ["Morrowind.esm"]),
          ("AATL_Data.esm", ["Morrowind.esm"]), ("Tamriel_Data.esm", ["Morrowind.esm"]),
          ("OAAB_Data.esm", ["Morrowind.esm"]),
          ("Patch for Purists.esm", ["Morrowind.esm", "Tribunal.esm", "Bloodmoon.esm"]),
          ("Some Mod.esp", ["Morrowind.esm"])]


def test_patch_for_purists_loads_right_after_bloodmoon(tmp_path):
    _df, plugins = _game(tmp_path, LAYOUT)
    order, _notes = m.compute_order(plugins, [[], m.builtin_rules()], [n for n, _p in plugins])
    assert order[:4] == ["Morrowind.esm", "Tribunal.esm", "Bloodmoon.esm", "Patch for Purists.esm"]
    assert order.index("Patch for Purists.esm") < order.index("Tamriel_Data.esm") < order.index("OAAB_Data.esm")
    assert order[-1] == "Some Mod.esp"


def test_your_rules_file_still_wins_over_the_built_in_rule(tmp_path):
    _df, plugins = _game(tmp_path, LAYOUT)
    mine = m.parse_rules("mwdialog_check.rules.txt", "[Order]\nAATL_Data.esm\nPatch for Purists.esm\n")[0]
    order, _notes = m.compute_order(plugins, [mine, m.builtin_rules()], [n for n, _p in plugins])
    assert order.index("AATL_Data.esm") < order.index("Patch for Purists.esm") < order.index("Tamriel_Data.esm")


def test_sort_uses_the_built_in_rules(tmp_path):
    df, plugins = _game(tmp_path, LAYOUT)
    args = argparse.Namespace(data_dir=str(df), no_mlox_rules=True, no_content_order=True)
    rule_sets, _files = m.sort_rule_sources(args, plugins, quiet=True)
    assert any(kind == "nearstart" and "Patch for Purists.esm" in entries
               for rules in rule_sets for kind, entries, _src in rules)
    assert not os.path.exists(df.parent / m.RULES_FILE)          # reading the rules writes nothing
