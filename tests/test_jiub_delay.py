"""mwpluginpatches: Friends & Frens Jiub companion delay unloads once the delay is reached."""
import os
import subprocess

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MOD = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwpluginpatches").replace("\\", "/")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

RUMOR = "1453113367223718194"

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
local vanilla = { id = "chargen name", head = { id = "headA" }, hair = { id = "hairA" } }
local companion = { id = "aa_comp_jiub", head = { id = "headB" }, hair = { id = "hairB" } }
charGen = { value = -1 }
tes3 = {
  event = setmetatable({}, { __index = function(_, k) return k end }),
  findGlobal = function(id) if id == "CharGenState" then return charGen end return nil end,
  getObject = function(id) if id == "chargen name" then return vanilla end if id == "aa_comp_jiub" then return companion end return nil end,
  player = { data = {} },
}
local config = {
  enabled = true,
  jiubDelayEnabled = FLAG,
  jiubDelayMinutes = 1,
  jiubSyncAppearance = true,
  jiubExcludeCensusOffice = true,
  isFriendsAndFrensActive = function() return ACTIVE end,
}
table.insert(package.loaders, 2, function(name)
  if name == "mwpluginpatches.config" then return function() return config end end
  if name == "mwpluginpatches.intercept" then return assert(loadfile("MOD/intercept.lua")) end
end)
local patch = assert(loadfile("MOD/patches/jiubDelay.lua"))()
local function armed()
  return #(list("simulate")) == 1 and #(list("infoFilter")) == 1 and #(list("mobileActivated")) == 1
end
local function unloaded()
  return #(list("simulate")) == 0 and #(list("infoFilter")) == 0 and #(list("mobileActivated")) == 0 and #(list("loaded")) == 1
end
local function rumor(ref)
  ref = ref or { object = { id = "some npc" }, cell = { id = "Balmora", editorName = "Balmora" } }
  return trigger("infoFilter", { passes = true, info = { id = "RUMOR" }, reference = ref })
end
"""


def run(script, flag=True, active=True):
    script = (BOOT + script).replace("MOD/", MOD + "/").replace("RUMOR", RUMOR)
    for key, value in (("FLAG", flag), ("ACTIVE", active)):
        script = script.replace(key, str(value).lower())
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stdout + out.stderr


def test_counts_after_chargen_then_unloads():
    run(r"""
tes3.player = nil
assert(patch.init() == true)
assert(#list("loaded") == 1 and not armed(), "init only registers loaded while no game is loaded")
tes3.player = { data = {} }
trigger("loaded")
assert(armed())
-- still in chargen: the clock does not run
charGen.value = 10
trigger("simulate", { delta = 60 })
assert((tes3.player.data.mwpluginpatches_jiub.secondsSinceCensus or 0) == 0)
charGen.value = -1
trigger("simulate", { delta = 30 })
assert(tes3.player.data.mwpluginpatches_jiub.secondsSinceCensus == 30)
assert(armed())
local e = rumor()
assert(e.passes == false, "held back during the delay")
trigger("simulate", { delta = 30 })
assert(tes3.player.data.mwpluginpatches_jiub.unlockedLogged == true)
assert(unloaded(), "every working handler comes off; loaded stays")
-- a later rumor no longer goes through our filter (the delay is over)
local e2 = rumor()
assert(e2.passes == true)
print("ok")
""")


def test_census_office_blocked_while_armed():
    run(r"""
assert(patch.init())
trigger("loaded")
charGen.value = -1
local e = rumor({ object = { id = "imperial guard" }, cell = { id = "Seyda Neen, Census and Excise Office", editorName = "" } })
assert(e.passes == false)
local e2 = rumor({ object = { id = "sellus gravius" }, cell = { id = "Seyda Neen", editorName = "" } })
assert(e2.passes == false)
assert(armed())
print("ok")
""")


def test_save_load_with_delay_already_reached_unloads():
    run(r"""
tes3.player.data.mwpluginpatches_jiub = { secondsSinceCensus = 120, unlockedLogged = true }
assert(patch.init())
-- init saw tes3.player and ran onLoaded
assert(unloaded())
assert(companion.head == vanilla.head and companion.hair == vanilla.hair, "appearance synced as it unloads")
print("ok")
""")


def test_new_game_later_in_the_session_rearms():
    run(r"""
tes3.player.data.mwpluginpatches_jiub = { secondsSinceCensus = 120, unlockedLogged = true }
assert(patch.init())
assert(unloaded())
-- a later new game: fresh player data, delay not reached
tes3.player.data = {}
charGen.value = -1
trigger("loaded")
assert(armed())
trigger("simulate", { delta = 10 })
assert(tes3.player.data.mwpluginpatches_jiub.secondsSinceCensus == 10)
assert(rumor().passes == false)
trigger("simulate", { delta = 50 })
assert(unloaded())
print("ok")
""")


def test_left_alone_when_off_or_fnf_missing():
    run(r"""
assert(patch.init() == false)
assert(#list("loaded") == 0 and #list("simulate") == 0)
print("ok")
""", flag=False, active=True)
    run(r"""
assert(patch.init() == false)
assert(#list("loaded") == 0)
print("ok")
""", flag=True, active=False)


def test_files_are_utf8_lf_without_bom():
    path = os.path.join(MOD, "patches", "jiubDelay.lua")
    with open(path, "rb") as f:
        data = f.read()
    assert not data.startswith(b"\xef\xbb\xbf") and b"\r\n" not in data
    data.decode("utf-8")