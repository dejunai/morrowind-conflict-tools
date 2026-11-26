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
    description = "Turns the inspector on: its hotkey and console commands work only while this is on. (The two buttons at the bottom work either way.)",
    variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
})

generalCategory:createKeyBinder({
    label = "In-Game Inspection Hotkey",
    description = "Press in game to open the inspector on whatever you are looking at, or on yourself if nothing. Default: Alt+I.",
    variable = mwse.mcm.createTableVariable({ id = "hotkey", table = config }),
    allowCombinations = true,
})

local displayCategory = page:createCategory("Inspection Options")

displayCategory:createYesNoButton({
    label = "Inspect Innate Spells, Abilities & Diseases",
    description = "Lists the target's spells, racial and birthsign abilities, diseases and blight in the report.",
    variable = mwse.mcm.createTableVariable({ id = "showSpells", table = config }),
})

displayCategory:createYesNoButton({
    label = "Inspect Equipped Items & Enchantments",
    description = "Lists the target's equipped items and their enchantments in the report.",
    variable = mwse.mcm.createTableVariable({ id = "showEquipment", table = config }),
})

displayCategory:createYesNoButton({
    label = "Inspect Attached Scene Nodes & Lingering VFX",
    description = "Looks for leftover magic visuals (glows, shield bubbles, particles) stuck on the target, a common cause of effects that won't go away.",
    variable = mwse.mcm.createTableVariable({ id = "showVFXNodes", table = config }),
})

displayCategory:createYesNoButton({
    label = "Mirror Output to MWSE.log",
    description = "Also copies each report into MWSE.log, so you can read it after you quit.",
    variable = mwse.mcm.createTableVariable({ id = "logToMWSE", table = config }),
})

local actionsCategory = page:createCategory("Quick Actions")

actionsCategory:createButton({
    label = "Inspect Player Character Now",
    description = "Opens the inspector on your character right now.",
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
    description = "Removes every active magic effect from your character right now, good and bad. Use it when an effect is stuck.",
    buttonText = "Purge Effects",
    callback = function()
        if tes3.player then
            inspector.clearEffects(tes3.player)
        else
            tes3.messageBox("A game must be loaded to purge effects.")
        end
    end,
})

template:register()
