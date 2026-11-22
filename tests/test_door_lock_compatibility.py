import os
import subprocess

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
PATCHES = os.path.join(ROOT, "Data Files", "MWSE", "mods", "mwsuite", "mwpluginpatches", "patches")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")


def test_owned_door_locking_and_activation_order():
    script = r'''
handlers, sounds, notices = {}, {}, {}
local config = { doorLockedNotification = true }
package.preload["mwpluginpatches.config"] = function() return config end
tes3 = {
  objectType = { door = 1, npc = 2 },
  event = { activate = "activate" },
  player = {}, mobilePlayer = { isSneaking = false },
  getLocked = function(p) return p.reference.locked end,
  lock = function(p) p.reference.locked, p.reference.level = true, p.level end,
  unlock = function(p) p.reference.locked = false; if p.reference.lockNode then p.reference.lockNode.locked = false end end,
  getOwner = function(p) return p.reference.owner end,
  hasOwnershipAccess = function(p) return p.target.access end,
  playSound = function(p) sounds[#sounds + 1] = p.sound end,
}
tes3ui = { showNotifyMenu = function(s) notices[#notices + 1] = s end }
mwse = { log = function() end }
event = { register = function(_, fn, opts) handlers[opts.priority] = fn end }
local owner = { objectType = tes3.objectType.npc }
local function cell(actors)
  local c = { isInterior = true, actors = actors or {} }
  function c:iterateReferences()
    local i = 0
    return function() i = i + 1; return self.actors[i] end
  end
  return c
end
local function door(dest, access)
  return { object = { objectType = tes3.objectType.door }, cell = cell(), destination = { cell = dest },
           owner = owner, access = access, data = {} }
end
local function activate(target)
  return handlers[9200]({ target = target, activator = tes3.player })
end
local function check(ok, message) if not ok then error(message, 2) end end

package.path = [[''' + PATCHES + r'''\?.lua;]] .. package.path
require("doorLockCompatibility").init()

local outside = { isInterior = false, isOrBehavesAsExterior = true }
local exit = door(outside, false); exit.locked = true; exit.lockNode = { locked = true, level = 38 }
check(activate(exit) == nil, "locked interior exit allows activation through without sneak or pick")
check(not exit.locked and not exit.lockNode.locked, "locked interior exit is unlocked")
check(exit.data.ab01drlkbl == 1, "abot bypass flag is set during activation")
handlers[9000]({ target = exit })
check(exit.data.ab01drlkbl == nil, "abot bypass flag is cleaned up after abot")
check(#sounds == 0 and #notices == 0, "interior exit produces no lock alert")

local keyedDoor = door(cell(), false); keyedDoor.locked = true
keyedDoor.lockNode = { locked = true, level = 50, key = { id = "luce_lwbc_cg_attic_key" } }
tes3.player.object = { inventory = { contains = function(self, id) return id == "luce_lwbc_cg_attic_key" end } }
check(activate(keyedDoor) == nil, "door with matching key allows activation standing without sneak or alert")
check(#sounds == 0 and #notices == 0, "key holder receives no lock alert")
tes3.player.object = nil

local unlockedExit = door(outside, false); unlockedExit.locked = false
check(activate(unlockedExit) == nil, "unlocked owned interior exit allows activation without sneak")

local absent = door(cell(), false)
check(activate(absent) == false, "standing activation is consumed")
check(absent.locked and absent.level == 38, "absent owner's door gets abot's standard lock level")
check(sounds[1] == "LockedDoor" and notices[1] == "The Door is Locked", "audible and optional visual feedback")

local present = door(cell({ { object = owner, disabled = false } }), false)
check(activate(present) == false and not present.locked, "present owner's unlocked door requires sneaking")

tes3.mobilePlayer.isSneaking = true
local locked = door(cell(), false); locked.locked = true
check(activate(locked) == nil and locked.data.ab01drlkbl == 1, "sneaking bypasses abot")
handlers[9000]({ target = locked })
check(locked.data.ab01drlkbl == nil, "temporary bypass is gone before Modern Lockpicking")

local blacklisted = door(cell(), false); blacklisted.locked = true; blacklisted.data.ab01drlkbl = 1
activate(blacklisted); handlers[9000]({ target = blacklisted })
check(blacklisted.data.ab01drlkbl == 1, "user's abot blacklist is preserved")

-- Arrille Tradehouse duplicate trapdoor conflict resolution
local arrilleCell = { id = "Seyda Neen, Arrille's Tradehouse", isInterior = true }
-- like MWSE's tes3reference: `disabled` is read-only, disable()/enable() change it
local trapdoorState = { disabled = false }
local trapdoor = setmetatable({ object = { id = "dim_com_m_trapdoor_b", objectType = tes3.objectType.door }, cell = arrilleCell, locked = true, lockNode = { locked = true, level = 75 }, data = {},
  disable = function() trapdoorState.disabled = true end, enable = function() trapdoorState.disabled = false end }, {
  __index = function(_, k) if k == "disabled" then return trapdoorState.disabled end end,
  __newindex = function(t, k, v) if k == "disabled" then error("disabled is read-only", 2) end rawset(t, k, v) end })
local rentDoor = { object = { id = "Rent_Arrille_Door", objectType = tes3.objectType.door }, cell = arrilleCell, locked = true, lockNode = { locked = true, level = 75 }, data = {} }
local cellDoors = { trapdoor, rentDoor }
function arrilleCell:iterateReferences(objType)
  local i = 0
  return function()
    i = i + 1
    return cellDoors[i]
  end
end
local activatedByPlayer = nil
tes3.player.activate = function(self, target) activatedByPlayer = target end
local rentVal = 1
tes3.getGlobal = function(var) if var == "Rent_Arrille" then return rentVal end return 0 end

-- When rented, activating dim_com_m_trapdoor_b forwards to Rent_Arrille_Door, disabling the duplicate
local res = activate(trapdoor)
check(res == false, "activation on dim_com_m_trapdoor_b is consumed and redirected")
check(trapdoor.disabled == true, "dim_com_m_trapdoor_b is disabled when rented")
check(activatedByPlayer == rentDoor, "Rent_Arrille_Door is activated instead")
check(not rentDoor.locked and not rentDoor.lockNode.locked, "Rent_Arrille_Door is unlocked")

-- When syncArrilleInnDoors runs while rented
require("doorLockCompatibility").syncArrilleInnDoors(arrilleCell)
check(trapdoor.disabled == true, "syncArrilleInnDoors disables dim_com_m_trapdoor_b while rented")

-- When unrented, syncArrilleInnDoors restores dim_com_m_trapdoor_b
rentVal = 0
require("doorLockCompatibility").syncArrilleInnDoors(arrilleCell)
check(trapdoor.disabled == false, "syncArrilleInnDoors re-enables dim_com_m_trapdoor_b when unrented")

print("ok")
'''
    result = subprocess.run([LUAJIT, "-"], input=script, text=True, capture_output=True, timeout=60)
    assert result.returncode == 0 and result.stdout.strip() == "ok", result.stderr + result.stdout
