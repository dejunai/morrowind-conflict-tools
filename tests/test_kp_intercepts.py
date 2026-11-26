"""mwpluginpatches: the intercepts that took over luafix KP1, KP2 and KP4 (Attend Me eye rays, Attend Me recruit
label, MWSE Containers Extended linked-container lookup). KP3 (Keg Drip mesh paths) has no intercept: it fixed no bug.

The target mods are faked with small stand-ins written for the test; nothing of theirs is copied. Each fake can be
written with the old luafix marker, and the intercept must then stand down.
"""
import os
import subprocess

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MOD = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwpluginpatches").replace("\\", "/")
SUITE = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite").replace("\\", "/")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

PATCHES = ("attendMeRays", "attendMeRecruitLabel", "g7ContainersLinkCache")

FAKE_ACTIONS = r"""MARK
local function rayWorld(extra)
    local ignore = { tes3.player }
    if extra then table.insert(ignore, extra) end
    return tes3.rayTest({ position = tes3.getPlayerEyePosition(), direction = tes3.getPlayerEyeVector(),
        maxDistance = 8192 * 8, ignore = ignore })
end
local function onSimulate()
    -- each caller reads .reference straight away, as Attend Me does (the result object is reused by the next ray)
    local function ref(hit) return hit and hit.reference end
    seen = { ref(rayWorld()), ref(rayWorld(companion)), ref(rayWorld()), ref(rayWorld(companion)) }
    if boomActions then error("stand-in failure") end
end
event.register("simulate", onSimulate)
actionsMove = function() return rayWorld() end
actionsFindAll = function()
    tes3.rayTest({ position = tes3.getPlayerEyePosition(), direction = tes3.getPlayerEyeVector(), findAll = true })
end
"""
FAKE_RECRUIT = r"""MARK
local active = false
local function onSimulate()
    if not active then return end
    if tes3.menuMode() then return end
    labels = (labels or 0) + 1
end
local function onClick() clicks = (clicks or 0) + 1 end
recruitStart = function()
    active = true
    event.register("simulate", onSimulate)
    event.register("mouseButtonDown", onClick)
end
recruitStop = function()
    active = false
    event.unregister("simulate", onSimulate)
    event.unregister("mouseButtonDown", onClick)
end
"""
FAKE_G7 = r"""MARK
local function checkData(itemData)
    local data = itemData and itemData.data and itemData.data.g7containers
    if data then return tes3.getReference(data.linkedRef), data.baseObject end
end
event.register("uiObjectTooltip", function(e) g7Seen = checkData(e.itemData) end)
event.register("itemTileUpdated", function(e) checkData(e.itemData) end, { filter = "MenuContents" })
event.register("equip", function(e)
    checkData(e.itemData)
    if e.boom then error("stand-in failure") end
    return false
end)
event.register("activate", function(e) checkData(e.itemData) end)
g7Outside = function(id) return tes3.getReference(id) end
"""
FAKE_OTHER = r"""event.register("simulate", function()
    local p = { position = tes3.getPlayerEyePosition(), direction = tes3.getPlayerEyeVector(), maxDistance = 65536,
        ignore = { tes3.player } }
    tes3.rayTest(p) tes3.rayTest(p)
end)
"""


def write_mods(tmp_path, marked):
    root = tmp_path / "mods"
    files = (("AttendMeMWSE/actions.lua", FAKE_ACTIONS, "-- local fix (KP1)"),
             ("AttendMeMWSE/recruit.lua", FAKE_RECRUIT, "-- local fix (KP2)"),
             ("Spammer/G7 Containers/main.lua", FAKE_G7, "-- local fix (KP4)"),
             ("someOtherMod/main.lua", FAKE_OTHER, ""))
    for rel, text, marker in files:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        header = ("local x = 1 %s: kept here by an old luafix run" % marker) if (marked and marker) else "-- as released"
        p.write_text(text.replace("MARK", header), encoding="utf-8")
    return str(root).replace("\\", "/")


@pytest.fixture()
def mods(tmp_path):
    return write_mods(tmp_path, marked=False)


@pytest.fixture()
def marked(tmp_path):
    return write_mods(tmp_path, marked=True)


