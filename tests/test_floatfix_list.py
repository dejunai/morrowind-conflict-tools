"""mwfloatfix_data.json: the loose items that could float (an item on a table a later plugin moved is listed, an
untouched cell isn't), and mwfloatfix checks only listed items when the list is there (LuaJIT, stub MWSE)."""
import json
import os
import struct
import subprocess
import types

import pytest

from conftest import m, plugin, rec, sub, z
from mwdialog_cellmods import float_items

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MOD = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwfloatfix", "main.lua")

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


def _cell(*refs):
    return rec("CELL", sub("NAME", z("")) + sub("DATA", struct.pack("<Iii", 0, 0, 0)) + b"".join(refs))


def _ref(index, oid, x, zpos, deleted=False):
    tail = sub("DELE", struct.pack("<I", 0)) if deleted else sub("DATA", struct.pack("<6f", x, 100.0, zpos, 0, 0, 0))
    return sub("FRMR", struct.pack("<I", index)) + sub("NAME", z(oid)) + tail


def test_a_blacklisted_plugin_still_counts_for_what_it_takes_away(tmp_path):
    """The conflict blacklist only quiets the report: a dock a blacklisted plugin deletes is gone in game too, so
    the bucket another plugin put on it is listed (the chargen dock: Ports of Vvardenfell and Damp Little Squat)."""
    data = tmp_path / "Data Files"
    data.mkdir()
    size = len(plugin(data / "Master.esm", [], [
        rec("STAT", sub("NAME", z("dock")) + sub("MODL", z("dock.nif"))),
        rec("MISC", sub("NAME", z("bucket")) + sub("MODL", z("bucket.nif"))),
        _cell(_ref(1, "dock", 100.0, 0.0))]))
    plugin(data / "Ports.esp", [("Master.esm", size)], [_cell(_ref((1 << 24) | 1, "dock", 0, 0, deleted=True))])
    plugin(data / "Squat.esp", [("Master.esm", size)], [_cell(_ref(1, "bucket", 110.0, 34.0))])
    (tmp_path / m.CONFLICT_BLACKLIST_FILE).write_text("Ports.esp\n")
    order = ["Master.esm", "Ports.esp", "Squat.esp"]
    args = types.SimpleNamespace(data_dir=str(data), dry_run=False)
    m.run_cell_conflicts(args, [(n, str(data / n)) for n in order])
    listed = json.loads((data / "MWSE" / "config" / "mwfloatfix_data.json").read_text())["cells"]
    assert listed["#0,0"] == [{"id": "bucket", "pos": [110, 100, 34], "from": "Squat.esp",
                               "why": "dock deleted by ports.esp"}]


def test_a_dock_our_own_patch_deletes_again_still_lists_the_bucket_on_it(tmp_path):
    """Ports deletes the dock, Sounds puts it back, our Cell Fixes deletes it again: the game loads our patch too,
    so the bucket on that dock is listed (the chargen dock bucket)."""
    data = tmp_path / "Data Files"
    data.mkdir()
    size = len(plugin(data / "Master.esm", [], [
        rec("STAT", sub("NAME", z("dock")) + sub("MODL", z("dock.nif"))),
        rec("MISC", sub("NAME", z("bucket")) + sub("MODL", z("bucket.nif"))),
        _cell(_ref(1, "dock", 100.0, 0.0))]))
    plugin(data / "Ports.esp", [("Master.esm", size)], [_cell(_ref((1 << 24) | 1, "dock", 0, 0, deleted=True))])
    plugin(data / "Sounds.esp", [("Master.esm", size)], [_cell(_ref((1 << 24) | 1, "dock", 100.0, 0.0))])
    plugin(data / "Squat.esp", [("Master.esm", size)], [_cell(_ref(1, "bucket", 110.0, 34.0))])
    fixes = next(x for x in m.OUR_PATCHES if "cell fixes" in x.lower())
    plugin(data / fixes, [("Master.esm", size)], [_cell(_ref((1 << 24) | 1, "dock", 0, 0, deleted=True))])
    order = ["Master.esm", "Ports.esp", "Sounds.esp", "Squat.esp", fixes]
    args = types.SimpleNamespace(data_dir=str(data), dry_run=False)
    m.run_cell_conflicts(args, [(n, str(data / n)) for n in order])
    listed = json.loads((data / "MWSE" / "config" / "mwfloatfix_data.json").read_text())["cells"]
    assert listed["#0,0"] == [{"id": "bucket", "pos": [110, 100, 34], "from": "Squat.esp",
                               "why": f"dock deleted by {fixes.lower()}"}]


