import os
import subprocess

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MOD = os.path.join(ROOT, "Data Files", "MWSE", "mods", "mwquicktoggle")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")


def test_toggle_restores_displaced_shield_and_weapon_ready_stows_light():
    script = r'''
local handlers, delayed = {}, {}
local weapon = { id = "sword", objectType = 1 }
local shield = { id = "shield", objectType = 2, slot = 7 }
local lantern = { id = "lantern", objectType = 4 }
local equipment = { { object = weapon }, { object = shield, itemData = { condition = 90 } } }

local function equipped(item, itemData)
  for _, stack in ipairs(equipment) do
    if stack.object == item and (itemData == nil or stack.itemData == itemData) then return true end
  end
  return false
end
local function remove(item)
  for i = #equipment, 1, -1 do if equipment[i].object == item then table.remove(equipment, i) end end
end

tes3 = {
  objectType = { weapon = 1, armor = 2, clothing = 3, light = 4 },
  armorSlot = { shield = 7 }, quickKeyType = { item = 1 },
  keybind = {}, worldController = { inputController = { isKeyDown = function() return false end } },
  mobilePlayer = {}, menuMode = function() return false end,
}
for i = 1, 10 do tes3.keybind["quick" .. i] = i end
tes3.player = { data = {}, object = {
  equipment = equipment,
  hasItemEquipped = function(_, item, itemData) return equipped(item, itemData) end,
} }
tes3.getQuickKey = function(p) if p.slot == 9 then return { type = 1, item = lantern } end end
tes3.getInputBinding = function(key) return { code = key, device = 0 } end
tes3.getEquippedItem = function(p)
  for _, stack in ipairs(equipment) do if stack.object.objectType == p.objectType then return stack end end
end
function tes3.mobilePlayer:equip(p)
  if p.item == lantern then remove(shield) elseif p.item == shield then remove(lantern) end
  if not equipped(p.item, p.itemData) then equipment[#equipment + 1] = { object = p.item, itemData = p.itemData } end
end
function tes3.mobilePlayer:unequip(p) remove(p.item) end

mwse = {
  loadConfig = function(_, defaults) return defaults end,
  saveConfig = function() end,
  mcm = { createTemplate = function() error("MCM should not run") end },
}
include = function() return nil end
timer = { delayOneFrame = function(fn) delayed[#delayed + 1] = fn end }
event = { register = function(name, fn, opts)
  handlers[name] = handlers[name] or {}
  handlers[name][opts and opts.priority or 0] = fn
end }
local function flush() local q = delayed; delayed = {}; for _, fn in ipairs(q) do fn() end end
local function check(ok, message) if not ok then error(message, 2) end end

package.path = [[''' + MOD + r'''\?.lua;]] .. package.path
require("main")

local function press9()
  handlers.keyDown[10000]({ keyCode = 9 })
  if not equipped(lantern) then tes3.mobilePlayer:equip({ item = lantern }) end
  handlers.keyDown[-10000]({ keyCode = 9 })
  flush()
end

press9()
check(equipped(lantern) and not equipped(shield), "lantern displaces shield")
press9()
check(not equipped(lantern) and equipped(shield), "second press restores exact shield")

press9()
handlers.weaponReadied[0]({ reference = tes3.player, weaponStack = { object = weapon } })
check(not equipped(lantern) and equipped(shield), "readying weapon replaces lantern with remembered shield")
print("ok")
'''
    result = subprocess.run([LUAJIT, "-"], input=script, text=True, capture_output=True, timeout=60)
    assert result.returncode == 0 and result.stdout.strip() == "ok", result.stderr + result.stdout
