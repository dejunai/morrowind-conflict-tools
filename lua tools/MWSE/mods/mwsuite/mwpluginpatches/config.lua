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
config.isPAndSActive = config.isPsGuardActive

function config.isTalesOfSeydaNeenActive()
    return tes3.isModActive("Clean Tales of Seyda Neen.esp")
        or tes3.isModActive("Tales of Seyda Neen.esp")
        or tes3.isModActive("Tales of Seyda Neen.ESP")
        or tes3.getObject("den_message_bottle2") ~= nil
end

function config.isTrainerLogActive()
    return tes3.isModActive("Trainer Log.esp")
        or tes3.isModActive("Trainer Log - AEA.esp")
        or tes3.isModActive("Trainer Log - AEA.ESP")
        or tes3.findDialogue("Training - Block") ~= nil
end

function config.isYsmirActive()
    return tes3.isModActive("YARR - yet another race revamp v1.2.ESP")
        or tes3.isModActive("YARR.esp")
        or tes3.getObject("exo_nord_ysmirshield") ~= nil
end

-- the load order can't change while the game runs, so once the game is initialized the answer is kept
local friendsAndFrensActive
function config.isFriendsAndFrensActive()
    if friendsAndFrensActive ~= nil then return friendsAndFrensActive end
    local active = tes3.isModActive("Friends & Frens - base.esm")
        or tes3.isModActive("Friends & Frens - Vvardenfell.ESP")
        or tes3.isModActive("Friends & Frens - TR.ESP")
        or tes3.isModActive("Friends and Frens.ESP")
        or tes3.isModActive("Friends and Frens - Jiub.esp")
        or tes3.getObject("aa_comp_jiub") ~= nil
    if tes3.isInitialized and tes3.isInitialized() then friendsAndFrensActive = active end
    return active
end

function config.isUIExpansionActive()
    return (lfs and lfs.fileexists and lfs.fileexists("Data Files/MWSE/mods/UI Expansion/MenuDialog.lua")) or false
end

function config.isLostHeirActive()
    return tes3.isModActive("t_lostheir.esp")
        or tes3.isModActive("LostHeir.esp")
end

function config.isMabrDistActive()
    return tes3.isModActive("MabrDist.esp")
        or tes3.findGlobal("gv_mabrDist") ~= nil
        or tes3.getScript("mabDist") ~= nil
end

function config.isCoastGuardContrabandActive()
    return tes3.isModActive("Vvardenfell Distribution - Seyda Neen Coast Guard.ESP")
        or tes3.findDialogue("contraband") ~= nil
end

function config.isAiVoicesActive()
    return (lfs and lfs.fileexists and lfs.fileexists("Data Files/MWSE/mods/AI Voices/main.lua")) or false
end

function config.isPersonalEffectsActive()
    return tes3.isModActive("Personal Effects_MWSE.ESP")
        or tes3.isModActive("Personal Effects.ESP")
        or tes3.getObject("R0_pe_basecont") ~= nil
        or tes3.getScript("R0_pe_init_scr") ~= nil
end

function config.isBardicInspirationActive()
    return tes3.isModActive("BardicInspiration.esp") == true
end


-- Resolve dynamic defaults based on whether target plugin is active in load order
function config.isGraphicHerbalismActive()
    return (lfs and lfs.fileexists and lfs.fileexists("Data Files/MWSE/mods/graphicHerbalism/main.lua"))
        or (tes3.isModActive and (tes3.isModActive("Graphic Herbalism.esp") or tes3.isModActive("Graphic Herbalism Extra.esp")))
        or false
end

function config.isMwcaConsumerActive()
    return (lfs and lfs.fileexists and (
        lfs.fileexists("Data Files/MWSE/mods/herbert100/animated containers/main.lua")
        or lfs.fileexists("Data Files/MWSE/mods/oaab/mwca/main.lua")
        or lfs.fileexists("Data Files/MWSE/mods/x32/mwca/main.lua")
    )) or false
end

-- Intercepts for tweaks that used to be hand edits (patches/: wtsMetadataLog, partyAlchemyModuleBox, kegDripCadence, essentialAttackerFilter, magicantMenuGuard, aheadOfTheClassesEquip). These run when
-- mwpluginpatches loads, before the load order is readable, so they look for the mod's own Lua file.
function config.isWatchTheSkiesInstalled()
    return (lfs and lfs.fileexists and lfs.fileexists("Data Files/MWSE/mods/tew/Watch the Skies/util.lua")) or false
end

