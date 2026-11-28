"""Suite MCM settings and actions must explain what they do."""
from pathlib import Path

import mwdialog_lua
from test_cr18_suite_logging import LUAJIT, need_lua


ROOT = Path(__file__).resolve().parents[1]
MODS = ROOT / "lua tools" / "MWSE" / "mods" / "mwsuite"
CONTROLS = {
    "createYesNoButton", "createOnOffButton", "createSlider", "createDropdown",
    "createKeyBinder", "createMouseBinder", "createButton", "createExclusionsPage",
}


def test_suite_mcm_controls_have_descriptions():
    missing = []
    for mod in sorted(MODS.iterdir()):
        if not (mod / "main.lua").is_file():
            continue
        if mod.name == "mwmanagermenu":
            continue
        for path in mod.rglob("*.lua"):
            tokens = mwdialog_lua.tokenize(path.read_text(encoding="utf-8"))
            for i, token in enumerate(tokens[:-2]):
                if token.v not in CONTROLS or i == 0 or tokens[i - 1].v != ":":
                    continue
                j = i + 1
                if tokens[j].v == "(":
                    j += 1
                if tokens[j].v != "{":
                    continue
                depth, fields = 0, set()
                for k in range(j, len(tokens) - 1):
                    value = tokens[k].v
                    if value == "{":
                        depth += 1
                    elif value == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    elif depth == 1 and tokens[k + 1].v == "=":
                        fields.add(value)
                # Native UI buttons use text, not the MCM buttonText property.
                if token.v == "createButton" and "text" in fields and "buttonText" not in fields:
                    continue
                if "description" not in fields:
                    missing.append(f"{path.relative_to(MODS)}:{token.line}")
    assert not missing, missing


def test_every_suite_settings_page_is_registered():
    missing = []
    for mod in sorted(MODS.iterdir()):
        if not (mod / "main.lua").is_file() or mod.name == "mwmanagermenu":
            continue
        code = "\n".join(p.read_text(encoding="utf-8") for p in mod.rglob("*.lua"))
        if "createTemplate" in code and not any(call in code for call in (
                ":register()", "mcm.register(", "registerModConfig(", "mcm.registerMCM(")):
            missing.append(mod.name)
    assert not missing, missing


@need_lua
def test_shared_menu_styles_registered_pages_and_preserves_callbacks():
    import subprocess

    lua = LUAJIT
    script = r'''
local ready, registered
event = { register = function(_, callback) ready = callback end }
mwse = {
    registerModConfig = function(name, package) registered = { name, package } end,
    log = function(message, ...) if message:find("failed") then error(message:format(...)) end end,
}
table.size = function(t)
    local count = 0
    for _ in pairs(t) do count = count + 1 end
    return count
end
tes3 = { palette = { headerColor = 1 }, uiState = { active = 4 } }
tes3ui = { getPalette = function(color) return { color, color, color } end }
local function element(text)
    local node = { children = {}, text = text, widget = {}, handlers = {} }
    function node:add(text)
        local child = element(text)
        self.children[#self.children + 1] = child
        return child
    end
    function node:createBlock() return self:add() end
    function node:createLabel(params) return self:add(params.text) end
    function node:createButton(params) return self:add(params.text) end
    function node:register(eventName, callback) self.handlers[eventName] = callback end
    function node:destroyChildren() self.children = {} end
    function node:getTopLevelMenu() return self end
    function node:updateLayout() end
    return node
end

local manager = dofile(arg[1])
local function capture(mod, package)
    local source = "@MWSE/mods/mwsuite/" .. mod .. "/mcm.lua"
    assert(loadstring("local p = ...; mwse.registerModConfig('Original label', p); return true", source))(package)
end

local info = {
    elements = { label = {}, info = {} },
    postCreate = function(self) self.elements.info.text = "Populated by the original callback" end,
}
local category = { elements = { label = {} }, components = { info } }
local sidebar = { elements = {}, components = {} }
local hover = { elements = { info = {} } }
local page = { elements = { mouseOver = hover }, components = { category }, sidebar = sidebar }
local firstContent, secondContent, saves
saves = 0
capture("mwsaveguard", {
    template = { pages = { page } },
    onCreate = function(container)
        firstContent = container
        category:postCreate()
        info:postCreate()
        page:postCreate()
    end,
    onClose = function(container) assert(container == firstContent); saves = saves + 1 end,
    onSearch = function(text) return text == "original description" end,
})
capture("mwteleportguard", {
    onCreate = function(container) secondContent = container end,
    onClose = function(container) assert(container == secondContent); saves = saves + 1 end,
})
for _, mod in ipairs(manager.suite) do
    if not manager.captured[mod] then capture(mod, { onCreate = function() end }) end
end
ready()
assert(registered[1] == "MW Conflict Tools")
local combined = registered[2]
local root = element()
combined.onCreate(root)
local tabCount = 0
for index = 1, #root.children - 1 do
    for _, tab in ipairs(root.children[index].children) do
        assert(tab.text and tab.text ~= "Original label")
        tabCount = tabCount + 1
    end
end
assert(tabCount == 19)
assert(root.children[1].children[1].widget.state == tes3.uiState.active)
assert(category.elements.label.font == 0 and category.elements.label.color[1] == 1)
assert(info.elements.label.font == 0)
assert(info.elements.info.font == 1 and hover.elements.info.font == 1)
assert(info.elements.info.text == "Populated by the original callback")
assert(combined.onSearch("original description"))
root.children[1].children[2].handlers.mouseClick()
assert(saves == 1 and secondContent)
combined.onClose()
assert(saves == 2)
'''
    subprocess.run(
        [str(lua), "-", str(MODS / "mwmanagermenu" / "main.lua")],
        input=script, text=True, check=True,
    )
