"""mwpluginpatches' Graphic Herbalism respawn delay, run in LuaJIT with stub MWSE calls shaped like Graphic Herbalism's
own: its state in ref.data.GH (1 picked, 2 spoiled) and its "HerbalismSwitch" node with named children. The patch
looked for a node named "Switch" (so it never acted), overwrote "spoiled" with "picked", and noted a harvest day for
every organic container closed."""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
PATCHES = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwpluginpatches", "patches")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

SCRIPT = r"""
handlers, day = {}, 10
package.preload["mwpluginpatches.config"] = function() return { herbRespawnDays = 3 } end
tes3 = { objectType = { container = 2 }, getGlobal = function(name) return name == "DaysPassed" and day or 0 end }
mwse = { log = function() end }
event = { register = function(name, fn) handlers[name] = fn end }
local function herb(withSwitch)
  local switch = { switchIndex = 0, children = { 1, 2, 3 },
                   getChildIndexByName = function(_, n) return ({ NORMAL = 0, HARVESTED = 1, SPOILED = 2 })[n] or -1 end }
  local node = { appCulled = false, update = function() end,
                 getObjectByName = function(_, n) return withSwitch and n == "HerbalismSwitch" and switch or nil end }
  return { object = { objectType = 2, organic = true }, sceneNode = node, data = {}, isEmpty = false, switch = switch }
end
local function check(ok, what) if not ok then error(what, 2) end end
package.path = [[PATCHES\?.lua;]] .. package.path
local patch = require("graphicHerbalismRespawn")
patch.init()

local h = herb(true)
handlers.containerClosed({ reference = h })
check(h.data.GH_harvestDay == nil, "an ordinary close (not picked by Graphic Herbalism) notes no harvest day")
h.data.GH, h.isEmpty = 1, true                      -- Graphic Herbalism picks it, then fires containerClosed
handlers.containerClosed({ reference = h })
check(h.data.GH_harvestDay == 10, "the harvest day is noted")
day = 11; h.data.GH, h.isEmpty, h.switch.switchIndex = nil, false, 0     -- the engine restocks, GH resets it
handlers.referenceActivated({ reference = h })
check(h.isEmpty and h.data.GH == 1 and h.switch.switchIndex == 1, "still picked on day 11, HerbalismSwitch at HARVESTED")

local s = herb(true)
s.data.GH = 2
handlers.containerClosed({ reference = s })
day = 12; patch.enforce(s)
check(s.data.GH == 2 and s.switch.switchIndex == 2, "a spoiled herb stays spoiled")

local c = herb(false)
c.data.GH = 1; day = 12
handlers.containerClosed({ reference = c })
day = 14; patch.enforce(c)
check(c.sceneNode.appCulled == true, "a mesh without a HerbalismSwitch stays hidden while picked")

day = 13; patch.enforce(h)
check(not h.isEmpty and h.data.GH == nil and h.data.GH_harvestDay == nil and h.switch.switchIndex == 0,
      "after 3 days it grows back")
print("ok")
"""


def test_a_picked_herb_stays_picked_for_its_days_then_grows_back():
    out = subprocess.run([LUAJIT, "-"], input=SCRIPT.replace("PATCHES", PATCHES), capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stderr + out.stdout


def test_graphic_herbalism_mcm_defaults_and_bounds():
    mcm = open(os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwpluginpatches", "mcm.lua"),
               encoding="utf-8").read()
    config = open(os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwpluginpatches", "config.lua"),
                  encoding="utf-8").read()
    assert 'label = "Harvested Flora Respawn Delay (Days)"' in mcm
    assert "min = 1" in mcm and "max = 90" in mcm
    assert "herbRespawnDays = 3" in config


def test_graphic_herbalism_active_detection_is_plugin_based():
    config = open(os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwpluginpatches", "config.lua"),
                  encoding="utf-8").read()
    start = config.index("function config.isGraphicHerbalismActive()")
    end = config.index("\nend", start) + len("\nend")
    function = config[start:end]
    assert 'tes3.isModActive("Graphic Herbalism.esp")' in function
    assert 'tes3.isModActive("Graphic Herbalism Extra.esp")' in function
