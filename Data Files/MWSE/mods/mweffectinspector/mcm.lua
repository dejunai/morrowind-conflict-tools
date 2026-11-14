local config = require("mweffectinspector.config")
local inspector = require("mweffectinspector.inspector")

local template = mwse.mcm.createTemplate("Effect Inspector")
template.onClose = function() config.save() end   -- not saveOnClose: config holds functions

local page = template:createSideBarPage({
    label = "Settings",
})

local mccInstalled = tes3.getFileSource("MWSE/mods/JosephMcKean/commands/main.lua") ~= nil
local uiexpInstalled = tes3.getFileSource("MWSE/mods/UI Expansion/main.lua") ~= nil

page.sidebar:createInfo({
    text = string.format([[mweffectinspector provides in-depth inspection and debugging tools for magic effects, constant abilities, enchantments, and lingering VFX particle nodes on actors.

Supported Console Commands:
  • showeffects (or /showeffects)
  • inspecteffects (or /inspecteffects)
  • cleareffects (or /cleareffects)
  • dispel (or /dispel)
  • purgeeffects

Integration Status:
  • More Console Commands: %s
  • UI Expansion: %s

When run inside the console, it inspects whatever reference is currently targeted/clicked. If no reference is selected in console, or when using the in-game hotkey, it inspects your crosshair target (or player).]],
    mccInstalled and "[Connected]" or "[Standalone Mode]",
    uiexpInstalled and "[Active]" or "[Vanilla Console Mode]"),
})

local generalCategory = page:createCategory("General Settings")

generalCategory:createYesNoButton({
    label = "Enable Effect Inspector",
    description = "Master toggle for the Effect Inspector suite.",
    variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
})

generalCategory:createKeyBinder({
    label = "In-Game Inspection Hotkey",
    description = "Press this hotkey in-game to inspect your current crosshair target (or yourself if no target). Defaults to Alt+I.",
    variable = mwse.mcm.createTableVariable({ id = "hotkey", table = config }),
    allowCombinations = true,
})

local displayCategory = page:createCategory("Inspection Options")

displayCategory:createYesNoButton({
    label = "Inspect Innate Spells, Abilities & Diseases",
    description = "Include innate spells, racial abilities, birthsign traits, blights, and diseases in the inspection report.",
    variable = mwse.mcm.createTableVariable({ id = "showSpells", table = config }),
})

displayCategory:createYesNoButton({
    label = "Inspect Equipped Items & Enchantments",
    description = "Include equipped gear and their enchantments (Constant Effect, On Strike, On Use) in the inspection report.",
    variable = mwse.mcm.createTableVariable({ id = "showEquipment", table = config }),
})

displayCategory:createYesNoButton({
    label = "Inspect Attached Scene Nodes & Lingering VFX",
    description = "Traverse the 3D scene node hierarchy looking for particle systems and attached magic/shield VFX nodes.",
    variable = mwse.mcm.createTableVariable({ id = "showVFXNodes", table = config }),
})

displayCategory:createYesNoButton({
    label = "Show Interactive Dispel Popup",
    description = "Display an in-game message box with a 'Purge / Dispel All Effects' button upon inspecting.",
    variable = mwse.mcm.createTableVariable({ id = "interactivePopup", table = config }),
})

displayCategory:createYesNoButton({
    label = "Mirror Output to MWSE.log",
    description = "Write full inspection details into MWSE.log for offline debugging.",
    variable = mwse.mcm.createTableVariable({ id = "logToMWSE", table = config }),
})

local actionsCategory = page:createCategory("Quick Actions")

actionsCategory:createButton({
    label = "Inspect Player Character Now",
    description = "Run a complete effect and VFX inspection on the player character immediately.",
    buttonText = "Inspect Player",
    callback = function()
        if tes3.player then
            inspector.inspectEffects(tes3.player)
        else
            tes3.messageBox("A game must be loaded to inspect the player.")
        end
    end,
})

actionsCategory:createButton({
    label = "Purge Player Active Effects Now",
    description = "Remove all active magic effects currently on the player character.",
    buttonText = "Purge Effects",
    callback = function()
        if tes3.player then
            inspector.clearEffects(tes3.player)
        else
            tes3.messageBox("A game must be loaded to purge effects.")
        end
    end,
})

mwse.mcm.register(template)
