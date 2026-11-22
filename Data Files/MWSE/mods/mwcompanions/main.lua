--[[mwdialog_luafix 3: A1 F1]] local print, mwse, mwluafix_log = (function(_p, _m) local S = package.loaded["mwluafix_logshim:mwcompanions"] if type(S) == "table" and S.v == 3 then return S.print, S.mwse, S end S = { v = 3, redirected = 0, dropped = 0, collapsed = 0 } package.loaded["mwluafix_logshim:mwcompanions"] = S local C = { name = "mwcompanions", init = 0, after = 0, keep = { "error", "traceback", "exception", "fail", "warn", "stack", "attempt to", "assert", "invalid", "%.lua:%d+:", "^lua:", "initializ", "register", "start", "loaded", "ready", "version", "active" }, perSecond = 25, maxBytes = 2097152, keepOld = 1, flushSeconds = 2.0, errorRepeat = 0 } local G, MARK = _G, "mwdialog_luafix" local find, lower, sub, gsub, concat, fmt, date, select, tostring, pcall = string.find, string.lower, string.sub, string.gsub, table.concat, string.format, os.date, select, tostring, pcall local dir = "Data Files\\MWSE\\logs" local path, oldPath = dir .. "\\" .. C.name .. ".log", dir .. "\\" .. C.name .. ".old.log" local t0 = os.time() - math.floor(os.clock()) - 1 local init, run, started, redirected, f, dead, busy, fails = 0, 0, false, false, nil, false, false, 0 local bytes, dirty, last, lastN, sec, secN, dropped, errs, errKeys = 0, false, nil, 0, -1, 0, 0, {}, 0 local function isErr(t) local l = lower(#t > 4096 and sub(t, 1, 4096) or t) for i = 1, #C.keep do local ok, h = pcall(find, l, C.keep[i]) if ok and h then return true end end return false end local function out(s) f:write(date("[%H:%M:%S] "), s, "\n") bytes = bytes + #s + 12 dirty = true end local function pending() if lastN > 0 then out("[previous line repeated " .. lastN .. " more time(s)]") lastN = 0 end if dropped > 0 then out("[" .. dropped .. " line(s) dropped: more than " .. C.perSecond .. " in one second]") dropped = 0 end end local function flushAll() if f then pending() if dirty then dirty = false f:flush() end end end local function rotate() if f then pcall(f.close, f) f = nil end if C.keepOld > 0 then os.remove(oldPath) os.rename(path, oldPath) else os.remove(path) end f = io.open(path, "w") bytes, last = 0, nil if f then pcall(f.setvbuf, f, "full", 16384) f:write(date("[%Y-%m-%d %H:%M:%S] "), C.name, ": lines past its MWSE.log allowance (", MARK, ")\n") end return f end local function open() pcall(function() lfs.mkdir(dir) end) local ok, m = pcall(function() return lfs.attributes(path, "modification") end) if ok and type(m) == "number" and m >= t0 then path, oldPath = dir .. "\\" .. C.name .. ".luafix.log", dir .. "\\" .. C.name .. ".luafix.old.log" end return rotate() end local function toFile(t) if t == last then lastN = lastN + 1 S.collapsed = S.collapsed + 1 return end local s = os.time() if s ~= sec then sec, secN = s, 0 end secN = secN + 1 if C.perSecond > 0 and secN > C.perSecond then dropped = dropped + 1 S.dropped = S.dropped + 1 return end if bytes >= C.maxBytes and not rotate() then dead = true return end pending() last = t out(t) S.redirected = S.redirected + 1 if not started then dirty = false f:flush() end end S.start = function() if started then return end started = true pcall(flushAll) pcall(function() timer.start({ type = timer.real, duration = C.flushSeconds, iterations = -1, persist = false, callback = function() pcall(flushAll) end }) end) end local function route(t, force) if not started then local ok, v = pcall(function() return tes3.isInitialized() end) if ok and v then S.start() end end if force or isErr(t) then if C.errorRepeat > 0 then local k = gsub(sub(t, 1, (find(t, "\n", 1, true) or 201) - 1), "%d+", "#") local n = errs[k] or 0 if n == 0 then if errKeys >= 500 then errs, errKeys = {}, 0 end errKeys = errKeys + 1 end errs[k] = n + 1 if n >= C.errorRepeat then if f then toFile(t) end return false end end if not f and not dead then open() end if f then pending() out(t) dirty = false f:flush() end return true end local _, nl = gsub(t, "\n", "") nl = nl + 1 if not redirected then if started then if run + nl <= C.after then run = run + nl return true end elseif init + nl <= C.init then init = init + nl return true end redirected = true if not f and not open() then dead = true _p(fmt("[%s] %s writes a lot to MWSE.log, but %s can't be opened: leaving it here", MARK, C.name, path)) return true end _p(fmt("[%s] %s has written %d line(s) to MWSE.log; its further output goes to %s (errors still show here)", MARK, C.name, init + run, path)) end if dead or not f then return true end toFile(t) return false end local function fail(e) fails = fails + 1 if fails >= 10 then dead = true end if fails == 1 then pcall(_p, fmt("[%s] %s: log shim error (the line went to MWSE.log): %s", MARK, C.name, tostring(e))) end end local function decidePrint(n, ...) local t if n <= 1 then t = tostring((...)) else local parts = {} for i = 1, n do parts[i] = tostring((select(i, ...))) end t = concat(parts, "\t") end return route(t, false) end S.print = function(...) if busy or dead then return _p(...) end busy = true local ok, pass = pcall(decidePrint, select("#", ...), ...) busy = false if not ok then fail(pass) return _p(...) end if pass then return _p(...) end end local function decideLog(f0, ...) local ok, t = pcall(fmt, tostring(f0), ...) if not ok then t = tostring(f0) end return route(t, false) end S.mwse = setmetatable({ log = function(f0, ...) if busy or dead then return _m.log(f0, ...) end busy = true local ok, pass = pcall(decideLog, f0, ...) busy = false if not ok then fail(pass) pass = true end if pass then return _m.log(f0, ...) end end }, { __index = _m, __newindex = _m }) local function back(g, ok, ...) if G.print == S.print then G.print = g end if not ok then error((...), 0) end return ... end local wrapped = setmetatable({}, { __mode = "k" }) local LV = { trace = 5, debug = 4, info = 3 } local function wrap(lg) for name, lv in pairs(LV) do local orig = lg[name] if type(orig) == "function" then rawset(lg, name, function(self, ...) if dead or self ~= lg or G.print == S.print then return orig(self, ...) end local sd = type(lg.makeRecord) == "function" and type(lg.writeRecord) == "function" and lg.sharedData if sd and type(sd.level) == "number" then if sd.level < lv then return end local rec = lg:makeRecord(lv) local g = G.print G.print = S.print return back(g, pcall(lg.writeRecord, lg, rec, ...)) end local g = G.print G.print = S.print return back(g, pcall(orig, self, ...)) end) end end end S.wrap = function(lg) if type(lg) == "table" and not wrapped[lg] then wrapped[lg] = true pcall(wrap, lg) end return lg end S.flush = flushAll S.stats = function() return { init = init, run = run, redirected = redirected, dead = dead, path = path, fails = fails, started = started } end pcall(function() event.register("initialized", S.start) for _, ev in ipairs({ "loaded", "save", "menuEnter" }) do event.register(ev, function() pcall(flushAll) end) end end) pcall(function() local p = newproxy(true) getmetatable(p).__gc = function() pcall(flushAll) end S.gc = p end) return S.print, S.mwse, S end)(print, mwse) --[[/mwluafix_logshim]] --[[
    mwcompanions: following, warping and follower combat in one place (replaces the companion suite's
    Smart Companions and Easy Escort parts). One 1-second timer, only while a switch that needs it is on; no
    per-frame handler. Followers come from the engine's friendlyActors list each time; nothing is cached.
]]
local config = require("mwcompanions.config")
local core = require("mwcompanions.core")

