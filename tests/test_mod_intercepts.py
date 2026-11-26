"""mwpluginpatches: rule-driven intercepts that replace old hand edits (Watch the Skies, Party Alchemy).

The target mods are faked here with small stand-ins written for the test; nothing of theirs is copied.
"""
import os
import subprocess

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MOD = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwpluginpatches").replace("\\", "/")
SUITE = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite").replace("\\", "/")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

# stand-ins: a util module whose metadataMissing shows a message then throws, and a main.lua that shows two messages
FAKE_UTIL = r"""local util = {}
function util.metadataMissing()
    tes3.messageBox({ message = "stand-in: metadata missing" })
    error("stand-in: metadata missing")
end
function util.other(a, b) return a + b, nil, "third" end
return util
"""
FAKE_PARTY = r"""tes3.messageBox("Switched to module: [%s]", "Vanilla NPC Style")
tes3.messageBox({ message = "Switched to module: [table form]" })
tes3.messageBox("[Party Alchemy] something else")
"""
FAKE_OTHER = r"""tes3.messageBox("Switched to module: [%s]", "not party alchemy")
"""


@pytest.fixture()
def mods(tmp_path):
    root = tmp_path / "mods"
    (root / "tew" / "Watch the Skies").mkdir(parents=True)
    (root / "tew" / "Watch the Skies" / "util.lua").write_text(FAKE_UTIL, encoding="utf-8")
    (root / "partyAlchemy").mkdir()
    (root / "partyAlchemy" / "main.lua").write_text(FAKE_PARTY, encoding="utf-8")
    (root / "someOtherMod").mkdir()
    (root / "someOtherMod" / "main.lua").write_text(FAKE_OTHER, encoding="utf-8")
    return str(root).replace("\\", "/")


BOOT = r"""
local handlers, logs, boxes = {}, {}, {}
event = { register = function(n, f) handlers[n] = f end }
mwse = { log = function(fmt, ...) logs[#logs + 1] = string.format(fmt, ...) end }
tes3 = { event = setmetatable({}, { __index = function(_, k) return k end }) }
tes3.messageBox = function(first, ...)
  local text = type(first) == "table" and first.message or string.format(first, ...)
  boxes[#boxes + 1] = text
  return "box"
end
local native = tes3.messageBox
package.path = "MODS/?.lua;" .. package.path
local config = setmetatable({
  enabled = ENABLED,
  wtsMetadataLogEnabled = WTS,
  partyAlchemyModuleBoxEnabled = PARTY,
  isWatchTheSkiesInstalled = function() return INSTALLED end,
  isPartyAlchemyInstalled = function() return INSTALLED end,
  isMwcaConsumerActive = function() return false end,
}, { __index = function(_, k) if k:match("^is") then return function() return false end end end })
table.insert(package.loaders, 2, function(name)
  if name == "mwpluginpatches.config" then return function() return config end end
  if name == "mwpluginpatches.intercept" then return assert(loadfile("MOD/intercept.lua")) end
  if name == "mwpluginpatches.patches.wtsMetadataLog" then return assert(loadfile("MOD/patches/wtsMetadataLog.lua")) end
  if name == "mwpluginpatches.patches.partyAlchemyModuleBox" then return assert(loadfile("MOD/patches/partyAlchemyModuleBox.lua")) end
  if name:match("^mwpluginpatches%.patches%.") then return function() return { init = function() end } end end
end)
local function joined(t) return table.concat(t, "|") end
"""


def run(script, mods, enabled=True, wts=True, party=True, installed=True):
    script = (BOOT + script).replace("MODS", mods).replace("SUITE", SUITE).replace("MOD", MOD)
    for key, value in (("ENABLED", enabled), ("WTS", wts), ("PARTY", party), ("INSTALLED", installed)):
        script = script.replace(key, str(value).lower())
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stdout + out.stderr


def test_wts_error_is_logged_when_util_loads_after_mwpluginpatches(mods):
    run(r"""
assert(loadfile("MOD/main.lua"))()
local util = require("tew.Watch the Skies.util")
local ok, err = pcall(util.metadataMissing)
assert(ok, "the error must not escape: " .. tostring(err))
assert(boxes[1] == "stand-in: metadata missing", "the mod's own message still shows")
assert(joined(logs):find("Watch the Skies: metadataMissing() raised an error", 1, true), joined(logs))
local a, b, c = util.other(2, 3)
assert(a == 5 and b == nil and c == "third", "other functions are untouched")
assert(require("tew.Watch the Skies.util") == util)
print("ok")
""", mods)


