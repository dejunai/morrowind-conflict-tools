"""Arrille's unrelated duplicate-door fix survives retirement of the lock workaround."""
import os
import subprocess

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MODS = os.path.join(ROOT, "Data Files", "MWSE", "mods", "mwsuite")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")


def run(script):
    result = subprocess.run([LUAJIT, "-"], input=script.replace("MODS", MODS),
                            text=True, capture_output=True, timeout=60, cwd=ROOT)
    assert result.returncode == 0 and result.stdout.strip().endswith("ok"), result.stdout + result.stderr


def test_arrille_rental_door_and_unrelated_activations():
    run(r'''
package.path = [[MODS\?.lua;]] .. package.path
local handlers, rent, activated = {}, 1, nil
tes3 = {
  objectType = { door = 1 },
  event = { activate = "activate", cellChanged = "cellChanged" },
  player = { activate = function(_, ref) activated = ref end },
  getLocked = function(p) return p.reference.locked end,
  unlock = function(p) p.reference.locked = false end,
  getGlobal = function() return rent end,
}
mwse = { log = function() end }
event = { register = function(name, fn, opts) handlers[name .. opts.priority] = fn end }
local mod = require("mwpluginpatches.patches.arrilleInnDoors")
mod.init()
local state = { disabled = false }
local cell = { id = "Seyda Neen, Arrille's Tradehouse" }
local trap = setmetatable({
  object = { id = "dim_com_m_trapdoor_b", objectType = 1 }, cell = cell,
  disable = function() state.disabled = true end, enable = function() state.disabled = false end,
}, {
  __index = function(_, k) if k == "disabled" then return state.disabled end end,
  __newindex = function(t, k, v) if k == "disabled" then error("read-only") end rawset(t, k, v) end,
})
local rental = { object = { id = "Rent_Arrille_Door", objectType = 1 }, cell = cell,
                 locked = true, lockNode = { locked = true }, data = {} }
local doors = { trap, rental }
function cell:iterateReferences()
  local i = 0
  return function() i = i + 1; return doors[i] end
end
local function activate(ref) return handlers.activate9400({ target = ref, activator = tes3.player }) end
assert(activate(trap) == false and trap.disabled and activated == rental)
assert(not rental.locked and not rental.lockNode.locked and rental.data.ab01drlkbl == 1)
handlers.activate9000({ target = rental })
assert(rental.data.ab01drlkbl == nil)
rental.data.ab01drlkbl = 1
activate(rental)
handlers.activate9000({ target = rental })
assert(rental.data.ab01drlkbl == 1, "existing abot blacklist must survive")
rent = 0
handlers.cellChanged0({ cell = cell })
assert(not trap.disabled)
rent = 1
handlers.cellChanged0({ cell = cell })
assert(trap.disabled)
local other = { object = { id = "other", objectType = 1 }, cell = cell, locked = true, data = {} }
assert(activate(other) == nil and other.locked and not other.data.ab01drlkbl)
print("ok")
''')


@pytest.mark.parametrize(
    ("legacy", "modern", "expected"),
    [("true", "nil", "true"), ("false", "nil", "false"), ("true", "false", "false")],
)
def test_old_switch_migrates_without_overwriting_new_setting(legacy, modern, expected):
    run(r'''
package.path = [[MODS\?.lua;]] .. package.path
local stored = { doorLockCompatibilityEnabled = LEGACY, doorLockedNotification = true,
                 arrilleInnCompatibilityEnabled = MODERN }
local saved
mwse = {
  loadConfig = function(name) if name == "mwpluginpatches" then return stored end end,
  saveConfig = function(_, c) saved = c end,
  log = function() end,
}
tes3 = setmetatable({}, { __index = function() return function() return nil end end })
lfs = { fileexists = function() return false end }
local config = require("mwpluginpatches.config")
assert(config.arrilleInnCompatibilityEnabled == EXPECTED)
assert(saved and saved.arrilleInnCompatibilityEnabled == EXPECTED)
assert(saved.doorLockCompatibilityEnabled == nil and saved.doorLockedNotification == nil)
print("ok")
'''.replace("LEGACY", legacy).replace("MODERN", modern).replace("EXPECTED", expected))


@pytest.mark.parametrize(("improved", "squat", "expected"), [
    ("true", "true", "true"), ("true", "false", "false"), ("false", "true", "false"),
])
def test_new_arrille_default_requires_both_plugins(improved, squat, expected):
    run(r'''
package.path = [[MODS\?.lua;]] .. package.path
mwse = { loadConfig = function() return nil end, saveConfig = function() end, log = function() end }
tes3 = setmetatable({
  isModActive = function(name)
    if name == "Improved Inns Expanded.esp" then return IMPROVED end
    if name == "Seyda Neen - Damp Little Squat - unshabby.ESP" then return SQUAT end
    return false
  end,
}, { __index = function() return function() return nil end end })
lfs = { fileexists = function() return false end }
local config = require("mwpluginpatches.config")
assert(config.arrilleInnCompatibilityEnabled == EXPECTED)
print("ok")
'''.replace("IMPROVED", improved).replace("SQUAT", squat).replace("EXPECTED", expected))
