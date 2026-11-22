local config = require("mwpluginpatches.config")

local template = mwse.mcm.createTemplate("Plugin Compatibility Patches")
template.onClose = function() config.save() end   -- not saveOnClose: config holds functions

local page = template:createSideBarPage({
    label = "Patches",
})

page:createOnOffButton({
    label = "Enabled",
    description = "The whole mod. Off: no patch below is applied. Takes effect after a restart.",
    variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
})

local function getStatusText(isActive)
    return isActive and " [Detected Active]" or " [Not Installed / Inactive]"
end

page.sidebar:createInfo({
    text = string.format([[mwpluginpatches unifies targeted compatibility patches and auto-configurations for installed third-party plugins.

Each patch automatically checks whether its target plugin is active in your load order:
  • If installed & active -> Defaults to ON.
  • If NOT installed -> Defaults to DISABLED.

Active Plugin Status:
  • Morrowind Comes Alive: %s
  • Ebonheart Underworks: %s
  • Privileges & Services: %s
  • YARR (Yet Another Race Revamp): %s
  • Friends & Frens: %s
  • The Lost Heir: %s
  • Mabrigash Distribution: %s
  • Cave Drips: %s
  • Yet Another Better Sounds Patch: %s
  • Expanded Sounds: %s
  • Clean Tales of Seyda Neen: %s
  • Trainer Log: %s]],
    config.isMcaActive() and "Active" or "Not Active",
    config.isEbonheartUnderworksActive() and "Active" or "Not Active",
    config.isPAndSActive() and "Active" or "Not Active",
    config.isYsmirActive() and "Active" or "Not Active",
    config.isFriendsAndFrensActive() and "Active" or "Not Active",
    config.isLostHeirActive() and "Active" or "Not Active",
    config.isMabrDistActive() and "Active" or "Not Active",
    config.isCaveDripsActive() and "Active" or "Not Active",
    config.isSwampSoundsActive() and "Active" or "Not Active",
    config.isExpandedSoundsActive() and "Active" or "Not Active",
    config.isTalesOfSeydaNeenActive() and "Active" or "Not Active",
    config.isTrainerLogActive() and "Active" or "Not Active"),
})

-- SECTION 1: FRIENDS & FRENS (JIUB COMPANION DELAY)
local fnfCategory = page:createCategory(string.format("Friends & Frens: Jiub Delayer%s", getStatusText(config.isFriendsAndFrensActive())))

fnfCategory:createYesNoButton({
    label = "Enable Jiub Companion Delayer",
    description = "Delays Jiub's companion introduction rumor until you finish character generation and spend time exploring Vvardenfell.",
    variable = mwse.mcm.createTableVariable({ id = "jiubDelayEnabled", table = config }),
})

fnfCategory:createSlider({
    label = "Delay After Census (Minutes)",
    description = "How many minutes of active post-census gameplay must elapse before the Jiub companion rumor can appear in dialogue.",
    min = 0,
    max = 30,
    step = 1,
    jump = 5,
    variable = mwse.mcm.createTableVariable({ id = "jiubDelayMinutes", table = config }),
})

fnfCategory:createYesNoButton({
    label = "Exclude Census & Excise Office NPCs",
    description = "Prevent NPCs inside the Census & Excise Office from mentioning Jiub's companion rumors.",
    variable = mwse.mcm.createTableVariable({ id = "jiubExcludeCensusOffice", table = config }),
})

fnfCategory:createYesNoButton({
    label = "Synchronize Jiub Head & Hair with Intro",
    description = "Matches the companion Jiub's head and hair mesh with whatever custom head/hair replacer is used on the tutorial boat.",
    variable = mwse.mcm.createTableVariable({ id = "jiubSyncAppearance", table = config }),
})

-- SECTION 2: THE LOST HEIR
local lostHeirCategory = page:createCategory(string.format("The Lost Heir: Delayer%s", getStatusText(config.isLostHeirActive())))

lostHeirCategory:createYesNoButton({
    label = "Enable The Lost Heir Delayer",
    description = "Disables quest NPC spawning from t_lostheir.esp until the Morrowind main quest reaches Mehra Milo (A2_4_MiloGone >= 1).",
    variable = mwse.mcm.createTableVariable({ id = "lostHeirDelayEnabled", table = config }),
})

-- SECTION 3: PRIVILEGES & SERVICES
local psCategory = page:createCategory(string.format("Privileges & Services: Guard & Topic Fixes%s", getStatusText(config.isPAndSActive())))

