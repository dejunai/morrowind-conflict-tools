local config = require("mwpluginpatches.config")

local template = mwse.mcm.createTemplate("Plugin Compatibility Patches")
template.onClose = function() config.save() end   -- not saveOnClose: config holds functions

local page = template:createSideBarPage({
    label = "Patches",
})

page:createOnOffButton({
    label = "Enabled",
    description = "Master switch for every patch on this page. Off: no patch is applied. Restart the game after changing this or turning any patch on or off.",
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
  • Clean Tales of Seyda Neen: %s
  • Trainer Log: %s
  • Personal Effects: %s
  • Animated Containers addons: %s
  • Watch the Skies: %s
  • Party Alchemy: %s
  • Keg Drip: %s
  • Essential Indicators: %s
  • Magican't: %s
  • Ahead of the Classes: %s
  • Attend Me (MWSE): %s
  • MWSE Containers Extended: %s]],
    config.isMcaActive() and "Active" or "Not Active",
    config.isEbonheartUnderworksActive() and "Active" or "Not Active",
    config.isPAndSActive() and "Active" or "Not Active",
    config.isYsmirActive() and "Active" or "Not Active",
    config.isFriendsAndFrensActive() and "Active" or "Not Active",
    config.isLostHeirActive() and "Active" or "Not Active",
    config.isMabrDistActive() and "Active" or "Not Active",
    config.isTalesOfSeydaNeenActive() and "Active" or "Not Active",
    config.isTrainerLogActive() and "Active" or "Not Active",
    config.isPersonalEffectsActive() and "Active" or "Not Active",
    config.isMwcaConsumerActive() and "Active" or "Not Active",
    config.isWatchTheSkiesInstalled() and "Active" or "Not Active",
    config.isPartyAlchemyInstalled() and "Active" or "Not Active",
    config.isKegDripInstalled() and "Active" or "Not Active",
    config.isEssentialIndicatorsInstalled() and "Active" or "Not Active",
    config.isMagicantInstalled() and "Active" or "Not Active",
    config.isAheadOfTheClassesInstalled() and "Active" or "Not Active",
    config.isAttendMeInstalled() and "Active" or "Not Active",
    config.isG7ContainersInstalled() and "Active" or "Not Active"),
})

-- SECTION 1: FRIENDS & FRENS (JIUB COMPANION DELAY)
local fnfCategory = page:createCategory(string.format("Friends & Frens: Jiub Delayer%s", getStatusText(config.isFriendsAndFrensActive())))

fnfCategory:createYesNoButton({
    label = "Enable Jiub Companion Delayer",
    description = "With Friends & Frens, people don't start talking about Jiub as a possible companion until you have finished making your character and spent some time exploring. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "jiubDelayEnabled", table = config }),
})

fnfCategory:createSlider({
    label = "Delay After Census (Minutes)",
    description = "How many minutes of play after leaving the Census and Excise Office before the Jiub rumor can come up.",
    min = 0,
    max = 30,
    step = 1,
    jump = 5,
    variable = mwse.mcm.createTableVariable({ id = "jiubDelayMinutes", table = config }),
})

fnfCategory:createYesNoButton({
    label = "Exclude Census & Excise Office NPCs",
    description = "People inside the Census and Excise Office never bring up the Jiub rumor.",
    variable = mwse.mcm.createTableVariable({ id = "jiubExcludeCensusOffice", table = config }),
})

fnfCategory:createYesNoButton({
    label = "Synchronize Jiub Head & Hair with Intro",
    description = "Companion Jiub gets the same head and hair as the Jiub on the prison ship, so he matches any head or hair replacer you use.",
    variable = mwse.mcm.createTableVariable({ id = "jiubSyncAppearance", table = config }),
})

local fnfLoreCategory = page:createCategory(string.format("Friends & Frens: Dialogue%s",
    getStatusText(config.isFriendsAndFrensActive())))

fnfLoreCategory:createYesNoButton({
    label = "Restore Generic Dialogue for Converted NPCs",
    description = "Friends & Frens stops the original NPCs it turns into companions (Fargoth, for one) from answering "
        .. "everyday topics. This gives those topics back. Its own new companions, and NPCs who never had those topics, "
        .. "are left alone. Restored topics stay in your save. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "friendsAndFrensLoreEnabled", table = config }),
})

