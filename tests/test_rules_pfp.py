"""mwdialog_check.rules.txt places Patch for Purists right after Bloodmoon.esm (a rule in the rules text, not
in the code). Reads the rules file next to the scripts; builds a temporary game."""
import os

import pytest

from conftest import m, plugin, misc

RULES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), m.RULES_FILE)
PFP = "Patch for Purists.esm"
LAYOUT = [("Morrowind.esm", []), ("Tribunal.esm", ["Morrowind.esm"]), ("Bloodmoon.esm", ["Morrowind.esm"]),
          ("AATL_Data.esm", ["Morrowind.esm"]), ("Tamriel_Data.esm", ["Morrowind.esm"]),
          ("OAAB_Data.esm", ["Morrowind.esm"]), (PFP, ["Morrowind.esm", "Tribunal.esm", "Bloodmoon.esm"]),
          ("Some Mod.esp", ["Morrowind.esm"])]


def _plugins(tmp_path):
    df = tmp_path / "Morrowind" / "Data Files"
    df.mkdir(parents=True)
    out = []
    for name, masters in LAYOUT:
        plugin(df / name, [(x, 1) for x in masters], [misc(name.split(".")[0].lower()[:20] + "_x")])
        out.append((name, str(df / name)))
    return out


@pytest.mark.skipif(not os.path.exists(RULES), reason="no mwdialog_check.rules.txt next to the scripts")
def test_rules_file_puts_patch_for_purists_right_after_bloodmoon(tmp_path):
    plugins = _plugins(tmp_path)
    rules = m.parse_rules(RULES)[0]
    assert any(kind == "nearstart" and PFP in entries for kind, entries, _src in rules)
    order, _notes = m.compute_order(plugins, [rules], [n for n, _p in plugins])
    assert order[:4] == ["Morrowind.esm", "Tribunal.esm", "Bloodmoon.esm", PFP]
    assert order.index(PFP) < order.index("Tamriel_Data.esm") and order.index(PFP) < order.index("OAAB_Data.esm")


def test_without_the_rule_the_code_does_not_move_it(tmp_path):
    plugins = _plugins(tmp_path)
    order, _notes = m.compute_order(plugins, [[]], [n for n, _p in plugins])
    assert order.index(PFP) > order.index("Tamriel_Data.esm")             # nothing about it is built in
