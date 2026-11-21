"""mwfloatfix_data.json: the loose items that could float (an item on a table a later plugin moved is listed, an
untouched cell isn't), and mwfloatfix checks only listed items when the list is there (LuaJIT, stub MWSE)."""
import os
import subprocess

import pytest

from mwdialog_cellmods import float_items

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.path.join(ROOT, "tools", "luajit", "luajit.exe")
MOD = os.path.join(ROOT, "Data Files", "MWSE", "mods", "mwfloatfix", "main.lua")

TAGS = {"furn_de_table": "STAT", "misc_com_bottle_01": "MISC"}
DEPS = {"morrowind.esm": set(), "tables.esp": {"morrowind.esm"}}


def test_an_item_on_a_table_a_later_plugin_moved_is_listed_and_an_untouched_cell_is_not():
    hist = {
        ("i", "balmora, inn"): {
            ("morrowind.esm", 1): [(0, "morrowind.esm", "furn_de_table", (100.0, 100.0, 0.0), 1.0, False),
                                   (1, "tables.esp", "furn_de_table", (300.0, 100.0, 0.0), 1.0, False)],
            ("morrowind.esm", 2): [(0, "morrowind.esm", "misc_com_bottle_01", (110.0, 95.0, 40.0), 1.0, False)],
        },
        ("i", "ald-ruhn, inn"): {
            ("morrowind.esm", 3): [(0, "morrowind.esm", "furn_de_table", (0.0, 0.0, 0.0), 1.0, False)],
            ("morrowind.esm", 4): [(0, "morrowind.esm", "misc_com_bottle_01", (5.0, 5.0, 40.0), 1.0, False)],
        },
    }
    found = float_items(hist, {}, lambda p: DEPS[p], TAGS)
    assert set(found) == {"balmora, inn"}
    assert found["balmora, inn"] == {("misc_com_bottle_01", 110, 95, 40): ("morrowind.esm",
                                                                           "furn_de_table moved by tables.esp")}


SCRIPT = r"""
local handlers, clock = {}, 0
os.clock = function() return clock end
local types = { miscItem = 1, book = 2, ingredient = 3, alchemy = 4, weapon = 5, ammunition = 6, armor = 7,
                clothing = 8, apparatus = 9, lockpick = 10, probe = 11, repairItem = 12, light = 13, npc = 14, creature = 15 }
tes3 = { objectType = types, scanCode = { delete = 211 }, event = setmetatable({}, { __index = function(_, k) return k end }),
         getActiveCells = function() return {} end }
tes3vector3 = { new = function(x, y, z) return { x = x, y = y, z = z } end }
event = { register = function(name, fn) handlers[name] = fn end }
mwse = { loadConfig = function(name, defaults)
    if name == "mwfloatfix" then defaults.enabled = true; defaults.log = false; return defaults end
    if name == "mwfloatfix_data" then return { cells = { ["balmora, inn"] = { { id = "Misc_Bottle", pos = { 110, 95, 40 } } } } } end
    return defaults
end }
dofile([[MOD]])
local cell = { isInterior = true, id = "Balmora, Inn" }
local function item(x, y, z, src)
  local p = { x = x, y = y, z = z }
  return { object = { id = "Misc_Bottle", objectType = 1 }, cell = cell, position = p, startingPosition = p,
           sceneNode = {}, tempData = {}, sourceMod = src }
end
local listed, other = item(111, 96, 40, "Morrowind.esm"), item(500, 500, 40, "Morrowind.esm")
local spawned = item(110, 95, 40, nil)              -- placed by a script on the same spot: no source plugin
handlers.referenceActivated({ reference = listed })
handlers.referenceActivated({ reference = other })
handlers.referenceActivated({ reference = spawned })
clock = 10
handlers.simulate()
if not listed.tempData.mwfloatfixChecked then error("the listed item is checked") end
if other.tempData.mwfloatfixChecked then error("an item the list doesn't name is skipped") end
if spawned.tempData.mwfloatfixChecked then error("an item a script placed is skipped") end
print("ok")
"""


@pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")
def test_mwfloatfix_skips_an_item_the_list_does_not_name():
    out = subprocess.run([LUAJIT, "-"], input=SCRIPT.replace("[[MOD]]", "[[" + MOD + "]]"), capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stderr + out.stdout
