local CONFIG_NAME = "mwteleportguard"

local defaultConfig = {
    enabled = true,
    fadeTransition = true,
    fadeDuration = 0.5,
    teleportCompanions = true,
    forceGoodbye = true,
    logToMWSE = true,
}

local config = mwse.loadConfig(CONFIG_NAME, defaultConfig)

-- Migrate settings from legacy DeferredDialogueTeleport if present
local oldConfig = mwse.loadConfig("DeferredDialogueTeleport")
if oldConfig then
    if oldConfig.enabled ~= nil and config.enabled == nil then
        config.enabled = oldConfig.enabled
    end
    if oldConfig.fadeDuration ~= nil and config.fadeDuration == nil then
        config.fadeDuration = oldConfig.fadeDuration
    end
end

function config.save()
    local plain = {}                    -- the functions on this table cannot go into JSON
    for k, v in pairs(config) do
        if type(v) ~= "function" then plain[k] = v end
    end
    mwse.saveConfig(CONFIG_NAME, plain)
end

return config
