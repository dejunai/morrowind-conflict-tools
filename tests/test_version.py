"""Package version: --version, run headers, pack-report summary, release.py match check."""
import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

import mwdialog_version
import mwdialog_report as MR

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ["mwdialog_check.py", "vortex_tidy.py", "mwdialog_luafix.py", "mwdialog_paths.py"]


def test_version_string():
    assert mwdialog_version.__version__ == "0.93-beta"
    assert "0.93-beta" in mwdialog_version.version_label()
    assert "mwdialog_check" in mwdialog_version.version_label("mwdialog_check")


@pytest.mark.parametrize("tool", TOOLS)
def test_version_flag_prints_and_exits_zero(tool):
    r = subprocess.run([sys.executable, str(ROOT / tool), "--version"],
                       capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr
    assert "0.93-beta" in (r.stdout + r.stderr)


def test_pack_report_summary_includes_version():
    text = MR.summary_text({}, [], [], "2026-01-01 00:00:00")
    assert "conflict-tools report: scrub summary" in text
    assert "version: 0.93-beta" in text


def test_release_py_refuses_a_mismatched_version():
    release = pytest.importorskip("release")
    with pytest.raises(SystemExit) as exc:
        release.main(["v9.9-beta"])
    assert "does not match __version__" in str(exc.value)
