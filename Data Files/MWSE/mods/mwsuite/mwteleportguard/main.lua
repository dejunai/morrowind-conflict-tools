--[[
    mwteleportguard - Mod-Agnostic Safe Dialogue Teleportation Suite Tool
    
    In Morrowind, authors sometimes script `Player->PositionCell` directly inside dialogue result
    scripts. Teleporting the player while the dialogue menu (`MenuDialog`) is still active causes
    severe engine issues: camera lockups, dialogue UI freezes, actor pointer corruption, companion
    abandonment, and crashes to desktop.

    mwteleportguard is completely mod-agnostic. It detects any script attempting to teleport the player
    during an active dialogue conversation, executes any accompanying quest updates (journal, items,
    variables) immediately, defers the physical cell transition until the dialogue window cleanly closes,
    and teleports the player along with their companions accompanied by a smooth visual fade.
]]

local config = require("mwteleportguard.config")

local pendingTeleport = nil

local function logMsg(fmt, ...)
    if config.logToMWSE then
        mwse.log("[mwteleportguard] " .. string.format(fmt, ...))
    end
end

-- a ; starts a comment, except inside quotes ("Wait; then go")
local function stripComments(cmd)
    return (cmd:gsub("[^\r\n]+", function(line)
        local quoted = false
        for i = 1, #line do
            local c = line:sub(i, i)
            if c == '"' then quoted = not quoted end
            if c == ";" and not quoted then return line:sub(1, i - 1) end
        end
    end))
end

--- Parses PositionCell from a legacy script command string.
--- Returns parsed table and the remaining script command string without the teleport.
local function extractTeleport(cmd)
    if not cmd or cmd == "" then
        return nil, cmd
    end
    -- a conditional teleport ("if ... PositionCell ... endif") must stay in the script: run here, it would
    -- happen every time. Comments (after ;) don't count.
    local uncommented = stripComments(cmd)
    local code = uncommented:gsub('"[^"\r\n]*"', '""'):lower()
    for _, word in ipairs({ "if", "elseif", "else", "while" }) do
        if code:find("%f[%w]" .. word .. "%f[%W]") then
            return nil, cmd
        end
    end

    local pattern = "[Pp][Ll][Aa][Yy][Ee][Rr]%s*->%s*[Pp][Oo][Ss][Ii][Tt][Ii][Oo][Nn][Cc][Ee][Ll][Ll]%s+([%-%d%.]+)[%s,]+([%-%d%.]+)[%s,]+([%-%d%.]+)[%s,]+([%-%d%.]+)[%s,]+([^\r\n;]+)"
    local x, y, z, rot, rawCell = string.match(uncommented, pattern)

    if not (x and y and z and rot and rawCell) then
        return nil, cmd
    end

    -- Clean cell name: strip quotes and leading/trailing whitespace
    local cleanCell = rawCell:match("^%s*[\"]?([^\"\r\n;]+)[\"]?%s*$") or rawCell:gsub("[\"]", ""):match("^%s*(.-)%s*$")

    local tp = {
        x = tonumber(x) or 0,
        y = tonumber(y) or 0,
        z = tonumber(z) or 0,
        rot = tonumber(rot) or 0,
        cell = cleanCell,
    }

    -- Remove the PositionCell line from the command string so the rest can run immediately
    local remaining = uncommented:gsub(pattern, ""):gsub("^%s+", ""):gsub("%s+$", "")

    return tp, remaining
end

local function executePendingTeleport()
    if not pendingTeleport then
        return
    end

    local tp = pendingTeleport
    pendingTeleport = nil

    logMsg("Dialogue window closed. Executing deferred teleport to '%s' (pos: %0.1f, %0.1f, %0.1f; rot: %0.1f)",
        tp.cell, tp.x, tp.y, tp.z, tp.rot)

    timer.frame.delayOneFrame(function()
        local duration = config.fadeTransition and math.max(0, config.fadeDuration or 0.5) or 0

        if duration > 0 then
            tes3.fadeOut({ duration = duration })
        end

        local function teleport()
            local rotZ = math.rad((tp.rot or 0) % 360)
            tes3.positionCell({
                reference = tes3.player,
                cell = tp.cell,
                position = tes3vector3.new(tp.x, tp.y, tp.z),
                orientation = tes3vector3.new(0, 0, rotZ),
                teleportCompanions = config.teleportCompanions,
            })

            if duration > 0 then
                tes3.fadeIn({ duration = duration })
            end
        end

        if duration > 0 then
            timer.start({ type = timer.simulate, duration = duration, callback = teleport })
        else
            timer.delayOneFrame(teleport, timer.simulate)   -- no fade: the shortest wait there is (a timer of 0 never fires)
        end
    end)
end

--- @param e infoResponseEventData
local function onInfoResponse(e)
    if not config.enabled then
        return
    end

    local dialogMenu = tes3ui.findMenu("MenuDialog")
    if not dialogMenu then
        return
    end

    local tp, remainingCmds = extractTeleport(e.command)
    if not tp then
        return
    end

    local actor = e.reference
    local actorName = (actor and actor.object and actor.object.name) or (actor and actor.id) or "Unknown Speaker"

    logMsg("Intercepted Player->PositionCell during dialogue with '%s' to '%s'. Deferring until dialogue exit.",
        actorName, tp.cell)

    -- If the dialogue script had other commands (Journal updates, AddItem, Set, etc.),
    -- run them immediately so quest progress is never lost
    if remainingCmds and remainingCmds:match("%S") then
        logMsg("Executing non-teleport dialogue commands immediately: %s", remainingCmds:gsub("[\r\n]+", " "))
        tes3.runLegacyScript({
            command = remainingCmds,
            reference = actor or tes3.player,
        })
    end

    -- Force dialogue session into Goodbye mode so the player can conclude the dialogue cleanly
    if config.forceGoodbye then
        tes3.runLegacyScript({ command = "goodbye", reference = actor or tes3.player })
    end

    -- Store pending teleport and block the original engine execution
    pendingTeleport = tp
    e.block = true
end

local function onMenuDialogActivated(e)
    e.element:register(tes3.uiEvent.destroy, function()
        executePendingTeleport()
    end)
end

local function onMenuExit(e)
    if pendingTeleport then
        executePendingTeleport()
    end
end

local function onInitialized()
    event.register(tes3.event.infoResponse, onInfoResponse)
    event.register(tes3.event.uiActivated, onMenuDialogActivated, { filter = "MenuDialog" })
    event.register(tes3.event.menuExit, onMenuExit)
    event.register(tes3.event.loaded, function()
        pendingTeleport = nil
    end)

    mwse.log("[mwteleportguard] Initialized mod-agnostic dialogue teleport protection.")
end

event.register(tes3.event.initialized, onInitialized)

event.register(tes3.event.modConfigReady, function()
    require("mwteleportguard.mcm")
end)
