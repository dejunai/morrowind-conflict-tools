"""CT-48: --full runs pathgrids once, after --clean and the last --sort. A standalone --fix still runs them."""
import sys

from conftest import m
from test_full_redundant import full_args
from test_pathgrid import run as pathgrid_run

STALL = ([(1000, 2000), (3000, 2000)], [(0, 1)])


def _spy_repair(monkeypatch):
    hits = []
    real = m.repair_pathgrids

    def spy(*a, **k):
        hits.append(1)
        return real(*a, **k)
    monkeypatch.setattr(m, "repair_pathgrids", spy)
    return hits


def test_run_full_calls_pathgrids_once_and_last_after_clean_and_sort(tmp_path, monkeypatch):
    # orchestration: fake main() so this does not run a real --full; record argv and the defer flag
    steps = []

    def fake(argv):
        steps.append((list(argv[1:]), m.DEFER_PATHGRIDS))
        return 0
    monkeypatch.setattr(m, "main", fake)
    monkeypatch.setattr(m, "full_check", lambda *a, **k: 0)
    monkeypatch.setattr(m, "full_missing_masters", lambda *a, **k: [])
    monkeypatch.setattr(m, "full_reset", lambda *a, **k: 0)
    monkeypatch.setattr(m, "multipatch_aside", lambda *a, **k: 0)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    (tmp_path / "Data Files").mkdir()
    m.run_full(full_args(tmp_path, no_redundant=True, no_interactive=True, fresh_answers=True))

    flags = [[a[0] for a in argv if a.startswith("--")] for argv, _d in steps]
    # a --fix or --all that can run pathgrids
    pathgrid_steps = [(i, argv, defer) for i, (argv, defer) in enumerate(steps)
                      if "--fix" in argv or "--all" in argv]
    assert pathgrid_steps, steps
    # only the last of those actually runs pathgrids
    assert pathgrid_steps[-1][2] is False
    assert all(defer is True for _i, _a, defer in pathgrid_steps[:-1])
    last_i, last_argv, _d = pathgrid_steps[-1]
    assert "--fix" in last_argv and "--multipatch" in last_argv
    # it is after --all (which includes --clean) and after a --sort
    before = [argv for argv, _d in steps[:last_i]]
    assert any("--all" in a for a in before)
    assert any("--sort" in a for a in before)
    # the sort immediately before the last --fix does not itself follow up with --fix
    prev_sort = [a for a in before if "--sort" in a][-1]
    assert "--no-follow-up" in prev_sort
    assert not any("--fix" in a or "--all" in a for a, _d in steps[last_i + 1:])
    # and it really is the last of those flags in the whole run
    assert sum(1 for a, d in steps if "--fix" in a and d is False) == 1


def test_standalone_fix_still_runs_pathgrids(tmp_path, monkeypatch):
    hits = _spy_repair(monkeypatch)
    assert m.DEFER_PATHGRIDS is False
    pathgrid_run(tmp_path, *STALL, (2000, 2000))
    assert hits, "standalone --fix (fix_cell_winners) must still call repair_pathgrids"


def test_deferred_fix_skips_pathgrids_and_does_not_drop_the_fixes_file(tmp_path, monkeypatch):
    hits = _spy_repair(monkeypatch)
    pg_file = tmp_path / m.PATHGRID_FIXES_FILE
    pg_file.write_text("keep me\n", encoding="utf-8")
    m.DEFER_PATHGRIDS = True
    try:
        pathgrid_run(tmp_path, *STALL, (2000, 2000))
    finally:
        m.DEFER_PATHGRIDS = False
    assert hits == []
    assert pg_file.read_text(encoding="utf-8") == "keep me\n"
