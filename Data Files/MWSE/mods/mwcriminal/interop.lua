local config = require("mwcriminal.config")
local core = require("mwcriminal.core")

local interop = {}

interop.isCompanion = core.isCompanion
interop.isBlacklisted = core.isStealthBlacklisted

function interop.blacklistEntity(id)
    if type(id) ~= "string" or id == "" then return end
    config.companionBlacklist[id:lower()] = true
    mwse.saveConfig("mwcriminal", config)
end

function interop.unblacklistEntity(id)
    if type(id) ~= "string" or id == "" then return end
    config.companionBlacklist[id:lower()] = nil
    mwse.saveConfig("mwcriminal", config)
end

function interop.clearSuspicion(ref)
    if not ref then return end
    local ok, stealthOverhaul = pcall(require, "StormAtronach.SO.interop")
    if not ok or not stealthOverhaul or type(stealthOverhaul.clearSuspicion) ~= "function" then return end
    if type(stealthOverhaul.isEnabled) == "function" then
        local enabledOk, enabled = pcall(stealthOverhaul.isEnabled)
        if not enabledOk or not enabled then return end
    end
    pcall(stealthOverhaul.clearSuspicion, ref)
end

return interop
