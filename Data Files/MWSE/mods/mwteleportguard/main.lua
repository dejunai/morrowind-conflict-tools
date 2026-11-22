--[[mwdialog_luafix 3: F1]] local print, mwse, mwluafix_log = (function(_p, _m) local S = package.loaded["mwluafix_logshim:mwteleportguard"] if type(S) == "table" and S.v == 3 then return S.print, S.mwse, S end S = { v = 3, redirected = 0, dropped = 0, collapsed = 0 } package.loaded["mwluafix_logshim:mwteleportguard"] = S local C = { name = "mwteleportguard", init = 0, after = 0, keep = { "error", "traceback", "exception", "fail", "warn", "stack", "attempt to", "assert", "invalid", "%.lua:%d+:", "^lua:", "initializ", "register", "start", "loaded", "ready", "version", "active" }, perSecond = 25, maxBytes = 2097152, keepOld = 1, flushSeconds = 2.0, errorRepeat = 0 } local G, MARK = _G, "mwdialog_luafix" local find, lower, sub, gsub, concat, fmt, date, select, tostring, pcall = string.find, string.lower, string.sub, string.gsub, table.concat, string.format, os.date, select, tostring, pcall local dir = "Data Files\\MWSE\\logs" local path, oldPath = dir .. "\\" .. C.name .. ".log", dir .. "\\" .. C.name .. ".old.log" local t0 = os.time() - math.floor(os.clock()) - 1 local init, run, started, redirected, f, dead, busy, fails = 0, 0, false, false, nil, false, false, 0 local bytes, dirty, last, lastN, sec, secN, dropped, errs, errKeys = 0, false, nil, 0, -1, 0, 0, {}, 0 local function isErr(t) local l = lower(#t > 4096 and sub(t, 1, 4096) or t) for i = 1, #C.keep do local ok, h = pcall(find, l, C.keep[i]) if ok and h then return true end end return false end local function out(s) f:write(date("[%H:%M:%S] "), s, "\n") bytes = bytes + #s + 12 dirty = true end local function pending() if lastN > 0 then out("[previous line repeated " .. lastN .. " more time(s)]") lastN = 0 end if dropped > 0 then out("[" .. dropped .. " line(s) dropped: more than " .. C.perSecond .. " in one second]") dropped = 0 end end local function flushAll() if f then pending() if dirty then dirty = false f:flush() end end end local function rotate() if f then pcall(f.close, f) f = nil end if C.keepOld > 0 then os.remove(oldPath) os.rename(path, oldPath) else os.remove(path) end f = io.open(path, "w") bytes, last = 0, nil if f then pcall(f.setvbuf, f, "full", 16384) f:write(date("[%Y-%m-%d %H:%M:%S] "), C.name, ": lines past its MWSE.log allowance (", MARK, ")\n") end return f end local function open() pcall(function() lfs.mkdir(dir) end) local ok, m = pcall(function() return lfs.attributes(path, "modification") end) if ok and type(m) == "number" and m >= t0 then path, oldPath = dir .. "\\" .. C.name .. ".luafix.log", dir .. "\\" .. C.name .. ".luafix.old.log" end return rotate() end local function toFile(t) if t == last then lastN = lastN + 1 S.collapsed = S.collapsed + 1 return end local s = os.time() if s ~= sec then sec, secN = s, 0 end secN = secN + 1 if C.perSecond > 0 and secN > C.perSecond then dropped = dropped + 1 S.dropped = S.dropped + 1 return end if bytes >= C.maxBytes and not rotate() then dead = true return end pending() last = t out(t) S.redirected = S.redirected + 1 if not started then dirty = false f:flush() end end S.start = function() if started then return end started = true pcall(flushAll) pcall(function() timer.start({ type = timer.real, duration = C.flushSeconds, iterations = -1, persist = false, callback = function() pcall(flushAll) end }) end) end local function route(t, force) if not started then local ok, v = pcall(function() return tes3.isInitialized() end) if ok and v then S.start() end end if force or isErr(t) then if C.errorRepeat > 0 then local k = gsub(sub(t, 1, (find(t, "\n", 1, true) or 201) - 1), "%d+", "#") local n = errs[k] or 0 if n == 0 then if errKeys >= 500 then errs, errKeys = {}, 0 end errKeys = errKeys + 1 end errs[k] = n + 1 if n >= C.errorRepeat then if f then toFile(t) end return false end end if not f and not dead then open() end if f then pending() out(t) dirty = false f:flush() end return true end local _, nl = gsub(t, "\n", "") nl = nl + 1 if not redirected then if started then if run + nl <= C.after then run = run + nl return true end elseif init + nl <= C.init then init = init + nl return true end redirected = true if not f and not open() then dead = true _p(fmt("[%s] %s writes a lot to MWSE.log, but %s can't be opened: leaving it here", MARK, C.name, path)) return true end _p(fmt("[%s] %s has written %d line(s) to MWSE.log; its further output goes to %s (errors still show here)", MARK, C.name, init + run, path)) end if dead or not f then return true end toFile(t) return false end local function fail(e) fails = fails + 1 if fails >= 10 then dead = true end if fails == 1 then pcall(_p, fmt("[%s] %s: log shim error (the line went to MWSE.log): %s", MARK, C.name, tostring(e))) end end local function decidePrint(n, ...) local t if n <= 1 then t = tostring((...)) else local parts = {} for i = 1, n do parts[i] = tostring((select(i, ...))) end t = concat(parts, "\t") end return route(t, false) end S.print = function(...) if busy or dead then return _p(...) end busy = true local ok, pass = pcall(decidePrint, select("#", ...), ...) busy = false if not ok then fail(pass) return _p(...) end if pass then return _p(...) end end local function decideLog(f0, ...) local ok, t = pcall(fmt, tostring(f0), ...) if not ok then t = tostring(f0) end return route(t, false) end S.mwse = setmetatable({ log = function(f0, ...) if busy or dead then return _m.log(f0, ...) end busy = true local ok, pass = pcall(decideLog, f0, ...) busy = false if not ok then fail(pass) pass = true end if pass then return _m.log(f0, ...) end end }, { __index = _m, __newindex = _m }) local function back(g, ok, ...) if G.print == S.print then G.print = g end if not ok then error((...), 0) end return ... end local wrapped = setmetatable({}, { __mode = "k" }) local LV = { trace = 5, debug = 4, info = 3 } local function wrap(lg) for name, lv in pairs(LV) do local orig = lg[name] if type(orig) == "function" then rawset(lg, name, function(self, ...) if dead or self ~= lg or G.print == S.print then return orig(self, ...) end local sd = type(lg.makeRecord) == "function" and type(lg.writeRecord) == "function" and lg.sharedData if sd and type(sd.level) == "number" then if sd.level < lv then return end local rec = lg:makeRecord(lv) local g = G.print G.print = S.print return back(g, pcall(lg.writeRecord, lg, rec, ...)) end local g = G.print G.print = S.print return back(g, pcall(orig, self, ...)) end) end end end S.wrap = function(lg) if type(lg) == "table" and not wrapped[lg] then wrapped[lg] = true pcall(wrap, lg) end return lg end S.flush = flushAll S.stats = function() return { init = init, run = run, redirected = redirected, dead = dead, path = path, fails = fails, started = started } end pcall(function() event.register("initialized", S.start) for _, ev in ipairs({ "loaded", "save", "menuEnter" }) do event.register(ev, function() pcall(flushAll) end) end end) pcall(function() local p = newproxy(true) getmetatable(p).__gc = function() pcall(flushAll) end S.gc = p end) return S.print, S.mwse, S end)(print, mwse) --[[/mwluafix_logshim]] --[[
    mwteleportguard - Mod-Agnostic Safe Dialogue Teleportation Suite Tool
    
    In Morrowind, authors sometimes script `Player->PositionCell` directly inside dialogue result
    scripts. Teleporting the player while the dialogue menu (`MenuDialog`) is still active causes
    severe engine issues: camera lockups, dialogue UI freezes, actor pointer corruption, companion
    abandonment, and crashes to desktop.

    mwteleportguard is completely mod-agnostic. It detects any script attempting to teleport the player
    during an active dialogue conversation, executes any accompanying quest updates (journal, items,
    variables) immediately, defers the physical cell transition until the dialogue window cleanly closes,
    and teleports the player along with their companions accompanied by a smooth visual fade.
]]

