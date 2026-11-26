local config = require("mwteleportguard.config")

local template = mwse.mcm.createTemplate({ name = "Teleport Guard" })
template.onClose = function() config.save() end   -- not saveOnClose: config holds functions

local page = template:createSideBarPage({
    label = "Settings",
})

page.sidebar:createInfo({
    text = [[Teleport Guard stops crashes and freezes when a mod moves you somewhere else in the middle of a conversation.

The problem:
Some mods send you to another place straight from a dialogue line, while the conversation window is still open. That can freeze the camera, break the dialogue window, leave your companions behind, or crash the game.

The fix:
Teleport Guard catches these moves. Everything else the line does (journal updates, items) happens right away, the conversation ends normally, and only then are you moved, together with your companions.]],
})

local category = page:createCategory("Teleport Protection Options")

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
    label = "Force Goodbye Mode on Dialogue",
    description = "Ends the conversation (only Goodbye is left) as soon as a move is waiting, so you can leave cleanly.",
    variable = mwse.mcm.createTableVariable({ id = "forceGoodbye", table = config }),
})

category:createYesNoButton({
    label = "Smooth Visual Fade Transition",
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