def test_wts_already_loaded_module_is_wrapped_in_place(mods):
    run(r"""
local util = require("tew.Watch the Skies.util")
assert(loadfile("MOD/main.lua"))()
assert(pcall(util.metadataMissing), "wrapped in place")
print("ok")
""", mods)


def test_wts_guard_passes_return_values_and_wraps_once(mods):
    run(r"""
local util = require("tew.Watch the Skies.util")
util.metadataMissing = function() return 1, nil, 3 end
assert(loadfile("MOD/main.lua"))()
local patch = require("mwpluginpatches.patches.wtsMetadataLog")
local first = util.metadataMissing
assert(patch.init() == true, "already active")
assert(require("mwpluginpatches.intercept").errorToLog({ label = "x", module = "tew.Watch the Skies.util", fn = "metadataMissing" }) == false,
  "a second wrap is refused")
assert(util.metadataMissing == first)
local a, b, c = util.metadataMissing()
assert(a == 1 and b == nil and c == 3)
print("ok")
""", mods)


@pytest.mark.parametrize("enabled,wts,installed", [(False, True, True), (True, False, True), (True, True, False)])
def test_wts_left_alone_when_off_or_not_installed(mods, enabled, wts, installed):
    run(r"""
assert(loadfile("MOD/main.lua"))()
local util = require("tew.Watch the Skies.util")
local ok, err = pcall(util.metadataMissing)
assert(not ok and tostring(err):find("stand-in: metadata missing", 1, true), "the error is the mod's own")
print("ok")
""", mods, enabled=enabled, wts=wts, installed=installed)


def test_party_alchemy_module_message_is_hidden_only_from_party_alchemy(mods):
    run(r"""
assert(loadfile("MOD/main.lua"))()
assert(tes3.messageBox ~= native)
assert(loadfile("MODS/partyAlchemy/main.lua"))()
assert(loadfile("MODS/someOtherMod/main.lua"))()
assert(tes3.messageBox("plain %s", "text") == "box", "other calls return what the game returns")
assert(joined(boxes) == "[Party Alchemy] something else|Switched to module: [not party alchemy]|plain text", joined(boxes))
print("ok")
""", mods)


@pytest.mark.parametrize("enabled,party,installed", [(False, True, True), (True, False, True), (True, True, False)])
def test_party_alchemy_left_alone_when_off_or_not_installed(mods, enabled, party, installed):
    run(r"""
assert(loadfile("MOD/main.lua"))()
assert(tes3.messageBox == native, "messageBox is not wrapped")
assert(loadfile("MODS/partyAlchemy/main.lua"))()
assert(#boxes == 3)
print("ok")
""", mods, enabled=enabled, party=party, installed=installed)


def test_defaults_on_only_when_the_mod_is_installed():
    script = r"""
package.path = [[SUITE/?.lua;]] .. package.path
local present = false
lfs = { fileexists = function(path)
  path = path:gsub("\\", "/")
  if path == "Data Files/MWSE/mods/tew/Watch the Skies/util.lua" or path == "Data Files/MWSE/mods/partyAlchemy/main.lua" then
    return present
  end
  return false
end }
mwse = { loadConfig = function() return nil end, saveConfig = function() end, log = function() end }
tes3 = setmetatable({}, { __index = function() return function() return nil end end })
package.loaded["mwpluginpatches.config"] = nil
local off = require("mwpluginpatches.config")
assert(off.enabled == false, "the master switch defaults off")
assert(off.wtsMetadataLogEnabled == false and off.partyAlchemyModuleBoxEnabled == false)
package.loaded["mwpluginpatches.config"] = nil
present = true
local on = require("mwpluginpatches.config")
assert(on.wtsMetadataLogEnabled == true and on.partyAlchemyModuleBoxEnabled == true)
assert(on.isWatchTheSkiesInstalled() and on.isPartyAlchemyInstalled())
print("ok")
""".replace("SUITE", SUITE)
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stdout + out.stderr


def test_mcm_lists_both_switches():
    with open(os.path.join(MOD, "mcm.lua"), encoding="utf-8") as f:
        text = f.read()
    for key in ("wtsMetadataLogEnabled", "partyAlchemyModuleBoxEnabled"):
        assert 'id = "%s"' % key in text


def test_rule_files_are_utf8_lf_without_bom():
    for rel in ("intercept.lua", "patches/wtsMetadataLog.lua", "patches/partyAlchemyModuleBox.lua", "config.lua", "main.lua", "mcm.lua"):
        with open(os.path.join(MOD, rel), "rb") as f:
            data = f.read()
        assert not data.startswith(b"\xef\xbb\xbf") and b"\r\n" not in data, rel
        data.decode("utf-8")
