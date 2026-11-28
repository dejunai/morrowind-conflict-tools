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
local mwcaInterop = require("mwpluginpatches.patches.mwcaInterop")
local wtsMetadataLog = require("mwpluginpatches.patches.wtsMetadataLog")
local partyAlchemyModuleBox = require("mwpluginpatches.patches.partyAlchemyModuleBox")
local kegDripCadence = require("mwpluginpatches.patches.kegDripCadence")
local essentialAttackerFilter = require("mwpluginpatches.patches.essentialAttackerFilter")
local magicantMenuGuard = require("mwpluginpatches.patches.magicantMenuGuard")
local aheadOfTheClassesEquip = require("mwpluginpatches.patches.aheadOfTheClassesEquip")
local attendMeRays = require("mwpluginpatches.patches.attendMeRays")
local attendMeRecruitLabel = require("mwpluginpatches.patches.attendMeRecruitLabel")
local g7ContainersLinkCache = require("mwpluginpatches.patches.g7ContainersLinkCache")
local ruinesRelicsJournal = require("mwpluginpatches.patches.ruinesRelicsJournal")
local hudCompanionMirror = require("mwpluginpatches.patches.hudCompanionMirror")

-- OAAB and Garden of Dreams call include("MWCA.interop") at file scope when their
-- main.lua is loaded. That is after this file (load-priority 4500) and before
-- initialized, so the stub has to be in package.loaded now, not in onInitialized.
if config.enabled and config.mwcaInteropEnabled and config.isMwcaConsumerActive() then
    mwcaInterop.init()
end

-- Watch the Skies requires its util module, and Party Alchemy shows its module message on
-- initialized. Keg Drip registers its simulate handler at file scope, Essential Indicators its
-- damage handler and Magican't its enterFrame handler on initialized. Attend Me registers its command-wheel
-- simulate handler at file scope and its recruit one when recruiting starts; MWSE Containers Extended registers
-- its handlers at file scope. Ruins'n'Relics registers its loaded handler (the Old Journal hand-out) at file scope
-- too. All of that happens after this file loads, so the intercepts go in now and see every one.
for _, patch in ipairs({ wtsMetadataLog, partyAlchemyModuleBox, kegDripCadence, essentialAttackerFilter, magicantMenuGuard,
    attendMeRays, attendMeRecruitLabel, g7ContainersLinkCache, ruinesRelicsJournal }) do
    local ok, err = pcall(patch.init)
    if not ok then
        mwse.log("[mwpluginpatches] An intercept failed to start: %s", tostring(err))
    end
end

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
    if config.aotcEquipOnceEnabled and config.isAheadOfTheClassesInstalled() then
        local ok, err = pcall(aheadOfTheClassesEquip.init)
        if not ok then mwse.log("[mwpluginpatches] Ahead of the Classes intercept failed to start: %s", tostring(err)) end
    end
    if config.hudCompanionMirrorEnabled and config.isHudCompanionInstalled() then
        local ok, err = pcall(hudCompanionMirror.init)
        if not ok then mwse.log("[mwpluginpatches] HUD Companion Health Bar mirror failed to start: %s", tostring(err)) end
    end

    mwse.log("[mwpluginpatches] Unified plugin compatibility patches initialized.")
end

event.register(tes3.event.initialized, onInitialized)

local function registerModConfig()
    require("mwpluginpatches.mcm")
end
event.register(tes3.event.modConfigReady, registerModConfig)
