"""mwpluginpatches: handler intercepts (Keg Drip cadence, Essential Indicators attacker filter, Magican't menu guard).

The target mods are faked with small stand-ins written for the test; nothing of theirs is copied.
"""
import os
import subprocess

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MOD = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwpluginpatches").replace("\\", "/")
SUITE = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite").replace("\\", "/")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

PREFIX = "This character's death would result in the thread of prophecy being severed."

FAKE_KEG = r"""local function onSimulate(e) kegCalls[#kegCalls + 1] = e.delta end
event.register("simulate", onSimulate)
event.register("cellChanged", function() kegOther = (kegOther or 0) + 1 end)
kegStop = function() event.unregister("simulate", onSimulate) end
kegIsRegistered = function() return event.isRegistered("simulate", onSimulate) end
kegAgain = function() event.register("simulate", onSimulate) end
"""
FAKE_OTHER = r"""event.register("simulate", function(e) otherCalls[#otherCalls + 1] = e.delta end)
event.register("damage", function(e) tes3.messageBox("PREFIX") end)
"""
FAKE_EI = r"""local function onDamage(e)
    e.damage = 0
    tes3.messageBox("PREFIX")
    tes3.messageBox("Essential Indicators: another line")
    if e.boom then error("stand-in failure") end
end
event.register("initialized", function() event.register("damage", onDamage) end)
eiWarnOutside = function() tes3.messageBox("PREFIX") end
"""
FAKE_MAGICANT = r"""local function fillbarCheck() magicantCalls = (magicantCalls or 0) + 1 end
event.register("initialized", function() event.register("enterFrame", fillbarCheck) end)
"""


@pytest.fixture()
def mods(tmp_path):
    root = tmp_path / "mods"
    for rel, text in (("KegDrip/main.lua", FAKE_KEG), ("someOtherMod/main.lua", FAKE_OTHER),
                      ("Essential Indicators/main.lua", FAKE_EI), ("tew/Magican't/main.lua", FAKE_MAGICANT)):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text.replace("PREFIX", PREFIX), encoding="utf-8")
    return str(root).replace("\\", "/")


BOOT = r"""
local handlers, logs, boxes = {}, {}, {}
kegCalls, otherCalls = {}, {}
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
tes3.mobilePlayer = { reference = tes3.player, activeMagicEffectList = {} }
tes3.messageBox = function(first, ...) boxes[#boxes + 1] = type(first) == "table" and first.message or first return "box" end
local config = setmetatable({
  enabled = ENABLED,
  kegDripCadenceEnabled = KEG, kegDripIntervalSeconds = 3,
  essentialAttackerFilterEnabled = EI,
  magicantMenuGuardEnabled = MAGICANT,
  isKegDripInstalled = function() return INSTALLED end,
  isEssentialIndicatorsInstalled = function() return INSTALLED end,
  isMagicantInstalled = function() return INSTALLED end,
}, { __index = function(_, k) if k:match("^is") then return function() return false end end end })
table.insert(package.loaders, 2, function(name)
  if name == "mwpluginpatches.config" then return function() return config end end
  if name == "mwpluginpatches.intercept" then return assert(loadfile("MOD/intercept.lua")) end
  for _, p in ipairs({ "kegDripCadence", "essentialAttackerFilter", "magicantMenuGuard" }) do
    if name == "mwpluginpatches.patches." .. p then return assert(loadfile("MOD/patches/" .. p .. ".lua")) end
  end
  if name:match("^mwpluginpatches%.patches%.") then return function() return { init = function() end } end end
end)
local function load(rel) assert(loadfile("MODS/" .. rel))() end
local function joined(t) return table.concat(t, "|") end
"""


def run(script, mods, enabled=True, keg=True, ei=True, magicant=True, installed=True):
    script = (BOOT + script).replace("MODS", mods).replace("PREFIX", PREFIX).replace("MOD", MOD)
    for key, value in (("ENABLED", enabled), ("KEG", keg), ("MAGICANT", magicant), ("EI", ei), ("INSTALLED", installed)):
        script = script.replace(key, str(value).lower())
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stdout + out.stderr


def test_keg_drip_simulate_runs_every_3_s_with_summed_delta(mods):
    run(r"""
assert(loadfile("MOD/main.lua"))()
load("KegDrip/main.lua")
load("someOtherMod/main.lua")
for i = 1, 13 do trigger("simulate", { delta = 0.5 }) end
assert(#kegCalls == 2 and kegCalls[1] == 3 and kegCalls[2] == 3, joined(kegCalls))
assert(#otherCalls == 13, "another mod's simulate handler is untouched")
trigger("cellChanged")
assert(kegOther == 1, "its other handlers are untouched")
assert(kegIsRegistered(), "isRegistered sees the original")
kegAgain()
assert(#list("simulate") == 2, "registering the same handler again reuses its wrapper (one keg + one other)")
kegStop()
assert(not kegIsRegistered() and #list("simulate") == 1, "unregister with the original removes the wrapper")
print("ok")
""", mods)


def test_keg_drip_interval_follows_the_setting(mods):
    run(r"""
config.kegDripIntervalSeconds = 1
assert(loadfile("MOD/main.lua"))()
load("KegDrip/main.lua")
for i = 1, 4 do trigger("simulate", { delta = 0.5 }) end
assert(#kegCalls == 2 and kegCalls[1] == 1, joined(kegCalls))
print("ok")
""", mods)