SCRIPT = r"""
local handlers, clock = {}, 0
os.clock = function() return clock end
local types = { miscItem = 1, book = 2, ingredient = 3, alchemy = 4, weapon = 5, ammunition = 6, armor = 7,
                clothing = 8, apparatus = 9, lockpick = 10, probe = 11, repairItem = 12, light = 13, npc = 14, creature = 15 }
tes3 = { objectType = types, scanCode = { delete = 211 }, event = setmetatable({}, { __index = function(_, k) return k end }),
         getActiveCells = function() return ACTIVE end, player = { data = {} },
         rayTest = function() return { distance = 0 } end }    -- resting on something: checked, not moved
local V = {}
V.__index = V
V.__add = function(a, b) return tes3vector3.new(a.x + b.x, a.y + b.y, a.z + b.z) end
V.__mul = function(a, k) return tes3vector3.new(a.x * k, a.y * k, a.z * k) end
tes3vector3 = { new = function(x, y, z) return setmetatable({ x = x, y = y, z = z }, V) end }
local ROT = setmetatable({}, { __mul = function(_, v) return v end })
event = { register = function(name, fn) handlers[name] = fn end,
          unregister = function(name, fn) if handlers[name] == fn then handlers[name] = nil end end,
          isRegistered = function(name, fn) return handlers[name] == fn end }
timer = { real = 1, delayOneFrame = function(f) f() end }
mwse = { loadConfig = function(name, defaults)
    if name == "mwfloatfix" then defaults.enabled = true; defaults.log = false; return defaults end
    if name == "mwfloatfix_data" then return { cells = { ["balmora, inn"] = { { id = "Misc_Bottle", pos = { 110, 95, 40 } } },
                                                         ["balmora, guild"] = { { id = "Misc_Bottle", pos = { 110, 95, 40 } } } } } end
    return defaults
end }
dofile([[MOD]])
INCELL, ACTIVE = {}, {}
local function cellOf(c)
  function c:iterateReferences() local i = 0 return function() i = i + 1 return INCELL[i] end end
  return c
end
local function enter(...)
  for _, r in ipairs({ ... }) do INCELL[#INCELL + 1] = r end
  ACTIVE = { INCELL[1] and INCELL[1].cell }
  if handlers.cellChanged then handlers.cellChanged({}) end
end
local cell = cellOf({ isInterior = true, id = "Balmora, Inn" })
local guild = cellOf({ isInterior = true, id = "Balmora, Guild" })
local function item(x, y, z, src, at)
  local p = { x = x, y = y, z = z }
  local node = { createBoundingBox = function() return { min = tes3vector3.new(-2, -2, 0), max = tes3vector3.new(2, 2, 4) } end,
                 worldTransform = { rotation = ROT, scale = 1, translation = tes3vector3.new(x, y, z) } }
  return { object = { id = "Misc_Bottle", objectType = 1 }, cell = at or cell, position = p, startingPosition = p,
           sceneNode = node, tempData = {}, sourceMod = src }
end
local listed, other = item(111, 96, 40, "Morrowind.esm"), item(500, 500, 40, "Morrowind.esm")
local spawned = item(110, 95, 40, nil)              -- placed by a script on the same spot: no source plugin
enter(listed, other, spawned)
clock = 10
handlers.simulate()
if not listed.tempData.mwfloatfixChecked then error("the listed item is checked") end
if other.tempData.mwfloatfixChecked then error("an item the list doesn't name is skipped") end
if spawned.tempData.mwfloatfixChecked then error("an item a script placed is skipped") end
local batch = {}
INCELL = {}                                       -- the next listed cell
for i = 1, 5 do batch[i] = item(110, 95, 40, "Morrowind.esm", guild) end
enter(unpack(batch))
clock = 20
handlers.simulate()
local n = 0
for _, r in ipairs(batch) do if r.tempData.mwfloatfixChecked then n = n + 1 end end
if n ~= 2 then error("a frame checks at most 2 items, checked " .. n) end
print("ok")
"""


@pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")
def test_mwfloatfix_skips_an_item_the_list_does_not_name():
    out = subprocess.run([LUAJIT, "-"], input=SCRIPT.replace("[[MOD]]", "[[" + MOD + "]]"), capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stderr + out.stdout


def test_object_info_reads_a_plugin_again_only_once_its_content_changes(tmp_path, monkeypatch):
    import mwdialog_cellmods as cm
    data = tmp_path / "Data Files"
    data.mkdir()
    a = plugin(data / "A.esp", [], [rec("STAT", sub("NAME", z("dock")) + sub("MODL", z("x/Dock.nif")))])
    order = [("A.esp", str(data / "A.esp"))]
    reads = []
    real = cm._plugin_objects
    monkeypatch.setattr(cm, "_plugin_objects", lambda d: reads.append(1) or real(d))
    monkeypatch.setattr(cm, "_parser_version", lambda: "v")
    assert cm.object_info(order)[1] == {"dock": "x\\dock.nif"} and len(reads) == 1
    cm._OBJECT_INFO.clear()                                       # a new run: only the file on disk is left
    assert cm.object_info(order)[1] == {"dock": "x\\dock.nif"} and len(reads) == 1
    plugin(data / "A.esp", [], [rec("STAT", sub("NAME", z("dock")) + sub("MODL", z("y.nif")) + sub("SCRI", z("s")))])
    cm._OBJECT_INFO.clear()
    tags, models, scripted = cm.object_info(order)
    assert models == {"dock": "y.nif"} and scripted == {"dock"} and len(reads) == 2
    assert a and (tmp_path / cm.OBJECT_CACHE_FILE).exists()
