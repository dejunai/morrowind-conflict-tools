"""--full's redundant-plugins step: early (before cleaning, fixing, merging, asset checks), auto in batch runs,
asking in a console, report only with --dry-run, skipped with --no-redundant; AutoMerge inputs."""
import sys

import pytest

from conftest import m, misc
from test_redundant import game, order, run, BASE, MW

SPEC = [BASE, ("Small.esp", [misc("a", 7)], MW, ""), ("Big.esp", [misc("a", 7), misc("b", 9)], MW, "")]


def full_args(tmp_path, **kw):
    a = dict(data_dir=str(tmp_path / "Data Files"), dry_run=False, fix_log=str(tmp_path / "mwdialog_fixes.log"),
             encoding="cp1252", yes=False, ini=None, vortex_dir=None, add_all_esp=False,
             collide_radius=m.COLLIDE_ANY_RADIUS, fresh_answers=True, use_answers=False, no_redundant=False,
             no_interactive=False, redundant_auto=False, no_vortex=True, play=False)
    a.update(kw)
    return m.argparse.Namespace(**a)


@pytest.fixture
def staged(monkeypatch, tmp_path):
    """run_full with every step but the redundant one faked: each records the load order it would read."""
    game(tmp_path, SPEC)
    calls = []
    real = m.main

    def fake(argv):
        if argv[1] in ("--redundant", "--redundant-auto"):
            calls.append((argv[1:], None))
            return real(argv + ["--no-vortex"])
        calls.append((argv[1:], [n for n in order(tmp_path)]))
        return 0
    monkeypatch.setattr(m, "main", fake)
    monkeypatch.setattr(m, "full_check", lambda *a, **k: 0)
    monkeypatch.setattr(m, "full_missing_masters", lambda *a, **k: [])
    monkeypatch.setattr(m, "full_reset", lambda *a, **k: 0)
    monkeypatch.setattr(m, "multipatch_aside", lambda *a, **k: 0)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    return calls


def steps(calls):
    return [c[0][0] for c in calls]


def test_stage_order_redundant_runs_before_everything_that_reads_plugins(staged, tmp_path):
    (tmp_path / m.MERGE_RECORD).write_text("[mwdialog_check AutoMerge.esp]\nX.esp\n", encoding="utf-8")
    m.run_full(full_args(tmp_path))
    s = steps(staged)
    assert s.index("--unmerge") < s.index("--redundant-auto")
    for later in ("--cell-conflicts", "--sort", "--clean", "--auto-merge", "--all"):
        assert s.index("--redundant-auto") < s.index(later), later
    assert s.count("--redundant") + s.count("--redundant-auto") == 1


def test_later_stages_see_the_plugin_turned_off(staged, tmp_path):
    m.run_full(full_args(tmp_path))
    after = [lo for args_, lo in staged if lo is not None]
    assert after and all("Small.esp" not in lo for lo in after)
    clean = next(lo for args_, lo in staged if args_[0] == "--clean")
    assert clean == ["Morrowind.esm", "Big.esp"]
    assert "--redundant: turned off Small.esp" in open(tmp_path / "mwdialog_fixes.log", encoding="utf-8").read()
    assert list(m.read_redundant(str(tmp_path))[0]) == ["Small.esp"]


def test_full_dry_run_changes_nothing(staged, tmp_path):
    m.run_full(full_args(tmp_path, dry_run=True))
    assert "--dry-run" in staged[[c[0][0] for c in staged].index("--redundant-auto")][0]
    assert order(tmp_path) == ["Morrowind.esm", "Small.esp", "Big.esp"]
    assert not (tmp_path / m.REDUNDANT_RECORD).exists()


def test_no_redundant_skips_the_step(staged, tmp_path):
    m.run_full(full_args(tmp_path, no_redundant=True))
    assert "--redundant" not in steps(staged) and "--redundant-auto" not in steps(staged)
    assert "Small.esp" in order(tmp_path)


