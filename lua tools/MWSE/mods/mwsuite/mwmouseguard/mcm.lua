local config = require("mwmouseguard.config")

local template = mwse.mcm.createTemplate({ name = "Mouse Guard" })
template.onClose = function() config.save() end   -- not saveOnClose: config holds functions

local page = template:createSideBarPage({
    label = "Settings",
})

page.sidebar:createInfo({
    text = [[mwmouseguard prevents the OS cursor and mousewheel scrolling from bleeding onto secondary monitors.

In multi-monitor setups (especially with MGE XE borderless windowed mode), Windows often lets the invisible cursor drift across screen boundaries. This causes mousewheel scrolling in Morrowind (menus, inventory, camera) to simultaneously scroll web browsers or documents on your second screen.

mwmouseguard clips the cursor to the Morrowind window while Morrowind is active, and immediately releases it when you Alt-Tab or press the Windows key.]],
})

local category = page:createCategory("Containment Options")

category:createYesNoButton({
    label = "Enable Mouse Containment",
    description = "When enabled, clips the mouse cursor to Morrowind's window to stop drift and scroll bleed to secondary monitors.",
    variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
})

category:createYesNoButton({
    label = "Contain During Menus & UI",
    description = "Keep cursor contained to Morrowind while inventory, journal, or dialog menus are open.",
    variable = mwse.mcm.createTableVariable({ id = "lockInMenus", table = config }),
})

category:createYesNoButton({
    label = "Contain During Gameplay",
    description = "Keep cursor contained during active 3D gameplay.",
    variable = mwse.mcm.createTableVariable({ id = "lockInGame", table = config }),
})

template:register()
