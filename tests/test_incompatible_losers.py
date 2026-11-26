"""--cell-conflicts: a plugin that lost an INCOMPATIBLE choice stays resolved (it loses again, without a question,
against any other plugin) while the plugin it lost to is still active; when that one is gone the record lapses
and the loser is looked at afresh (the existing re-enable of plugins whose winner is gone is untouched)."""
import builtins
import types

import pytest

from conftest import m, plugin
from test_conflict_always_loses import INCOMPATIBLE

HIMM = "himmelryn.ESP"          # the case is the file's own; every comparison ignores it
ORDER = ["Snow.esp", "Anthology.esp", HIMM, "Other.esp"]


def world(tmp_path, order=None):
    data = tmp_path / "Data Files"
    data.mkdir()
    for n in ORDER:
        plugin(data / n, [], [])
    m.write_load_order(str(tmp_path), order or ORDER, "test")
    (tmp_path / "Morrowind.ini").write_text("[Game Files]\n", encoding="cp1252")
    args = types.SimpleNamespace(data_dir=str(data), ini=str(tmp_path / "Morrowind.ini"), dry_run=False,
                                 use_answers=False, only_new=False, plugins=None, openmw_cfg=None)
    return args


def session(args, tmp_path, pairs, replies):
    """Run --cell-conflicts over `pairs` (lowercase keys); returns (questions asked, output order)."""
    order = m.read_load_order(args)
    plugins = [(n, str(tmp_path / "Data Files" / n)) for n in order]
    names = {n.lower(): n for n in ORDER}
    masters = {n.lower(): [] for n in ORDER}
    asked, left = [], iter(replies)

    def answer(prompt=""):
        if "Run --sort" in prompt:
            return "n"
        asked.append(prompt)
        return next(left)
    old = builtins.input
    builtins.input = answer
    try:
        m._conflict_session(args, [(p, INCOMPATIBLE) for p in pairs], names, masters, 1, plugins)
    finally:
        builtins.input = old
    return asked, m.read_load_order(args)


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(m, "IN_FULL", True)
    monkeypatch.setattr(m, "cell_conflicts_interactive", lambda a: True)
    monkeypatch.setattr(m, "main", lambda argv: 0)


def lose_to_snow(args, tmp_path):
    asked, order = session(args, tmp_path, [("himmelryn.esp", "snow.esp")], ["3"])      # Snow wins: Himmelryn off
    assert len(asked) == 1 and HIMM not in order
    return order


def test_the_loser_of_an_incompatible_choice_is_recorded_with_its_winner(tmp_path):
    args = world(tmp_path)
    lose_to_snow(args, tmp_path)
    assert m.read_incompatible_losers(str(tmp_path)) == [("himmelryn.esp", "snow.esp")]
    text = (tmp_path / m.INCOMPATIBLE_LOSERS_FILE).read_text(encoding="utf-8")
    assert "himmelryn.ESP\tSnow.esp\t" in text and text.startswith("; mwdialog_incompatible_losers.txt")


@pytest.mark.parametrize("pair", [("anthology.esp", "himmelryn.esp"), ("himmelryn.esp", "anthology.esp")])
def test_a_recorded_loser_is_not_asked_again_against_another_plugin(tmp_path, capsys, pair):
    args = world(tmp_path)
    lose_to_snow(args, tmp_path)
    m.write_load_order(str(tmp_path), ORDER, "Dej's re-enable put it back")       # back on, as --full does
    capsys.readouterr()
    asked, order = session(args, tmp_path, [pair], [])
    assert asked == []
    assert HIMM not in order and "Anthology.esp" in order and "Snow.esp" in order
    out = capsys.readouterr().out
    assert "himmelryn.ESP already lost an incompatibility to Snow.esp" in out
    assert m.read_incompatible_losers(str(tmp_path)) == [("himmelryn.esp", "snow.esp")]


