"""U1: a loop that makes one UI element per entry of a list that can hold every object of a kind (built from
tes3.iterateObjects / nonDynamicData in the same file) is drawn 100 at a time with a "show the next" entry. The
shapes are the ones found in staged mods (Map Icons, Tooltips Complete, Companion Leveler)."""
import os
import subprocess

import pytest

from conftest import _load

lf = _load("mwdialog_luafix")
CFG = dict(lf.DEFAULTS)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))


def analyse(src):
    a = lf.FileAnalysis(src, "testmod", "testmod/main.lua", CFG)
    a.run()
    return a


def u1(src):
    return [f for f in analyse(src).findings if f["rule"] == "U1"]


def patch(src):
    new, _r = lf.build_patch(src, analyse(src).findings, "testmod", CFG, "high", False)
    return new


# Map Icons: every interior cell, through a function's return, into a parameter of the drawing function
MAP_ICONS = """local function exclusionList(filter)
    local list = {}
    for _, cell in pairs(tes3.dataHandler.nonDynamicData.cells) do
        if cell.isInterior then table.insert(list, cell.id) end
    end
    return list
end
local function toggleList(layer, list, id)
    local pane = layer:createVerticalScrollPane()
    pane = pane:getContentElement()
    for _, cell in ipairs(list) do
        local label = pane:createLabel { id = cell, text = cell }
        label:register("mouseOver", function() label.color = 1 end)
    end
end
local function show(layer)
    local keys = exclusionList(true)
    toggleList(layer, keys, "switchIconer")
    toggleList(layer, exclusionList(), "blackList")
end
return show
"""

# Tooltips Complete: its own exclusions page, two panes, pairs over the list
TOOLTIPS = """local function getSortedObjectList(objectType)
    local list = {}
    for obj in tes3.iterateObjects(objectType) do list[#list + 1] = obj.id:lower() end
    table.sort(list)
    return list
end
local blockedIds = {}
local function distribute(t, blocked, allowed, callback)
    for i, name in pairs(t) do
        if blockedIds[name] then
            blocked:createTextSelect{text=name}:register("mouseClick", callback)
        else
            allowed:createTextSelect{text=name}:register("mouseClick", callback)
        end
    end
end
local function onTab(blocked, allowed, callback)
    local items = getSortedObjectList(tes3.objectType.armor)
    distribute(items, blocked, allowed, callback)
end
return onTab
"""

# Companion Leveler: straight over nonDynamicData.classes, the elements nested in one made in the loop
CLASSES = """local function classList(pane)
    for n, k in pairs(tes3.dataHandler.nonDynamicData.classes) do
        local bl = pane:createBlock {}
        local b = bl:createTextSelect { text = k.name }
    end
end
return classList
"""


def test_the_three_shapes_found_in_mods_are_fingerprinted_and_patched():
    for src in (MAP_ICONS, TOOLTIPS, CLASSES):
        f = u1(src)
        assert len(f) == 1 and f[0]["conf"] == "high", (src[:40], f)
        new = patch(src)
        assert "localpatch_pages(" in new and "localpatch_pages = function" in new
        assert new.count("\n") == src.count("\n")                       # line numbers kept
        assert not u1(new)                                               # a second run changes nothing
    assert "localpatch_pages(list, {pane}, function(_, cell)" in patch(MAP_ICONS)
    assert "localpatch_pages(t, {blocked, allowed}, function(i, name)" in patch(TOOLTIPS)
    assert "end, true)" in patch(TOOLTIPS) and "end, false)" in patch(MAP_ICONS)


def test_a_small_list_or_one_nothing_large_feeds_is_left_alone():
    src = """local options = { "a", "b", "c" }
local function draw(pane)
    for _, o in ipairs(options) do pane:createLabel { text = o } end
end
local function count() local n = 0 for _ in tes3.iterateObjects(tes3.objectType.npc) do n = n + 1 end return n end
return draw, count
"""
    assert not u1(src)


def test_a_body_that_breaks_or_returns_is_only_reported():
    src = CLASSES.replace("local b = bl:createTextSelect { text = k.name }",
                          "local b = bl:createTextSelect { text = k.name }\n        if k.id == 'x' then break end")
    f = u1(src)
    assert len(f) == 1 and f[0]["conf"] == "report" and "Break" in f[0]["fix"]
    assert "localpatch_pages(" not in (patch(src) or "")                # no patch at all


@pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")
def test_the_patched_loop_draws_100_then_the_next_on_click():
    new = patch(MAP_ICONS)
    script = r"""
local made, clicks = {}, {}
local function element()
  local e = { children = {} }
  function e:createVerticalScrollPane() return element() end
  function e:getContentElement() return self end
  function e:createLabel(p) local c = element() c.text = p.text self.children[#self.children + 1] = c return c end
  function e:createTextSelect(p) local c = element() c.text = p.text c.isMore = true self.children[#self.children + 1] = c
    c.parentEl = self return c end
  function e:register(ev, fn) if ev == "mouseClick" then self.onClick = fn end end
  function e:destroy() for i, c in ipairs(self.parentEl.children) do if c == self then table.remove(self.parentEl.children, i) end end end
  function e:getTopLevelMenu() return { updateLayout = function() end } end
  return e
end
local cells = {}
for i = 1, 250 do cells[i] = { isInterior = true, id = "cell" .. i } end
tes3 = { dataHandler = { nonDynamicData = { cells = cells } } }
local show = assert(loadstring([==[""" + new + r"""]==]))()
local layer = element()
local pane
layer.createVerticalScrollPane = function() pane = element() return pane end
show(layer)
local function labels() local n, more = 0, nil for _, c in ipairs(pane.children) do if c.isMore then more = c else n = n + 1 end end return n, more end
local n, more = labels()
assert(n == 100 and more and more.text == "Show the next 100 (150 more)...", tostring(n) .. " " .. tostring(more and more.text))
more.onClick()
n, more = labels()
assert(n == 200 and more and more.text == "Show the next 50 (50 more)...", tostring(n))
more.onClick()
n, more = labels()
assert(n == 250 and more == nil and pane.children[250].text == "cell250", "all drawn, in order, no entry left")
print("ok")
"""
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stderr + out.stdout


def test_a_later_unrelated_loop_in_the_file_does_not_change_the_verdict():
    src = MAP_ICONS.replace("return show\n", "local function other(z) for _, x in ipairs(z) do end end\nreturn show, other\n")
    f = u1(src)
    assert len(f) == 1 and f[0]["conf"] == "high", f              # it once read the header of the file's last loop
