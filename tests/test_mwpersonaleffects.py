"""The extracted Personal Effects repair is opt-in and gated on its target plugin."""
import os
import subprocess

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MODS = os.path.join(ROOT, "Data Files", "MWSE", "mods")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")


def run_lua(body, *, stored="nil", legacy="nil", active=False):
    prelude = r'''
local storedConfig = STORED_CONFIG
local legacyConfig = LEGACY_CONFIG
local pluginActive = PLUGIN_ACTIVE
handlers, overrides = {}, {}
mwse = {
  loadConfig = function(name)
    if name == "mwpersonaleffects" then return storedConfig end
    if name == "mwpluginpatches" then return legacyConfig end
  end,
  overrideScript = function(name, callback) overrides[name] = callback end,
  log = function() end,
  mcm = {},
}
tes3 = {
  event = { initialized = "initialized", modConfigReady = "modConfigReady", loaded = "loaded",
    cellChanged = "cellChanged", uiActivated = "uiActivated" },
  uiEvent = { destroy = "destroy" },
  objectType = { container = "container", npc = "npc" },
  isModActive = function() return pluginActive end,
  getObject = function() return nil end,
  getScript = function() return nil end,
}
tes3ui = { registerID = function(id) return id end }
event = { register = function(name, callback) handlers[name] = callback end }
timer = {
  real = "real",
  start = function() end,
  frame = { delayOneFrame = function() end },
}
mwscript = { stopScript = function() end }
package.path = [[MODS\?.lua;]] .. package.path
function check(ok, message) if not ok then error(message, 2) end end
'''
    script = (prelude.replace("STORED_CONFIG", stored)
              .replace("LEGACY_CONFIG", legacy)
              .replace("PLUGIN_ACTIVE", "true" if active else "false")
              .replace("MODS", MODS) + body + '\nprint("ok")\n')
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stdout + out.stderr


def test_legacy_setting_only_migrates_when_legacy_bundle_was_active():
    run_lua(r'''
local config = require("mwpersonaleffects.config")
check(not config.enabled, "legacy opt-in does not survive when the old bundle was off")
''', legacy="{ enabled = false, personalEffectsFixEnabled = true }")
    run_lua(r'''
local config = require("mwpersonaleffects.config")
check(config.enabled, "an effective legacy opt-in is preserved")
''', legacy="{ enabled = true, personalEffectsFixEnabled = true }")
    run_lua(r'''
local config = require("mwpersonaleffects.config")
check(not config.enabled, "a saved standalone opt-out overrides the legacy setting")
''', stored="{ enabled = false }", legacy="{ enabled = true, personalEffectsFixEnabled = true }")


def test_repairs_register_only_when_enabled_and_personal_effects_is_active():
    run_lua(r'''
require("mwpersonaleffects.main")
handlers.initialized()
check(next(overrides) == nil, "disabled standalone module registers no overrides")
''', stored="{ enabled = false }", active=True)
    run_lua(r'''
require("mwpersonaleffects.main")
handlers.initialized()
check(next(overrides) == nil, "module does not patch unrelated load orders")
''', stored="{ enabled = true }", active=False)
    run_lua(r'''
require("mwpersonaleffects.main")
handlers.initialized()
local count = 0
for _ in pairs(overrides) do count = count + 1 end
check(count == 3, "enabled module overrides all three Personal Effects scripts")
''', stored="{ enabled = true }", active=True)