psCategory:createYesNoButton({
    label = "Enable Privileges & Services Fixes",
    description = "Fixes the guard cell black screen fadeout in non-vanilla interiors and suppresses the rogue °(target) topic on ordinary NPCs.",
    variable = mwse.mcm.createTableVariable({ id = "pAndSFixesEnabled", table = config }),
})

-- SECTION 4: YARR - YSMIR COMBAT SHIELD
local ysmirCategory = page:createCategory(string.format("YARR: Ysmir Combat Shield Fix%s", getStatusText(config.isYsmirActive())))

ysmirCategory:createYesNoButton({
    label = "Enable Dynamic Combat-Only Shield",
    description = "Replaces the noisy constant blue bubble shield VFX on peaceful Nord NPCs with a combat-only shield.",
    variable = mwse.mcm.createTableVariable({ id = "ysmirShieldEnabled", table = config }),
})

-- SECTION 5: MORROWIND COMES ALIVE (MCA)
local mcaCategory = page:createCategory(string.format("Morrowind Comes Alive: AutoStartup%s", getStatusText(config.isMcaActive())))

mcaCategory:createInfo({
    text = "These questionnaire choices are applied when MCA first initializes in a save. Changing them does not "
        .. "reconfigure a save where MCA has already been initialized.",
})

mcaCategory:createYesNoButton({
    label = "Enable Silent AutoStartup for MCA",
    description = "Automatically initializes Morrowind Comes Alive silently without questionnaire popups.",
    variable = mwse.mcm.createTableVariable({ id = "mcaEnabled", table = config }),
})

mcaCategory:createYesNoButton({
    label = "Enable companions?",
    description = "Allow recruitable companion NPCs and Ordinator Shareel to spawn.",
    variable = mwse.mcm.createTableVariable({ id = "mcaCompanions", table = config }),
})

mcaCategory:createDropdown({
    label = "Enable courtesans?",
    description = "Choose which courtesan NPCs spawn in taverns.",
    options = {
        { label = "Enable", value = "all" },
        { label = "Disable", value = "none" },
        { label = "Disable male only", value = "female" },
        { label = "Disable female only", value = "male" },
    },
    variable = mwse.mcm.createTableVariable({ id = "mcaCourtesans", table = config }),
})

mcaCategory:createYesNoButton({
    label = "Enable hostile drunks in taverns?",
    description = "Allow belligerent drunks to spawn in taverns.",
    variable = mwse.mcm.createTableVariable({ id = "mcaHostileDrunks", table = config }),
})

mcaCategory:createYesNoButton({
    label = "Enable respawning hostile NPCs in caves and ruins?",
    description = "Allow hostile bandits, witches, and daedra worshippers to respawn.",
    variable = mwse.mcm.createTableVariable({ id = "mcaRespawnCaves", table = config }),
})

mcaCategory:createYesNoButton({
    label = "Enable bandit attacks in towns?",
    description = "Allow random bandit raids on towns.",
    variable = mwse.mcm.createTableVariable({ id = "mcaBanditAttacksTowns", table = config }),
})

mcaCategory:createYesNoButton({
    label = "Enable hostile Ashlanders at outcast Ashlander campsites?",
    description = "Allow hostile Ashlander outcasts and Mabrigash to spawn at outcast camps.",
    variable = mwse.mcm.createTableVariable({ id = "mcaHostileAshlanders", table = config }),
})

mcaCategory:createYesNoButton({
    label = "Enable Brigands and Highwaymen at crossroads?",
    description = "Allow highwaymen bandits to ambush travelers at crossroads.",
    variable = mwse.mcm.createTableVariable({ id = "mcaCrossroadBandits", table = config }),
})

mcaCategory:createDropdown({
    label = "Preferred size of hostile NPC parties",
    description = "Select MCA's hostile party size range. This affects bandits and other hostile NPC parties, "
        .. "including outcasts, deserters and smugglers. Larger groups make encounters more dangerous.",
    options = {
        { label = "2-5", value = 0 },
        { label = "2-10", value = 1 },
        { label = "2-20", value = 2 },
    },
    variable = mwse.mcm.createTableVariable({ id = "mcaPartySize", table = config }),
})

-- SECTION 6: EBONHEART UNDERWORKS
local euCategory = page:createCategory(string.format("Ebonheart Underworks: AutoStartup%s", getStatusText(config.isEbonheartUnderworksActive())))

