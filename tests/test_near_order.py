"""[NearStart] and [NearEnd] blocks are [Order] rules too, in the order they place their plugins: [NearStart]
as listed, [NearEnd] reversed (its first plugin loads last). Builds a temporary game."""
from conftest import m, plugin, misc


def _game(tmp_path, layout):
    df = tmp_path / "Morrowind" / "Data Files"
    df.mkdir(parents=True)
    out = []
    for name, masters in layout:
        plugin(df / name, [(x, 1) for x in masters], [misc(name.split(".")[0].lower()[:20] + "_x")])
        out.append((name, str(df / name)))
    return out


def _sort(plugins, *rule_sets):
    return m.compute_order(plugins, list(rule_sets), [n for n, _p in plugins])


BASE = [("Morrowind.esm", [])]


def test_near_start_block_orders_its_plugins(tmp_path):
    # A needs Late.esp, so without an order rule B (ranked after A) would load before A
    plugins = _game(tmp_path, BASE + [("Late.esp", ["Morrowind.esm"]), ("A.esp", ["Morrowind.esm", "Late.esp"]),
                                      ("B.esp", ["Morrowind.esm"]), ("C.esp", ["Morrowind.esm"])])
    order, notes = _sort(plugins, [("nearstart", ["A.esp", "B.esp"], "mine.txt:1")])
    assert order.index("Late.esp") < order.index("A.esp") < order.index("B.esp")
    assert order.index("B.esp") < order.index("C.esp")                  # still in the start band
    assert notes["applied"] == 1 and not notes["cycles"]


def test_near_end_block_orders_its_plugins_reversed(tmp_path):
    # Y needs Late.esp, which is ranked last, so by rank alone X would load before Y
    plugins = _game(tmp_path, BASE + [("Late.esp", ["Morrowind.esm"]), ("X.esp", ["Morrowind.esm"]),
                                      ("Y.esp", ["Morrowind.esm", "Late.esp"]), ("Z.esp", ["Morrowind.esm"])])
    rules = [("nearend", ["Late.esp"], "mine.txt:1"), ("nearend", ["X.esp", "Y.esp"], "mine.txt:4")]
    order, notes = _sort(plugins, rules)
    assert order == ["Morrowind.esm", "Z.esp", "Late.esp", "Y.esp", "X.esp"]   # "X, Y": Y before X
    assert notes["applied"] == 1


def test_mlox_near_blocks_keep_mlox_meaning(tmp_path):
    # mlox lists [NearEnd] plugins by priority, not as an order: only your rules file's blocks order
    plugins = _game(tmp_path, BASE + [("Late.esp", ["Morrowind.esm"]), ("X.esp", ["Morrowind.esm"]),
                                      ("Y.esp", ["Morrowind.esm", "Late.esp"])])
    mine = [("nearend", ["Late.esp"], "mine.txt:1")]
    mlox = [("nearend", ["X.esp", "Y.esp"], "mlox_base.txt:1")]
    order, notes = _sort(plugins, mine, [], mlox)
    assert order.index("X.esp") < order.index("Y.esp") and notes["applied"] == 0
    order, notes = _sort(plugins, mine + [("nearend", ["X.esp", "Y.esp"], "mine.txt:4")])
    assert order.index("Y.esp") < order.index("X.esp") and notes["applied"] == 1


def test_one_plugin_blocks_order_nothing(tmp_path):
    plugins = _game(tmp_path, BASE + [("X.esp", ["Morrowind.esm"]), ("Y.esp", ["Morrowind.esm"])])
    _order, notes = _sort(plugins, [("nearend", ["X.esp"], "f:1"), ("nearend", ["Y.esp"], "f:4")])
    assert notes["applied"] == 0


