"""mwsuite.mwsoundfix: bumps MWSF_Epoch on every load, zeroes a patched script's loop flags when its reference
becomes active again (skipping a reference with no script context yet), and stays idle without the patch.
Its MCM lists repaired scripts 100 per page, with Previous/Next and a Page X of Y label.
Plugin names are MCM Category headers (headerColor + font 1); sound lines are indented Info text."""
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
assert(m.HEADER_FONT == 1)
assert(m.SOUND_INDENT == "\194\160\194\160\194\160\194\160- ")
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

# formatPageText / pageGroups: headers, NBSP indent + bullet, blank line between mods, (cont.)
FORMATTING = r"""
event = { register = function() end }
mwse = { log = function() end, mcm = { createTemplate = function() return { createPage = function() end, register = function() end } end },
         loadConfig = function() return nil end }
tes3 = { event = setmetatable({}, { __index = function(_, k) return k end }), findGlobal = function() return nil end }
local m = assert(loadfile("MAIN"))()
local data = { scripts = {
  loopscript = { owner = "B.esp", loopFlags = { "mwsfOn1" }, repairs = { "loop: hum" } },
  shotscript = { owner = "A.esp", loopFlags = {}, repairs = { "one-shot: bell" } },
  another = { owner = "B.esp", loopFlags = {}, repairs = { "one-shot: drip" } },
} }
local entries = m.collectEntries(data)
local text = m.formatPageText(entries, m.paginate(#entries, 1))
local indent = m.SOUND_INDENT
local expected = table.concat({
  "A.esp (1)",
  indent .. "shotscript  -  one-shot: bell",
  "",
  "B.esp (2)",
  indent .. "another  -  one-shot: drip",
  indent .. "loopscript  -  loop: hum",
}, "\n")
assert(text == expected, "got:\n" .. text)
assert(not text:match("\n$"), "no trailing blank line after the last mod")
-- a plugin that crosses the page boundary repeats its header as (cont.)
local many = { scripts = {} }
for i = 1, 101 do
  many.scripts[string.format("s%03d", i)] = {
    owner = (i <= 50) and "A.esp" or "B.esp", loopFlags = {}, repairs = { "loop: " .. i }
  }
end
local all = m.collectEntries(many)
local g1 = m.pageGroups(all, m.paginate(101, 1))
assert(#g1 == 2 and g1[1].title == "A.esp (50)" and not g1[1].continued, g1[1] and g1[1].title)
assert(g1[2].title == "B.esp (51)" and not g1[2].continued, g1[2] and g1[2].title)
assert(#g1[1].lines == 50 and #g1[2].lines == 50, "headers do not count toward the 100")
assert(g1[1].lines[1]:sub(1, #indent) == indent and g1[1].lines[1]:find("s001", 1, true))
local g2 = m.pageGroups(all, m.paginate(101, 2))
assert(#g2 == 1 and g2[1].title == "B.esp (cont.)" and g2[1].continued, g2[1] and g2[1].title)
assert(#g2[1].lines == 1 and g2[1].lines[1]:find("s101", 1, true))
local t2 = m.formatPageText(all, m.paginate(101, 2))
assert(t2 == "B.esp (cont.)\n" .. indent .. "s101  -  loop: 101", t2)
print("ok")
"""

HELPER = r"""
local handlers, logs = {}, {}
event = { register = function(name, fn) handlers[name] = fn end }
local infos, buttons, hosts = {}, {}, {}
tes3ui = { getPalette = function(p) return p end }
local function infoComp(text)
  local comp = { text = text, elements = { info = { text = text, borderLeft = 0, wrapText = false } }, disabled = false }
  function comp:enable() self.disabled = false end
  function comp:disable() self.disabled = true end
  infos[#infos + 1] = comp
  return comp
end
local function makeCategory(data)
  data = data or {}
  local cat = {
    label = type(data) == "table" and data.label or data,
    postCreate = type(data) == "table" and data.postCreate or nil,
    components = {},
    infos = {},
    elements = {
      label = { color = nil, font = 0 },
      outerContainer = { paddingBottom = 0 },
      subcomponentsContainer = { children = {} },
    },
  }
  function cat:createInfo(o)
    local c = infoComp(o.text)
    c.postCreate = o.postCreate
    self.infos[#self.infos + 1] = c
    return c
  end
  function cat:createCategory(data)
    local child = makeCategory(data)
    self.components[#self.components + 1] = child
    return child
  end
  function cat:create(parent)
    if parent and parent.children then
      local el = {}
      function el:destroy()
        for i, c in ipairs(parent.children) do
          if c == self then table.remove(parent.children, i) return end
        end
      end
      parent.children[#parent.children + 1] = el
      self.elements.outerContainer = el
    end
    if self.postCreate then self:postCreate() end
    for _, child in ipairs(self.infos) do
      if child.postCreate then child:postCreate(child) end
    end
    for _, child in ipairs(self.components) do
      child:create(self.elements.subcomponentsContainer)
    end
  end
  return cat
end
local page = {
  createInfo = function(_, o) return infoComp(o.text) end,
  createCategory = function(_, data)
    local cat = makeCategory(data)
    hosts[#hosts + 1] = cat
    return cat
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
         findGlobal = function(id) assert(id == "MWSF_Epoch") return epoch end,
         palette = { headerColor = "header_color" } }
local mod = assert(loadfile("MAIN"))()
handlers.modConfigReady()
for _, b in ipairs(buttons) do if b.postCreate then b:postCreate() end end
for _, h in ipairs(hosts) do if h.postCreate then h:postCreate() end end
local function infoText(i) return infos[i] and infos[i].text or "" end
local function listHost() return hosts[1] end
local function groups()
  local h = listHost()
  return h and h.components or {}
end
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


def test_page_formatting_headers_indent_and_blank_lines(tmp_path):
    run_lua(FORMATTING, tmp_path)


@pytest.mark.parametrize("patched", [True, False])
def test_helper(tmp_path, patched):
    body = HELPER + r"""
