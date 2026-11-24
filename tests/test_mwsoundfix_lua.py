"""mwsuite.mwsoundfix: bumps MWSF_Epoch on every load, zeroes a patched script's loop flags when its reference
becomes active again (skipping a reference with no script context yet), and stays idle without the patch."""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MAIN = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwsoundfix", "main.lua").replace("\\", "/")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

SCRIPT = r"""
local handlers, logs = {}, {}
event = { register = function(name, fn) handlers[name] = fn end }
local infos, cats = {}, {}
local page = { createInfo = function(_, o) infos[#infos + 1] = o.text end,
               createCategory = function(_, label)
                   cats[#cats + 1] = label
                   return { createInfo = function(_, o) infos[#infos + 1] = label .. "|" .. o.text end } end }
mwse = { log = function(f, ...) logs[#logs + 1] = string.format(f, ...) end,
         mcm = { createTemplate = function() return { createPage = function() return page end, register = function() end } end },
         loadConfig = function() return { version = 1, loopMode = "flag", built = "2026-11-24T03:00:00",
                      scripts = { loopscript = { owner = "B.esp", loopFlags = { "mwsfOn1" }, repairs = { "loop: hum" } },
                                  shotscript = { owner = "A.esp", loopFlags = {}, repairs = { "one-shot: bell" } },
                                  another = { owner = "B.esp", loopFlags = {}, repairs = { "one-shot: drip" } } } } end }
local epoch = PATCHED and { value = 31999 } or nil
tes3 = { event = setmetatable({}, { __index = function(_, k) return k end }),
         findGlobal = function(id) assert(id == "MWSF_Epoch") return epoch end }
assert(loadfile("MAIN"))()
handlers.modConfigReady()
assert(infos[1]:find("3 script%(s%) in 2 plugin%(s%)"), infos[1])
assert(cats[1] == "A.esp (1)" and cats[2] == "B.esp (2)", table.concat(cats, ","))
assert(infos[3] == "B.esp (2)|another  -  one-shot: drip\nloopscript  -  loop: hum", infos[3])
handlers.initialized()
if not PATCHED then
  assert(handlers.loaded == nil and handlers.referenceActivated == nil, "idle registers nothing")
  assert(logs[1]:find("idle"))
  print("ok") return
end
handlers.loaded({}) assert(epoch.value == 32000)
handlers.loaded({}) assert(epoch.value == 1, "wraps before a short overflows")
local ctx = { mwsfOn1 = 1 }
local ref = { object = { script = { id = "LoopScript" } }, context = ctx }
handlers.referenceActivated({ reference = ref })
assert(ctx.mwsfOn1 == 0 and ref.modified == true)
local fresh = { object = { script = { id = "LoopScript" } } }          -- no context yet: left alone, no error
handlers.referenceActivated({ reference = fresh })
assert(fresh.modified == nil)
handlers.referenceActivated({ reference = { object = { script = { id = "Other" } }, context = { mwsfOn1 = 1 } } })
assert(#logs == 1, "no errors logged: " .. table.concat(logs, " | "))
print("ok")
"""


@pytest.mark.parametrize("patched", [True, False])
def test_helper(tmp_path, patched):
    f = tmp_path / "t.lua"
    f.write_text(f"PATCHED = {'true' if patched else 'false'}\n" + SCRIPT.replace("MAIN", MAIN), encoding="utf-8")
    r = subprocess.run([LUAJIT, str(f)], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr + r.stdout
