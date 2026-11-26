--[[
    mwconsole effect inspector window. Opens through guard.openWindow (game check, error capture, one close path,
    closed before a save loads). Opening it again refreshes the same window for the new reference.
]]
local config = require("mwconsole.config")
local guard = require("mwconsole.guard")
local collect = require("mwconsole.effects.collect")

local window = {}
window.ID = "mwconsole:EffectInspector"

local function out(line)
    pcall(tes3ui.log, "%s", line)
    if config.effects.logToMWSE then mwse.log("[mwconsole] %s", line) end
end
window.out = out

--- console selection, then the crosshair target, then the player
function window.defaultTarget()
    local ref = tes3ui.getConsoleReference and tes3ui.getConsoleReference()
    if ref then return ref end
    local console = tes3ui.findMenu("MenuConsole")
    if console then
        local ok, r = pcall(function() return console:getPropertyObject("MenuConsole_current_ref") end)
        if ok and r then return r end
    end
    return tes3.getPlayerTarget() or tes3.player
end

local function color(name)
    local ok, c = pcall(tes3ui.getPalette, name)
    return ok and c or nil
end

local function label(parent, text, paletteName)
    local l = parent:createLabel({ text = text })
    local c = paletteName and color(paletteName)
    if c then l.color = c end
    l.wrapText = true
    l.widthProportional = 1.0
    return l
end

local function section(parent, title)
    local b = parent:createBlock({})
    b.widthProportional = 1.0
    b.autoHeight = true
    b.borderTop = 8
    b.borderBottom = 2
    label(b, title, "header_color")
end

local build

--- opens (or refreshes) the inspector on ref. opts = { vfxOnly = bool, statusSetter = fn }
function window.open(ref, opts)
    opts = opts or {}
    if not guard.isGameLoaded() then return guard.needGame(opts.statusSetter) end
    ref = ref or window.defaultTarget()
    if not ref then
        out("mwconsole: nothing to inspect")
        return nil
    end
    if not collect.isValid(ref) then
        out("Selection is no longer available")
        return nil
    end
    return guard.openWindow({
        id = window.ID, title = "Effect inspector (mwconsole)", where = "open the effect inspector",
        statusSetter = opts.statusSetter,
        build = function(menu, win) build(menu, win, ref, opts) end,
    })
end

build = function(menu, win, ref, opts)
    win.ref = ref
    menu.width = 720
    menu.height = 560
    menu.minWidth = 560
    menu.minHeight = 400
    menu.positionX = 0.5
    menu.positionY = 0.5
    local main = menu:createBlock({})
    main.widthProportional = 1.0
    main.heightProportional = 1.0
    main.flowDirection = "top_to_bottom"

    local obj = ref.object
    local name = (obj and obj.name ~= "" and obj.name) or ref.id
    local dead = collect.isDead(ref)
    local cell = ref.cell and (ref.cell.editorName or ref.cell.id) or "?"
    label(main, string.format("%s%s", name, dead and " (dead)" or ""), "header_color")
    label(main, string.format("Base %s   Reference %s   Cell %s", obj and obj.id or "?", ref.id, cell), "normal_color")
    local mobile = ref.mobile
    if mobile and mobile.health then
        label(main, string.format("Health %d/%d   Magicka %d/%d   Fatigue %d/%d",
            mobile.health.current or 0, mobile.health.base or 0, mobile.magicka.current or 0, mobile.magicka.base or 0,
            mobile.fatigue.current or 0, mobile.fatigue.base or 0), "active_color")
    end

    local scroll = main:createVerticalScrollPane({})
    scroll.widthProportional = 1.0
    scroll.heightProportional = 1.0
    local body = scroll:getContentElement()
    body.flowDirection = "top_to_bottom"
    body.widthProportional = 1.0

    local active = {}
    if not opts.vfxOnly then
        active = collect.active(ref)
        section(body, "Active magic effects")
        if #active == 0 then label(body, "No active effects", "disabled_color") end
        for _, a in ipairs(active) do
            local time = a.permanent and "constant" or string.format("%ds left of %ds", math.floor(a.remaining), math.floor(a.duration))
            label(body, string.format("%s, %d pts, %s", a.name, a.magnitude, time), "active_color")
            label(body, string.format("    from %s [%s], cast by %s", a.sourceName, a.sourceId, a.caster), "normal_color")
        end
        if config.effects.showSpells then
            section(body, "Spells and abilities")
            local spells = collect.spells(ref)
            if #spells == 0 then label(body, "No spells or abilities", "disabled_color") end
            for _, s in ipairs(spells) do
                label(body, string.format("[%s] %s: %s", s.type, s.name, s.effects), "normal_color")
            end
        end
        if config.effects.showEquipment then
            section(body, "Enchanted equipment")
            local items = collect.enchantedEquipment(ref)
            if #items == 0 then label(body, "No enchanted equipment", "disabled_color") end
            for _, it in ipairs(items) do label(body, string.format("%s: %s", it.name, it.effects), "normal_color") end
        end
    end
    if config.effects.showVFX or opts.vfxOnly then
        section(body, "Visual-effect scene nodes")
        local nodes = collect.vfxNodes(ref, collect.parseWords(config.effects.vfxWords))
        if #nodes == 0 then label(body, "No visual-effect nodes", "disabled_color") end
        for _, n in ipairs(nodes) do
            label(body, string.format("%s[%s] %s", string.rep("  ", math.min(n.depth, 8)), n.type, n.name), "normal_color")
        end
    end

    local buttons = main:createBlock({})
    buttons.widthProportional = 1.0
    buttons.autoHeight = true
    buttons.flowDirection = "left_to_right"
    if not opts.vfxOnly then
        local purge = buttons:createButton({ text = "Purge active effects" })
        if #active == 0 then
            purge.disabled = true
            pcall(function() purge.widget.state = 2 end)    -- greyed out
        end
        purge:register("mouseClick", function()
            if #active == 0 then return end
            window.purge(ref)
            window.open(ref, opts)
        end)
    end
    local refresh = buttons:createButton({ text = "Refresh" })
    refresh:register("mouseClick", function() window.open(ref, opts) end)
    local spacer = buttons:createBlock({})
    spacer.widthProportional = 1.0
    local close = buttons:createButton({ text = "Close" })
    close:register("mouseClick", function() win:close("button") end)
end

--- purge with the same checks and messages wherever it is called from
function window.purge(ref, statusSetter)
    if not guard.isGameLoaded() then return guard.needGame(statusSetter) end
    ref = ref or window.defaultTarget()
    if not ref or not collect.isValid(ref) then
        out("Selection is no longer available")
        return false
    end
    local ok, count = guard.run("purge active effects", function()
        local n = collect.purge(ref)
        local name = (ref.object and ref.object.name ~= "" and ref.object.name) or ref.id
        out(string.format("Purged %d active effect(s) from %s (%s).", n, name, ref.id))
        tes3.messageBox(string.format("Purged %d active effect(s) from %s.", n, name))
        return n
    end)
    return ok and count
end

--- a short report in the console (the "showeffects" command prints this, then opens the window)
function window.printSummary(ref)
    local name = (ref.object and ref.object.name ~= "" and ref.object.name) or ref.id
    out(string.format("Effects on %s (%s): %d active", name, ref.id, #collect.active(ref)))
end

return window
