local config = require("mwmouseguard.config")

local template = mwse.mcm.createTemplate({ name = "Mouse Guard" })
template.onClose = function() config.save() end   -- not saveOnClose: config holds functions

local page = template:createSideBarPage({
    label = "Settings",
})

page.sidebar:createInfo({
    text = [[Mouse Guard stops the mouse from drifting onto a second monitor.

With more than one screen (especially in MGE XE's borderless window mode), Windows can let the hidden mouse pointer slide off the edge of the Morrowind window. Then scrolling the mouse wheel in game also scrolls whatever is open on your other screen.

Mouse Guard keeps the pointer inside the Morrowind window while you play, and lets it go as soon as you Alt-Tab or press the Windows key.]],
})

local category = page:createCategory("When to keep the mouse in the window")

category:createYesNoButton({
    label = "Enable Mouse Containment",
    description = "Keeps the mouse pointer inside the Morrowind window, so scrolling in game doesn't also scroll something on another monitor.",
    variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
})

category:createYesNoButton({
    label = "Keep the mouse in the window during menus",
    description = "Also keeps the pointer in the window while menus (inventory, journal, dialogue) are open.",
    variable = mwse.mcm.createTableVariable({ id = "lockInMenus", table = config }),
})

category:createYesNoButton({
    label = "Keep the mouse in the window during gameplay",
    description = "Keeps the pointer in the window while you are playing with no menu open.",
    variable = mwse.mcm.createTableVariable({ id = "lockInGame", table = config }),
})

template:register()
