"""The vendored tes3conv (tools/tes3conv): the pinned v0.4.1 program travels with its license files, wherever
it goes (the repository, deploy.py's list, and a local sync.py copy into MWManager). Fails if the program is there without its
licenses, or its SHA-256 is not the pin."""
import hashlib
import importlib.util
import os
import shutil
import subprocess

import pytest

from conftest import SRC

FOLDER = os.path.join(SRC, "tools", "tes3conv")
EXE = os.path.join(FOLDER, "tes3conv.exe")
# written out here on purpose: changing the program means changing this pin, tes3diff.py and NOTICE.md together
PIN = "3c259868c9deca42a658ff6c69cbc8578f8eeee99ebab5342bdb73beef650b40"
LICENSES = ("LICENSE", "LICENSE-tes3", "LICENSE-mimalloc_rust")
NOTICE = "NOTICE.md"
DEPLOY = os.path.join(SRC, "deploy.py")
MANIFEST = os.path.join(SRC, "deploy_manifest.txt")


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def text(name):
    with open(os.path.join(FOLDER, name), encoding="utf-8") as f:
        return f.read()


def test_the_vendored_program_is_the_pinned_release():
    assert os.path.isfile(EXE), "tools/tes3conv/tes3conv.exe is missing"
    assert sha256(EXE) == PIN


def test_the_pin_agrees_with_tes3diff_and_the_notice():
    assert PIN in text(NOTICE)
    if os.path.isfile(os.path.join(SRC, "tes3diff.py")):
        spec = importlib.util.spec_from_file_location("tes3diff_pin", os.path.join(SRC, "tes3diff.py"))
        t = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(t)
        assert t.EXE_SHA256["windows"] == PIN


def test_the_program_never_ships_without_its_license_files_and_notice():
    for name in LICENSES + (NOTICE,):
        p = os.path.join(FOLDER, name)
        assert os.path.isfile(p) and os.path.getsize(p) > 500, f"{name} is missing or empty"
    for name in LICENSES:
        t = text(name)
        assert "MIT License" in t or "Permission is hereby granted" in t
        assert "Greatness7" in t or "Octavian Oncescu" in t
    n = text(NOTICE)
    for must in ("v0.4.1", "https://github.com/Greatness7/tes3conv", "6dc51f7950d3581f62cf568ccb714801c24a10f0",
                 "51fae82b79838d76a39d0d1d0d472d7f48e8577f", "MIT OR Apache-2.0"):
        assert must in n, must


def test_every_program_under_tools_tes3conv_has_licenses_beside_it():
    root = os.path.join(SRC, "tools", "tes3conv")
    found = 0
    for base, _dirs, files in os.walk(root):
        exes = [f for f in files if f.lower().endswith((".exe", ".dll"))]
        if exes:
            found += len(exes)
            assert any(f.upper().startswith("LICENSE") for f in files), f"{base}: a program without a license file"
            assert NOTICE in files, f"{base}: a program without a NOTICE.md"
    assert found


@pytest.mark.skipif(shutil.which("git") is None or not os.path.isdir(os.path.join(SRC, ".git")),
                    reason="not a git checkout")
def test_git_tracks_the_program_and_every_license_file_without_lfs_or_ignore_rules():
    def git(*args):
        return subprocess.run(["git", "-C", SRC, *args], capture_output=True)
    tracked = git("ls-files", "-z", "--", "tools/tes3conv").stdout.decode().split("\0")
    for name in ("tes3conv.exe", NOTICE) + LICENSES:
        assert "tools/tes3conv/" + name in tracked, name
    assert git("check-ignore", "-q", "tools/tes3conv/tes3conv.exe").returncode == 1   # not ignored
    attrs = git("check-attr", "filter", "--", "tools/tes3conv/tes3conv.exe").stdout.decode()
    assert "lfs" not in attrs


@pytest.mark.skipif(not (os.path.isfile(DEPLOY) and os.path.isfile(MANIFEST)),
                    reason="deploy.py and deploy_manifest.txt are not vendored here (MWManager)")
def test_deploy_ships_the_program_only_together_with_its_licenses():
    spec = importlib.util.spec_from_file_location("deploy_for_vendored", DEPLOY)
    d = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(d)
    names = [n for n in os.listdir(FOLDER)]
    tracked = ["tools/tes3conv/" + n for n in names] + ["README.md", "tes3diff.py", "tests/test_x.py"]
    shipped = {src for src, _dst in d.ship_list(tracked, d.read_manifest(MANIFEST))}
    assert "tools/tes3conv/tes3conv.exe" in shipped
    for name in LICENSES + (NOTICE,):
        assert "tools/tes3conv/" + name in shipped, f"{name} would not ship with the program"
    assert "tes3diff.py" not in shipped and "tests/test_x.py" not in shipped         # the dev tool stays home
