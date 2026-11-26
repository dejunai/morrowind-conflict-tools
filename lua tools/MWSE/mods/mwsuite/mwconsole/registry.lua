--[[
    mwconsole registry: one store of console commands for dispatch, help and completion.

    entry = { name, description, aliases = {}, arguments = { {index, metavar, required, choices, help,
              containsSpaces, didYouMean, argKind} }, callback, caseSensitive, argPattern,
              source = "mwconsole" | mod name | "user", kind = "builtin" | "mod" | "user",
              context = "lua" | "any", needsGame = bool, native = bool (callback gets (argv, ctx)) }

    Rules:
    * names and aliases are lowercase; an alias works from the moment it is registered
    * a duplicate name is refused (logged once), the first registration keeps it
    * native-API and user commands may never use a vanilla mwscript name (built-ins and MCC-route commands may,
      for lua mode; in mwscript mode a vanilla name always goes to the engine)
    * an override replaces a command and the original comes back when the override is removed
]]
local log = require("mwconsole.log")
local parser = require("mwconsole.parser")
local sigs = require("mwconsole.complete.mwscript_sigs")
local guard = require("mwconsole.guard")

local registry = {}

local commands = {}     -- name -> entry
local aliases = {}      -- alias -> name
local shadowed = {}     -- name -> entry replaced by an override
local listeners = {}    -- functions called after any change (completion cache, MCM list)

registry.commands = commands
registry.aliases = aliases
registry.RESERVED = { alias = true, help = true, lua = true, mwconsole = true }

local function changed()
    for _, fn in ipairs(listeners) do pcall(fn) end
end

