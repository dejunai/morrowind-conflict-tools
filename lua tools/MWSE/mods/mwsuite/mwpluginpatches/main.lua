local config = require("mwpluginpatches.config")

local autoStartup = require("mwpluginpatches.patches.autoStartup")
local pandsfixes = require("mwpluginpatches.patches.pandsfixes")
local ysmirShield = require("mwpluginpatches.patches.ysmirShield")
local jiubDelay = require("mwpluginpatches.patches.jiubDelay")
local friendsAndFrensLore = require("mwpluginpatches.patches.friendsAndFrensLore")
local lostHeirDelay = require("mwpluginpatches.patches.lostHeirDelay")
local mabrDist = require("mwpluginpatches.patches.mabrDist")
local talesHandwritingFix = require("mwpluginpatches.patches.talesHandwritingFix")
local trainerLogUnlock = require("mwpluginpatches.patches.trainerLogUnlock")
local coastGuardContraband = require("mwpluginpatches.patches.coastGuardContraband")
local graphicHerbalismRespawn = require("mwpluginpatches.patches.graphicHerbalismRespawn")
local bardicInstruments = require("mwpluginpatches.patches.bardicInstruments")
local aiVoicesConsole = require("mwpluginpatches.patches.aiVoicesConsole")
local uiExpansionTopics = require("mwpluginpatches.patches.uiExpansionTopics")
local personalEffects = require("mwpluginpatches.patches.personalEffects")

local function onInitialized()
    if not config.enabled then
        mwse.log("[mwpluginpatches] Off: no patch is applied (turn it on in its MCM, then restart).")
        return
    end
    mwse.log("[mwpluginpatches] Initializing unified plugin compatibility patches...")

    -- 1. AutoStartup (MCA & Ebonheart Underworks)
    if (config.mcaEnabled and config.isMcaActive()) or (config.euEnabled and config.isEbonheartUnderworksActive()) then
        autoStartup.init()
    end

    -- 2. Privileges & Services Fixes (Guard Cell Black Screen & Target Topic Filter)
    if (config.pAndSFixesEnabled or config.psGuardFixEnabled) and config.isPAndSActive() then
        pandsfixes.init()
    end

    -- 3. Ysmir Combat Shield (YARR)
    if config.ysmirShieldEnabled and config.isYsmirActive() then
        ysmirShield.init()
    end

    -- 4. Friends & Frens Jiub Companion Delayer
    if config.jiubDelayEnabled and config.isFriendsAndFrensActive() then
        jiubDelay.init()
    end
    if config.friendsAndFrensLoreEnabled and config.isFriendsAndFrensActive() then
        friendsAndFrensLore.init()
    end

    -- 5. The Lost Heir Delayer
    if config.lostHeirDelayEnabled and config.isLostHeirActive() then
        lostHeirDelay.init()
    end

    -- 6. Mabrigash Distribution Popup Suppression
    if config.mabrDistSuppressionEnabled and config.isMabrDistActive() then
        mabrDist.init()
    end

    -- Looping sound scripts (Cave Drips, Yet Another Better Sounds Patch, Expanded Sounds) are left to
    -- conflict-tools --soundfix, which rewrites every GetSoundPlaying-guarded loop at its root.

    -- 10. Clean Tales of Seyda Neen: Illegible Handwriting Dialogue Filter
    if config.talesHandwritingFixEnabled and config.isTalesOfSeydaNeenActive() then
        talesHandwritingFix.init()
    end

    -- 11. Trainer Log: Auto-Unlock Training Topics
    if config.trainerLogUnlockEnabled and config.isTrainerLogActive() then
        trainerLogUnlock.init()
    end

    if config.coastGuardContrabandEnabled then
        coastGuardContraband.init()
    end
    if config.graphicHerbalismRespawnEnabled and config.isGraphicHerbalismActive() then
        graphicHerbalismRespawn.init()
    end
    if config.musicalInstrumentsEnabled and config.isBardicInspirationActive() then
        bardicInstruments.init()
    end
    if config.aiVoicesConsoleEnabled and config.isAiVoicesActive() then
        aiVoicesConsole.init()
    end
    if config.uiExpansionTopicsEnabled and config.isUIExpansionActive() then
        uiExpansionTopics.init()
    end
    if config.personalEffectsEnabled and config.isPersonalEffectsActive() then
        personalEffects.init()
    end

    mwse.log("[mwpluginpatches] Unified plugin compatibility patches initialized.")
end

event.register(tes3.event.initialized, onInitialized)

local function registerModConfig()
    require("mwpluginpatches.mcm")
end
event.register(tes3.event.modConfigReady, registerModConfig)
