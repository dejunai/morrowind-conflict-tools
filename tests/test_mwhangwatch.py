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
    step = SRC[SRC.index("local function stepNowPlaying()"):SRC.index("local function stopNowTimer()")]
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


def test_turning_the_watch_off_unregisters_and_unwraps_everything(tmp_path):
    luajit = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
    if not os.path.isfile(luajit):
        pytest.skip("LuaJIT not available")
    (tmp_path / "Data Files" / "MWSE" / "logs").mkdir(parents=True)
    mods = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite").replace("\\", "/")
    script = r'''
package.path = MODS .. "/?.lua;" .. package.path
-- a small copy of MWSE's core\lib\event.lua: the same local tables mwhangwatch reaches through the debug library
local generalEvents, filteredEvents, eventPriorities, doOnceCallbacks = {}, {}, {}, {}
local function getEventTable(name, filter)
  if filter ~= nil then
    filteredEvents[name] = filteredEvents[name] or {}
    filteredEvents[name][filter] = filteredEvents[name][filter] or {}
    return filteredEvents[name][filter]
  end
  generalEvents[name] = generalEvents[name] or {}
  return generalEvents[name]
end
local function find(t, fn) for i, f in ipairs(t) do if f == fn then return i end end end
local function register(name, fn, opts)
  local _ = doOnceCallbacks
  local t = getEventTable(name, opts and opts.filter)
  if find(t, fn) then return end
  t[#t + 1] = fn
  eventPriorities[fn] = opts and opts.priority or 0
end
local function unregister(name, fn, opts)
  local t = getEventTable(name, opts and opts.filter)
  local i = find(t, fn)
  if i then table.remove(t, i) end
end
local function isRegistered(name, fn, opts) return find(getEventTable(name, opts and opts.filter), fn) ~= nil end
event = { register = register, unregister = unregister, isRegistered = isRegistered }
local cfg
mwse = { loadConfig = function(_, d) d.enabled = true; d.audio = true; cfg = d; return d end, buildNumber = 1 }
lfs = { mkdir = function() end }
timer = { real = 1, start = function() return { cancel = function() end } end }
tes3 = { event = setmetatable({}, { __index = function(_, k) return k end }) }
include = function(name) local ok, r = pcall(require, name) if ok then return r end return nil end
-- another mod's sound handler, there before the watch starts
local function otherMod(e) end
event.register("addSound", otherMod)
local before = {}
for name, t in pairs(generalEvents) do before[name] = #t end
require("mwhangwatch.main")
local applySettings = generalEvents.initialized[1]
applySettings()
assert(generalEvents.addSound[1] ~= otherMod or #generalEvents.addSound > 1, "audio watch did not start")
local wrapped = false
for _, f in ipairs(generalEvents.addSound) do if f ~= otherMod and eventPriorities[f] == 0 then wrapped = true end end
assert(wrapped, "the other mod's handler was not wrapped")
assert(event.register ~= register, "event.register not patched")
assert(#generalEvents.enterFrame >= 1 and #generalEvents.cellChanged >= 1, "watch handlers missing")
-- a mod unregisters its own function while it is wrapped: still works
event.unregister("addSound", otherMod)
event.register("addSound", otherMod)
-- off
cfg.enabled = false
applySettings()
assert(event.register == register and event.unregister == unregister and event.isRegistered == isRegistered,
  "event functions not put back")
for name, t in pairs(generalEvents) do
  local want = before[name] or 0
  if name == "initialized" or name == "loaded" or name == "modConfigReady" then want = #t end   -- its own setup
  assert(#t == want, name .. " still has " .. #t .. " handler(s), wanted " .. want)
end
assert(generalEvents.addSound[1] == otherMod, "the other mod's handler is still wrapped")
-- on again
cfg.enabled = true
applySettings()
assert(#generalEvents.enterFrame >= 1 and #generalEvents.addSound == 2, "not registered again: " .. #generalEvents.addSound)
cfg.audio = false
applySettings()
assert(#generalEvents.addSound == 1 and generalEvents.addSound[1] == otherMod, "audio off left handlers")
assert(#generalEvents.enterFrame >= 1, "the watch went off with the audio watch")
print("OK")
'''
    program = tmp_path / "onoff.lua"
    program.write_text(f"MODS = [[{mods}]]\n" + script, encoding="utf-8")
    result = subprocess.run([luajit, str(program)], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0 and result.stdout.strip().endswith("OK"), result.stdout + result.stderr
