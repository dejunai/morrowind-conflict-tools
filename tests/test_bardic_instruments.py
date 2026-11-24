"""mwpluginpatches' Bardic Inspiration instrument whitelist, run in LuaJIT with stubs of that mod's modules: a listed
drum counts as an instrument, using it plays or opens the gig's song menu under the mod's own conditions, and a
performance without a lute in hand skips the lute animation (which needs a node only lute meshes have)."""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.path.join(ROOT, "tools", "luajit", "luajit.exe")
MODS = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

SCRIPT = r"""
local handlers, said, menus, randoms, stops, lutePlays, vanity, controls = {}, nil, 0, 0, 0, 0, false, true
local inventory, gig, npcs, held = {}, nil, {}, nil
mwse = { log = function() end }
event = { register = function(name, fn) handlers[name] = fn end }
local cell = { isInterior = true, behavesAsExterior = false }
function cell:iterateReferences()
  local i = 0
  return function() i = i + 1; return npcs[i] end
end
tes3 = { objectType = { npc = 1, weapon = 2 }, player = { object = { inventory = inventory }, cell = cell },
         mobilePlayer = { cell = cell }, worldController = { hour = { value = 20 } },
         messageBox = function(m) said = m end, getEquippedItem = function() return held end,
         setVanityMode = function(p) vanity = p.enabled end }
local common = { config = { enabled = true }, data = { knownSongs = {} },
                 hasLute = function() return false end, isLute = function(o) return o.id == "mer_lute" end,
                 isInnkeeper = function(r) return r.publican end,
                 disableControls = function() controls = false end, stopMusic = function() stops = stops + 1 end }
local animate = { play = function() lutePlays = lutePlays + 1 end }
local loaded = {
  ["common"] = common, ["controllers.animationController"] = animate,
  ["controllers.songController"] = { showMenu = function() menus = menus + 1 end,
                                     playRandom = function() randoms = randoms + 1 end },
  ["data.performances"] = { STATE = { PLAYED = "played", SKIP = "skip" }, getCurrent = function() return gig end },
  ["messages.messages"] = { notTavern = "not a tavern", noGigScheduled = "no gig", notNightTime = "not night",
                            alreadyPlayed = "played already" },
}
for name, module in pairs(loaded) do package.loaded["mer.bardicInspiration." .. name] = module end
package.loaded["mwpluginpatches.config"] = { musicalInstruments = { misc_de_drum_01 = true, t_removed = false } }
package.path = [[MODS\?.lua;]] .. package.path
require("mwpluginpatches.patches.bardicInstruments").init()

local drum = { id = "Misc_De_Drum_01" }
local function use(item, who)
  said = nil
  return handlers.equip({ reference = who or tes3.player, item = item })
end
local function check(ok, what) if not ok then error(what, 2) end end

check(not common.hasLute(), "empty handed: no instrument")
inventory[1] = { object = { id = "T_Removed" } }
check(not common.hasLute(), "an item taken off the list is no instrument")
inventory[2] = { object = drum }
check(common.hasLute(), "a listed drum is an instrument")

check(use({ id = "iron dagger" }) == nil, "other items equip as usual")
check(use(drum, {}) == nil, "someone else's drum is left alone")
check(use(drum) == false and said == "not a tavern", "indoors, no innkeeper")
npcs[1] = { publican = true }
use(drum); check(said == "no gig", "no gig booked")
gig = { state = "scheduled" }
tes3.worldController.hour.value = 12
use(drum); check(said == "not night", "too early")
tes3.worldController.hour.value = 20
use(drum); check(said == nil and menus == 1, "the song menu opens")
gig.state = "played"
use(drum); check(said == "played already" and menus == 1, "played already")
gig.state = "skip"
use(drum); check(said == nil and menus == 1, "a gig being wound up")
gig.state = "scheduled"; common.data.songPlaying = {}
use(drum); check(menus == 1, "already playing")
common.data.songPlaying = nil

cell.isInterior = false
use(drum); check(randoms == 1, "outdoors a song plays")
common.data.travelPlay = true
use(drum); check(stops == 1 and randoms == 1, "used again, it stops")
common.data.travelPlay = nil
common.config.enabled = false
check(use(drum) == nil and randoms == 1, "Bardic Inspiration switched off")

animate.play()
check(lutePlays == 0 and vanity and not controls, "no lute in hand: camera and controls only")
held = { object = { id = "iron dagger" } }
animate.play()
check(lutePlays == 0, "a dagger is never given the lute animation")
held = { object = { id = "mer_lute" } }
animate.play()
check(lutePlays == 1, "a lute keeps the mod's animation")
print("ok")
"""


def test_a_listed_drum_is_an_instrument_that_can_be_played():
    out = subprocess.run([LUAJIT, "-"], input=SCRIPT.replace("MODS", MODS), capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stderr + out.stdout


def test_the_guar_skin_drums_are_on_the_default_list():
    with open(os.path.join(MODS, "mwpluginpatches", "config.lua"), encoding="utf-8") as f:
        config = f.read()
    assert "misc_de_drum_01 = true" in config and "misc_de_drum_02 = true" in config
