"""mwfloatfix puts the people mwfloatfix_rescue.json lists, under water in this save, back on their footing once per
save (LuaJIT, stub MWSE)."""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.path.join(ROOT, "tools", "luajit", "luajit.exe")
MOD = os.path.join(ROOT, "Data Files", "MWSE", "mods", "mwsuite", "mwfloatfix", "main.lua")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

SCRIPT = r"""
local handlers, clock, config, page = {}, 0, nil, nil
os.clock = function() return clock end
local types = { miscItem = 1, book = 2, ingredient = 3, alchemy = 4, weapon = 5, ammunition = 6, armor = 7,
                clothing = 8, apparatus = 9, lockpick = 10, probe = 11, repairItem = 12, light = 13, npc = 14, creature = 15 }
local world = { isInterior = false, gridX = -2, gridY = -9 }
tes3 = { objectType = types, scanCode = { delete = 211 }, event = setmetatable({}, { __index = function(_, k) return k end }),
         player = { data = {} }, getActiveCells = function() return {} end,
         makeSafeObjectHandle = function(r) return { valid = function() return not r.gone end, getObject = function() return r end } end,
         positionCell = function(p)
             local r = p.reference
             r.position = { x = p.position[1], y = p.position[2], z = p.position[3] }
             r.faced = p.orientation[3]
             r.moves = r.moves + 1
             return true
         end }
tes3vector3 = { new = function(x, y, z) return { x = x, y = y, z = z } end }
event = { register = function(name, fn) handlers[name] = fn end }
mwse = { loadConfig = function(name, defaults)
    if name == "mwfloatfix" then config = defaults; config.enabled, config.log = ENABLED, false; return config end
    if name == "mwfloatfix_rescue" then return { npcs = { { id = "am_fisherman4", cell = "#-2,-9",
        from = { -9384, -72926, 88 }, to = { -9355, -72897, 70 } } } } end
    return defaults
end }
dofile([[MOD]])
local function person(id, x, y, z, dead)
    return { object = { id = id .. "00000000", objectType = types.npc }, baseObject = { id = id }, cell = world,
             position = { x = x, y = y, z = z }, orientation = { x = 0, y = 0, z = 4.25 }, isDead = dead, moves = 0,
             tempData = {} }            -- no sourceMod and no startingPosition: neither may be relied on
end
local function load(ref)
    handlers.referenceActivated({ reference = ref })
    clock = clock + 5
    handlers.simulate()
    return ref
end
local function check(ok, what) if not ok then error(what, 2) end end

if not ENABLED then
    check(load(person("AM_Fisherman4", -9384, -72926, -96)).moves == 0, "switched off it moves no one")
    print("ok") return
end
check(load(person("AM_Fisherman4", -9384, -72926, 88)).moves == 0, "one standing dry is left alone")
check(load(person("AM_Fisherman4", -9384, -72926, -96, true)).moves == 0, "a body is left alone")
check(load(person("AM_Fisherman4", -2000, -72926, -96)).moves == 0, "one far from the spot is left alone")
check(load(person("someone_else", -9384, -72926, -96)).moves == 0, "one the list doesn't name is left alone")
local gone = person("AM_Fisherman4", -9384, -72926, -96)
gone.gone = true
check(load(gone).moves == 0, "a reference unloaded before the cell settled is left alone")

local early = person("AM_Fisherman4", -9390, -72900, -96)
handlers.referenceActivated({ reference = early })
handlers.simulate()
check(early.moves == 0, "nothing moves before the cell has settled")
clock = clock + 5
handlers.simulate()
check(early.moves == 1 and early.position.x == -9355 and early.position.z == 70, "put back on the dock")
check(early.faced == 4.25, "facing as before")
check(load(person("AM_Fisherman4", -9355, -72897, -96)).moves == 0, "only once per save")
tes3.player.data = {}
check(load(person("AM_Fisherman4", -9384, -72926, -96)).moves == 1, "another save is put right too")
print("ok")
"""


@pytest.mark.parametrize("enabled", ["true", "false"])
def test_listed_people_under_water_are_put_back_once_per_save(enabled):
    script = SCRIPT.replace("ENABLED", enabled).replace("[[MOD]]", "[[" + MOD + "]]")
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stderr + out.stdout
