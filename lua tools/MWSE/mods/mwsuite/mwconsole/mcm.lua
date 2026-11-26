--[[
    mwconsole MCM ("Console (mwconsole)"). Buttons that open a window or act on the world follow the window
    rules: at the main menu they only say "Load a game first".
]]
local config = require("mwconsole.config")
local guard = require("mwconsole.guard")
local registry = require("mwconsole.registry")
local index = require("mwconsole.complete.index")
local toggles = require("mwconsole.toggles")
local window = require("mwconsole.effects.window")
local panel = require("mwconsole.selection.panel")
local user = require("mwconsole.user.commands")
local store = require("mwconsole.user.store")
local console_ui = require("mwconsole.console_ui")

local mcm = {}

local function var(tbl, id)
    return mwse.mcm.createTableVariable({ id = id, table = tbl })
end

local function statusText()
    local n, mods, users = 0, {}, 0
    for _, e in pairs(registry.commands) do
        n = n + 1
        if e.kind == "user" then users = users + 1 end
        if e.kind == "mod" then mods[e.source] = true end
    end
    local modList = {}
    for m in pairs(mods) do modList[#modList + 1] = m end
    table.sort(modList)
    local uiexp = tes3.getFileSource and tes3.getFileSource("MWSE\\mods\\UI Expansion\\main.lua") ~= nil
    return table.concat({
        "mwconsole: console commands, Tab completion, details of the selected object and the effect inspector.",
        "",
        "Status: " .. (config.enabled and "on" or "off (turn it on above)"),
        "UI Expansion console: " .. (uiexp and "found" or "not found (completion and the panel need it)"),
        string.format("Commands: %d (%d from other mods: %s)", n, #modList, #modList > 0 and table.concat(modList, ", ") or "none"),
        string.format("ID list: %s", index.built and string.format("%d IDs, built in %.0f ms", index.count, index.buildMs) or "not built yet"),
        config.userScripts.on and string.format("Developer scripts: ON (%d commands)", users) or "Developer scripts: off",
        "",
        "Credits: by dejunai. Command API compatible with More Console Commands by JosephMcKean; ideas from Blue's "
            .. "Smart Console (Safebox), Easy Console Commands (TribalLu) and Selection Details (NullCascade). "
            .. "Links are on the Credits page.",
    }, "\n")
end

local function commandList()
    local lines = {}
    for _, e in ipairs(registry.list()) do
        local tag = e.kind == "user" and " (user)" or (e.source ~= "mwconsole" and (" (" .. e.source .. ")") or "")
        lines[#lines + 1] = string.format("%s%s: %s", e.name, tag, e.description or "")
    end
    return #lines > 0 and table.concat(lines, "\n") or "No commands yet (turn mwconsole on, then reopen this page)."
end

function mcm.build(main)
    local template = mwse.mcm.createTemplate({ name = "Console (mwconsole)" })
    template.onClose = function() config.save() end          -- not saveOnClose: config holds functions
    local apply = function() if main then main.apply() end end

    local page = template:createSideBarPage({ label = "Settings" })
    page.sidebar:createInfo({ text = "", postCreate = function(self) self.elements.info.text = statusText() end })

    local general = page:createCategory("mwconsole")
    general:createOnOffButton({
        label = "Turn on mwconsole",
        description = "Master switch. Off: none of mwconsole's commands, keys, completion or panel do anything.",
        variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }), callback = apply,
    })

    local cmds = page:createCategory("Commands")
    cmds:createOnOffButton({ label = "Mod commands in the lua console",
        description = "Turns on mwconsole's extra commands (money, coc, showeffects, ...) and those other mods add.",
        variable = var(config.commands, "on") })
    cmds:createOnOffButton({ label = "Also accept them in mwscript mode",
        description = "Lets mod commands run in mwscript mode too, but never overrides a real Morrowind command with the same name.",
        variable = var(config.commands, "inMwscript") })
    cmds:createOnOffButton({ label = "Open the console in lua mode",
        description = "Switches the console to lua mode the first time it opens. Ctrl+Left or Ctrl+Right switches mode any time.",
        variable = var(config.console, "startLua") })

    local comp = page:createCategory("Completion")
    comp:createOnOffButton({ label = "Tab completion",
        description = "Tab fills in commands and IDs; press it again to cycle, Shift+Tab to go back.",
        variable = var(config.complete, "on") })
    comp:createOnOffButton({ label = "Show suggestions while typing",
        description = "Shows the best matches under the input as you type. Turn off if the console feels slow.",
        variable = var(config.complete, "live") })
    comp:createSlider({ label = "Letters before suggesting",
        description = "How many letters you type before suggestions appear under the input.",
        min = 1, max = 5, step = 1, jump = 1, variable = var(config.complete, "minChars") })
    comp:createOnOffButton({ label = "Build the ID list at startup",
        description = "Makes the first console open instant, at the cost of a slightly longer game start.",
        variable = var(config.complete, "prebuild") })
    comp:createOnOffButton({ label = "Include dialogue topics",
        description = "Adds dialogue topics to the ID list (bigger, a little slower). Takes effect after Rebuild ID list.",
        variable = var(config.complete, "topics") })
    comp:createOnOffButton({ label = "Index objects created during play",
        description = "Adds objects that mods create while you play to the ID list.",
        variable = var(config.complete, "runtimeObjects") })
    comp:createButton({ buttonText = "Rebuild ID list", label = "ID list",
        description = "Builds the list of object, cell, faction and spell IDs again. Works at the main menu too.",
        callback = function()
            guard.run("rebuild the ID list", function()
                index.build(nil, { topics = config.complete.topics })
                tes3.messageBox(string.format("mwconsole: %d IDs in %.0f ms", index.count, index.buildMs))
            end)
        end })

    local sel = page:createCategory("Selection details")
    sel:createOnOffButton({ label = "Show details of the selected object",
        description = "Opens a panel next to the console with the selected object's files, owner, script values and more.",
        variable = var(config.panel, "on") })
    sel:createOnOffButton({ label = "Only while Ctrl is held",
        description = "Shows the panel only while you hold Ctrl with the console open.",
        variable = var(config.panel, "requireCtrl") })
    sel:createOnOffButton({ label = "Panel on the right side",
        description = "On: the panel sits on the right of the screen. Off: on the left.",
        variable = var(config.panel, "right") })
    sel:createSlider({ label = "Panel opacity (percent)",
        description = "How solid the panel's background is.",
        min = 30, max = 100, step = 5, jump = 10,
        variable = mwse.mcm.createVariable({
            get = function() return math.floor((config.panel.alpha or 0.85) * 100 + 0.5) end,
            set = function(_, v) config.panel.alpha = v / 100 end }) })
    sel:createOnOffButton({ label = "Scan visual effects on objects",
        description = "Lets the panel's effects button inspect stuck glows on non-living objects (doors, containers, lights).",
        variable = var(config.panel, "objectVfx") })

    sel:createKeyBinder({ label = "Selection details hotkey",
        description = "Press in game (outside menus) to open the selection details window for the console selection, else what you are looking at, else yourself. Its Show Effects button opens the effect inspector. Default Alt+I.",
        variable = var(config.panel, "hotkey"), allowCombinations = true })
    sel:createButton({ buttonText = "Show my details now", label = "Selection details",
        description = "Opens the selection details window on your character. Needs a loaded game.",
        callback = function() guard.run("open the selection details", panel.openDetails, tes3.player) end })

    local eff = page:createCategory("Effect inspector")
    eff:createOnOffButton({ label = "List spells and abilities",
        description = "The inspector lists the target's spells, abilities, diseases and blight.",
        variable = var(config.effects, "showSpells") })
    eff:createOnOffButton({ label = "List enchanted equipment",
        description = "The inspector lists the target's equipped enchanted items.",
        variable = var(config.effects, "showEquipment") })
    eff:createOnOffButton({ label = "List leftover visual effects",
        description = "The inspector lists particle systems and scene nodes that look like magic visuals.",
        variable = var(config.effects, "showVFX") })
    eff:createTextField({ label = "Words that mark a visual-effect node",
        description = "Comma-separated. A scene node whose name contains one of these counts as a visual effect.",
        variable = var(config.effects, "vfxWords") })
    eff:createOnOffButton({ label = "Copy reports to MWSE.log",
        description = "Also writes the inspector's console lines to MWSE.log.",
        variable = var(config.effects, "logToMWSE") })
    eff:createButton({ buttonText = "Inspect my character now", label = "Inspect",
        description = "Opens the effect inspector on your character. Needs a loaded game.",
        callback = function() guard.run("open the effect inspector", window.open, tes3.player) end })
    eff:createButton({ buttonText = "Purge my active effects now", label = "Purge",
        description = "Removes every active magic effect from your character. Needs a loaded game.",
        callback = function() guard.run("purge active effects", window.purge, tes3.player) end })

    local tog = page:createCategory("Quick toggle keys")
    tog:createOnOffButton({ label = "Quick toggle keys (master switch)",
        description = "Lets the keys below run ResetActors, ToggleCollision and ToggleMenus. They never fire while you're typing or in a menu.",
        variable = var(config.toggles, "on"), callback = function() toggles.update() end })
    for _, t in ipairs(toggles.LIST) do
        tog:createKeyBinder({ label = "Key: " .. t.label,
            description = "Unbound by default. Runs " .. t.command .. " when pressed (exact modifiers).",
            variable = var(config.toggles, t.key), allowCombinations = true,
            callback = function() toggles.update() end })
    end
    tog:createDropdown({ label = "Hold or press",
        description = "Press: flips it on and off. Hold: on only while the key is held (never gets out of sync). "
            .. "Typing tcl or tm by hand can make Press get out of step.",
        options = { { label = "Press", value = "press" }, { label = "Hold", value = "hold" } },
        variable = var(config.toggles, "style"), callback = function() toggles.update() end })

    local adv = page:createCategory("Advanced")
    adv:createOnOffButton({ label = "Use mwcompanions with follow",
        description = "follow tells you when mwcompanions counts the character as a companion.",
        variable = var(config.compat, "useMwcompanions") })
    adv:createOnOffButton({ label = "qqq uses mwexitguard's fast exit",
        description = "When mwexitguard is on, qqq ends the game the same quick way it does.",
        variable = var(config.compat, "useMwexitguard") })
    adv:createDropdown({ label = "Log level",
        description = "How much goes to MWSE\\logs\\mwconsole.log. Errors also leave one line in MWSE.log.",
        options = { { label = "Errors", value = "ERROR" }, { label = "Warnings", value = "WARN" },
                    { label = "Info", value = "INFO" }, { label = "Debug", value = "DEBUG" } },
        variable = var(config, "logLevel") })

    -- Developer page
    local dev = template:createSideBarPage({ label = "Developer" })
    dev.sidebar:createInfo({ text = user.WARNING .. "\n\nScripts are kept in " .. store.BASE
        .. "\\user_commands.json and " .. store.SCRIPTS .. "\\. Add them in the lua console with alias add <name> <lua>; "
        .. "alias list, alias show, alias rm and alias reload manage them." })
    local devCat = dev:createCategory("User script commands")
    devCat:createButton({
        label = "User script commands",
        buttonText = config.userScripts.on and "On (turn off)" or "Off (turn on...)",
        description = "Lets you save short Lua snippets as console commands. Turning on asks you to confirm the warning first.",
        callback = function(self)
            if config.userScripts.on then
                guard.run("turn off user script commands", user.setOn, false)
                pcall(function() self:setText("Off (turn on...)") end)
            else
                user.confirmTurnOn(function(on)
                    if on then pcall(function() self:setText("On (turn off)") end) end
                end)
            end
        end })
    devCat:createOnOffButton({ label = "Safe mode for scripts",
        description = "Blocks the riskiest functions (quit, run programs, delete or rename files, writing files outside MWSE\\config\\mwconsole). Turning this off shows a second warning.",
        variable = var(config.userScripts, "safeMode"),
        callback = function()
            if not config.userScripts.safeMode and not config.userScripts.unsafeWarned then
                config.userScripts.unsafeWarned = true
                tes3.messageBox("Safe mode is off: user scripts can now quit the game, run programs and delete or rename files. Turn it back on unless you need this.")
            elseif config.userScripts.safeMode then
                config.userScripts.unsafeWarned = false
            end
        end })
    devCat:createOnOffButton({ label = "Let scripts replace other commands",
        description = "Allows alias add <name> --override. Never applies to real Morrowind commands.",
        variable = var(config.userScripts, "allowOverride") })
    devCat:createSlider({ label = "Script step limit (millions)",
        description = "Stops a script that runs too long.",
        min = 1, max = 100, step = 1, jump = 5, variable = var(config.userScripts, "maxInstructions") })
    devCat:createButton({ buttonText = "Reload scripts", label = "Reload",
        description = "Reads user_commands.json and the scripts folder again.",
        callback = function()
            guard.run("reload user scripts", function()
                local n = user.loadAll()
                tes3.messageBox(string.format("mwconsole: %d user command(s) loaded", n))
            end)
        end })

    local listPage = template:createPage({ label = "Commands" })
    listPage:createInfo({ text = "", postCreate = function(self) self.elements.info.text = commandList() end })

    -- Credits: the mods whose ideas mwconsole borrows (listed with their authors and pages)
    local CREDITS = {
        { mod = "More Console Commands", author = "JosephMcKean",
          idea = "The command API that other mods use to add console commands, and the set of everyday commands (money, coc, cure, levelup, spawn and the rest), reimplemented here.",
          url = "https://www.nexusmods.com/morrowind/mods/52500" },
        { mod = "Blue - Smart Console", author = "Safebox",
          idea = "Console suggestions and Tab completion that know what each command expects.",
          url = "https://www.nexusmods.com/morrowind/mods/53427" },
        { mod = "Easy Console Commands", author = "TribalLu",
          idea = "Keys for ResetActors, ToggleCollision and ToggleMenus.",
          url = "https://www.nexusmods.com/morrowind/mods/54855" },
        { mod = "Selection Details", author = "NullCascade",
          idea = "Details of the selected object (ID, source, mesh, textures, scripts, ownership, Lua data) shown beside the console.",
          url = "https://www.nexusmods.com/morrowind/mods/51095" },
        { mod = "mweffectinspector", author = "dej (dejunai)",
          idea = "The effect inspector (showeffects, cleareffects and the in-game window), now part of mwconsole." },
    }
    local credits = template:createPage({ label = "Credits" })
    credits:createInfo({ text = "mwconsole is by dejunai. It borrows ideas from the mods below. No code from the third-party mods is used. Each link opens the original mod's page; please support their authors." })
    for _, c in ipairs(CREDITS) do
        local cat = credits:createCategory(c.mod .. " - by " .. c.author)
        cat:createInfo({ text = c.idea })
        if c.url then cat:createHyperlink({ text = c.url, url = c.url }) end
    end

    template:register()
    return template
end

-- for tests and the MCM status line
mcm.statusText = statusText
mcm.commandList = commandList
mcm.console_ui = console_ui

return mcm
