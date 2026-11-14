local config = require("mwcompanionsneak.config")
local inspectorUI = require("mwcompanionsneak.inspectorUI")

local CONFIG_NAME = "mwcompanionsneak"

local template = mwse.mcm.createTemplate({ name = "mwcompanionsneak" })
template:saveOnClose(CONFIG_NAME, config)
template.onClose = function()
    mwse.saveConfig(CONFIG_NAME, config)
end

local page = template:createSideBarPage({
    label = "Settings",
    description = "mwcompanionsneak eliminates unwanted stealth detection feedback:\n\n1. Companion Stealth Disregard: Prevents followers, companions, and friendly summons from detecting the sneaking player, preserving the sneak crosshair and hidden indicator.\n\n2. Entity Detection Blacklist: Automatically blacklists all creatures from stealth detection (if enabled) and allows blacklisting false-positive entities (such as critters, ambient animals, or roosters) via the Detection Inspector hotkey (Default: K).",
})

local general = page:createCategory("General Options")

general:createOnOffButton({
    label = "Enable Mod",
    description = "Enable or disable companion sneak disregard and entity blacklisting.",
    variable = mwse.mcm.createTableVariable({
        id = "enabled",
        table = config,
    }),
})

local compCat = page:createCategory("Companion Options")

compCat:createOnOffButton({
    label = "Include Creature Followers",
    description = "When enabled, creature companions (pack guars, pet scribs, summoned minions following you) will also ignore you while sneaking.",
    variable = mwse.mcm.createTableVariable({
        id = "includeCreatures",
        table = config,
    }),
})

compCat:createOnOffButton({
    label = "Include Escort Quest Targets",
    description = "When enabled, NPCs with active escort packages targeting the player will also ignore you while sneaking.",
    variable = mwse.mcm.createTableVariable({
        id = "includeEscorts",
        table = config,
    }),
})

local blCat = page:createCategory("Entity Blacklist Options")

blCat:createOnOffButton({
    label = "Blacklist All Creatures",
    description = "When enabled, all creatures (animals, monsters, roosters, ambient critters) are automatically ignored by stealth detection. Only NPCs will detect the sneaking player.",
    variable = mwse.mcm.createTableVariable({
        id = "blacklistAllCreatures",
        table = config,
    }),
})

blCat:createKeyBinder({
    label = "Detection Inspector Hotkey",
    description = "Press this key in-game to open the Detection Inspector window. It displays all actors currently suspecting or detecting you, lets you inspect their IDs and distances, and lets you blacklist false-positive entities with a single click.\n\nDefault: K",
    allowCombinations = true,
    variable = mwse.mcm.createTableVariable({
        id = "inspectorKey",
        table = config,
    }),
})

blCat:createButton({
    label = "Open Detection Inspector UI",
    description = "Opens the in-game Detection Inspector to view nearby actors and manage blacklisted entities.",
    buttonText = "Open Inspector",
    callback = function()
        inspectorUI.open()
    end,
})

blCat:createButton({
    label = "Clear Custom Blacklist",
    description = "Clears all custom blacklisted entity IDs.",
    buttonText = "Clear Blacklist",
    callback = function()
        config.blacklist = {}
        mwse.saveConfig(CONFIG_NAME, config)
        tes3.messageBox("Custom entity blacklist cleared.")
    end,
})

local debugCat = page:createCategory("Diagnostics")

debugCat:createOnOffButton({
    label = "Debug Logging",
    description = "Enables detailed logging in MWSE.log for sneak detection events.",
    variable = mwse.mcm.createTableVariable({
        id = "debugMode",
        table = config,
    }),
})

template:register()
