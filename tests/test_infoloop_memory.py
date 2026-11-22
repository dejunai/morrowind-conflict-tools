"""Exercise dialogue guard retention with the LuaJIT MWSE test harness."""
import os
import subprocess

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MODS = os.path.join(ROOT, "Data Files", "MWSE", "mods", "mwsuite").replace("\\", "/")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")


def test_topic_scan_and_conversation_release_infos(tmp_path):
    script = r'''
package.path = MODS .. "/?.lua;" .. package.path
local regularPairs = pairs
local weakScan = setmetatable({}, { __mode = "k" })
pairs = function(t)
  if type(t) == "table" and t._generate then
    local i = 0
    return function()
      i = i + 1
      if i == 1 then
        local info = { id = "temporary" }
        weakScan[info] = true
        return i, info
      end
    end
  end
  if type(t) == "table" and t._walk then
    local i = 0
    return function()
      i = i + 1
      if t._fail and i == 2 then error("broken topic") end
      if t._walk[i] then return i, t._walk[i] end
    end
  end
  return regularPairs(t)
end
local handlers, queued, saved = {}, nil, nil
event = { register = function(name, fn) handlers[name] = fn end }
mwse = {
  loadConfig = function(_, d) d.enabled = true; d.scanBudgetMs = 0; return d end,
  saveConfig = function(_, data) saved = data end,
  log = function() end,
}
lfs = { mkdir = function() end }
timer = {
  real = 1,
  start = function() return { cancel = function() end } end,
  frame = { delayOneFrame = function(fn) queued = fn; return true end },
}
tes3ui = { registerID = function(id) return id end, findMenu = function() end }
tes3 = {
  event = setmetatable({}, { __index = function(_, k) return k end }),
  dataHandler = { nonDynamicData = { dialogues = {} } },
}
local guard = require("mwinfoloop.main")
local a, b = { id = "a", sourceMod = "test" }, { id = "b", sourceMod = "test" }
local topics = tes3.dataHandler.nonDynamicData.dialogues
topics[1] = { id = "clean", info = { true, _generate = true } }
topics[2] = { id = "broken", info = { a, b, _walk = { a, b }, _fail = true } }
topics[3] = { id = "cycle", info = { a, b, _walk = { a, b, a } } }
guard.startScan(nil, "fixture")
for i = 1, 3 do
  assert(queued)
  local step = queued; queued = nil; step()
  local scan = guard.state().scan
  if not scan.finished then
    assert(next(scan.seen) == nil and next(scan.pos) == nil, "past topic INFOs retained")
    collectgarbage("collect") collectgarbage("collect")
    assert(next(weakScan) == nil, "past topic INFO is still reachable")
  end
end
assert(saved and saved.topics == 3 and saved.circular == 1)
assert(saved.anomalies.cycle.kind == "cycle" and saved.anomalies.cycle.length == 2)
assert(saved.anomalies.broken.kind == "error")
assert(not saved.anomalies.clean)

guard.applyResults({ tracked = { kind = "cycle" } })
do
  local info = { id = "loop" }
  local dial, ref = { id = "tracked", info = { info } }, {}
  local first = { dialogue = dial, info = info, reference = ref, passes = false }
  local repeated = { dialogue = dial, info = info, reference = ref, passes = false }
  guard.onInfoFilter(first)
  guard.onInfoFilter(repeated)
  assert(not first.passes and repeated.passes, "cycle did not terminate")
  local nextWalk = { dialogue = dial, info = info, reference = ref, passes = false }
  guard.onInfoFilter(nextWalk)
  assert(not nextWalk.passes, "previous walk contaminated the next one")
  guard.resetConversation()
end
local weak = setmetatable({}, { __mode = "k" })
do
  local info = { id = "transient" }
  local dial = { id = "tracked", info = { info } }
  weak[info] = true
  guard.onInfoFilter({ dialogue = dial, info = info, reference = {}, passes = false })
end
guard.resetConversation()
collectgarbage("collect") collectgarbage("collect")
assert(next(weak) == nil, "previous conversation INFO retained")
print("OK")
'''
    program = tmp_path / "guard.lua"
    program.write_text(f"MODS = [[{MODS}]]\n" + script, encoding="utf-8")
    result = subprocess.run([LUAJIT, str(program)], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0 and result.stdout.strip().endswith("OK"), result.stdout + result.stderr
