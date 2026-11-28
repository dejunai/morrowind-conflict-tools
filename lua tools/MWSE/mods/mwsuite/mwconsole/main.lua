--[[
    mwconsole - console commands, Tab completion, selection details and the effect inspector, in one mod.
    Part of the mwsuite (MW Conflict Tools). By dejunai.
    Command API compatible with More Console Commands by JosephMcKean. Ideas from Blue's Smart Console (Safebox),
    Easy Console Commands (TribalLu) and Selection Details (NullCascade); no code from them is used.

    Off until switched on in its MCM. Needs UI Expansion's console for completion, the mode keys and the panel;
    without it, registered commands still work through the vanilla console's Enter key.
    The selection details hotkey is Alt+I, in the world or with the console open. The selection panel never goes in
    front of the console (see guard.lua), so console picking keeps working.
]]
local config = require("mwconsole.config")
local log = require("mwconsole.log")
local guard = require("mwconsole.guard")
local registry = require("mwconsole.registry")
local compat = require("mwconsole.compat_mcc")
local console_ui = require("mwconsole.console_ui")
local index = require("mwconsole.complete.index")
local completeUi = require("mwconsole.complete.ui")
local toggles = require("mwconsole.toggles")
local panel = require("mwconsole.selection.panel")
local window = require("mwconsole.effects.window")
local user = require("mwconsole.user.commands")

local mwconsole = { active = false, guest = false, builtins = false, initialized = false }

-- MCC's own commands; in guest mode (real MCC installed) MCC provides them
local MCC_NAMES = {
    kaching = true, motherlode = true, money = true, cure = true, join = true, levelup = true, max = true, set = true,
    skills = true, speedy = true, coc = true, fly = true, mark = true, recall = true, position = true,
    emptyinventory = true, follow = true, kill = true, killall = true, peace = true, resurrect = true,
    showinventory = true, spawn = true, wander = true, additem = true, dupe = true, setownership = true,
    unlock = true, untrap = true, time = true, weather = true, cls = true, lookup = true, qqq = true,
}

local function out(line) console_ui.print(line) end

local function registerBuiltins()
    if mwconsole.builtins then return end
    mwconsole.builtins = true
    local function add(def)
        if mwconsole.guest and MCC_NAMES[def.name] then return end
        local ok, msg = registry.register(def, { source = "mwconsole", kind = "builtin", native = true })
        if not ok then log.warn("built-in %s: %s", def.name, tostring(msg)) end
    end
    for _, m in ipairs({ "gold", "stats", "travel", "actors", "items", "world", "misc", "effects" }) do
        local ok, err = pcall(function() require("mwconsole.commands." .. m)(add) end)
        if not ok then log.error("loading commands.%s: %s", m, tostring(err)) end
    end
    user.registerAliasCommand()
end

-- dispatch ------------------------------------------------------------------------------------------------------

local function onRun(entry, ok)
    pcall(event.trigger, "mwconsole:commandRun", { name = entry.name, source = entry.source, ok = ok })
end

local function onConsoleCommand(e)
    if e.block or not config.enabled or not config.commands.on then return end
    local handled = registry.dispatch(e.command, e.context, {
        print = out, ref = tes3ui.getConsoleReference(), inMwscript = config.commands.inMwscript, onRun = onRun,
    })
    if handled then e.block = true end
end

-- sandbox helpers for the lua console (no globals are written) --------------------------------------------------

local function onSandbox(e)
    if not config.enabled or not e.sandbox then return end
    local sb = e.sandbox
    if compat.published then sb.command = compat.interop end
    sb.showeffects = function(ref) return window.open(ref) end
    sb.inspecteffects = sb.showeffects
    sb.cleareffects = function(ref) return window.purge(ref) end
    sb.dispel = sb.cleareffects
    sb.sel = function(ref) return panel.printRows(ref) end
    sb.mwconsole = include("mwconsole.api")
end

-- console ------------------------------------------------------------------------------------------------------

local function vanillaEnter(input)
    input:registerBefore("keyEnter", function()
        if not config.enabled or not config.commands.on then return end
        local text = (input.text or ""):gsub("|", "")
        if registry.dispatch(text, "lua", { print = out, ref = tes3ui.getConsoleReference(), onRun = onRun }) then
            input.text = ""
            return false
        end
    end)
end

local function onConsoleOpened(e)
    if not config.enabled then return end
    local menu = e.element
    if not console_ui.isAttached(menu) then
        console_ui.markAttached(menu)
        local hasUiExp = console_ui.findInput(menu) ~= nil
        if hasUiExp then
            guard.run("attach to the console", completeUi.attach, menu)
            if config.console.startLua and console_ui.getMode(menu) ~= "lua" then console_ui.toggleMode(menu) end
        else
            local input = menu:findChild(console_ui.VANILLA_INPUT)
            if input then vanillaEnter(input) end
        end
    end
    user.consoleWarningOnce(out)
    if config.complete.on and not index.built and not config.complete.prebuild then
        guard.run("build the ID list", completeUi.ensureIndex)
    end
    guard.run("show the selection panel", panel.refresh)
