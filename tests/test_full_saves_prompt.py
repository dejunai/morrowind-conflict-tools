"""Bare --full asks before rewriting when .ess saves are present; --yes skips; no TTY refuses."""
import os
import types

import mwdialog_check as m


def _args(dry_run=False, yes=False):
    return types.SimpleNamespace(dry_run=dry_run, yes=yes)


def test_ess_saves_finds_ess_only_in_saves(tmp_path):
    folder = tmp_path / "Saves"
    folder.mkdir()
    (folder / "quicksave.ess").write_bytes(b"ESS")
    (folder / "note.txt").write_text("x")
    (folder / "nested").mkdir()
    (folder / "nested" / "other.ess").write_bytes(b"ESS")
    found = {os.path.basename(p) for p in m.ess_saves(str(tmp_path))}
    assert found == {"quicksave.ess"}
    assert m.ess_saves(str(tmp_path / "nope")) == []


def test_no_saves_does_not_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "preserve_saves", lambda a=None: "")
    assert m.confirm_full_if_saves(_args(), str(tmp_path)) == 0


def test_dry_run_skips_prompt(tmp_path, monkeypatch):
    (tmp_path / "Saves").mkdir()
    (tmp_path / "Saves" / "quicksave.ess").write_bytes(b"ESS")
    monkeypatch.setattr(m, "preserve_saves", lambda a=None: "")
    called = []
    monkeypatch.setattr("builtins.input", lambda prompt="": called.append(prompt) or "n")
    assert m.confirm_full_if_saves(_args(dry_run=True), str(tmp_path)) == 0
    assert called == []


def test_preserve_saves_skips_prompt(tmp_path, monkeypatch):
    (tmp_path / "Saves").mkdir()
    (tmp_path / "Saves" / "quicksave.ess").write_bytes(b"ESS")
    monkeypatch.setattr(m, "preserve_saves", lambda a=None: "strict")
    called = []
    monkeypatch.setattr("builtins.input", lambda prompt="": called.append(prompt) or "n")
    assert m.confirm_full_if_saves(_args(), str(tmp_path)) == 0
    assert called == []


def test_yes_skips_prompt(tmp_path, monkeypatch):
    (tmp_path / "Saves").mkdir()
    (tmp_path / "Saves" / "quicksave.ess").write_bytes(b"ESS")
    monkeypatch.setattr(m, "preserve_saves", lambda a=None: "")
    called = []
    monkeypatch.setattr("builtins.input", lambda prompt="": called.append(prompt) or "n")
    assert m.confirm_full_if_saves(_args(yes=True), str(tmp_path)) == 0
    assert called == []


def test_no_tty_refuses_without_yes(tmp_path, monkeypatch, capsys):
    (tmp_path / "Saves").mkdir()
    (tmp_path / "Saves" / "quicksave.ess").write_bytes(b"ESS")
    monkeypatch.setattr(m, "preserve_saves", lambda a=None: "")
    class _Stdin:
        def isatty(self):
            return False
    monkeypatch.setattr(m.sys, "stdin", _Stdin())
    assert m.confirm_full_if_saves(_args(), str(tmp_path)) == 2
    err = capsys.readouterr().err
    assert "Nothing was changed" in err
    assert "--preserve-saves=strict" in err
    assert "--yes" in err


def test_interactive_yes_continues(tmp_path, monkeypatch):
    (tmp_path / "Saves").mkdir()
    (tmp_path / "Saves" / "quicksave.ess").write_bytes(b"ESS")
    monkeypatch.setattr(m, "preserve_saves", lambda a=None: "")
    class _Stdin:
        def isatty(self):
            return True
    monkeypatch.setattr(m.sys, "stdin", _Stdin())
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    assert m.confirm_full_if_saves(_args(), str(tmp_path)) == 0


def test_interactive_no_cancels(tmp_path, monkeypatch, capsys):
    (tmp_path / "Saves").mkdir()
    (tmp_path / "Saves" / "quicksave.ess").write_bytes(b"ESS")
    monkeypatch.setattr(m, "preserve_saves", lambda a=None: "")
    class _Stdin:
        def isatty(self):
            return True
    monkeypatch.setattr(m.sys, "stdin", _Stdin())
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert m.confirm_full_if_saves(_args(), str(tmp_path)) == 2
    assert "cancelled" in capsys.readouterr().out
