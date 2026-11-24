"""mwcriminal: with "Picking a loading door only unlocks it" on, Modern Lockpicking's shouldOpen() says no for a door
that leads to another cell (it stays unlocked and shut); other doors, containers, and the switch off are untouched."""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MAIN = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwcriminal", "main.lua").replace("\\", "/")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

SCRIPT = r"""
local handlers = {}
event = { register = function(name, fn) if name == "initialized" then handlers.initialized = fn end end }
mwse = { log = function() end, saveConfig = function() end, loadConfig = function() return nil end }
lfs = { fileexists = function() return false end, directoryexists = function() return false end }
timer = { start = function() end, simulate = 1 }
tes3 = { event = setmetatable({}, { __index = function(_, k) return k end }),
         objectType = { door = "door", container = "container", sound = "sound" },
         getSound = function() return nil end, getFileExists = function() return false end }
local config = { enabled = ENABLED, noLoadDoorOnPick = SWITCH }
local lockController = { shouldOpen = function() return true end }
package.preload["mwcriminal.config"] = function() return config end
package.preload["mwcriminal.core"] = function() return {} end
package.preload["mwcriminal.interop"] = function() return {} end
package.preload["mwcriminal.inspectorUI"] = function() return {} end
package.preload["tauer.modern-lockpicking.services.locks.lockController"] = function() return lockController end
assert(loadfile("MAIN"))()
handlers.initialized()
local loading = { object = { objectType = "door" }, destination = { cell = {} } }
local plain = { object = { objectType = "door" } }
local chest = { object = { objectType = "container" } }
print(tostring(lockController.shouldOpen(loading)) .. " " .. tostring(lockController.shouldOpen(plain))
      .. " " .. tostring(lockController.shouldOpen(chest)))
"""


@pytest.mark.parametrize("enabled, switch, want", [
    (True, True, "false true true"),      # only the loading door stays shut
    (True, False, "true true true"),      # switch off: Modern Lockpicking as it is
    (False, True, "true true true"),      # mwcriminal off: nothing changes
])
def test_picked_loading_door_only_unlocks(tmp_path, enabled, switch, want):
    f = tmp_path / "t.lua"
    f.write_text(SCRIPT.replace("MAIN", MAIN).replace("ENABLED", str(enabled).lower())
                 .replace("SWITCH", str(switch).lower()), encoding="utf-8")
    r = subprocess.run([LUAJIT, str(f)], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == want, r.stderr + r.stdout
