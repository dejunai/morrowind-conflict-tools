--[[
    mwconsole console_ui: every dependency on UI Expansion's console lives here.
    UIExp builds MenuConsole with a text input "UIEXP:ConsoleInputBox" inside a thin border inside a left-to-right
    block that also holds an unnamed button whose text is "lua" or "mwscript" (the mode switch).
]]
local console_ui = {}

console_ui.MENU = "MenuConsole"
console_ui.INPUT = "UIEXP:ConsoleInputBox"
console_ui.VANILLA_INPUT = "MenuConsole_text_input"
console_ui.ATTACHED = "mwconsole:attached"

-- keyPress data0 values for the arrow keys (MWSE text input)
console_ui.KEY_LEFT = -0x7FFFFFFF
console_ui.KEY_RIGHT = -0x7FFFFFFE
console_ui.KEY_TAB = 9

function console_ui.findMenu() return tes3ui.findMenu(console_ui.MENU) end

function console_ui.findInput(menu)
    menu = menu or console_ui.findMenu()
    return menu and menu:findChild(console_ui.INPUT) or nil
end

--- UIExp's mode button: a button in the input's row whose text is "lua" or "mwscript"
function console_ui.findToggle(menu)
    local input = console_ui.findInput(menu)
    local row = input and input.parent and input.parent.parent
    if not row then return nil end
    for _, child in ipairs(row.children) do
        local t = child.text and child.text:lower()
        if t == "lua" or t == "mwscript" then return child end
        for _, sub in ipairs(child.children or {}) do
            local st = sub.text and sub.text:lower()
            if st == "lua" or st == "mwscript" then return child end
        end
    end
    return nil
end

function console_ui.getMode(menu)
    local toggle = console_ui.findToggle(menu)
    local t = toggle and toggle.text and toggle.text:lower()
    if t == "lua" then return "lua" end
    return "mwscript"
end

--- clicks UIExp's mode button (UIExp does the switching in its mouseClick handler)
function console_ui.toggleMode(menu)
    local toggle = console_ui.findToggle(menu)
    if not toggle then return false end
    toggle:triggerEvent("mouseClick")
    return true
end

function console_ui.isAttached(menu)
    local ok, v = pcall(function() return menu:getPropertyBool(console_ui.ATTACHED) end)
    return ok and v == true
end

function console_ui.markAttached(menu)
    pcall(function() menu:setPropertyBool(console_ui.ATTACHED, true) end)
end

--- text input contents: the cursor is shown as "|" inside the text (UIExp writes it the same way)
function console_ui.splitCursor(text)
    text = text or ""
    local at = text:find("|", 1, true)
    if not at then return text, "" end
    return text:sub(1, at - 1), text:sub(at + 1)
end

function console_ui.joinCursor(before, after)
    return before .. "|" .. (after or "")
end

function console_ui.print(line)
    pcall(tes3ui.log, "%s", line)
end

--- empties the console output
function console_ui.clear(menu)
    menu = menu or console_ui.findMenu()
    if not menu then return false end
    local pane = menu:findChild("MenuConsole_scroll_pane")
    local content = pane and pane:getContentElement()
    if not content then return false end
    content:destroyChildren()
    menu:updateLayout()
    return true
end

return console_ui
