local config = require("mwteleportguard.config")

local template = mwse.mcm.createTemplate({ name = "Teleport Guard" })
template.onClose = function() config.save() end   -- not saveOnClose: config holds functions

local page = template:createSideBarPage({
    label = "Settings",
})

page.sidebar:createInfo({
    text = [[Teleport Guard delays moves triggered by dialogue until the conversation closes.

- Journal updates and item rewards still happen during the conversation.
- Leave the conversation to finish the move.
- Enable the companion option if your followers should travel with you.]],
})

local category = page:createCategory("Dialogue teleports")

category:createYesNoButton({
    label = "Enable Safe Dialogue Teleportation",
    description = "Turns the protection on: a move during a conversation waits until the conversation is over.",
    variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
})

category:createYesNoButton({
    label = "Teleport Active Companions",
    description = "Brings your companions along to wherever you are sent.",
    variable = mwse.mcm.createTableVariable({ id = "teleportCompanions", table = config }),
})

category:createYesNoButton({
    label = "Offer only Goodbye when a move is waiting",
    description = "Ends the conversation (only Goodbye is left) as soon as a move is waiting, so you can leave cleanly.",
    variable = mwse.mcm.createTableVariable({ id = "forceGoodbye", table = config }),
})

category:createYesNoButton({
    label = "Fade the screen during a teleport",
    description = "Fades the screen to black and back when you are moved.",
    variable = mwse.mcm.createTableVariable({ id = "fadeTransition", table = config }),
})

category:createSlider({
    label = "Fade Transition Duration (Seconds)",
    description = "How long the fade to black lasts, in seconds (with the fade above on).",
    min = 0,
    max = 2,
    step = 0.1,
    jump = 0.5,
    variable = mwse.mcm.createTableVariable({ id = "fadeDuration", table = config }),
})

category:createYesNoButton({
    label = "Log Interceptions to MWSE.log",
    description = "Writes each caught move, and where it sent you, to MWSE.log.",
    variable = mwse.mcm.createTableVariable({ id = "logToMWSE", table = config }),
})

template:register()
