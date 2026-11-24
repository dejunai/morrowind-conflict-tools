"""The Personal Effects repair is a mwpluginpatches patch: on by default only when Personal Effects is active."""
import os
import subprocess

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MODS = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")


def run_lua(body, *, stored="nil", active=False):
    prelude = r'''
local storedConfig = STORED_CONFIG
local pluginActive = PLUGIN_ACTIVE
overrides = {}
mwse = {
  loadConfig = function(name) if name == "mwpluginpatches" then return storedConfig end end,
  saveConfig = function() end,
  overrideScript = function(name, callback) overrides[name] = callback end,
  log = function() end,
  mcm = {},
}
tes3 = {
  event = { initialized = "initialized", modConfigReady = "modConfigReady", loaded = "loaded",
    cellChanged = "cellChanged", uiActivated = "uiActivated" },
  uiEvent = { destroy = "destroy" },
  objectType = { container = "container", npc = "npc" },
  isModActive = function(name) return pluginActive and name == "Personal Effects.ESP" end,
  getObject = function() return nil end,
  getScript = function() return nil end,
  findGlobal = function() return nil end,
  findDialogue = function() return nil end,
}
tes3ui = { registerID = function(id) return id end }
event = { register = function() end }
timer = { real = "real", start = function() end, frame = { delayOneFrame = function() end } }
mwscript = { stopScript = function() end }
package.path = [[MODS]] .. "/?.lua;" .. package.path
function check(ok, message) if not ok then error(message, 2) end end
'''
    script = (prelude.replace("STORED_CONFIG", stored)
              .replace("PLUGIN_ACTIVE", "true" if active else "false")
              .replace("MODS", MODS.replace("\\", "/")) + body + '\nprint("ok")\n')
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stdout + out.stderr


def test_defaults_to_on_only_when_personal_effects_is_active():
    run_lua(r'''
local config = require("mwpluginpatches.config")
check(config.personalEffectsEnabled == true, "on by default with Personal Effects active")
''', active=True)
    run_lua(r'''
local config = require("mwpluginpatches.config")
check(config.personalEffectsEnabled == false, "off by default without Personal Effects")
''', active=False)
    run_lua(r'''
local config = require("mwpluginpatches.config")
check(config.personalEffectsEnabled == false, "a saved opt-out wins over the default")
''', stored="{ personalEffectsEnabled = false }", active=True)


def test_repairs_register_only_when_enabled_and_personal_effects_is_active():
    run_lua(r'''
require("mwpluginpatches.patches.personalEffects").init()
check(next(overrides) == nil, "an unrelated load order is not patched")
''', stored="{ personalEffectsEnabled = true }", active=False)
    run_lua(r'''
require("mwpluginpatches.patches.personalEffects").init()
check(next(overrides) == nil, "a saved opt-out registers no overrides")
''', stored="{ personalEffectsEnabled = false }", active=True)
    run_lua(r'''
require("mwpluginpatches.patches.personalEffects").init()
local count = 0
for _ in pairs(overrides) do count = count + 1 end
check(count == 3, "the patch overrides all three Personal Effects scripts")
''', active=True)
