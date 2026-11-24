"""mwguard: wraps nothing while it is off at start-up, and lets go of handlers that are unregistered (run under
LuaJIT against stubbed MWSE)."""
import os
import subprocess

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MODS = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite").replace("\\", "/")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

HARNESS = r'''
local registry = {}                    -- event -> list of callbacks (MWSE's own register, stubbed)
local regOpts = {}
local function realRegister(et, cb, opts) registry[et] = registry[et] or {}; table.insert(registry[et], cb); regOpts[cb] = opts end
local function realUnregister(et, cb)
  for i, f in ipairs(registry[et] or {}) do if f == cb then table.remove(registry[et], i) return end end
end
local function realIsRegistered(et, cb)
  for _, f in ipairs(registry[et] or {}) do if f == cb then return true end end
  return false
end
event = { register = realRegister, unregister = realUnregister, isRegistered = realIsRegistered }
mwse = {
  loadConfig = function(_, d) local c = {} for k, v in pairs(d) do c[k] = v end c.enabled = ENABLED return c end,
  log = function() end, mcm = {},
}
lfs = { mkdir = function() end, fileexists = function() return true end }
timersStarted = {}
timersCancelled = 0
timer = {
  real = 1,
  start = function(opts)
    local t = { opts = opts, cancelled = false, cancel = function(self) if not self.cancelled then self.cancelled = true; timersCancelled = timersCancelled + 1 end end }
    table.insert(timersStarted, t)
    return t
  end,
}
tes3 = { event = { loaded = "loaded", initialized = "initialized", modConfigReady = "modConfigReady", uiActivated = "uiActivated" } }
helpMenus = {}
mwseLogs = {}
mwse.log = function(fmt, ...) table.insert(mwseLogs, string.format(fmt, ...)) end
do
  local nextId = 1000
  local ids = {}
  local function makeEl(id)
    local children = {}
    local el = { id = id, children = children }
    function el:findChild(cid)
      for _, c in ipairs(children) do if c.id == cid then return c end end
      return nil
    end
    function el:createLabel(p)
      local c = makeEl(p and p.id)
      table.insert(children, c)
      return c
    end
    function el:updateLayout() self.layoutUpdated = (self.layoutUpdated or 0) + 1 end
    function el:destroy()
      if id and helpMenus[id] == self then helpMenus[id] = nil end
    end
    return el
  end
  tes3ui = {
    registerID = function(name)
      if ids[name] then return ids[name] end
      nextId = nextId + 1
      ids[name] = nextId
      return nextId
    end,
    findMenu = function() return nil end,
    createHelpLayerMenu = function(p)
      local m = makeEl(p.id)
      helpMenus[p.id] = m
      return m
    end,
    findHelpLayerMenu = function(id) return helpMenus[id] end,
  }
end
-- MWSE include: require, or nil when the module is missing; other load errors still raise.
include = function(name)
  local ok, result = pcall(require, name)
  if ok then return result end
  if type(result) == "string" and result:find("module '" .. name .. "' not found", 1, true) then
    return nil
  end
  error(result)
end
package.path = MODS .. "/?.lua;" .. package.path
require("mwguard.main")

-- a closure that looks like it comes from another mod's main.lua
local make = load("return function() return function(e) return e end end",
  "@C:\\Game\\Data Files\\MWSE\\mods\\othermod\\main.lua")()
'''

OFF = HARNESS + r'''
assert(event.register == realRegister, "mwguard replaced event.register while off")
local cb = make()
event.register("simulate", cb)
assert(registry.simulate[1] == cb, "the handler was wrapped while mwguard is off")
print("OK")
'''

ON = HARNESS + r'''
assert(event.register ~= realRegister, "mwguard should wrap while on")
local owned = load("return function() end",
  "@C:\\Game\\Data Files\\MWSE\\mods\\mwsuite\\mwcriminal\\main.lua")()
event.register("simulate", owned)
assert(registry.simulate[1] == owned, "nested suite exemption was lost")
event.unregister("simulate", owned)
local probe = setmetatable({}, { __mode = "k" })
for _ = 1, 1000 do
  local cb = make()
  probe[cb] = true
  event.register("simulate", cb)
  assert(registry.simulate[1] ~= cb, "per-frame handler not wrapped")
  assert(event.isRegistered("simulate", cb))
  event.unregister("simulate", cb)
  assert(not event.isRegistered("simulate", cb))
end
assert(#registry.simulate == 0)
collectgarbage("collect") collectgarbage("collect")
local left = 0
for _ in pairs(probe) do left = left + 1 end
assert(left == 0, left .. " unregistered handlers are still held")
-- a handler registered again after unregistering is measured again
local cb = make()
event.register("simulate", cb) event.unregister("simulate", cb) event.register("simulate", cb)
assert(event.isRegistered("simulate", cb) and #registry.simulate == 1)
print("OK")
'''