euCategory:createYesNoButton({
    label = "Enable Silent AutoStartup for Ebonheart Underworks",
    description = "Automatically applies configuration without dialogue prompts upon entering Ebonheart.",
    variable = mwse.mcm.createTableVariable({ id = "euEnabled", table = config }),
})

euCategory:createYesNoButton({
    label = "Morrowind Rebirth Mode",
    description = "Enable this if you have Morrowind Rebirth installed.",
    variable = mwse.mcm.createTableVariable({ id = "euRebirth", table = config }),
})

euCategory:createYesNoButton({
    label = "Thief Branch Content",
    description = "Enable the additional Thief questline content in the Underworks.",
    variable = mwse.mcm.createTableVariable({ id = "euThiefBranch", table = config }),
})

-- SECTION 7: MABRIGASH DISTRIBUTION
local mabrCategory = page:createCategory(string.format("Mabrigash Distribution: Popup Suppression%s", getStatusText(config.isMabrDistActive())))

mabrCategory:createYesNoButton({
    label = "Suppress 'Distributing Mabrigash' Popup",
    description = "Silently suppresses the background distribution notification box on game startup and cell load.",
    variable = mwse.mcm.createTableVariable({ id = "mabrDistSuppressionEnabled", table = config }),
})

-- SECTION 10: LOOPING SOUND SCRIPTS
local dripCategory = page:createCategory(string.format("Cave Drips: Drip Sound%s",
    getStatusText(config.isCaveDripsActive())))

dripCategory:createYesNoButton({
    label = "Start Each Drip Loop Once",
    description = "Runs Cave Drips' R0_Sound_Cave_Drip_scr in Lua. The engine can report the drip loop as not playing "
        .. "while it plays, so the original script restarts it every frame (mwsoundguard RUNAWAY entries). With this "
        .. "on, each drip starts its loop once while it is loaded; the drip visuals are placed as before. "
        .. "Takes effect after a restart.",
    variable = mwse.mcm.createTableVariable({ id = "caveDripSoundEnabled", table = config }),
})

local swampCategory = page:createCategory(string.format("Yet Another Better Sounds Patch: Swamp Sounds%s",
    getStatusText(config.isSwampSoundsActive())))

swampCategory:createYesNoButton({
    label = "One Swamp Loop Per Sound Source",
    description = "Runs SwampSoundScript in Lua with the same day, night and weather choices. The original starts "
        .. "a new random swamp loop every frame because the engine reports the playing one as stopped. With this "
        .. "on, each swamp sound source keeps one loop until day turns to night (or back) or the weather turns bad. "
        .. "Takes effect after a restart.",
    variable = mwse.mcm.createTableVariable({ id = "swampSoundEnabled", table = config }),
})

local expandedCategory = page:createCategory(string.format("Expanded Sounds: Water and Boat Loops%s",
    getStatusText(config.isExpandedSoundsActive())))

expandedCategory:createYesNoButton({
    label = "Start Expanded Sounds Loops Once",
    description = "Runs Float and Sound_Boat_Creak in Lua, preserving Float's boat rocking while starting its water "
        .. "loop and each boat-creak loop only once per loaded source. Takes effect after a restart.",
    variable = mwse.mcm.createTableVariable({ id = "expandedSoundsEnabled", table = config }),
})

-- SECTION 11: CLEAN TALES OF SEYDA NEEN
local talesCategory = page:createCategory(string.format("Clean Tales of Seyda Neen: Dialogue Fix%s",
    getStatusText(config.isTalesOfSeydaNeenActive())))

talesCategory:createYesNoButton({
    label = "Filter 'Illegible Handwriting' Topic",
    description = "Hides the 'illegible handwriting' topic from NPCs once the quest 'den_bottle' is completed (journal >= 50) or if the player does not have the note.",
    variable = mwse.mcm.createTableVariable({ id = "talesHandwritingFixEnabled", table = config }),
})

-- SECTION 12: TRAINER LOG
local trainerCategory = page:createCategory(string.format("Trainer Log: Auto-Unlock Topics%s",
    getStatusText(config.isTrainerLogActive())))

trainerCategory:createYesNoButton({
    label = "Enable Training Topic Auto-Unlock",
    description = "Automatically unlocks all 27 'Training - <Skill>' topics when speaking to any training service provider or on save load, bypassing the Caius Cosades / Socucius Ergalla dialogue prerequisites.",
    variable = mwse.mcm.createTableVariable({ id = "trainerLogUnlockEnabled", table = config }),
})

