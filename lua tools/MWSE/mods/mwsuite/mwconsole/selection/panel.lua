--[[
    mwconsole selection details, shown two ways, both built and closed through guard:
    * the panel next to the console for the console selection. Never takes focus from the console, never enters
      menu mode itself and is never brought in front of the console (the engine only picks world objects for the
      console while MenuConsole is on top); it goes away with the console.
    * the details window (the hotkey, default Alt+I, works with the console open too): the same rows on the console
      selection, else the crosshair target, else the player. It enters menu mode and has a Close button; Esc, a save load and closing menu
      mode close it.
    Both have a Show Effects button that opens the effect inspector on the shown reference (greyed on non-actors).
]]
local config = require("mwconsole.config")
local guard = require("mwconsole.guard")
local collect = require("mwconsole.selection.collect")
local effects = require("mwconsole.effects.collect")
local window = require("mwconsole.effects.window")

local panel = {}
panel.ID = "mwconsole:SelectionPanel"
panel.DETAILS_ID = "mwconsole:SelectionDetails"

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

function panel.showEffects(ref, win)
    local mode = panel.effectsButtonMode(ref)
    if mode == "invalid" then
        out("Selection is no longer available")
        if win and win.id == panel.DETAILS_ID then win:close("stale") else panel.refresh() end
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

local function build(menu, win, ref, standalone)
    win.ref = ref
    local vw, vh = tes3ui.getViewportSize()
    if type(vw) ~= "number" or vw < 1 then vw = 1024 end
    if type(vh) ~= "number" or vh < 1 then vh = 768 end
    -- explicit pixel size: autoHeight plus a scroll pane that is also autoHeight collapses the
    -- frame (fixedFrame also auto-sizes width unless autoWidth is off, so widthProportional children
    -- and the frame size each other and shrink to the border). Same pattern as the effect inspector.
    local width = math.max(320, math.floor(vw * (config.panel.widthPct or 35) / 100))
    local height = math.max(240, math.floor(vh * (config.panel.heightPct or 75) / 100))
    menu.autoWidth = false
    menu.autoHeight = false
    menu.minWidth = 320
    menu.minHeight = 240
    -- keep a size the user already dragged the details window to (rebuild would otherwise reset it)
    if not (standalone and win.sized and menu.width >= 320 and menu.height >= 240) then
        menu.width = width
        menu.height = height
    end
    if standalone then win.sized = true end
    menu.flowDirection = "top_to_bottom"
    if standalone then
        menu.absolutePosAlignX = 0.5
        menu.absolutePosAlignY = 0.5
    else
        menu.alpha = config.panel.alpha or 0.85
        menu.absolutePosAlignX = config.panel.right and 0.98 or 0.02
        menu.absolutePosAlignY = 0.05
    end
    local function rebuild()
        if standalone then panel.openDetails(ref) else panel.refresh() end
    end

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
        guard.run("open the effect inspector", panel.showEffects, ref, win)
    end)
    win.effectsButton = btn

    local copyAll = head:createButton({ text = "Copy all" })
    copyAll:register("mouseClick", function()
        guard.run("copy the selection details", function()
            if not effects.isValid(ref) then out("Selection is no longer available") return end
            copy(table.concat(collect.asText(collect.rows(ref)), "\n"), "all rows")
        end)
    end)
    if standalone then
        local close = head:createButton({ text = "Close" })
        close:register("mouseClick", function() win:close("button") end)
    end

    local scroll = menu:createVerticalScrollPane({})
    scroll.widthProportional = 1.0
    scroll.heightProportional = 1.0
    scroll.autoHeight = false
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
                guard.run("show the selection details", rebuild)
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

    -- guard closes both kinds when menu mode ends (the console closing, or anything else) and before a save loads
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
        id = panel.ID, where = "show the selection panel", modal = false, keepConsoleOnTop = true,
        build = function(menu, win) build(menu, win, ref) end,
    })
    guard.focusConsole()          -- the panel never keeps keyboard focus
    return win
end

--- what the hotkey shows: the console selection, else the crosshair target, else the player
function panel.hotkeyTarget()
    local ref = tes3ui.getConsoleReference()
    if ref and effects.isValid(ref) then return ref end
    local target = tes3.getPlayerTarget()
    if target and effects.isValid(target) then return target end
    return tes3.player
end

--- the details window (the hotkey and the MCM button). Needs a loaded game; refreshes in place if already open.
function panel.openDetails(ref)
    if not config.enabled then return nil end
    if not guard.isGameLoaded() then return guard.needGame() end
    ref = ref or panel.hotkeyTarget()
    if not ref or not effects.isValid(ref) then
        out("Selection is no longer available")
        return nil
    end
    return guard.openWindow({
        id = panel.DETAILS_ID, title = "Selection details (mwconsole)", where = "open the selection details",
        modal = true, dragFrame = true,
        build = function(menu, win) build(menu, win, ref, true) end,
    })
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
