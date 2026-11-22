"""mwguard: wraps nothing while it is off at start-up, and lets go of handlers that are unregistered (run under
LuaJIT against stubbed MWSE)."""
import os
import subprocess

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MODS = os.path.join(ROOT, "Data Files", "MWSE", "mods", "mwsuite").replace("\\", "/")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

HARNESS = r'''
local registry = {}                    -- event -> list of callbacks (MWSE's own register, stubbed)
local function realRegister(et, cb) registry[et] = registry[et] or {}; table.insert(registry[et], cb) end
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
timer = { real = 1, start = function() return { cancel = function() end } end }
tes3 = { event = { loaded = "loaded", initialized = "initialized", modConfigReady = "modConfigReady" } }
include = function() return nil end
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
