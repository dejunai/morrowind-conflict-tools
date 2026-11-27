"""mwpluginpatches: Ahead of the Classes equip-once intercept (patches/aheadOfTheClassesEquip.lua).

The mod is faked with a small stand-in that mimics its timer + equip loop; nothing of theirs is copied.
"""
import os
import subprocess

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MOD = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwpluginpatches").replace("\\", "/")
SUITE = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite").replace("\\", "/")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

# a stand-in for Danae\Classes\main.lua: a simulate handler starts the timer, whose callback adds gear and equips all
FAKE_AOTC = r"""
local function startClass()
    for _, id in ipairs(GEAR) do tes3.addItem(id) end
    for _, stack in pairs(tes3.player.object.inventory) do
        local o = stack.object
        if o.objectType == tes3.objectType.armor or o.objectType == tes3.objectType.weapon
            or o.objectType == tes3.objectType.clothing then
            tes3.equip{ item = o, reference = tes3.player, playSound = false }
        end
    end
end
function chargenDone()
    timer.start{ type = "simulate", duration = 0.7, callback = startClass }
end
"""
FAKE_OTHER = r"""
function otherStartsTimer(cb) timer.start{ type = "simulate", duration = 1, callback = cb } end
"""


@pytest.fixture()
def mods(tmp_path):
    root = tmp_path / "mods"
    for rel, text in (("Danae/Classes/main.lua", FAKE_AOTC), ("someOtherMod/main.lua", FAKE_OTHER)):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return str(root).replace("\\", "/")