-- SECTION 2: THE LOST HEIR
local lostHeirCategory = page:createCategory(string.format("The Lost Heir: Delayer%s", getStatusText(config.isLostHeirActive())))

lostHeirCategory:createYesNoButton({
    label = "Enable The Lost Heir Delayer",
    description = "Keeps The Lost Heir's people and creatures out of the world until the main quest reaches Mehra Milo's disappearance, so its story doesn't start too early. Its buildings and containers stay put. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "lostHeirDelayEnabled", table = config }),
})

-- SECTION 3: PRIVILEGES & SERVICES
local psCategory = page:createCategory(string.format("Privileges & Services: Guard & Topic Fixes%s", getStatusText(config.isPAndSActive())))

psCategory:createYesNoButton({
    label = "Enable Privileges & Services Fixes",
    description = "Fixes the screen getting stuck black when Privileges & Services' guards act inside interiors added by other mods, and hides the stray '°(target)' topic on ordinary NPCs. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "pAndSFixesEnabled", table = config }),
})

-- SECTION 4: YARR - YSMIR COMBAT SHIELD
local ysmirCategory = page:createCategory(string.format("YARR: Ysmir Combat Shield Fix%s", getStatusText(config.isYsmirActive())))

ysmirCategory:createYesNoButton({
    label = "Enable Dynamic Combat-Only Shield",
    description = "Nord NPCs no longer glow with a blue shield bubble all the time. They get a shield only while fighting, and it goes away afterwards. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "ysmirShieldEnabled", table = config }),
})

-- SECTION 5: MORROWIND COMES ALIVE (MCA)
local mcaCategory = page:createCategory(string.format("Morrowind Comes Alive: AutoStartup%s", getStatusText(config.isMcaActive())))

mcaCategory:createInfo({
    text = "These answers are used, instead of MCA's questions, the first time MCA starts in a save. Changing them "
        .. "later doesn't change a save where MCA has already started.",
})

mcaCategory:createYesNoButton({
    label = "Enable Silent AutoStartup for MCA",
    description = "Starts Morrowind Comes Alive quietly with the answers below, instead of asking its questions in pop-ups. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "mcaEnabled", table = config }),
})

mcaCategory:createYesNoButton({
    label = "Enable companions?",
    description = "Lets MCA's recruitable companions (and Ordinator Shareel) appear.",
    variable = mwse.mcm.createTableVariable({ id = "mcaCompanions", table = config }),
})

mcaCategory:createDropdown({
    label = "Enable courtesans?",
    description = "Which of MCA's courtesans appear in taverns.",
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
    description = "Lets rowdy drunks who may start fights appear in taverns.",
    variable = mwse.mcm.createTableVariable({ id = "mcaHostileDrunks", table = config }),
})

mcaCategory:createYesNoButton({
    label = "Enable respawning hostile NPCs in caves and ruins?",
    description = "Lets hostile bandits, witches and Daedra worshippers come back to caves and ruins after you clear them.",
    variable = mwse.mcm.createTableVariable({ id = "mcaRespawnCaves", table = config }),
})

mcaCategory:createYesNoButton({
    label = "Enable bandit attacks in towns?",
    description = "Lets bandits raid towns now and then.",
    variable = mwse.mcm.createTableVariable({ id = "mcaBanditAttacksTowns", table = config }),
})

mcaCategory:createYesNoButton({
    label = "Enable hostile Ashlanders at outcast Ashlander campsites?",
    description = "Lets hostile outcast Ashlanders and Mabrigash appear at outcast camps.",
    variable = mwse.mcm.createTableVariable({ id = "mcaHostileAshlanders", table = config }),
})

mcaCategory:createYesNoButton({
    label = "Enable Brigands and Highwaymen at crossroads?",
    description = "Lets highwaymen ambush travelers at crossroads.",
    variable = mwse.mcm.createTableVariable({ id = "mcaCrossroadBandits", table = config }),
})

