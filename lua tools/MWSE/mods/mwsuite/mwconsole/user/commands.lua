--[[
    mwconsole user script commands: the `alias` console command and loading saved scripts into the registry.
    Developer feature, off by default; it can only be turned on in the MCM (with a warning).
]]
local config = require("mwconsole.config")
local log = require("mwconsole.log")
local guard = require("mwconsole.guard")
local registry = require("mwconsole.registry")
local sigs = require("mwconsole.complete.mwscript_sigs")
local store = require("mwconsole.user.store")
local runner = require("mwconsole.user.runner")

local user = {}

user.OFF_MESSAGE = "User script commands are off. Turn them on in Mod Config > Console > Developer."
user.WARNING = "Developer feature. User script commands run any Lua you write, with full access to the game and to "
    .. "files that MWSE can reach. A mistake can corrupt or break your saves, permanently change your character, or "
    .. "crash the game. Only run scripts you understand, and back up your saves first."
user.CONSOLE_WARNING = {
    "mwconsole: user script commands are ON. They run any Lua you saved, with full access to the game.",
    "Mistakes can break saves or crash the game; back up your saves. (Turn off in Mod Config > Console > Developer.)",
}

local loaded = {}           -- names registered from the store this session
local overrideLogged = {}

function user.validName(name)
    if type(name) ~= "string" then return false, "a name is needed" end
    if not name:match("^[a-z0-9_]+$") then return false, name .. ": use only a-z, 0-9 and _" end
    if #name < 2 or #name > 32 then return false, name .. ": use 2 to 32 characters" end
    if registry.RESERVED[name] then return false, name .. " is reserved" end
    if sigs.isVanilla(name) then return false, name .. " is a Morrowind command and can't be used" end
    return true
end

