local config = require("mwpersonaleffects.config")
local template = mwse.mcm.createTemplate({ name = "mwpersonaleffects" })
template:saveOnClose("mwpersonaleffects", config)

local page = template:createSideBarPage({
    label = "Personal Effects",
    description = "Standalone Lua replacement for Personal Effects' Census and Excise scripts. "
        .. "The ESP records remain required. This module replaces the script behavior and repairs the "
        .. "Sellus Gravius and door guard facing issues.",
})

page:createYesNoButton({
    label = "Enable Personal Effects repairs",
    description = "Unlock and populate the class effects chest, stop the legacy scripts, restore NPC facing, "
        .. "and clean up duplicate chests and player clones. Takes effect after a restart.",
    variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
})

template:register()
