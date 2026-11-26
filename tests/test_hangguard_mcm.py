"""Shared Guard & Hang Watch MCM: one template, two pages, both configs saved on close."""
import os
import re
import subprocess

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MODS = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite").replace("\\", "/")
MENU = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwmanagermenu", "main.lua")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")


HARNESS = r"""
package.path = MODS .. "/?.lua;" .. package.path
local registry = {}
event = {
    register = function(et, cb, opts)
        registry[et] = registry[et] or {}
        table.insert(registry[et], cb)
    end,
    unregister = function() end,
    isRegistered = function() return false end,
}
local saved = {}
local components, registered = {}, nil
local function component(kind, data)
    return setmetatable({ kind = kind, data = data or {}, components = {} }, {
        __index = function(t, k)
            return function(self, d)
                local child = component(k, type(d) == "table" and d or { label = d })
                self.components[#self.components + 1] = child
                components[#components + 1] = child
                return child
            end
        end,
    })
end
mwse = {
    loadConfig = function(_, d) local c = {} for k, v in pairs(d) do c[k] = v end return c end,
    saveConfig = function(name, cfg) saved[name] = cfg end,
    log = function() end,
    mcm = {
        createTableVariable = function(d) return d end,
        createTemplate = function(d)
            local t = component("template", d)
            t.register = function(self) registered = self end
            t.createSideBarPage = function(self, d2)
                local p = component("page", d2)
                self.components[#self.components + 1] = p
                components[#components + 1] = p
                return p
            end
            return t
        end,
    },
}
lfs = { mkdir = function() end, fileexists = function() return true end }
timer = { real = 1, start = function() return { cancel = function() end } end }
tes3 = {
    event = setmetatable({}, { __index = function(_, k) return k end }),
}
tes3ui = {
    registerID = function(name) return name end,
    findMenu = function() return nil end,
    createHelpLayerMenu = function()
        return { autoWidth = true, autoHeight = true, consumeMouseEvents = false,
                 findChild = function() return nil end,
                 createLabel = function() return { consumeMouseEvents = false } end,
                 updateLayout = function() end }
    end,
    findHelpLayerMenu = function() return nil end,
}
include = function(name)
    local ok, result = pcall(require, name)
    if ok then return result end
    if type(result) == "string" and result:find("module '" .. name .. "' not found", 1, true) then
        return nil
    end
    error(result)
end
-- game order: mwguard loads first (load-priority 1000000), then hangwatch, then modConfigReady
require("mwguard.main")
require("mwhangwatch.main")
for _, fn in ipairs(registry.modConfigReady or {}) do fn() end
"""


def run(tmp_path, body):
    script = tmp_path / "t.lua"
    script.write_text("MODS = [[" + MODS + "]]\n" + HARNESS + body, encoding="utf-8")
    r = subprocess.run([LUAJIT, str(script)], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip().endswith("OK"), r.stdout + r.stderr


def test_one_template_named_guard_and_hang_watch(tmp_path):
    run(tmp_path, r"""
assert(registered, "no template registered")
assert(registered.data.name == "Guard & Hang Watch", tostring(registered.data.name))
local labels = {}
for _, p in ipairs(registered.components) do
    if p.data and p.data.label then labels[#labels + 1] = p.data.label end
end
assert(labels[1] == "Memory & Hang Log", tostring(labels[1]))
assert(labels[2] == "Lua Profiler", tostring(labels[2]))
assert(#labels == 2, table.concat(labels, ", "))
print("OK")
""")


def test_pages_have_memory_hang_log_and_profiler_controls(tmp_path):
    run(tmp_path, r"""
local function find(id, tableRef)
    for _, c in ipairs(components) do
        local v = c.data and c.data.variable
        if v and v.id == id and (tableRef == nil or v.table == tableRef) then return c end
    end
end
local hang = require("mwhangwatch.mcm")
assert(hang and hang.config, "hangwatch hooks missing")
assert(find("showAddressSpace"), "HUD switch missing")
assert(find("memWarn", hang.config), "memory warning switch missing")
assert(find("memLimit", hang.config), "memory warning level missing")
assert(find("enabled", hang.config), "hangwatch enable missing")
assert(find("audio", hang.config), "audio switch missing")
assert(find("soundLines", hang.config), "sound lines slider missing")
assert(find("EnableLogTimestamps"), "enable timestamps switch missing")
assert(find("logTimestampMode"), "timestamp style dropdown missing")
assert(find("costMs") and find("reportSeconds") and find("sampleEvery") and find("logNoticeToMWSE"),
    "profiler sliders missing")
local n = 0
for _, c in ipairs(components) do
    local v = c.data and c.data.variable
    if v and v.id == "enabled" then n = n + 1 end
end
assert(n == 2, "expected hangwatch and profiler enable switches, got " .. n)
local cats = {}
for _, c in ipairs(components) do
    if c.kind == "createCategory" then cats[#cats + 1] = c.data.label end
end
assert(cats[1] == "Memory" and cats[2] == "Hang log", table.concat(cats, ", "))
local enable, style
for _, c in ipairs(components) do
    if c.data and c.data.label == "Enable timestamps" then enable = c end
    if c.data and c.data.label == "Timestamp style" then style = c end
end
assert(enable and enable.data.description:find("Off until", 1, true), "enable timestamps description")
assert(style and style.kind == "createDropdown", "timestamp style is not a dropdown")
local values = {}
for _, opt in ipairs(style.data.options or {}) do values[#values + 1] = opt.value end
assert(values[1] == "wallclock" and values[2] == "elapsed", table.concat(values, ", "))
assert(style.data.description:find("%[17:42:33%]", 1) and style.data.description:find("%[000042%]", 1),
    "timestamp style description")
print("OK")
""")


def test_on_close_saves_both_config_files(tmp_path):
    run(tmp_path, r"""
local hang = require("mwhangwatch.mcm")
hang.config.enabled = true
hang.config.memWarn = true
assert(registered.onClose, "no onClose")
registered.onClose()
assert(saved.mwguard, "mwguard.json not saved")
assert(saved.mwhangwatch, "mwhangwatch.json not saved")
assert(saved.mwhangwatch == hang.config)
assert(saved.mwhangwatch.enabled == true and saved.mwhangwatch.memWarn == true)
print("OK")
""")


def test_hangwatch_enable_callback_applies_right_away(tmp_path):
    run(tmp_path, r"""
local hang = require("mwhangwatch.mcm")
local applied = 0
hang.applySettings = function() applied = applied + 1 end
local btn
for _, c in ipairs(components) do
    local v = c.data and c.data.variable
    if v and v.id == "enabled" and v.table == hang.config then btn = c end
end
assert(btn and btn.data.callback, "hangwatch enable has no callback")
btn.data.callback()
assert(applied == 1, "applySettings not called: " .. applied)
print("OK")
""")


def test_mwmanagermenu_lists_mwguard_not_a_second_hangwatch_tab():
    text = open(MENU, encoding="utf-8").read()
    body = re.search(r"local SUITE = \{(.*?)\}", text, re.S).group(1)
    names = re.findall(r'"([^"]+)"', body)
    assert "mwguard" in names
    assert "mwhangwatch" not in names, names


def test_hangwatch_no_longer_registers_its_own_template():
    main = open(os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwhangwatch", "main.lua"),
                encoding="utf-8").read()
    assert "modConfigReady" not in main
    assert 'include("mwhangwatch.mcm")' in main
    mcm = open(os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwhangwatch", "mcm.lua"),
               encoding="utf-8").read()
    assert 'id = "enabled"' in mcm
