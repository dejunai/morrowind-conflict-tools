"""mwpluginpatches' Lua runs of known plugin sound scripts the engine restarts every frame: run in LuaJIT with
stub MWSE calls in which the engine always says "not playing" (the case mwsoundguard logs as RUNAWAY)."""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.path.join(ROOT, "tools", "luajit", "luajit.exe")
PATCHES = os.path.join(ROOT, "Data Files", "MWSE", "mods", "mwsuite", "mwpluginpatches", "patches")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

STUBS = r"""
plays, removes, created, overrides, handlers = {}, {}, {}, {}, {}
hour, weatherIndex = 12, 0
tes3 = {
  event = { referenceDeactivated = "referenceDeactivated" },
  getScript = function() return {} end,
  getSoundPlaying = function() return false end,                 -- the engine's wrong answer
  playSound = function(p) plays[#plays + 1] = p.reference.id .. ":" .. p.sound .. (p.loop and ":loop" or "") end,
  removeSound = function(p) removes[#removes + 1] = p.reference.id .. ":" .. p.sound end,
  createReference = function(p) created[#created + 1] = p.object .. "@" .. p.position[3] end,
  getCurrentWeather = function() return { index = weatherIndex } end,
  worldController = { hour = setmetatable({}, { __index = function() return hour end }) },
}
mwse = { overrideScript = function(id, fn) overrides[id] = fn end, log = function() end }
event = { register = function(name, fn) handlers[name] = fn end }
math.randomseed(1)
function ref(id, cell)
  return { id = id, cell = cell, position = { x = 1, y = 2, z = 3 }, context = {},
           orientation = { x = 0, y = 0, z = 0 }, startingOrientation = { x = 0, y = 0, z = 0 } }
end
function frames(script, r, n) for _ = 1, n do overrides[script]({ reference = r, delta = 1 / 60 }) end end
function check(ok, what) if not ok then error(what, 2) end end
"""


def run(body):
    script = STUBS + "\npackage.path = [[" + PATCHES + "\\?.lua;]] .. package.path\n" + body + "\nprint('ok')\n"
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stderr + out.stdout


def test_cave_drip_starts_its_loop_once_and_places_visuals_once():
    run(r"""
require("caveDripSound").init()
local wet = ref("drip1", { waterLevel = 50 })
frames("R0_Sound_Cave_Drip_scr", wet, 300)
check(#plays == 1 and plays[1] == "drip1:Cave Drip:loop", "one loop, got " .. #plays)
check(#created == 2 and created[1] == "R0_Sound_Cave_Drip_vis@50" and created[2] == "R0_Sound_Cave_Drip_dmy@50",
      "visuals at the water level once")
check(wet.context.visset == 1, "visset kept in the script's own variable")
local dry = ref("drip2", { waterLevel = nil })
frames("R0_Sound_Cave_Drip_scr", dry, 10)
check(#plays == 2 and created[3] == "R0_Sound_Cave_Drip_vis@3" and #created == 3, "no water: PlaceAtMe")
handlers.referenceDeactivated({ reference = wet })               -- unloaded: the engine stopped it
frames("R0_Sound_Cave_Drip_scr", wet, 5)
check(#plays == 3 and #created == 3, "starts again after a reload, visuals not placed twice")
""")


def test_swamp_keeps_one_loop_and_switches_with_day_night_and_weather():
    run(r"""
require("swampSound").init()
local s = ref("swamp", { isInterior = false })
frames("SwampSoundScript", s, 300)
check(#plays == 1 and (plays[1] == "swamp:swamp 2:loop" or plays[1] == "swamp:swamp 3:loop"), "one day loop")
check(s.context.daytim == 1, "daytim set by day")
local day = plays[1]:match("swamp:(.-):loop")
hour = 22
frames("SwampSoundScript", s, 100)
check(#plays == 2 and plays[2]:find("swampNight", 1, true), "one night loop after dusk")
check(removes[1] == "swamp:" .. day, "the day loop it started was stopped")
hour = 3
frames("SwampSoundScript", s, 50)
check(#plays == 2 and s.context.daytim == 0, "before 6:00 daytim keeps its value, nothing new starts")
weatherIndex = 6
frames("SwampSoundScript", s, 20)
check(#plays == 2 and removes[#removes]:find("swampNight", 1, true), "bad weather stops the loop")
local inside = ref("cellar", { isInterior = true })
frames("SwampSoundScript", inside, 20)
check(#plays == 2, "nothing indoors")
""")


def test_expanded_sounds_keeps_one_loop_and_preserves_float_rocking():
    run(r"""
require("expandedSounds").init()
local boat = ref("rowboat", {})
frames("Float", boat, 30)
check(#plays == 1 and plays[1] == "rowboat:plx_ES_Water:loop", "one water loop")
check(boat.orientation.x > 0 and boat.context.swingTime == 1, "Float still rocks the boat")
frames("Float", boat, 211)
check(#plays == 1 and math.abs(boat.orientation.x) < 0.000001 and boat.context.timer == 0,
      "Float completes and resets its four-second rocking cycle")
local creak = ref("creak", {})
frames("Sound_Boat_Creak", creak, 300)
check(#plays == 2 and plays[2] == "creak:Boat Creak:loop", "one boat-creak loop")
handlers.referenceDeactivated({ reference = boat })
frames("Float", boat, 1)
check(#plays == 3, "water loop restarts after the source reloads")
""")
