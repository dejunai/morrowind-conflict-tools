"""deploy.py ships exactly what deploy_manifest.txt names (git-tracked files only), never tests, .git/CI, dev
files, audits or backups; it saves the target in deploy.ini, backs up what it overwrites (SHA256SUMS.txt,
NEW_FILES.txt, a relative ROLLBACK.ps1), hash-checks, never puts an older "lua tools" file over a newer one, and an
unknown switch does nothing. Temporary folders only. Python 3.9+."""
import importlib.util
import os
import shutil
import subprocess

import pytest

from conftest import SRC

DEPLOY = os.path.join(SRC, "deploy.py")
pytestmark = pytest.mark.skipif(not os.path.isfile(DEPLOY) or shutil.which("git") is None,
                                reason="deploy.py is not vendored here (MWManager), or git is missing")
DEV = ("tests/", "diag/", ".git", ".github/", "deploy.py", "deploy.ini", "deploy_manifest.txt", "sync.py",
       "agents.md", "_backup/", "backups/", "docs/dev/")


def load():
    spec = importlib.util.spec_from_file_location("deploy_under_test", DEPLOY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def is_dev(rel):
    low = rel.replace("\\", "/").lower()
    return low.startswith(DEV) or "/tests/" in low or "audit" in low.rsplit("/", 1)[-1] or "/.git" in low


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false",
                    *args], check=True, capture_output=True)


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())


@pytest.fixture
def proj(tmp_path):
    p = tmp_path / "project"
    p.mkdir()
    shutil.copyfile(DEPLOY, str(p / "deploy.py"))
    shutil.copyfile(os.path.join(SRC, "deploy_manifest.txt"), str(p / "deploy_manifest.txt"))
    for rel, data in {"vortex_tidy.py": "print(1)\n", "mwdialog_x.py": "x = 1\n", "tidy.bat": "@echo off\n",
                      "Play Morrowind.bat": "@echo off\n", "README.md": "# readme\n", "docs/MORE_INFO.md": "more\n",
                      "docs/CHANGES.md": "c\n", "docs/dev/TODO.md": "todo\n", "LUA_EDIT_AUDIT.md": "audit\n", "AGENTS.md": "a\n", "sync.py": "s\n",
                      "docs/OFF-LAYOUT.md": "off\n", "tests/test_a.py": "def test(): pass\n",
                      "tests/fixtures/f.lua": "--\n", "diag/d.py": "d\n", ".gitignore": "deploy.ini\n",
                      ".github/workflows/ci.yml": "on: push\n",
                      "lua tools/MWSE/mods/mwsuite/mwguard/main.lua": "return 1\n",
                      "lua tools/MWSE/core/initialize.lua": "core\n",
                      "lua tools/mwsuite-metadata.toml": "[tools]\n",
                      "tools/luajit/luajit.exe": b"MZ", "tools/luajit/jit/.gitignore": "*\n"}.items():
        put(p / rel, data)
    put(p / "untracked.py", "not tracked\n")
    git(p, "init", "-q")
    git(p, "add", "-A", ".", ":!untracked.py")
    git(p, "commit", "-q", "-m", "init")
    dep = load()
    return p, dep, tmp_path


def run(dep, proj_dir, *argv):
    return dep.main(list(argv), project=str(proj_dir), ini=str(proj_dir / "deploy.ini"))


def tree(root):
    out = {}
    for base, _ds, fns in os.walk(str(root)):
        for fn in fns:
            p = os.path.join(base, fn)
            out[os.path.relpath(p, str(root)).replace(os.sep, "/")] = open(p, "rb").read()
    return out


def test_the_real_manifest_ships_no_test_or_dev_file():
    dep = load()
    files = dep.ship_list(dep.tracked_files(SRC), dep.read_manifest(os.path.join(SRC, "deploy_manifest.txt")))
    assert files, "the manifest ships nothing"
    bad = [r for r, d in files if is_dev(r) or is_dev(d)]
    assert bad == [], bad
    assert not any("/mwse/core/" in d.lower() for _r, d in files)
    dests = {d for _r, d in files}
    assert {"vortex_tidy.py", "mwdialog_check.py", "docs/README.md", "docs/MORE_INFO.md", "docs/CHANGES.md"} <= dests
    assert not any(d.lower().startswith("docs/dev/") for d in dests)       # dev notes stay in the repository


def test_rules_in_the_manifest_cannot_ship_a_never_file(tmp_path):
    dep = load()
    rules = [("include", "**", None)]
    tracked = ["tests/test_x.py", "a/tests/b.py", ".gitignore", ".github/x.yml", "deploy.py", "sync.py",
               "CODEX_AUDIT-1.MD", "_backup/n.txt", "backups/b.zip", "docs/dev/TODO.md", "mwdialog_x.py"]
    assert [d for _r, d in dep.ship_list(tracked, rules)] == ["mwdialog_x.py"]


