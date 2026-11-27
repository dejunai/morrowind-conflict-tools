"""mwexitguard / newgame.lua: once a game has been loaded in this Morrowind session, New Game is blocked until
Morrowind is restarted (MGE XE does not reset in-session). Loading a save is never blocked and the first New Game after
launch works. The block is the `load` event with newGame == true (every way into a new game passes it) plus a dimmed
New Game button on MenuOptions. Run against a small stand-in for the MWSE API, written for the test."""
import os
import re
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
SUITE = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite").replace("\\", "/")
GUARD = SUITE + "/mwexitguard"
needs_luajit = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

BOOT = r"""
local handlers, logs, boxes = {}, {}, {}
local function key(name, options)
  return tostring(name) .. "|" .. tostring(type(options) == "table" and options.filter or nil)
end
local function list(name, options) local k = key(name, options) handlers[k] = handlers[k] or {} return handlers[k] end
event = {
  register = function(name, fn, options)
    local l = list(name, options) l[#l + 1] = { fn = fn, priority = type(options) == "table" and options.priority or 0 }
  end,
}
function count(name)
  local n, prefix = 0, tostring(name) .. "|"
  for k, l in pairs(handlers) do if k:sub(1, #prefix) == prefix then n = n + #l end end
  return n
end
-- fires every handler of the event (highest priority first); a handler returning false blocks and claims
function fire(name, e, filter)
  e = e or {}
  local all = {}
  local prefix = tostring(name) .. "|"
  for k, l in pairs(handlers) do
    if k == prefix .. "nil" or (filter ~= nil and k == prefix .. tostring(filter)) then
      for _, h in ipairs(l) do all[#all + 1] = h end
    end
  end
  table.sort(all, function(a, b) return a.priority > b.priority end)
  for _, h in ipairs(all) do
    if h.fn(e) == false then e.blocked = true break end
  end
  return e
end
mwse = { log = function(fmt, ...) logs[#logs + 1] = string.format(fmt, ...) end }
function logged(text) for _, l in ipairs(logs) do if l:find(text, 1, true) then return true end end return false end

local nextId = 0
local function element(id)
  nextId = nextId + 1
  local el = { id = id, children = {}, handlers = {}, props = {}, alpha = 1.0, n = nextId }
  function el:register(name, fn) self.handlers[name] = fn end
  function el:findChild(want)
    if self.id == want then return self end
    for _, c in ipairs(self.children) do local r = c:findChild(want) if r then return r end end
  end
  function el:getPropertyBool(k) return self.props[k] == true end
  function el:setPropertyBool(k, v) self.props[k] = v end
  function el:updateLayout() self.layouts = (self.layouts or 0) + 1 end
  function el:add(child) self.children[#self.children + 1] = child return child end
  return el
end
function makeMenu()
  local menu = element("MenuOptions")
  local container = menu:add(element("MenuOptions_New_container"))
  container:add(element("MenuOptions_New_button"))
  menu:add(element("MenuOptions_Load_container"))
  menu.new = container
  return menu
end

onMain, menuNow = false, nil
clicks, tips = 0, 0
tes3 = {
  event = setmetatable({}, { __index = function(_, k) return k end }),
  onMainMenu = function() return onMain end,
  messageBox = function(first, ...) boxes[#boxes + 1] = type(first) == "table" and first.message or first end,
  worldController = { menuClickSound = { play = function() clicks = clicks + 1 end } },
}
tes3ui = {
  registerID = function(s) return s end,
  findMenu = function(id) if menuNow and menuNow.id == id then return menuNow end end,
  createTooltipMenu = function() tips = tips + 1 return { createLabel = function(_, p) tipText = p.text end } end,
  enterMenuMode = function() enteredMenuMode = (enteredMenuMode or 0) + 1 end,
}
local cfg = @@CONFIG@@
package.loaded["mwexitguard.config"] = cfg
ng = assert(loadfile("@@GUARD@@/newgame.lua"))()
"""


def run(script, config="{ blockNewGameInSession = true }"):
    script = BOOT.replace("@@CONFIG@@", config).replace("@@GUARD@@", GUARD) + script
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stdout + out.stderr


@needs_luajit
def test_first_new_game_from_the_title_screen_is_allowed_then_the_session_is_used():
    run(r"""
assert(ng.init() == true)
local e = fire("load", { newGame = true })
assert(not e.blocked and #boxes == 0, "the first New Game must work")
assert(ng.isUsed() == false)
fire("loaded", { newGame = true })
assert(ng.isUsed() == true, "the new game marks the session used")
print("ok")
""")


@needs_luajit
def test_a_second_new_game_is_blocked_with_a_one_line_message_and_a_log_line():
    run(r"""
ng.init()
fire("loaded", { newGame = false })
local e = fire("load", { newGame = true })
assert(e.blocked == true, "New Game after a load must be blocked")
assert(#boxes == 1 and boxes[1] == ng.MESSAGE and not boxes[1]:find("\n", 1, true))
assert(ng.MESSAGE:find("Restart Morrowind", 1, true) and ng.MESSAGE:find("MGE XE", 1, true))
assert(logged("New Game blocked"))
print("ok")
""")


@needs_luajit
def test_loading_a_save_is_never_blocked():
    run(r"""
ng.init()
fire("loaded", { newGame = false })
for _ = 1, 3 do
  local e = fire("load", { newGame = false, filename = "quiksave" })
  assert(not e.blocked)
  fire("loaded", { newGame = false })
end
assert(#boxes == 0)
print("ok")
""")


