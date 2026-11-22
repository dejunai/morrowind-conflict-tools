--[[mwdialog_luafix 4: A1]] --[[
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
    local canWarp = config.warp and not core.attendMeHandlesWarping()
    local me = tes3.mobilePlayer
    local atEase = config.sheatheAfterCombat and not (me.inCombat or me.weaponReady or me.castReady)
    for _, f in ipairs(list) do
        local mob = f.mobile
        -- the engine can end a follower's fight with the weapon still out, and it then stays out
        if atEase and f.kind == 2 and mob.weaponReady and not mob.inCombat then mob.weaponReady = false end
        if config.followerTraits then setTraits(mob) end
        if config.levitateWater then
            matchPlayer(mob, "levitate", "mwcompanionsLevitate")
            matchPlayer(mob, "waterWalking", "mwcompanionsWaterWalk")
        end
        if canWarp and core.shouldWarp(mob, f.kind, config.warpDistance) then
            far[#far + 1] = mob.reference
        end
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
    if config.enabled and (config.warp or config.levitateWater or config.followerTraits
            or config.sheatheAfterCombat) then
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
-- Kept as safe handles: a downed escort's cell can unload mid-fight, and its old mobile must not be touched then.
local downed = {}   -- reference id -> safe handle of the reference
local downedTimer

local function anyHostile(mob)
    for _, a in ipairs(mob.hostileActors or {}) do
        if a and not a.isDead then return true end
    end
    return false
end

local function holdDowned()
    local left = false
    for id, handle in pairs(downed) do
        local ref = handle:valid() and handle:getObject()
        local mob = ref and ref.mobile
        if not mob or ref.disabled or mob.isDead then
            downed[id] = nil
        elseif tes3.mobilePlayer.inCombat or anyHostile(mob) then
            mob.fatigue.currentRaw = 0
            left = true
        else
            downed[id] = nil
            mob.fatigue.currentRaw = mob.fatigue.base
        end
    end
    if not left and downedTimer then
        downedTimer:cancel()
        downedTimer = nil
    end
end

local function knockDownEscort(mob, attacker)
    downed[mob.reference.id] = tes3.makeSafeObjectHandle(mob.reference)
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
        if downed[mob.reference.id] then
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
        local commandedElsewhere = core.isAttendMeCompanion(f.mobile.reference)
            and not core.isAttendMeActivelyFollowing(f.mobile)
        if f.kind == 2 and not f.mobile.inCombat and not core.isEscort(f.mobile) and not commandedElsewhere then
            f.mobile:startCombat(enemy)
        end
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
    if not lfs.fileexists("Data Files\\MWSE\\mods\\abot\\Smart Companions\\main.lua") then return end
    local sc = mwse.loadConfig("abotSmart_Companions")
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
    local conflicts = {}
    for _, c in ipairs(checks) do
        if c[1] and c[2] then conflicts[#conflicts + 1] = c[3] end
    end
    if #conflicts > 0 then
        mwse.log("[%s] Warning: enabled switches overlap mwcompanions: %s. Turn one off.", NAME,
            table.concat(conflicts, ", "))
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