BOOT = r"""
local handlers, logs = {}, {}
local function list(name) handlers[name] = handlers[name] or {} return handlers[name] end
event = {
  register = function(name, fn, options) local l = list(name) for _, f in ipairs(l) do if f == fn then return end end l[#l + 1] = fn end,
  unregister = function(name, fn) local l = list(name) for i = #l, 1, -1 do if l[i] == fn then table.remove(l, i) end end end,
  isRegistered = function(name, fn) for _, f in ipairs(list(name)) do if f == fn then return true end end return false end,
}
local nativeRegister = event.register
local function trigger(name, e) e = e or {} for _, f in ipairs({ unpack(list(name)) }) do f(e) end return e end
mwse = { log = function(fmt, ...) logs[#logs + 1] = string.format(fmt, ...) end }
local menu = false
tes3 = { event = setmetatable({}, { __index = function(_, k) return k end }), menuMode = function() return menu end }
tes3.player = { id = "player" }
companion = { id = "companion" }
local refA, refB = { id = "refA" }, { id = "refB" }
local eye = { x = 1, y = 2, z = 3 }
tes3.getPlayerEyePosition = function() return { x = eye.x, y = eye.y, z = eye.z } end
tes3.getPlayerEyeVector = function() return { x = 0, y = 1, z = 0 } end
rays = 0
local result = {}  -- MWSE reuses one result object per rayTest
local function nativeRayTest(p)
  rays = rays + 1
  result.reference = (p.ignore and #p.ignore == 2) and refB or refA
  result.intersection = { x = rays }
  return result
end
tes3.rayTest = nativeRayTest
lookups = 0
local world = { box1 = { id = "box1" }, box2 = { id = "box2" } }
local function nativeGetReference(id) lookups = lookups + 1 return world[id] end
tes3.getReference = nativeGetReference
tes3.makeSafeObjectHandle = function(ref)
  return { valid = function() return not ref.gone end, getObject = function() return ref end }
end
local function item(id) return { data = { g7containers = { linkedRef = id, baseObject = "bag" } } } end
local function readFile(rel)
  local f = io.open("MODS/" .. rel, "rb") if not f then return nil end
  local d = f:read("*a") f:close() return d
end
local config = setmetatable({
  enabled = ENABLED,
  attendMeRaysEnabled = FLAG, attendMeRecruitLabelEnabled = FLAG, g7ContainersLinkCacheEnabled = FLAG,
  isAttendMeInstalled = function() return INSTALLED end,
  isG7ContainersInstalled = function() return INSTALLED end,
  modFileHas = function(rel, text) local d = readFile(rel) return d ~= nil and d:find(text, 1, true) ~= nil end,
}, { __index = function(_, k) if k:match("^is") then return function() return false end end end })
table.insert(package.loaders, 2, function(name)
  if name == "mwpluginpatches.config" then return function() return config end end
  if name == "mwpluginpatches.intercept" then return assert(loadfile("MOD/intercept.lua")) end
  for _, p in ipairs({ "attendMeRays", "attendMeRecruitLabel", "g7ContainersLinkCache" }) do
    if name == "mwpluginpatches.patches." .. p then return assert(loadfile("MOD/patches/" .. p .. ".lua")) end
  end
  if name:match("^mwpluginpatches%.patches%.") then return function() return { init = function() end } end end
end)
local function load(rel) assert(loadfile("MODS/" .. rel))() end
local function joined(t) local o = {} for i, v in ipairs(t) do o[i] = tostring(v and v.id) end return table.concat(o, "|") end
local function logged(text) for _, l in ipairs(logs) do if l:find(text, 1, true) then return true end end return false end
"""


def run(script, mods, enabled=True, flag=True, installed=True):
    script = (BOOT + script).replace("MODS", mods).replace("MOD", MOD)
    for key, value in (("ENABLED", enabled), ("FLAG", flag), ("INSTALLED", installed)):
        script = script.replace(key, str(value).lower())
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stdout + out.stderr


def test_kp1_one_ray_per_ignore_set_per_frame(mods):
    run(r"""
assert(loadfile("MOD/main.lua"))()
load("AttendMeMWSE/actions.lua")
load("someOtherMod/main.lua")
rays = 0
trigger("simulate")
-- the wheel's four casts become two (one per ignore set); the other mod's two identical casts are not shared
assert(rays == 4, "2 for Attend Me + 2 for the other mod, got " .. rays)
assert(joined(seen) == "refA|refB|refA|refB", joined(seen))
assert(tes3.rayTest == nativeRayTest, "rayTest is put back after the handler")
rays = 0
trigger("simulate")
assert(rays == 4, "a new frame casts again")
rays = 0
local hit = actionsMove()
assert(rays == 1 and hit == result and hit.intersection, "outside the handler the real result comes back")
eye.x = 9
rays = 0
trigger("simulate")
assert(rays == 4)
print("ok")
""", mods)


