local CONFIG_NAME = "mwpluginpatches"

local config = {}

-- Dynamic plugin active / installed checks
function config.isMcaActive()
    return tes3.isModActive("MCA.esm") or tes3.findGlobal("MCA_Loaded") ~= nil or tes3.getScript("MCA_setup") ~= nil
end

function config.isEbonheartUnderworksActive()
    return tes3.isModActive("Ebonheart_Underworks.esp") or tes3.findGlobal("dd19rebirthConfig") ~= nil or tes3.getScript("dd19_rebirthConfigScript") ~= nil
end

function config.isPsGuardActive()
    return tes3.isModActive("Privileges and Services.esp")
        or tes3.isModActive("Privileges&Services 1.1.esp")
        or tes3.isModActive("Privileges&Services - Improvement Patch.esp")
        or tes3.findGlobal("ABM_ll_GuardCallCell") ~= nil
        or tes3.getScript("ABM_ll_DetectPCCrimeScript") ~= nil
end

function config.isYsmirActive()
    return tes3.isModActive("YARR - yet another race revamp v1.2.ESP")
        or tes3.isModActive("YARR.esp")
        or tes3.getObject("exo_nord_ysmirshield") ~= nil
end

function config.isFriendsAndFrensActive()
    return tes3.isModActive("Friends & Frens - base.esm")
        or tes3.isModActive("Friends & Frens - Vvardenfell.ESP")
        or tes3.isModActive("Friends & Frens - TR.ESP")
        or tes3.isModActive("Friends and Frens.ESP")
        or tes3.isModActive("Friends and Frens - Jiub.esp")
        or tes3.getObject("aa_comp_jiub") ~= nil
end

function config.isLostHeirActive()
    return tes3.isModActive("t_lostheir.esp")
        or tes3.isModActive("LostHeir.esp")
end

-- Resolve dynamic defaults based on whether target plugin is active in load order
local function getDynamicDefaults()
    local mca = config.isMcaActive()
    local eu = config.isEbonheartUnderworksActive()
    local ps = config.isPsGuardActive()
    local ysmir = config.isYsmirActive()
    local fnf = config.isFriendsAndFrensActive()
    local lostHeir = config.isLostHeirActive()

    return {
        -- AutoStartup: Morrowind Comes Alive
        mcaEnabled = mca,
        mcaCompanions = false,
        mcaCourtesans = "none",
        mcaHostileDrunks = false,
        mcaRespawnCaves = false,
        mcaBanditAttacksTowns = false,
        mcaHostileAshlanders = false,
        mcaCrossroadBandits = false,
        mcaPartySize = 0,

        -- AutoStartup: Ebonheart Underworks
        euEnabled = eu,
        euRebirth = false,
        euThiefBranch = false,

        -- Privileges & Services Guard Cell Fix
        psGuardFixEnabled = ps,

        -- Ysmir Combat Shield (YARR)
        ysmirShieldEnabled = ysmir,

        -- Friends & Frens Jiub Companion Delay
        jiubDelayEnabled = fnf,
        jiubDelayMinutes = 5,
        jiubSyncAppearance = true,
        jiubExcludeCensusOffice = true,

        -- The Lost Heir Delayer
        lostHeirDelayEnabled = lostHeir,
    }
end

local loadedConfig = mwse.loadConfig(CONFIG_NAME)
local dynamicDefaults = getDynamicDefaults()

if loadedConfig == nil then
    loadedConfig = {}
    -- Migrate settings from legacy configs if they existed
    local oldAuto = mwse.loadConfig("AutoStartupConfig")
    if oldAuto then
        for k, v in pairs(oldAuto) do
            loadedConfig[k] = v
        end
    end
    local oldFnf = mwse.loadConfig("FriendsAndFrensJiubDelay")
    if oldFnf then
        if oldFnf.enabled ~= nil then loadedConfig.jiubDelayEnabled = oldFnf.enabled end
        if oldFnf.delayMinutes ~= nil then loadedConfig.jiubDelayMinutes = oldFnf.delayMinutes end
        if oldFnf.syncAppearance ~= nil then loadedConfig.jiubSyncAppearance = oldFnf.syncAppearance end
        if oldFnf.excludeCensusOffice ~= nil then loadedConfig.jiubExcludeCensusOffice = oldFnf.excludeCensusOffice end
    end
end

-- Merge with dynamic defaults so newly active plugins default on
for k, v in pairs(dynamicDefaults) do
    if loadedConfig[k] == nil then
        loadedConfig[k] = v
    end
end

-- Copy into config table
for k, v in pairs(loadedConfig) do
    config[k] = v
end

function config.save()
    local toSave = {}
    for k, v in pairs(config) do
        if type(v) ~= "function" then
            toSave[k] = v
        end
    end
    mwse.saveConfig(CONFIG_NAME, toSave)
end

return config
