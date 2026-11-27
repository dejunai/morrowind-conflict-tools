local CONFIG_NAME = "mwexitguard"

local defaultConfig = {
    enabled = false,
    skipConfirmation = false,
    enableAltF4 = true,
    blockNewGameInSession = true,   -- no second New Game in one session (newgame.lua); separate from `enabled`
    logToMWSE = true,
}

local config = mwse.loadConfig(CONFIG_NAME, defaultConfig)

function config.save()
    local plain = {}
    for k, v in pairs(config) do
        if type(v) ~= "function" then
            plain[k] = v
        end
    end
    mwse.saveConfig(CONFIG_NAME, plain)
end

return config