def test_kp1_error_still_surfaces_and_raytest_is_put_back(mods):
    run(r"""
assert(loadfile("MOD/main.lua"))()
load("AttendMeMWSE/actions.lua")
boomActions = true
local ok, err = pcall(trigger, "simulate")
assert(not ok and tostring(err):find("stand-in failure", 1, true), "the mod's own error still surfaces")
assert(tes3.rayTest == nativeRayTest, "rayTest is put back after an error")
local later = function(p) return nativeRayTest(p) end
boomActions = false
tes3.rayTest = later
trigger("simulate")
assert(tes3.rayTest == later, "a rayTest set by someone else is what gets put back")
assert(logged("Attend Me: its command wheel casts one eye ray"))
print("ok")
""", mods)


def test_kp1_findall_passes_through(mods):
    run(r"""
assert(loadfile("MOD/main.lua"))()
local src = assert(io.open("MODS/AttendMeMWSE/actions.lua")):read("*a")
src = src:gsub('event.register%("simulate", onSimulate%)', 'event.register("simulate", function() actionsFindAll() actionsFindAll() end)')
assert(loadstring(src, "@MODS/AttendMeMWSE/actions.lua"))()
rays = 0
trigger("simulate")
assert(rays == 2, "findAll casts are not shared: " .. rays)
print("ok")
""", mods)


def test_kp2_label_every_third_frame_click_untouched(mods):
    run(r"""
assert(loadfile("MOD/main.lua"))()
load("AttendMeMWSE/recruit.lua")
recruitStart()
for i = 1, 9 do trigger("simulate") end
assert(labels == 3, tostring(labels))
menu = true
for i = 1, 5 do trigger("simulate") end
menu = false
assert(labels == 3)
trigger("simulate")
assert(labels == 4, "menu frames don't count: the 10th game frame is a label frame")
trigger("mouseButtonDown") trigger("mouseButtonDown")
assert(clicks == 2, "the click is not throttled")
recruitStop()
assert(#list("simulate") == 0, "stop removes the wrapped handler")
recruitStart()
assert(#list("simulate") == 1, "start again reuses the wrapper")
print("ok")
""", mods)


def test_kp4_linked_container_found_once(mods):
    run(r"""
assert(loadfile("MOD/main.lua"))()
load("Spammer/G7 Containers/main.lua")
lookups = 0
for i = 1, 3 do trigger("uiObjectTooltip", { itemData = item("box1") }) end
for i = 1, 2 do trigger("itemTileUpdated", { itemData = item("box1") }) end
assert(lookups == 1 and g7Seen and g7Seen.id == "box1", tostring(lookups))
assert(tes3.getReference == nativeGetReference, "getReference is put back")
trigger("uiObjectTooltip", { itemData = item("box2") })
assert(lookups == 2)
world.box1.deleted = true
trigger("uiObjectTooltip", { itemData = item("box1") })
assert(lookups == 3, "a deleted reference is looked up again")
world.box1.deleted = nil
trigger("uiObjectTooltip", { itemData = item("box1") })
assert(lookups == 3)
world.box1.gone = true
trigger("uiObjectTooltip", { itemData = item("box1") })
assert(lookups == 4, "an invalid handle is looked up again")
world.box1.gone = nil
trigger("load")
trigger("uiObjectTooltip", { itemData = item("box1") })
assert(lookups == 5, "a save load drops the kept handles")
trigger("uiObjectTooltip", { itemData = item("missing") })
trigger("uiObjectTooltip", { itemData = item("missing") })
assert(lookups == 7 and g7Seen == nil, "a missing container is not kept")
lookups = 0
trigger("activate", { itemData = item("box1") }) trigger("activate", { itemData = item("box1") })
g7Outside("box1")
assert(lookups == 3, "other handlers and calls outside the handlers are untouched")
local e = { itemData = item("box1") }
assert(list("equip")[1](e) == false, "equip still blocks")
local ok = pcall(list("equip")[1], { itemData = item("box1"), boom = true })
assert(not ok and tes3.getReference == nativeGetReference, "put back after an error")
print("ok")
""", mods)