def test_console_asks_instead(staged, tmp_path, monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    import builtins
    monkeypatch.setattr(builtins, "input", lambda p="": "k")
    m.run_full(full_args(tmp_path))
    red = next(c[0] for c in staged if c[0][0] in ("--redundant", "--redundant-auto"))
    assert red[0] == "--redundant" and "--no-interactive" not in red
    assert "Small.esp" in order(tmp_path)                       # kept both, as answered


def test_non_interactive_full_only_turns_off_sure_duplicates(staged, tmp_path):
    """Two versions of one mod are reported, never picked between, in a batch --full."""
    recs = [misc(f"i{i}", 1) for i in range(8)]
    from test_redundant import write
    df = str(tmp_path / "Data Files")
    write(df, "Mod - A.esp", recs, MW, "adds things")
    write(df, "Mod - B.esp", recs[:7] + [misc("i7", 2)], MW, "adds things")
    m.write_load_order(str(tmp_path), order(tmp_path) + ["Mod - A.esp", "Mod - B.esp"])
    m.run_full(full_args(tmp_path))
    assert order(tmp_path)[-2:] == ["Mod - A.esp", "Mod - B.esp"]
    assert "Small.esp" not in order(tmp_path)


def test_redundant_automerge_input_marks_the_merge_for_rebuild(tmp_path):
    """Small.esp is inside the AutoMerge (not in the load order itself): measured as the merge's inputs, it is
    redundant; it is recorded off, the merge is marked for rebuild, and --unmerge leaves it off."""
    from test_redundant import write
    df, paths = game(tmp_path, [BASE, ("Other.esp", [misc("o", 1)], MW, ""),
                                ("Big.esp", [misc("a", 7), misc("b", 9)], MW, "")])
    write(df, "Small.esp", [misc("a", 7)], MW, "")
    write(df, "Other2.esp", [misc("o2", 1)], MW, "")
    write(df, "mwdialog_check AutoMerge.esp", [misc("a", 7), misc("o2", 1)], MW, "")
    (tmp_path / m.MERGE_RECORD).write_text("[mwdialog_check AutoMerge.esp]\nSmall.esp\nOther2.esp\n", encoding="utf-8")
    m.write_load_order(str(tmp_path), ["Morrowind.esm", "Other.esp", "mwdialog_check AutoMerge.esp", "Big.esp"])
    run(tmp_path, "--redundant-auto", "--no-interactive")
    assert list(m.read_redundant(str(tmp_path))[0]) == ["Small.esp"]
    assert m.read_merge_rebuild(str(tmp_path)) == {"mwdialog_check AutoMerge.esp": ["Small.esp"]}
    run(tmp_path, "--unmerge", "--no-follow-up")
    lo = order(tmp_path)
    assert "Other2.esp" in lo and "Small.esp" not in lo
    assert m.read_merge_rebuild(str(tmp_path)) == {}


def test_undo_of_a_merged_input_waits_for_the_merge(tmp_path):
    from test_redundant import write
    df, _p = game(tmp_path, [BASE, ("Big.esp", [misc("a", 7), misc("b", 9)], MW, "")])
    write(df, "Small.esp", [misc("a", 7)], MW, "")
    write(df, "Other2.esp", [misc("o2", 1)], MW, "")
    write(df, "mwdialog_check AutoMerge.esp", [misc("a", 7), misc("o2", 1)], MW, "")
    (tmp_path / m.MERGE_RECORD).write_text("[mwdialog_check AutoMerge.esp]\nSmall.esp\nOther2.esp\n", encoding="utf-8")
    m.write_load_order(str(tmp_path), ["Morrowind.esm", "mwdialog_check AutoMerge.esp", "Big.esp"])
    run(tmp_path, "--redundant-auto", "--no-interactive")
    run(tmp_path, "--redundant-undo", "Small.esp")
    assert "Small.esp" not in order(tmp_path)                 # still inside the merge: not doubled
    assert m.read_redundant(str(tmp_path))[0] == {} and m.read_merge_rebuild(str(tmp_path)) == {}
    assert "--redundant-undo: turned Small.esp back on" in open(tmp_path / "fix.log", encoding="utf-8").read()
