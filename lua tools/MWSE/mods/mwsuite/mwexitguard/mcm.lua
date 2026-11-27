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
The game is only saved when you save, never when you quit. So once you confirm Exit, Exit Guard simply closes the game instantly. Save first as usual: anything you haven't saved is lost, just as with a normal exit.

New Game:
MGE XE doesn't reset when a game is started over inside a running session, so once a save has been loaded (or a first New Game started), New Game is turned off until you restart Morrowind. Loading a save still works. This part has its own switch below and works even when Exit Guard itself is off.

The in-game New Game block builds on the idea of Petethegoat's Continue (Nexus Mods, Morrowind mod 45952), which can hide the New Game button while in game.]],
})

page.sidebar:createHyperlink({
    text = "Continue by Petethegoat (Nexus Mods)",
    url = "https://www.nexusmods.com/morrowind/mods/45952",
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
    label = "Block New Game Once a Game Is Loaded",
    description = "After a save has been loaded, or a New Game started, in this Morrowind session, New Game is blocked (the button is dimmed, and the game also refuses it from the console or another mod) until you restart Morrowind. MGE XE does not reset in-session, so a second New Game cannot be trusted to work. Loading a save is never blocked, and the first New Game after launch works. Works even when Exit Guard is off. Restart the game after changing it.",
    variable = mwse.mcm.createTableVariable({
        id = "blockNewGameInSession",
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
