"""mwwarnsuppression finds its patch sites by the warning text each one prints, not by address.
Needs the bundled LuaJIT and a Morrowind.exe next to the scripts; skipped without them."""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.path.join(ROOT, "tools", "luajit", "luajit.exe")
EXE = os.path.join(ROOT, "Morrowind.exe")
MODS = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite")
DRIVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "warnlocate_driver.lua")

pytestmark = pytest.mark.skipif(not (os.path.isfile(LUAJIT) and os.path.isfile(EXE)),
                                reason="needs tools\\luajit and Morrowind.exe")


def _find(*extra):
    out = subprocess.run([LUAJIT, DRIVER, MODS, EXE, *extra], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return dict(line.rstrip().split(" ", 1) for line in out.stdout.splitlines())


def _build_the_addresses_came_from():
    with open(EXE, "rb") as f:
        f.seek(0x4A1B02 - 0x400000)
        return f.read(3) == b"\x8b\xcd\xe8"


def test_every_site_is_found_and_the_patch_keeps_the_jump_target():
    found = _find()
    for name in ("bodyPart", "texture", "nif", "kf"):
        assert found[name] != "none", name
    assert found["bodyPart"].split()[1] == "33"                # the whole call, replaced by no-ops
    for name in ("nif", "kf"):                                 # jz rel32 -> jmp rel32 + nop
        b = found[name].split()[2:]
        assert b[0] == "E9" and b[5] == "90" and len(b) == 6
    assert found["texture"].split()[2] == "EB"                 # jz short -> jmp short


def test_known_addresses_on_the_build_they_were_taken_from():
    if not _build_the_addresses_came_from():
        pytest.skip("another Morrowind.exe build")
    found = _find()
    assert found["bodyPart"] == "0x4A1B02 33"
    assert found["texture"] == "0x483DF6 2 EB 48"
    assert found["nif"] == "0x4EDE64 6 E9 D3 00 00 00 90"
    assert found["kf"] == "0x4EDF44 6 E9 F4 00 00 00 90"


def test_code_another_patcher_changed_is_left_alone():
    found = _find("break")                                     # every jz rel32 turned into jnz
    assert found["nif"] == "none" and found["kf"] == "none"
