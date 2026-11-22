--[[mwdialog_luafix 3: A1 F1]] local print, mwse, mwluafix_log = (function(_p, _m) local S = package.loaded["mwluafix_logshim:mwcriminal"] if type(S) == "table" and S.v == 3 then return S.print, S.mwse, S end S = { v = 3, redirected = 0, dropped = 0, collapsed = 0 } package.loaded["mwluafix_logshim:mwcriminal"] = S local C = { name = "mwcriminal", init = 0, after = 0, keep = { "error", "traceback", "exception", "fail", "warn", "stack", "attempt to", "assert", "invalid", "%.lua:%d+:", "^lua:", "initializ", "register", "start", "loaded", "ready", "version", "active" }, perSecond = 25, maxBytes = 2097152, keepOld = 1, flushSeconds = 2.0, errorRepeat = 0 } local G, MARK = _G, "mwdialog_luafix" local find, lower, sub, gsub, concat, fmt, date, select, tostring, pcall = string.find, string.lower, string.sub, string.gsub, table.concat, string.format, os.date, select, tostring, pcall local dir = "Data Files\\MWSE\\logs" local path, oldPath = dir .. "\\" .. C.name .. ".log", dir .. "\\" .. C.name .. ".old.log" local t0 = os.time() - math.floor(os.clock()) - 1 local init, run, started, redirected, f, dead, busy, fails = 0, 0, false, false, nil, false, false, 0 local bytes, dirty, last, lastN, sec, secN, dropped, errs, errKeys = 0, false, nil, 0, -1, 0, 0, {}, 0 local function isErr(t) local l = lower(#t > 4096 and sub(t, 1, 4096) or t) for i = 1, #C.keep do local ok, h = pcall(find, l, C.keep[i]) if ok and h then return true end end return false end local function out(s) f:write(date("[%H:%M:%S] "), s, "\n") bytes = bytes + #s + 12 dirty = true end local function pending() if lastN > 0 then out("[previous line repeated " .. lastN .. " more time(s)]") lastN = 0 end if dropped > 0 then out("[" .. dropped .. " line(s) dropped: more than " .. C.perSecond .. " in one second]") dropped = 0 end end local function flushAll() if f then pending() if dirty then dirty = false f:flush() end end end local function rotate() if f then pcall(f.close, f) f = nil end if C.keepOld > 0 then os.remove(oldPath) os.rename(path, oldPath) else os.remove(path) end f = io.open(path, "w") bytes, last = 0, nil if f then pcall(f.setvbuf, f, "full", 16384) f:write(date("[%Y-%m-%d %H:%M:%S] "), C.name, ": lines past its MWSE.log allowance (", MARK, ")\n") end return f end local function open() pcall(function() lfs.mkdir(dir) end) local ok, m = pcall(function() return lfs.attributes(path, "modification") end) if ok and type(m) == "number" and m >= t0 then path, oldPath = dir .. "\\" .. C.name .. ".luafix.log", dir .. "\\" .. C.name .. ".luafix.old.log" end return rotate() end local function toFile(t) if t == last then lastN = lastN + 1 S.collapsed = S.collapsed + 1 return end local s = os.time() if s ~= sec then sec, secN = s, 0 end secN = secN + 1 if C.perSecond > 0 and secN > C.perSecond then dropped = dropped + 1 S.dropped = S.dropped + 1 return end if bytes >= C.maxBytes and not rotate() then dead = true return end pending() last = t out(t) S.redirected = S.redirected + 1 if not started then dirty = false f:flush() end end S.start = function() if started then return end started = true pcall(flushAll) pcall(function() timer.start({ type = timer.real, duration = C.flushSeconds, iterations = -1, persist = false, callback = function() pcall(flushAll) end }) end) end local function route(t, force) if not started then local ok, v = pcall(function() return tes3.isInitialized() end) if ok and v then S.start() end end if force or isErr(t) then if C.errorRepeat > 0 then local k = gsub(sub(t, 1, (find(t, "\n", 1, true) or 201) - 1), "%d+", "#") local n = errs[k] or 0 if n == 0 then if errKeys >= 500 then errs, errKeys = {}, 0 end errKeys = errKeys + 1 end errs[k] = n + 1 if n >= C.errorRepeat then if f then toFile(t) end return false end end if not f and not dead then open() end if f then pending() out(t) dirty = false f:flush() end return true end local _, nl = gsub(t, "\n", "") nl = nl + 1 if not redirected then if started then if run + nl <= C.after then run = run + nl return true end elseif init + nl <= C.init then init = init + nl return true end redirected = true if not f and not open() then dead = true _p(fmt("[%s] %s writes a lot to MWSE.log, but %s can't be opened: leaving it here", MARK, C.name, path)) return true end _p(fmt("[%s] %s has written %d line(s) to MWSE.log; its further output goes to %s (errors still show here)", MARK, C.name, init + run, path)) end if dead or not f then return true end toFile(t) return false end local function fail(e) fails = fails + 1 if fails >= 10 then dead = true end if fails == 1 then pcall(_p, fmt("[%s] %s: log shim error (the line went to MWSE.log): %s", MARK, C.name, tostring(e))) end end local function decidePrint(n, ...) local t if n <= 1 then t = tostring((...)) else local parts = {} for i = 1, n do parts[i] = tostring((select(i, ...))) end t = concat(parts, "\t") end return route(t, false) end S.print = function(...) if busy or dead then return _p(...) end busy = true local ok, pass = pcall(decidePrint, select("#", ...), ...) busy = false if not ok then fail(pass) return _p(...) end if pass then return _p(...) end end local function decideLog(f0, ...) local ok, t = pcall(fmt, tostring(f0), ...) if not ok then t = tostring(f0) end return route(t, false) end S.mwse = setmetatable({ log = function(f0, ...) if busy or dead then return _m.log(f0, ...) end busy = true local ok, pass = pcall(decideLog, f0, ...) busy = false if not ok then fail(pass) pass = true end if pass then return _m.log(f0, ...) end end }, { __index = _m, __newindex = _m }) local function back(g, ok, ...) if G.print == S.print then G.print = g end if not ok then error((...), 0) end return ... end local wrapped = setmetatable({}, { __mode = "k" }) local LV = { trace = 5, debug = 4, info = 3 } local function wrap(lg) for name, lv in pairs(LV) do local orig = lg[name] if type(orig) == "function" then rawset(lg, name, function(self, ...) if dead or self ~= lg or G.print == S.print then return orig(self, ...) end local sd = type(lg.makeRecord) == "function" and type(lg.writeRecord) == "function" and lg.sharedData if sd and type(sd.level) == "number" then if sd.level < lv then return end local rec = lg:makeRecord(lv) local g = G.print G.print = S.print return back(g, pcall(lg.writeRecord, lg, rec, ...)) end local g = G.print G.print = S.print return back(g, pcall(orig, self, ...)) end) end end end S.wrap = function(lg) if type(lg) == "table" and not wrapped[lg] then wrapped[lg] = true pcall(wrap, lg) end return lg end S.flush = flushAll S.stats = function() return { init = init, run = run, redirected = redirected, dead = dead, path = path, fails = fails, started = started } end pcall(function() event.register("initialized", S.start) for _, ev in ipairs({ "loaded", "save", "menuEnter" }) do event.register(ev, function() pcall(flushAll) end) end end) pcall(function() local p = newproxy(true) getmetatable(p).__gc = function() pcall(flushAll) end S.gc = p end) return S.print, S.mwse, S end)(print, mwse) --[[/mwluafix_logshim]] --[[
    mwcriminal: sneaking, theft and door locks in one place.
    One activate handler (priority 9300, above abot Door Locks and Modern Lockpicking so it decides first), one
    detectSneak handler and one book-menu hook. Each behavior has its own MCM switch; all start off.
]]
local config = require("mwcriminal.config")
local core = require("mwcriminal.core")