BOOT = r"""
local logs, handlers = {}, {}
mwse = { log = function(fmt, ...) logs[#logs + 1] = string.format(fmt, ...) end }
local function list(name) handlers[name] = handlers[name] or {} return handlers[name] end
event = {
  register = function(name, fn) local l = list(name) for _, f in ipairs(l) do if f == fn then return end end l[#l + 1] = fn end,
  unregister = function(name, fn) local l = list(name) for i = #l, 1, -1 do if l[i] == fn then table.remove(l, i) end end end,
  isRegistered = function(name, fn) for _, f in ipairs(list(name)) do if f == fn then return true end end return false end,
}
function trigger(name, e) e = e or {} for _, f in ipairs({ unpack(list(name)) }) do f(e) end return e end
tes3 = {
  event = setmetatable({}, { __index = function(_, k) return k end }),
  objectType = { armor = "armor", weapon = "weapon", clothing = "clothing", misc = "misc" },
  weaponType = { marksmanBow = 9, marksmanCrossbow = 10, marksmanThrown = 11, arrow = 12, bolt = 13 },
  armorSlot = { helmet = 0, cuirass = 1, shield = 8 },
  clothingSlot = { shirt = 2, ring = 8 },
}
charGenValue = -1
tes3.findGlobal = function(id) if id == "CharGenState" then return { value = charGenValue } end return nil end
tes3.player = { id = "player", object = { equipment = {}, inventory = {} } }
tes3.mobilePlayer = { reference = tes3.player }
local npc = { id = "npc", equipment = {} }
ITEMS = {
  helm1 = { objectType = "armor", slot = 0 }, helm2 = { objectType = "armor", slot = 0 },
  cuir1 = { objectType = "armor", slot = 1 },
  shield1 = { objectType = "armor", slot = 8 },
  shirt1 = { objectType = "clothing", slot = 2 }, shirt2 = { objectType = "clothing", slot = 2 },
  ring1 = { objectType = "clothing", slot = 8 }, ring2 = { objectType = "clothing", slot = 8 }, ring3 = { objectType = "clothing", slot = 8 },
  sword1 = { objectType = "weapon", type = 1, isTwoHanded = false }, sword2 = { objectType = "weapon", type = 1, isTwoHanded = false },
  claymore = { objectType = "weapon", type = 2, isTwoHanded = true },
  bow = { objectType = "weapon", type = 9 },
  arrows = { objectType = "weapon", type = 12 }, bolts = { objectType = "weapon", type = 13 },
  dart = { objectType = "weapon", type = 11 },
  potion = { objectType = "misc" },
}
for id, o in pairs(ITEMS) do o.id = id end
local function slotKey(o)
  if o.objectType == "misc" then return "misc" end
  if o.objectType == "weapon" then return (o.type >= 11) and "ammo" or "weapon" end
  return o.objectType .. o.slot
end
equipCalls, equipLog = 0, {}
local function engineEquip(p)
  equipCalls = equipCalls + 1
  local item = type(p.item) == "string" and ITEMS[p.item] or p.item
  local ref = p.reference or p.mobile.reference
  equipLog[#equipLog + 1] = (ref == tes3.player and "P:" or "N:") .. item.id
  local eq = (ref == tes3.player) and tes3.player.object.equipment or npc.equipment
  local rings = 0
  for _, s in ipairs(eq) do if s.object.id:match("^ring") then rings = rings + 1 end end
  if item.id:match("^ring") and rings < 2 then eq[#eq + 1] = { object = item } return true end
  for i, s in ipairs(eq) do if slotKey(s.object) == slotKey(item) and not s.object.id:match("^ring") then eq[i] = { object = item } return true end end
  eq[#eq + 1] = { object = item }
  return true
end
tes3.equip = engineEquip
tes3.getObject = function(id) return ITEMS[id] end
tes3.addItem = function(id)
  local inv = tes3.player.object.inventory
  for _, s in ipairs(inv) do if s.object.id == id then return end end
  inv[#inv + 1] = { object = ITEMS[id] }
end
local started = {}
timer = { start = function(p) started[#started + 1] = p return p end }
local nativeTimerStart = timer.start
local config = setmetatable({
  enabled = ENABLED, aotcEquipOnceEnabled = FLAG,
  isAheadOfTheClassesInstalled = function() return INSTALLED end,
}, { __index = function(_, k) if k:match("^is") then return function() return false end end end })
table.insert(package.loaders, 2, function(name)
  if name == "mwpluginpatches.config" then return function() return config end end
  if name == "mwpluginpatches.intercept" then return assert(loadfile("MOD/intercept.lua")) end
  if name == "mwpluginpatches.patches.aheadOfTheClassesEquip" then return assert(loadfile("MOD/patches/aheadOfTheClassesEquip.lua")) end
end)
local patch = require("mwpluginpatches.patches.aheadOfTheClassesEquip")
local function load(rel) assert(loadfile("MODS/" .. rel))() end
local function joined(t) return table.concat(t, ",") end
local function worn()
  local ids = {}
  for _, s in ipairs(tes3.player.object.equipment) do ids[#ids + 1] = s.object.id end
  table.sort(ids)
  return joined(ids)
end
local function wear(...)
  local eq = {}
  for _, o in ipairs({ ... }) do eq[#eq + 1] = { object = o } end
  tes3.player.object.equipment = eq
end
local function fire() local t = started[#started] started[#started] = nil return t.callback({}) end
function beginChargen() charGenValue = 10 trigger("loaded") end
local function unloaded()
  return timer.start == nativeTimerStart and tes3.equip == engineEquip and #(list("simulate")) == 0
end
"""


def run(script, mods, enabled=True, flag=True, installed=True):
    script = (BOOT + script).replace("MODS", mods).replace("MOD/", MOD + "/")
    for key, value in (("ENABLED", enabled), ("FLAG", flag), ("INSTALLED", installed)):
        script = script.replace(key, str(value).lower())
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stdout + out.stderr


def test_each_slot_gets_one_item_and_repeats_are_skipped(mods):
    run(r"""
assert(patch.init() == true)
assert(timer.start == nativeTimerStart, "not armed until chargen is pending")
beginChargen()
assert(timer.start ~= nativeTimerStart)
load("Danae/Classes/main.lua")
GEAR = { "helm1", "helm2", "cuir1", "shirt1", "shirt2", "sword1", "sword2", "arrows", "bolts", "potion" }
chargenDone()
assert(#started == 1)
fire()
local got = worn()
local helmets, shirts, swords, ammo = 0, 0, 0, 0
for _, s in ipairs(tes3.player.object.equipment) do
  local o = s.object
  if o.id:match("^helm") then helmets = helmets + 1
  elseif o.id:match("^shirt") then shirts = shirts + 1 elseif o.id:match("^sword") then swords = swords + 1
  elseif o.id == "arrows" or o.id == "bolts" then ammo = ammo + 1 end
end
assert(helmets == 1 and shirts == 1 and swords == 1 and ammo == 1, got)
assert(#tes3.player.object.equipment == 5, got)
assert(equipCalls == 5, "only the equips that fill a slot reach the engine: " .. equipCalls)
assert(unloaded(), "wrappers and simulate come off after the pass")
local seen = false
for _, l in ipairs(logs) do if l:find("skipped", 1, true) then seen = true end end
assert(seen, "one summary line")
print("ok")
""", mods)


