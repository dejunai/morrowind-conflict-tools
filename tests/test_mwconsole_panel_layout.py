"""mwconsole selection panel and details window: explicit pixel size, no autoHeight on the frame or the scroll pane."""
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
LUAJIT = Path(os.environ.get("MWMANAGER_LUAJIT", ROOT / "tools" / "luajit" / "luajit.exe"))
MOD = ROOT / "lua tools" / "MWSE" / "mods" / "mwsuite" / "mwconsole"
pytestmark = pytest.mark.skipif(not LUAJIT.is_file(), reason="LuaJIT not available")


def run_lua(body):
    script = PRELUDE + body
    result = subprocess.run([str(LUAJIT), "-", str(MOD)], input=script, capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr + result.stdout


PRELUDE = r"""
local MOD = arg[1]
local function stubModule(fields)
    return setmetatable(fields or {}, { __index = function() return function() end end })
end
local function element()
    local e = { children = {} }
    function e:createBlock() local c = element(); self.children[#self.children+1] = c; return c end
    function e:createLabel() return element() end
    function e:createButton() local c = element(); function c:register() end; return c end
    function e:createTextSelect() local c = element(); function c:register() end; return c end
    function e:createVerticalScrollPane()
        local c = element()
        function c:getContentElement() return element() end
        self.scroll = c
        return c
    end
    function e:register() end
    function e:updateLayout() end
    function e:destroyChildren() end
    function e:destroy() end
    function e:findChild() end
    return e
end
tes3 = { player = {}, mobilePlayer = {}, menuMode = function() return false end, getPlayerTarget = function() return nil end }
tes3ui = {
    getViewportSize = function() return 1000, 800 end,
    getPalette = function() return {1,1,1} end,
    log = function() end,
    findMenu = function() return { visible = true } end,
    getConsoleReference = function() return { id = "ref_1" } end,
    createTooltipMenu = function() return element() end,
    enterMenuMode = function() end,
    leaveMenuMode = function() end,
    acquireTextInput = function() end,
    menuMode = function() return true end,
    moveMenuToFront = function() end,
    createMenu = function(p) local m = element(); m.id = p.id; return m end,
}
mwse = { loadConfig = function(_, d) d.enabled = true; d.panel.on = true; return d end, saveConfig = function() end, log = function() end }
event = { register = function() end, unregister = function() end }
package.preload["mwconsole.config"] = function() return assert(loadfile(MOD .. "/config.lua"))() end
package.preload["mwconsole.log"] = function() return stubModule() end
package.preload["mwconsole.guard"] = function()
    local windows = {}
    local guard = stubModule({
        isGameLoaded = function() return true end,
        needGame = function() return nil end,
        run = function(_, fn, ...) return true, fn(...) end,
        focusConsole = function() end,
        getWindow = function(id) return windows[id] end,
    })
    function guard.openWindow(spec)
        local existing = windows[spec.id]
        if existing and existing.menu then
            existing.menu:destroyChildren()
            existing.build = spec.build or existing.build
            existing.build(existing.menu, existing)
            return existing
        end
        local menu = tes3ui.createMenu({ id = spec.id })
        local win = { id = spec.id, menu = menu, build = spec.build }
        windows[spec.id] = win
        spec.build(menu, win)
        return win
    end
    return guard
end
package.preload["mwconsole.effects.collect"] = function()
    return { isValid = function() return true end, isActor = function() return true end }
end
package.preload["mwconsole.effects.window"] = function() return stubModule() end
package.preload["mwconsole.selection.collect"] = function()
    return {
        rows = function() return { { section = "Object", label = "id", value = "ref_1" } } end,
        asText = function() return { "id: ref_1" } end,
    }
end
local panel = assert(loadfile(MOD .. "/selection/panel.lua"))()
"""


def test_the_console_panel_gets_a_real_pixel_size_and_the_scroll_pane_fills_it():
    run_lua(r"""
local win = panel.refresh()
assert(win and win.menu, "panel opened")
local m = win.menu
assert(m.autoWidth == false and m.autoHeight == false, "frame is not auto-sized")
assert(m.minWidth == 320 and m.minHeight == 240, "minimum 320x240")
assert(m.width == 350 and m.height == 600, "35% of 1000 by 75% of 800, got " .. tostring(m.width) .. "x" .. tostring(m.height))
assert(m.scroll, "scroll pane")
assert(m.scroll.widthProportional == 1.0 and m.scroll.heightProportional == 1.0, "scroll fills the frame")
assert(m.scroll.autoHeight == false, "scroll is not autoHeight")
""")


def test_the_details_window_uses_the_same_sizing():
    run_lua(r"""
local win = panel.openDetails({ id = "ref_1" })
assert(win and win.menu)
local m = win.menu
assert(m.autoWidth == false and m.autoHeight == false)
assert(m.minWidth == 320 and m.minHeight == 240)
assert(m.width == 350 and m.height == 600)
assert(m.scroll and m.scroll.heightProportional == 1.0 and m.scroll.autoHeight == false)
""")


def test_a_dragged_details_size_is_kept_on_rebuild():
    run_lua(r"""
local win = panel.openDetails({ id = "ref_1" })
win.menu.width, win.menu.height = 500, 400
local again = panel.openDetails({ id = "ref_1" })
assert(again == win, "same window")
assert(win.menu.width == 500 and win.menu.height == 400, "dragged size kept, got " .. tostring(win.menu.width) .. "x" .. tostring(win.menu.height))
""")