local NAME = "mwcriminal"
local function save() mwse.saveConfig(NAME, config) end

local ownedBookOpen = false   -- the book being opened is someone else's and the player is standing
local opener                  -- { ref, position, facing, cell } of the NPC who answered the last knock
local knockSound

local function lockedFeedback(ref)
    local isDoor = ref.object.objectType == tes3.objectType.door
    tes3.playSound({ sound = isDoor and "LockedDoor" or "LockedChest", reference = ref })
    if config.lockedNotification then tes3ui.showNotifyMenu(isDoor and "The door is locked." or "It is locked.") end
end

local function restoreOpener()
    if not opener then return end
    local o = opener
    opener = nil
    local ref = o.ref:valid() and o.ref:getObject()
    if ref then
        ref.position = o.position
        ref.facing = o.facing
    end
end

-- the NPC inside opens: they are moved in front of the arrival marker, facing the player
local function knock(door)
    local who = core.opener(door, tes3.worldController.hour.value)
    if not who then return false end
    restoreOpener()
    local marker = door.destination.marker
    if marker then
        opener = { ref = tes3.makeSafeObjectHandle(who), position = who.position:copy(), facing = who.facing,
            cell = door.destination.cell }
        who.position = marker.position + marker.forwardDirection * 72
        local facing = marker.facing + math.pi
        who.facing = facing > math.pi and facing - 2 * math.pi or facing
    end
    if knockSound then tes3.playSound({ sound = knockSound }) end
    tes3.unlock({ reference = door })
    if door.data then door.data.mwcriminalLocked = nil end
    tes3ui.showNotifyMenu(who.object.name .. " opens the door.")
    return true
