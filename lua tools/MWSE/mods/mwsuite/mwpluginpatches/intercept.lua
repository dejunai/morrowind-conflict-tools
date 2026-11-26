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

          An optional rule.when() makes the drop conditional: the box is held back only when
          it returns true.

      intercept.wrapHandlers(rule)    rule = { label, source, event, wrap }
          Wraps event.register once. A callback registered for rule.event straight from a file
          whose path contains rule.source is replaced by rule.wrap(callback). unregister and
          isRegistered are mapped to the wrapper, so the mod can still remove its handler.

      intercept.throttle(rule)        rule = { label, source, event, interval }
          wrapHandlers that runs the handler at most once per interval seconds, with e.delta
          set to the time summed since its last run.

      intercept.skipWhen(rule)        rule = { label, source, event, when }
          wrapHandlers that skips a call whenever when(e) returns true.

    Planned, not built yet: logRedirect(rule) for print/mwse.log calls made from a given source
    file, using the same source matching.

    Handler rules must be in place before the target registers (mwpluginpatches loads at
    load-priority 4500, before plain main.lua mods).

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
    return ((source or ""):lower():gsub("\\", "/"))
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
                local drop = true
                if rule.when then
                    local ok, wanted = pcall(rule.when)
                    drop = ok and wanted == true
                end
                if drop then return nil end
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

-- event handlers: wrapHandlers, throttle, skipWhen --------------------------------------
-- event.register is wrapped once. A callback is replaced by a wrapper only when the
-- register call comes straight from the rule's source file (up to 3 frames above the hook) for the
-- rule's event; everything else goes through untouched. The original -> wrapper map
-- (weak keys) keeps event.unregister and event.isRegistered working for the mod, and a
-- second register of the same callback reuses the same wrapper.

local handlerRules = {}
local wrapperMaps = {}
local nativeRegister, nativeUnregister, nativeIsRegistered

local function eventKey(eventId, options)
    local filter = type(options) == "table" and options.filter or nil
    return tostring(eventId):lower() .. "|" .. tostring(filter)
end

-- frame 1 is this function, 2 wrapperFor, 3 the event.* hook, 4+ the code that called event.*
local function registeringSource(pattern)
    for level = 4, 6 do
        local info = debug.getinfo(level, "S")
        if not info then return false end
        if normalise(info.source):find(pattern, 1, true) then return true end
    end
    return false
end

local function wrapperFor(eventId, callback, options)
    if type(callback) ~= "function" then return callback end
    local key = eventKey(eventId, options)
    local map = wrapperMaps[key]
    if map and map[callback] then return map[callback] end
    local name = tostring(eventId):lower()
    local wrapped = callback
    for i = 1, #handlerRules do
        local rule = handlerRules[i]
        if rule.event == name and registeringSource(rule.source) then
            local ok, result = pcall(rule.wrap, wrapped)
            if ok and type(result) == "function" then
                wrapped = result
                if not rule.reported then
                    rule.reported = true
                    log("%s: its %s handler now goes through our %s.", rule.label, rule.event, rule.what or "wrapper")
                end
            elseif not ok then
                log("%s: could not wrap its %s handler: %s", rule.label, rule.event, tostring(result))
            end
        end
    end
    if wrapped == callback then return callback end
    if not map then
        map = setmetatable({}, { __mode = "k" })
        wrapperMaps[key] = map
    end
    map[callback] = wrapped
    return wrapped
end

local function mapped(eventId, callback, options)
    local map = wrapperMaps[eventKey(eventId, options)]
    return map and map[callback] or callback
end

local function installRegisterHook()
    if nativeRegister then return true end
    if type(event) ~= "table" or type(event.register) ~= "function" then return false end
    nativeRegister, nativeUnregister, nativeIsRegistered = event.register, event.unregister, event.isRegistered
    event.register = function(eventId, callback, options, ...)
        return nativeRegister(eventId, wrapperFor(eventId, callback, options), options, ...)
    end
    if type(nativeUnregister) == "function" then
        event.unregister = function(eventId, callback, options, ...)
            return nativeUnregister(eventId, mapped(eventId, callback, options), options, ...)
        end
    end
    if type(nativeIsRegistered) == "function" then
        event.isRegistered = function(eventId, callback, options, ...)
            return nativeIsRegistered(eventId, mapped(eventId, callback, options), options, ...)
        end
    end
    return true
end

-- rule = { label, source, event, wrap = function(original) return replacement end, what }
local function applyWrapHandlers(rule)
    if type(rule.wrap) ~= "function" or type(rule.source) ~= "string" or rule.event == nil then return false end
    if not installRegisterHook() then return false end
    handlerRules[#handlerRules + 1] = {
        label = rule.label, source = rule.source:lower(), event = tostring(rule.event):lower(),
        wrap = rule.wrap, what = rule.what,
    }
    return true
end

-- Event data handed to a throttled handler: reads fall through to the real data, delta is the
-- summed time, and claim / block written by the handler are copied back.
local function throttledData(e, delta)
    local data = setmetatable({ delta = delta }, { __index = e })
    return data
end

local function copyBack(data, e)
    if type(e) ~= "table" then return end
    for _, field in ipairs({ "claim", "block" }) do
        local v = rawget(data, field)
        if v ~= nil then e[field] = v end
    end
end

local function finishThrottled(data, e, ...)
    copyBack(data, e)
    return ...
end

-- rule = { label, source, event, interval = seconds or function() return seconds end }
-- The handler runs at most once per interval, with e.delta = the time summed since its last
-- run (e.delta of the skipped calls, or os.clock when the event has no delta).
local function applyThrottle(rule)
    local function interval()
        local v = rule.interval
        if type(v) == "function" then
            local ok, r = pcall(v)
            v = ok and r or nil
        end
        v = tonumber(v)
        return (v and v > 0) and v or 1
    end
    return applyWrapHandlers({
        label = rule.label, source = rule.source, event = rule.event, what = "throttle",
        wrap = function(original)
            local summed, lastClock = 0, nil
            return function(e, ...)
                local d = type(e) == "table" and tonumber(e.delta) or nil
                if not d then
                    local now = os.clock()
                    d = lastClock and (now - lastClock) or 0
                    lastClock = now
                end
                summed = summed + d
                if summed < interval() then return nil end
                local delta = summed
                summed = 0
                local data = throttledData(e, delta)
                return finishThrottled(data, e, original(data, ...))
            end
        end,
    })
end

-- rule = { label, source, event, when = function(e) return true to skip this call end }
local function applySkipWhen(rule)
    if type(rule.when) ~= "function" then return false end
    return applyWrapHandlers({
        label = rule.label, source = rule.source, event = rule.event, what = rule.what or "guard",
        wrap = function(original)
            return function(e, ...)
                local ok, skip = pcall(rule.when, e)
                if ok and skip == true then return nil end
                return original(e, ...)
            end
        end,
    })
end

--------------------------------------------------------------------------------------------

intercept.wrapHandlers = applyWrapHandlers
intercept.throttle = applyThrottle
intercept.skipWhen = applySkipWhen
intercept.errorToLog = applyErrorToLog
intercept.messageBoxDrop = applyMessageBoxDrop
intercept.calledFrom = calledFrom

return intercept
