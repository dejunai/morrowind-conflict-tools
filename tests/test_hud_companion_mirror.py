"""mwpluginpatches' HUD Companion Health Bar mirror: its blacklist and mwcompanions' never-followers list (Excluded
Plugins, Blacklist, Whitelist) stay the same, each change carried over from the side it was made on. The real
mwcompanions core and the real patch, under LuaJIT, against HUD Companion Health Bar's config table as its own code
reads it."""
import os
import struct
import subprocess
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
SUITE = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")


def _plugin(game):
    os.makedirs(os.path.join(game, "Data Files"), exist_ok=True)
    name = b"ab01trout9\0"
    body = b"NAME" + struct.pack("<I", len(name)) + name
    with open(os.path.join(game, "Data Files", "abotWaterLife.esm"), "wb") as f:
        f.write(b"TES3" + struct.pack("<III", 0, 0, 0) + b"CREA" + struct.pack("<III", len(body), 0, 0) + body)


SCRIPT = r"""
local saved, logs = {}, {}
local function copy(t) if type(t) ~= "table" then return t end local o = {} for k, v in pairs(t) do o[k] = copy(v) end return o end
mwse = { loadConfig = function(name, defaults) return copy(saved[name]) or (defaults and copy(defaults)) end,
         saveConfig = function(name, t) saved[name] = copy(t) end,
         log = function(fmt, ...) logs[#logs + 1] = string.format(fmt, ...) end }
local GAME_IDS = { ab01trout9 = "AB01trout9", somenpc = "SomeNPC", guar_pet = "Guar_Pet" }
tes3 = { installDirectory = [[@GAME@]], isModActive = function(n) return n == "abotWaterLife.esm" end,
         objectType = { creature = 6, npc = 2 },
         getObject = function(id) local g = GAME_IDS[id:lower()] return g and { id = g } end }
event = { register = function() end }
package.path = [[@SUITE@\?.lua;]] .. package.path
-- HUD Companion Health Bar's config module, as its main.lua reads it (require(...).mcm.blackList)
local hud = { mcm = { blackList = { SomeNPC = true } } }
package.preload["Pirate.HUD Companion Health Bar.config"] = function() return hud end
local config = require("mwcompanions.config")
local core = require("mwcompanions.core")
core.rebuildPluginLists()
local mirror = require("mwpluginpatches.patches.hudCompanionMirror")
local function check(ok, what) if not ok then error(what, 2) end end

-- 1. the first sync: each side gets what the other has
mirror.sync()
check(hud.mcm.blackList.AB01trout9 == true, "the excluded plugin's creature goes on the HUD's blacklist, as the game spells it")
check(config.blacklist.somenpc == true, "the HUD's own entry goes on mwcompanions' blacklist")
check(saved.HUD_Companion_Health_Bar and saved.HUD_Companion_Health_Bar.blackList.AB01trout9, "the HUD's config is saved")

-- 2. whitelisted in mwcompanions: off the HUD's blacklist
config.whitelist.AB01trout9 = true
mirror.sync()
check(hud.mcm.blackList.AB01trout9 == nil, "a creature whitelisted in mwcompanions leaves the HUD's blacklist")

-- 3. added in the HUD: on mwcompanions' blacklist
hud.mcm.blackList.Guar_Pet = true
mirror.sync()
check(config.blacklist.guar_pet == true and not core.isBlacklisted({ baseObject = { id = "AB01trout9" } }),
      "a HUD addition is never a follower in mwcompanions; the whitelisted creature still is one")

-- 4. taken off in the HUD: may be a follower again in mwcompanions
hud.mcm.blackList.SomeNPC = nil
mirror.sync()
check(config.blacklist.somenpc == nil and hud.mcm.blackList.SomeNPC == nil, "taken off on both sides")

-- 5. nothing changed: nothing to do
local a, b = mirror.sync()
check(a == 0 and b == 0, "a sync with no change changes nothing")
print("ok")
"""


def test_the_two_lists_follow_each_other():
    game = tempfile.mkdtemp(prefix="hudmirror-")
    _plugin(game)
    script = SCRIPT.replace("@GAME@", game).replace("@SUITE@", SUITE)
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stderr + out.stdout
