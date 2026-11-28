"""CR-12 (mwfloatfix): the list is trusted by the patches' size and Cell Fixes' content hash (FNV-1a, the same in
Lua and Python), not their file dates, found under tes3.installDirectory; an item is marked checked only once the
rays have answered; a cell change keeps the queue; skips are logged."""
import os
import shutil
import subprocess

import pytest

from mwdialog_cellmods import fnv1a_file

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwfloatfix", "main.lua")


def _luajit():
    exe = os.environ.get("MWMANAGER_LUAJIT") or os.path.join(ROOT, "tools", "luajit", "luajit.exe")
    return exe if os.path.isfile(exe) or shutil.which(exe) else None


LUAJIT = _luajit()
FIXES = "mwdialog_check Cell Fixes.esp"

SCRIPT = r"""
local handlers, clock, logged, lines = {}, 0, {}, {}
os.clock = function() return clock end
local types = { miscItem = 1, book = 2, ingredient = 3, alchemy = 4, weapon = 5, ammunition = 6, armor = 7,
                clothing = 8, apparatus = 9, lockpick = 10, probe = 11, repairItem = 12, light = 13, npc = 14, creature = 15 }
local RAY = @RAY@
tes3 = { objectType = types, scanCode = { delete = 211 }, event = setmetatable({}, { __index = function(_, k) return k end }),
         getActiveCells = function() return ACTIVE end, installDirectory = [[@INSTALL@]], player = { data = {} },
         rayTest = function(p) return RAY(p) end }
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
local asked = {}
lfs = { attributes = function(p)
          asked[#asked + 1] = p
          local f = io.open(p, "rb"); if not f then return nil end
          local size = f:seek("end"); f:close(); return { size = size, modification = 1 }
        end, mkdir = function() end }
mwse = { log = function(fmt, ...) logged[#logged + 1] = string.format(fmt, ...) end,
         loadConfig = function(name, defaults)
    if name == "mwfloatfix" then defaults.enabled = true; defaults.log = true; return defaults end
    if name == "mwfloatfix_data" then return @DATA@ end
    return defaults
end }
local realOpen = io.open
io.open = function(p, mode)
  if p:find("mwfloatfix.log", 1, true) then
    return { write = function(_, ...) for _, s in ipairs({ ... }) do lines[#lines + 1] = s end end,
             close = function() end, flush = function() end, setvbuf = function() end, seek = function() end }
  end
  return realOpen(package.config:sub(1, 1) == "/" and p:gsub("\\", "/") or p, mode)    -- Windows paths on Linux
end
dofile([[@MOD@]])
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
local cell = cellOf({ isInterior = true, id = "Balmora, Inn", editorName = "Balmora, Inn" })
if handlers.loaded then handlers.loaded({}) end   -- the game loads first (the log file opens there)
local function item(x, y, z, box)
  local p = { x = x, y = y, z = z }
  local node = { worldTransform = { rotation = ROT, scale = 1, translation = tes3vector3.new(x, y, z) } }
  if box then node.createBoundingBox = function() return { min = tes3vector3.new(-2, -2, 0), max = tes3vector3.new(2, 2, 4) } end end
  return { object = { id = "Misc_Bottle", objectType = 1 }, cell = cell, position = p, startingPosition = p,
           sceneNode = node, tempData = {}, sourceMod = "Morrowind.esm" }
end
local function step() clock = clock + 10; if handlers.simulate then handlers.simulate() end end
local function checked(r) return r.tempData.mwfloatfixChecked and true or false end
@BODY@
"""


def run(tmp_path, body, data="nil", ray="function() return { distance = 0 } end"):
    script = (SCRIPT.replace("@MOD@", MOD).replace("@INSTALL@", str(tmp_path)).replace("@DATA@", data)
              .replace("@RAY@", ray).replace("@BODY@", body))
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, timeout=60, cwd=str(tmp_path))
    assert out.returncode == 0, out.stderr + out.stdout
    return out.stdout


def _fixes(tmp_path, content=b"TES3 cell fixes " * 1000):
    d = tmp_path / "Data Files"
    d.mkdir(exist_ok=True)
    (d / FIXES).write_bytes(content)
    return d / FIXES


def _data(size, fnv):
    stamp = f'fnv1a = "{fnv}"' if fnv else ""
    return ('{ sources = { ["' + FIXES + '"] = { size = ' + str(size) + ", " + stamp + ' } }, '
            'cells = { ["balmora, inn"] = { { id = "Misc_Bottle", pos = { 110, 95, 40 } } } } }')


ONE = '{ cells = { ["balmora, inn"] = { { id = "Misc_Bottle", pos = { 110, 95, 40 } } } } }'


