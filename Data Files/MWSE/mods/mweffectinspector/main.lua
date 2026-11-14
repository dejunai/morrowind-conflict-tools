local config = require("mweffectinspector.config")
local inspector = require("mweffectinspector.inspector")

local INSPECT_COMMANDS = {
    ["showeffects"] = true,
    ["inspecteffects"] = true,
    ["/inspecteffects"] = true,
    ["/showeffects"] = true,
    ["magiceffects"] = true,
    ["/magiceffects"] = true,
    ["effects"] = true,
    ["/effects"] = true,
}

local CLEAR_COMMANDS = {
    ["cleareffects"] = true,
    ["/cleareffects"] = true,
    ["purgeeffects"] = true,
    ["/purgeeffects"] = true,
    ["dispel"] = true,
    ["/dispel"] = true,
    ["removeeffects"] = true,
    ["/removeeffects"] = true,
}

local function parseFirstWord(cmdStr)
    if not cmdStr then return nil end
    local clean = cmdStr:gsub("^%s*`*", ""):gsub("`*%s*$", "")
    local firstWord = clean:match("^(%S+)")
    return firstWord and firstWord:lower()
end

-- 1. Integration with More Console Commands (complement when available)
local function tryRegisterWithMCC()
    local interop = include("JosephMcKean.commands.interop")
    if interop and interop.registerCommands then
        interop.registerCommands({
            {
                name = "showeffects",
                description = "Inspect active magic effects, abilities, enchantments, and attached VFX nodes on the target",
                aliases = { "effects", "inspecteffects", "magiceffects", "/inspecteffects", "/showeffects" },
                callback = function(argv)
                    inspector.inspectEffects()
                end,
            },
            {
                name = "cleareffects",
                description = "Remove and purge all active magic effects from the targeted actor",
                aliases = { "dispel", "purgeeffects", "removeeffects", "/cleareffects", "/dispel" },
                callback = function(argv)
                    inspector.clearEffects()
                end,
            },
        })
        mwse.log("[mweffectinspector] Successfully integrated with More Console Commands.")
        return true
    end
    return false
end

-- 2. Independent Console Listener for UI Expansion
local function onUIExpConsoleCommand(e)
    if not config.enabled then return end
    if not e.command then return end

    local cmd = parseFirstWord(e.command)
    if not cmd then return end

    if INSPECT_COMMANDS[cmd] then
        inspector.inspectEffects()
        e.block = true
    elseif CLEAR_COMMANDS[cmd] then
        inspector.clearEffects()
        e.block = true
    end
end

-- 3. Independent Vanilla Console Listener (fallback if UI Expansion is absent)
local function onMenuConsoleActivated(e)
    if not config.enabled then return end
    local menu = e.element
    local input = menu:findChild("MenuConsole_text_input")
    if not input then return end

    input:registerBefore("keyEnter", function()
        local text = input.text
        local cmd = parseFirstWord(text)
        if cmd then
            if INSPECT_COMMANDS[cmd] then
                input.text = ""
                inspector.inspectEffects()
                return false
            elseif CLEAR_COMMANDS[cmd] then
                input.text = ""
                inspector.clearEffects()
                return false
            end
        end
    end)
end

-- 4. In-Game Hotkey Listener (inspect target/player without opening console)
local function onKeyDown(e)
    if not config.enabled then return end
    if tes3.isKeyEqual({ actual = e, expected = config.hotkey }) then
        if not tes3.menuMode() then
            inspector.inspectEffects(tes3.getPlayerTarget() or tes3.player)
        end
    end
end

-- Initialization
local function onInitialized()
    -- Attempt integration with More Console Commands
    tryRegisterWithMCC()
    event.register("command:register", tryRegisterWithMCC)

    -- Register independent UI Expansion & Vanilla console listeners
    event.register("UIEXP:consoleCommand", onUIExpConsoleCommand)
    event.register("uiActivated", onMenuConsoleActivated, { filter = "MenuConsole" })

    -- In-game hotkey
    event.register("keyDown", onKeyDown)

    mwse.log("[mweffectinspector] Initialized. Available console commands: showeffects, inspecteffects, /inspecteffects, cleareffects, dispel.")
end

event.register("initialized", onInitialized)

-- Mod Config Menu
local function registerModConfig()
    require("mweffectinspector.mcm")
end
event.register("modConfigReady", registerModConfig)