function registry.onChange(fn) listeners[#listeners + 1] = fn end

function registry.resolve(word)
    if type(word) ~= "string" then return nil end
    local w = word:lower()
    local e = commands[w]
    if e then return e end
    local target = aliases[w]
    return target and commands[target] or nil
end

function registry.isTaken(word)
    local w = word:lower()
    return commands[w] ~= nil or aliases[w] ~= nil
end

--- owner of a name or alias, for messages
function registry.ownerOf(word)
    local e = registry.resolve(word)
    return e and e.source or nil
end

local function addAliases(entry)
    local kept = {}
    for _, a in ipairs(entry.aliases or {}) do
        if type(a) == "string" then
            local al = a:lower()
            if al ~= entry.name then
                if (entry.kind == "user" or (entry.native and entry.kind == "mod")) and sigs.isVanilla(al) then
                    log.warn("alias %s of %s refused: it is a Morrowind command", al, entry.name)
                elseif commands[al] or (aliases[al] and aliases[al] ~= entry.name) then
                    log.warn("alias %s of %s refused: already used by %s", al, entry.name, registry.ownerOf(al) or "?")
                else
                    aliases[al] = entry.name
                    kept[#kept + 1] = al
                end
            end
        end
    end
    entry.aliases = kept
end

local function removeAliases(entry)
    for _, a in ipairs(entry.aliases or {}) do
        if aliases[a] == entry.name then aliases[a] = nil end
    end
end

--[[ register(def, opts) -> ok, message
     opts = { source, kind, native, override } ]]
function registry.register(def, opts)
    opts = opts or {}
    if type(def) ~= "table" or type(def.name) ~= "string" or def.name == "" then
        return false, "a command needs a name"
    end
    if type(def.callback) ~= "function" then
        return false, def.name .. ": a command needs a callback"
    end
    local name = def.name:lower()
    local kind = opts.kind or "mod"
    local native = opts.native and true or false
    if (kind == "user" or (native and kind == "mod")) and sigs.isVanilla(name) then
        return false, string.format("%s is a Morrowind command and can't be replaced", name)
    end
    local existing = commands[name]
    local aliasOwner = aliases[name]
    if existing or aliasOwner then
        local owner = existing or commands[aliasOwner]
        local can = opts.override and owner ~= nil
        if can and kind == "user" and owner.kind == "user" then can = false end   -- user vs user: refused
        if can and kind == "mod" then can = owner.source == opts.source end
        if not can then
            local msg = string.format("%s is already a command from %s", name, owner and owner.source or "?")
            if kind == "mod" and not native then log.error("%s", msg) end   -- MCC logs duplicates as errors
            return false, msg
        end
        if existing then
            if not shadowed[name] then shadowed[name] = existing end
            removeAliases(existing)
            commands[name] = nil
        else
            return false, string.format("%s is already an alias of %s", name, aliasOwner)
        end
    end
    local entry = {}
    for k, v in pairs(def) do entry[k] = v end
    entry.name = name
    entry.description = def.description or ""
    entry.arguments = def.arguments or {}
    entry.aliases = def.aliases or {}
    entry.source = opts.source or def.source or "unknown"
    entry.kind = kind
    entry.native = native
    entry.override = existing ~= nil
    entry.context = def.context or "lua"
    entry.needsGame = def.needsGame ~= false
    commands[name] = entry
    addAliases(entry)
    changed()
    return true, entry
end

--- remove a command. source must match unless force. Restores a shadowed original.
function registry.unregister(name, source, force)
    local w = name:lower()
    local e = commands[w]
    if not e then return false, w .. " is not a command" end
    if not force and source and e.source ~= source then
        return false, string.format("%s belongs to %s", w, e.source)
    end
    removeAliases(e)
    commands[w] = nil
    local orig = shadowed[w]
    if orig then
        shadowed[w] = nil
        commands[w] = orig
        addAliases(orig)
    end
    changed()
    return true
end

function registry.list()
    local out = {}
    for _, e in pairs(commands) do out[#out + 1] = e end
    table.sort(out, function(a, b) return a.name < b.name end)
    return out
end

function registry.isOverridden(name) return shadowed[name:lower()] ~= nil end

-- arguments ------------------------------------------------------------------------------------------------------

function registry.usage(e)
    local parts = { "usage: " .. e.name }
    for _, a in ipairs(e.arguments or {}) do
        local mv = a.metavar or "arg"
        parts[#parts + 1] = a.required and mv or ("[" .. mv .. "]")
    end
    return table.concat(parts, " ")
end

registry.didYouMean = {}   -- value -> suggestion, filled by commands and mods (argument field didYouMean = true)

--- builds argv from the typed words; returns argv or nil, { lines }
function registry.parseArgs(e, words)
    local args = {}
    for i, w in ipairs(words) do args[i] = e.caseSensitive and w or w:lower() end
    local spec = e.arguments or {}
    if spec[1] and spec[1].containsSpaces and #args > 1 then args = { table.concat(args, " ") } end
    local missing = {}
    for i, a in ipairs(spec) do
        local idx = a.index or i
        local v = args[idx]
        if v == nil then
            if a.required then missing[#missing + 1] = a.metavar or ("arg" .. idx) end
        elseif a.choices then
            local found = false
            for _, c in ipairs(a.choices) do if tostring(c):lower() == v:lower() then found = true break end end
            if not found then
                local lines = { registry.usage(e) }
                if a.didYouMean and registry.didYouMean[v] then
                    lines[#lines + 1] = "Did you mean: " .. registry.didYouMean[v]
                end
                local shown = {}
                for k, c in ipairs(a.choices) do if k <= 20 then shown[#shown + 1] = tostring(c) end end
                lines[#lines + 1] = string.format("%s: error: argument %s: invalid choice: %s (choose from %s%s)",
                    e.name, a.metavar or idx, v, table.concat(shown, ", "), #a.choices > 20 and ", ..." or "")
                return nil, lines
            end
        end
    end
    if #missing > 0 then
        return nil, { registry.usage(e),
            string.format("%s: error: the following arguments are required: %s", e.name, table.concat(missing, ", ")) }
    end
    return args
end

-- dispatch -------------------------------------------------------------------------------------------------------

registry.depth = 0

--[[ dispatch(text, context, io) -> handled
     io = { print = fn(line), ref = reference or nil, inMwscript = bool (option), onRun = fn(entry, ok) }
     A command runs in mwscript context only when the option allows it, its name is not a vanilla command, and
     (for user scripts) it was declared context "any". ]]
function registry.dispatch(text, context, io)
    io = io or {}
    local out = io.print or function() end
    local name, words = parser.split(text)
    if not name then return false end
    local e = registry.resolve(name)
    if not e then return false end
    if context == "mwscript" then
        if not io.inMwscript or sigs.isVanilla(name) then return false end
        if e.kind == "user" and e.context ~= "any" then return false end
    end
    if e.needsGame and not guard.isGameLoaded() then
        out(guard.NOT_LOADED)
        return true
    end
    local argv, errLines = registry.parseArgs(e, words)
    if not argv then
        for _, l in ipairs(errLines) do out(l) end
        return true
    end
    if registry.depth >= 8 then
        out(e.name .. ": too many nested commands")
        return true
    end
    registry.depth = registry.depth + 1
    local ctx = { ref = io.ref, context = context, print = out, name = e.name, raw = text, words = words }
    local ok, err = xpcall(function()
        if e.native then return e.callback(argv, ctx) end
        return e.callback(argv)
    end, debug.traceback)
    registry.depth = registry.depth - 1
    if not ok then
        local first = tostring(err):match("^[^\n]*") or tostring(err)
        out(string.format("%s: %s", e.name, first))
        guard.reportError("command " .. e.name .. " (" .. tostring(e.source) .. ")", err)
    end
    if io.onRun then pcall(io.onRun, e, ok) end
    return true
end

return registry
