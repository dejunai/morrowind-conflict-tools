-- Keg Drip refreshes its drips and puddles from a simulate handler that it lets run every frame and that
-- does the work once a second. Here that handler is called at most once per interval (3 s by default),
-- with e.delta set to the time summed since its last call, so the refresh happens on that cadence.
-- Replaces an old hand edit of KegDrip\main.lua; that file stays as released. By dej (dejunai).

local config = require("mwpluginpatches.config")
local intercept = require("mwpluginpatches.intercept")

local this = {}
local active = false

function this.interval()
    local v = tonumber(config.kegDripIntervalSeconds)
    if not v or v < 1 then return 3 end
    return v
end

function this.init()
    if active then return true end
    if not (config.enabled and config.kegDripCadenceEnabled and config.isKegDripInstalled()) then
        return false
    end
    active = intercept.throttle({
        label = "Keg Drip",
        source = "/mods/kegdrip/main.lua",
        event = "simulate",
        interval = this.interval,
    }) == true
    if active then
        mwse.log("[mwpluginpatches] Keg Drip: its refresh runs at most every %s s.", tostring(this.interval()))
    end
    return active
end

return this
