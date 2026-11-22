--[[mwdialog_luafix 3: F1]] local print, mwse, mwluafix_log = (function(_p, _m) local S = package.loaded["mwluafix_logshim:mweffectinspector"] if type(S) == "table" and S.v == 3 then return S.print, S.mwse, S end S = { v = 3, redirected = 0, dropped = 0, collapsed = 0 } package.loaded["mwluafix_logshim:mweffectinspector"] = S local C = { name = "mweffectinspector", init = 0, after = 0, keep = { "error", "traceback", "exception", "fail", "warn", "stack", "attempt to", "assert", "invalid", "%.lua:%d+:", "^lua:", "initializ", "register", "start", "loaded", "ready", "version", "active" }, perSecond = 25, maxBytes = 2097152, keepOld = 1, flushSeconds = 2.0, errorRepeat = 0 } local G, MARK = _G, "mwdialog_luafix" local find, lower, sub, gsub, concat, fmt, date, select, tostring, pcall = string.find, string.lower, string.sub, string.gsub, table.concat, string.format, os.date, select, tostring, pcall local dir = "Data Files\\MWSE\\logs" local path, oldPath = dir .. "\\" .. C.name .. ".log", dir .. "\\" .. C.name .. ".old.log" local t0 = os.time() - math.floor(os.clock()) - 1 local init, run, started, redirected, f, dead, busy, fails = 0, 0, false, false, nil, false, false, 0 local bytes, dirty, last, lastN, sec, secN, dropped, errs, errKeys = 0, false, nil, 0, -1, 0, 0, {}, 0 local function isErr(t) local l = lower(#t > 4096 and sub(t, 1, 4096) or t) for i = 1, #C.keep do local ok, h = pcall(find, l, C.keep[i]) if ok and h then return true end end return false end local function out(s) f:write(date("[%H:%M:%S] "), s, "\n") bytes = bytes + #s + 12 dirty = true end local function pending() if lastN > 0 then out("[previous line repeated " .. lastN .. " more time(s)]") lastN = 0 end if dropped > 0 then out("[" .. dropped .. " line(s) dropped: more than " .. C.perSecond .. " in one second]") dropped = 0 end end local function flushAll() if f then pending() if dirty then dirty = false f:flush() end end end local function rotate() if f then pcall(f.close, f) f = nil end if C.keepOld > 0 then os.remove(oldPath) os.rename(path, oldPath) else os.remove(path) end f = io.open(path, "w") bytes, last = 0, nil if f then pcall(f.setvbuf, f, "full", 16384) f:write(date("[%Y-%m-%d %H:%M:%S] "), C.name, ": lines past its MWSE.log allowance (", MARK, ")\n") end return f end local function open() pcall(function() lfs.mkdir(dir) end) local ok, m = pcall(function() return lfs.attributes(path, "modification") end) if ok and type(m) == "number" and m >= t0 then path, oldPath = dir .. "\\" .. C.name .. ".luafix.log", dir .. "\\" .. C.name .. ".luafix.old.log" end return rotate() end local function toFile(t) if t == last then lastN = lastN + 1 S.collapsed = S.collapsed + 1 return end local s = os.time() if s ~= sec then sec, secN = s, 0 end secN = secN + 1 if C.perSecond > 0 and secN > C.perSecond then dropped = dropped + 1 S.dropped = S.dropped + 1 return end if bytes >= C.maxBytes and not rotate() then dead = true return end pending() last = t out(t) S.redirected = S.redirected + 1 if not started then dirty = false f:flush() end end S.start = function() if started then return end started = true pcall(flushAll) pcall(function() timer.start({ type = timer.real, duration = C.flushSeconds, iterations = -1, persist = false, callback = function() pcall(flushAll) end }) end) end local function route(t, force) if not started then local ok, v = pcall(function() return tes3.isInitialized() end) if ok and v then S.start() end end if force or isErr(t) then if C.errorRepeat > 0 then local k = gsub(sub(t, 1, (find(t, "\n", 1, true) or 201) - 1), "%d+", "#") local n = errs[k] or 0 if n == 0 then if errKeys >= 500 then errs, errKeys = {}, 0 end errKeys = errKeys + 1 end errs[k] = n + 1 if n >= C.errorRepeat then if f then toFile(t) end return false end end if not f and not dead then open() end if f then pending() out(t) dirty = false f:flush() end return true end local _, nl = gsub(t, "\n", "") nl = nl + 1 if not redirected then if started then if run + nl <= C.after then run = run + nl return true end elseif init + nl <= C.init then init = init + nl return true end redirected = true if not f and not open() then dead = true _p(fmt("[%s] %s writes a lot to MWSE.log, but %s can't be opened: leaving it here", MARK, C.name, path)) return true end _p(fmt("[%s] %s has written %d line(s) to MWSE.log; its further output goes to %s (errors still show here)", MARK, C.name, init + run, path)) end if dead or not f then return true end toFile(t) return false end local function fail(e) fails = fails + 1 if fails >= 10 then dead = true end if fails == 1 then pcall(_p, fmt("[%s] %s: log shim error (the line went to MWSE.log): %s", MARK, C.name, tostring(e))) end end local function decidePrint(n, ...) local t if n <= 1 then t = tostring((...)) else local parts = {} for i = 1, n do parts[i] = tostring((select(i, ...))) end t = concat(parts, "\t") end return route(t, false) end S.print = function(...) if busy or dead then return _p(...) end busy = true local ok, pass = pcall(decidePrint, select("#", ...), ...) busy = false if not ok then fail(pass) return _p(...) end if pass then return _p(...) end end local function decideLog(f0, ...) local ok, t = pcall(fmt, tostring(f0), ...) if not ok then t = tostring(f0) end return route(t, false) end S.mwse = setmetatable({ log = function(f0, ...) if busy or dead then return _m.log(f0, ...) end busy = true local ok, pass = pcall(decideLog, f0, ...) busy = false if not ok then fail(pass) pass = true end if pass then return _m.log(f0, ...) end end }, { __index = _m, __newindex = _m }) local function back(g, ok, ...) if G.print == S.print then G.print = g end if not ok then error((...), 0) end return ... end local wrapped = setmetatable({}, { __mode = "k" }) local LV = { trace = 5, debug = 4, info = 3 } local function wrap(lg) for name, lv in pairs(LV) do local orig = lg[name] if type(orig) == "function" then rawset(lg, name, function(self, ...) if dead or self ~= lg or G.print == S.print then return orig(self, ...) end local sd = type(lg.makeRecord) == "function" and type(lg.writeRecord) == "function" and lg.sharedData if sd and type(sd.level) == "number" then if sd.level < lv then return end local rec = lg:makeRecord(lv) local g = G.print G.print = S.print return back(g, pcall(lg.writeRecord, lg, rec, ...)) end local g = G.print G.print = S.print return back(g, pcall(orig, self, ...)) end) end end end S.wrap = function(lg) if type(lg) == "table" and not wrapped[lg] then wrapped[lg] = true pcall(wrap, lg) end return lg end S.flush = flushAll S.stats = function() return { init = init, run = run, redirected = redirected, dead = dead, path = path, fails = fails, started = started } end pcall(function() event.register("initialized", S.start) for _, ev in ipairs({ "loaded", "save", "menuEnter" }) do event.register(ev, function() pcall(flushAll) end) end end) pcall(function() local p = newproxy(true) getmetatable(p).__gc = function() pcall(flushAll) end S.gc = p end) return S.print, S.mwse, S end)(print, mwse) --[[/mwluafix_logshim]] local config = require("mweffectinspector.config")
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