def test_no_duplicate_edge_when_order_says_the_same(tmp_path):
    plugins = _game(tmp_path, BASE + [("X.esp", ["Morrowind.esm"]), ("Y.esp", ["Morrowind.esm"])])
    near_only, n1 = _sort(plugins, [("nearend", ["X.esp", "Y.esp"], "f:1")])
    both, n2 = _sort(plugins, [("nearend", ["X.esp", "Y.esp"], "f:1"), ("order", ["Y.esp", "X.esp"], "f:5")])
    assert near_only == both and n1["applied"] == n2["applied"] == 1
    assert not n2["cycles"]                                              # "already so": not a contradiction


def test_later_order_rule_contradicting_a_near_block_is_skipped_and_reported(tmp_path):
    plugins = _game(tmp_path, BASE + [("A.esp", ["Morrowind.esm"]), ("B.esp", ["Morrowind.esm"])])
    order, notes = _sort(plugins, [("nearstart", ["A.esp", "B.esp"], "mine.txt:1")],
                         [("order", ["B.esp", "A.esp"], "mlox_base.txt:9")])
    assert order.index("A.esp") < order.index("B.esp")
    assert notes["cycles"] == [("B.esp", "A.esp", "mlox_base.txt:9")]


def test_near_block_contradicting_an_earlier_rule_or_master_is_skipped(tmp_path):
    plugins = _game(tmp_path, BASE + [("A.esp", ["Morrowind.esm"]), ("B.esp", ["Morrowind.esm", "A.esp"])])
    # B has A as a master: "[NearStart] B, A" can't put B first; the step is reported, the order stays valid
    order, notes = _sort(plugins, [("nearstart", ["B.esp", "A.esp"], "mine.txt:1")])
    assert order.index("A.esp") < order.index("B.esp")
    assert notes["cycles"] == [("B.esp", "A.esp", "mine.txt:1")]
    steps = [st for (src, _eb), st in notes["steps"].items() if src == "mine.txt:1"]
    assert steps and steps[0]["kind"] == "nearstart" and steps[0]["skipped"]


def test_esm_still_loads_before_esp(tmp_path):
    plugins = _game(tmp_path, BASE + [("A.esp", ["Morrowind.esm"]), ("B.esm", ["Morrowind.esm"])])
    order, notes = _sort(plugins, [("nearstart", ["A.esp", "B.esm"], "f:1")])
    assert order.index("B.esm") < order.index("A.esp")
    assert notes["esm_after_esp"] == 1


def test_wildcards_in_near_blocks(tmp_path):
    plugins = _game(tmp_path, BASE + [("Late.esp", ["Morrowind.esm"]),
                                      ("P1 Script Fix.esp", ["Morrowind.esm", "Late.esp"]),
                                      ("Q.esp", ["Morrowind.esm"])])
    order, _ = _sort(plugins, [("nearstart", ["*Script Fix.esp", "Q.esp"], "f:1")])
    assert order.index("P1 Script Fix.esp") < order.index("Q.esp")


def test_rule_helpers_read_near_blocks():
    rules = [("nearstart", ["A.esp", "B.esp"], "f:1"), ("nearend", ["X.esp", "Y.esp"], "f:4"),
             ("order", ["C.esp", "D.esp"], "f:7")]
    assert m.rule_puts_before(rules, "A.esp", "B.esp") and not m.rule_puts_before(rules, "B.esp", "A.esp")
    assert m.rule_puts_before(rules, "Y.esp", "X.esp") and not m.rule_puts_before(rules, "X.esp", "Y.esp")
    assert m.ordering_rules(rules) == [["a.esp", "b.esp"], ["y.esp", "x.esp"], ["c.esp", "d.esp"]]


def test_parsed_rules_file(tmp_path):
    p = tmp_path / "r.txt"
    p.write_text("[NearEnd]\nX.esp\nY.esp\n\n[NearStart]\nA.esp\nB.esp\n")
    rules = m.parse_rules(str(p))[0]
    assert [k for k, _e, _s in rules] == ["nearend", "nearstart"]
    assert m.rule_puts_before(rules, "Y.esp", "X.esp") and m.rule_puts_before(rules, "A.esp", "B.esp")