local NAME = "mwcompanions"
local tick          -- the 1 s timer
local muteUntil = 0 -- os.clock() until which followers' Attack/Hello lines are muted

local function followers()
    local list = {}
    local fa = tes3.mobilePlayer and tes3.mobilePlayer.friendlyActors or {}
    for i = 1, #fa do
        local kind = core.followerKind(fa[i])
        if kind > 0 then list[#list + 1] = { mobile = fa[i], kind = kind } end
    end
    return list
end

local function setTraits(mob)
    if mob.alarm > 0 then mob.alarm = 0 end
    if mob.actorType ~= tes3.actorType.npc then return end
    if mob.waterBreathing < 1 then mob.waterBreathing = 1 end
    if mob.acrobatics.current < 150 then mob.acrobatics.current = 150 end
    if mob.athletics.current < 220 then mob.athletics.current = 220 end
end

-- shortcut: the flag stays on a follower dismissed mid-levitation until it follows again; clear it on dismissal if that shows
local function matchPlayer(mob, attr, flag)
    local data = mob.reference.data
    if tes3.mobilePlayer[attr] > 0 then
        if mob[attr] <= 0 then
            mob[attr] = 1
            data[flag] = true
            if attr == "levitate" then mob.isFlying = true end
        end
    elseif data[flag] then
        mob[attr] = 0
        data[flag] = nil
        if attr == "levitate" then mob.isFlying = false end
    end
end

local function sweep()
    if not config.enabled or not tes3.player or tes3.menuMode() then return end
    local list = followers()
    local far = {}
    for _, f in ipairs(list) do
        local mob = f.mobile
        if config.followerTraits then setTraits(mob) end
        if config.levitateWater then
            matchPlayer(mob, "levitate", "mwcompanionsLevitate")
            matchPlayer(mob, "waterWalking", "mwcompanionsWaterWalk")
        end
        if config.warp and core.shouldWarp(mob, f.kind, config.warpDistance) then far[#far + 1] = mob.reference end
    end
    local player = tes3.player
    for i, ref in ipairs(far) do
        local pos = core.warpSpot(i, #far, player.position, player.facing)
        local ok = pcall(tes3.positionCell, { reference = ref, cell = player.cell, position = pos,
            orientation = player.orientation:copy() })
        if not ok then ref.position = pos end
    end
end

local function restartTick()
    if tick then tick:cancel() end
    tick = nil
    if config.enabled and (config.warp or config.levitateWater or config.followerTraits) then
        tick = timer.start({ type = timer.simulate, duration = 1, iterations = -1, callback = sweep })
    end
end

-- collapse instead of death: health back, knocked out, waiting where it fell, then following again
local function collapse(mob, attacker)
    local ref = mob.reference
    mob:stopCombat(true)
    mob.health.current = math.max(1, mob.health.base * config.collapseHealth / 100)
    if attacker and attacker ~= tes3.mobilePlayer and attacker.actionData and attacker.actionData.target == mob then
        attacker.actionData.target = tes3.mobilePlayer
    end
    -- off the follow package, or the engine moves the unconscious follower through the next door
    tes3.setAIWander({ reference = ref, idles = { 40, 0, 0, 0, 0, 0, 0, 0 }, reset = true })
    if ref.data then ref.data.mwcompanionsCollapsed = true end
    mob.fatigue.currentRaw = -16000
    timer.start({ type = timer.simulate, duration = config.collapseSeconds, callback = "mwcompanions:recover",
        data = { id = ref.id } })
end

local function recover(e)
    local ref = tes3.getReference(e.timer.data.id)
    if not ref or not (ref.data and ref.data.mwcompanionsCollapsed) then return end
    if not ref.mobile then   -- in a cell that isn't loaded: try again later
        timer.start({ type = timer.simulate, duration = 10, callback = "mwcompanions:recover", data = e.timer.data })
        return
    end
    if ref.data then ref.data.mwcompanionsCollapsed = nil end
    ref.mobile.fatigue.currentRaw = ref.mobile.fatigue.base
    tes3.setAIFollow({ reference = ref, target = tes3.player })
end

-- escorts can't die: a killing blow drains fatigue to zero, they stay down while the fight lasts, then get up.
-- Only escorts down right now are listed (bounded, cleared on recovery; a load drops it and fatigue regenerates).
local downed = {}   -- mobile -> true
local downedTimer

local function anyHostile(mob)
    for _, a in ipairs(mob.hostileActors or {}) do
        if a and not a.isDead then return true end
    end
    return false
end

local function holdDowned()
    local left = false
    for mob in pairs(downed) do
        local ref = mob.reference
        if not ref or ref.disabled or mob.isDead then
            downed[mob] = nil
        elseif tes3.mobilePlayer.inCombat or anyHostile(mob) then
            mob.fatigue.currentRaw = 0
            left = true
        else
            downed[mob] = nil
            mob.fatigue.currentRaw = mob.fatigue.base
        end
    end
    if not left and downedTimer then
        downedTimer:cancel()
        downedTimer = nil
    end
end

local function knockDownEscort(mob, attacker)
    downed[mob] = true
    mob:stopCombat(true)
    if mob.health.current < 1 then mob.health.current = 1 end
    mob.fatigue.currentRaw = 0
    if attacker and attacker ~= tes3.mobilePlayer and attacker.actionData and attacker.actionData.target == mob then
        attacker.actionData.target = tes3.mobilePlayer
    end
    if not downedTimer then
        downedTimer = timer.start({ type = timer.simulate, duration = 0.5, iterations = -1, callback = holdDowned })
    end
end

local function soulTrapping(attacker, target)
    return attacker == tes3.mobilePlayer and not core.isCompanion(target)
        and tes3.isAffectedBy({ reference = target.reference, effect = tes3.effect.soultrap })
end

local function onDamage(e)
    if not config.enabled then return end
    local mob, attacker = e.mobile, e.attacker
    local data = mob.reference.data
    if config.escortProtection and mob ~= tes3.mobilePlayer then
        if downed[mob] then
            if e.damage > 0 then e.damage = 0 end
            return
        end
        local h = mob.health
        if (h.current - math.abs(e.damage) <= 0 or (e.magicSourceInstance and h.normalized < 0.5))
            and core.isEscort(mob) then
            if e.damage > 0 then e.damage = 0 end
            knockDownEscort(mob, attacker)
            return
        end
    end
    if config.resilient and mob ~= tes3.mobilePlayer then
        if data.mwcompanionsCollapsed then
            if e.damage > 0 then e.damage = 0 end
            return
        end
        local h = mob.health
        -- magic damage can't be blocked here, so a magic hit collapses at half health (as Smart Companions did)
        if (h.current - math.abs(e.damage) <= 0 or (e.magicSourceInstance and h.normalized < 0.5))
            and core.isFollower(mob) then
            if e.damage > 0 then e.damage = 0 end
            collapse(mob, attacker)
            return
        end
    end
    if config.noFriendlyFire and attacker and not e.magicSourceInstance and e.damage > 0
        and core.areFriends(mob, attacker) and not soulTrapping(attacker, mob) then
        e.damage = 0
        mob.friendlyFireHitCount = 0
        if mob.actionData and mob.actionData.target == attacker then mob:stopCombat(true) end
    end
end

local function onSpellResist(e)
    if not (config.enabled and config.noFriendlyFire) or not (e.caster and e.target) or e.caster == e.target then return end
    local effect = e.effect and e.effect.object
    if not (effect and effect.isHarmful) then return end
    local caster, target = e.caster.mobile, e.target.mobile
    if effect.id == tes3.effect.soultrap and caster == tes3.mobilePlayer then return end
    if core.areFriends(caster, target) then
        e.resistedPercent = 100
        target.friendlyFireHitCount = 0
    end
end

local function onCombatStarted(e)
    if not config.enabled then return end
    local actor, target = e.actor, e.target
    if config.escortSelfDefense and target ~= tes3.mobilePlayer and core.isEscort(actor)
        and not core.isSelfDefense(actor, target) then
        local handle = tes3.makeSafeObjectHandle(actor.reference)
        timer.delayOneFrame(function()
            local ref = handle:valid() and handle:getObject()
            if ref and ref.mobile and ref.mobile.inCombat then ref.mobile:stopCombat(true) end
        end)
        return
    end
    if not config.assist then return end
    local enemy = (target == tes3.mobilePlayer and actor) or (actor == tes3.mobilePlayer and target) or nil
    if not enemy or core.isFollower(enemy) then return end
    for _, f in ipairs(followers()) do
        if f.kind == 2 and not f.mobile.inCombat and not core.isEscort(f.mobile) then f.mobile:startCombat(enemy) end
    end
end

local function onInfoFilter(e)
    if not e.passes or os.clock() >= muteUntil then return end
    local id = e.dialogue and e.dialogue.id
    if id ~= "Attack" and id ~= "Hello" then return end
    local ref = e.reference
    if ref and ref.mobile and core.isFollower(ref.mobile) then e.passes = false end
end

local function onActivate(e)
    if not (config.enabled and config.noSneakActivate) or e.activator ~= tes3.player then return end
    local mob = e.target.mobile
    if mob and tes3.mobilePlayer.isSneaking and core.isFollower(mob) then return false end
end

local function onCellChanged(e)
    if not config.enabled or not e.previousCell then return end
    if config.muteOnCellChange then muteUntil = os.clock() + 3 end
    if config.warp or config.levitateWater then timer.delayOneFrame(sweep) end
end

-- one MWSE.log line per switch that duplicates an original option still switched on
local function warnOverlaps()
    local sc = mwse.loadConfig("abotSmart_Companions")
    local am = mwse.loadConfig("AttendMeMWSE")
    local checks = {}
    if sc then
        local function n(k) return (tonumber(sc[k]) or 0) > 0 or sc[k] == true end
        checks = {
            { config.warp, n("autoWarp") or n("autoMoveCC"), "Smart Companions warp / automove" },
            { config.levitateWater, n("warpLevitate") or n("warpWaterWalk"), "Smart Companions warp levitate / water walk" },
            { config.followerTraits, n("fixAlarm") or n("fixWaterBreathing") or n("fixAcrobatics") or n("fixAthletics"),
                "Smart Companions follower fixes" },
            { config.noFriendlyFire, n("noFriendlyFireMagic") or n("noFriendlyFireDamage"), "Smart Companions friendly fire" },
            { config.resilient, n("followersResiliency"), "Smart Companions resilient followers" },
            { config.assist, n("autoAttack"), "Smart Companions auto attack" },
            { config.muteOnCellChange, n("muteCC"), "Smart Companions mute on cell change" },
            { config.noSneakActivate, n("skipActivatingFollowerWhileSneaking"), "Smart Companions skip activation while sneaking" },
        }
    end
    if am then checks[#checks + 1] = { config.warp, am.teleportFollowers == true, "Attend Me teleport" } end
    for _, c in ipairs(checks) do
        if c[1] and c[2] then mwse.log("[%s] Warning: %s is still switched on and overlaps a mwcompanions switch: turn one off", NAME, c[3]) end
    end
end

event.register(tes3.event.initialized, function()
    timer.register("mwcompanions:recover", recover)
    event.register(tes3.event.damage, onDamage)
    event.register(tes3.event.spellResist, onSpellResist)
    event.register(tes3.event.combatStarted, onCombatStarted)
    event.register(tes3.event.infoFilter, onInfoFilter)
    event.register(tes3.event.activate, onActivate)
    event.register(tes3.event.cellChanged, onCellChanged)
    if config.enabled then warnOverlaps() end
end)
event.register(tes3.event.loaded, function()
    tick = nil   -- MWSE cancels all non-persistent timers before loaded
    downedTimer = nil
    downed = {}
    muteUntil = 0
    restartTick()
end)
event.register("mwcompanions:changed", restartTick)
event.register(tes3.event.modConfigReady, function() require("mwcompanions.mcm") end)
