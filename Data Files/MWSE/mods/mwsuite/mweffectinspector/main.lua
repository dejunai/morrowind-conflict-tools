local config = require("mweffectinspector.config")
local inspector = require("mweffectinspector.inspector")

local INSPECT_COMMANDS = {
    ["inspecteffects"] = true,
    ["showeffects"] = true,
    ["effects"] = true,
    ["magiceffects"] = true,
    ["/inspecteffects"] = true,
    ["/showeffects"] = true,
}

local CLEAR_COMMANDS = {
    ["cleareffects"] = true,
    ["purgeeffects"] = true,
    ["dispel"] = true,
    ["/dispel"] = true,
    ["removeeffects"] = true,
    ["/removeeffects"] = true,
}

local function parseFirstWord(cmdStr)
    if not cmdStr then return nil end
    local clean = cmdStr:gsub("^%s*`*", ""):gsub("`*%s*$", "")
    clean = clean:gsub("%(.*%)", "")
    local firstWord = clean:match("^(%S+)")
    return firstWord and firstWord:lower()
end

local function handleConsoleCommand(cmdStr)
    local cmd = parseFirstWord(cmdStr)
    if not cmd then return false end
    if INSPECT_COMMANDS[cmd] then
        inspector.inspectEffects()
        return true
    elseif CLEAR_COMMANDS[cmd] then
        inspector.clearEffects()
        return true
    end
    return false
end

-- Expose to global Lua environment for UI Expansion Lua console (e.g. inspecteffects or inspecteffects())
_G.inspecteffects = function(ref) inspector.inspectEffects(ref) end
_G.showeffects = function(ref) inspector.inspectEffects(ref) end
_G.cleareffects = function(ref) inspector.clearEffects(ref) end
_G.dispel = function(ref) inspector.clearEffects(ref) end

-- 1. Integration with More Console Commands
local mccRegistered = false
local function tryRegisterWithMCC()
    if mccRegistered then return true end
    local interop = include("JosephMcKean.commands.interop")
    if interop and interop.registerCommands then
        local commands = {
            {
                name = "showeffects",
                description = "Inspect active magic effects, abilities, enchantments, and attached VFX nodes on the target",
                aliases = { "effects", "inspecteffects", "magiceffects", "/inspecteffects", "/showeffects" },
                arguments = {},
                callback = function(argv)
                    inspector.inspectEffects()
                end,
            },
            {
                name = "cleareffects",
                description = "Remove and purge all active magic effects from the targeted actor",
                aliases = { "dispel", "purgeeffects", "removeeffects", "/cleareffects", "/dispel" },
                arguments = {},
                callback = function(argv)
                    inspector.clearEffects()
                end,
            },
        }

        local toRegister = {}
        for _, cmd in ipairs(commands) do
            local name = cmd.name:lower()
            if not (interop.data and interop.data.commands and interop.data.commands[name]) then
                table.insert(toRegister, cmd)
            end
        end

        if #toRegister > 0 then
            interop.registerCommands(toRegister)
        end
        mccRegistered = true
        mwse.log("[mweffectinspector] Successfully integrated with More Console Commands.")
        return true
    end
    return false
end

-- 2. UI Expansion Console Listener (catches both Lua and MWScript contexts)
local function onUIExpConsoleCommand(e)
    if not config.enabled then return end
    if not e.command then return end
    if handleConsoleCommand(e.command) then
        e.block = true
    end
end

-- 3. Vanilla Console Listener (fallback if UI Expansion is absent)
local function onMenuConsoleActivated(e)
    if not config.enabled then return end
    local menu = e.element
    local input = menu:findChild("MenuConsole_text_input")
    if not input then return end

    input:registerBefore("keyEnter", function()
        if handleConsoleCommand(input.text) then
            input.text = ""
            return false
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
    tryRegisterWithMCC()
    event.register("command:register", tryRegisterWithMCC)

    -- Single unfiltered listener catches all UI Expansion console contexts (lua, mwscript, etc.)
    event.register("UIEXP:consoleCommand", onUIExpConsoleCommand)

    event.register("uiActivated", onMenuConsoleActivated, { filter = "MenuConsole" })
    event.register("keyDown", onKeyDown)

    mwse.log("[mweffectinspector] Initialized. Available console commands: showeffects, inspecteffects, /inspecteffects, cleareffects, dispel.")
end

event.register("initialized", onInitialized)

local function registerModConfig()
    require("mweffectinspector.mcm")
end
event.register("modConfigReady", registerModConfig)
