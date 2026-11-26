"""mwconsole's MCM: the selection details hotkey (Alt+I) goes through the template registry, its button opens
the details window, and nothing in the menu still refers to the removed mweffectinspector."""
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
LUAJIT = Path(os.environ.get("MWMANAGER_LUAJIT", ROOT / "tools" / "luajit" / "luajit.exe"))
MOD = ROOT / "lua tools" / "MWSE" / "mods" / "mwsuite" / "mwconsole"
pytestmark = pytest.mark.skipif(not LUAJIT.is_file(), reason="LuaJIT not available")

PRELUDE = r'''
local MOD, SAVED = arg[1], arg[2]
tes3 = { player = { id = "player" }, getFileSource = function() return nil end }
local calls = {}
mwse = {
    loadConfig = function(name, defaults)
        if SAVED == "old" then
            return { enabled = true, effects = { hotkey = { keyCode = 34, isAltDown = false, isShiftDown = true, isControlDown = false } } }
        end
        return defaults
    end,
    saveConfig = function() end,
}
local function stubModule(fields)
    return setmetatable(fields or {}, { __index = function() return function() end end })
end
package.preload["mwconsole.config"] = function() return assert(loadfile(MOD .. "/config.lua"))() end
package.preload["mwconsole.guard"] = function()
    return stubModule({ run = function(where, fn, ...) calls[#calls + 1] = { where = where, args = { ... } } return true, fn(...) end })
end
package.preload["mwconsole.registry"] = function() return stubModule({ commands = {}, list = function() return {} end }) end
package.preload["mwconsole.complete.index"] = function() return stubModule({ built = false }) end
package.preload["mwconsole.toggles"] = function() return stubModule({ LIST = {} }) end
package.preload["mwconsole.effects.window"] = function() return stubModule() end
local opened = {}
package.preload["mwconsole.selection.panel"] = function()
    return stubModule({ openDetails = function(ref) opened[#opened + 1] = ref end })
end
package.preload["mwconsole.user.commands"] = function() return stubModule({ WARNING = "dev only" }) end
package.preload["mwconsole.user.store"] = function() return stubModule({ BASE = "b", SCRIPTS = "s" }) end
package.preload["mwconsole.console_ui"] = function() return stubModule() end

local components, registered = {}, nil
local function component(kind, data)
    local c = setmetatable({ kind = kind, data = data or {}, components = {} }, { __index = function(t, k)
        return function(self, d)
            local child = component(k, type(d) == "table" and d or { label = d })
            components[#components + 1] = child
            return child
        end
    end })
    return c
end
mwse.mcm = {
    createTableVariable = function(d) return d end,
    createVariable = function(d) return d end,
    createTemplate = function(d)
        local t = component("template", d)
        t.register = function(self) registered = self end
        t.createSideBarPage = function(self, d2)
            local p = component("page", d2)
            p.sidebar = component("sidebar", {})
            return p
        end
        return t
    end,
}
local config = require("mwconsole.config")
local mcm = assert(loadfile(MOD .. "/mcm.lua"))()
local template = mcm.build(nil)
'''


def run_lua(body, saved="new"):
    script = PRELUDE + body
    result = subprocess.run([str(LUAJIT), "-", str(MOD), saved], input=script, capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr + result.stdout


def test_details_hotkey_is_registered_through_the_template():
    run_lua(r'''
assert(registered == template, "template:register() was not called")
local found
for _, c in ipairs(components) do
    if c.kind == "createKeyBinder" and c.data.variable and c.data.variable.id == "hotkey" then found = c end
end
assert(found, "no hotkey key binder")
assert(found.data.variable.table == config.panel, "the hotkey lives in config.panel")
assert(found.data.label == "Selection details hotkey", tostring(found.data.label))
local k = config.panel.hotkey
assert(k.keyCode == 23 and k.isAltDown and not k.isShiftDown and not k.isControlDown, "default Alt+I")
assert(config.effects.hotkey == nil, "no hotkey left under effects")
''')


def test_show_my_details_button_opens_the_details_window():
    run_lua(r'''
local btn
for _, c in ipairs(components) do
    if c.kind == "createButton" and c.data.buttonText == "Show my details now" then btn = c end
end
assert(btn and btn.data.description and #btn.data.description > 10, "button with a description")
btn.data.callback()
assert(#opened == 1 and opened[1] == tes3.player, "opens the details window on the player")
''')


def test_nothing_mentions_mweffectinspector():
    run_lua(r'''
for _, c in ipairs(components) do
    for _, key in ipairs({ "label", "description", "text", "buttonText" }) do
        local v = c.data[key]
        assert(type(v) ~= "string" or not v:lower():find("mweffectinspector", 1, true), c.kind .. " " .. tostring(v))
    end
end
''')


def test_an_older_saved_hotkey_moves_to_the_details_window():
    run_lua(r'''
local k = config.panel.hotkey
assert(k and k.keyCode == 34 and k.isShiftDown, "the saved key is kept")
assert(config.effects.hotkey == nil, "and removed from effects")
assert(config.panel.on == true, "other panel defaults still filled")
''', saved="old")
