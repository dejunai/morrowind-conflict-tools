--[[mwdialog_luafix 3: F1]] local print, mwse, mwluafix_log = (function(_p, _m) local S = package.loaded["mwluafix_logshim:mwpluginpatches"] if type(S) == "table" and S.v == 3 then return S.print, S.mwse, S end S = { v = 3, redirected = 0, dropped = 0, collapsed = 0 } package.loaded["mwluafix_logshim:mwpluginpatches"] = S local C = { name = "mwpluginpatches", init = 0, after = 0, keep = { "error", "traceback", "exception", "fail", "warn", "stack", "attempt to", "assert", "invalid", "%.lua:%d+:", "^lua:", "initializ", "register", "start", "loaded", "ready", "version", "active" }, perSecond = 25, maxBytes = 2097152, keepOld = 1, flushSeconds = 2.0, errorRepeat = 0 } local G, MARK = _G, "mwdialog_luafix" local find, lower, sub, gsub, concat, fmt, date, select, tostring, pcall = string.find, string.lower, string.sub, string.gsub, table.concat, string.format, os.date, select, tostring, pcall local dir = "Data Files\\MWSE\\logs" local path, oldPath = dir .. "\\" .. C.name .. ".log", dir .. "\\" .. C.name .. ".old.log" local t0 = os.time() - math.floor(os.clock()) - 1 local init, run, started, redirected, f, dead, busy, fails = 0, 0, false, false, nil, false, false, 0 local bytes, dirty, last, lastN, sec, secN, dropped, errs, errKeys = 0, false, nil, 0, -1, 0, 0, {}, 0 local function isErr(t) local l = lower(#t > 4096 and sub(t, 1, 4096) or t) for i = 1, #C.keep do local ok, h = pcall(find, l, C.keep[i]) if ok and h then return true end end return false end local function out(s) f:write(date("[%H:%M:%S] "), s, "\n") bytes = bytes + #s + 12 dirty = true end local function pending() if lastN > 0 then out("[previous line repeated " .. lastN .. " more time(s)]") lastN = 0 end if dropped > 0 then out("[" .. dropped .. " line(s) dropped: more than " .. C.perSecond .. " in one second]") dropped = 0 end end local function flushAll() if f then pending() if dirty then dirty = false f:flush() end end end local function rotate() if f then pcall(f.close, f) f = nil end if C.keepOld > 0 then os.remove(oldPath) os.rename(path, oldPath) else os.remove(path) end f = io.open(path, "w") bytes, last = 0, nil if f then pcall(f.setvbuf, f, "full", 16384) f:write(date("[%Y-%m-%d %H:%M:%S] "), C.name, ": lines past its MWSE.log allowance (", MARK, ")\n") end return f end local function open() pcall(function() lfs.mkdir(dir) end) local ok, m = pcall(function() return lfs.attributes(path, "modification") end) if ok and type(m) == "number" and m >= t0 then path, oldPath = dir .. "\\" .. C.name .. ".luafix.log", dir .. "\\" .. C.name .. ".luafix.old.log" end return rotate() end local function toFile(t) if t == last then lastN = lastN + 1 S.collapsed = S.collapsed + 1 return end local s = os.time() if s ~= sec then sec, secN = s, 0 end secN = secN + 1 if C.perSecond > 0 and secN > C.perSecond then dropped = dropped + 1 S.dropped = S.dropped + 1 return end if bytes >= C.maxBytes and not rotate() then dead = true return end pending() last = t out(t) S.redirected = S.redirected + 1 if not started then dirty = false f:flush() end end S.start = function() if started then return end started = true pcall(flushAll) pcall(function() timer.start({ type = timer.real, duration = C.flushSeconds, iterations = -1, persist = false, callback = function() pcall(flushAll) end }) end) end local function route(t, force) if not started then local ok, v = pcall(function() return tes3.isInitialized() end) if ok and v then S.start() end end if force or isErr(t) then if C.errorRepeat > 0 then local k = gsub(sub(t, 1, (find(t, "\n", 1, true) or 201) - 1), "%d+", "#") local n = errs[k] or 0 if n == 0 then if errKeys >= 500 then errs, errKeys = {}, 0 end errKeys = errKeys + 1 end errs[k] = n + 1 if n >= C.errorRepeat then if f then toFile(t) end return false end end if not f and not dead then open() end if f then pending() out(t) dirty = false f:flush() end return true end local _, nl = gsub(t, "\n", "") nl = nl + 1 if not redirected then if started then if run + nl <= C.after then run = run + nl return true end elseif init + nl <= C.init then init = init + nl return true end redirected = true if not f and not open() then dead = true _p(fmt("[%s] %s writes a lot to MWSE.log, but %s can't be opened: leaving it here", MARK, C.name, path)) return true end _p(fmt("[%s] %s has written %d line(s) to MWSE.log; its further output goes to %s (errors still show here)", MARK, C.name, init + run, path)) end if dead or not f then return true end toFile(t) return false end local function fail(e) fails = fails + 1 if fails >= 10 then dead = true end if fails == 1 then pcall(_p, fmt("[%s] %s: log shim error (the line went to MWSE.log): %s", MARK, C.name, tostring(e))) end end local function decidePrint(n, ...) local t if n <= 1 then t = tostring((...)) else local parts = {} for i = 1, n do parts[i] = tostring((select(i, ...))) end t = concat(parts, "\t") end return route(t, false) end S.print = function(...) if busy or dead then return _p(...) end busy = true local ok, pass = pcall(decidePrint, select("#", ...), ...) busy = false if not ok then fail(pass) return _p(...) end if pass then return _p(...) end end local function decideLog(f0, ...) local ok, t = pcall(fmt, tostring(f0), ...) if not ok then t = tostring(f0) end return route(t, false) end S.mwse = setmetatable({ log = function(f0, ...) if busy or dead then return _m.log(f0, ...) end busy = true local ok, pass = pcall(decideLog, f0, ...) busy = false if not ok then fail(pass) pass = true end if pass then return _m.log(f0, ...) end end }, { __index = _m, __newindex = _m }) local function back(g, ok, ...) if G.print == S.print then G.print = g end if not ok then error((...), 0) end return ... end local wrapped = setmetatable({}, { __mode = "k" }) local LV = { trace = 5, debug = 4, info = 3 } local function wrap(lg) for name, lv in pairs(LV) do local orig = lg[name] if type(orig) == "function" then rawset(lg, name, function(self, ...) if dead or self ~= lg or G.print == S.print then return orig(self, ...) end local sd = type(lg.makeRecord) == "function" and type(lg.writeRecord) == "function" and lg.sharedData if sd and type(sd.level) == "number" then if sd.level < lv then return end local rec = lg:makeRecord(lv) local g = G.print G.print = S.print return back(g, pcall(lg.writeRecord, lg, rec, ...)) end local g = G.print G.print = S.print return back(g, pcall(orig, self, ...)) end) end end end S.wrap = function(lg) if type(lg) == "table" and not wrapped[lg] then wrapped[lg] = true pcall(wrap, lg) end return lg end S.flush = flushAll S.stats = function() return { init = init, run = run, redirected = redirected, dead = dead, path = path, fails = fails, started = started } end pcall(function() event.register("initialized", S.start) for _, ev in ipairs({ "loaded", "save", "menuEnter" }) do event.register(ev, function() pcall(flushAll) end) end end) pcall(function() local p = newproxy(true) getmetatable(p).__gc = function() pcall(flushAll) end S.gc = p end) return S.print, S.mwse, S end)(print, mwse) --[[/mwluafix_logshim]] local config = require("mwpluginpatches.config")

local jiubDelay = {}

local JIUB_RUMOR_INFO_ID = "1453113367223718194"

local function getPlayerData()
    if not tes3.player then return nil end
    local data = tes3.player.data
    if not data then return nil end
    data.mwpluginpatches_jiub = data.mwpluginpatches_jiub or data.FriendsAndFrensJiub or {
        secondsSinceCensus = 0,
        unlockedLogged = false,
    }
    return data.mwpluginpatches_jiub
end

local function syncJiubAppearance()
    if not config.jiubSyncAppearance then return end

    local vanillaJiub = tes3.getObject("chargen name")
    local compJiub = tes3.getObject("aa_comp_jiub")

    if vanillaJiub and compJiub then
        if compJiub.head ~= vanillaJiub.head or compJiub.hair ~= vanillaJiub.hair then
            compJiub.head = vanillaJiub.head
            compJiub.hair = vanillaJiub.hair
            mwse.log("[mwpluginpatches] Synchronized aa_comp_jiub appearance with chargen name (Head: %s, Hair: %s)",
                vanillaJiub.head and vanillaJiub.head.id or "default",
                vanillaJiub.hair and vanillaJiub.hair.id or "default")
        end
    end
end

local function onSimulate(e)
    if not config.jiubDelayEnabled or not config.isFriendsAndFrensActive() then return end

    -- Check if character generation is complete (journal enabled, Census Office exited)
    local charGenState = tes3.findGlobal("CharGenState")
    if not charGenState or charGenState.value ~= -1 then
        return
    end

    local data = getPlayerData()
    if not data then return end

    data.secondsSinceCensus = (data.secondsSinceCensus or 0) + e.delta

    local requiredSeconds = math.max(0, (config.jiubDelayMinutes or 5) * 60)
    if data.secondsSinceCensus >= requiredSeconds and not data.unlockedLogged then
        data.unlockedLogged = true
        mwse.log("[mwpluginpatches] Post-census delay of %s minutes reached. Jiub companion rumor is now eligible to appear.",
            config.jiubDelayMinutes)
    end
end

local function onInfoFilter(e)
    if not config.jiubDelayEnabled or not config.isFriendsAndFrensActive() then return end
    if not e.passes or not e.info then return end

    local isJiubRumor = (tostring(e.info.id) == JIUB_RUMOR_INFO_ID)
    if not isJiubRumor then return end

    -- 1. Exclude while still in CharGen (before journal / release papers)
    local charGenState = tes3.findGlobal("CharGenState")
    if charGenState and charGenState.value ~= -1 then
        e.passes = false
        return
    end

    -- 2. Exclude NPCs located inside the Census & Excise Office
    if config.jiubExcludeCensusOffice then
        local cell = e.reference and e.reference.cell
        if cell then
            local cellId = cell.id:lower()
            local editorName = cell.editorName and cell.editorName:lower() or ""
            if string.find(cellId, "census and excise") or string.find(editorName, "census and excise") then
                e.passes = false
                return
            end
        end

        local actorId = e.reference and e.reference.object.id:lower() or ""
        if string.find(actorId, "chargen") or actorId == "socucius ergalla" or actorId == "sellus gravius" then
            e.passes = false
            return
        end
    end

    -- 3. Check post-census gameplay timer
    local data = getPlayerData()
    local requiredSeconds = math.max(0, (config.jiubDelayMinutes or 5) * 60)
    if not data or (data.secondsSinceCensus or 0) < requiredSeconds then
        e.passes = false
        return
    end
end

local function onMobileActivated(e)
    if not config.jiubSyncAppearance then return end
    if e.reference and e.reference.object.id:lower() == "aa_comp_jiub" then
        syncJiubAppearance()
    end
end

function jiubDelay.init()
    if not config.jiubDelayEnabled or not config.isFriendsAndFrensActive() then
        return
    end

    syncJiubAppearance()
    event.register(tes3.event.simulate, onSimulate)
    event.register(tes3.event.infoFilter, onInfoFilter)
    event.register(tes3.event.mobileActivated, onMobileActivated)
    event.register(tes3.event.loaded, syncJiubAppearance)

    mwse.log("[mwpluginpatches] Friends & Frens Jiub Companion Delayer patch active.")
end

return jiubDelay