mcaCategory:createDropdown({
    label = "Preferred size of hostile NPC parties",
    description = "How big MCA's hostile groups (bandits, outcasts, deserters, smugglers) can get. Bigger groups mean "
        .. "harder fights.",
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
    description = "Sets up Ebonheart Underworks quietly with the choices below, instead of asking you in pop-ups. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "euEnabled", table = config }),
})

euCategory:createYesNoButton({
    label = "Morrowind Rebirth Mode",
    description = "Turn on if you use Morrowind Rebirth, so Ebonheart Underworks is set up to match it.",
    variable = mwse.mcm.createTableVariable({ id = "euRebirth", table = config }),
})

euCategory:createYesNoButton({
    label = "Thief Branch Content",
    description = "Adds the extra thief questline in the Underworks.",
    variable = mwse.mcm.createTableVariable({ id = "euThiefBranch", table = config }),
})

-- SECTION 7: MABRIGASH DISTRIBUTION
local mabrCategory = page:createCategory(string.format("Mabrigash Distribution: Popup Suppression%s", getStatusText(config.isMabrDistActive())))

mabrCategory:createYesNoButton({
    label = "Suppress 'Distributing Mabrigash' Popup",
    description = "Hides the 'Distributing Mabrigash' message box that pops up when the game starts or you enter an area. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "mabrDistSuppressionEnabled", table = config }),
})

-- SECTION 11: CLEAN TALES OF SEYDA NEEN
local talesCategory = page:createCategory(string.format("Clean Tales of Seyda Neen: Dialogue Fix%s",
    getStatusText(config.isTalesOfSeydaNeenActive())))

talesCategory:createYesNoButton({
    label = "Filter 'Illegible Handwriting' Topic",
    description = "Once you have finished the message-in-a-bottle quest, people stop offering the 'illegible handwriting' topic. If you started the quest while the topic was hidden, you get the topic back. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "talesHandwritingFixEnabled", table = config }),
})

-- SECTION 12: TRAINER LOG
local trainerCategory = page:createCategory(string.format("Trainer Log: Auto-Unlock Topics%s",
    getStatusText(config.isTrainerLogActive())))

trainerCategory:createYesNoButton({
    label = "Enable Training Topic Auto-Unlock",
    description = "Gives you all 27 'Training - <skill>' topics the first time you talk to any trainer, without needing to talk to Caius Cosades or Socucius Ergalla first. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "trainerLogUnlockEnabled", table = config }),
})

trainerCategory:createYesNoButton({
    label = "Unlock Immediately on Load",
    description = "Gives the training topics as soon as you load a save, instead of waiting until you talk to a trainer.",
    variable = mwse.mcm.createTableVariable({ id = "trainerLogAutoUnlockOnLoad", table = config }),
})

-- SECTION 13: GRAPHIC HERBALISM
local graphicHerbalismCategory = page:createCategory(string.format("Graphic Herbalism: Respawn Delay%s",
    getStatusText(config.isGraphicHerbalismActive())))

graphicHerbalismCategory:createYesNoButton({
    label = "Enable Harvested Flora Respawn Delay",
    description = "With Graphic Herbalism, plants you have picked stay picked for the number of days set below, instead "
        .. "of growing back the next day. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "graphicHerbalismRespawnEnabled", table = config }),
})

graphicHerbalismCategory:createSlider({
    label = "Harvested Flora Respawn Delay (Days)",
    description = "How many in-game days a picked plant stays picked before it grows back. Default: 3 days.",
    min = 1,
    max = 90,
    step = 1,
    jump = 5,
    variable = mwse.mcm.createTableVariable({ id = "herbRespawnDays", table = config }),
})

-- SECTION 14: SEYDA NEEN COAST GUARD: CONTRABAND
local cgCategory = page:createCategory(string.format("Seyda Neen Coast Guard: Contraband%s",
    getStatusText(config.isCoastGuardContrabandActive())))

cgCategory:createYesNoButton({
    label = "Enable Coast Guard Contraband Changes",
    description = "Turns on the changes below for the Seyda Neen Coast Guard 'contraband' topic. Off: the topic works as the plugin made it. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "coastGuardContrabandEnabled", table = config }),
})