end

local function onReferenceChanged()
    if not config.enabled then return end
    guard.run("show the selection panel", panel.refresh)
end

local function consoleOpen()
    local ok, open = pcall(function()
        local console = tes3ui.findMenu("MenuConsole")
        return console ~= nil and console.visible == true
    end)
    return ok and open == true
end

--- a hotkey with no Ctrl or Alt (and not F1-F12) would be typed into the console's input while it is open
local function typesText(k)
    if k.isControlDown or k.isAltDown then return false end
    local c = k.keyCode or 0
    return not ((c >= 59 and c <= 68) or c == 87 or c == 88)
end

--- the hotkey's own character must not reach the console input (UI Expansion does the same for Ctrl+C/X/V)
local function dropTypedText()
    pcall(function() tes3.worldController.menuController.inputController:flushBufferedTextEvents() end)
end

local function onKeyDown(e)
    if not config.enabled then return end
    local hotkey = config.panel.hotkey
    if type(hotkey) ~= "table" then return end
    -- the selection details hotkey: in the world, or with the console open (menu mode, top menu is the console or
    -- our own windows); never in any other menu. Target: console selection, else the crosshair target, else the player
    local inConsole = false
    if tes3.menuMode() then
        inConsole = consoleOpen()
        if not inConsole then return end
    end
    if not tes3.isKeyEqual({ actual = e, expected = hotkey }) then return end
    if inConsole then
        if typesText(hotkey) then return end
        dropTypedText()
    end
    guard.run("open the selection details", panel.openDetails)
end

local function onCtrl()
    if config.enabled and config.panel.requireCtrl then
        local c = tes3ui.findMenu("MenuConsole")
        if c and c.visible then guard.run("show the selection panel", panel.refresh) end
    end
end

local function onObjectCreated(e)
    if config.complete.runtimeObjects and index.built and e.object then
        index.add("object", e.object.id)
    end
end

-- switching on and off -----------------------------------------------------------------------------------------

local eventsOn = false
local function setEvents(on)
    if on == eventsOn then return end
    eventsOn = on
    local fn = on and event.register or event.unregister
    fn("UIEXP:consoleCommand", onConsoleCommand, { priority = -100 })
    fn("uiActivated", onConsoleOpened, { filter = "MenuConsole", priority = -9000 })
    fn("consoleReferenceChanged", onReferenceChanged)
    fn("keyDown", onKeyDown)
    fn("keyDown", onCtrl, { filter = tes3.scanCode.lCtrl })
    fn("keyUp", onCtrl, { filter = tes3.scanCode.lCtrl })
    fn("objectCreated", onObjectCreated)
end

--- turn everything on (from main.lua load, or from the MCM)
function mwconsole.activate()
    if mwconsole.active then return end
    mwconsole.active = true
    mwconsole.guest = compat.realMccPresent()
    if not mwconsole.guest then compat.publish() end
    registerBuiltins()
    setEvents(true)
    toggles.update()
    if mwconsole.initialized then
        -- switched on after the game started: let mods register now, then the user commands
        pcall(event.trigger, "command:register")
        user.loadAll()
    end
    log.info("active%s", mwconsole.guest and " (guest mode: More Console Commands is installed)" or "")
end

function mwconsole.deactivate()
    if not mwconsole.active then return end
    mwconsole.active = false
    setEvents(false)
    toggles.update()
    panel.close("off")
    user.unloadAll()
end

function mwconsole.apply()
    if config.enabled then mwconsole.activate() else mwconsole.deactivate() end
    toggles.update()
end

local function onInitialized()
    mwconsole.initialized = true
    if not config.enabled then return end
    if not mwconsole.guest then pcall(event.trigger, "command:register") end
    user.loadAll()
    if config.complete.on and config.complete.prebuild then guard.run("build the ID list", completeUi.ensureIndex) end
end

-- always registered (cheap): game state for the window rules, the sandbox, the MCM
event.register("loaded", function() guard.setLoaded(true) end)
event.register("load", function() guard.setLoaded(false) end, { priority = 9000 })
event.register("UIEXP:sandboxConsole", onSandbox)
event.register("initialized", onInitialized, { priority = -999 })
event.register("modConfigReady", function()
    local ok, err = pcall(function() require("mwconsole.mcm").build(mwconsole) end)
    if not ok then log.error("MCM: %s", tostring(err)) end
end)

if config.enabled then mwconsole.activate() end

package.loaded["mwconsole.main"] = mwconsole
return mwconsole
