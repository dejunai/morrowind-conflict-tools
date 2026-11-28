-- Watch the Skies: if its metadata file is missing, util.metadataMissing() shows a message and then throws,
-- which stops the mod starting. That throw is logged instead and the mod keeps going. Replaces an old
-- hand edit of tew\Watch the Skies\util.lua; that file stays as released. By dej (dejunai).
-- Watch the Skies only calls it from its initialized handler, so the guard is taken off again once every
-- initialized handler has run: nothing of it stays for the rest of the session.

local config = require("mwpluginpatches.config")
local intercept = require("mwpluginpatches.intercept")

local this = {}
local active = false
local rule
local LAST = -9999         -- after every other initialized handler (Watch the Skies' runs at -150)

function this.unload()
    if rule then intercept.removeErrorToLog(rule) end
    rule = nil
    active = false
end

function this.init()
    if active then return true end
    if not (config.enabled and config.wtsMetadataLogEnabled and config.isWatchTheSkiesInstalled()) then
        return false
    end
    rule = {
        label = "Watch the Skies",
        module = "tew.Watch the Skies.util",
        fn = "metadataMissing",
    }
    active = intercept.errorToLog(rule) == true
    if active then
        event.register(tes3.event.initialized, this.unload, { priority = LAST })
        mwse.log("[mwpluginpatches] Watch the Skies: a missing-metadata error is logged instead of stopping the mod (until initialized ends).")
    else
        rule = nil
    end
    return active
end

return this
