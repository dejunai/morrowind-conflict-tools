local config = require("mwteleportguard.config")

local template = mwse.mcm.createTemplate({ name = "Teleport Guard" })
template.onClose = function() config.save() end   -- not saveOnClose: config holds functions

local page = template:createSideBarPage({
    label = "Settings",
})

page.sidebar:createInfo({
    text = [[mwteleportguard is a mod-agnostic safety tool that prevents crashes and freezes caused by scripted player teleports during dialogue.

The Problem:
In vanilla Morrowind, executing `Player->PositionCell` while the dialogue window is open unloads the active cell out from underneath the conversation. This triggers camera freezes, orphaned dialogue UI, actor pointer corruption, companion abandonment, and frequent crashes to desktop.

The Solution:
mwteleportguard intercepts any dialogue command attempting to teleport the player. It executes any accompanying quest updates (journal, items, variables) immediately, ensures a clean "Goodbye" exit, and defers the physical cell transition until the dialogue window has fully closed. It also ensures all companion followers are safely teleported alongside you.]],
})

local category = page:createCategory("Teleport Protection Options")

category:createYesNoButton({
    label = "Enable Safe Dialogue Teleportation",
    description = "Master toggle for intercepting and deferring mid-dialogue teleports.",
    variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
})

category:createYesNoButton({
    label = "Teleport Active Companions",
    description = "Automatically teleports all active companion followers along with the player to the destination cell.",
    variable = mwse.mcm.createTableVariable({ id = "teleportCompanions", table = config }),
})

category:createYesNoButton({
    label = "Force Goodbye Mode on Dialogue",
    description = "Forces the dialogue conversation into Goodbye mode when a teleport is queued, allowing a natural, clean exit.",
    variable = mwse.mcm.createTableVariable({ id = "forceGoodbye", table = config }),
})

category:createYesNoButton({
    label = "Smooth Visual Fade Transition",
    description = "Performs a smooth cinematic black fadeout and fadein when the deferred teleport occurs.",
    variable = mwse.mcm.createTableVariable({ id = "fadeTransition", table = config }),
})

category:createSlider({
    label = "Fade Transition Duration (Seconds)",
    description = "Length of the black screen fade transition in seconds.",
    min = 0,
    max = 2,
    step = 0.1,
    jump = 0.5,
    variable = mwse.mcm.createTableVariable({ id = "fadeDuration", table = config }),
})

category:createYesNoButton({
    label = "Log Interceptions to MWSE.log",
    description = "Record intercepted dialogue teleports and destinations in MWSE.log.",
    variable = mwse.mcm.createTableVariable({ id = "logToMWSE", table = config }),
})

mwse.mcm.register(template)
