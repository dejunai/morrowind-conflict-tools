"""Effect Inspector exposes its hotkey through the MWSE template registry."""
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
LUAJIT = Path(os.environ.get("MWMANAGER_LUAJIT", ROOT / "tools" / "luajit" / "luajit.exe"))
pytestmark = pytest.mark.skipif(not LUAJIT.is_file(), reason="LuaJIT not available")


def test_keybind_template_is_registered():
    script = r'''
local config = { save = function() end }
package.preload["mweffectinspector.config"] = function() return config end
package.preload["mweffectinspector.inspector"] = function() return {} end
local registered
local function category()
    local c = { components = {} }
    function c:createCategory() local child = category(); self.components[#self.components + 1] = child; return child end
    function c:createInfo() end
    function c:createYesNoButton() end
    function c:createButton() end
    function c:createKeyBinder(data)
        self.components[#self.components + 1] = { class = "KeyBinder", componentType = "Setting", variable = data.variable }
    end
    return c
end
mwse = { mcm = {
    createTableVariable = function(data) return data end,
    createTemplate = function()
        local t = { pages = {} }
        function t:createSideBarPage()
            local page = category()
            page.sidebar = category()
            self.pages[#self.pages + 1] = page
            return page
        end
        function t:register() registered = { template = self } end
        return t
    end,
} }
tes3 = { getFileSource = function() return nil end }
assert(loadfile(arg[1]))()
assert(registered and registered.template, "core keybind menu requires package.template")
local found
local function visit(c)
    for _, child in ipairs(c.components) do
        if child.class == "KeyBinder" then found = child end
        if child.components then visit(child) end
    end
end
for _, page in ipairs(registered.template.pages) do visit(page) end
assert(found and found.variable.id == "hotkey" and found.variable.table == config)
'''
    mod = ROOT / "lua tools" / "MWSE" / "mods" / "mwsuite" / "mweffectinspector" / "mcm.lua"
    result = subprocess.run([str(LUAJIT), "-", str(mod)], input=script, capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr
