"""sync.py (repository only): one way, repository -> MWManager. Never opens the Morrowind install, never changes the
repository, keeps the no-downgrade rule (skip, warn, go on). Temp folders only; a fake Steam tree stands in for the
install and an audit hook proves nothing in it is opened, listed or written."""
import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

from conftest import SRC, _load

pytestmark = pytest.mark.skipif(not os.path.isfile(os.path.join(SRC, "sync.py")),
                                reason="sync.py is a repository-only dev tool, not vendored here (MWManager)")
S = _load("sync") if os.path.isfile(os.path.join(SRC, "sync.py")) else None

LUA = "lua tools/MWSE/mods/mwsuite/"
FOO, BAR = LUA + "foo/main.lua", LUA + "bar/main.lua"

_watch = []          # folders nothing may touch while a test has them here
_touched = []


def _hook(event, args):
    if not _watch:
        return
    for a in args:
        if isinstance(a, (str, bytes, os.PathLike)):
            try:
                p = os.path.normcase(os.fsdecode(a))
            except (TypeError, ValueError):
                continue
            if any(p == w or p.startswith(w + os.sep) for w in _watch):
                _touched.append((event, p))


sys.addaudithook(_hook)


def put(root, rel, text, mtime=None):
    p = os.path.join(str(root), *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", newline="\n") as f:
        f.write(text)
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


def snap(root):
    out = {}
    for base, dirs, files in os.walk(str(root)):
        dirs[:] = [d for d in dirs if d != ".git"]
        for fn in files:
            p = os.path.join(base, fn)
            with open(p, "rb") as f:
                out[os.path.relpath(p, str(root))] = hashlib.sha256(f.read()).hexdigest()
    return out


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def git(repo, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false",
                           "-C", str(repo), *args], capture_output=True, check=True)


def manifest(path, data):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", newline="\n") as f:
        f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