def test_prepatched_files_make_each_intercept_stand_down(marked):
    run(r"""
assert(loadfile("MOD/main.lua"))()
load("AttendMeMWSE/actions.lua")
load("AttendMeMWSE/recruit.lua")
load("Spammer/G7 Containers/main.lua")
rays = 0
trigger("simulate")
assert(rays == 4, "no sharing on top of the file's own KP1 edit")
recruitStart()
labels = 0
for i = 1, 9 do trigger("simulate") end
assert(labels == 9, "no 1-in-3 gate on top of the file's own KP2 edit")
lookups = 0
for i = 1, 3 do trigger("uiObjectTooltip", { itemData = item("box1") }) end
assert(lookups == 3, "no cache on top of the file's own KP4 edit")
assert(logged("old luafix KP1 edit") and logged("old luafix KP2 edit") and logged("old luafix KP4 edit"))
print("ok")
""", marked)


@pytest.mark.parametrize("enabled,flag,installed", [(False, True, True), (True, False, True), (True, True, False)])
def test_left_alone_when_off_or_not_installed(mods, enabled, flag, installed):
    run(r"""
assert(loadfile("MOD/main.lua"))()
assert(event.register == nativeRegister, "event.register is not wrapped")
load("AttendMeMWSE/actions.lua")
load("AttendMeMWSE/recruit.lua")
load("Spammer/G7 Containers/main.lua")
rays = 0
trigger("simulate")
assert(rays == 4)
for i = 1, 3 do trigger("uiObjectTooltip", { itemData = item("box1") }) end
assert(lookups == 3)
print("ok")
""", mods, enabled=enabled, flag=flag, installed=installed)


def test_defaults_on_only_when_installed_and_marker_read(tmp_path):
    game = tmp_path / "game"
    target = game / "Data Files" / "MWSE" / "mods" / "AttendMeMWSE"
    target.mkdir(parents=True)
    (target / "actions.lua").write_text("x = 1 -- local fix (KP1): kept\n", encoding="utf-8")
    (target / "recruit.lua").write_text("x = 1\n", encoding="utf-8")
    script = r"""
package.path = [[SUITE/?.lua;]] .. package.path
local present = false
local files = { ["Data Files/MWSE/mods/AttendMeMWSE/main.lua"] = true, ["Data Files/MWSE/mods/Spammer/G7 Containers/main.lua"] = true }
lfs = { fileexists = function(path) return files[path:gsub("\\", "/")] and present or false end }
mwse = { loadConfig = function() return nil end, saveConfig = function() end, log = function() end }
tes3 = setmetatable({}, { __index = function() return function() return nil end end })
package.loaded["mwpluginpatches.config"] = nil
local off = require("mwpluginpatches.config")
assert(not off.attendMeRaysEnabled and not off.attendMeRecruitLabelEnabled and not off.g7ContainersLinkCacheEnabled)
package.loaded["mwpluginpatches.config"] = nil
present = true
local on = require("mwpluginpatches.config")
assert(on.attendMeRaysEnabled and on.attendMeRecruitLabelEnabled and on.g7ContainersLinkCacheEnabled)
assert(on.modFileHas("AttendMeMWSE/actions.lua", "-- local fix (KP1)") == true)
assert(on.modFileHas("AttendMeMWSE/recruit.lua", "-- local fix (KP2)") == false)
assert(on.modFileHas("AttendMeMWSE/missing.lua", "x") == false)
print("ok")
""".replace("SUITE", SUITE)
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=str(game))
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stdout + out.stderr


def test_mcm_lists_the_switches():
    with open(os.path.join(MOD, "mcm.lua"), encoding="utf-8") as f:
        text = f.read()
    for key in ("attendMeRaysEnabled", "attendMeRecruitLabelEnabled", "g7ContainersLinkCacheEnabled"):
        assert 'id = "%s"' % key in text


def test_files_are_utf8_lf_without_bom():
    for rel in ["patches/%s.lua" % p for p in PATCHES] + ["config.lua", "main.lua", "mcm.lua"]:
        with open(os.path.join(MOD, rel), "rb") as f:
            data = f.read()
        assert not data.startswith(b"\xef\xbb\xbf") and b"\r\n" not in data, rel
        data.decode("utf-8")
