local config = require("mwpluginpatches.config")

local autoStartup = require("mwpluginpatches.patches.autoStartup")
local psguardfix = require("mwpluginpatches.patches.psguardfix")
local ysmirShield = require("mwpluginpatches.patches.ysmirShield")
local jiubDelay = require("mwpluginpatches.patches.jiubDelay")
local lostHeirDelay = require("mwpluginpatches.patches.lostHeirDelay")

local function onInitialized()
    mwse.log("[mwpluginpatches] Initializing unified plugin compatibility patches...")

    -- 1. AutoStartup (MCA & Ebonheart Underworks)
    if (config.mcaEnabled and config.isMcaActive()) or (config.euEnabled and config.isEbonheartUnderworksActive()) then
        autoStartup.init()
    end

    -- 2. Privileges & Services Guard Cell Black Screen Fix
    if config.psGuardFixEnabled and config.isPsGuardActive() then
        psguardfix.init()
    end

    -- 3. Ysmir Combat Shield (YARR)
    if config.ysmirShieldEnabled and config.isYsmirActive() then
        ysmirShield.init()
    end

    -- 4. Friends & Frens Jiub Companion Delayer
    if config.jiubDelayEnabled and config.isFriendsAndFrensActive() then
        jiubDelay.init()
    end

    -- 5. The Lost Heir Delayer
    if config.lostHeirDelayEnabled and config.isLostHeirActive() then
        lostHeirDelay.init()
    end

    mwse.log("[mwpluginpatches] Unified plugin compatibility patches initialized.")
end

event.register(tes3.event.initialized, onInitialized)

local function registerModConfig()
    require("mwpluginpatches.mcm")
end
event.register(tes3.event.modConfigReady, registerModConfig)