def test_a_deploy_ships_the_manifest_set_and_nothing_dev(proj, capsys):
    p, dep, tmp = proj
    target, backups = tmp / "game" / "conflict-tools", tmp / "bk"
    assert run(dep, p, str(target), "--backups", str(backups)) == 0
    got = tree(target)
    assert set(got) == {"vortex_tidy.py", "mwdialog_x.py", "tidy.bat", "docs/README.md", "docs/MORE_INFO.md",
                        "docs/CHANGES.md", "docs/OFF-LAYOUT.md", "lua tools/MWSE/mods/mwsuite/mwguard/main.lua",
                        "lua tools/mwsuite-metadata.toml", "tools/luajit/luajit.exe"}
    assert not [r for r in got if is_dev(r)]                              # the deployed tree has no test/dev file
    assert got["docs/README.md"] == b"# readme\n"
    assert "deploy.ini" in os.listdir(str(p))                             # saved for next time
    assert run(dep, p) == 0                                               # no argument: the saved target
    assert "Nothing to copy" in capsys.readouterr().out


def test_dry_run_and_unknown_switches_write_nothing(proj, capsys):
    p, dep, tmp = proj
    target = tmp / "t"
    assert run(dep, p, str(target), "--dry-run") == 0
    assert not target.exists() and not (p / "deploy.ini").exists()
    with pytest.raises(SystemExit) as e:
        run(dep, p, str(target), "--fast")
    assert e.value.code == 2
    assert not target.exists() and not (p / "deploy.ini").exists()
    with pytest.raises(SystemExit) as e:
        run(dep, p, "--help")
    assert e.value.code == 0 and "deploy_manifest.txt" in capsys.readouterr().out


def test_no_target_and_nothing_saved_stops_with_a_message(proj, capsys):
    p, dep, _tmp = proj
    assert run(dep, p) == 2
    assert "no target folder given" in capsys.readouterr().out


def test_a_new_target_replaces_the_saved_one(proj):
    p, dep, tmp = proj
    assert run(dep, p, str(tmp / "one"), "--backups", str(tmp / "bk")) == 0
    assert run(dep, p, str(tmp / "two")) == 0
    assert dep.read_ini(str(p / "deploy.ini"))["target"] == str(tmp / "two")
    assert dep.read_ini(str(p / "deploy.ini"))["backups"] == str(tmp / "bk")


def test_overwritten_files_are_backed_up_with_sums_and_a_relative_rollback(proj):
    p, dep, tmp = proj
    target, backups = tmp / "t", tmp / "bk"
    assert run(dep, p, str(target), "--backups", str(backups)) == 0
    (target / "vortex_tidy.py").write_text("old\n")
    put(p / "mwdialog_new.py", "n\n")
    git(p, "add", "mwdialog_new.py")
    assert run(dep, p) == 0
    (b,) = [x for x in sorted(os.listdir(str(backups))) if x.startswith("conflict-tools-deploy-")][-1:]
    b = backups / b
    sums = (b / "SHA256SUMS.txt").read_text().splitlines()
    assert len(sums) == 1 and sums[0].endswith("  t/vortex_tidy.py") and len(sums[0].split("  ")[0]) == 64
    assert (b / "t" / "vortex_tidy.py").read_text() == "old\n"
    assert (b / "NEW_FILES.txt").read_text().split() == ["mwdialog_new.py"]
    ps1 = (b / "ROLLBACK.ps1").read_text()
    assert "-split '  ', 2" in ps1 and str(tmp) not in ps1 and '"..' in ps1     # relative to the backup folder
    assert (target / "vortex_tidy.py").read_text() == "print(1)\n"


def test_backups_inside_the_target_or_its_game_are_refused(proj, capsys):
    p, dep, tmp = proj
    game = tmp / "Morrowind"
    put(game / "Morrowind.exe", b"MZ")
    target = game / "conflict-tools"
    assert run(dep, p, str(target), "--backups", str(game / "bk")) == 1
    assert run(dep, p, str(target), "--backups", str(target / "bk")) == 1
    assert "inside the target or its game install" in capsys.readouterr().err
    assert not target.exists()


def test_a_newer_lua_tools_file_in_the_target_is_not_downgraded(proj, capsys):
    p, dep, tmp = proj
    target = tmp / "t"
    assert run(dep, p, str(target), "--backups", str(tmp / "bk")) == 0
    lua = target / "lua tools" / "MWSE" / "mods" / "mwsuite" / "mwguard" / "main.lua"
    lua.write_text("return 2 -- edited in the target\n")
    later = os.path.getmtime(str(p / "lua tools" / "MWSE" / "mods" / "mwsuite" / "mwguard" / "main.lua")) + 100
    os.utime(str(lua), (later, later))
    (p / "vortex_tidy.py").write_text("print(2)\n")
    capsys.readouterr()
    assert run(dep, p) == 0
    out = capsys.readouterr().out
    assert "WARNING: kept lua tools/MWSE/mods/mwsuite/mwguard/main.lua" in out
    assert lua.read_text() == "return 2 -- edited in the target\n"
    assert (target / "vortex_tidy.py").read_text() == "print(2)\n"        # the rest goes on


def test_an_older_committed_lua_tools_file_in_the_target_is_replaced(proj):
    p, dep, tmp = proj
    target = tmp / "t"
    assert run(dep, p, str(target), "--backups", str(tmp / "bk")) == 0
    src = p / "lua tools" / "MWSE" / "mods" / "mwsuite" / "mwguard" / "main.lua"
    src.write_text("return 3\n")
    git(p, "commit", "-q", "-am", "newer lua")
    dst = target / "lua tools" / "MWSE" / "mods" / "mwsuite" / "mwguard" / "main.lua"
    os.utime(str(dst), (os.path.getmtime(str(src)) + 100,) * 2)          # newer mtime, but a known older version
    assert run(dep, p) == 0
    assert dst.read_text() == "return 3\n"
