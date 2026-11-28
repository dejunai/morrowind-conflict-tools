local config = require("mwexitguard.config")

local template = mwse.mcm.createTemplate({ name = "Exit Guard" })
template.onClose = function() config.save() end

local page = template:createSideBarPage({
    label = "Settings",
})

page.sidebar:createInfo({
    label = "Save before quitting",
    text = [[Exit Guard skips the slow shutdown that can freeze a heavily modded game.

- Exit Guard closes the game without saving.
- Restart Morrowind after changing the Exit Guard or New Game switch.
- The New Game switch works independently. You can still load saves in the same session.

The New Game block builds on Petethegoat's Continue.]],
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
    description = "On: clicking Exit closes Morrowind immediately. Save first. Off: Exit still asks you to confirm.",
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