local config = require("mwteleportguard.config")

local pendingTeleport = nil

local function logMsg(fmt, ...)
    if config.logToMWSE then
        mwse.log("[mwteleportguard] " .. string.format(fmt, ...))
    end
end

--- Parses PositionCell from a legacy script command string.
--- Returns parsed table and the remaining script command string without the teleport.
local function extractTeleport(cmd)
    if not cmd or cmd == "" then
        return nil, cmd
    end
    -- a conditional teleport ("if ... PositionCell ... endif") must stay in the script: run here, it would
    -- happen every time. Comments (after ;) don't count.
    local code = cmd:gsub(";[^\r\n]*", ""):lower()
    for _, word in ipairs({ "if", "elseif", "else", "while" }) do
        if code:find("%f[%w]" .. word .. "%f[%W]") then
            return nil, cmd
        end
    end

    local pattern = "[Pp][Ll][Aa][Yy][Ee][Rr]%s*->%s*[Pp][Oo][Ss][Ii][Tt][Ii][Oo][Nn][Cc][Ee][Ll][Ll]%s+([%-%d%.]+)[%s,]+([%-%d%.]+)[%s,]+([%-%d%.]+)[%s,]+([%-%d%.]+)[%s,]+([^\r\n;]+)"
    local x, y, z, rot, rawCell = string.match(cmd, pattern)

    if not (x and y and z and rot and rawCell) then
        return nil, cmd
    end

    -- Clean cell name: strip quotes and leading/trailing whitespace
    local cleanCell = rawCell:match("^%s*[\"]?([^\"\r\n;]+)[\"]?%s*$") or rawCell:gsub("[\"]", ""):match("^%s*(.-)%s*$")

    local tp = {
        x = tonumber(x) or 0,
        y = tonumber(y) or 0,
        z = tonumber(z) or 0,
        rot = tonumber(rot) or 0,
        cell = cleanCell,
    }

    -- Remove the PositionCell line from the command string so the rest can run immediately
    local remaining = cmd:gsub(pattern, ""):gsub("^%s+", ""):gsub("%s+$", "")

    return tp, remaining
