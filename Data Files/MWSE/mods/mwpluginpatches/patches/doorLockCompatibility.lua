--[[mwdialog_luafix 3: F1]] local print, mwse, mwluafix_log = (function(_p, _m) local S = package.loaded["mwluafix_logshim:mwpluginpatches"] if type(S) == "table" and S.v == 3 then return S.print, S.mwse, S end S = { v = 3, redirected = 0, dropped = 0, collapsed = 0 } package.loaded["mwluafix_logshim:mwpluginpatches"] = S local C = { name = "mwpluginpatches", init = 0, after = 0, keep = { "error", "traceback", "exception", "fail", "warn", "stack", "attempt to", "assert", "invalid", "%.lua:%d+:", "^lua:", "initializ", "register", "start", "loaded", "ready", "version", "active" }, perSecond = 25, maxBytes = 2097152, keepOld = 1, flushSeconds = 2.0, errorRepeat = 0 } local G, MARK = _G, "mwdialog_luafix" local find, lower, sub, gsub, concat, fmt, date, select, tostring, pcall = string.find, string.lower, string.sub, string.gsub, table.concat, string.format, os.date, select, tostring, pcall local dir = "Data Files\\MWSE\\logs" local path, oldPath = dir .. "\\" .. C.name .. ".log", dir .. "\\" .. C.name .. ".old.log" local t0 = os.time() - math.floor(os.clock()) - 1 local init, run, started, redirected, f, dead, busy, fails = 0, 0, false, false, nil, false, false, 0 local bytes, dirty, last, lastN, sec, secN, dropped, errs, errKeys = 0, false, nil, 0, -1, 0, 0, {}, 0 local function isErr(t) local l = lower(#t > 4096 and sub(t, 1, 4096) or t) for i = 1, #C.keep do local ok, h = pcall(find, l, C.keep[i]) if ok and h then return true end end return false end local function out(s) f:write(date("[%H:%M:%S] "), s, "\n") bytes = bytes + #s + 12 dirty = true end local function pending() if lastN > 0 then out("[previous line repeated " .. lastN .. " more time(s)]") lastN = 0 end if dropped > 0 then out("[" .. dropped .. " line(s) dropped: more than " .. C.perSecond .. " in one second]") dropped = 0 end end local function flushAll() if f then pending() if dirty then dirty = false f:flush() end end end local function rotate() if f then pcall(f.close, f) f = nil end if C.keepOld > 0 then os.remove(oldPath) os.rename(path, oldPath) else os.remove(path) end f = io.open(path, "w") bytes, last = 0, nil if f then pcall(f.setvbuf, f, "full", 16384) f:write(date("[%Y-%m-%d %H:%M:%S] "), C.name, ": lines past its MWSE.log allowance (", MARK, ")\n") end return f end local function open() pcall(function() lfs.mkdir(dir) end) local ok, m = pcall(function() return lfs.attributes(path, "modification") end) if ok and type(m) == "number" and m >= t0 then path, oldPath = dir .. "\\" .. C.name .. ".luafix.log", dir .. "\\" .. C.name .. ".luafix.old.log" end return rotate() end local function toFile(t) if t == last then lastN = lastN + 1 S.collapsed = S.collapsed + 1 return end local s = os.time() if s ~= sec then sec, secN = s, 0 end secN = secN + 1 if C.perSecond > 0 and secN > C.perSecond then dropped = dropped + 1 S.dropped = S.dropped + 1 return end if bytes >= C.maxBytes and not rotate() then dead = true return end pending() last = t out(t) S.redirected = S.redirected + 1 if not started then dirty = false f:flush() end end S.start = function() if started then return end started = true pcall(flushAll) pcall(function() timer.start({ type = timer.real, duration = C.flushSeconds, iterations = -1, persist = false, callback = function() pcall(flushAll) end }) end) end local function route(t, force) if not started then local ok, v = pcall(function() return tes3.isInitialized() end) if ok and v then S.start() end end if force or isErr(t) then if C.errorRepeat > 0 then local k = gsub(sub(t, 1, (find(t, "\n", 1, true) or 201) - 1), "%d+", "#") local n = errs[k] or 0 if n == 0 then if errKeys >= 500 then errs, errKeys = {}, 0 end errKeys = errKeys + 1 end errs[k] = n + 1 if n >= C.errorRepeat then if f then toFile(t) end return false end end if not f and not dead then open() end if f then pending() out(t) dirty = false f:flush() end return true end local _, nl = gsub(t, "\n", "") nl = nl + 1 if not redirected then if started then if run + nl <= C.after then run = run + nl return true end elseif init + nl <= C.init then init = init + nl return true end redirected = true if not f and not open() then dead = true _p(fmt("[%s] %s writes a lot to MWSE.log, but %s can't be opened: leaving it here", MARK, C.name, path)) return true end _p(fmt("[%s] %s has written %d line(s) to MWSE.log; its further output goes to %s (errors still show here)", MARK, C.name, init + run, path)) end if dead or not f then return true end toFile(t) return false end local function fail(e) fails = fails + 1 if fails >= 10 then dead = true end if fails == 1 then pcall(_p, fmt("[%s] %s: log shim error (the line went to MWSE.log): %s", MARK, C.name, tostring(e))) end end local function decidePrint(n, ...) local t if n <= 1 then t = tostring((...)) else local parts = {} for i = 1, n do parts[i] = tostring((select(i, ...))) end t = concat(parts, "\t") end return route(t, false) end S.print = function(...) if busy or dead then return _p(...) end busy = true local ok, pass = pcall(decidePrint, select("#", ...), ...) busy = false if not ok then fail(pass) return _p(...) end if pass then return _p(...) end end local function decideLog(f0, ...) local ok, t = pcall(fmt, tostring(f0), ...) if not ok then t = tostring(f0) end return route(t, false) end S.mwse = setmetatable({ log = function(f0, ...) if busy or dead then return _m.log(f0, ...) end busy = true local ok, pass = pcall(decideLog, f0, ...) busy = false if not ok then fail(pass) pass = true end if pass then return _m.log(f0, ...) end end }, { __index = _m, __newindex = _m }) local function back(g, ok, ...) if G.print == S.print then G.print = g end if not ok then error((...), 0) end return ... end local wrapped = setmetatable({}, { __mode = "k" }) local LV = { trace = 5, debug = 4, info = 3 } local function wrap(lg) for name, lv in pairs(LV) do local orig = lg[name] if type(orig) == "function" then rawset(lg, name, function(self, ...) if dead or self ~= lg or G.print == S.print then return orig(self, ...) end local sd = type(lg.makeRecord) == "function" and type(lg.writeRecord) == "function" and lg.sharedData if sd and type(sd.level) == "number" then if sd.level < lv then return end local rec = lg:makeRecord(lv) local g = G.print G.print = S.print return back(g, pcall(lg.writeRecord, lg, rec, ...)) end local g = G.print G.print = S.print return back(g, pcall(orig, self, ...)) end) end end end S.wrap = function(lg) if type(lg) == "table" and not wrapped[lg] then wrapped[lg] = true pcall(wrap, lg) end return lg end S.flush = flushAll S.stats = function() return { init = init, run = run, redirected = redirected, dead = dead, path = path, fails = fails, started = started } end pcall(function() event.register("initialized", S.start) for _, ev in ipairs({ "loaded", "save", "menuEnter" }) do event.register(ev, function() pcall(flushAll) end) end end) pcall(function() local p = newproxy(true) getmetatable(p).__gc = function() pcall(flushAll) end S.gc = p end) return S.print, S.mwse, S end)(print, mwse) --[[/mwluafix_logshim]] local config = require("mwpluginpatches.config")

local this = {}
local bypassed = setmetatable({}, { __mode = "k" })

local function isDoor(ref)
    return ref and ref.object and ref.object.objectType == tes3.objectType.door
end

local function playerHasKey(ref)
    local lockNode = ref.lockNode
    local key = lockNode and lockNode.key
    if not key then
        return false
    end
    local inv = tes3.player and tes3.player.object and tes3.player.object.inventory
    if inv and inv:contains(key.id) then
        return true
    end
    return (tes3.getItemCount({ reference = tes3.player, item = key }) or 0) > 0
end

local function ownerIsAbsent(ref)
    local destination = ref.destination
    local cell = destination and destination.cell
    if not cell or not cell.isInterior then
        return false
    end
    local owner = tes3.getOwner({ reference = ref })
    if not owner or owner.objectType ~= tes3.objectType.npc then
        return false
    end
    for actor in cell:iterateReferences(tes3.objectType.npc) do
        if not actor.disabled and actor.object == owner then
            return false
        end
    end
    return true
end

local function isInteriorExit(ref)
    local source = ref.cell or (tes3.player and tes3.player.cell)
    local destination = ref.destination and ref.destination.cell
    if not source or not destination then
        return false
    end
    local sourceIsInterior = source.isInterior and not source.isOrBehavesAsExterior
    local destIsExterior = destination.isOrBehavesAsExterior or not destination.isInterior
    return sourceIsInterior and destIsExterior
end

-- tes3reference.disabled is read-only: a reference is disabled and enabled through its methods
local function setDisabled(ref, disabled)
    if disabled and not ref.disabled then
        ref:disable()
    elseif not disabled and ref.disabled then
        ref:enable()
    end
end

local function syncArrilleInnDoors(cell)
    cell = cell or (tes3.player and tes3.player.cell)
    if not (cell and cell.id and cell.id:find("Arrille's Tradehouse")) then
        return
    end
    local rentGlobal = (tes3.getGlobal and tes3.getGlobal("Rent_Arrille"))
        or (tes3.findGlobal and tes3.findGlobal("Rent_Arrille") and tes3.findGlobal("Rent_Arrille").value)
    local isRented = rentGlobal == 1

    for ref in cell:iterateReferences(tes3.objectType.door) do
        local objId = ref.object and ref.object.id and ref.object.id:lower()
        if objId == "dim_com_m_trapdoor_b" then
            setDisabled(ref, isRented)
        elseif objId == "rent_arrille_door" then
            if isRented and tes3.getLocked({ reference = ref }) then
                tes3.unlock({ reference = ref })
                if ref.lockNode then ref.lockNode.locked = false end
            end
        end
    end
end

local function beforeActivate(e)
    local door = e.target
    if e.activator ~= tes3.player or not isDoor(door) then
        return
    end

    -- Resolve Seyda Neen Arrille's Tradehouse duplicate trapdoors (Improved Inns vs OAAB Damp Little Squat).
    local objId = door.object and door.object.id and door.object.id:lower()
    if objId == "dim_com_m_trapdoor_b" or objId == "rent_arrille_door" then
        local cell = door.cell or (tes3.player and tes3.player.cell)
        if cell and cell.id and cell.id:find("Arrille's Tradehouse") then
            local rentGlobal = (tes3.getGlobal and tes3.getGlobal("Rent_Arrille"))
                or (tes3.findGlobal and tes3.findGlobal("Rent_Arrille") and tes3.findGlobal("Rent_Arrille").value)
            local isRented = rentGlobal == 1
            if isRented then
                if objId == "dim_com_m_trapdoor_b" then
                    setDisabled(door, true)
                    for ref in cell:iterateReferences(tes3.objectType.door) do
                        if ref.object and ref.object.id and ref.object.id:lower() == "rent_arrille_door" then
                            if tes3.getLocked({ reference = ref }) then
                                tes3.unlock({ reference = ref })
                            end
                            if ref.lockNode then ref.lockNode.locked = false end
                            if ref.data and not ref.data.ab01drlkbl then
                                ref.data.ab01drlkbl = 1
                                bypassed[ref] = true
                            end
                            tes3.player:activate(ref)
                            return false
                        end
                    end
                elseif objId == "rent_arrille_door" then
                    if tes3.getLocked({ reference = door }) then
                        tes3.unlock({ reference = door })
                    end
                    if door.lockNode then door.lockNode.locked = false end
                    if door.data and not door.data.ab01drlkbl then
                        door.data.ab01drlkbl = 1
                        bypassed[door] = true
                    end
                    return
                end
            end
        end
    end

    -- Conceptually, nobody locks you in after hours; they just want you to leave.
    -- When exiting an interior to the exterior, never require sneaking or lockpicking,
    -- even if the door is owned and locked.
    if isInteriorExit(door) then
        if tes3.getLocked({ reference = door }) then
            tes3.unlock({ reference = door })
        end
        if door.data and not door.data.ab01drlkbl then
            door.data.ab01drlkbl = 1
            bypassed[door] = true
        end
        return
    end

    -- If the player possesses the key, allow legitimate key unlock/entry without sneaking or blocking.
    if playerHasKey(door) then
        return
    end

    if not tes3.getLocked({ reference = door }) and ownerIsAbsent(door) then
        tes3.lock({ reference = door, level = 38 })
    end

    if tes3.getLocked({ reference = door }) then
        if not tes3.mobilePlayer.isSneaking then
            tes3.playSound({ sound = "LockedDoor", reference = door })
            if config.doorLockedNotification then
                tes3ui.showNotifyMenu("The Door is Locked")
            end
            return false
        end

        -- Let Modern Lockpicking validate the pick and open its interface; abot otherwise consumes activation first.
        if door.data and not door.data.ab01drlkbl then
            door.data.ab01drlkbl = 1
            bypassed[door] = true
        end
        return
    end

    if not tes3.mobilePlayer.isSneaking and not tes3.hasOwnershipAccess({ target = door }) then
        return false
    end
end

local function afterAbot(e)
    local door = e.target
    if bypassed[door] then
        if door.data then
            door.data.ab01drlkbl = nil
        end
        bypassed[door] = nil
    end
end

this.syncArrilleInnDoors = syncArrilleInnDoors

function this.init()
    event.register(tes3.event.activate, beforeActivate, { priority = 9200 })
    event.register(tes3.event.activate, afterAbot, { priority = 9000 })
    if tes3.event and tes3.event.cellChanged then
        event.register(tes3.event.cellChanged, function(e) syncArrilleInnDoors(e and e.cell) end, { priority = 0 })
    end
    mwse.log("[mwpluginpatches] Door lock compatibility active (owned-empty locking, free interior exits, sneak-to-pick, standing lock feedback, inn door resolver).")
end

return this
