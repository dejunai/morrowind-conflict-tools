local CONFIG_NAME = "mwmouseguard"

local defaultConfig = {
    enabled = false,
    lockInMenus = true,
    lockInGame = true,
}

local config = mwse.loadConfig(CONFIG_NAME, defaultConfig)

-- Migrate settings from legacy mouseBleedFix if present
local oldConfig = mwse.loadConfig("mouseBleedFix")
if oldConfig then
    if oldConfig.enabled ~= nil and config.enabled == nil then
        config.enabled = oldConfig.enabled
    end
    if oldConfig.lockInMenus ~= nil and config.lockInMenus == nil then
        config.lockInMenus = oldConfig.lockInMenus
    end
    if oldConfig.lockInGame ~= nil and config.lockInGame == nil then
        config.lockInGame = oldConfig.lockInGame
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