def test_a_slot_filled_before_the_pass_is_left_alone(mods):
    run(r"""
assert(patch.init())
beginChargen()
load("Danae/Classes/main.lua")
wear(ITEMS.shirt1, ITEMS.ring1)
GEAR = { "shirt2", "helm1", "ring2", "ring3" }
chargenDone() fire()
assert(worn() == "helm1,ring1,ring2,shirt1", worn())
assert(unloaded())
print("ok")
""", mods)


def test_two_handed_weapon_and_shield_do_not_go_together(mods):
    run(r"""
assert(patch.init())
beginChargen()
load("Danae/Classes/main.lua")
GEAR = { "shield1", "claymore", "sword1" }
chargenDone() fire()
local s = worn()
local hasShield, hasClaymore = s:find("shield1", 1, true), s:find("claymore", 1, true)
assert(not (hasShield and hasClaymore), s)
assert(hasShield or hasClaymore, s)
print("ok")
""", mods)
    run(r"""
assert(patch.init())
beginChargen()
load("Danae/Classes/main.lua")
wear(ITEMS.bow)
GEAR = { "shield1", "arrows" }
chargenDone() fire()
assert(worn() == "arrows,bow", "a bow counts as two-handed, arrows go in the ammunition slot: " .. worn())
print("ok")
""", mods)
    run(r"""
assert(patch.init())
beginChargen()
load("Danae/Classes/main.lua")
wear(ITEMS.shield1)
GEAR = { "claymore", "sword1" }
chargenDone() fire()
assert(worn() == "shield1,sword1", worn())
print("ok")
""", mods)


def test_thrown_weapons_use_the_ammunition_slot(mods):
    run(r"""
assert(patch.init())
beginChargen()
load("Danae/Classes/main.lua")
GEAR = { "dart", "arrows", "sword1" }
chargenDone() fire()
local n = 0
for _, s in ipairs(tes3.player.object.equipment) do if s.object.id == "dart" or s.object.id == "arrows" then n = n + 1 end end
assert(n == 1 and worn():find("sword1", 1, true), worn())
print("ok")
""", mods)


def test_skipped_equips_are_logged_with_item_slot_and_reason(mods):
    run(r"""
assert(patch.init())
beginChargen()
load("Danae/Classes/main.lua")
ITEMS.helm2.name = "Steel Helm"
ITEMS.shield1.name = "Round Shield"
ITEMS.claymore.name = "Claymore"
wear(ITEMS.shirt1)
GEAR = { "helm1", "helm2", "shirt2", "shirt1", "claymore", "shield1" }
chargenDone() fire()
local function find(...)
  local parts = { ... }
  for _, l in ipairs(logs) do
    local ok = l:find("skipped", 1, true) == nil and false or true
    for _, part in ipairs(parts) do if not l:find(part, 1, true) then ok = false end end
    if ok then return l end
  end
end
assert(find("skipped shirt2", "slot clothing2", "slot occupied by shirt1"), table.concat(logs, "\n"))
assert(find("skipped helm2 (Steel Helm)", "slot armor0") or find("skipped helm1", "slot armor0"), table.concat(logs, "\n"))
assert(find("skipped", "(Round Shield)", "two-handed weapon is held: claymore (Claymore)")
  or find("skipped claymore (Claymore)", "shield is held: shield1 (Round Shield)"), table.concat(logs, "\n"))
local repeats = 0
for _, l in ipairs(logs) do if l:find("repeat, already equipped in this slot", 1, true) then repeats = repeats + 1 end end
assert(repeats >= 1, "re-walked items are logged as repeats")
assert(find("equipped", "skipped", "equip call(s)"), "summary line kept")
print("ok")
""", mods)


