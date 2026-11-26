"""mwsuite.mwsoundfix: bumps MWSF_Epoch on every load, zeroes a patched script's loop flags when its reference
becomes active again (skipping a reference with no script context yet), and stays idle without the patch.
Its MCM lists repaired scripts 100 per page, with Previous/Next and a Page X of Y label."""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MAIN = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwsoundfix", "main.lua").replace("\\", "/")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

PAGING = r"""
event = { register = function() end }
mwse = { log = function() end, mcm = { createTemplate = function() return { createPage = function() end, register = function() end } end },
         loadConfig = function() return nil end }
tes3 = { event = setmetatable({}, { __index = function(_, k) return k end }), findGlobal = function() return nil end }
local m = assert(loadfile("MAIN"))()
assert(m.PAGE_SIZE == 100)
local function check(total, page, want)
  local n = m.paginate(total, page)
  for k, v in pairs(want) do
    assert(n[k] == v, string.format("%s: total=%s page=%s got %s want %s", k, tostring(total), tostring(page), tostring(n[k]), tostring(v)))
  end
end
check(0, 1, { page = 1, pages = 1, first = 0, last = 0, hasPrev = false, hasNext = false, label = "Page 1 of 1" })
check(100, 1, { page = 1, pages = 1, first = 1, last = 100, hasPrev = false, hasNext = false, label = "Page 1 of 1" })
check(101, 1, { page = 1, pages = 2, first = 1, last = 100, hasPrev = false, hasNext = true, label = "Page 1 of 2" })
check(101, 2, { page = 2, pages = 2, first = 101, last = 101, hasPrev = true, hasNext = false, label = "Page 2 of 2" })
check(101, 0, { page = 1, pages = 2, first = 1, last = 100, hasPrev = false, hasNext = true })
check(101, 99, { page = 2, pages = 2, first = 101, last = 101, hasPrev = true, hasNext = false })
check(200, 2, { page = 2, pages = 2, first = 101, last = 200, hasPrev = true, hasNext = false, label = "Page 2 of 2" })
check(201, 3, { page = 3, pages = 3, first = 201, last = 201, hasPrev = true, hasNext = false, label = "Page 3 of 3" })
print("ok")
"""

HELPER = r"""
local handlers, logs = {}, {}
event = { register = function(name, fn) handlers[name] = fn end }
local infos, cats, buttons = {}, {}, {}
local function infoComp(text)
  local comp = { text = text, elements = { info = { text = text } }, disabled = false }
  function comp:enable() self.disabled = false end
  function comp:disable() self.disabled = true end
  infos[#infos + 1] = comp
  return comp
end
local page = {
  createInfo = function(_, o) return infoComp(o.text) end,
  createCategory = function(_, label)
    cats[#cats + 1] = label
    return { createInfo = function(_, o) return infoComp(label .. "|" .. o.text) end }
  end,
  createButton = function(_, o)
    local b = { buttonText = o.buttonText, callback = o.callback, postCreate = o.postCreate,
                text = o.buttonText, disabled = false, description = o.description,
                elements = { button = { text = o.buttonText, widget = { state = 0 } }, outerContainer = { visible = true } } }
    function b:enable() self.disabled = false end
    function b:disable() self.disabled = true end
    function b:setText(t) self.buttonText = t; self.elements.button.text = t end
    buttons[#buttons + 1] = b
    return b
  end,
}
mwse = { log = function(f, ...) logs[#logs + 1] = string.format(f, ...) end,
         mcm = { createTemplate = function() return { createPage = function() return page end, register = function() end } end },
         loadConfig = function()
           local scripts = SCRIPTS
           if not scripts then
             scripts = { loopscript = { owner = "B.esp", loopFlags = { "mwsfOn1" }, repairs = { "loop: hum" } },
                         shotscript = { owner = "A.esp", loopFlags = {}, repairs = { "one-shot: bell" } },
                         another = { owner = "B.esp", loopFlags = {}, repairs = { "one-shot: drip" } } }
           end
           return { version = 1, loopMode = "flag", built = "2026-11-24T03:00:00", scripts = scripts }
         end }
local epoch = PATCHED and { value = 31999 } or nil
tes3 = { event = setmetatable({}, { __index = function(_, k) return k end }),
         findGlobal = function(id) assert(id == "MWSF_Epoch") return epoch end }
local mod = assert(loadfile("MAIN"))()
handlers.modConfigReady()
for _, b in ipairs(buttons) do if b.postCreate then b:postCreate() end end
local function infoText(i) return infos[i] and infos[i].text or "" end
local function click(label)
  for _, b in ipairs(buttons) do
    if b.buttonText == label then b.callback(); return b end
  end
  error("no button " .. label)
end
local function btn(label)
  for _, b in ipairs(buttons) do if b.buttonText == label then return b end end
end
"""


