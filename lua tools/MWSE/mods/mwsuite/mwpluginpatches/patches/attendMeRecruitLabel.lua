-- Attend Me (MWSE) recruitment mode casts a 65536-unit eye ray and re-lays-out the HUD every frame just to label the
-- NPC under the crosshair. Here its recruit simulate handler runs one frame in three (the same pace as the command
-- wheel's own target HUD), so the label refreshes every 3rd frame. The click that recruits or dismisses still casts
-- its own ray, so who is recruited is unchanged; frames spent in a menu are passed straight through (the mod returns
-- at once there) and don't count. The mod's files are not edited. By dej (dejunai).
--
-- Stays loaded: recruitment mode can start any time in a session, and the wrap only costs a counter while it is on.
-- Stands down when recruit.lua already has the old luafix edit ("-- local fix (KP2)"), so the label is not cut to
-- one frame in nine.

local config = require("mwpluginpatches.config")
local intercept = require("mwpluginpatches.intercept")

local this = {}
local active = false
local SOURCE = "/mods/attendmemwse/recruit.lua"
local EVERY = 3
this.FILE = "AttendMeMWSE/recruit.lua"
this.MARKER = "-- local fix (KP2)"

function this.prepatched()
    return config.modFileHas(this.FILE, this.MARKER) == true
end

function this.init()
    if active then return true end
    if not (config.enabled and config.attendMeRecruitLabelEnabled and config.isAttendMeInstalled()) then
        return false
    end
    if this.prepatched() then
        mwse.log("[mwpluginpatches] Attend Me: recruit.lua already labels every 3rd frame (old luafix KP2 edit); this intercept stands down.")
        return false
    end
    active = intercept.wrapHandlers({
        label = "Attend Me recruit",
        source = SOURCE,
        event = "simulate",
        what = "every-3rd-frame label",
        wrap = function(original)
            local frame = 0
            return function(e, ...)
                if tes3.menuMode() then return original(e, ...) end
                frame = frame + 1
                if frame % EVERY ~= 1 then return nil end
                return original(e, ...)
            end
        end,
    }) == true
    if active then
        mwse.log("[mwpluginpatches] Attend Me: the recruit-mode aim label refreshes every %d frames.", EVERY)
    end
    return active
end

return this
