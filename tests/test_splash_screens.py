"""Tidy's splash rule: the game shows only TGA splashes from the top of Splash\\ (a DDS-only Splash folder showed none;
subfolders are never picked). Every splash becomes at most 1024 wide, 24-bit unless it has alpha, RLE when smaller,
the original kept in the mod's Off\\splash screens\\. A non-TGA at the top is converted, unless the mod has MWSE code
that may load it by name; one in a subfolder is only a mod's own, and is left alone."""
import os
import shutil
import struct
import subprocess

import pytest

from conftest import m

import mwdialog_assets as ah

GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXCONV = os.path.join(GAME, "texconv.exe")
pytestmark = pytest.mark.skipif(not os.path.isfile(TEXCONV), reason="texconv.exe not available")


def tga(path, w, h, bpp=3):
    path.parent.mkdir(parents=True, exist_ok=True)
    pixel = bytes([40, 80, 120, 255][:bpp])
    head = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, w, h, bpp * 8, 8 if bpp == 4 else 0)
    path.write_bytes(head + pixel * (w * h))


def size_of(path):
    data = path.read_bytes()
    return struct.unpack_from("<HH", data, 12) + (data[16], data[2])


@pytest.fixture
def game(tmp_path):
    shutil.copy2(TEXCONV, tmp_path / "texconv.exe")
    (tmp_path / "Data Files").mkdir()
    return tmp_path


def dds_from(tga_path, out_dir):
    subprocess.run([str(TEXCONV), "-nologo", "-y", "-ft", "dds", "-f", "BC1_UNORM", "-m", "1", "-o", str(out_dir),
                    str(tga_path)], check=True, capture_output=True)
    tga_path.unlink()


def test_wide_and_non_tga_splashes_become_1024_wide_rle_tga_with_the_original_in_off(game):
    mod = game / "staging" / "Splash Pack"
    tga(mod / "Splash" / "wide.tga", 2048, 8)
    tga(mod / "Splash" / "fine.tga", 1024, 8)
    tga(mod / "Splash" / "pic.tga", 2048, 8)
    dds_from(mod / "Splash" / "pic.tga", mod / "Splash")
    tga(mod / "Splash" / "regional" / "mine.tga", 64, 8)
    dds_from(mod / "Splash" / "regional" / "mine.tga", mod / "Splash" / "regional")
    issues, fixes = ah.check_folder(str(mod), m, str(game / "Data Files"))
    splash = sorted(rel.replace("\\", "/") for kind, _f, rel, _j in fixes if kind == "splash")
    assert splash == ["Splash/pic.dds", "Splash/wide.tga"], issues
    done, skipped = ah.apply_folder(str(mod), [f for f in fixes if f[0] == "splash"], m, str(game), "Splash Pack")
    assert (done, skipped) == (2, [])
    assert size_of(mod / "Splash" / "wide.tga")[:3] == (1024, 4, 24)
    assert size_of(mod / "Splash" / "pic.tga")[:3] == (1024, 4, 24)
    assert not (mod / "Splash" / "pic.dds").exists()
    assert size_of(mod / "Splash" / "fine.tga") == (1024, 8, 24, 2)          # already small enough: untouched
    assert (mod / "Splash" / "regional" / "mine.dds").exists()              # a subfolder: a mod's own
    kept = sorted(p.name for p in (mod / "Off").rglob("*") if p.is_file() and not p.name.endswith(".sha256"))
    assert kept == ["pic.dds", "wide.tga"]
    _issues, again = ah.check_folder(str(mod), m, str(game / "Data Files"))
    assert not [f for f in again if f[0] == "splash"]                       # nothing left to do


def test_a_mod_with_mwse_code_keeps_its_dds_splash(game):
    mod = game / "staging" / "Regional Splash"
    (mod / "MWSE" / "mods" / "RegionalSplash").mkdir(parents=True)
    (mod / "MWSE" / "mods" / "RegionalSplash" / "main.lua").write_text("return {}\n")
    tga(mod / "Splash" / "Morrowind.tga", 64, 8)
    dds_from(mod / "Splash" / "Morrowind.tga", mod / "Splash")
    issues, fixes = ah.check_folder(str(mod), m, str(game / "Data Files"))
    assert not [f for f in fixes if f[0] == "splash"]
    assert any("MWSE code may load it by name" in msg for _s, _r, msg in issues)