@needs_luajit
def test_the_block_runs_first_and_claims_the_event():
    run(r"""
ng.init()
fire("loaded", {})
local seen = 0
event.register("load", function() seen = seen + 1 end, { priority = 10000 })      -- e.g. mwconsole's own
fire("load", { newGame = true })
assert(seen == 0, "another mod must not see a new game begin that was refused")
fire("load", { newGame = false })
assert(seen == 1)
print("ok")
""")


@needs_luajit
def test_death_screen_main_menu_is_kept_up_when_the_block_fires():
    run(r"""
ng.init()
fire("loaded", {})
menuNow = makeMenu() menuNow.visible = false onMain = true
fire("load", { newGame = true })
assert(menuNow.visible == true and enteredMenuMode == 1)
onMain, enteredMenuMode = false, nil
fire("load", { newGame = true })
assert(enteredMenuMode == nil, "in game the menu is left alone")
print("ok")
""")


@needs_luajit
def test_the_new_game_button_is_untouched_until_a_game_is_loaded():
    run(r"""
ng.init()
menuNow = makeMenu()
fire("uiActivated", { element = menuNow, newlyCreated = true }, "MenuOptions")
fire("menuEnter", {})
assert(menuNow.new.alpha == 1.0 and next(menuNow.new.handlers) == nil, "title screen: the button works as always")
print("ok")
""")


@needs_luajit
def test_the_new_game_button_is_dimmed_and_gets_a_tooltip_and_a_message_after_a_load():
    run(r"""
ng.init()
menuNow = makeMenu()
fire("loaded", {})                                   -- patches the menu that already exists
local b = menuNow.new
assert(b.alpha == 0.4 and b.children[1].alpha == 0.4, "dimmed, children too")
assert(menuNow:findChild("MenuOptions_Load_container").alpha == 1.0, "Load is not touched")
assert(b.handlers.mouseClick and b.handlers.help and b.children[1].handlers.mouseClick)
b.handlers.mouseClick()
assert(clicks == 1 and #boxes == 1 and boxes[1] == ng.MESSAGE)
b.handlers.help()
assert(tips == 1 and tipText == ng.TOOLTIP)
-- opening the menu again does not patch twice
local before = b.handlers.mouseClick
fire("uiActivated", { element = menuNow, newlyCreated = false }, "MenuOptions")
fire("menuEnter", {})
assert(b.handlers.mouseClick == before and menuNow.layouts == 1)
-- a menu that is rebuilt is patched again
menuNow = makeMenu()
fire("uiActivated", { element = menuNow, newlyCreated = true }, "MenuOptions")
assert(menuNow.new.alpha == 0.4)
print("ok")
""")


@needs_luajit
def test_a_menu_without_the_button_or_no_menu_at_all_is_harmless():
    run(r"""
ng.init()
fire("loaded", {})
menuNow = nil
fire("menuEnter", {})
local bare = { id = "MenuOptions", findChild = function() return nil end }
fire("uiActivated", { element = bare }, "MenuOptions")
assert(ng.patchMenu(bare) == false and ng.patchMenu(nil) == false)
print("ok")
""")


@needs_luajit
def test_switched_off_nothing_is_registered():
    run(r"""
assert(ng.init() == false)
assert(count("load") + count("loaded") + count("uiActivated") + count("menuEnter") == 0)
fire("loaded", {})
assert(fire("load", { newGame = true }).blocked == nil)
print("ok")
""", config="{ blockNewGameInSession = false }")


@needs_luajit
def test_a_config_without_the_key_counts_as_on_and_init_is_idempotent():
    run(r"""
assert(ng.init() == true and ng.init() == false)
assert(count("load") == 1 and count("loaded") == 1 and count("menuEnter") == 1 and count("uiActivated") == 1)
fire("loaded", {})
assert(fire("load", { newGame = true }).blocked == true)
print("ok")
""", config="{}")


@needs_luajit
def test_ongoing_cost_is_a_filtered_ui_listener_and_a_menu_enter_that_returns_at_once():
    text = open(os.path.join(GUARD, "newgame.lua"), encoding="utf-8").read()
    assert 'event.register("uiActivated", this.onUiActivated, { filter = MENU })' in text
    assert re.search(r"function this\.onMenuEnter\(\)\n\s+if not active\(\) then return end", text)
    run(r"""
ng.init()
assert(count("uiActivated|MenuOptions") == 0 and count("uiActivated") == 1)
for _ = 1, 1000 do fire("menuEnter", {}) end        -- before any load: nothing happens
assert(logs ~= nil and #boxes == 0)
print("ok")
""")


@needs_luajit
def test_every_exit_guard_file_compiles():
    for name in ("config.lua", "main.lua", "mcm.lua", "newgame.lua"):
        out = subprocess.run([LUAJIT, "-e", f'assert(loadfile("{GUARD}/{name}"))'], capture_output=True, text=True)
        assert out.returncode == 0, name + out.stderr


def test_the_switch_is_on_by_default_has_its_own_name_and_is_in_the_mcm_with_the_continue_credit():
    cfg = open(os.path.join(GUARD, "config.lua"), encoding="utf-8").read()
    mcm = open(os.path.join(GUARD, "mcm.lua"), encoding="utf-8").read()
    main = open(os.path.join(GUARD, "main.lua"), encoding="utf-8").read()
    assert re.search(r"\bblockNewGameInSession = true\b", cfg)
    assert 'id = "blockNewGameInSession"' in mcm
    assert "Restart the game after changing it" in mcm
    assert "Petethegoat" in mcm and "https://www.nexusmods.com/morrowind/mods/45952" in mcm
    assert 'require("mwexitguard.newgame").init()' in main
    new = open(os.path.join(GUARD, "newgame.lua"), encoding="utf-8").read()
    assert "Petethegoat" in new and "MenuOptions_New_container" in new
    assert not new.startswith("\ufeff") and new.isascii()