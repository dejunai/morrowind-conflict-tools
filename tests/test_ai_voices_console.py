"""Voices of Vvardenfell's console lines: held back by our own Lua, never by editing that mod."""
import os
import subprocess

import pytest

import mwdialog_luafix as L

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MOD = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwpluginpatches").replace("\\", "/")


def test_it_is_not_a_known_bug():
    assert not [bug for bug in L.KNOWN_BUGS if "ai voices" in bug[2].lower()]


SCRIPT = r"""
local enabled, active = ...
local printed, handlers = {}, {}
event = { register = function(n, f) handlers[n] = f end }
mwse = { log = function() end }
tes3 = { event = setmetatable({}, { __index = function(_, k) return k end }) }
tes3ui = { logToConsole = function(text, isCommand) printed[#printed + 1] = tostring(text) .. (isCommand and "!" or ""); return "native" end }
local native = tes3ui.logToConsole
local config = setmetatable({ enabled = true, aiVoicesConsoleEnabled = ENABLED, isAiVoicesActive = function() return ACTIVE end },
  { __index = function(_, k) if k:match("^is") then return function() return false end end end })
table.insert(package.loaders, 2, function(name)
  if name == "mwpluginpatches.config" then return function() return config end end
  if name == "mwpluginpatches.patches.aiVoicesConsole" then return assert(loadfile("MOD/patches/aiVoicesConsole.lua")) end
  if name:match("^mwpluginpatches%.patches%.") then return function() return { init = function() end } end end
end)
assert(loadfile("MOD/main.lua"))()
handlers.initialized()
tes3ui.logToConsole("VoV: Playing Line at Vo\\AIV\\a.mp3")
tes3ui.logToConsole("VoV: Missing Line at Vo\\AIV\\b.mp3")
assert(tes3ui.logToConsole("player->additem gold_001 1", true) == "native")
tes3ui.logToConsole("another mod: VoV: Playing Line at x")
if ENABLED and ACTIVE then
  assert(table.concat(printed, "|") == "player->additem gold_001 1!|another mod: VoV: Playing Line at x", table.concat(printed, "|"))
else
  assert(tes3ui.logToConsole == native and #printed == 4, "left alone")
end
"""


@pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")
@pytest.mark.parametrize("enabled,active", [(True, True), (False, True), (True, False)])
def test_only_those_two_messages_are_held_back(enabled, active):
    script = SCRIPT.replace("MOD", MOD).replace("ENABLED", str(enabled).lower()).replace("ACTIVE", str(active).lower())
    got = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True)
    assert got.returncode == 0, got.stderr