def test_essential_warning_only_for_the_players_side(mods):
    run(r"""
assert(loadfile("MOD/main.lua"))()
load("Essential Indicators/main.lua")
load("someOtherMod/main.lua")
trigger("initialized")
local guard = { reference = { id = "guard" } }
local summon = { reference = { id = "my_atronach" } }
tes3.mobilePlayer.activeMagicEffectList = { { isSummon = true, effectInstance = { createdData = { object = summon.reference } } } }
-- someOtherMod registered its damage handler first and shows the same text: that one is never touched
local function hit(e) boxes = {} e.damage = 10 trigger("damage", e) return e end
local e = hit({ attacker = guard })
assert(e.damage == 0, "the protection still runs")
assert(joined(boxes) == "PREFIX|Essential Indicators: another line", "guard hit: only Essential Indicators' warning hidden: " .. joined(boxes))
local function shown() return joined(boxes) == "PREFIX|PREFIX|Essential Indicators: another line" end
hit({ attacker = tes3.mobilePlayer })
assert(shown(), "player hit shows it")
hit({ attacker = summon })
assert(shown(), "summon hit shows it")
hit({ attacker = guard, projectile = { firingMobile = tes3.mobilePlayer } })
assert(shown(), "player's projectile shows it")
hit({ magicSourceInstance = { caster = tes3.player } })
assert(shown(), "player's spell shows it")
hit({})
assert(not shown(), "no attacker: hidden")
boxes = {}
eiWarnOutside()
assert(boxes[1] == "PREFIX", "outside a damage call it is not touched")
boxes = {}
local ok = pcall(trigger, "damage", { attacker = guard, boom = true, damage = 1 })
assert(not ok, "the mod's own error still surfaces")
boxes = {}
eiWarnOutside()
assert(boxes[1] == "PREFIX", "state is reset after an error")
print("ok")
""", mods)


def test_magicant_check_skipped_in_menus(mods):
    run(r"""
assert(loadfile("MOD/main.lua"))()
load("tew/Magican't/main.lua")
trigger("initialized")
trigger("enterFrame")
menu = true
trigger("enterFrame") trigger("enterFrame")
menu = false
trigger("enterFrame")
assert(magicantCalls == 2, tostring(magicantCalls))
print("ok")
""", mods)


@pytest.mark.parametrize("enabled,flag,installed", [(False, True, True), (True, False, True), (True, True, False)])
def test_left_alone_when_off_or_not_installed(mods, enabled, flag, installed):
    run(r"""
assert(loadfile("MOD/main.lua"))()
assert(event.register == nativeRegister, "event.register is not wrapped")
load("KegDrip/main.lua")
load("Essential Indicators/main.lua")
load("tew/Magican't/main.lua")
trigger("initialized")
for i = 1, 4 do trigger("simulate", { delta = 0.5 }) end
assert(#kegCalls == 4)
menu = true trigger("enterFrame")
assert(magicantCalls == 1)
trigger("damage", { attacker = { reference = {} } })
assert(boxes[1] == "PREFIX")
print("ok")
""", mods, enabled=enabled, keg=flag, ei=flag, magicant=flag, installed=installed)


def test_defaults_on_only_when_the_mods_are_installed():
    script = r"""
package.path = [[SUITE/?.lua;]] .. package.path
local present = false
local files = { ["Data Files/MWSE/mods/KegDrip/main.lua"] = true, ["Data Files/MWSE/mods/Essential Indicators/main.lua"] = true,
  ["Data Files/MWSE/mods/tew/Magican't/main.lua"] = true }
lfs = { fileexists = function(path) return files[path:gsub("\\", "/")] and present or false end }
mwse = { loadConfig = function() return nil end, saveConfig = function() end, log = function() end }
tes3 = setmetatable({}, { __index = function() return function() return nil end end })
package.loaded["mwpluginpatches.config"] = nil
local off = require("mwpluginpatches.config")
assert(off.enabled == false)
assert(not off.kegDripCadenceEnabled and not off.essentialAttackerFilterEnabled and not off.magicantMenuGuardEnabled)
package.loaded["mwpluginpatches.config"] = nil
present = true
local on = require("mwpluginpatches.config")
assert(on.kegDripCadenceEnabled and on.essentialAttackerFilterEnabled and on.magicantMenuGuardEnabled)
assert(on.kegDripIntervalSeconds == 3)
print("ok")
""".replace("SUITE", SUITE)
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stdout + out.stderr


def test_mcm_lists_the_switches():
    with open(os.path.join(MOD, "mcm.lua"), encoding="utf-8") as f:
        text = f.read()
    for key in ("kegDripCadenceEnabled", "kegDripIntervalSeconds", "essentialAttackerFilterEnabled", "magicantMenuGuardEnabled"):
        assert 'id = "%s"' % key in text


def test_files_are_utf8_lf_without_bom():
    for rel in ("intercept.lua", "patches/kegDripCadence.lua", "patches/essentialAttackerFilter.lua",
                "patches/magicantMenuGuard.lua", "config.lua", "main.lua", "mcm.lua"):
        with open(os.path.join(MOD, rel), "rb") as f:
            data = f.read()
        assert not data.startswith(b"\xef\xbb\xbf") and b"\r\n" not in data, rel
        data.decode("utf-8")
