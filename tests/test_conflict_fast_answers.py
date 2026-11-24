"""--cell-conflicts at scale: a saved answer is replayed without planning both sides' turn-offs or showing the
detail; object use is read once per session; a plugin kept against an incompatible partner wins its other
incompatible pairs without being asked again."""
import builtins

from conftest import m
from test_conflict_confirm import _families

INCOMPATIBLE = {"place": [], "refs": [], "settings": [], "doubled": False,
                "incompatible": {"cells": {(1, 2)}, "evidence": {"terrain"}}}
MINOR = {"place": [], "refs": [(("i", "house"), 1, False)], "settings": [], "doubled": False}


def counting(monkeypatch):
    calls = {"plans": [], "reads": 0}
    real_plan, real_use = m.disable_dependents, m.object_use

    def plan(plugins, masters, roots, *a, **k):
        calls["plans"].append(roots[0])
        return real_plan(plugins, masters, roots, *a, **k)

    def use(*a, **k):
        calls["reads"] += 1
        return real_use(*a, **k)
    monkeypatch.setattr(m, "disable_dependents", plan)
    monkeypatch.setattr(m, "object_use", use)
    return calls


def test_saved_answers_replay_without_planning_or_detail(tmp_path, monkeypatch, capsys):
    args, plugins, masters = _families(tmp_path)
    args.only_new = True
    names = {n.lower(): n for n, _p in plugins}
    m.write_conflict_answers(str(tmp_path), {
        "a.esp|b.esp": {"do": "off", "plugin": "B.esp", "pair": ["A.esp", "B.esp"],
                        "affected": ["B.esp", "A B patch.esp"]},
        "object user.esp|unrelated.esp": {"do": "order", "plugin": "Object user.esp", "pair": ["Object user.esp", "Unrelated.esp"]}})
    calls = counting(monkeypatch)
    def no_pair_questions(prompt=""):
        assert "Run --sort" in prompt, "asked about a pair: " + prompt   # only the closing offer may be asked
        return "n"
    monkeypatch.setattr(builtins, "input", no_pair_questions)
    m._conflict_session(args, [(("a.esp", "b.esp"), INCOMPATIBLE), (("object user.esp", "unrelated.esp"), MINOR)],
                        names, masters, 1, plugins)
    out = capsys.readouterr().out
    assert calls["plans"] == ["B.esp"]                  # only the side the answer turns off, once
    assert calls["reads"] == 1
    assert "last time's answer: turn off B.esp" in out and "moved land leaves" not in out
    assert "B.esp" not in m.read_load_order(args)


def test_a_kept_incompatible_plugin_wins_its_other_pairs_without_asking(tmp_path, monkeypatch, capsys):
    args, plugins, masters = _families(tmp_path)
    names = {n.lower(): n for n, _p in plugins}
    asked = []

    def answer(prompt=""):
        if "Run --sort" in prompt:                      # the closing offer, not a pair
            return "n"
        asked.append(prompt)
        return "4"                                      # pair 1: turn off Object user.esp, A.esp stays
    monkeypatch.setattr(builtins, "input", answer)
    monkeypatch.setattr(m, "cell_conflicts_interactive", lambda a: True)
    pairs = [(("a.esp", "object user.esp"), INCOMPATIBLE), (("a.esp", "unrelated.esp"), INCOMPATIBLE)]
    m._conflict_session(args, pairs, names, masters, 1, plugins)
    out = capsys.readouterr().out
    assert len(asked) == 1, asked
    assert "A.esp was kept against another incompatible plugin: turn off Unrelated.esp" in out
    order = m.read_load_order(args)
    assert "Object user.esp" not in order and "Unrelated.esp" not in order and "A.esp" in order
    saved = m.read_conflict_answers(str(tmp_path))
    assert saved["a.esp|unrelated.esp"]["do"] == "off" and saved["a.esp|unrelated.esp"]["plugin"] == "Unrelated.esp"