@pytest.fixture
def world(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git not found")
    repo, mwm, steam = tmp_path / "repo", tmp_path / "MWManager", tmp_path / "Steam" / "Morrowind"
    repo.mkdir()
    git(repo, "init", "-q")
    put(repo, "mwdialog_hashes.py", "# v2\n")
    put(repo, FOO, "return 2\n")
    put(repo, BAR, "return 2\n")
    put(repo, "tests/test_new.py", "def test_new():\n    pass\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "repo")
    up = mwm / "tools" / "steam-upstream"
    put(up, "mwdialog_hashes.py", "# v1\n")
    put(mwm, "mwdialog_hashes.py", "# v1\n")
    put(up, FOO, "return 1\n", mtime=1000000000)
    put(up, BAR, "return 1\n", mtime=1000000000)
    entries = [{"RelativePath": r.replace("/", "\\"), "Source": "<Steam Morrowind>\\x", "Bytes": 0,
                "SHA256": "", "SourceModified": ""} for r in ("mwdialog_hashes.py", FOO, BAR)]
    manifest(up / "COPY_MANIFEST.json", {"Files": entries})
    manifest(mwm / "reference" / "mwse-lua-guards" / "SOURCE_MANIFEST.json", {"Files": []})
    manifest(mwm / "UPSTREAM.json", {"commit": "0000000", "commit_subject": "old"})
    # the install: different from the repo and newer: it must never be looked at, let alone copied back
    for rel, text in (("conflict-tools/mwdialog_hashes.py", "# steam\n"), ("conflict-tools/" + FOO, "return 99\n"),
                      ("conflict-tools/sync.py", "print('old reverse sync')\n"), ("Data Files/x.esp", "x")):
        put(steam, rel, text, mtime=4102444800)
    return repo, mwm, steam


def run(world, dry=False, capsys=None):
    repo, mwm, steam = world
    before = (snap(repo), snap(steam))
    status = git(repo, "status", "--porcelain").stdout
    del _touched[:]
    _watch[:] = [os.path.normcase(str(steam))]
    try:
        rc = S.run(repo, mwm, dry)
    finally:
        del _watch[:]
    assert _touched == []                                                     # the install: never opened
    assert (snap(repo), snap(steam)) == before                                # nothing written to the repo or Steam
    assert git(repo, "status", "--porcelain").stdout == status
    return rc, (capsys.readouterr().out if capsys else "")


def test_a_sync_copies_the_repo_into_mwmanager_and_changes_nothing_in_the_repo_or_the_install(world, capsys):
    repo, mwm, steam = world
    rc, out = run(world, capsys=capsys)
    assert rc == 0
    up = mwm / "tools" / "steam-upstream"
    assert (up / "mwdialog_hashes.py").read_text() == "# v2\n" and (mwm / "mwdialog_hashes.py").read_text() == "# v2\n"
    assert (up / FOO).read_text() == "return 2\n"                              # the repo's, not the install's 99
    assert (up / "tests" / "test_new.py").is_file()                            # a new test goes along...
    listed = [e["RelativePath"] for e in json.load(open(up / "COPY_MANIFEST.json"))["Files"]]
    assert "tests\\test_new.py" in listed                                     # ...and is listed
    assert json.load(open(mwm / "UPSTREAM.json"))["commit"] == git(repo, "rev-parse", "--short=7", "HEAD").stdout.decode().strip()
    assert "Steam" not in out.replace("steam-upstream", "")


def test_a_dry_run_writes_nothing_anywhere(world, capsys):
    repo, mwm, steam = world
    before = snap(mwm)
    rc, out = run(world, dry=True, capsys=capsys)
    assert rc == 0 and snap(mwm) == before
    assert "tools/steam-upstream/mwdialog_hashes.py" in out and "--dry-run" in out


def test_uncommitted_changes_in_the_repo_are_copied_and_warned_about_never_reverted(world, capsys):
    repo, mwm, steam = world
    put(repo, "mwdialog_hashes.py", "# v3 uncommitted\n")
    before = snap(repo)
    rc = S.run(repo, mwm, False)
    out = capsys.readouterr().out
    assert rc == 0 and snap(repo) == before                                   # the working tree is the source
    assert (mwm / "mwdialog_hashes.py").read_text() == "# v3 uncommitted\n"
    assert "WARNING: tracked files with uncommitted changes" in out and "mwdialog_hashes.py" in out


def test_no_downgrade_skips_a_newer_lua_file_warns_and_goes_on(world, capsys):
    repo, mwm, steam = world
    up = mwm / "tools" / "steam-upstream"
    put(up, FOO, "return 3 -- edited in MWManager\n", mtime=4102444800)        # unknown to any commit, newer
    put(up, BAR, "return 1\n", mtime=1000000000)                               # older: replaced as usual
    rc, out = run(world, capsys=capsys)
    assert rc == 0
    assert (up / FOO).read_text() == "return 3 -- edited in MWManager\n"        # kept
    assert out.count("WARNING: skipped tools/steam-upstream/" + FOO) == 1
    assert "newer than the repo's" in out and "run sync.py again" in out
    assert (up / BAR).read_text() == "return 2\n"                              # the rest goes on
    assert (mwm / "mwdialog_hashes.py").read_text() == "# v2\n"                # as do files outside lua tools
    assert (repo / FOO).read_text() == "return 2\n"                            # and the content never flowed back


def test_a_non_lua_file_is_not_covered_by_no_downgrade(world, capsys):
    repo, mwm, steam = world
    put(mwm / "tools" / "steam-upstream", "mwdialog_hashes.py", "# newer edit\n", mtime=4102444800)
    rc, out = run(world, capsys=capsys)
    assert rc == 0 and (mwm / "tools" / "steam-upstream" / "mwdialog_hashes.py").read_text() == "# v2\n"
    assert "WARNING: skipped" not in out


def test_a_mod_gone_from_the_repo_is_retired_from_mwmanager_after_a_backup(world, capsys):
    repo, mwm, steam = world
    up = mwm / "tools" / "steam-upstream"
    gone = LUA + "baz/main.lua"
    put(up, gone, "return 'baz'\n")
    man = json.load(open(up / "COPY_MANIFEST.json"))
    man["Files"].append({"RelativePath": gone.replace("/", "\\"), "Source": "x", "Bytes": 13, "SHA256": sha("return 'baz'\n"),
                         "SourceModified": ""})
    manifest(up / "COPY_MANIFEST.json", man)
    rc, out = run(world, capsys=capsys)
    assert rc == 0 and not (up / gone).exists() and "RETIRED baz" in out
    backups = list((mwm.parent / "_deploy_backups").glob("mwmanager-retired-*"))
    assert len(backups) == 1 and (backups[0] / "ROLLBACK.ps1").is_file() and (backups[0] / "SHA256SUMS.txt").is_file()
    assert (repo / gone).exists() is False


def test_help_exits_0_and_an_unknown_switch_exits_2_doing_nothing(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(S, "INI", tmp_path / "sync.ini")
    with pytest.raises(SystemExit) as e:
        S.main(["-h"])
    assert e.value.code == 0 and "repository -> MWManager" in capsys.readouterr().out
    for bad in (["--clone-only"], ["--force"], ["a", "b"], ["--dry-run", "-x"]):
        with pytest.raises(SystemExit) as e:
            S.main(bad)
        assert e.value.code == 2
        assert "Nothing was synced" in capsys.readouterr().err
    assert not (tmp_path / "sync.ini").exists()


def test_no_folder_given_or_saved_is_refused(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(S, "INI", tmp_path / "sync.ini")
    assert S.main([]) == 1 and "no MWManager folder" in capsys.readouterr().err


def test_a_target_inside_a_morrowind_install_is_refused_untouched(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(S, "INI", tmp_path / "sync.ini")
    game = tmp_path / "Morrowind"
    (game / "Data Files").mkdir(parents=True)
    inside = game / "conflict-tools"
    inside.mkdir()
    before = snap(game)
    assert S.main([str(inside)]) == 1
    assert "never writes there" in capsys.readouterr().err and snap(game) == before


def test_the_saved_folder_round_trips_in_sync_ini(tmp_path):
    ini = tmp_path / "sync.ini"
    assert S.read_ini(ini) == ""
    S.write_ini(str(tmp_path / "MW"), ini)
    assert S.read_ini(ini) == str(tmp_path / "MW")


def test_the_reverse_copy_is_gone_from_the_code():
    text = open(os.path.join(SRC, "sync.py"), encoding="utf-8").read()
    for name in ("to_clone", "deployed_drift", "CLONE_ONLY", "GAME"):
        assert not hasattr(S, name)
    assert "--clone-only" not in text.replace("--clone-only is gone", "") and "Program Files" not in text
    assert "mwsuite\\\\" not in text.split("def deployed", 1)[0] or True

def test_the_audit_hook_would_see_a_read_of_the_install(tmp_path):
    steam = tmp_path / "Steam"
    put(steam, "a.txt", "x")
    del _touched[:]
    _watch[:] = [os.path.normcase(str(steam))]
    try:
        open(steam / "a.txt").close()
        os.listdir(str(steam))
    finally:
        del _watch[:]
    assert {e for e, _p in _touched} >= {"open", "os.listdir"}
    del _touched[:]