local function parseArgSpec(list)
    local out = {}
    for i, mv in ipairs(list or {}) do
        local name, opt = tostring(mv):match("^(.-)(%??)$")
        out[#out + 1] = { index = i, metavar = name, required = opt ~= "?" }
    end
    return out
end

local function makeCallback(name)
    return function(_, ctx)
        local entry = store.get(name)
        if not entry then ctx.print(name .. ": not found; try alias reload") return end
        local code, err = store.readScript(entry)
        if not code then ctx.print(name .. ": " .. tostring(err)) return end
        local target
        pcall(function() target = tes3.getPlayerTarget() end)
        return runner.run(name, code, ctx.words or {}, {
            print = ctx.print, ref = ctx.ref, target = target,
            cmd = function(other, ...)
                local parts = { other }
                for i = 1, select("#", ...) do
                    local a = tostring((select(i, ...)))
                    parts[#parts + 1] = a:find("%s") and ('"' .. a .. '"') or a
                end
                return registry.dispatch(table.concat(parts, " "), "lua", { print = ctx.print, ref = ctx.ref, inMwscript = false })
            end,
        })
    end
end

--- registers one stored command; returns ok, message
local function registerOne(name, entry)
    if entry.on == false then return false, name .. " is off" end
    local ok, msg = user.validName(name)
    if not ok then return false, msg end
    local wantOverride = entry.override and config.userScripts.allowOverride
    local okR, res = registry.register({
        name = name, description = entry.description or "(user script)", aliases = entry.aliases or {},
        arguments = parseArgSpec(entry.args), callback = makeCallback(name), caseSensitive = true,
        context = entry.context == "any" and "any" or "lua", needsGame = entry.needsGame ~= false,
    }, { source = "user", kind = "user", native = true, override = wantOverride })
    if not okR then return false, res end
    loaded[name] = true
    if res.override and not overrideLogged[name] then
        overrideLogged[name] = true
        log.warn("user command %s overrides an existing command", name)
    end
    return true
end

function user.unloadAll()
    for name in pairs(loaded) do
        registry.unregister(name, "user")
        runner.forget(name)
    end
    loaded = {}
end

--- (re)loads every saved command. Returns the number registered and a list of problems.
function user.loadAll()
    user.unloadAll()
    if not config.enabled or not config.userScripts.on then return 0, {} end
    local _, warning = store.load()
    local problems = {}
    if warning then problems[#problems + 1] = warning end
    local names = {}
    for name in pairs(store.data.commands) do names[#names + 1] = name end
    table.sort(names)
    local n = 0
    for _, name in ipairs(names) do
        local ok, msg = registerOne(name, store.data.commands[name])
        if ok then n = n + 1 elseif msg and not msg:find(" is off$") then problems[#problems + 1] = msg end
    end
    for _, p in ipairs(problems) do log.warn("user commands: %s", p) end
    return n, problems
end

function user.count()
    local n = 0
    for _ in pairs(loaded) do n = n + 1 end
    return n
end

function user.isLoaded(name) return loaded[name] == true end

-- the alias command --------------------------------------------------------------------------------------------

local function words(s)
    local out = {}
    for w in s:gmatch("%S+") do out[#out + 1] = w end
    return out
end

local sub = {}

local function needEntry(p, name)
    local e = name and store.get(name)
    if not e then p((name or "?") .. " is not a user command") end
    return e
end

local function saveAndReload(p, okMessage)
    local ok, err = store.save()
    if not ok then p("couldn't save: " .. tostring(err)) return false end
    user.loadAll()
    if okMessage then p(okMessage) end
    return true
end

local function checkCode(p, name, code)
    if #code > (config.userScripts.inlineLimit or 500) or code:find("\n") then
        p(string.format("%s: inline scripts are one line of up to %d characters; use alias file %s",
            name, config.userScripts.inlineLimit or 500, name))
        return false
    end
    local fn, err = runner.compile(code, name)
    if not fn then p(tostring(err)) return false end
    return true
end

local function clashCheck(p, name, override)
    if registry.isTaken(name) and not loaded[name] then
        local owner = registry.ownerOf(name) or "?"
        if override then
            if not config.userScripts.allowOverride then
                p("overrides are off (Mod Config > Console > Developer)")
                return false
            end
            if owner == "user" then p(name .. " is already a user command") return false end
            return true
        end
        p(string.format("%s is already a command from %s", name, owner))
        return false
    end
    return true
end

sub.add = function(p, rest)
    local name, tail = rest:match("^(%S+)%s*(.*)$")
    if not name then p("usage: alias add <name> [--override] <lua...>") return end
    name = name:lower()
    local override = false
    if tail:match("^%-%-override%s") then override = true tail = tail:gsub("^%-%-override%s+", "") end
    local ok, msg = user.validName(name)
    if not ok then p(msg) return end
    if store.get(name) then p(name .. " is already a user command; use alias edit") return end
    if not clashCheck(p, name, override) then return end
    if tail == "" then p("usage: alias add <name> [--override] <lua...>") return end
    if not checkCode(p, name, tail) then return end
    store.put(name, { code = tail, aliases = {}, args = {}, description = "", context = "lua", needsGame = true,
                      on = true, override = override or nil })
    saveAndReload(p, "added " .. name)
end

sub.file = function(p, rest)
    local name = (rest:match("^(%S+)") or ""):lower()
    local ok, msg = user.validName(name)
    if not ok then p(msg) return end
    local e = store.get(name)
    if e and e.code then p(name .. " is an inline command; remove it first") return end
    if not e and not clashCheck(p, name, false) then return end
    local file, path = store.writeTemplate(name)
    if not file then p("couldn't create the file: " .. tostring(path)) return end
    if not e then
        store.put(name, { file = file, aliases = {}, args = {}, description = "", context = "lua", needsGame = true, on = true })
        saveAndReload(p)
    end
    p("script file: " .. path)
end

sub.edit = function(p, rest)
    local name, code = rest:match("^(%S+)%s*(.*)$")
    local e = needEntry(p, name and name:lower())
    if not e then return end
    if e.file then p(name .. " lives in a file; edit " .. store.scriptPath(e.file) .. " then alias reload") return end
    if not checkCode(p, name, code) then return end
    e.code = code
    store.put(name:lower(), e)
    runner.forget(name:lower())
    saveAndReload(p, "updated " .. name)
end

sub.rm = function(p, rest)
    local name = (rest:match("^(%S+)") or ""):lower()
    local e = needEntry(p, name)
    if not e then return end
    if e.file then store.retireScript(e.file) end
    store.remove(name)
    saveAndReload(p, "removed " .. name .. (e.file and " (its file is in scripts\\removed)" or ""))
end

sub.rename = function(p, rest)
    local w = words(rest)
    local old, new = (w[1] or ""):lower(), (w[2] or ""):lower()
    local e = needEntry(p, old)
    if not e then return end
    local ok, msg = user.validName(new)
    if not ok then p(msg) return end
    if store.get(new) or (registry.isTaken(new) and not loaded[new]) then p(new .. " is already a command") return end
    store.remove(old)
    store.put(new, e)
    runner.forget(old)
    saveAndReload(p, string.format("renamed %s to %s", old, new))
end

sub.also = function(p, rest)
    local w = words(rest:lower())
    local e = needEntry(p, w[1])
    if not e then return end
    e.aliases = e.aliases or {}
    for i = 2, #w do
        local ok, msg = user.validName(w[i])
        if not ok then p(msg)
        elseif registry.isTaken(w[i]) and registry.resolve(w[i]) ~= registry.commands[w[1]] then
            p(w[i] .. " is already a command from " .. (registry.ownerOf(w[i]) or "?"))
        else
            local dup = false
            for _, a in ipairs(e.aliases) do if a == w[i] then dup = true end end
            if not dup then e.aliases[#e.aliases + 1] = w[i] end
        end
    end
    store.put(w[1], e)
    saveAndReload(p, w[1] .. " aliases: " .. table.concat(e.aliases, ", "))
end

sub.unalso = function(p, rest)
    local w = words(rest:lower())
    local e = needEntry(p, w[1])
    if not e then return end
    local kept = {}
    for _, a in ipairs(e.aliases or {}) do if a ~= w[2] then kept[#kept + 1] = a end end
    e.aliases = kept
    store.put(w[1], e)
    saveAndReload(p, w[1] .. " aliases: " .. (#kept > 0 and table.concat(kept, ", ") or "none"))
end

sub.args = function(p, rest)
    local w = words(rest)
    local name = (w[1] or ""):lower()
    local e = needEntry(p, name)
    if not e then return end
    e.args = {}
    for i = 2, #w do e.args[#e.args + 1] = w[i] end
    store.put(name, e)
    saveAndReload(p, registry.usage({ name = name, arguments = parseArgSpec(e.args) }))
end

sub.desc = function(p, rest)
    local name, text = rest:match("^(%S+)%s*(.*)$")
    local e = needEntry(p, name and name:lower())
    if not e then return end
    e.description = text
    store.put(name:lower(), e)
    saveAndReload(p, "description set")
end

sub.game = function(p, rest)
    local w = words(rest:lower())
    local e = needEntry(p, w[1])
    if not e then return end
    if w[2] ~= "on" and w[2] ~= "off" then p("usage: alias game <name> on|off") return end
    e.needsGame = w[2] == "on"
    store.put(w[1], e)
    saveAndReload(p, w[1] .. (e.needsGame and " needs a loaded game" or " also works without a loaded game"))
end

sub.mode = function(p, rest)
    local w = words(rest:lower())
    local e = needEntry(p, w[1])
    if not e then return end
    if w[2] ~= "lua" and w[2] ~= "any" then p("usage: alias mode <name> lua|any") return end
    e.context = w[2]
    store.put(w[1], e)
    saveAndReload(p, w[1] .. " runs in " .. (w[2] == "any" and "both console modes" or "lua mode only"))
end

local function setOn(p, rest, value)
    local name = (rest:match("^(%S+)") or ""):lower()
    local e = needEntry(p, name)
    if not e then return end
    e.on = value
    store.put(name, e)
    saveAndReload(p, name .. (value and " is on" or " is off"))
end
sub.on = function(p, rest) setOn(p, rest, true) end
sub.off = function(p, rest) setOn(p, rest, false) end

sub.list = function(p)
    local names = {}
    for name in pairs(store.data.commands) do names[#names + 1] = name end
    table.sort(names)
    if #names == 0 then p("no user commands") return end
    for _, name in ipairs(names) do
        local e = store.data.commands[name]
        local flags = {}
        if e.on == false then flags[#flags + 1] = "off" end
        if e.override then flags[#flags + 1] = "! override" end
        if e.file then flags[#flags + 1] = "file" end
        if not loaded[name] and e.on ~= false then flags[#flags + 1] = "not loaded" end
        p(string.format("%s%s%s%s", name,
            (e.aliases and #e.aliases > 0) and (" (" .. table.concat(e.aliases, ", ") .. ")") or "",
            #flags > 0 and (" [" .. table.concat(flags, ", ") .. "]") or "",
            (e.description and e.description ~= "") and (" - " .. e.description) or ""))
    end
end

sub.show = function(p, rest)
    local name = (rest:match("^(%S+)") or ""):lower()
    local e = needEntry(p, name)
    if not e then return end
    p(registry.usage({ name = name, arguments = parseArgSpec(e.args) }))
    p(string.format("mode %s, needs game %s, %s", e.context or "lua", tostring(e.needsGame ~= false), e.on == false and "off" or "on"))
    if e.file then p("file: " .. store.scriptPath(e.file)) end
    local code = store.readScript(e)
    for line in tostring(code or ""):gmatch("[^\n]+") do p("  " .. line) end
end

sub.reload = function(p)
    local n, problems = user.loadAll()
    for _, pr in ipairs(problems) do p(pr) end
    p(string.format("loaded %d user command(s)", n))
end

user.SUBCOMMANDS = { "add", "file", "edit", "rm", "rename", "also", "unalso", "args", "desc", "game", "mode",
                     "on", "off", "list", "show", "reload" }

function user.aliasCommand(argv, ctx)
    local p = ctx.print
    local raw = ctx.raw or ""
    local _, after = raw:match("^%s*`?(%S+)%s*(.*)$")
    after = after or ""
    local subName, rest = after:match("^(%S+)%s*(.*)$")
    subName = subName and subName:lower()
    if not subName then
        p("usage: alias " .. table.concat(user.SUBCOMMANDS, "|") .. " ...")
        return
    end
    if not config.userScripts.on then
        if subName == "list" then store.load() sub.list(p) return end
        p(user.OFF_MESSAGE)
        return
    end
    local fn = sub[subName]
    if not fn then p("unknown: alias " .. subName .. " (try: " .. table.concat(user.SUBCOMMANDS, ", ") .. ")") return end
    fn(p, rest or "")
end

function user.registerAliasCommand()
    return registry.register({
        name = "alias", description = "Developer: save short Lua snippets as console commands (alias add/list/show/rm ...)",
        arguments = { { index = 1, metavar = "subcommand", required = false, choices = user.SUBCOMMANDS } },
        callback = user.aliasCommand, caseSensitive = true, needsGame = false,
    }, { source = "mwconsole", kind = "builtin", native = true })
end

--- the two-line console warning, once per turn-on
function user.consoleWarningOnce(print)
    if config.enabled and config.userScripts.on and not config.userScripts.consoleWarned then
        for _, l in ipairs(user.CONSOLE_WARNING) do print(l) end
        config.userScripts.consoleWarned = true
        config.save()
        return true
    end
    return false
end

--- MCM: turning the feature on goes through a confirmation; off resets the one-time warnings
function user.setOn(value)
    if value then
        config.userScripts.on = true
        config.userScripts.warningShown = os.date("%Y-%m-%d %H:%M:%S")
        config.userScripts.consoleWarned = false
    else
        config.userScripts.on = false
        config.userScripts.warningShown = false
        config.userScripts.consoleWarned = false
    end
    config.save()
    return user.loadAll()
end

function user.confirmTurnOn(onDone)
    tes3.messageBox({
        message = user.WARNING,
        buttons = { "Turn on", "Cancel" },
        callback = function(e)
            local turnedOn = e.button == 0
            if turnedOn then guard.run("turn on user script commands", user.setOn, true) end
            if onDone then pcall(onDone, turnedOn) end
        end,
    })
end

return user