cgCategory:createYesNoButton({
    label = "Enable Bulk Contraband Turn-In",
    description = "Hands in all your contraband of one kind at once, instead of one at a time, for the full reward "
        .. "(10% of its value per item).",
    variable = mwse.mcm.createTableVariable({ id = "coastGuardBulkTurnIn", table = config }),
})

cgCategory:createYesNoButton({
    label = "Hide Topic When All Contraband Surrendered",
    description = "Removes the 'contraband' topic once you have nothing left to hand in.",
    variable = mwse.mcm.createTableVariable({ id = "coastGuardHideExhausted", table = config }),
})

cgCategory:createYesNoButton({
    label = "Turn In: Skooma (50 gold/bottle)",
    description = "Hand in skooma for 50 gold a bottle. Off: you keep it, and the guard asks about the next kind.",
    variable = mwse.mcm.createTableVariable({ id = "coastGuardTurnInSkooma", table = config }),
})

cgCategory:createYesNoButton({
    label = "Turn In: Raw Ebony (20 gold/chunk)",
    description = "Hand in raw ebony for 20 gold a chunk. Off: you keep it.",
    variable = mwse.mcm.createTableVariable({ id = "coastGuardTurnInRawEbony", table = config }),
})

cgCategory:createYesNoButton({
    label = "Turn In: Raw Glass (20 gold/piece)",
    description = "Hand in raw glass for 20 gold a piece. Off: you keep it.",
    variable = mwse.mcm.createTableVariable({ id = "coastGuardTurnInRawGlass", table = config }),
})

cgCategory:createYesNoButton({
    label = "Turn In: Moon Sugar (5 gold/portion)",
    description = "Hand in moon sugar for 5 gold a portion. Off: you keep it.",
    variable = mwse.mcm.createTableVariable({ id = "coastGuardTurnInMoonSugar", table = config }),
})

cgCategory:createYesNoButton({
    label = "Turn In: 6th House Ash Statues (25 gold/statue)",
    description = "Hand in Sixth House ash statues for 25 gold each. Off: you keep them.",
    variable = mwse.mcm.createTableVariable({ id = "coastGuardTurnInAshStatues", table = config }),
})

cgCategory:createYesNoButton({
    label = "Turn In: Vampire Dust (50 gold/portion) [Lore Addition]",
    description = "Extra, lore-friendly: you can also hand in vampire dust, for 50 gold a portion.",
    variable = mwse.mcm.createTableVariable({ id = "coastGuardTurnInVampireDust", table = config }),
})


local topicsCategory = page:createCategory(string.format("UI Expansion: Dialogue Topic Colours%s",
    getStatusText(config.isUIExpansionActive())))

topicsCategory:createYesNoButton({
    label = "Wait for the Topic List Before Colouring",
    description = "UI Expansion colours dialogue topics only once, when the window first opens. If another mod builds "
        .. "the window early (Immersive Travel, with travel NPCs), every topic stays amber. This makes the colouring "
        .. "wait until the topic list is ready. Neither mod is edited. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "uiExpansionTopicsEnabled", table = config }),
})

local personalEffectsCategory = page:createCategory(string.format("Personal Effects: Census and Excise%s",
    getStatusText(config.isPersonalEffectsActive())))

personalEffectsCategory:createYesNoButton({
    label = "Run Its Census Scripts in Lua",
    description = "Runs Personal Effects' Census and Excise Office scripts in Lua instead (its plugin is still needed): "
        .. "your class's starting chest is unlocked and filled once, Sellus Gravius and the door guard keep facing the "
        .. "right way, and duplicate chests or copies of your character are cleaned up. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "personalEffectsEnabled", table = config }),
})

local mwcaCategory = page:createCategory(string.format("Animated Containers: MWCA Interop%s",
    getStatusText(config.isMwcaConsumerActive())))

