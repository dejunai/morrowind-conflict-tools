local config = require("mwexitguard.config")

local template = mwse.mcm.createTemplate({ name = "Exit Guard" })
template.onClose = function() config.save() end

local page = template:createSideBarPage({
    label = "Settings",
})

page.sidebar:createInfo({
    text = [[Exit Guard fixes the long freeze, and often a crash, that many modded games have when you quit.

The problem:
When you choose Exit, Morrowind unloads everything piece by piece. With MGE XE and a big mod list this can freeze the game for 15-30 seconds and then crash it.

The fix:
The game is only saved when you save, never when you quit. So once you confirm Exit, Exit Guard simply closes the game instantly. Save first as usual: anything you haven't saved is lost, just as with a normal exit.]]
})

page:createYesNoButton({
    label = "Enable Exit Guard",
    description = "Closes the game instantly when you confirm Exit, skipping the freeze and crash. Restart the game after turning it on.",
    variable = mwse.mcm.createTableVariable({
        id = "enabled",
        table = config,
    }),
})

page:createYesNoButton({
    label = "Skip Confirmation Dialog",
    description = "Clicking Exit closes the game right away, without asking 'Are you sure?'. Off by default, so a misclick can't close your game.",
    variable = mwse.mcm.createTableVariable({
        id = "skipConfirmation",
        table = config,
    }),
})

page:createYesNoButton({
    label = "Enable Clean Alt+F4",
    description = "Pressing Alt+F4 also closes the game instantly, instead of freezing.",
    variable = mwse.mcm.createTableVariable({
        id = "enableAltF4",
        table = config,
    }),
})

page:createYesNoButton({
    label = "Log to MWSE.log",
    description = "Writes a line to MWSE.log each time Exit Guard closes the game.",
    variable = mwse.mcm.createTableVariable({
        id = "logToMWSE",
        table = config,
    }),
})

template:register()