assert(infoText(1):find("3 script%(s%) in 2 plugin%(s%)"), infoText(1))
assert(infoText(2) == "Page 1 of 1", infoText(2))
assert(btn("Previous") and btn("Previous").disabled, "previous disabled on the only page")
assert(btn("Next") and btn("Next").disabled, "next disabled on the only page")
local g = groups()
assert(#g == 2, "two plugin categories")
assert(g[1].label == "A.esp (1)" and g[2].label == "B.esp (2)")
assert(g[1].elements.label.font == mod.HEADER_FONT, "header uses font 1")
assert(g[1].elements.label.color == "header_color", "header uses headerColor")
local indent = mod.SOUND_INDENT
assert(g[1].infos[1].text == indent .. "shotscript  -  one-shot: bell\n", "blank line before the next mod")
assert(g[2].infos[1].text == indent .. "another  -  one-shot: drip\n" .. indent .. "loopscript  -  loop: hum")
assert(g[1].infos[1].elements.info.borderLeft == 16)
assert(g[2].infos[1].text:sub(-1) ~= "\n", "no blank line after the last mod")
click("Previous"); click("Next")
assert(infoText(2) == "Page 1 of 1" and groups()[1].label == "A.esp (1)", "buttons on a single page do nothing")
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
local g = groups()
assert(#g == 2 and g[1].label == "A.esp (50)" and g[2].label == "B.esp (51)")
local function countScripts(gs)
  local n = 0
  for _, cat in ipairs(gs) do
    for line in cat.infos[1].text:gmatch("[^\n]+") do
      if line:match("s%d%d%d") then n = n + 1 end
    end
  end
  return n
end
assert(countScripts(g) == 100, "page 1 lists 100 scripts, headers excluded")
assert(g[1].infos[1].text:find("s001", 1, true) and g[2].infos[1].text:find("s100", 1, true))
assert(not g[1].infos[1].text:find("s101", 1, true) and not g[2].infos[1].text:find("s101", 1, true))
assert(g[1].infos[1].text:sub(-1) == "\n" or g[1].infos[1].text:find("\n$"), "blank line before the next mod header")
click("Previous")
assert(infoText(2) == "Page 1 of 2" and btn("Previous").disabled, "previous on the first page does nothing")
click("Next")
assert(infoText(2) == "Page 2 of 2", infoText(2))
assert(not btn("Previous").disabled and btn("Next").disabled)
g = groups()
assert(#g == 1 and g[1].label == "B.esp (cont.)", g[1] and g[1].label)
assert(countScripts(g) == 1 and g[1].infos[1].text:find("s101", 1, true), g[1] and g[1].infos[1].text)
assert(g[1].infos[1].text:sub(-1) ~= "\n", "no blank line after the last mod on the page")
click("Next")
assert(infoText(2) == "Page 2 of 2" and btn("Next").disabled, "next on the last page does nothing")
click("Previous")
assert(infoText(2) == "Page 1 of 2", infoText(2))
g = groups()
assert(#g == 2 and g[1].label == "A.esp (50)" and countScripts(g) == 100)
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
local g = groups()
assert(#g == 1 and g[1].label == "A.esp (cont.)", g[1] and g[1].label)
local n = 0
for line in g[1].infos[1].text:gmatch("[^\n]+") do
  if line:match("s%d%d%d") then n = n + 1 end
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
