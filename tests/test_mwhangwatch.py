"""mwhangwatch: one memory warning level everywhere, and the now-playing scan builds no table per check."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(ROOT, "Data Files", "MWSE", "mods", "mwsuite", "mwhangwatch", "main.lua"), encoding="utf-8").read()


def test_memory_level_is_the_same_in_the_header_default_and_fallback():
    header = re.search(r"it is (\d+)% used", SRC).group(1)
    default = re.search(r"memLimit\s*=\s*(\d+)", SRC).group(1)
    fallback = re.search(r"config\.memLimit or (\d+)", SRC).group(1)
    assert header == default == fallback, (header, default, fallback)


def test_now_playing_scan_reuses_one_params_table():
    step = SRC[SRC.index("local function stepNowPlaying()"):SRC.index("onNowScanFrame = function()")]
    assert "getSoundPlaying, {" not in step and "pcall(tes3.getSoundPlaying, q)" in step
