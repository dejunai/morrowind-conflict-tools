"""No downgrade: --play (deploy_lua_tools) never puts an older version of a lua tools file over a
newer one (the local sync.py script uses the same rule). Hash lineage (--play's deploy record, a repo's git log) decides; modification times only for content
no record knows. Temporary folders only. Python 3.9+."""
import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mwdialog_backup                           # noqa: E402
import mwdialog_paths as P                       # noqa: E402

REL = os.path.join("MWSE", "mods", "mwsuite", "a", "main.lua")
HAVE_GIT = shutil.which("git") is not None


@pytest.fixture(autouse=True)
def _own_backups(monkeypatch):
    monkeypatch.setattr(mwdialog_backup, "ROOT", None)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def put(path, data, mtime=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def setup(tmp_path):
    src = tmp_path / "lua tools"
    data = tmp_path / "game" / "Data Files"
    data.mkdir(parents=True)
    return src, data


def deploy(src, data, tmp_path):
    return P.deploy_lua_tools(str(data), str(src), str(tmp_path / "bak"))


def entry(data):
    man = json.loads((data.parent / P.LUA_MANIFEST).read_text(encoding="utf-8"))
    return man["mods"]["mwsuite/a"]["files"][REL.replace(os.sep, "/")]


# downgrade_reason ------------------------------------------------------------------------------------------

def test_lineage_source_the_destination_moved_past():
    assert P.downgrade_reason({"v1"}, {"v2"}, ["v2", "v1"], 200, 100) == "lineage"     # mtime irrelevant


def test_lineage_newer_source_is_copied():
    assert P.downgrade_reason({"v2"}, {"v1"}, ["v2", "v1"], 100, 200) is None


def test_recorded_destination_is_replaced_whatever_the_mtime():
    assert P.downgrade_reason({"v3"}, {"v2"}, ["v2", "v1"], 100, 200) is None
    assert P.downgrade_reason({"v3"}, {"v1"}, [], 100, 200, src_history=["v2", "v1"]) is None


def test_unrecorded_source_over_out_of_band_edit_is_dated_by_mtime():
    assert P.downgrade_reason({"s"}, {"d"}, [], 100, 200) == "mtime"
    assert P.downgrade_reason({"s"}, {"d"}, [], 100, 100) == "mtime"
    assert P.downgrade_reason({"s"}, {"d"}, [], 200, 100) is None


def test_source_known_destination_out_of_band_is_kept():
    assert P.downgrade_reason({"v1"}, {"edit"}, ["v1"], 300, 100) == "lineage"


def test_git_blob_ids_match_git_and_autocrlf(tmp_path):
    lf, crlf = b"a\nb\n", b"a\r\nb\r\n"
    ids = P.git_blob_ids(crlf)
    assert P.git_blob_ids(lf) <= ids and len(ids) == 2
    if HAVE_GIT:
        f = tmp_path / "x"
        f.write_bytes(lf)
        out = subprocess.run(["git", "hash-object", str(f)], capture_output=True, check=True).stdout
        assert out.decode().strip() in P.git_blob_ids(lf)


@pytest.mark.skipif(not HAVE_GIT, reason="git not installed")
def test_git_path_history_newest_first(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def g(*a):
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
                        "-c", "core.autocrlf=false", *a], check=True, capture_output=True)
    g("init", "-q")
    f = repo / "lua tools" / "m.lua"
    for v in (b"v1\n", b"v2\n"):
        put(f, v)
        g("add", "-A")
        g("commit", "-q", "-m", "c")
    hist = P.git_path_history(repo, "lua tools/m.lua")
    blob = lambda d: hashlib.sha1(b"blob %d\0" % len(d) + d).hexdigest()
    assert hist == [blob(b"v2\n"), blob(b"v1\n")]
    assert P.git_path_history(repo, "lua tools/none.lua") == []
    assert P.git_path_history(tmp_path / "not-a-repo", "x") == []
    # Steam still has v1, the clone moved to v2: a downgrade whatever the times say
    assert P.downgrade_reason(P.git_blob_ids(b"v1\r\n"), P.git_blob_ids(b"v2\r\n"), hist, 300, 100) == "lineage"
    # an uncommitted clone edit made after Steam's (unrecorded) copy: kept
    assert P.downgrade_reason(P.git_blob_ids(b"v3\n"), P.git_blob_ids(b"wip\n"), hist, 100, 200) == "mtime"


# --play ---------------------------------------------------------------------------------------------------

def test_play_records_lineage_and_never_redeploys_an_older_version(tmp_path):
    src, data = setup(tmp_path)
    s, d = src / REL, data / REL
    put(s, b"v1", 1000)
    assert deploy(src, data, tmp_path)["copied"] == [REL]
    put(s, b"v2", 2000)
    res = deploy(src, data, tmp_path)
    assert res["updated"] == [REL] and d.read_bytes() == b"v2"
    assert entry(data)["sha256"] == sha(b"v2") and entry(data)["history"] == [sha(b"v1")]
    put(s, b"v1", 3000)                              # a stale v1 back in lua tools, with a fresh mtime
    res = deploy(src, data, tmp_path)
    assert res["updated"] == [] and res["newer"] == [REL] and res["newer_why"] == {REL: "lineage"}
    assert d.read_bytes() == b"v2"
    assert entry(data)["sha256"] == sha(b"v2") and entry(data)["history"] == [sha(b"v1")]
    put(s, b"v3", 4000)                              # a real new version still deploys
    res = deploy(src, data, tmp_path)
    assert res["updated"] == [REL] and res["newer"] == [] and d.read_bytes() == b"v3"
    assert entry(data)["history"] == [sha(b"v2"), sha(b"v1")]


def test_play_out_of_band_edit_newer_than_lua_tools_is_kept(tmp_path):
    src, data = setup(tmp_path)
    s, d = src / REL, data / REL
    put(s, b"v1", 1000)
    deploy(src, data, tmp_path)
    put(d, b"edited in Data Files", 5000)
    res = deploy(src, data, tmp_path)
    assert res["newer_why"] == {REL: "lineage"} and d.read_bytes() == b"edited in Data Files"
    put(s, b"v2", 4000)                              # lua tools changed too, but before the Data Files edit
    res = deploy(src, data, tmp_path)
    assert res["newer_why"] == {REL: "mtime"} and d.read_bytes() == b"edited in Data Files"
    put(s, b"v3", 6000)                              # lua tools changed after it: deployed, old one backed up
    res = deploy(src, data, tmp_path)
    assert res["updated"] == [REL] and d.read_bytes() == b"v3"
    assert (tmp_path / "bak" / REL).read_bytes() == b"edited in Data Files"


def test_play_identical_is_a_no_op_and_never_deployed_deploys(tmp_path):
    src, data = setup(tmp_path)
    put(src / REL, b"same", 2000)
    put(data / REL, b"same", 1000)
    res = deploy(src, data, tmp_path)
    assert res["copied"] == res["updated"] == res["newer"] == []
    put(src / REL, b"new", 2000)
    put(data / REL, b"old, never deployed", 1000)    # no record and no newer evidence
    res = deploy(src, data, tmp_path)
    assert res["updated"] == [REL] and (data / REL).read_bytes() == b"new"


def test_play_warning_is_one_actionable_line():
    for why in ("lineage", "mtime"):
        line = P.lua_newer_line(REL, why, "LT")
        assert "\n" not in line and REL in line and "WARNING" in line and "LT" in line and "delete" in line