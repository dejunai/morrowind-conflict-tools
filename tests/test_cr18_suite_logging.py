"""CR-18: mwsoundguard names the Lua caller and the object behind a numeric id, and can watch actor loops (log
only); mwhangwatch's memory warning is opt-in, a toast instead of a modal, and leaves one line in MWSE.log;
mwsaveguard says when another mod swallowed a save, and drops the leftover logToMWSE key. LuaJIT, stub MWSE."""
import os
import re
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MODS = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite").replace("\\", "/")
need_lua = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")


def src(*parts):
    return open(os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", *parts), encoding="utf-8").read()


def run(tmp_path, script):
    (tmp_path / "Data Files" / "MWSE" / "logs").mkdir(parents=True, exist_ok=True)
    program = tmp_path / "t.lua"
    program.write_text(f"MODS = [[{MODS}]]\n" + script, encoding="utf-8")
    r = subprocess.run([LUAJIT, str(program)], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip().endswith("OK"), r.stdout + r.stderr
    return r.stdout


def own_log(tmp_path, name):
    for p in (tmp_path / "Data Files" / "MWSE" / "logs" / name, tmp_path / ("Data Files\\MWSE\\logs\\" + name)):
        if p.exists():                               # the Lua writes a Windows path: one file name elsewhere
            return p.read_text(encoding="utf-8", errors="replace")
    return ""


# ------------------------------------------------------------------------------------------------ mwsoundguard
SOUNDGUARD = r'''
os.clock = (function() local t = 0 return function() t = t + 0.01 return t end end)()
local function userdata(fields)
  local v = newproxy(true)
  getmetatable(v).__index = fields
  return v
end
handlers = {}
local enginePlays = 0
tes3 = { objectType = { npc = 1, creature = 2, light = 3 },
  event = { initialized = "initialized", loaded = "loaded", modConfigReady = "modConfigReady", addSound = "addSound",
            addTempSound = "addTempSound", referenceDeactivated = "referenceDeactivated" },
  getSoundPlaying = function() return false end }
-- the engine: tes3.playSound raises addSound, and plays unless a handler blocks it
tes3.playSound = function(p)
  local e = { reference = p.reference, sound = p.sound, pitch = 1, flags = p.loop and 1 or 0 }
  for _, fn in ipairs(handlers.addSound or {}) do fn(e) end
  if not e.block then enginePlays = enginePlays + 1 end
  return not e.block
end
tes3.removeSound = function() return true end
mwse = { loadConfig = function(name, d) if name == "mwsoundguard" then d.enabled = true d.watchActors = WATCH end
                                        return name == "mwsoundguard" and d or nil end,
         log = function() end }
lfs = { attributes = function() return nil end, mkdir = function() end }
event = { register = function(name, fn) handlers[name] = handlers[name] or {} table.insert(handlers[name], fn) end,
          unregister = function() end }
timer = { real = 1, start = function() return { cancel = function() end } end }
local guard = dofile(MODS .. "/mwsoundguard/main.lua")
for _, fn in ipairs(handlers.initialized) do fn() end
local sound = userdata({ id = "Fire 40", filename = "Fx\\envrn\\fire.wav" })
local lightObj = userdata({ id = "1399197442720713248", objectType = 3, mesh = "l\\light_tikitorch00.nif",
                            name = "Tiki Torch", sourceMod = "Morrowind.esm", sound = sound })
local torch = userdata({ id = "1399197442720713248", object = lightObj,
                         baseObject = userdata({ id = "light_tikitorch00" }), cell = userdata({ id = "Seyda Neen" }) })
-- another mod's code, as MWSE loads it
local mod = load("return function(ref, snd) for _ = 1, 12 do tes3.playSound({ reference = ref, sound = snd, loop = true }) end end",
                 "@Data Files\\MWSE\\mods\\othermod\\main.lua")()
mod(torch, sound)
'''


@need_lua
def test_soundguard_names_the_lua_caller_and_the_object_behind_a_numeric_id(tmp_path):
    run(tmp_path, "WATCH = false\n" + SOUNDGUARD + r'''
assert(enginePlays == 1, "one copy kept, got " .. enginePlays)
guard.summary()
print("OK")
''')
    log = own_log(tmp_path, "mwsoundguard.log")
    assert "RUNAWAY loop: Fire 40" in log
    assert "mesh l\\light_tikitorch00.nif" in log and "name Tiki Torch" in log and "base light_tikitorch00" in log
    assert "from Morrowind.esm" in log
    assert re.search(r"started by: Lua othermod\\main\.lua:1", log), log
    assert "this IS the object's own sound" in log


@need_lua
def test_soundguard_actor_watch_logs_restarts_but_never_blocks(tmp_path):
    run(tmp_path, "WATCH = true\n" + SOUNDGUARD + r'''
local corpse = userdata({ id = "corpse", object = userdata({ id = "ancestor_ghost", objectType = 2 }),
                          cell = userdata({ id = "Ashinabi" }) })
local flies = userdata({ id = "Flies", filename = "Fx\\flies.wav" })
local before = enginePlays
mod(corpse, flies)
assert(enginePlays - before == 12, "actor sounds must never be blocked")
print("OK")
''')
    log = own_log(tmp_path, "mwsoundguard.log")
    assert "actor loop restarted (not blocked): Flies on corpse" in log
    assert "Lua othermod\\main.lua:1" in log


def test_soundguard_wraps_play_and_remove_without_pcall_between_caller_and_getinfo():
    s = src("mwsoundguard", "main.lua")
    assert 'debug.getinfo(3, "Sl")' in s and "tes3.playSound = function" in s and "tes3.removeSound = function" in s
    assert "pcall(callerOf" not in s
    for key in ("attributeCallers = true", "watchActors = false"):
        assert key in s


# ------------------------------------------------------------------------------------------------ mwhangwatch
HANGWATCH = r'''
package.path = MODS .. "/?.lua;" .. package.path
handlers, timers, boxes, logged = {}, {}, {}, {}
event = { register = function(name, fn) handlers[name] = fn end, unregister = function() end }
mwse = { loadConfig = function(_, d) if SAVED ~= nil then d.memWarn = SAVED d.memLimit = 80 end return d end,
         log = function(fmt, ...) logged[#logged + 1] = string.format(fmt, ...) end,
         saveConfig = function() end }
lfs = { mkdir = function() end }
timer = { real = 1, start = function(p) timers[#timers + 1] = p return { cancel = function() end } end }
tes3 = { event = setmetatable({}, { __index = function(_, k) return k end }),
         messageBox = function(p) boxes[#boxes + 1] = p end, playSound = function() end,
         getActiveCells = function() return {} end }
tes3ui = { menuMode = function() return false end,
           enterMenuMode = function() error("the memory warning must not enter menu mode") end }
include = function(name)
  if name == "mwguard.interop" then return { addressSpace = function() return 3930 end } end
  local ok, r = pcall(require, name) if ok then return r end
end
require("mwhangwatch.main")
'''


@need_lua
def test_hangwatch_memory_warning_is_opt_in(tmp_path):
    run(tmp_path, "SAVED = nil\n" + HANGWATCH + r'''
assert(#timers == 0, "no memory timer without an explicit opt-in")
print("OK")
''')
    assert "memWarn    = false" in src("mwhangwatch", "main.lua")


@need_lua
def test_hangwatch_memory_warning_is_a_toast_and_one_mwse_log_line(tmp_path):
    run(tmp_path, "SAVED = true\n" + HANGWATCH + r'''
assert(#timers == 1, "the saved opt-in starts the memory timer")
timers[1].callback()
assert(#boxes == 1, "one notice")
local b = boxes[1]
assert(type(b) == "table" and b.buttons == nil and b.callback == nil, "a toast has no buttons")
assert(b.message:find("memory at 96%%"), b.message)
local hits = 0
for _, l in ipairs(logged) do if l:find("^%[mwhangwatch%] MEMORY WARNING: 96%% used") then hits = hits + 1 end end
assert(hits == 1, "one line in MWSE.log")
print("OK")
''')
    assert "MEMORY WARNING" in own_log(tmp_path, "mwhangwatch.log")


def test_hangwatch_mcm_says_what_off_means_and_never_turns_the_watch_on():
    s = src("mwhangwatch", "main.lua")
    assert "Off: the mod does nothing" not in s
    assert not re.search(r"config\.enabled\s*=\s*true", s)
    memwarning = s[s.index("local function memWarning"):s.index("local function memCheck")]
    assert "buttons =" not in memwarning and "enterMenuMode" not in memwarning


# ------------------------------------------------------------------------------------------------ mwsaveguard
SAVEGUARD = r'''
package.path = MODS .. "/?.lua;" .. MODS .. "/?/init.lua;" .. package.path
local function stub()
  return setmetatable({}, { __index = function() return stub() end, __call = function() return nil end })
end
logged, saved = {}, {}
-- MWSE's core\lib\event.lua, as far as this needs: handlers by priority, stopped at the first false
local generalEvents, eventPriorities = {}, {}
local function getEventTable(name) generalEvents[name] = generalEvents[name] or {} return generalEvents[name] end
event = {}
function event.register(name, cb, opts)
  local t = getEventTable(name)
  eventPriorities[cb] = opts and opts.priority or 0
  table.insert(t, cb)
  table.sort(t, function(a, b) return eventPriorities[a] > eventPriorities[b] end)
end
function event.trigger(name, e)
  for _, cb in ipairs(getEventTable(name)) do
    if cb(e) == false then e.block = true return e end
    if e.claim then return e end
  end
  return e
end
frameTimers = {}
CLOCK = 0
os.clock = function() return CLOCK end
mwse = { loadConfig = function(_, d) local c = {} for k, v in pairs(d) do c[k] = v end c.enabled = true
                                     c.logToMWSE = true return c end,
         saveConfig = function(name, c) saved[#saved + 1] = c end,
         log = function(fmt, ...) logged[#logged + 1] = string.format(fmt, ...) end, mcm = stub() }
local none = { player = true, dataHandler = true, mobilePlayer = true }
tes3 = setmetatable({}, { __index = function(_, k) if none[k] then return nil end return stub() end })
tes3ui = { menuMode = function() return false end }
lfs = { mkdir = function() end }
timer = { real = 1, delayOneFrame = function(fn, kind) frameTimers[#frameTimers + 1] = { fn = fn, kind = kind } end,
          start = function() return { cancel = function() end } end }
dofile(MODS .. "/mwsaveguard/main.lua")
local function nextFrame() local t = frameTimers frameTimers = {} for _, x in ipairs(t) do x.fn() end end
CLOCK = 100                             -- well past the settling window
'''


@need_lua
def test_saveguard_names_the_handlers_when_another_mod_swallows_a_save(tmp_path):
    run(tmp_path, SAVEGUARD + r'''
assert(#saved == 1 and saved[1].logToMWSE == nil, "the leftover logToMWSE key is dropped once")
-- a save nobody blocks: no complaint
event.trigger("save", { filename = "quiksave", name = "Quicksave" })
assert(#frameTimers == 1, "a save it lets through is watched")
nextFrame()
for _, l in ipairs(logged) do assert(not l:find("swallowed"), l) end
-- WBSR's saveBlock, compressed by luafix G1 to below mwsaveguard's own handler
local saveBlock = load("return function() return false end", "@Data Files\\MWSE\\mods\\abot\\WBSR\\main.lua")()
event.register("save", saveBlock, { priority = 9147 })
event.trigger("save", { filename = "quiksave", name = "Quicksave" })
assert(frameTimers[1] and frameTimers[1].kind == timer.real, "checked on a real-time frame (menus pause simulate)")
nextFrame()
local hit
for _, l in ipairs(logged) do if l:find("swallowed by another mod") then hit = l end end
assert(hit and hit:find("abot\\WBSR\\main.lua:1 (priority 9147)", 1, true), tostring(hit))
print("OK")
''')
    assert "Save swallowed by another mod" in own_log(tmp_path, "mwsaveguard.log")


# ---------------------------------------------------------------------------- mwsaveguard.wbsr_bard (CR-17)
WBSR_SETUP = r'''
function event.unregister(name, cb)
  local t = getEventTable(name)
  for i = #t, 1, -1 do if t[i] == cb then table.remove(t, i) end end
end
function event.isRegistered(name, cb)
  for _, x in ipairs(getEventTable(name)) do if x == cb then return true end end
  return false
end
local realLoad = mwse.loadConfig
mwse.loadConfig = function(name, d) if name == "abotWBSR" then return WBSR_CFG end return realLoad(name, d) end
lfs.attributes = function(p) if WBSR_FILE and p:find("abot\\WBSR\\main.lua", 1, true) then return { mode = "file" } end end
-- WBSR as far as this needs (its addTempSoundHP is lowered to 9130 by mwdialog_luafix G1, as in the game)
if WBSR_FILE then
  WBSR = load([[
local voiceoverRef
local function saveBlock() return false end
local function addTempSoundHP(e)
  if voiceoverRef or not e.path:lower():find("^vo[\\/]") then return end
  voiceoverRef = e.reference
  if not event.isRegistered("save", saveBlock) then event.register("save", saveBlock, { priority = 9147 }) end
end
event.register("modConfigReady", function() end)
event.register("loaded", function() event.register("addTempSound", addTempSoundHP, { priority = 9130 }) end)
return { done = function() voiceoverRef = nil event.unregister("save", saveBlock) end,
         blocking = function() return event.isRegistered("save", saveBlock) end }
]], "@Data Files\\MWSE\\mods\\abot\\WBSR\\main.lua")()
end
'''


def wbsr_harness(file=True, cfg="nil"):
    pre = f"WBSR_FILE = {'true' if file else 'false'}\nWBSR_CFG = {cfg}\n"
    return pre + SAVEGUARD.replace('dofile(MODS .. "/mwsaveguard/main.lua")',
                                   WBSR_SETUP + 'dofile(MODS .. "/mwsaveguard/main.lua")\n'
                                   'BARD = package.loaded["mwsaveguard.wbsr_bard"]\n'
                                   'event.trigger("initialized", {})\nevent.trigger("loaded", {})\n')


@need_lua
def test_wbsr_bard_lets_saves_through_while_a_bard_sings_but_not_for_a_speech(tmp_path):
    run(tmp_path, wbsr_harness() + r'''
assert(BARD and BARD.present() and BARD.enabled(), "on by default with WBSR there")
assert(BARD.stats().bookends == 9130, "placed around WBSR's own addTempSound handler")
local raflod = { id = "raflod the braggart00000000", object = { name = "Raflod the Braggart", id = "raflod the braggart" } }
-- a bard song: WBSR takes it as its voiceover and blocks saving; the block is lifted at once
event.trigger("addTempSound", { path = "Vo\\Bard\\Red Diamond.mp3", reference = raflod, isVoiceover = true })
assert(not WBSR.blocking(), "WBSR's save block is lifted for a bard song")
event.trigger("save", { filename = "quiksave", name = "Quicksave" })
nextFrame()
for _, l in ipairs(logged) do assert(not l:find("swallowed"), l) end
-- the next song (WBSR still holds the first as its voiceover: nothing new to lift)
event.trigger("addTempSound", { path = "Vo\\Bard\\Stagger Sway.mp3", reference = raflod, isVoiceover = true })
assert(not WBSR.blocking())
-- a real speech keeps its block
WBSR.done()
event.trigger("addTempSound", { path = "Vo\\D\\m\\Azura speech.mp3", reference = { object = { id = "azura" } } })
assert(WBSR.blocking(), "a speech still blocks saving")
-- a bard song while that speech holds WBSR's voiceover lifts nothing
event.trigger("addTempSound", { path = "Vo\\Bard\\Red Diamond.mp3", reference = raflod, isVoiceover = true })
assert(WBSR.blocking(), "the speech's block stays")
print("OK")
''')
    log = own_log(tmp_path, "mwsaveguard.log")
    assert log.count("Released WBSR's save block for a bard song: Raflod the Braggart") == 1
    assert "Vo\\Bard\\Red Diamond.mp3" in log


@need_lua
def test_wbsr_bard_switched_off_leaves_the_block_to_wbsr(tmp_path):
    out = run(tmp_path, wbsr_harness().replace("c.logToMWSE = true", "c.logToMWSE = true c.letBardSongsSave = false")
              + r'''
assert(BARD.present() and not BARD.enabled())
assert(BARD.stats().bookends == nil, "nothing registered while switched off")
event.trigger("addTempSound", { path = "Vo\\Bard\\Red Diamond.mp3", reference = {}, isVoiceover = true })
assert(WBSR.blocking(), "WBSR's block stays")
for _, l in ipairs(logged) do print(l) end
print("OK")
''')
    assert "left to WBSR" in out


@need_lua
def test_wbsr_bard_does_nothing_without_wbsr(tmp_path):
    out = run(tmp_path, wbsr_harness(file=False) + r'''
assert(BARD and not BARD.present() and not BARD.enabled())
assert(#getEventTable("addTempSound") == 0, "no addTempSound handler at all")
for _, l in ipairs(logged) do print(l) end
print("OK")
''')
    assert "wbsr_bard" not in out
