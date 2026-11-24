"""Tidy's splash rule: the game shows only TGA splashes from the top of Splash\\ (a DDS-only Splash folder showed none;
subfolders are never picked). Wider than 2048 is cut to 2048 (1024 lost too much detail); a loading screen has no use
for alpha, so every splash is 24-bit; one at most 2048 wide is only re-encoded (same pixels) when that saves at least
10%. The original is kept in the mod's Off\\splash screens\\. A non-TGA at the top is converted, unless the mod has
MWSE code that may load it by name; one in a subfolder is only a mod's own, and is left alone."""
import os
import random
import shutil
import struct
import subprocess

import pytest

from conftest import m

import mwdialog_assets as ah

GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXCONV = os.path.join(GAME, "tools", "texconv.exe")
pytestmark = pytest.mark.skipif(not os.path.isfile(TEXCONV), reason="texconv.exe not available")


def tga(path, w, h, bpp=3, noisy=False):
    """An uncompressed TGA: one colour, or varied pixels RLE can't shrink."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if noisy:
        rnd = random.Random(w * h * bpp)
        pixels = b"".join(bytes(rnd.randrange(256) for _ in range(3)) + (b"\x80" if bpp == 4 else b"")
                          for _ in range(w * h))
    else:
        pixels = bytes([40, 80, 120, 255][:bpp]) * (w * h)
    head = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, w, h, bpp * 8, 8 if bpp == 4 else 0)
    path.write_bytes(head + pixels)


def header(path):
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


def test_splashes_are_capped_at_2048_made_24_bit_and_kept_in_off(game):
    mod = game / "staging" / "Splash Pack"
    tga(mod / "Splash" / "huge.tga", 4096, 8)
    tga(mod / "Splash" / "alpha.tga", 2048, 8, bpp=4, noisy=True)       # same pixels, 24-bit: 25% smaller
    tga(mod / "Splash" / "fine.tga", 1024, 8, noisy=True)               # 24-bit, RLE can't help: left alone
    tga(mod / "Splash" / "pic.tga", 64, 8)
    dds_from(mod / "Splash" / "pic.tga", mod / "Splash")
    tga(mod / "Splash" / "regional" / "mine.tga", 64, 8)
    dds_from(mod / "Splash" / "regional" / "mine.tga", mod / "Splash" / "regional")
    before = ah._tga_read((mod / "Splash" / "alpha.tga").read_bytes())[3]
    issues, fixes = ah.check_folder(str(mod), m, str(game / "Data Files"))
    splash = sorted(rel.replace("\\", "/") for kind, _f, rel, _j in fixes if kind == "splash")
    assert splash == ["Splash/alpha.tga", "Splash/huge.tga", "Splash/pic.dds"], issues
    done, skipped = ah.apply_folder(str(mod), [f for f in fixes if f[0] == "splash"], m, str(game), "Splash Pack")
    assert (done, skipped) == (3, [])
    assert header(mod / "Splash" / "huge.tga")[:3] == (2048, 4, 24)
    assert header(mod / "Splash" / "alpha.tga")[:3] == (2048, 8, 24)
    after = ah._tga_read((mod / "Splash" / "alpha.tga").read_bytes())[3]
    assert [b"".join(r[i:i + 3] for i in range(0, len(r), 4)) for r in before] == after       # same colours
    assert header(mod / "Splash" / "pic.tga")[:3] == (64, 8, 24)
    assert not (mod / "Splash" / "pic.dds").exists()
    assert header(mod / "Splash" / "fine.tga") == (1024, 8, 24, 2)
    assert (mod / "Splash" / "regional" / "mine.dds").exists()              # a subfolder: a mod's own
    kept = sorted(p.name for p in (mod / "Off").rglob("*") if p.is_file() and not p.name.endswith(".sha256"))
    assert kept == ["alpha.tga", "huge.tga", "pic.dds"]
    _issues, again = ah.check_folder(str(mod), m, str(game / "Data Files"))
    assert not [f for f in again if f[0] == "splash"]                       # nothing left to do


def test_uncapped_splash_keeps_its_width_but_loses_alpha_and_cache_follows_the_rule(game, monkeypatch):
    mod = game / "staging" / "Wide Splash"
    tga(mod / "Splash" / "huge.tga", 4096, 8, noisy=True)
    tga(mod / "Splash" / "alpha.tga", 1024, 8, bpp=4, noisy=True)
    monkeypatch.setattr(ah, "SPLASH_MAX_WIDTH", None)
    _issues, fixes = ah.check_folder(str(mod), m, str(game / "Data Files"))
    assert sorted(rel.replace("\\", "/") for kind, _f, rel, _j in fixes if kind == "splash") == ["Splash/alpha.tga"]
    monkeypatch.setattr(ah, "SPLASH_MAX_WIDTH", 2048)
    _issues, fixes = ah.check_folder(str(mod), m, str(game / "Data Files"))
    assert "Splash/huge.tga" in [rel.replace("\\", "/") for kind, _f, rel, _j in fixes if kind == "splash"]


def test_a_mod_with_mwse_code_keeps_its_dds_splash(game):
    mod = game / "staging" / "Example Splash"
    (mod / "MWSE" / "mods" / "ExampleSplash").mkdir(parents=True)
    (mod / "MWSE" / "mods" / "ExampleSplash" / "main.lua").write_text("return {}\n")
    tga(mod / "Splash" / "Morrowind.tga", 64, 8)
    dds_from(mod / "Splash" / "Morrowind.tga", mod / "Splash")
    issues, fixes = ah.check_folder(str(mod), m, str(game / "Data Files"))
    assert not [f for f in fixes if f[0] == "splash"]
    assert any("MWSE code may load it by name" in msg for _s, _r, msg in issues)

def test_no_reduce_flags_turn_off_both_size_limits(monkeypatch):
    monkeypatch.setattr(m, "TEXTURE_MAX_EDGE", 2048)
    monkeypatch.setattr(ah, "SPLASH_MAX_WIDTH", 2048)
    monkeypatch.setattr(m.MP, "default_data_dir", lambda: None)
    with pytest.raises(SystemExit):                     # stops at "no Data Files given", after the flags apply
        m._main(["--no-reduce-textures", "--no-reduce-splash"])
    assert m.TEXTURE_MAX_EDGE > 1 << 20 and ah.SPLASH_MAX_WIDTH is None
