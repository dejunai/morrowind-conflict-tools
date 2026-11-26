"""mwpluginpatches: MWCA.interop stub for Animated Containers addons."""
import os
import subprocess

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MOD = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwpluginpatches").replace("\\", "/")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")


SUITE = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite").replace("\\", "/")

def run(script):
    script = script.replace("SUITE", SUITE).replace("MOD", MOD)
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stdout + out.stderr


BOOT = r"""
event = { register = function() end }
mwse = { log = function(fmt, ...) end }
tes3 = { event = setmetatable({}, { __index = function(_, k) return k end }) }
local present = { consumers = CONSUMERS, real = REAL }
lfs = { fileexists = function(path)
  path = path:gsub("\\", "/")
  if path == "Data Files/MWSE/mods/MWCA/interop.lua" then return present.real end
  if path == "Data Files/MWSE/mods/herbert100/animated containers/main.lua"
      or path == "Data Files/MWSE/mods/oaab/mwca/main.lua"
      or path == "Data Files/MWSE/mods/x32/mwca/main.lua" then
    return present.consumers
  end
  return false
end }
local config = setmetatable({
  enabled = ENABLED,
  mwcaInteropEnabled = PATCH,
  isMwcaConsumerActive = function() return present.consumers end,
}, { __index = function(_, k) if k:match("^is") then return function() return false end end end })
table.insert(package.loaders, 2, function(name)
  if name == "mwpluginpatches.config" then return function() return config end end
  if name == "mwpluginpatches.patches.mwcaInterop" then return assert(loadfile("MOD/patches/mwcaInterop.lua")) end
  if name:match("^mwpluginpatches%.patches%.") then return function() return { init = function() end } end end
end)
local function include(name)
  if package.loaded[name] ~= nil then return package.loaded[name] end
  local loader = package.preload[name]
  if loader then
    local mod = loader(name)
    package.loaded[name] = mod
    return mod
  end
  return nil
end
"""


def test_file_scope_init_lets_addons_register_before_herbert_reads():
    run(BOOT.replace("CONSUMERS", "true").replace("REAL", "false")
        .replace("ENABLED", "true").replace("PATCH", "true") + r"""
assert(loadfile("MOD/main.lua"))()
-- as oaab/mwca/main.lua and x32/mwca/main.lua do at file scope
local mwca = include("MWCA.interop")
assert(type(mwca) == "table", "the stub must exist before the addons load")
mwca["oaab\\o\\comrchcloset.nif"] = { "oaab\\o\\comrchclosetac.nif", 1, 2, 0.5, 0.5, "AC_closet_open", "AC_closet_close", 0 }
mwca["x32\\o\\gard_chest.nif"] = { "x32\\o\\gard_chest.nif", 1, 2, 0.5, 0.5, "AB_ContChestOpen", "AB_ContChestClose", 0 }
-- as herbert does later, on initialized
local old = include("MWCA.interop")
assert(old == mwca, "herbert must see the same table the addons wrote")
assert(old["oaab\\o\\comrchcloset.nif"][1] == "oaab\\o\\comrchclosetac.nif")
assert(old["x32\\o\\gard_chest.nif"][6] == "AB_ContChestOpen")
print("ok")
""")


def test_off_when_master_or_patch_or_consumers_are_off():
    for enabled, patch, consumers in (
        ("false", "true", "true"),
        ("true", "false", "true"),
        ("true", "true", "false"),
    ):
        run(BOOT.replace("CONSUMERS", consumers).replace("REAL", "false")
            .replace("ENABLED", enabled).replace("PATCH", patch) + r"""
assert(loadfile("MOD/main.lua"))()
assert(include("MWCA.interop") == nil, "the stub stays off")
assert(package.loaded["MWCA.interop"] == nil)
assert(package.preload["MWCA.interop"] == nil)
print("ok")
""")


def test_existing_interop_file_is_left_alone():
    run(BOOT.replace("CONSUMERS", "true").replace("REAL", "true")
        .replace("ENABLED", "true").replace("PATCH", "true") + r"""
package.loaded["MWCA.interop"] = { kept = true }
assert(loadfile("MOD/main.lua"))()
local mwca = include("MWCA.interop")
assert(mwca and mwca.kept == true and mwca[1] == nil, "a real interop table is not replaced")
print("ok")
""")


def test_defaults_on_only_when_a_consumer_is_present():
    run(r"""
package.path = [[SUITE\?.lua;]] .. package.path
local present = false
lfs = { fileexists = function(path)
  path = path:gsub("\\", "/")
  if path == "Data Files/MWSE/mods/oaab/mwca/main.lua" then return present end
  return false
end }
mwse = { loadConfig = function() return nil end, saveConfig = function() end, log = function() end }
tes3 = setmetatable({}, { __index = function() return function() return nil end end })
package.loaded["mwpluginpatches.config"] = nil
present = false
local off = require("mwpluginpatches.config")
assert(off.isMwcaConsumerActive() == false and off.mwcaInteropEnabled == false)
package.loaded["mwpluginpatches.config"] = nil
present = true
local on = require("mwpluginpatches.config")
assert(on.isMwcaConsumerActive() == true and on.mwcaInteropEnabled == true)
print("ok")
""")
