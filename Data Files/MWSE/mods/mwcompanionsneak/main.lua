--[[
    mwcompanionsneak
    Author: Antigravity

    Core Goals:
      1. Eliminate detection feedback from companions: Prevents followers, companions,
         and friendly summons from detecting the sneaking player, preserving the sneak crosshair,
         hidden indicator, and stealth bar.
      2. Entity Blacklisting & Creature Disregard: Auto-blacklists all creatures from stealth detection,
         and supports blacklisting specific false-positive entities (such as critters, ambient animals, or roosters).
      3. Stealth Mod Agnostic: Operates cleanly with vanilla stealth, Stealth Overhaul (SO),
         Skillful Sneaking, or any other sneaking overhaul.
]]

local config = require("mwcompanionsneak.config")
local interop = require("mwcompanionsneak.interop")
local inspectorUI = require("mwcompanionsneak.inspectorUI")

-- Backward compatibility aliases
package.loaded["companionsneak"] = interop
package.loaded["companionsneak.config"] = config
package.loaded["companionsneak.interop"] = interop
package.loaded["mwcompanionsneak"] = interop
package.loaded["mwcompanionsneak.interop"] = interop

local function logDebug(fmt, ...)
    if config.debugMode then
        mwse.log("[mwcompanionsneak] " .. fmt, ...)
    end
end

--- Intercept detectSneak events before the engine or other mods evaluate them.
--- Priority 2000 ensures this runs before default engine logic and other mods (e.g. SO at 1000).
--- @param e detectSneakEventData
local function onDetectSneak(e)
    if not config.enabled then return end
    if e.target ~= tes3.mobilePlayer then return end

    local detector = e.detector
    if not detector then return end

    local isComp = interop.isCompanion(detector)
    local isBl = interop.isBlacklisted(detector)

    if isComp or isBl then
        e.isDetected = false
        detector.isPlayerDetected = false
        detector.isPlayerHidden = true

        local ref = detector.reference
        if ref then
            interop.clearSuspicion(ref)
        end

        logDebug("Suppressed sneak detection from %s: %s",
            isComp and "companion" or "blacklisted entity",
            ref and ref.id or "unknown")

        return false -- Claims the event, halting lower priority handlers
    end
end
event.register(tes3.event.detectSneak, onDetectSneak, { priority = 2000 })

--- Periodic sweep to maintain companion and blacklisted entity hidden state while sneaking.
local function onSweep()
    if not config.enabled or tes3.menuMode() then return end
    local mp = tes3.mobilePlayer
    if not mp or not mp.isSneaking then return end

    -- 1. Check friendly actors
    local friendlies = mp.friendlyActors
    if friendlies then
        for mob in tes3.iterate(friendlies) do
            if interop.isCompanion(mob) or interop.isBlacklisted(mob) then
                mob.isPlayerDetected = false
                mob.isPlayerHidden = true
                if mob.reference then
                    interop.clearSuspicion(mob.reference)
                end
            end
        end
    end

    -- 2. Check nearby blacklisted actors
    local nearby = tes3.findActorsInProximity({ reference = tes3.player, range = 2000 })
    if nearby then
        for _, mob in ipairs(nearby) do
            if mob ~= mp and interop.isBlacklisted(mob) then
                mob.isPlayerDetected = false
                mob.isPlayerHidden = true
                if mob.reference then
                    interop.clearSuspicion(mob.reference)
                end
            end
        end
    end
end

-- Keybind listener for Detection Inspector UI
local function onKeyDown(e)
    if not config.enabled then return end
    local bind = config.inspectorKey
    if not bind or not bind.keyCode then return end

    if e.keyCode == bind.keyCode then
        if bind.isShiftDown and not e.isShiftDown then return end
        if bind.isAltDown and not e.isAltDown then return end
        if bind.isControlDown and not e.isControlDown then return end

        if tes3ui.findMenu(tes3ui.registerID("mwcompanionsneak:DetectionInspector")) then
            inspectorUI.close()
        elseif not tes3ui.menuMode() then
            inspectorUI.open()
        end
    end
end
event.register("keyDown", onKeyDown)

event.register(tes3.event.loaded, function()
    timer.start({
        type = timer.simulate,
        duration = 0.35,
        iterations = -1,
        callback = onSweep,
    })
    mwse.log("[mwcompanionsneak] Initialized successfully. Companion sneak disregard and entity blacklist active.")
end)

-- Register Mod Config Menu
local function registerModConfig()
    require("mwcompanionsneak.mcm")
end
event.register(tes3.event.modConfigReady, registerModConfig)

return interop