def test_a_saved_answer_that_picks_the_other_side_does_not_override_a_recorded_loss(tmp_path):
    args = world(tmp_path)
    lose_to_snow(args, tmp_path)
    m.write_load_order(str(tmp_path), ORDER, "back on")
    m.write_conflict_answers(str(tmp_path), {"anthology.esp|himmelryn.esp": {
        "do": "off", "plugin": "Anthology.esp", "pair": ["Anthology.esp", HIMM], "when": "earlier"}})
    args.use_answers = True
    asked, order = session(args, tmp_path, [("anthology.esp", "himmelryn.esp")], [])
    assert asked == [] and HIMM not in order and "Anthology.esp" in order


def test_the_record_lapses_when_its_winner_is_gone(tmp_path, capsys):
    args = world(tmp_path)
    lose_to_snow(args, tmp_path)
    # Snow.esp is no longer active, and Himmelryn is back (the existing re-enable of a loser whose winner is gone)
    m.write_load_order(str(tmp_path), ["Anthology.esp", HIMM, "Other.esp"], "winner removed")
    asked, order = session(args, tmp_path, [("anthology.esp", "himmelryn.esp")], ["4"])
    assert len(asked) == 1                              # asked as a fresh incompatibility
    assert "already lost" not in capsys.readouterr().out
    assert HIMM not in order and "Anthology.esp" in order
    assert ("himmelryn.esp", "snow.esp") in m.read_incompatible_losers(str(tmp_path))   # the line stays, inactive


def test_the_existing_reenable_still_fires_only_when_the_winner_is_gone(tmp_path):
    args = world(tmp_path)
    lose_to_snow(args, tmp_path)
    assert m.release_lost_winners(args) == 0            # Snow.esp is still there: Himmelryn stays off
    assert HIMM not in m.read_load_order(args)
    m.write_load_order(str(tmp_path), ["Anthology.esp", "Other.esp"], "winner removed")
    assert m.release_lost_winners(args) == 1
    assert HIMM in m.read_load_order(args)
    asked, order = session(args, tmp_path, [("anthology.esp", "himmelryn.esp")], ["s"])
    assert len(asked) == 1 and HIMM in order            # re-evaluated normally


def test_two_resolved_sides_that_did_not_lose_to_each_other_are_asked(tmp_path):
    args = world(tmp_path)
    m.add_incompatible_loser(str(tmp_path), HIMM, "Snow.esp")
    m.add_incompatible_loser(str(tmp_path), "Anthology.esp", "Other.esp")
    asked, order = session(args, tmp_path, [("anthology.esp", "himmelryn.esp")], ["s"])
    assert len(asked) == 1 and set(order) == set(ORDER)


def test_a_loss_between_the_pair_itself_decides_it(tmp_path):
    args = world(tmp_path)
    m.add_incompatible_loser(str(tmp_path), HIMM, "Anthology.esp")
    m.add_incompatible_loser(str(tmp_path), "Anthology.esp", "Other.esp")
    asked, order = session(args, tmp_path, [("anthology.esp", "himmelryn.esp")], [])
    assert asked == [] and HIMM not in order and "Anthology.esp" in order


def test_a_dry_run_records_nothing(tmp_path):
    args = world(tmp_path)
    args.dry_run = True
    session(args, tmp_path, [("himmelryn.esp", "snow.esp")], ["3"])
    assert not (tmp_path / m.INCOMPATIBLE_LOSERS_FILE).exists()


def test_adding_is_idempotent_and_ignores_case(tmp_path):
    assert m.add_incompatible_loser(str(tmp_path), HIMM, "Snow.esp") is True
    assert m.add_incompatible_loser(str(tmp_path), "HIMMELRYN.esp", "snow.ESP") is False
    assert m.add_incompatible_loser(str(tmp_path), HIMM, "Other.esp") is True
    assert m.read_incompatible_losers(str(tmp_path)) == [("himmelryn.esp", "snow.esp"), ("himmelryn.esp", "other.esp")]
