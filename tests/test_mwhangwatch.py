"""mwhangwatch: one memory warning level everywhere, and the now-playing scan builds no table per check."""
import os
import re
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwhangwatch", "main.lua"), encoding="utf-8").read()


def test_memory_level_is_the_same_in_the_header_default_and_fallback():
    header = re.search(r"it is (\d+)% used", SRC).group(1)
    default = re.search(r"memLimit\s*=\s*(\d+)", SRC).group(1)
    fallback = re.search(r"config\.memLimit or (\d+)", SRC).group(1)
    assert header == default == fallback, (header, default, fallback)


def test_now_playing_scan_reuses_one_params_table():
    step = SRC[SRC.index("local function stepNowPlaying()"):SRC.index("onNowScanFrame = function()")]
    assert "getSoundPlaying, {" not in step and "pcall(tes3.getSoundPlaying, q)" in step


def test_audio_watch_skips_details_beyond_line_limit(tmp_path):
    luajit = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
    if not os.path.isfile(luajit):
        pytest.skip("LuaJIT not available")
    (tmp_path / "Data Files" / "MWSE" / "logs").mkdir(parents=True)
    mods = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite").replace("\\", "/")
    script = r'''
package.path = MODS .. "/?.lua;" .. package.path
local handlers = {}
event = { register = function(name, fn) handlers[name] = fn end, unregister = function() end }
mwse = { loadConfig = function(_, d) d.enabled = true; d.audio = true; d.soundLines = 1; return d end }
lfs = { mkdir = function() end }
timer = { real = 1, start = function() return { cancel = function() end } end }
tes3 = { event = setmetatable({}, { __index = function(_, k) return k end }) }
-- MWSE include: require, or nil when the module is missing; other load errors still raise.
include = function(name)
  local ok, result = pcall(require, name)
  if ok then return result end
  if type(result) == "string" and result:find("module '" .. name .. "' not found", 1, true) then
    return nil
  end
  error(result)
end
require("mwhangwatch.main")
handlers.initialized()
local reads = 0
local e = setmetatable({ sound = { id = "bell" } }, {
  __index = function(_, k)
    if k == "volume" then reads = reads + 1; return 0.5 end
  end,
})
for _ = 1, 1000 do handlers.addSound(e) end
local tally
for i = 1, 20 do
  local name, value = debug.getupvalue(handlers.addSound, i)
  if not name then break end
  if name == "soundTally" then tally = value end
end
assert(tally and tally.bell == 1000, "sound tally changed")
assert(reads == 1, "detailed sound fields read after line limit: " .. reads)
print("OK")
'''
    program = tmp_path / "watch.lua"
    program.write_text(f"MODS = [[{mods}]]\n" + script, encoding="utf-8")
    result = subprocess.run([luajit, str(program)], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0 and result.stdout.strip().endswith("OK"), result.stdout + result.stderr
    log = (tmp_path / "Data Files" / "MWSE" / "logs" / "mwhangwatch.log").read_text()
    assert log.count("sound: ref  bell") == 1