BODY_LIST = r"""
local other = item(500, 500, 40, true)
enter(other)
step()
print("other=" .. tostring(checked(other)))
print("asked=" .. (asked[1] or ""))
print("logged=" .. table.concat(logged, " | "))
"""


@pytest.mark.skipif(LUAJIT is None, reason="LuaJIT not available")
def test_the_list_is_trusted_when_cell_fixes_hash_matches(tmp_path):
    f = _fixes(tmp_path)
    out = run(tmp_path, BODY_LIST, data=_data(os.path.getsize(f), fnv1a_file(str(f))))
    assert "other=false" in out                      # the list is trusted: an item it doesn't name isn't queued
    assert f"asked={tmp_path}\\Data Files\\{FIXES}" in out    # under tes3.installDirectory, not the working dir
    assert "doesn't match" not in out


@pytest.mark.skipif(LUAJIT is None, reason="LuaJIT not available")
@pytest.mark.parametrize("fnv, why", [("00000000", "its contents changed"), (None, "no content stamp")])
def test_a_rebuilt_cell_fixes_of_the_same_size_makes_the_list_stale(tmp_path, fnv, why):
    f = _fixes(tmp_path)
    out = run(tmp_path, BODY_LIST, data=_data(os.path.getsize(f), fnv))
    assert "other=false" in out and why in out and "no items are checked" in out     # stale: nothing at all


@pytest.mark.skipif(LUAJIT is None, reason="LuaJIT not available")
def test_lua_and_python_hash_alike(tmp_path):
    f = _fixes(tmp_path, bytes(range(256)) * 300 + b"\xff\x00\x80")
    good = run(tmp_path, BODY_LIST, data=_data(os.path.getsize(f), fnv1a_file(str(f))))
    assert "other=false" in good


@pytest.mark.skipif(LUAJIT is None, reason="LuaJIT not available")
def test_an_item_without_a_bounding_box_yet_is_tried_again_then_given_up_on(tmp_path):
    out = run(tmp_path, r"""
local r = item(110, 95, 40, false)
enter(r)
step()
print("first=" .. tostring(checked(r)))
for i = 1, 5 do step() end
print("later=" .. tostring(checked(r)))
print("lines=" .. table.concat(lines, ""))
""", data=ONE)
    assert "first=false" in out and "later=true" in out
    assert "no bounding box yet (gave up after 3 tries)" in out


@pytest.mark.skipif(LUAJIT is None, reason="LuaJIT not available")
def test_a_failed_ray_test_does_not_mark_the_item(tmp_path):
    out = run(tmp_path, r"""
local r = item(110, 95, 40, true)
enter(r)
step()
print("first=" .. tostring(checked(r)))
FAIL = false
step(); step()
print("later=" .. tostring(checked(r)))
""", data=ONE, ray="function() if FAIL ~= false then error('not ready') end return { distance = 0 } end")
    assert "first=false" in out and "later=true" in out


@pytest.mark.skipif(LUAJIT is None, reason="LuaJIT not available")
def test_a_cell_change_keeps_the_queue_and_skips_are_logged(tmp_path):
    out = run(tmp_path, r"""
local r = item(110, 95, 40, true)
enter(r)
handlers.cellChanged({})
step()
print("kept=" .. tostring(checked(r)))
print("lines=" .. table.concat(lines, ""))
""", data=ONE, ray="function() return nil end")
    assert "kept=true" in out and "left Misc_Bottle in Balmora, Inn: no floor found within reach" in out


@pytest.mark.skipif(LUAJIT is None, reason="LuaJIT not available")
def test_without_the_list_it_says_so_once_and_registers_nothing(tmp_path):
    out = run(tmp_path, r"""
print("logged=" .. table.concat(logged, " | "))
print("handlers=" .. tostring(handlers.cellChanged ~= nil or handlers.loaded ~= nil or handlers.simulate ~= nil))
""")
    assert "mwfloatfix_data.json is missing: no items are checked" in out and "handlers=false" in out


@pytest.mark.skipif(LUAJIT is None, reason="LuaJIT not available")
def test_a_cell_is_done_once_its_items_are_handled_and_never_checked_again(tmp_path):
    out = run(tmp_path, r"""
local r = item(110, 95, 40, true)
enter(r)
print("sim=" .. tostring(handlers.simulate ~= nil))
step()
print("checked=" .. tostring(checked(r)))
print("done=" .. tostring(tes3.player.data.mwfloatfixDone and tes3.player.data.mwfloatfixDone["balmora, inn"]))
print("idle=" .. tostring(handlers.simulate == nil))
local again = item(110, 95, 40, true)             -- the next visit (another session's reference)
INCELL = {}
enter(again)
step()
print("again=" .. tostring(checked(again)))
""", data=ONE)
    assert "sim=true" in out and "checked=true" in out and "done=true" in out
    assert "idle=true" in out and "again=false" in out