def test_engine_refused_equips_are_logged(mods):
    run(r"""
assert(patch.init())
beginChargen()
load("Danae/Classes/main.lua")
GEAR = { "helm1", "arrows" }
chargenDone()
local engine = tes3.equip
tes3.equip = function(p)
  local item = type(p.item) == "string" and ITEMS[p.item] or p.item
  if item.id == "arrows" then return false end
  return engine(p)
end
fire()
local seen
for _, l in ipairs(logs) do if l:find("engine refused arrows", 1, true) and l:find("slot ammo", 1, true) then seen = l end end
assert(seen, table.concat(logs, "\n"))
assert(not worn():find("arrows", 1, true), worn())
print("ok")
""", mods)


def test_guard_only_runs_inside_the_mods_timer_callback(mods):
    run(r"""
assert(patch.init())
beginChargen()
load("Danae/Classes/main.lua")
load("someOtherMod/main.lua")
local called = false
local cb = function() called = true end
otherStartsTimer(cb)
assert(started[#started].callback == cb)
tes3.equip{ item = ITEMS.helm1, reference = tes3.player }
tes3.equip{ item = ITEMS.helm2, reference = tes3.player }
assert(equipCalls == 2 and worn() == "helm2", worn())
GEAR = {}
chargenDone()
local t = started[#started]
assert(t.duration == 0.7 and t.type == "simulate" and t.callback ~= nil)
print("ok")
""", mods)


def test_other_references_pass_through_during_the_pass(mods):
    run(r"""
assert(patch.init())
beginChargen()
local src = [[
timer.start{ callback = function()
  tes3.equip{ item = ITEMS.helm1, reference = NPC }
  tes3.equip{ item = ITEMS.helm2, reference = NPC }
  tes3.equip{ item = ITEMS.potion, reference = tes3.player }
  tes3.equip{ item = "helm1", reference = tes3.player }
  tes3.equip{ item = "helm2", reference = tes3.player }
  tes3.equip{ item = ITEMS.shirt1, mobile = tes3.mobilePlayer }
  tes3.equip{ item = ITEMS.shirt2, mobile = tes3.mobilePlayer }
end }
]]
NPC = { id = "npc" }
assert(loadstring(src, "@C:/x/mods/Danae/Classes/main.lua"))()
fire()
assert(equipLog[1] == "N:helm1" and equipLog[2] == "N:helm2" and equipLog[3] == "P:potion", joined(equipLog))
assert(worn() == "helm1,potion,shirt1", worn())
assert(equipCalls == 5, equipCalls)
assert(unloaded())
print("ok")
""", mods)


def test_tes3_equip_is_restored_when_the_callback_fails(mods):
    run(r"""
assert(patch.init())
beginChargen()
load("Danae/Classes/main.lua")
GEAR = { "helm1" }
chargenDone()
local cb = started[#started].callback
tes3.addItem = function() error("boom") end
local ok, err = pcall(cb, {})
assert(not ok and tostring(err):find("boom", 1, true), tostring(err))
assert(unloaded(), "restored after an error")
print("ok")
""", mods)


def test_the_callback_still_gets_its_arguments_and_returns(mods):
    run(r"""
assert(patch.init())
beginChargen()
local got
timer.start{ callback = function(...) got = { ... } return "r" end }
assert(started[#started].callback ~= nil)
local src = [[
timer.start{ callback = function(a, b) seenA, seenB = a, b return "back" end }
]]
local f = assert(loadstring(src, "@C:/x/mods/Danae/Classes/main.lua"))
f()
local cb = started[#started].callback
assert(cb ~= nil)
local r = cb("a", "b")
assert(seenA == "a" and seenB == "b" and r == "back")
assert(unloaded())
print("ok")
""", mods)


def test_save_load_with_chargen_done_does_not_arm(mods):
    run(r"""
assert(patch.init() == true)
assert(#list("loaded") == 1, "the loaded hook is registered")
charGenValue = -1
trigger("loaded")
assert(unloaded())
assert(#list("loaded") == 1, "loaded stays so a later new game can re-arm")
print("ok")
""", mods)