function config.isPartyAlchemyInstalled()
    return (lfs and lfs.fileexists and lfs.fileexists("Data Files/MWSE/mods/partyAlchemy/main.lua")) or false
end

function config.isKegDripInstalled()
    return (lfs and lfs.fileexists and lfs.fileexists("Data Files/MWSE/mods/KegDrip/main.lua")) or false
end

function config.isEssentialIndicatorsInstalled()
    return (lfs and lfs.fileexists and lfs.fileexists("Data Files/MWSE/mods/Essential Indicators/main.lua")) or false
end

function config.isMagicantInstalled()
    return (lfs and lfs.fileexists and lfs.fileexists("Data Files/MWSE/mods/tew/Magican't/main.lua")) or false
end

function config.isAheadOfTheClassesInstalled()
    return (lfs and lfs.fileexists and lfs.fileexists("Data Files/MWSE/mods/Danae/Classes/main.lua")) or false
end

-- the intercepts that took over luafix KP1, KP2 and KP4 (patches/: attendMeRays, attendMeRecruitLabel, g7ContainersLinkCache)
function config.isAttendMeInstalled()
    return (lfs and lfs.fileexists and lfs.fileexists("Data Files/MWSE/mods/AttendMeMWSE/main.lua")) or false
end

function config.isG7ContainersInstalled()
    return (lfs and lfs.fileexists and lfs.fileexists("Data Files/MWSE/mods/Spammer/G7 Containers/main.lua")) or false
end

-- Ruins'n'Relics (patches/ruinesRelicsJournal): its Old Journal goes on a table instead of arriving with a pop-up
function config.isRuinesRelicsInstalled()
    return (lfs and lfs.fileexists and lfs.fileexists("Data Files/MWSE/mods/Ruines'n'relics/main.lua")) or false
end

function config.isHudCompanionInstalled()
    return (lfs and lfs.fileexists and lfs.fileexists("Data Files/MWSE/mods/Pirate/HUD Companion Health Bar/main.lua"))
        or false
end

-- true when a mod's Lua file (path under Data Files/MWSE/mods) contains text; used to see an old luafix edit
-- ("-- local fix (KPn)") so an intercept doing the same job stands down. Read only, once per intercept at start.
function config.modFileHas(relativePath, text)
    if type(relativePath) ~= "string" or type(text) ~= "string" or not io or not io.open then return false end
    local f = io.open("Data Files/MWSE/mods/" .. relativePath, "rb")
    if not f then return false end
    local ok, data = pcall(f.read, f, "*a")
    f:close()
    return ok and type(data) == "string" and data:find(text, 1, true) ~= nil
end

