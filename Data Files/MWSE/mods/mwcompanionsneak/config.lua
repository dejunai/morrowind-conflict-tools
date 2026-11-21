local CONFIG_NAME = "mwcompanionsneak"

local defaultConfig = {
    enabled = false,
    includeCreatures = true,       -- Include creature companions (pets, pack guars, summons)
    includeEscorts = true,         -- Include escort quest targets as companions
    blacklistAllCreatures = true,  -- Auto-blacklist ALL creatures from stealth detection
    blacklist = {
        ["_rooster300000000"] = true,
        ["_chicken_stationary00000000"] = true,
    },
    inspectorKey = {
        keyCode = tes3.scanCode.k,
        isShiftDown = false,
        isAltDown = false,
        isControlDown = false,
    },
    debugMode = false,
}

local config = mwse.loadConfig(CONFIG_NAME, defaultConfig)

-- Migrate existing blacklist from Stealth Overhaul or older configs if empty
if config.blacklist == nil or table.empty(config.blacklist) then
    config.blacklist = {
        ["_rooster300000000"] = true,
        ["_chicken_stationary00000000"] = true,
    }
    local soConfig = mwse.loadConfig("Stealth_Overhaul")
    if soConfig and soConfig.blacklist and type(soConfig.blacklist) == "table" then
        for id, state in pairs(soConfig.blacklist) do
            if state then
                config.blacklist[tostring(id):lower()] = true
            end
        end
    end
end

if config.blacklistAllCreatures == nil then
    config.blacklistAllCreatures = true
end

return config