def test_disarms_a_second_after_chargen_if_the_timer_never_runs(mods):
    run(r"""
assert(patch.init())
beginChargen()
assert(not unloaded())
charGenValue = -1
trigger("simulate", { delta = 0.5 })
assert(not unloaded(), "still waiting for AotC's 0.7 s timer")
trigger("simulate", { delta = 0.6 })
assert(unloaded(), "gone after 1 s with no equip callback")
assert(#list("loaded") == 1)
print("ok")
""", mods)


def test_a_new_game_later_in_the_session_rearms(mods):
    run(r"""
assert(patch.init())
beginChargen()
load("Danae/Classes/main.lua")
GEAR = { "helm1", "helm2" }
chargenDone() fire()
assert(unloaded() and worn() == "helm1")
-- a later new game
tes3.player.object.equipment, tes3.player.object.inventory = {}, {}
equipCalls = 0
GEAR = { "shirt1", "shirt2" }
beginChargen()
assert(timer.start ~= nativeTimerStart)
chargenDone() fire()
assert(worn() == "shirt1", worn())
assert(equipCalls == 1)
assert(unloaded())
print("ok")
""", mods)


def test_does_not_clobber_a_later_timer_wrapper(mods):
    run(r"""
assert(patch.init())
beginChargen()
local ours = timer.start
local laterCalls = 0
local later = function(...) laterCalls = laterCalls + 1 return ours(...) end
timer.start = later
load("Danae/Classes/main.lua")
GEAR = { "helm1", "helm2" }
chargenDone() fire()
assert(timer.start == later, "a wrapper installed after ours is left in place")
assert(tes3.equip == engineEquip)
assert(#list("simulate") == 0)
-- our function is still under theirs, but is now a pass-through
local ran = false
later({ callback = function() ran = true end, duration = 1 })
assert(laterCalls >= 2 and started[#started].callback ~= nil)
started[#started].callback()
assert(ran and tes3.equip == engineEquip)
print("ok")
""", mods)


@pytest.mark.parametrize("enabled,flag,installed", [(False, True, True), (True, False, True), (True, True, False)])
def test_left_alone_when_off_or_not_installed(mods, enabled, flag, installed):
    run(r"""
assert(patch.init() == false)
assert(timer.start == nativeTimerStart, "timer.start is not wrapped")
assert(#list("loaded") == 0)
load("Danae/Classes/main.lua")
GEAR = { "helm1", "helm2" }
chargenDone() fire()
assert(equipCalls == 2, "every equip call goes through: " .. equipCalls)
print("ok")
""", mods, enabled=enabled, flag=flag, installed=installed)


def test_defaults_on_only_when_the_mod_is_installed():
    script = r"""
package.path = [[SUITE/?.lua;]] .. package.path
local present = false
lfs = { fileexists = function(path) return path:gsub("\\", "/") == "Data Files/MWSE/mods/Danae/Classes/main.lua" and present or false end }
mwse = { loadConfig = function() return nil end, saveConfig = function() end, log = function() end }
tes3 = setmetatable({}, { __index = function() return function() return nil end end })
package.loaded["mwpluginpatches.config"] = nil
local off = require("mwpluginpatches.config")
assert(off.aotcEquipOnceEnabled == false and off.isAheadOfTheClassesInstalled() == false)
package.loaded["mwpluginpatches.config"] = nil
present = true
local on = require("mwpluginpatches.config")
assert(on.aotcEquipOnceEnabled == true)
print("ok")
""".replace("SUITE", SUITE)
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stdout + out.stderr


def test_mcm_and_main_list_the_switch():
    for rel, needle in (("mcm.lua", 'id = "aotcEquipOnceEnabled"'), ("main.lua", "aheadOfTheClassesEquip.init")):
        with open(os.path.join(MOD, rel), encoding="utf-8") as f:
            assert needle in f.read(), rel


def test_files_are_utf8_lf_without_bom():
    for rel in ("patches/aheadOfTheClassesEquip.lua", "config.lua", "main.lua", "mcm.lua"):
        with open(os.path.join(MOD, rel), "rb") as f:
            data = f.read()
        assert not data.startswith(b"\xef\xbb\xbf") and b"\r\n" not in data, rel
        data.decode("utf-8")