end

local function onDoor(door)
    if core.isExit(door) then
        if config.interiorExit and tes3.getLocked({ reference = door }) then
            tes3.unlock({ reference = door })
            if door.data then door.data.mwcriminalLocked = nil end
        end
        return
    end
    if config.eveningLocks then
        local verdict = core.lockVerdict(door, tes3.worldController.hour.value)
        if verdict then core.applyVerdict(door, verdict) end
    end
    if not tes3.getLocked({ reference = door }) or core.hasKey(door) or core.isSneaking() then return end
    if config.knocking and door.destination and not door.object.script and knock(door) then return end
    if config.sneakToPick then
        lockedFeedback(door)
        return false
    end
end

local function takeSheet(ref, book)
    local owned = core.isOwned(ref)
    if owned and not core.isSneaking() then return false end
    local count = math.max(ref.stackSize or 1, 1)
    local owner = owned and tes3.getOwner({ reference = ref }) or nil
    -- the item data goes with the item: a world object left holding it is written twice by a save, which can crash it
    local itemData = ref.itemData
    ref.itemData = nil
    tes3.addItem({ reference = tes3.player, item = book, count = count, itemData = itemData })
    ref:delete()
    if owner then
        tes3.setItemIsStolen({ item = book, from = owner, stolen = true })
        tes3.triggerCrime({ type = tes3.crimeType.theft, victim = owner, value = book.value * count })
    end
    return false
end

local function addToBlacklist(ref)
    local key = core.blacklistKey(ref)
    if config.blacklist[key] then
        tes3.messageBox("%s is already on the mwcriminal blacklist.", ref.object.name or ref.object.id)
        return
    end
    config.blacklist[key] = string.format("%s (%s)", ref.object.name ~= "" and ref.object.name or ref.object.id,
        ref.cell.displayName or ref.cell.id)
    save()
    tes3.messageBox("%s added to the mwcriminal blacklist (remove it in the mod's settings).", config.blacklist[key])
end

local function onActivate(e)
    ownedBookOpen = false
    if not config.enabled or e.activator ~= tes3.player then return end
    local ref = e.target
    if tes3.worldController.inputController:isShiftDown() then
        addToBlacklist(ref)
        return false
    end
    if core.isBlacklisted(ref) then return end
    local obj = ref.object
    local t = obj.objectType
    if t == tes3.objectType.door then return onDoor(ref) end
    local sneaking = core.isSneaking()
    if t == tes3.objectType.container and tes3.getLocked({ reference = ref }) and not core.hasKey(ref) then
        if sneaking then return end
        if config.sneakToPick then
            lockedFeedback(ref)
            return false
        end
    end
    if t == tes3.objectType.book then
        if config.plainPaper and core.isBlankSheet(obj) then return takeSheet(ref, obj) end
        if config.readStanding and not sneaking and core.isOwned(ref) then
            ownedBookOpen = true
            return
        end
    end
    if config.sneakToSteal and not sneaking and core.isOwned(ref) then return false end
end

local function onBookMenu(e)
    if not ownedBookOpen then return end
    ownedBookOpen = false
    local take = e.element:findChild("MenuBook_button_take") or e.element:findChild("MenuBook_PickupButton")
        or e.element:findChild("MenuScroll_Pickup")
    if not take then return end
    local red = tes3ui.getPalette("negative_color")
    take.color = red
    for _, child in ipairs(take.children) do child.color = red end
    e.element:updateLayout()
