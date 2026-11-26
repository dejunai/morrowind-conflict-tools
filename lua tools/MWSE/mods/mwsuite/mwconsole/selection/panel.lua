--[[
    mwconsole selection panel: shows details of the reference selected in the console, next to the console.
    Never takes focus from the console and never enters menu mode itself. Built and closed through guard.
]]
local config = require("mwconsole.config")
local guard = require("mwconsole.guard")
local collect = require("mwconsole.selection.collect")
local effects = require("mwconsole.effects.collect")
local window = require("mwconsole.effects.window")

local panel = {}
panel.ID = "mwconsole:SelectionPanel"

local collapsed = {}        -- section -> true, for this session

local function out(line) pcall(tes3ui.log, "%s", line) end

local function copy(text, what)
    local ok = pcall(os.setClipboardText, text)
    pcall(tes3.messageBox, ok and ("Copied " .. what) or "Couldn't reach the clipboard")
end

local function ctrlDown()
    local ok, down = pcall(function() return tes3.worldController.inputController:isControlDown() end)
    return ok and down
end

--- the Show Effects button: what it does for this reference
function panel.effectsButtonMode(ref)
    if not effects.isValid(ref) then return "invalid" end
    if effects.isActor(ref) then return "actor" end
    if config.panel.objectVfx then return "vfx" end
    return "disabled"
end

function panel.showEffects(ref)
    local mode = panel.effectsButtonMode(ref)
    if mode == "invalid" then
        out("Selection is no longer available")
        panel.refresh()
        return nil
    elseif mode == "actor" then
        return window.open(ref)
    elseif mode == "vfx" then
        return window.open(ref, { vfxOnly = true })
    end
    return nil
end

local function runAction(ref, row)
    if row.action == "copy" then
        copy(row.value, row.label)
    elseif type(row.action) == "string" and row.action:find("^copyjson:") then
        if not effects.isValid(ref) then
            out("Selection is no longer available")
            return
        end
        local field = row.action:match("^copyjson:(.+)$")
        local text = collect.toJson(ref[field])
        mwse.log("[mwconsole] %s of %s:\n%s", field, ref.id, text)
        copy(text, row.label .. " (also written to MWSE.log)")
    end
end

local function build(menu, win, ref)
    win.ref = ref
    local vw, vh = tes3ui.getViewportSize()
    menu.width = math.floor(vw * (config.panel.widthPct or 35) / 100)
    menu.maxHeight = math.floor(vh * (config.panel.heightPct or 75) / 100)
    menu.autoHeight = true
    menu.alpha = config.panel.alpha or 0.85
    menu.absolutePosAlignX = config.panel.right and 0.98 or 0.02
    menu.absolutePosAlignY = 0.05
    menu.flowDirection = "top_to_bottom"

    local rows = collect.rows(ref)

    -- header: title + Show Effects + Copy all (always visible, outside the scroll area)
    local head = menu:createBlock({})
    head.widthProportional = 1.0
    head.autoHeight = true
    head.flowDirection = "left_to_right"
    local title = head:createLabel({ text = ref.id })
    title.widthProportional = 1.0
    pcall(function() title.color = tes3ui.getPalette("header_color") end)

    local mode = panel.effectsButtonMode(ref)
    local btn = head:createButton({ text = mode == "vfx" and "Show Visual Effects" or "Show Effects" })
    if mode == "disabled" then
        btn.disabled = true
        pcall(function() btn.widget.state = 2 end)
        btn:register("help", function()
            local tip = tes3ui.createTooltipMenu()
            tip:createLabel({ text = "Only creatures and characters have magic effects" })
        end)
    end
    btn:register("mouseClick", function()
        if btn.disabled then return end
        guard.run("open the effect inspector", panel.showEffects, ref)
    end)
    win.effectsButton = btn

    local copyAll = head:createButton({ text = "Copy all" })
    copyAll:register("mouseClick", function()
        guard.run("copy the selection details", function()
            if not effects.isValid(ref) then out("Selection is no longer available") return end
            copy(table.concat(collect.asText(collect.rows(ref)), "\n"), "all rows")
        end)
    end)

    local scroll = menu:createVerticalScrollPane({})
    scroll.widthProportional = 1.0
    scroll.autoHeight = true
    local body = scroll:getContentElement()
    body.flowDirection = "top_to_bottom"
    body.widthProportional = 1.0

    local lastSection
    for _, row in ipairs(rows) do
        if row.section ~= lastSection then
            lastSection = row.section
            local sec = row.section
            local header = body:createTextSelect({ text = (collapsed[sec] and "+ " or "- ") .. sec })
            header.borderTop = 4
            header:register("mouseClick", function()
                collapsed[sec] = not collapsed[sec]
                panel.refresh()
            end)
        end
        if not collapsed[row.section] then
            local line = string.format("%s: %s", row.label, row.value)
            local el
            if row.action then
                el = body:createTextSelect({ text = line })
                el:register("mouseClick", function() guard.run("copy a value", runAction, ref, row) end)
            else
                el = body:createLabel({ text = line })
            end
            el.wrapText = true
            el.widthProportional = 1.0
        end
    end

    -- the panel goes away with the console (menu mode ends) and before a save loads (guard)
    if not win.menuExitHooked then
        win.menuExitHooked = true
        win:on("menuExit", function() win:close("console closed") end)
    end
end

--- show, refresh or hide the panel for the current console selection
function panel.refresh()
    if not config.enabled or not config.panel.on then return panel.close("off") end
    local console = tes3ui.findMenu("MenuConsole")
    if not console or not console.visible then return panel.close("no console") end
    local ref = tes3ui.getConsoleReference()
    if not ref then return panel.close("no selection") end
    if config.panel.requireCtrl and not ctrlDown() then return panel.close("ctrl") end
    if not guard.isGameLoaded() then return panel.close("no game") end
    local win = guard.openWindow({
        id = panel.ID, where = "show the selection panel", modal = false,
        build = function(menu, win) build(menu, win, ref) end,
    })
    guard.focusConsole()          -- the panel never keeps keyboard focus
    return win
end

function panel.close(reason)
    local w = guard.getWindow(panel.ID)
    if w then w:close(reason) end
    return nil
end

--- the `sel` command: the panel's rows in the console
function panel.printRows(ref, toLog)
    ref = ref or tes3ui.getConsoleReference()
    if not ref then out("Nothing is selected in the console") return end
    for _, line in ipairs(collect.asText(collect.rows(ref))) do
        out(line)
        if toLog then mwse.log("[mwconsole] %s", line) end
    end
end

return panel
