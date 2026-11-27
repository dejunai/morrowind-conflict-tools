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
    # orchestration: fake main() so this does not run a real --full; record argv and FULL_FINAL_PASS
    steps = []

    def fake(argv):
        steps.append((list(argv[1:]), m.FULL_FINAL_PASS))
        return 0
    monkeypatch.setattr(m, "main", fake)
    monkeypatch.setattr(m, "full_check", lambda *a, **k: 0)
    monkeypatch.setattr(m, "full_missing_masters", lambda *a, **k: [])
    monkeypatch.setattr(m, "full_reset", lambda *a, **k: 0)
    monkeypatch.setattr(m, "multipatch_aside", lambda *a, **k: 0)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    (tmp_path / "Data Files").mkdir()
    m.run_full(full_args(tmp_path, no_redundant=True, no_interactive=True, fresh_answers=True))

    # a --fix that can run pathgrids (early --full --fix is not the final pass)
    pathgrid_steps = [(i, argv, final) for i, (argv, final) in enumerate(steps)
                      if "--fix" in argv]
    assert pathgrid_steps, steps
    # only the last of those is the final pass (pathgrids run)
    assert pathgrid_steps[-1][2] is True
    assert all(final is False for _i, _a, final in pathgrid_steps[:-1])
    last_i, last_argv, _d = pathgrid_steps[-1]
    assert "--fix" in last_argv and "--multipatch" in last_argv
    # it is after --auto-merge, a later --clean (not bundled with --fix), and a --sort
    before = [argv for argv, _d in steps[:last_i]]
    merge_i = next(i for i, a in enumerate(before) if "--auto-merge" in a)
    assert any("--clean" in a and "--fix" not in a for a in before[merge_i + 1:])
    assert any("--sort" in a for a in before)
    assert not any("--all" in a for a in (argv for argv, _d in steps))
    # the sort immediately before the last --fix does not itself follow up with --fix
    prev_sort = [a for a in before if "--sort" in a][-1]
    assert "--no-follow-up" in prev_sort
    assert not any("--fix" in a or "--all" in a for a, _d in steps[last_i + 1:])
    assert sum(1 for a, final in steps if "--fix" in a and final is True) == 1


def test_standalone_fix_still_runs_pathgrids(tmp_path, monkeypatch):
    hits = _spy_repair(monkeypatch)
    assert m.IN_FULL is False and m.FULL_FINAL_PASS is False
    pathgrid_run(tmp_path, *STALL, (2000, 2000))
    assert hits, "standalone --fix (fix_cell_winners) must still call repair_pathgrids"


def test_deferred_fix_skips_pathgrids_and_does_not_drop_the_fixes_file(tmp_path, monkeypatch):
    hits = _spy_repair(monkeypatch)
    pg_file = tmp_path / m.PATHGRID_FIXES_FILE
    pg_file.write_text("keep me\n", encoding="utf-8")
    m.IN_FULL = True
    m.FULL_FINAL_PASS = False
    try:
        pathgrid_run(tmp_path, *STALL, (2000, 2000), fix=True)
    finally:
        m.IN_FULL = False
        m.FULL_FINAL_PASS = False
    assert hits == []
    assert pg_file.read_text(encoding="utf-8") == "keep me\n"


def test_full_final_pass_still_runs_pathgrids(tmp_path, monkeypatch):
    hits = _spy_repair(monkeypatch)
    m.IN_FULL = True
    m.FULL_FINAL_PASS = True
    try:
        pathgrid_run(tmp_path, *STALL, (2000, 2000), fix=True)
    finally:
        m.IN_FULL = False
        m.FULL_FINAL_PASS = False
    assert hits, "the last --full --fix must still call repair_pathgrids"
