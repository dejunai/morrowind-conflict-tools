local config = require("mwpluginpatches.config")

local autoStartup = require("mwpluginpatches.patches.autoStartup")
local pandsfixes = require("mwpluginpatches.patches.pandsfixes")
local ysmirShield = require("mwpluginpatches.patches.ysmirShield")
local jiubDelay = require("mwpluginpatches.patches.jiubDelay")
local lostHeirDelay = require("mwpluginpatches.patches.lostHeirDelay")
local mabrDist = require("mwpluginpatches.patches.mabrDist")
local noAccidentalTheftBookFix = require("mwpluginpatches.patches.noAccidentalTheftBookFix")
local caveDripSound = require("mwpluginpatches.patches.caveDripSound")
local swampSound = require("mwpluginpatches.patches.swampSound")
local expandedSounds = require("mwpluginpatches.patches.expandedSounds")
local talesHandwritingFix = require("mwpluginpatches.patches.talesHandwritingFix")
local trainerLogUnlock = require("mwpluginpatches.patches.trainerLogUnlock")
local doorLockCompatibility = require("mwpluginpatches.patches.doorLockCompatibility")
local coastGuardContraband = require("mwpluginpatches.patches.coastGuardContraband")
local graphicHerbalismRespawn = require("mwpluginpatches.patches.graphicHerbalismRespawn")

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

    -- 5. The Lost Heir Delayer
    if config.lostHeirDelayEnabled and config.isLostHeirActive() then
        lostHeirDelay.init()
    end

    -- 6. Mabrigash Distribution Popup Suppression
    if config.mabrDistSuppressionEnabled and config.isMabrDistActive() then
        mabrDist.init()
    end

    -- 7. No Accidental Theft - Book Reading Fix
    if config.noAccidentalTheftBookFixEnabled and config.isNoAccidentalTheftActive() then
        noAccidentalTheftBookFix.init()
    end

    -- 8. Cave Drips: one drip loop per activator instead of a restart every frame
    if config.caveDripSoundEnabled and config.isCaveDripsActive() then
        caveDripSound.init()
    end

    -- 9. Yet Another Better Sounds Patch: one swamp loop per activator instead of a restart every frame
    if config.swampSoundEnabled and config.isSwampSoundsActive() then
        swampSound.init()
    end

    -- Expanded Sounds: keep the Float rocking and boat creak, but start each loop once
    if config.expandedSoundsEnabled and config.isExpandedSoundsActive() then
        expandedSounds.init()
    end

    -- 10. Clean Tales of Seyda Neen: Illegible Handwriting Dialogue Filter
    if config.talesHandwritingFixEnabled and config.isTalesOfSeydaNeenActive() then
        talesHandwritingFix.init()
    end

    -- 11. Trainer Log: Auto-Unlock Training Topics
    if config.trainerLogUnlockEnabled and config.isTrainerLogActive() then
        trainerLogUnlock.init()
    end

    -- 12. abot Door Locks + Accidental Theft Prevention + Modern Lockpicking ordering
    if config.doorLockCompatibilityEnabled then
        doorLockCompatibility.init()
    end
    if config.coastGuardContrabandEnabled then
        coastGuardContraband.init()
    end
    if config.graphicHerbalismRespawnEnabled and config.isGraphicHerbalismActive() then
        graphicHerbalismRespawn.init()
    end

    mwse.log("[mwpluginpatches] Unified plugin compatibility patches initialized.")
end

event.register(tes3.event.initialized, onInitialized)

local function registerModConfig()
    require("mwpluginpatches.mcm")
end
event.register(tes3.event.modConfigReady, registerModConfig)