mwcaCategory:createYesNoButton({
    label = "Enable MWCA Interop Stub",
    description = "Puts an empty MWCA.interop table on the MWSE load path so Animated Containers Rewritten can import "
        .. "mesh replacements from the OAAB and Garden of Dreams container addons. Those addons write into that table "
        .. "when they load; without it they do nothing. Official MWCA's own animator is not used, and a real "
        .. "MWCA/interop.lua already in Data Files is left alone. Off unless one of those mods is installed. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "mwcaInteropEnabled", table = config }),
})

local wtsCategory = page:createCategory(string.format("Watch the Skies: Missing Metadata%s",
    getStatusText(config.isWatchTheSkiesInstalled())))

wtsCategory:createYesNoButton({
    label = "Log Missing-Metadata Error Instead of Stopping",
    description = "If Watch the Skies can't find its Watch the Skies-metadata.toml, it shows a message and then "
        .. "throws a Lua error that stops it starting. With this on, you still see the message, but the error is "
        .. "written to MWSE.log and the rest of the mod keeps going. Its files are not edited. Off unless Watch the "
        .. "Skies is installed. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "wtsMetadataLogEnabled", table = config }),
})

local partyAlchemyCategory = page:createCategory(string.format("Party Alchemy: Module Message%s",
    getStatusText(config.isPartyAlchemyInstalled())))

partyAlchemyCategory:createYesNoButton({
    label = "Hide 'Switched to module' Message",
    description = "Party Alchemy shows a 'Switched to module: [...]' debug message at the main menu every time the "
        .. "game starts. This hides only that message, and only when it comes from Party Alchemy; its other messages "
        .. "and its log line are kept. Its files are not edited. Off unless Party Alchemy is installed. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "partyAlchemyModuleBoxEnabled", table = config }),
})

local kegDripCategory = page:createCategory(string.format("Keg Drip: Refresh Cadence%s",
    getStatusText(config.isKegDripInstalled())))

kegDripCategory:createYesNoButton({
    label = "Refresh Drips and Puddles Less Often",
    description = "Keg Drip checks every active cell for drips and puddles once a second. With this on, it checks "
        .. "once per the interval below instead, and puddles grow by the time that passed, so they look the same "
        .. "over time. Its files are not edited. Off unless Keg Drip is installed. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "kegDripCadenceEnabled", table = config }),
})

kegDripCategory:createSlider({
    label = "Refresh Interval (Seconds)",
    description = "How often Keg Drip refreshes while the setting above is on. Default 3.",
    min = 1,
    max = 10,
    step = 1,
    jump = 2,
    variable = mwse.mcm.createTableVariable({ id = "kegDripIntervalSeconds", table = config }),
})

local essentialCategory = page:createCategory(string.format("Essential Indicators: Prophecy Warning%s",
    getStatusText(config.isEssentialIndicatorsInstalled())))

essentialCategory:createYesNoButton({
    label = "Warn Only for Your Own Hits",
    description = "Essential Indicators shows its 'thread of prophecy' warning whenever an essential character is "
        .. "hurt, even by guards or creatures. With this on, it shows only when the hit came from you, a creature you "
        .. "summoned, or your arrow, bolt, thrown weapon or spell. Essential characters are still protected as before. "
        .. "Its files are not edited. Off unless Essential Indicators is installed. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "essentialAttackerFilterEnabled", table = config }),
})

local magicantCategory = page:createCategory(string.format("Magican't: Menu Pause%s",
    getStatusText(config.isMagicantInstalled())))

magicantCategory:createYesNoButton({
    label = "Skip Fill-Bar Check While a Menu Is Open",
    description = "Magican't checks every frame whether you can afford your selected spell and greys the HUD "
        .. "magic bar if not. With this on, it doesn't check while a menu is open, so if you pick a new spell in "
        .. "the magic menu the bar updates when the menu closes. Its files are not edited. Off unless Magican't is "
        .. "installed. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "magicantMenuGuardEnabled", table = config }),
})

local aotcCategory = page:createCategory(string.format("Ahead of the Classes: Starting Gear%s",
    getStatusText(config.isAheadOfTheClassesInstalled())))

