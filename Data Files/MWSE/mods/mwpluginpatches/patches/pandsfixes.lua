--[[mwdialog_luafix 3: F1]] local print, mwse, mwluafix_log = (function(_p, _m) local S = package.loaded["mwluafix_logshim:mwpluginpatches"] if type(S) == "table" and S.v == 3 then return S.print, S.mwse, S end S = { v = 3, redirected = 0, dropped = 0, collapsed = 0 } package.loaded["mwluafix_logshim:mwpluginpatches"] = S local C = { name = "mwpluginpatches", init = 0, after = 0, keep = { "error", "traceback", "exception", "fail", "warn", "stack", "attempt to", "assert", "invalid", "%.lua:%d+:", "^lua:", "initializ", "register", "start", "loaded", "ready", "version", "active" }, perSecond = 25, maxBytes = 2097152, keepOld = 1, flushSeconds = 2.0, errorRepeat = 0 } local G, MARK = _G, "mwdialog_luafix" local find, lower, sub, gsub, concat, fmt, date, select, tostring, pcall = string.find, string.lower, string.sub, string.gsub, table.concat, string.format, os.date, select, tostring, pcall local dir = "Data Files\\MWSE\\logs" local path, oldPath = dir .. "\\" .. C.name .. ".log", dir .. "\\" .. C.name .. ".old.log" local t0 = os.time() - math.floor(os.clock()) - 1 local init, run, started, redirected, f, dead, busy, fails = 0, 0, false, false, nil, false, false, 0 local bytes, dirty, last, lastN, sec, secN, dropped, errs, errKeys = 0, false, nil, 0, -1, 0, 0, {}, 0 local function isErr(t) local l = lower(#t > 4096 and sub(t, 1, 4096) or t) for i = 1, #C.keep do local ok, h = pcall(find, l, C.keep[i]) if ok and h then return true end end return false end local function out(s) f:write(date("[%H:%M:%S] "), s, "\n") bytes = bytes + #s + 12 dirty = true end local function pending() if lastN > 0 then out("[previous line repeated " .. lastN .. " more time(s)]") lastN = 0 end if dropped > 0 then out("[" .. dropped .. " line(s) dropped: more than " .. C.perSecond .. " in one second]") dropped = 0 end end local function flushAll() if f then pending() if dirty then dirty = false f:flush() end end end local function rotate() if f then pcall(f.close, f) f = nil end if C.keepOld > 0 then os.remove(oldPath) os.rename(path, oldPath) else os.remove(path) end f = io.open(path, "w") bytes, last = 0, nil if f then pcall(f.setvbuf, f, "full", 16384) f:write(date("[%Y-%m-%d %H:%M:%S] "), C.name, ": lines past its MWSE.log allowance (", MARK, ")\n") end return f end local function open() pcall(function() lfs.mkdir(dir) end) local ok, m = pcall(function() return lfs.attributes(path, "modification") end) if ok and type(m) == "number" and m >= t0 then path, oldPath = dir .. "\\" .. C.name .. ".luafix.log", dir .. "\\" .. C.name .. ".luafix.old.log" end return rotate() end local function toFile(t) if t == last then lastN = lastN + 1 S.collapsed = S.collapsed + 1 return end local s = os.time() if s ~= sec then sec, secN = s, 0 end secN = secN + 1 if C.perSecond > 0 and secN > C.perSecond then dropped = dropped + 1 S.dropped = S.dropped + 1 return end if bytes >= C.maxBytes and not rotate() then dead = true return end pending() last = t out(t) S.redirected = S.redirected + 1 if not started then dirty = false f:flush() end end S.start = function() if started then return end started = true pcall(flushAll) pcall(function() timer.start({ type = timer.real, duration = C.flushSeconds, iterations = -1, persist = false, callback = function() pcall(flushAll) end }) end) end local function route(t, force) if not started then local ok, v = pcall(function() return tes3.isInitialized() end) if ok and v then S.start() end end if force or isErr(t) then if C.errorRepeat > 0 then local k = gsub(sub(t, 1, (find(t, "\n", 1, true) or 201) - 1), "%d+", "#") local n = errs[k] or 0 if n == 0 then if errKeys >= 500 then errs, errKeys = {}, 0 end errKeys = errKeys + 1 end errs[k] = n + 1 if n >= C.errorRepeat then if f then toFile(t) end return false end end if not f and not dead then open() end if f then pending() out(t) dirty = false f:flush() end return true end local _, nl = gsub(t, "\n", "") nl = nl + 1 if not redirected then if started then if run + nl <= C.after then run = run + nl return true end elseif init + nl <= C.init then init = init + nl return true end redirected = true if not f and not open() then dead = true _p(fmt("[%s] %s writes a lot to MWSE.log, but %s can't be opened: leaving it here", MARK, C.name, path)) return true end _p(fmt("[%s] %s has written %d line(s) to MWSE.log; its further output goes to %s (errors still show here)", MARK, C.name, init + run, path)) end if dead or not f then return true end toFile(t) return false end local function fail(e) fails = fails + 1 if fails >= 10 then dead = true end if fails == 1 then pcall(_p, fmt("[%s] %s: log shim error (the line went to MWSE.log): %s", MARK, C.name, tostring(e))) end end local function decidePrint(n, ...) local t if n <= 1 then t = tostring((...)) else local parts = {} for i = 1, n do parts[i] = tostring((select(i, ...))) end t = concat(parts, "\t") end return route(t, false) end S.print = function(...) if busy or dead then return _p(...) end busy = true local ok, pass = pcall(decidePrint, select("#", ...), ...) busy = false if not ok then fail(pass) return _p(...) end if pass then return _p(...) end end local function decideLog(f0, ...) local ok, t = pcall(fmt, tostring(f0), ...) if not ok then t = tostring(f0) end return route(t, false) end S.mwse = setmetatable({ log = function(f0, ...) if busy or dead then return _m.log(f0, ...) end busy = true local ok, pass = pcall(decideLog, f0, ...) busy = false if not ok then fail(pass) pass = true end if pass then return _m.log(f0, ...) end end }, { __index = _m, __newindex = _m }) local function back(g, ok, ...) if G.print == S.print then G.print = g end if not ok then error((...), 0) end return ... end local wrapped = setmetatable({}, { __mode = "k" }) local LV = { trace = 5, debug = 4, info = 3 } local function wrap(lg) for name, lv in pairs(LV) do local orig = lg[name] if type(orig) == "function" then rawset(lg, name, function(self, ...) if dead or self ~= lg or G.print == S.print then return orig(self, ...) end local sd = type(lg.makeRecord) == "function" and type(lg.writeRecord) == "function" and lg.sharedData if sd and type(sd.level) == "number" then if sd.level < lv then return end local rec = lg:makeRecord(lv) local g = G.print G.print = S.print return back(g, pcall(lg.writeRecord, lg, rec, ...)) end local g = G.print G.print = S.print return back(g, pcall(orig, self, ...)) end) end end end S.wrap = function(lg) if type(lg) == "table" and not wrapped[lg] then wrapped[lg] = true pcall(wrap, lg) end return lg end S.flush = flushAll S.stats = function() return { init = init, run = run, redirected = redirected, dead = dead, path = path, fails = fails, started = started } end pcall(function() event.register("initialized", S.start) for _, ev in ipairs({ "loaded", "save", "menuEnter" }) do event.register(ev, function() pcall(flushAll) end) end end) pcall(function() local p = newproxy(true) getmetatable(p).__gc = function() pcall(flushAll) end S.gc = p end) return S.print, S.mwse, S end)(print, mwse) --[[/mwluafix_logshim]] local config = require("mwpluginpatches.config")

local pandsfixes = {}

local SCRIPTS = {
    "ABM_ll_DetectPCCrimeScript",
    "ABM_ll_StopIntruderScript",
    "ABM_PutItBackScript",
}

local wasRunning = {}

-- ABM_ll_GuardCallCell: 1 Hlaalu, 2 Redoran, 3 Telvanni, 4 Temple, 5 Imperial (6 Mournhold: P&S's own)
local NAMES = { "Hlaalu", "Redoran", "Telvanni", "Temple", "Imperial" }

-- mesh file names (lower, no folder), vanilla prefixes and the names Tamriel Data / other mods use
local KINDS = {
    { 1, { "^in_h_", "^ex_h_", "hlaalu" } },
    { 2, { "^in_r_", "^ex_r_", "redoran", "redwall" } },
    { 3, { "^in_t_", "^ex_t_", "telvanni", "_tel_" } },
    { 4, { "temple", "ordinator", "_shrine" } },
    { 5, { "^in_imp", "^ex_imp", "imperial", "_imp_", "legion", "fort_", "_fort" } },
    { 0, { "cave", "cavern", "grotto", "mine", "tomb", "crypt", "barrow", "ruin", "dwrv", "dwemer",
           "daedr", "^in_dae", "^ex_dae", "velothi", "stronghold", "sewer", "lava", "ashl", "^in_py", "^in_mold",
           "^in_bone", "^in_mud", "_bm_ice", "ancestral", "burial" } },
}

-- the cell's name says it outright
local CELL_NAMES = {
    { 0, { "cave", "cavern", "grotto", "mine", "tomb", "crypt", "barrow", "ruin", "sewer", "shrine of",
           "daedric", "dwemer", "egg mine", "stronghold", "lair" } },
    { 4, { "temple", "ordinator" } },
    { 5, { "fort ", "legion", "imperial", "garrison", "census", "excise" } },
    { 1, { "hlaalu" } }, { 2, { "redoran" } }, { 3, { "telvanni" } },
}

local detected = {}

local function matches(text, pats)
    for _, p in ipairs(pats) do
        if text:find(p) then return true end
    end
    return false
end

local function countModels(cell, score, near)
    for ref in cell:iterateReferences({ tes3.objectType.static, tes3.objectType.activator, tes3.objectType.door }) do
        local m = ref.object.mesh
        if m and (not near or ref.position:distance(near) < 4096) then
            local base = m:lower():gsub("^.*[\\/]", "")
            for _, k in ipairs(KINDS) do
                if matches(base, k[2]) then
                    score[k[1]] = (score[k[1]] or 0) + 1
                    break
                end
            end
        end
    end
end

-- whose guards for this place: value, how it was decided
local function detectGuards(cell)
    local id = cell.id:lower()
    if detected[id] then return detected[id][1], detected[id][2] end
    local name = (cell.name or cell.id):lower()
    local v, why
    for _, k in ipairs(CELL_NAMES) do
        if matches(name, k[2]) then
            v, why = k[1], "the place's name"
            break
        end
    end
    if not v then
        local score = {}
        if cell.isInterior then
            countModels(cell, score)
        else
            for _, c in pairs(tes3.getActiveCells()) do
                countModels(c, score, tes3.player.position)
            end
        end
        local best, n, clan = 0, 0, 0
        for k = 1, 5 do
            clan = clan + (score[k] or 0)
            if (score[k] or 0) > n then
                best, n = k, score[k]
            end
        end
        if (score[0] or 0) >= 5 and (score[0] or 0) > clan then
            v, why = 0, string.format("%d cave/tomb/ruin meshes", score[0])
        elseif n >= 5 then
            v, why = best, string.format("%d %s meshes", n, NAMES[best])
        elseif cell.isInterior then
            v, why = 5, "an interior not recognised (default)"
        else
            v, why = 0, "an exterior not recognised (default)"
        end
    end
    detected[id] = { v, why }
    return v, why
end

local function global(id)
    return tes3.findGlobal(id)
end

local function guardNearby()
    for _, cell in pairs(tes3.getActiveCells()) do
        for ref in cell:iterateReferences(tes3.objectType.npc) do
            local id = ref.baseObject.id:lower()
            if id:find("^abm_thguard") and not ref.disabled and not ref.deleted then
                return true
            end
        end
    end
    return false
end

local function fadeBackIn()
    local f = tes3.worldController.transitionFader
    if f and f.value and f.value > 0.05 then
        tes3.fadeIn({ fader = f, duration = 0.3 })
        return true
    end
    return false
end

local function check()
    local callCell = global("ABM_ll_GuardCallCell")
    if not callCell then return end
    for _, name in ipairs(SCRIPTS) do
        local running = tes3.getLegacyScriptRunning({ script = name })
        if running and callCell.value == 0 and tes3.player and tes3.player.cell then
            local v, why = detectGuards(tes3.player.cell)
            if v > 0 then
                callCell.value = v
                mwse.log("[mwpluginpatches] %s: %s guards (%s)", tes3.player.cell.id, NAMES[v], why)
            end
        end
        if running and callCell.value == 0 then
            -- no guards for this place: don't let it fade out
            tes3.stopLegacyScript({ script = name })
            local putBack = global("ABM_PutItBack")
            if putBack and putBack.value ~= 3 then putBack.value = 0 end
            running = false
            mwse.log("[mwpluginpatches] stopped %s (no guards for %s)", name,
                tes3.player and tes3.player.cell.id or "?")
            timer.start({
                type = timer.real,
                duration = 0.5,
                callback = function()
                    if not guardNearby() then fadeBackIn() end
                end
            })
        elseif wasRunning[name] and not running then
            -- script finished: a guard should be here; if left faded out, recover
            timer.start({
                type = timer.real,
                duration = 1.0,
                callback = function()
                    if not guardNearby() and fadeBackIn() then
                        mwse.log("[mwpluginpatches] %s ended with no guard; fading in", name)
                    end
                end
            })
        end
        wasRunning[name] = running
    end
end

local function onInfoFilter(e)
    if e.dialogue and e.dialogue.id then
        local id = e.dialogue.id:lower()
        if id:find("%(target%)") then
            local topicVal = tes3.getGlobal("ABM_Topic") or 0
            local targetVal = tes3.getGlobal("ABM_TargetGlobal") or 0
            if topicVal <= 0 and targetVal <= 0 then
                e.passes = false
                return false
            end
            -- Must be speaking to a P&S companion/guard if target selection is not active
            local ref = e.reference
            if ref and targetVal <= 0 then
                local obj = ref.object.baseObject or ref.object
                local sId = (obj.script and obj.script.id or ""):lower()
                local oId = (obj.id or ""):lower()
                if not (sId:find("abm_") or sId:find("companion") or oId:find("abm_")) then
                    e.passes = false
                    return false
                end
            end
        end
    end
end

function pandsfixes.init()
    if not config.pAndSFixesEnabled or not config.isPAndSActive() then
        return
    end

    -- MWSE cancels every timer just before `loaded`, so it is started again there
    local function startCheck()
        timer.start({
            type = timer.real,
            duration = 0.35,
            iterations = -1,
            persist = false,
            callback = function()
                if tes3.player then check() end
            end
        })
    end
    startCheck()

    event.register(tes3.event.loaded, function()
        wasRunning = {}
        startCheck()
    end)

    event.register(tes3.event.infoFilter, onInfoFilter)

    mwse.log("[mwpluginpatches] Privileges & Services guard call, fade, and target-topic filter active.")
end

return pandsfixes
