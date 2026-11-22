"""--full asks about the conflicts that have no answer yet, before the patches are built."""
import builtins
import types

import pytest

from conftest import m
from test_full_redundant import full_args

KEEP = {"do": "order", "plugin": "A.esp", "pair": ["A.esp", "B.esp"], "when": "earlier"}


def session(tmp_path, monkeypatch, replies, console=True, **flags):
    data = tmp_path / "Data Files"
    data.mkdir()
    m.write_conflict_answers(str(tmp_path), {"a.esp|b.esp": KEEP})
    monkeypatch.setattr(m, "cell_conflicts_interactive", lambda args: console and not args.no_interactive)
    monkeypatch.setattr(m, "IN_FULL", True)
    asked, left = [], iter(replies)

    def answer(prompt=""):
        asked.append(prompt)
        got = next(left)
        if got is EOFError:
            raise EOFError
        return got
    monkeypatch.setattr(builtins, "input", answer)
    a = dict(data_dir=str(data), dry_run=False, use_answers=True, only_new=False, no_interactive=False)
    a.update(flags)
    c = {"place": [], "refs": [(("i", "hall"), 1, False)], "settings": [], "doubled": False}
    names = {f"{x}.esp": f"{x.upper()}.esp" for x in "abcdef"}
    pairs = [("c.esp", "d.esp"), ("e.esp", "f.esp"), ("a.esp", "b.esp")]        # remembered one last
    m._conflict_session(types.SimpleNamespace(**a), [(p, c) for p in pairs], names, {}, 1)
    rules = (tmp_path / m.RULES_FILE).read_text(encoding="cp1252")
    new = (tmp_path / m.NEW_CONFLICTS_FILE).read_text(encoding="utf-8").split()
    return asked, rules, new


def test_only_the_new_pairs_are_asked_and_their_answers_apply_in_this_run(tmp_path, monkeypatch):
    asked, rules, new = session(tmp_path, monkeypatch, ["2", "s"])
    assert len(asked) == 2
    assert "D.esp\nC.esp" in rules and "A.esp\nB.esp" in rules
    assert new == ["e.esp|f.esp"]
    assert set(m.read_conflict_answers(str(tmp_path))) == {"a.esp|b.esp", "c.esp|d.esp"}


@pytest.mark.parametrize("replies", [["q"], ["a", "q"], [EOFError]])
@pytest.mark.parametrize("flags", [{}, {"use_answers": False, "only_new": True}])
def test_stopping_still_replays_the_remembered_answers(tmp_path, monkeypatch, replies, flags):
    asked, rules, new = session(tmp_path, monkeypatch, replies, **flags)
    assert len(asked) == len(replies)
    assert "A.esp\nB.esp" in rules
    assert new == ["c.esp|d.esp", "e.esp|f.esp"]


@pytest.mark.parametrize("console,no_interactive", [(False, False), (True, True)])
def test_unattended_asks_nothing(tmp_path, monkeypatch, console, no_interactive):
    asked, rules, new = session(tmp_path, monkeypatch, [], console, no_interactive=no_interactive)
    assert not asked and "A.esp\nB.esp" in rules
    assert new == ["c.esp|d.esp", "e.esp|f.esp"]


@pytest.mark.parametrize("console,yes,no_interactive,answers,asks", [
    (True, False, False, True, True),
    (True, True, False, True, True),        # --yes doesn't answer these, as with the redundant plugins
    (True, False, True, True, False),
    (False, False, False, True, False),
    (True, False, False, False, False),     # no answers yet: a report, and the question at the end
])
def test_full_conflict_step(tmp_path, monkeypatch, console, yes, no_interactive, answers, asks):
    (tmp_path / "Data Files").mkdir()
    if answers:
        m.write_conflict_answers(str(tmp_path), {"a.esp|b.esp": KEEP})
    (tmp_path / m.NEW_CONFLICTS_FILE).write_text("c.esp|d.esp", encoding="utf-8")         # left for later
    calls, prompts = [], []
    monkeypatch.setattr(m, "main", lambda argv: calls.append(argv[1:]) or 0)
    for name in ("full_check", "full_reset", "multipatch_aside"):
        monkeypatch.setattr(m, name, lambda *a, **k: 0)
    monkeypatch.setattr(m, "full_missing_masters", lambda *a, **k: [])
    monkeypatch.setattr(m, "read_load_order", lambda a: [])
    monkeypatch.setattr(m, "cell_conflicts_interactive", lambda a: console and not a.no_interactive)
    monkeypatch.setattr(m.sys.stdin, "isatty", lambda: console, raising=False)
    monkeypatch.setattr(builtins, "input", lambda p="": prompts.append(p) or "n")
    m.run_full(full_args(tmp_path, fresh_answers=False, no_redundant=True, yes=yes, no_interactive=no_interactive))
    first = [c[0] for c in calls]
    step = calls[first.index("--cell-conflicts")]
    assert ("--no-interactive" not in step) == asks
    assert first.index("--cell-conflicts") < first.index("--clean")
    assert all("--no-interactive" in c for c in calls if c is not step)
    if asks:
        assert not any("Answer them now" in p for p in prompts)     # put off: not asked twice in one run
