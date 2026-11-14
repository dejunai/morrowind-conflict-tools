local config = require("mwpluginpatches.config")

local template = mwse.mcm.createTemplate("Plugin Compatibility Patches")
template.onClose = function() config.save() end   -- not saveOnClose: config holds functions

local page = template:createSideBarPage({
    label = "Patches",
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
  • The Lost Heir: %s]],
    config.isMcaActive() and "Active" or "Not Active",
    config.isEbonheartUnderworksActive() and "Active" or "Not Active",
    config.isPsGuardActive() and "Active" or "Not Active",
    config.isYsmirActive() and "Active" or "Not Active",
    config.isFriendsAndFrensActive() and "Active" or "Not Active",
    config.isLostHeirActive() and "Active" or "Not Active"),
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
local psCategory = page:createCategory(string.format("Privileges & Services: Guard Cell Fix%s", getStatusText(config.isPsGuardActive())))

psCategory:createYesNoButton({
    label = "Enable Guard Cell Black Screen Fix",
    description = "Dynamically resolves non-vanilla interior cells to architectural guard factions to prevent permanent black screen fadeouts.",
    variable = mwse.mcm.createTableVariable({ id = "psGuardFixEnabled", table = config }),
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

mcaCategory:createYesNoButton({
    label = "Enable Silent AutoStartup for MCA",
    description = "Automatically initializes Morrowind Comes Alive silently without questionnaire popups.",
    variable = mwse.mcm.createTableVariable({ id = "mcaEnabled", table = config }),
})

mcaCategory:createYesNoButton({
    label = "Enable MCA Companions",
    description = "Allow recruitable companion NPCs and Ordinator Shareel to spawn.",
    variable = mwse.mcm.createTableVariable({ id = "mcaCompanions", table = config }),
})

mcaCategory:createDropdown({
    label = "Courtesan Spawns",
    description = "Choose which courtesan NPCs spawn in taverns.",
    options = {
        { label = "None", value = "none" },
        { label = "Female Only", value = "female" },
        { label = "Male Only", value = "male" },
        { label = "Both", value = "all" },
    },
    variable = mwse.mcm.createTableVariable({ id = "mcaCourtesans", table = config }),
})

mcaCategory:createYesNoButton({
    label = "Hostile Drunks in Taverns",
    description = "Allow belligerent drunks to spawn in taverns.",
    variable = mwse.mcm.createTableVariable({ id = "mcaHostileDrunks", table = config }),
})

mcaCategory:createYesNoButton({
    label = "Respawning Enemies in Caves & Ruins",
    description = "Allow hostile bandits, witches, and daedra worshippers to respawn.",
    variable = mwse.mcm.createTableVariable({ id = "mcaRespawnCaves", table = config }),
})

mcaCategory:createYesNoButton({
    label = "Bandit Attacks on Towns",
    description = "Allow random bandit raids on towns.",
    variable = mwse.mcm.createTableVariable({ id = "mcaBanditAttacksTowns", table = config }),
})

mcaCategory:createYesNoButton({
    label = "Hostile Ashlander Outcasts",
    description = "Allow hostile Ashlander outcasts and Mabrigash to spawn at outcast camps.",
    variable = mwse.mcm.createTableVariable({ id = "mcaHostileAshlanders", table = config }),
})

mcaCategory:createYesNoButton({
    label = "Highwaymen at Crossroads",
    description = "Allow highwaymen bandits to ambush travelers at crossroads.",
    variable = mwse.mcm.createTableVariable({ id = "mcaCrossroadBandits", table = config }),
})

mcaCategory:createSlider({
    label = "Hostile Party Size",
    description = "Extra enemies spawning together in hostile groups (0 = Normal, 1 = +1, 2 = +2, 3 = +3).",
    min = 0,
    max = 3,
    step = 1,
    jump = 1,
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

mwse.mcm.register(template)