local function getDynamicDefaults()
    local mca = config.isMcaActive()
    local eu = config.isEbonheartUnderworksActive()
    local ps = config.isPAndSActive()
    local ysmir = config.isYsmirActive()
    local fnf = config.isFriendsAndFrensActive()
    local lostHeir = config.isLostHeirActive()
    local mabr = config.isMabrDistActive()
    local tales = config.isTalesOfSeydaNeenActive()
    local trainerLog = config.isTrainerLogActive()
    local coastGuard = config.isCoastGuardContrabandActive()
    local bardic = config.isBardicInspirationActive()

    return {
        enabled = false,          -- the whole mod

        -- Coast Guard Contraband Bulk Turn-In & Filter
        coastGuardContrabandEnabled = coastGuard,
        coastGuardBulkTurnIn = true,
        coastGuardHideExhausted = true,
        coastGuardTurnInSkooma = true,
        coastGuardTurnInRawEbony = true,
        coastGuardTurnInRawGlass = true,
        coastGuardTurnInMoonSugar = true,
        coastGuardTurnInAshStatues = true,
        coastGuardTurnInVampireDust = false,

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

        -- Privileges & Services Fixes
        pAndSFixesEnabled = ps,
        psGuardFixEnabled = ps,

        -- Clean Tales of Seyda Neen: Illegible Handwriting filter
        talesHandwritingFixEnabled = tales,

        -- Trainer Log: Auto-Unlock Training Topics
        trainerLogUnlockEnabled = trainerLog,
        trainerLogAutoUnlockOnLoad = true,

        -- Ysmir Combat Shield (YARR)
        ysmirShieldEnabled = ysmir,

        -- Friends & Frens Jiub Companion Delay
        jiubDelayEnabled = fnf,
        jiubDelayMinutes = 5,
        jiubSyncAppearance = true,
        jiubExcludeCensusOffice = true,

        -- Friends & Frens: converted vanilla NPCs keep their generic dialogue
        friendsAndFrensLoreEnabled = fnf,

        -- UI Expansion: topic colours wait until the topic list exists
        uiExpansionTopicsEnabled = config.isUIExpansionActive(),

        -- The Lost Heir Delayer
        lostHeirDelayEnabled = lostHeir,

        -- Mabrigash Distribution Popup Suppression
        mabrDistSuppressionEnabled = mabr,

        -- Personal Effects: its Census and Excise scripts run in Lua
        personalEffectsEnabled = config.isPersonalEffectsActive(),

        -- Voices of Vvardenfell: its routine lines in the player's console
        aiVoicesConsoleEnabled = config.isAiVoicesActive(),

        -- Bardic Inspiration: items that count as instruments besides its lutes (lower-case ids)
        musicalInstrumentsEnabled = bardic,
        musicalInstruments = {
            misc_de_drum_01 = true, misc_de_drum_02 = true,
            t_imp_drum_01 = true, t_imp_drum_02 = true, t_imp_drum_03 = true, t_imp_drum_04 = true,
            t_nor_deerskindrum_01 = true, t_nor_music_drum_01 = true, t_nor_music_drum_02 = true,
            t_nor_music_drum_03 = true, t_nor_music_drum_04 = true, t_orc_drum_01 = true, t_rga_drum_01 = true,
            t_de_music_lyre_01 = true, t_de_music_panflute_01 = true, t_nor_music_flute_01 = true,
            t_nor_music_lyre_01 = true, t_nor_music_lyre_02 = true, t_nor_music_warhorn_01 = true,
            t_rga_flute_01 = true,
            ab_misc_6thflute = true, ab_misc_ashlflute = true, ab_mus_6thflute = true, ab_mus_ashlflute = true,
            ab_mus_ashllyre = true, ab_mus_deharp = true, ab_mus_delyre = true,
        },

        -- Graphic Herbalism Respawn Delay (days)
        graphicHerbalismRespawnEnabled = config.isGraphicHerbalismActive(),
        herbRespawnDays = 3,

        -- MWCA interop stub for Animated Containers Rewritten and OAAB / Garden of Dreams addons
        mwcaInteropEnabled = config.isMwcaConsumerActive(),

        -- Intercepts that replace old hand edits (patches/: wtsMetadataLog, partyAlchemyModuleBox, kegDripCadence, essentialAttackerFilter, magicantMenuGuard)
        wtsMetadataLogEnabled = config.isWatchTheSkiesInstalled(),
        partyAlchemyModuleBoxEnabled = config.isPartyAlchemyInstalled(),
        kegDripCadenceEnabled = config.isKegDripInstalled(),
        kegDripIntervalSeconds = 3,
        essentialAttackerFilterEnabled = config.isEssentialIndicatorsInstalled(),
        magicantMenuGuardEnabled = config.isMagicantInstalled(),

        -- Ahead of the Classes: its post-chargen equip pass fills each slot with at most one item
        aotcEquipOnceEnabled = config.isAheadOfTheClassesInstalled(),

        -- Attend Me and MWSE Containers Extended: the per-frame work luafix KP1, KP2 and KP4 used to cut by editing them
        attendMeRaysEnabled = config.isAttendMeInstalled(),
        attendMeRecruitLabelEnabled = config.isAttendMeInstalled(),
        g7ContainersLinkCacheEnabled = config.isG7ContainersInstalled(),

        -- Ruins'n'Relics: no "old journal" pop-up at new game; the book lies on the table in the Census and Excise Office
        ruinesRelicsJournalEnabled = config.isRuinesRelicsInstalled(),

        -- HUD Companion Health Bar: its blacklist and mwcompanions' never-followers list kept the same
        hudCompanionMirrorEnabled = config.isHudCompanionInstalled(),
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

local needsSave = loadedConfig.doorLockCompatibilityEnabled ~= nil
    or loadedConfig.doorLockedNotification ~= nil
    or loadedConfig.arrilleInnCompatibilityEnabled ~= nil
loadedConfig.arrilleInnCompatibilityEnabled = nil
loadedConfig.doorLockCompatibilityEnabled = nil
loadedConfig.doorLockedNotification = nil

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

if config.mcaPartySize == 3 then
    config.mcaPartySize = 2
    mwse.log("[mwpluginpatches] MCA party size 3 was invalid; changed it to MCA's largest option (2-20).")
    needsSave = true
end
if needsSave then
    config.save()
end

return config