def run(tmp_path, body, enabled):
    script = tmp_path / "t.lua"
    script.write_text(f"ENABLED = {'true' if enabled else 'false'}\nMODS = [[{MODS}]]\n" + body, encoding="utf-8")
    r = subprocess.run([LUAJIT, str(script)], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip().endswith("OK"), r.stdout + r.stderr


def test_off_at_start_up_wraps_nothing(tmp_path):
    run(tmp_path, OFF, enabled=False)


def test_unregistered_handlers_are_released(tmp_path):
    run(tmp_path, ON, enabled=True)


def test_nested_suite_interop_preserves_short_exemptions(tmp_path):
    run(tmp_path, r'''
package.path = MODS .. "/?.lua;" .. package.path
local guard = require("mwguard.interop")
guard.exempt("mwcriminal")
guard.exemptLog("mwcriminal")
assert(guard.isExempt("mwsuite/mwcriminal"))
assert(guard.isLogExempt("mwsuite/mwcriminal"))
assert(not guard.isExempt("mwsuite/mwcompanions"))
assert(not guard.isLogExempt("mwsuite/mwcompanions"))
print("OK")
''', enabled=False)


def test_source_hints_do_not_retain_whole_files(tmp_path):
    source = tmp_path / "Data Files" / "MWSE" / "mods" / "othermod" / "main.lua"
    source.parent.mkdir(parents=True)
    source.write_text(
        "".join(f"-- {i:06d} " + "x" * 150 + "\n" for i in range(12000))
        + "return function(e) local mouse = e; return mouse end\n",
        encoding="utf-8",
    )
    run(tmp_path, HARNESS + r'''
local cb = assert(loadfile(SOURCE))()
collectgarbage("collect") collectgarbage("collect")
local before = collectgarbage("count")
event.register("simulate", cb)
local st
for i = 1, 20 do
  local name, value = debug.getupvalue(registry.simulate[1], i)
  if not name then break end
  if name == "st" then st = value end
end
assert(st and st.hint == "mouse", "handler hint missing")
collectgarbage("collect") collectgarbage("collect")
local retained = collectgarbage("count") - before
assert(retained < 512, string.format("source hints retained %.0f KiB", retained))
print("OK")
'''.replace("SOURCE", "[[" + str(source).replace("\\", "/") + "]]"), enabled=True)


def test_address_space_hud_uses_help_layer_and_recovers_after_load(tmp_path):
    run(tmp_path, HARNESS + r'''
local guard = require("mwguard.interop")
guard.addressSpace = function() return 2048, 4096 end
local function fire(ev)
  for _, fn in ipairs(registry[ev] or {}) do fn() end
end
local function hudTimers()
  local out = {}
  for _, t in ipairs(timersStarted) do if t.opts and t.opts.duration == 1 then table.insert(out, t) end end
  return out
end
assert(#registry.initialized >= 2 and #registry.loaded >= 2 and #registry.uiActivated >= 1)
assert(regOpts[registry.uiActivated[1]] and regOpts[registry.uiActivated[1]].filter == "MenuMulti")
fire("initialized")
local menuId = tes3ui.registerID("mwguard:addressSpaceMenu")
local labelId = tes3ui.registerID("mwguard:addressSpace")
local menu = tes3ui.findHelpLayerMenu(menuId)
assert(menu, "help-layer menu not created")
assert(menu.autoWidth == true and menu.autoHeight == true)
assert(menu.absolutePosAlignX == 0.99 and menu.absolutePosAlignY == 0.01)
assert(menu.consumeMouseEvents == false)
local label = menu:findChild(labelId)
assert(label and label.text == "50" and label.consumeMouseEvents == false)

-- simulate load / new game destroying help-layer menus: loaded cancels prior timer and recreates HUD
local prevTimer = hudTimers()[1]
assert(prevTimer, "HUD timer not started")
menu:destroy()
assert(tes3ui.findHelpLayerMenu(menuId) == nil)
guard.addressSpace = function() return 3072, 4096 end
fire("loaded")
assert(prevTimer.cancelled and timersCancelled == 1 and #hudTimers() == 2)
local recreated = tes3ui.findHelpLayerMenu(menuId)
assert(recreated and recreated:findChild(labelId).text == "75")

-- uiActivated(MenuMulti) recreates lazily if missing again
recreated:destroy()
fire("uiActivated")
assert(tes3ui.findHelpLayerMenu(menuId):findChild(labelId).text == "75")

-- errors in updateHud are logged once instead of swallowed silently
local calls = 0
guard.addressSpace = function() calls = calls + 1; error("boom") end
hudTimers()[2].opts.callback()
hudTimers()[2].opts.callback()
assert(calls == 2)
local errLogs = 0
for _, m in ipairs(mwseLogs) do if m:find("address%-space HUD error: .*boom") then errLogs = errLogs + 1 end end
assert(errLogs == 1, "expected 1 HUD error log, got " .. errLogs)
print("OK")
''', enabled=False)
