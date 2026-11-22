"""MCA setup options use the original questionnaire values."""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LUAJIT = Path(os.environ.get("MWMANAGER_LUAJIT", ROOT / "tools" / "luajit" / "luajit.exe"))
MODS = ROOT / "Data Files" / "MWSE" / "mods" / "mwsuite"
pytestmark = pytest.mark.skipif(not LUAJIT.is_file(), reason="LuaJIT not available")


def run(script):
    result = subprocess.run([str(LUAJIT), "-"], input=script.replace("MODS", str(MODS)),
                            capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr


def test_original_mca_options_and_values():
    run(r'''
local settings = {}
local node = {}
local function newNode()
    local n = { sidebar = node }
    return setmetatable(n, { __index = function(_, key)
        if key == "register" then return function() end end
        if key:match("^create") then return function(_, data)
            if type(data) == "table" and data.variable and data.variable.id then
                settings[data.variable.id] = { kind = key, data = data }
            end
            return newNode()
        end end
    end })
end
node.createInfo = function() end
local config = setmetatable({ save = function() end }, { __index = function(_, key)
    if key:match("^is") then return function() return false end end
end })
package.preload["mwpluginpatches.config"] = function() return config end
mwse = { mcm = {
    createTemplate = function() return newNode() end,
    createTableVariable = function(data) return data end,
} }
assert(loadfile([[MODS\mwpluginpatches\mcm.lua]]))()
local party = settings.mcaPartySize
assert(party.kind == "createDropdown" and party.data.description)
for i, option in ipairs({ "2-5", "2-10", "2-20" }) do
    assert(party.data.options[i].label == option and party.data.options[i].value == i - 1)
end
assert(#party.data.options == 3)
assert(settings.arrilleInnCompatibilityEnabled and not settings.doorLockCompatibilityEnabled)
assert(not settings.doorLockedNotification)
local courtesans = settings.mcaCourtesans.data.options
for i, pair in ipairs({ {"Enable", "all"}, {"Disable", "none"}, {"Disable male only", "female"},
                         {"Disable female only", "male"} }) do
    assert(courtesans[i].label == pair[1] and courtesans[i].value == pair[2])
end
''')


def test_invalid_legacy_party_size_is_repaired_and_reported():
    run(r'''
package.path = [[MODS\?.lua;]] .. package.path
local saved, logged
mwse = {
    loadConfig = function(name) if name == "mwpluginpatches" then return { mcaPartySize = 3 } end end,
    saveConfig = function(_, value) saved = value.mcaPartySize end,
    log = function(message) logged = message end,
}
tes3 = setmetatable({}, { __index = function() return function() return nil end end })
lfs = { fileexists = function() return false end }
local config = require("mwpluginpatches.config")
assert(config.mcaPartySize == 2 and saved == 2 and logged:find("invalid", 1, true))
''')


def test_invalid_party_size_in_initialized_save_is_repaired():
    run(r'''
package.path = [[MODS\?.lua;]] .. package.path
local config = { mcaEnabled = true, mcaPartySize = 2, euEnabled = false,
                 isMcaActive = function() return true end }
package.preload["mwpluginpatches.config"] = function() return config end
local globals = { MCA_Loaded = { value = 1 }, MCA_MoreEnemies = { value = 3 } }
tes3 = { findGlobal = function(name) return globals[name] end }
local logs = 0
mwse = { log = function() logs = logs + 1 end }
local startup = require("mwpluginpatches.patches.autoStartup")
startup.applyStartupConfig()
assert(globals.MCA_MoreEnemies.value == 2 and logs == 1)
globals.MCA_MoreEnemies.value = 1
startup.applyStartupConfig()
assert(globals.MCA_MoreEnemies.value == 1 and logs == 1)
config.mcaEnabled = false
globals.MCA_MoreEnemies.value = 3
startup.applyStartupConfig()
assert(globals.MCA_MoreEnemies.value == 3 and logs == 1)
''')