end

local function executePendingTeleport()
    if not pendingTeleport then
        return
    end

    local tp = pendingTeleport
    pendingTeleport = nil

    logMsg("Dialogue window closed. Executing deferred teleport to '%s' (pos: %0.1f, %0.1f, %0.1f; rot: %0.1f)",
        tp.cell, tp.x, tp.y, tp.z, tp.rot)

    timer.frame.delayOneFrame(function()
        local duration = config.fadeTransition and math.max(0, config.fadeDuration or 0.5) or 0

        if duration > 0 then
            tes3.fadeOut({ duration = duration })
        end

        local function teleport()
            local rotZ = math.rad((tp.rot or 0) % 360)
            tes3.positionCell({
                reference = tes3.player,
                cell = tp.cell,
                position = tes3vector3.new(tp.x, tp.y, tp.z),
                orientation = tes3vector3.new(0, 0, rotZ),
                teleportCompanions = config.teleportCompanions,
            })

            if duration > 0 then
                tes3.fadeIn({ duration = duration })
            end
        end

        if duration > 0 then
            timer.start({ type = timer.simulate, duration = duration, callback = teleport })
        else
            timer.delayOneFrame(teleport, timer.simulate)   -- no fade: the shortest wait there is (a timer of 0 never fires)
        end
    end)
end

--- @param e infoResponseEventData
local function onInfoResponse(e)
    if not config.enabled then
        return
    end

    local dialogMenu = tes3ui.findMenu("MenuDialog")
    if not dialogMenu then
        return
    end

    local tp, remainingCmds = extractTeleport(e.command)
    if not tp then
        return
    end

    local actor = e.reference
    local actorName = (actor and actor.object and actor.object.name) or (actor and actor.id) or "Unknown Speaker"

    logMsg("Intercepted Player->PositionCell during dialogue with '%s' to '%s'. Deferring until dialogue exit.",
        actorName, tp.cell)

    -- If the dialogue script had other commands (Journal updates, AddItem, Set, etc.),
    -- run them immediately so quest progress is never lost
    if remainingCmds and remainingCmds:match("%S") then
        logMsg("Executing non-teleport dialogue commands immediately: %s", remainingCmds:gsub("[\r\n]+", " "))
        tes3.runLegacyScript({
            command = remainingCmds,
            reference = actor or tes3.player,
        })
    end

    -- Force dialogue session into Goodbye mode so the player can conclude the dialogue cleanly
    if config.forceGoodbye then
        tes3.runLegacyScript({ command = "goodbye", reference = actor or tes3.player })
    end

    -- Store pending teleport and block the original engine execution
    pendingTeleport = tp
    e.block = true
end

local function onMenuDialogActivated(e)
    e.element:register(tes3.uiEvent.destroy, function()
        executePendingTeleport()
    end)
end

local function onMenuExit(e)
    if pendingTeleport then
        executePendingTeleport()
    end
end

local function onInitialized()
    event.register(tes3.event.infoResponse, onInfoResponse)
    event.register(tes3.event.uiActivated, onMenuDialogActivated, { filter = "MenuDialog" })
    event.register(tes3.event.menuExit, onMenuExit)
    event.register(tes3.event.loaded, function()
        pendingTeleport = nil
    end)

    mwse.log("[mwteleportguard] Initialized mod-agnostic dialogue teleport protection.")
end

event.register(tes3.event.initialized, onInitialized)

event.register(tes3.event.modConfigReady, function()
    require("mwteleportguard.mcm")
end)
