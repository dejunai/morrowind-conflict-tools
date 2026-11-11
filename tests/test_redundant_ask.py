"""The redundant step asks whenever someone can answer: --yes doesn't answer it, every group is asked
(medium confidence and two versions too), the console is read even when stdin is redirected (Windows),
and when nobody can answer it says why and what it did."""
import builtins
import io
import sys

import pytest

from conftest import m, misc
from test_redundant import game, order, run, write, BASE, MW
from test_full_redundant import full_args, steps, SPEC, staged  # noqa: F401  (fixture)


def console(monkeypatch, answers):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    asked = []
    it = iter(answers)

    def fake(prompt=""):
        asked.append(prompt)
        return next(it)
    monkeypatch.setattr(builtins, "input", fake)
    return asked


def test_full_with_yes_still_asks_in_a_console(staged, tmp_path, monkeypatch):
    """The user's run: --add-all-esp --full --yes in PowerShell. --yes must not turn mods off unasked."""
    asked = console(monkeypatch, ["s"] * 10)
    m.run_full(full_args(tmp_path, yes=True))
    asked = [a for a in asked if "turn it off" in a]
    red = next(c[0] for c in staged if c[0][0] in ("--redundant", "--redundant-auto"))
    assert red[0] == "--redundant" and "--redundant-auto" not in red and "--no-interactive" not in red
    assert len(asked) == 1 and "Small.esp" in asked[0]
    assert "Small.esp" in order(tmp_path)                       # skipped, as answered


def test_full_redundant_auto_in_console_turns_off_sure_ones_and_asks_the_rest(staged, tmp_path, monkeypatch):
    recs = [misc(f"i{i}", 1) for i in range(8)]
    df = str(tmp_path / "Data Files")
    write(df, "Mod - A.esp", recs, MW, "adds things")
    write(df, "Mod - B.esp", recs[:7] + [misc("i7", 2)], MW, "adds things")
    m.write_load_order(str(tmp_path), order(tmp_path) + ["Mod - A.esp", "Mod - B.esp"])
    asked = console(monkeypatch, ["b"] + ["n"] * 5)              # "n" for --full's own questions at the end
    m.run_full(full_args(tmp_path, redundant_auto=True))
    red = [a for a in asked if "turn off" in a]
    assert len(red) == 1 and "keep Mod - A.esp" in red[0]       # only the two-versions pair is asked
    lo = order(tmp_path)
    assert "Small.esp" not in lo and "Mod - A.esp" not in lo and "Mod - B.esp" in lo


def test_nobody_to_ask_says_why_and_what_it_did(staged, tmp_path, capsys):
    m.run_full(full_args(tmp_path))                             # the fixture's stdin is not a console
    out = capsys.readouterr().out
    assert "Not asking: the output isn't on screen" in out or "Not asking: the input isn't a console" in out
    assert "Turning off the 1 high-confidence duplicate(s)" in out
    assert "Small.esp" not in order(tmp_path)


def test_no_interactive_says_so(tmp_path, capsys, monkeypatch):
    game(tmp_path, SPEC)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    run(tmp_path, "--redundant", "--no-interactive")
    assert "Not asking: --no-interactive was given. Reporting only" in capsys.readouterr().out


def test_medium_confidence_groups_are_asked_too(tmp_path, monkeypatch):
    """Spread.esp's records are copies spread over two plugins (medium): never auto, but asked."""
    game(tmp_path, [BASE, ("Spread.esp", [misc("a", 7), misc("b", 8)], MW, ""),
                    ("One.esp", [misc("a", 7), misc("x", 1)], MW, ""), ("Two.esp", [misc("b", 8), misc("y", 1)], MW, "")])
    asked = console(monkeypatch, ["o"])
    run(tmp_path, "--redundant-auto")
    assert len(asked) == 1 and "[medium] Spread.esp" in asked[0]
    assert "Spread.esp" not in order(tmp_path)


def test_answered_pairs_are_skipped_with_a_note(tmp_path, monkeypatch, capsys):
    game(tmp_path, SPEC)
    console(monkeypatch, ["k"])
    run(tmp_path, "--redundant")
    capsys.readouterr()
    asked = console(monkeypatch, [])
    run(tmp_path, "--redundant")
    out = capsys.readouterr().out
    assert asked == [] and "Already answered, not asked again (keep both" in out and "Big.esp + Small.esp" in out


def test_q_stops_asking(tmp_path, monkeypatch):
    game(tmp_path, [BASE, ("Itm1.esp", [misc("a", 1)], MW, ""), ("Itm2.esp", [misc("b", 1)], MW, "")])
    asked = console(monkeypatch, ["q"])
    run(tmp_path, "--redundant")
    assert len(asked) == 1 and order(tmp_path) == ["Morrowind.esm", "Itm1.esp", "Itm2.esp"]


def test_end_of_input_is_no_answer(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)

    def eof(_p=""):
        raise EOFError
    monkeypatch.setattr(builtins, "input", eof)
    assert m.ask("? ") is None


def test_prompt_is_flushed_first(monkeypatch):
    flushed = []

    class Out(io.StringIO):
        def flush(self):
            flushed.append(True)
    monkeypatch.setattr(sys, "stdout", Out())
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(builtins, "input", lambda p="": "o")
    assert m.ask("? ") == "o" and flushed


def test_windows_console_read_when_stdin_is_redirected(monkeypatch):
    """py.exe / a wrapper can hand Python a redirected stdin while the window is a console: CONIN$ answers."""
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)

    class Out(io.StringIO):
        def isatty(self):
            return True
    monkeypatch.setattr(sys, "stdout", Out())
    monkeypatch.setattr(m.os, "name", "nt")
    opened = []

    def fake_open(path, *a, **k):
        opened.append(path)
        assert path == "CONIN$"
        return io.StringIO("b\n")
    monkeypatch.setattr(m, "open", fake_open, raising=False)
    assert m.console_interactive() == (True, "")
    assert m.ask("? ") == "b" and opened == ["CONIN$", "CONIN$"]


def test_no_console_at_all(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    ok, why = m.console_interactive()
    assert not ok and "output isn't on screen" in why