aotcCategory:createYesNoButton({
    label = "Equip One Item Per Slot",
    description = "When a new game leaves character creation, Ahead of the Classes adds your class gear and then tries to "
        .. "equip every armor, weapon and clothing item it finds, over and over as the inventory changes, so items for the "
        .. "same slot swap in and out. With this on, each slot gets at most one item: a slot that is already filled is left "
        .. "alone. Adding the gear is unchanged, you can equip anything yourself afterwards, and its files are not edited. "
        .. "Off unless Ahead of the Classes is installed. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "aotcEquipOnceEnabled", table = config }),
})

local attendMeCategory = page:createCategory(string.format("Attend Me: Fewer Eye Rays%s",
    getStatusText(config.isAttendMeInstalled())))

attendMeCategory:createYesNoButton({
    label = "Command Wheel: One Eye Ray Per Frame",
    description = "While Attend Me's command wheel is open, its labels and target display cast the same long eye ray "
        .. "up to four times in one frame. With this on, a repeat of the same ray in that frame reuses the first "
        .. "answer, so what the wheel shows is unchanged. Stands down by itself if Attend Me's actions.lua still has "
        .. "the old luafix KP1 edit. Its files are not edited. Off unless Attend Me is installed. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "attendMeRaysEnabled", table = config }),
})

attendMeCategory:createYesNoButton({
    label = "Recruit Mode: Aim Label Every 3rd Frame",
    description = "In recruitment mode Attend Me casts an eye ray every frame just to name the NPC under the "
        .. "crosshair. With this on, that label refreshes every 3rd frame, like the command wheel's target display. "
        .. "Clicking still checks who you aim at, so who is recruited or dismissed is unchanged. Stands down by itself "
        .. "if recruit.lua still has the old luafix KP2 edit. Its files are not edited. Off unless Attend Me is "
        .. "installed. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "attendMeRecruitLabelEnabled", table = config }),
})

local g7Category = page:createCategory(string.format("MWSE Containers Extended: Linked Containers%s",
    getStatusText(config.isG7ContainersInstalled())))

g7Category:createYesNoButton({
    label = "Find Each Linked Container Once",
    description = "MWSE Containers Extended searches every cell for an item's linked container on each inventory "
        .. "tile, tooltip and equip. With this on, the container is found once and kept, and looked up again only "
        .. "if it is gone or was deleted (and after loading a save). Stands down by itself if its main.lua still has "
        .. "the old luafix KP4 edit. Its files are not edited. Off unless the mod is installed. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "g7ContainersLinkCacheEnabled", table = config }),
})

local voicesCategory = page:createCategory(string.format("Voices of Vvardenfell: Console%s",
    getStatusText(config.isAiVoicesActive())))

voicesCategory:createYesNoButton({
    label = "Hide Voice-Line Console Messages",
    description = "Keeps Voices of Vvardenfell's 'Playing Line' and 'Missing Line' messages out of the console. "
        .. "Other console messages are untouched, and that mod's files are not edited. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "aiVoicesConsoleEnabled", table = config }),
})

local instrumentCategory = page:createCategory(string.format("Bardic Inspiration: Musical Instruments%s",
    getStatusText(config.isBardicInspirationActive())))

instrumentCategory:createYesNoButton({
    label = "Enable Musical Instrument Whitelist",
    description = "Lets the items on the Musical Instruments page (drums, flutes, lyres...) be played with Bardic "
        .. "Inspiration, which otherwise only knows lutes. Use one from your inventory or a quick key to play; outdoors, "
        .. "use it again to stop. The songs are Bardic Inspiration's own. Needs a restart.",
    variable = mwse.mcm.createTableVariable({ id = "musicalInstrumentsEnabled", table = config }),
})

template:createExclusionsPage({
    label = "Musical Instruments",
    description = "Items on the left count as instruments for Bardic Inspiration. Click an item to move it to the "
        .. "other list. Lutes don't need to be listed.",
    leftListLabel = "Instruments",
    rightListLabel = "Other items",
    showAllBlocked = true,
    variable = mwse.mcm.createTableVariable({ id = "musicalInstruments", table = config }),
    filters = { { label = "Miscellaneous items", type = "Object", objectType = tes3.objectType.miscItem } },
})

template:register()
