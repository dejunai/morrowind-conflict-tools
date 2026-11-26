--[[
    mwconsole completion engine: works out what is being typed at the cursor and lists candidates.
    Pure logic (no UI): analyze(before, mode) -> context; candidates(context) -> list; apply(...) -> new text.
    mwscript mode:  [ref->]Function arg1 arg2 ...   (argument kinds from mwscript_sigs)
    lua mode:       command arg1 ...                (registered commands, then choices or argKind)
                    a.b.c                           (fields of a global table, for plain Lua)
]]
local parser = require("mwconsole.parser")
local sigs = require("mwconsole.complete.mwscript_sigs")
local index = require("mwconsole.complete.index")
local registry = require("mwconsole.registry")

local engine = {}

local function startsWith(s, p) return s:sub(1, #p) == p end

--- context = { what = "function"|"ref"|"command"|"arg"|"luapath"|"none", kind, prefix, start, quoted, fn, argIndex }
function engine.analyze(before, mode)
    local ctx = { what = "none", prefix = "", start = #before + 1, quoted = false }
    local base, offset = before, 0
    if mode ~= "lua" then
        local arrow = before:find("->", 1, true)
        if arrow then
            base = before:sub(arrow + 2)
            offset = arrow + 1
        end
    end
    local toks = parser.tokenize(base)
    local atSpace = base:match("%s$") ~= nil and not (toks[#toks] and toks[#toks].open)
    local cur, curIndex
    if #toks == 0 or atSpace then
        curIndex = #toks + 1
        ctx.prefix = ""
        ctx.start = #before + 1
    else
        cur = toks[#toks]
        curIndex = #toks
        ctx.prefix = cur.text
        ctx.start = cur.s + offset
        ctx.quoted = cur.quoted
    end
    if mode == "lua" then
        if curIndex == 1 then
            if ctx.prefix:find("[%.:]") then
                ctx.what = "luapath"
            else
                ctx.what = "command"
            end
            return ctx
        end
        local entry = registry.resolve(toks[1].text)
        if not entry then return ctx end
        local argIndex = curIndex - 1
        local spec
        for i, a in ipairs(entry.arguments or {}) do
            if (a.index or i) == argIndex then spec = a break end
        end
        ctx.fn = entry.name
        ctx.argIndex = argIndex
        if spec then
            ctx.what = "arg"
            ctx.choices = spec.choices
            ctx.kind = spec.argKind
        end
        return ctx
    end
    -- mwscript
    if curIndex == 1 then
        if offset == 0 and ctx.quoted then
            ctx.what = "ref"            -- "some id"-> : a reference ID before the arrow
            ctx.kind = "object"
        else
            ctx.what = "function"
        end
        return ctx
    end
    local sig = sigs.get(toks[1].text)
    if not sig then return ctx end
    local arg = sig.args[curIndex - 1]
    ctx.fn = sig.name
    ctx.argIndex = curIndex - 1
    if arg then
        ctx.what = "arg"
        ctx.kind = arg.kind
    end
    return ctx
end

local ID_KINDS = { object = true, item = true, actor = true, creature = true, spell = true, cell = true, global = true,
                   faction = true, script = true, sound = true, class = true, race = true, region = true,
                   topic = true, quest = true, effect = true }
engine.ID_KINDS = ID_KINDS

local commandNames         -- cached sorted list of names and aliases, rebuilt when the registry changes
registry.onChange(function() commandNames = nil end)

local function allCommandNames()
    if not commandNames then
        commandNames = {}
        for name in pairs(registry.commands) do commandNames[#commandNames + 1] = name end
        for alias in pairs(registry.aliases) do commandNames[#commandNames + 1] = alias end
        table.sort(commandNames)
    end
    return commandNames
end

local function luaPath(prefix, limit)
    local out = {}
    local path, sep, last = prefix:match("^(.*)([%.:])([%w_]*)$")
    if not path then return out end
    local t = _G
    for part in path:gmatch("[^%.:]+") do
        local ok, v = pcall(function() return t[part] end)
        if not ok or type(v) ~= "table" then return out end
        t = v
    end
    local keys = {}
    local low = last:lower()
    for k in pairs(t) do
        if type(k) == "string" and k:lower():sub(1, #low) == low then keys[#keys + 1] = k end
    end
    table.sort(keys)
    for i = 1, math.min(#keys, limit) do out[i] = path .. sep .. keys[i] end
    return out
end

--- candidates for a context. opts = { limit = 200, substring = bool (Tab only), budgetMs }
function engine.candidates(ctx, opts)
    opts = opts or {}
    local limit = opts.limit or 200
    local p = ctx.prefix:lower()
    local out = {}
    if ctx.what == "function" then
        for _, e in ipairs(sigs.list) do
            if startsWith(e.name:lower(), p) then out[#out + 1] = e.name if #out >= limit then break end end
        end
        if #out == 0 and opts.substring and p ~= "" then
            for _, e in ipairs(sigs.list) do
                if e.name:lower():find(p, 1, true) then out[#out + 1] = e.name if #out >= limit then break end end
            end
        end
    elseif ctx.what == "command" then
        for _, n in ipairs(allCommandNames()) do
            if startsWith(n, p) then out[#out + 1] = n if #out >= limit then break end end
        end
    elseif ctx.what == "luapath" then
        out = luaPath(ctx.prefix, limit)
    elseif ctx.what == "arg" or ctx.what == "ref" then
        if ctx.choices then
            for _, c in ipairs(ctx.choices) do
                local s = tostring(c)
                if startsWith(s:lower(), p) then out[#out + 1] = s end
            end
        elseif ctx.kind == "axis" then
            for _, a in ipairs({ "X", "Y", "Z" }) do if startsWith(a:lower(), p) then out[#out + 1] = a end end
        elseif ctx.kind and (ID_KINDS[ctx.kind] or index.hasKind(ctx.kind)) then
            out = index.prefix(ctx.kind, ctx.prefix, limit)
            if #out == 0 and opts.substring and p ~= "" then
                out = index.contains(ctx.kind, ctx.prefix, limit, opts.budgetMs)
            end
        end
    end
    return out
end

--- the new text before the cursor with candidate in place of the word being typed
function engine.apply(before, ctx, candidate, mode)
    local head = before:sub(1, ctx.start - 1)
    local text = candidate
    local isId = (ctx.what == "arg" or ctx.what == "ref") and ctx.kind ~= nil and ctx.kind ~= "axis"
    if ctx.quoted or (candidate:find("[%s,]") and (isId or ctx.what == "arg")) then
        text = '"' .. candidate .. '"'
        if ctx.what == "ref" then text = text .. "->" end
    end
    return head .. text
end

return engine
