"""--preserve-saves: generated patches never bring back an object a game in progress may have dealt with (while
the plugins they were built on are all still active); =strict also keeps the active plugins, the auto-merge and
the reference clean-ups as they are, and --full skips its reset."""
import types

from conftest import m, plugin
from test_doubled_deleted import _cell, _deleted, _order, _ref, _setup
from test_full_redundant import full_args, staged  # noqa: F401  (the fixture)


def build(args, data, order):
    m.fix_cell_winners(args, [(n, str(data / n)) for n in order])


def move_b_away(data):
    """B.esp now puts its bottle far from A's: nothing is doubled any more."""
    size = (data / "Master.esm").stat().st_size
    plugin(data / "B.esp", [("Master.esm", size)], [_cell(_ref(1, "misc_bottle", x=5000.0))])


def test_a_rebuild_never_brings_an_object_back_while_its_plugins_stay(tmp_path):
    data, args, order = _setup(tmp_path)
    args.preserve_saves = "basic"
    build(args, data, order)
    assert _deleted(data) == [("A.esp", 1)]
    move_b_away(data)
    build(args, data, order)
    assert _deleted(data) == [("A.esp", 1)]               # kept: A's bottle doesn't come back


def test_without_the_switch_it_comes_back(tmp_path):
    data, args, order = _setup(tmp_path)
    build(args, data, order)
    move_b_away(data)
    build(args, data, order)
    assert _deleted(data) == []


def test_with_a_plugin_gone_the_rebuild_goes_ahead(tmp_path):
    data, args, order = _setup(tmp_path)
    args.preserve_saves = "basic"
    build(args, data, order)
    _order(tmp_path, ["Master.esm", "A.esp"])
    build(args, data, ["Master.esm", "A.esp"])            # B.esp left: no missing master is kept around
    assert _deleted(data) == []


def test_strict_keeps_the_active_plugins_and_the_merge(tmp_path, monkeypatch, capsys):
    data, args, order = _setup(tmp_path)
    args.preserve_saves = "strict"
    args.dry_run = False
    assert m.fix_doubled(types.SimpleNamespace(**vars(args)), [(n, str(data / n)) for n in order]) == []
    assert m.read_load_order(args) == order
    assert m.run_reenable(types.SimpleNamespace(**vars(args), reenable=[])) == 2
    assert m.run_auto_merge(args, [], [], []) == 0
    assert m.fix_ref_groups(args, []) is None
    out = capsys.readouterr().out
    assert "reported only" in out and "refused" in out and "kept as it is" in out


def test_full_strict_has_no_reset_unmerge_or_redundant_step(staged, tmp_path):  # noqa: F811
    (tmp_path / m.MERGE_RECORD).write_text("[mwdialog_check AutoMerge.esp]\nX.esp\n", encoding="utf-8")
    m.run_full(full_args(tmp_path, preserve_saves="strict"))
    steps = [c[0] for c in staged]
    assert "--unmerge" not in [s[0] for s in steps]
    assert not any(s[0] in ("--redundant", "--redundant-auto") for s in steps)
    assert all("--preserve-saves" in s and s[s.index("--preserve-saves") + 1] == "strict"
               for s in steps if s[0] not in ("--redundant", "--redundant-auto"))
