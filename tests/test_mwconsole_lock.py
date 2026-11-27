"""mwconsole: the selection panel must never end up above the console (the engine only picks world objects for the
console while MenuConsole is the top menu), and the details hotkey (Alt+I) works with the console open without
typing into the console or reacting to a plain 'i'."""
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
LUAJIT = Path(os.environ.get("MWMANAGER_LUAJIT", ROOT / "tools" / "luajit" / "luajit.exe"))
MOD = ROOT / "lua tools" / "MWSE" / "mods" / "mwsuite" / "mwconsole"
pytestmark = pytest.mark.skipif(not LUAJIT.is_file(), reason="LuaJIT not available")


def run_lua(script):
    result = subprocess.run([str(LUAJIT), "-", str(MOD)], input=script, capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr + result.stdout


GUARD = r"""
local MOD = arg[1]
package.preload["mwconsole.log"] = function()
    return setmetatable({}, { __index = function() return function() end end })
end
local fronted = {}          -- menus moved to the front, in order
local console = { id = "MenuConsole", visible = true }
local menus = {}
local function newMenu()
    local m = { children = 0 }
    function m:destroyChildren() end
    function m:updateLayout() end
    function m:destroy() self.destroyed = true end
    return m
end
tes3 = { player = {}, mobilePlayer = {}, messageBox = function() end, scanCode = { escape = 1 } }
tes3ui = {
    findMenu = function(id) if id == "MenuConsole" then return console end return menus[id] end,
    createMenu = function(p) local m = newMenu(); m.id = p.id; menus[p.id] = m; return m end,
    moveMenuToFront = function(m) fronted[#fronted + 1] = m end,
    menuMode = function() return true end,
    enterMenuMode = function() end,
    leaveMenuMode = function() end,
    acquireTextInput = function() end,
}
event = { register = function() end, unregister = function() end }
local guard = assert(loadfile(MOD .. "/guard.lua"))()
guard.setLoaded(true)
local function build() end
local function panel() return guard.openWindow({ id = "p", modal = false, build = build, keepConsoleOnTop = true }) end
local function details() return guard.openWindow({ id = "d", modal = true, dragFrame = true, build = build }) end
"""


def test_the_panel_is_never_moved_in_front_of_the_console():
    run_lua(GUARD + r"""
local w = panel()
assert(w and w.menu, "panel opened")
assert(#fronted == 1 and fronted[1] == console, "console raised after the panel was built")
panel()                                  -- every refresh
panel()
assert(#fronted == 3, "console raised on each refresh, got " .. #fronted)
for _, m in ipairs(fronted) do assert(m == console, "only the console is ever moved to the front") end
""")


def test_a_normal_window_still_goes_to_the_front_on_refresh():
    run_lua(GUARD + r"""
local w = details()
assert(w and w.menu)
assert(#fronted == 0, "a new window is already on top")
details()
assert(#fronted == 1 and fronted[1] == w.menu, "refresh moves the details window to the front")
""")


def test_the_console_is_not_raised_over_an_open_details_window():
    run_lua(GUARD + r"""
details()
panel()
panel()
assert(#fronted == 0, "the details window stays on top while it is open, got " .. #fronted)
""")


def test_the_console_is_left_alone_when_it_is_hidden():
    run_lua(GUARD + r"""
console.visible = false
panel()
assert(#fronted == 0, "no hidden console is raised")
""")


MAIN = r"""
local MOD = arg[1]
local handlers = {}
local flushed = 0
local consoleVisible = true
local menuMode = false
local opened = 0
local ctl = { menuMode = false }
tes3 = {
    scanCode = { lCtrl = 29, escape = 1 }, event = {},
    menuMode = function() return menuMode end,
    isKeyEqual = function(a)
        local x, y = a.actual, a.expected
        return x.keyCode == y.keyCode and (x.isControlDown or false) == (y.isControlDown or false)
            and (x.isAltDown or false) == (y.isAltDown or false) and (x.isShiftDown or false) == (y.isShiftDown or false)
    end,
    worldController = { menuController = { inputController = { flushBufferedTextEvents = function() flushed = flushed + 1 end } } },
}
tes3ui = { findMenu = function(id) if id == "MenuConsole" then return { visible = consoleVisible } end end }
event = {
    register = function(name, fn) handlers[name] = handlers[name] or {}; table.insert(handlers[name], fn) end,
    unregister = function() end, trigger = function() end,
}
mwse = { loadConfig = function(_, d) d.enabled = true; return d end, saveConfig = function() end }
function include() return nil end
local function stubModule(fields)
    return setmetatable(fields or {}, { __index = function() return function() end end })
end
package.preload["mwconsole.config"] = function() return assert(loadfile(MOD .. "/config.lua"))() end
package.preload["mwconsole.log"] = function() return stubModule() end
package.preload["mwconsole.guard"] = function()
    return stubModule({ run = function(where, fn, ...) return true, fn(...) end })
end
package.preload["mwconsole.registry"] = function() return stubModule({ commands = {} }) end
package.preload["mwconsole.compat_mcc"] = function() return stubModule({ realMccPresent = function() return false end }) end
package.preload["mwconsole.console_ui"] = function() return stubModule() end
package.preload["mwconsole.complete.index"] = function() return stubModule({ built = false }) end
package.preload["mwconsole.complete.ui"] = function() return stubModule() end
package.preload["mwconsole.toggles"] = function() return stubModule() end
package.preload["mwconsole.selection.panel"] = function()
    return stubModule({ openDetails = function() opened = opened + 1 end })
end
package.preload["mwconsole.effects.window"] = function() return stubModule() end
package.preload["mwconsole.user.commands"] = function() return stubModule() end
local config = require("mwconsole.config")
assert(loadfile(MOD .. "/main.lua"))()
local function press(e)
    for _, fn in ipairs(handlers.keyDown or {}) do fn(e) end
end
local function altI() return { keyCode = 23, isAltDown = true } end
local function plainI() return { keyCode = 23 } end
"""


def test_default_hotkey_is_alt_i():
    run_lua(MAIN + r"""
local k = config.panel.hotkey
assert(k.keyCode == 23 and k.isAltDown and not k.isControlDown and not k.isShiftDown, "Alt+I")
""")


def test_alt_i_opens_the_details_in_the_world():
    run_lua(MAIN + r"""
press(altI())
assert(opened == 1, "opened in the world")
assert(flushed == 0, "nothing to flush outside the console")
""")


def test_alt_i_opens_the_details_with_the_console_open_and_drops_the_typed_character():
    run_lua(MAIN + r"""
menuMode = true
press(altI())
assert(opened == 1, "opened with the console open")
assert(flushed == 1, "the character the keypress would type is dropped")
""")


def test_a_plain_i_in_the_console_types_and_opens_nothing():
    run_lua(MAIN + r"""
menuMode = true
press(plainI())
assert(opened == 0 and flushed == 0, "plain i is left to the console")
press({ keyCode = 23, isControlDown = true })
assert(opened == 0 and flushed == 0, "Ctrl+I is not the key")
press({ keyCode = 23, isAltDown = true, isShiftDown = true })
assert(opened == 0 and flushed == 0, "Alt+Shift+I is not the key")
""")


def test_the_hotkey_does_nothing_in_other_menus():
    run_lua(MAIN + r"""
menuMode = true
consoleVisible = false
press(altI())
assert(opened == 0 and flushed == 0, "inventory, dialogue and so on are left alone")
""")


def test_a_hotkey_rebound_to_a_plain_letter_never_fires_while_the_console_is_open():
    run_lua(MAIN + r"""
config.panel.hotkey = { keyCode = 23, isControlDown = false, isAltDown = false, isShiftDown = false }
menuMode = true
press(plainI())
assert(opened == 0 and flushed == 0, "a plain letter would be typed text")
menuMode = false
press(plainI())
assert(opened == 1, "but it works in the world")
config.panel.hotkey = { keyCode = 59, isControlDown = false, isAltDown = false, isShiftDown = false }
menuMode = true
press({ keyCode = 59 })
assert(opened == 2, "a function key works with the console open")
""")
