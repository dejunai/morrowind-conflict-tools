"""mwperformers' bard fixes, in LuaJIT with stub MWSE calls. In dialogue the bard's script is kept on its own
one-frame skip (`if ( state )`, none of them has a MenuMode check) and the song is cut. AM_Lute is a shield, so
Weapon Sheathing hung it on his back and hid the hand: lute shields go on that mod's exclusion list."""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.path.join(ROOT, "tools", "luajit", "luajit.exe")
MOD = os.path.join(ROOT, "Data Files", "MWSE", "mods", "mwsuite", "mwperformers", "main.lua")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

SCRIPT = r"""
local handlers, stopped, speaker = {}, 0, nil
event = {
  register = function(name, fn) handlers[name] = handlers[name] or {}; table.insert(handlers[name], fn) end,
  unregister = function(name, fn)
    for i = #(handlers[name] or {}), 1, -1 do if handlers[name][i] == fn then table.remove(handlers[name], i) end end
  end,
}
local function fire(name, e)
  local copy = {}
  for i, fn in ipairs(handlers[name] or {}) do copy[i] = fn end
  for _, fn in ipairs(copy) do fn(e or {}) end
end
local armor = { { id = "AM_Lute", mesh = "m\\Misc_de_lute_01.nif", slot = 8 },
                { id = "detd_am_lute_armor", mesh = "m\\misc_de_lute_01.nif", slot = 8 },
                { id = "steel_shield", mesh = "a\\resolute_shield.nif", slot = 8 },
                { id = "lute_helm", mesh = "m\\misc_de_lute_01.nif", slot = 0 } }
local sheathing = { blocked = {} }
include = function(name) if name == "weaponSheathing.config" then return sheathing end end
tes3 = { objectType = { npc = 1, armor = 2 }, armorSlot = { shield = 8 },
         event = setmetatable({}, { __index = function(_, k) return k end }),
         getActiveCells = function() return {} end, getPlayerTarget = function() end,
         iterateObjects = function() local i = 0; return function() i = i + 1; return armor[i] end end,
         makeSafeObjectHandle = function(r)
           return { valid = function() return not r.gone end, getObject = function() return r end }
         end,
         removeSound = function() stopped = stopped + 1 end }
tes3ui = { getServiceActor = function() return speaker end, findMenu = function() end }
timer = { delayOneFrame = function() end }
mwse = { loadConfig = function(_, d) d.enabled = ENABLED; d.log = false; return d end, saveConfig = function() end }
dofile([[MOD]])
local function check(ok, what) if not ok then error(what, 2) end end
local function npc(script, context)
  local base = { objectType = 1, id = "someone", mesh = "base_anim.nif", script = script and { id = script } }
  return { reference = { object = { id = base.id, baseObject = base, objectType = 1 }, context = context } }
end

fire("initialized")
if not ENABLED then
  check(next(sheathing.blocked) == nil, "switched off: another mod's settings are left alone")
  speaker = npc("DM_Bard_script", { state = 0, positiononce = 1 })
  fire("uiActivated")
  check(stopped == 0 and speaker.reference.context.state == 0, "switched off: no bard is silenced")
  print("ok")
  return
end
check(sheathing.blocked.am_lute and sheathing.blocked.detd_am_lute_armor, "lute shields stay in the hand")
check(not sheathing.blocked.steel_shield and not sheathing.blocked.lute_helm, "other armour is sheathed as usual")

local bard = { state = 0, positiononce = 1, reposition = 0 }
speaker = npc("DM_Bard_script", bard)
fire("uiActivated")
check(bard.state == 1 and stopped == 1, "the song stops and the script skips its frame")
for _ = 1, 3 do
  bard.state = 0                              -- what the script does when it skips
  fire("enterFrame")
  check(bard.state == 1, "it skips every frame of the dialogue")
end
fire("uiActivated")                           -- back from barter
check(#handlers.enterFrame == 1, "one frame handler, however often the dialogue shows")
fire("menuExit")
bard.state = 0
fire("enterFrame")
check(bard.state == 0 and #handlers.enterFrame == 0, "he sings again afterwards, and no frame handler is left")

fire("uiActivated")
bard.state = 0
fire("loaded")
fire("enterFrame")
check(bard.state == 0, "loading a save ends it")

local quest = { state = 5 }
speaker = npc("my_bard_quest", quest)
fire("uiActivated")
fire("enterFrame")
check(quest.state == 5, "another script's own 'state' is never written")
fire("menuExit")

stopped = 0
speaker = npc("guard_script", { state = 0, positiononce = 1 })
fire("uiActivated")
check(stopped == 0, "someone who doesn't perform is left alone")
print("ok")
"""


@pytest.mark.parametrize("enabled", ["true", "false"])
def test_bards_hold_their_lute_and_are_quiet_in_dialogue(enabled):
    script = SCRIPT.replace("ENABLED", enabled).replace("[[MOD]]", "[[" + MOD + "]]")
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stderr + out.stdout