end

local function onDetectSneak(e)
    if not (config.enabled and config.companionDetection) or e.target ~= tes3.mobilePlayer then return end
    local d = e.detector
    if not d or not core.ignoredDetector(d) then return end
    e.isDetected = false
    d.isPlayerDetected = false
    d.isPlayerHidden = true
    local ok, so = pcall(require, "StormAtronach.SO.interop")
    if ok and so and so.clearSuspicion then pcall(so.clearSuspicion, d.reference) end
    return false   -- Stealth Overhaul (priority 1000) never sees it
end

-- Essential Indicators: the crosshair is tinted while it rests on something locked the player has no key for
local ei
local function onTargetChanged(e)
    if not ei then return end
    local ref = e.current
    local t = ref and ref.object.objectType
    if config.enabled and config.lockedCrosshair and (t == tes3.objectType.door or t == tes3.objectType.container)
        and tes3.getLocked({ reference = ref }) and not core.hasKey(ref) and not core.isBlacklisted(ref) then
        ei.registerColorOverride(1.0, 0.55, 0.1, 1.0, NAME, 900)
    else
        ei.deregisterColorOverride(NAME)
    end
end

local function onCellChanged(e)
    if opener and e.previousCell == opener.cell then restoreOpener() end
end

-- one MWSE.log line per switch that duplicates an original mod still switched on
local function warnOverlaps()
    local function on(name, key, default)
        local c = mwse.loadConfig(name)
        if c == nil then return default end
        return c[key] == true
    end
    local pp = mwse.loadConfig("mwpluginpatches") or {}
    local checks = {
        { config.plainPaper, on("mwplainpaperfix", "enabled", false), "mwplainpaperfix" },
        { config.sneakToSteal, on("noAccidentalTheft", "enabled", lfs.fileexists("Data Files\\MWSE\\mods\\mer\\accidentalTheftProtection\\main.lua")), "Accidental Theft Protection" },
        { config.readStanding, pp.enabled == true and pp.noAccidentalTheftBookFixEnabled == true, "mwpluginpatches book fix" },
        { config.companionDetection, on("mwcompanionsneak", "enabled", false), "mwcompanionsneak" },
        { config.interiorExit or config.sneakToPick, pp.enabled == true and pp.doorLockCompatibilityEnabled == true, "mwpluginpatches door lock compatibility" },
        { config.eveningLocks or config.knocking, on("abotDoor_Locks", "modEnabled", lfs.fileexists("Data Files\\MWSE\\mods\\abot\\Door Locks\\main.lua")), "abot Door Locks" },
    }
    for _, c in ipairs(checks) do
        if c[1] and c[2] then mwse.log("[mwcriminal] Warning: %s is still switched on and overlaps a mwcriminal switch: turn one off", c[3]) end
    end
end

event.register(tes3.event.initialized, function()
    knockSound = tes3.getSound("ab01KnockKnockSND")
    if not knockSound and tes3.getFileExists("Sound\\abot\\knockdoor.wav") then
        knockSound = tes3.createObject({ objectType = tes3.objectType.sound, id = "ab01KnockKnockSND",
            filename = "abot\\knockdoor.wav", volume = 1 })
    end
    event.register(tes3.event.activate, onActivate, { priority = 9300 })
    event.register(tes3.event.uiActivated, onBookMenu, { filter = "MenuBook" })
    event.register(tes3.event.uiActivated, onBookMenu, { filter = "MenuScroll" })
    event.register(tes3.event.detectSneak, onDetectSneak, { priority = 2000 })
    event.register(tes3.event.cellChanged, onCellChanged)
    local ok, interop = pcall(require, "Essential Indicators.interop")
    if ok and type(interop) == "table" then
        ei = interop
        event.register(tes3.event.activationTargetChanged, onTargetChanged)
        -- a lock picked or opened in a menu (Modern Lockpicking) leaves the same target in view
        event.register(tes3.event.menuExit, function() onTargetChanged({ current = tes3.getPlayerTarget() }) end)
    end
    if config.enabled then warnOverlaps() end
end)
event.register(tes3.event.loaded, function() opener = nil end)
event.register(tes3.event.modConfigReady, function() require("mwcriminal.mcm") end)
