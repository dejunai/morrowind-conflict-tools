-- Watch the Skies: if its metadata file is missing, util.metadataMissing() shows a message and then throws,
-- which stops the mod starting. That throw is logged instead and the mod keeps going. Replaces an old
-- hand edit of tew\Watch the Skies\util.lua; that file stays as released. By dej (dejunai).

local config = require("mwpluginpatches.config")
local intercept = require("mwpluginpatches.intercept")

local this = {}
local active = false

function this.init()
    if active then return true end
    if not (config.enabled and config.wtsMetadataLogEnabled and config.isWatchTheSkiesInstalled()) then
        return false
    end
    active = intercept.errorToLog({
        label = "Watch the Skies",
        module = "tew.Watch the Skies.util",
        fn = "metadataMissing",
    }) == true
    if active then
        mwse.log("[mwpluginpatches] Watch the Skies: a missing-metadata error is logged instead of stopping the mod.")
    end
    return active
end

return this
