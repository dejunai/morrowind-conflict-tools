"""UI Expansion's one-shot topic painter waits for the topic rows, whoever lays the dialogue menu out early."""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MOD = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwpluginpatches").replace("\\", "/")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

SCRIPT = r"""
local handlers, startup = {}, nil
event = { register = function(name, fn, o)
  if name == "initialized" then startup = fn end
  if name ~= "uiActivated" then return end
  local at, p = #handlers + 1, o and o.priority or 0
  for i, h in ipairs(handlers) do if h.p < p then at = i break end end
  table.insert(handlers, at, { f = fn, p = p })
end }
mwse = { log = function() end }
tes3 = { event = setmetatable({}, { __index = function(_, k) return k end }) }
local config = setmetatable({ enabled = true, uiExpansionTopicsEnabled = ENABLED, isUIExpansionActive = function() return true end },
  { __index = function(_, k) if k:match("^is") then return function() return false end end end })
table.insert(package.loaders, 2, function(name)
  if name == "mwpluginpatches.config" then return function() return config end end
  if name == "mwpluginpatches.patches.uiExpansionTopics" then return assert(loadfile("MOD/patches/uiExpansionTopics.lua")) end
  if name:match("^mwpluginpatches%.patches%.") then return function() return { init = function() end } end end
end)
assert(loadfile("MOD/main.lua"))()

-- MWSE's after-event loop: priorities, a boolean result ends it, the end is taken once, an erase leaves a dead slot
local function newMenu()
  local list, count = {}, 0
  local menu = { id = "MenuDialog", rows = 0, laidOut = 0, paints = {} }
  function menu:findChild(id) if id == "MenuDialog_a_topic" and self.rows > 0 then return {} end end
  function menu:registerAfter(ev, fn, p)
    assert(ev == "preUpdate")
    p = p or 0
    local at = count + 1
    for i = 1, count do if list[i].p < p then at = i break end end
    for i = count, at, -1 do list[i + 1] = list[i] end
    list[at], count = { f = fn, p = p }, count + 1
  end
  function menu:unregisterAfter(ev, fn)
    for i = 1, count do if list[i].f == fn then
      for j = i, count - 1 do list[j] = list[j + 1] end
      list[count], count = "dead", count - 1
      return true
    end end
  end
  function menu:updateLayout()
    self.laidOut = self.laidOut + 1                           -- the engine's own handler runs first
    local last = count
    for i = 1, last do
      assert(list[i] ~= "dead", "MWSE would call a moved-from function: crash")
      local result = list[i].f({ source = self })
      if type(result) == "boolean" then return end
    end
  end
  return menu
end
local function painter(e)                                    -- as UI Expansion's MenuDialog.lua registers it
  if not e.newlyCreated then return end
  local function first()
    assert(e.element:unregisterAfter("preUpdate", first))
    table.insert(e.element.paints, e.element.rows)
  end
  e.element:registerAfter("preUpdate", first)
end
local function earlyLayout(e) e.element:updateLayout() end   -- as ImmersiveTravel, for NPCs who offer travel

local function conversation(...)
  handlers = {}
  startup()                                                  -- the patch, through mwpluginpatches' own main
  for _, f in ipairs({ ... }) do event.register("uiActivated", f) end
  local menu = newMenu()
  for _, h in ipairs(handlers) do h.f({ newlyCreated = true, element = menu }) end
  menu:updateLayout()                                        -- a layout before the greeting has built the list
  menu.rows = 3
  menu:updateLayout()
  menu:updateLayout()
  return menu
end
local orders = { painterFirst = { painter, earlyLayout }, layoutFirst = { earlyLayout, painter }, alone = { painter } }
for name, order in pairs(orders) do
  local menu = conversation(unpack(order))
  if ENABLED then
    assert(#menu.paints == 1 and menu.paints[1] == 3, name .. ": painted with rows " .. tostring(menu.paints[1]))
  else
    assert(menu.paints[1] == 0, name .. ": left alone when switched off")
  end
  assert(menu.laidOut >= 3, "the engine's own layout always runs")
end
"""


@pytest.mark.parametrize("enabled", [True, False])
def test_the_painter_runs_once_and_only_with_rows(enabled):
    script = SCRIPT.replace("MOD", MOD).replace("ENABLED", str(enabled).lower())
    got = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True)
    assert got.returncode == 0, got.stderr
