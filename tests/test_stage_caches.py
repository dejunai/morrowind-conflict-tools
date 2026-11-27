"""CT-43: the asset check and the pathgrid check take what an earlier run worked out from their caches. A first
run works everything out, a second run with nothing changed reads nothing again, and a changed input is worked
out again. The pathgrid cache is kept across edits to code the pathgrid check never runs and across line
endings (the deployed copy is CRLF, the checkout LF); the pathgrid stage prints its time like the asset check."""
import os
import re
import shutil
import subprocess
import sys

from conftest import SRC, ah, m
import mwdialog_pathgrid as PG
from test_cache import dds, install, reopen, run as asset_run
from test_pathgrid import run as pathgrid_run

STALL = ([(1000, 2000), (3000, 2000)], [(0, 1)])


# ---------------------------------------------------------------- the asset check
def test_asset_check_second_run_reads_nothing_and_a_changed_file_is_read_again(tmp_path, capsys, monkeypatch):
    g, df = install(tmp_path)
    reads = []
    real_tex, real_model = ah.texture_facts, ah.model_facts
    monkeypatch.setattr(ah, "texture_facts", lambda head, m: reads.append("tex") or real_tex(head, m))
    monkeypatch.setattr(ah, "model_facts", lambda b, m: reads.append("nif") or real_model(b, m))
    asset_run(df, capsys)
    assert reads.count("tex") == 5 and reads.count("nif") == 2          # run 1: every file is read
    reopen(g)
    del reads[:]
    m.main([str(df), "--plugins", "Base.esm", "--asset-check", "--no-vortex", "--min-severity", "INFO"])
    assert reads == []                                                  # run 2: all from the cache
    assert re.search(r"^\[\d+s\] Asset health: done, \d+ file\(s\) to fix$", capsys.readouterr().err, re.M)
    reopen(g)
    (df / "Textures" / "tx_b.dds").write_bytes(dds(64, 64))             # another size: worked out again
    asset_run(df, capsys)
    assert reads == ["tex"]


# ---------------------------------------------------------------- the pathgrid check
def test_pathgrid_second_run_hits_the_cache_and_prints_its_time(tmp_path, capsys):
    pathgrid_run(tmp_path, *STALL, (2000, 2000))
    err = capsys.readouterr().err
    assert re.search(r"^\[\d+s\] Pathgrids: 1 outdoor pathgrid\(s\), 0 taken from mwdialog_pathgrid_cache\.json$",
                     err, re.M)
    pathgrid_run(tmp_path, *STALL, (2000, 2000))
    assert re.search(r"^\[\d+s\] Pathgrids: 1 outdoor pathgrid\(s\), 1 taken from", capsys.readouterr().err, re.M)
    pathgrid_run(tmp_path, *STALL, (2000, 2040))                        # the stall moved: worked out again
    assert re.search(r"^\[\d+s\] Pathgrids: 1 outdoor pathgrid\(s\), 0 taken from", capsys.readouterr().err, re.M)


def _version_of(folder):
    code = "import sys; sys.path.insert(0, sys.argv[1]); import mwdialog_pathgrid as PG; print(PG._code_version())"
    out = subprocess.run([sys.executable, "-c", code, str(folder)], capture_output=True, text=True,
                         cwd=str(folder), env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def _copy_tools(dst, crlf=False):
    """A copy of the tools with LF line endings (CRLF with crlf=True), whatever the checkout here has: a Windows
    checkout with core.autocrlf=true is CRLF, so _edit's LF snippets would not be found in a raw copy."""
    dst.mkdir()
    for n in os.listdir(SRC):
        if n.startswith("mwdialog_") and n.endswith(".py"):
            b = open(os.path.join(SRC, n), "rb").read().replace(b"\r\n", b"\n")
            if crlf:
                b = b.replace(b"\n", b"\r\n")
            (dst / n).write_bytes(b)
    return dst


def _edit(folder, name, old, new):
    p = folder / name
    text = p.read_bytes().decode("utf-8")
    assert old in text
    p.write_bytes(text.replace(old, new, 1).encode("utf-8"))


def test_pathgrid_code_version_ignores_line_endings_and_code_it_never_runs(tmp_path):
    here = PG._code_version()                                               # this checkout, LF or CRLF
    assert here == PG._code_version()
    assert _version_of(_copy_tools(tmp_path / "lf")) == here
    assert _version_of(_copy_tools(tmp_path / "crlf", crlf=True)) == here      # the deployed copy
    other = _copy_tools(tmp_path / "other")
    # the Multipatch's bone grafting and the --play hash hook live in the same files but never run here
    _edit(other, "mwdialog_footing.py", "def graft_bones(data, ref_data, need):\n",
          "def graft_bones(data, ref_data, need):\n    pass  # changed\n")
    _edit(other, "mwdialog_tes3.py", "def write_plugin_bytes(path, data, keep_times=None):\n",
          "def write_plugin_bytes(path, data, keep_times=None):\n    pass  # changed\n")
    (other / "mwdialog_footing.py").write_bytes((other / "mwdialog_footing.py").read_bytes()
                                                + b"\n\ndef something_new():\n    return 1\n")
    assert _version_of(other) == here


def test_pathgrid_code_version_changes_with_code_the_check_uses(tmp_path):
    here = PG._code_version()
    surfaces = _copy_tools(tmp_path / "surfaces")
    _edit(surfaces, "mwdialog_footing.py", "class Surfaces:\n", "class Surfaces:\n    CHANGED = 1\n")
    assert _version_of(surfaces) != here
    own = _copy_tools(tmp_path / "own")
    _edit(own, "mwdialog_pathgrid.py", "CLEAR = 48.0", "CLEAR = 40.0")
    assert _version_of(own) != here
    land = _copy_tools(tmp_path / "land")                                 # two calls away: Placements -> land_heights
    _edit(land, "mwdialog_records.py", "    return [v * 8.0 for v in h]", "    return [v * 8.5 for v in h]")
    assert _version_of(land) != here


def test_a_cache_from_another_code_version_is_not_used(tmp_path, capsys):
    pathgrid_run(tmp_path, *STALL, (2000, 2000))
    path = tmp_path / PG.PATHGRID_CACHE_FILE
    data = path.read_text(encoding="utf-8").replace(PG._code_version(), "0" * 40)
    path.write_text(data, encoding="utf-8")
    capsys.readouterr()
    pathgrid_run(tmp_path, *STALL, (2000, 2000))
    assert re.search(r"^\[\d+s\] Pathgrids: 1 outdoor pathgrid\(s\), 0 taken from", capsys.readouterr().err, re.M)