def run_lua(body, tmp_path, extras=""):
    f = tmp_path / "t.lua"
    f.write_text(extras + "\n" + body.replace("MAIN", MAIN), encoding="utf-8")
    r = subprocess.run([LUAJIT, str(f)], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip().endswith("ok"), r.stderr + r.stdout
    return r.stdout


def test_paginate_boundaries(tmp_path):
    run_lua(PAGING, tmp_path)


@pytest.mark.parametrize("patched", [True, False])
def test_helper(tmp_path, patched):
    body = HELPER + r"""
assert(infoText(1):find("3 script%(s%) in 2 plugin%(s%)"), infoText(1))
assert(infoText(2) == "Page 1 of 1", infoText(2))
assert(btn("Previous") and btn("Previous").disabled, "previous disabled on the only page")
assert(btn("Next") and btn("Next").disabled, "next disabled on the only page")
assert(infoText(3) == "A.esp (1)\nshotscript  -  one-shot: bell\nB.esp (2)\nanother  -  one-shot: drip\nloopscript  -  loop: hum", infoText(3))
click("Previous"); click("Next")
assert(infoText(2) == "Page 1 of 1" and infoText(3):find("shotscript"), "buttons on a single page do nothing")
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
    run_lua(body, tmp_path, extras=f"PATCHED = {'true' if patched else 'false'}\n")


def test_mcm_pages_one_hundred_and_one_entries(tmp_path):
    body = HELPER + r"""
assert(infoText(1):find("101 script%(s%) in 2 plugin%(s%)"), infoText(1))
assert(infoText(2) == "Page 1 of 2", infoText(2))
assert(btn("Previous").disabled and not btn("Next").disabled)
local n = 0
for line in infoText(3):gmatch("[^\n]+") do
  if line:match("^s%d%d%d") then n = n + 1 end
end
assert(n == 100, "page 1 lists 100 scripts, got " .. n .. " in:\n" .. infoText(3))
assert(infoText(3):find("s001  -  loop: 1", 1, true) and infoText(3):find("s100  -  loop: 100", 1, true))
assert(not infoText(3):find("s101", 1, true), "s101 belongs on page 2")
click("Previous")
assert(infoText(2) == "Page 1 of 2" and btn("Previous").disabled, "previous on the first page does nothing")
click("Next")
assert(infoText(2) == "Page 2 of 2", infoText(2))
assert(not btn("Previous").disabled and btn("Next").disabled)
n = 0
for line in infoText(3):gmatch("[^\n]+") do
  if line:match("^s%d%d%d") then n = n + 1 end
end
assert(n == 1 and infoText(3):find("s101  -  loop: 101", 1, true), "page 2 has the leftover script: " .. infoText(3))
click("Next")
assert(infoText(2) == "Page 2 of 2" and btn("Next").disabled, "next on the last page does nothing")
click("Previous")
assert(infoText(2) == "Page 1 of 2", infoText(2))
n = 0
for line in infoText(3):gmatch("[^\n]+") do
  if line:match("^s%d%d%d") then n = n + 1 end
end
assert(n == 100 and infoText(3):find("s001", 1, true), "previous returns to page 1")
print("ok")
"""
    scripts = (
        "SCRIPTS = {}\n"
        "for i = 1, 101 do\n"
        '  SCRIPTS[string.format("s%03d", i)] = { owner = (i <= 50) and "A.esp" or "B.esp", '
        'loopFlags = {}, repairs = { "loop: " .. i } }\n'
        "end\n"
    )
    run_lua(body, tmp_path, extras=scripts)


def test_mcm_two_hundred_is_exactly_two_pages(tmp_path):
    body = HELPER + r"""
assert(infoText(2) == "Page 1 of 2")
click("Next")
assert(infoText(2) == "Page 2 of 2" and btn("Next").disabled)
local n = 0
for line in infoText(3):gmatch("[^\n]+") do
  if line:match("^s%d%d%d") then n = n + 1 end
end
assert(n == 100, "page 2 of a 200-script list is a full page, got " .. n)
print("ok")
"""
    scripts = (
        "SCRIPTS = {}\n"
        "for i = 1, 200 do\n"
        '  SCRIPTS[string.format("s%03d", i)] = { owner = "A.esp", loopFlags = {}, repairs = { "loop: " .. i } }\n'
        "end\n"
    )
    run_lua(body, tmp_path, extras=scripts)
