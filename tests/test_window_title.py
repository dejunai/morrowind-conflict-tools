"""CT-49: the console window title is the current step, not a finished progress count.

A counted phase (pathgrids, the plugin scan, asset health) puts 'done/total' in the title and
puts the previous title back when it ends, so the next step's title is what you see. Tests hook
the title setter; the Windows API is not called.
"""
import mwdialog_console as MC
from test_pathgrid import run as pathgrid_run

STALL = ([(1000, 2000), (3000, 2000)], [(0, 1)])


def _titles(monkeypatch):
    seen = []
    MC._saved_titles[:] = []
    MC._current_title = None
    monkeypatch.setattr(MC, "_title_hook", seen.append)
    return seen


def test_end_count_restores_the_previous_title_and_drops_the_finished_count(monkeypatch):
    seen = _titles(monkeypatch)
    MC.set_title("mwdialog_check - Cell Fixes")
    MC.begin_count()
    MC.count_title("mwdialog_check - pathgrids", 0, 10)
    MC.count_title("mwdialog_check - pathgrids", 10, 10)
    MC.end_count("mwdialog_check")
    assert seen == [
        "mwdialog_check - Cell Fixes",
        "mwdialog_check - pathgrids 0/10",
        "mwdialog_check - pathgrids 10/10",
        "mwdialog_check - Cell Fixes",
    ]
    # no prior title: the finished count is still replaced
    MC._current_title = None
    MC.begin_count()
    MC.count_title("mwdialog_check - pathgrids", 5, 5)
    MC.end_count("mwdialog_check - Cell Fixes")
    assert seen[-1] == "mwdialog_check - Cell Fixes"
    assert seen[-2] == "mwdialog_check - pathgrids 5/5"


def test_title_changes_after_pathgrids_and_the_next_step_sets_its_own(tmp_path, monkeypatch):
    seen = _titles(monkeypatch)
    pathgrid_run(tmp_path, *STALL, (2000, 2000))
    counts = [t for t in seen if t.startswith("mwdialog_check - pathgrids ")]
    assert counts, seen
    assert all(" / " not in t or t.split()[-1].count("/") == 1 for t in counts)
    last_count = counts[-1]
    assert last_count.split()[-1] == last_count.split()[-1]  # done/total
    at = seen.index(last_count)
    after = seen[at + 1:]
    assert after, "the finished pathgrid count was left in the title bar: %r" % seen
    assert not any(t.startswith("mwdialog_check - pathgrids ") for t in after), after
    # the next Cell Fixes work names itself (door owners, then writing the patch)
    assert "mwdialog_check - Cell Fixes: door owners" in after
    assert "mwdialog_check - Cell Fixes: writing the patch" in after
    assert seen[0] == "mwdialog_check - Cell Fixes"