trainerCategory:createYesNoButton({
    label = "Unlock Immediately on Load",
    description = "Adds the training topics immediately when loading a saved game rather than waiting until talking to a trainer NPC.",
    variable = mwse.mcm.createTableVariable({ id = "trainerLogAutoUnlockOnLoad", table = config }),
})

-- SECTION 13: DOOR LOCK COMPATIBILITY
local doorCategory = page:createCategory(string.format("Door Locks: Compatibility%s",
    getStatusText(config.isDoorLockSuiteInstalled())))

doorCategory:createYesNoButton({
    label = "Coordinate Door Locking and Lockpicking",
    description = "Locks an NPC-owned interior door when its owner is absent. Standing at a locked door plays "
        .. "the locked-door sound; sneak to pass it to Modern Lockpicking. Owned unlocked doors also require sneaking.",
    variable = mwse.mcm.createTableVariable({ id = "doorLockCompatibilityEnabled", table = config }),
})

doorCategory:createYesNoButton({
    label = "Show 'The Door is Locked' Notification",
    description = "Also shows a visual notification when a locked door is tried while standing.",
    variable = mwse.mcm.createTableVariable({ id = "doorLockedNotification", table = config }),
})

-- SECTION 14: SEYDA NEEN COAST GUARD: CONTRABAND
local cgCategory = page:createCategory(string.format("Seyda Neen Coast Guard: Contraband%s",
    getStatusText(config.isCoastGuardContrabandActive())))

cgCategory:createYesNoButton({
    label = "Enable Bulk Contraband Turn-In",
    description = "Turns in all units of the current contraband type in a single press rather than 1 at a time, "
        .. "awarding the full 10% market value finder's fee at once.",
    variable = mwse.mcm.createTableVariable({ id = "coastGuardBulkTurnIn", table = config }),
})

cgCategory:createYesNoButton({
    label = "Hide Topic When All Contraband Surrendered",
    description = "Removes the 'contraband' topic from dialogue once all eligible and enabled contraband has been surrendered.",
    variable = mwse.mcm.createTableVariable({ id = "coastGuardHideExhausted", table = config }),
})

cgCategory:createYesNoButton({
    label = "Turn In: Skooma (50 gold/bottle)",
    description = "When enabled, skooma is surrendered for bounty. When disabled, skooma is kept in your inventory and the guard checks the next contraband type.",
    variable = mwse.mcm.createTableVariable({ id = "coastGuardTurnInSkooma", table = config }),
})

cgCategory:createYesNoButton({
    label = "Turn In: Raw Ebony (20 gold/chunk)",
    description = "When enabled, raw ebony is surrendered for bounty. When disabled, raw ebony is kept in your inventory.",
    variable = mwse.mcm.createTableVariable({ id = "coastGuardTurnInRawEbony", table = config }),
})

cgCategory:createYesNoButton({
    label = "Turn In: Raw Glass (20 gold/piece)",
    description = "When enabled, raw glass is surrendered for bounty. When disabled, raw glass is kept in your inventory.",
    variable = mwse.mcm.createTableVariable({ id = "coastGuardTurnInRawGlass", table = config }),
})

cgCategory:createYesNoButton({
    label = "Turn In: Moon Sugar (5 gold/portion)",
    description = "When enabled, moon sugar is surrendered for bounty. When disabled, moon sugar is kept in your inventory.",
    variable = mwse.mcm.createTableVariable({ id = "coastGuardTurnInMoonSugar", table = config }),
})

cgCategory:createYesNoButton({
    label = "Turn In: 6th House Ash Statues (25 gold/statue)",
    description = "When enabled, 6th House ash statues are surrendered for bounty. When disabled, ash statues are kept in your inventory.",
    variable = mwse.mcm.createTableVariable({ id = "coastGuardTurnInAshStatues", table = config }),
})

cgCategory:createYesNoButton({
    label = "Turn In: Vampire Dust (50 gold/portion) [Lore Addition]",
    description = "Optional lore-friendly extension: allow surrendering forbidden vampire dust to the Census and Excise for a 10% finder's fee (50 gold per portion).",
    variable = mwse.mcm.createTableVariable({ id = "coastGuardTurnInVampireDust", table = config }),
})


template:register()
