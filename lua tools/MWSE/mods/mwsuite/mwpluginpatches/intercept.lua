--[[
    Shared intercept helpers for mwpluginpatches. Each per-mod patch in patches/ calls one of
    these instead of anyone editing that mod's Lua:

      intercept.errorToLog(rule)      rule = { label, module, fn }
          Wraps module[fn] for a module the mod loads with require(). If that function throws,
          the error goes to MWSE.log and the mod carries on. The module is wrapped as soon as it
          loads (a searcher placed first in package.loaders), or straight away if it is already
          in package.loaded.

      intercept.messageBoxDrop(rule)  rule = { label, source, prefix }
          Holds back a tes3.messageBox whose text starts with prefix, only when the call comes
          from a file whose path contains source (debug.getinfo, lowercased, forward slashes).
          The same text from any other mod still shows.

    Planned, not built yet (for hand-edit throttles and log redirects, if they come back from
    luafix): throttle(rule) for event callbacks registered from a given source file, and
    logRedirect(rule) for print/mwse.log calls made from a given source file. Both would use the
    same source matching as messageBoxDrop.

    Both helpers return true when the intercept is in place. By dej (dejunai).
]]

local intercept = {}

local wrappedFns = setmetatable({}, { __mode = "k" })

local function log(fmt, ...)
    local ok, text = pcall(string.format, fmt, ...)
    mwse.log("[mwpluginpatches] %s", ok and text or tostring(fmt))
end

-- errorToLog ------------------------------------------------------------------------------

local function wrapFunction(mod, rule)
    if type(mod) ~= "table" then return false end
    local original = mod[rule.fn]
    if type(original) ~= "function" or wrappedFns[original] then return false end
    local function finish(ok, ...)
        if ok then return ... end
        log("%s: %s() raised an error; logged here instead of stopping the mod: %s",
            rule.label, rule.fn, tostring((...)))
    end
    local function guarded(...)
        return finish(pcall(original, ...))
    end
    wrappedFns[guarded] = true
    mod[rule.fn] = guarded
    return true
end

local searchers = {}   -- module name -> rule, for the one searcher this file installs
local searcherInstalled = false

local function findChunk(name, self)
    local loaders = package.loaders or package.searchers
    local messages = {}
    for _, loader in ipairs(loaders) do
        if loader ~= self then
            local found = loader(name)
            if type(found) == "function" then return found end
            if type(found) == "string" then messages[#messages + 1] = found end
        end
    end
    return table.concat(messages)
end

local function searcher(name)
    local rule = searchers[name]
    if not rule then return nil end
    local chunk = findChunk(name, searcher)
    if type(chunk) ~= "function" then return chunk end
    return function(...)
        local mod = chunk(...)
        if mod == nil then mod = package.loaded[name] end
        local ok, err = pcall(wrapFunction, mod, rule)
        if not ok then log("%s: could not wrap %s.%s: %s", rule.label, rule.module, rule.fn, tostring(err)) end
        return mod
    end
end

local function applyErrorToLog(rule)
    local loaded = package.loaded[rule.module]
    if type(loaded) == "table" then
        return wrapFunction(loaded, rule)
    end
    searchers[rule.module] = rule
    if not searcherInstalled then
        local loaders = package.loaders or package.searchers
        table.insert(loaders, 1, searcher)
        searcherInstalled = true
    end
    return true
end

-- messageBoxDrop --------------------------------------------------------------------------

local drops = {}
local nativeMessageBox

local function normalise(source)
    return (source or ""):lower():gsub("\\", "/")
end

local function calledFrom(pattern)
    for level = 3, 8 do
        local info = debug.getinfo(level, "S")
        if not info then return false end
        if normalise(info.source):find(pattern, 1, true) then return true end
    end
    return false
end

local function messageText(first)
    if type(first) == "string" then return first end
    if type(first) == "table" and type(first.message) == "string" then return first.message end
    return nil
end

local function filteredMessageBox(first, ...)
    local text = messageText(first)
    if text then
        for i = 1, #drops do
            local rule = drops[i]
            if text:sub(1, #rule.prefix) == rule.prefix and calledFrom(rule.source) then
                return nil
            end
        end
    end
    return nativeMessageBox(first, ...)
end

local function applyMessageBoxDrop(rule)
    if type(tes3.messageBox) ~= "function" then return false end
    drops[#drops + 1] = rule
    if not nativeMessageBox then
        nativeMessageBox = tes3.messageBox
        tes3.messageBox = filteredMessageBox
    end
    return true
end

--------------------------------------------------------------------------------------------

intercept.errorToLog = applyErrorToLog
intercept.messageBoxDrop = applyMessageBoxDrop
intercept.calledFrom = calledFrom

return intercept
