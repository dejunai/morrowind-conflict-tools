--[[
    mwcompanions core: who is a follower, read without crashing the engine.
    Merges Smart Companions' validFollower and Attend Me's crash-safe `companion` read; also used by other mods
    (require("mwcompanions.core").isFollower(mobile)).
]]
local config = require("mwcompanions.config")
local core = {}

local function lower(s) return s and s:lower() or "" end

local function attendMeFollowers()
    local mod = package.loaded["AttendMeMWSE.followers"]
    return type(mod) == "table" and mod or nil
end

function core.isAttendMeCompanion(ref)
    if not ref then return false end
    local mod = attendMeFollowers()
    if mod and type(mod.hasForcedCompanion) == "function" then
        local ok, forced = pcall(mod.hasForcedCompanion, ref)
        if ok and forced then return true end
    end
    local ok, forced = pcall(function() return ref.data and ref.data.attendMeCompanion == true end)
    return ok and forced == true
end

function core.attendMeHandlesWarping()
    local mod = package.loaded["AttendMeMWSE.teleport"]
    if type(mod) ~= "table" or type(mod.process) ~= "function" then return false end
    local ok, cfg = pcall(mwse.loadConfig, "AttendMeMWSE")
    return ok and type(cfg) == "table" and cfg.teleportFollowers == true
end

--- the script declares this local; the script's own context is safe for that test (abot), not for its value
local function scriptHasLocal(script, name)
    local ok, v = pcall(function() return script.context and script.context[name] end)
    return ok and v ~= nil
end

--- `companion` of an NPC, or nil. Reading a local that a creature or a script-stripped reference doesn't really
--- have crashes inside the engine, where pcall can't catch it (Sails and Sales, abotWaterLife, Immersive Travel).
function core.companionVar(ref)
    local obj = ref and ref.baseObject
    if not obj or obj.objectType ~= tes3.objectType.npc or not obj.script then return nil end
    local data = ref.data
    if data and (data.rfuzzo_noscript or data.rfuzzo_invincible) then return nil end
    local ok, live = pcall(function()
        local vars = ref.attachments and ref.attachments.variables
        return vars == nil or vars.script ~= nil
    end)
    if not ok or not live then return nil end
    if not scriptHasLocal(obj.script, "companion") then return nil end
    local ok2, value = pcall(function() return ref.context and ref.context.companion end)
    return ok2 and value or nil
end

--- guards follow the player for a while when MoreAttentiveGuards has them watch a sneaking player
function core.isGuard(ref)
    local obj = ref.baseObject
    if obj.isGuard then return true end
    local mag = package.loaded["celediel.MoreAttentiveGuards.interop"]
    if mag and mag.getGuardFollower then
        local ok, g = pcall(mag.getGuardFollower)
        if ok and g and (g == ref or g == ref.mobile) then return true end
    end
    return false
end

function core.isBlacklisted(ref)
    local obj = ref.baseObject
    local id = lower(obj.id)
    if config.blacklist[id] or config.blacklist[obj.id] then return true end
    -- abot's water life and birds carry follow/escort packages of their own; the pack guar is a real follower
    if obj.objectType == tes3.objectType.creature and id ~= "ab01guguarpackmount" then
        if id:sub(1, 4) == "ab01" or (obj.script and lower(obj.script.id):sub(1, 4) == "ab01") then return true end
    end
    return false
end

--- the active package if it is follow/escort, and whether it targets the player
local function followPackage(mobile)
    local planner = mobile.aiPlanner
    local ok, p = pcall(function() return planner and planner:getActivePackage() end)
    if not ok or not p then return nil end
    if p.type ~= tes3.aiPackage.follow and p.type ~= tes3.aiPackage.escort then return p.type, false end
    local t = p.targetActor
    return p.type, t == tes3.mobilePlayer or (t ~= nil and t.reference == tes3.player)
end

function core.isAttendMeActivelyFollowing(mobile)
    local ref = mobile and mobile.reference
    if not ref or not core.isAttendMeCompanion(ref) then return false end
    local mod = attendMeFollowers()
    if mod and type(mod.isActivelyFollowing) == "function" then
        local ok, following = pcall(mod.isActivelyFollowing, ref)
        if ok then return following == true end
    end
    local ptype, toPlayer = followPackage(mobile)
    return (ptype == tes3.aiPackage.follow or ptype == tes3.aiPackage.escort) and toPlayer
end

--- 0 = not a follower, 1 = follower, 2 = companion (`companion = 1`)
function core.followerKind(mobile)
    if not mobile or mobile == tes3.mobilePlayer or mobile.isDead then return 0 end
    local ref = mobile.reference
    if not ref or ref.disabled or not ref.baseObject then return 0 end
    if core.isBlacklisted(ref) or core.isGuard(ref) then return 0 end
    if core.isAttendMeCompanion(ref) and ref.baseObject.objectType == tes3.objectType.npc then return 2 end
    local companion = core.companionVar(ref) == 1
    local ptype, toPlayer = followPackage(mobile)
    if ptype == tes3.aiPackage.follow then
        if not toPlayer then return 0 end
        return companion and 2 or 1
    elseif ptype == tes3.aiPackage.escort then
        return (toPlayer and companion) and 2 or 0   -- escort quests: only real companions
    elseif ptype == nil then
        return companion and 2 or 0                  -- companion between packages
    end
    return 0                                         -- wander/travel/activate: told to wait
end

--- on an escort package for the player (escort quests), companion or not
function core.isEscort(mobile)
    if not mobile or mobile == tes3.mobilePlayer or not mobile.reference then return false end
    local ptype, toPlayer = followPackage(mobile)
    return ptype == tes3.aiPackage.escort and toPlayer == true
end

--- an escort fights only who attacks it, never in the player's defense (user, 2026-11-21)
function core.isSelfDefense(mobile, enemy)
    local ad = enemy and enemy.actionData
    return ad ~= nil and ad.target == mobile
end

function core.isFollower(mobile) return core.followerKind(mobile) > 0 end
function core.isCompanion(mobile) return core.followerKind(mobile) == 2 end

--- the player and their followers are one side
local function onPlayerSide(mobile) return mobile == tes3.mobilePlayer or core.isFollower(mobile) end
function core.areFriends(a, b)
    return a ~= nil and b ~= nil and a ~= b and onPlayerSide(a) and onPlayerSide(b)
end

--- far enough (or in another cell) to warp; companions and summons stay in a fight they are in
function core.shouldWarp(mobile, kind, distance)
    if not mobile.canMove or mobile.fatigue.current <= 0 then return false end
    local ref = mobile.reference
    if core.isAttendMeCompanion(ref) and not core.isAttendMeActivelyFollowing(mobile) then return false end
    if ref.data and ref.data.rfuzzo_invincible then return false end   -- Immersive Travel crew and mounts
    if (mobile.inCombat or not mobile.canAct)
        and (kind == 2 or lower(ref.baseObject.id):find("summon", 1, true)) then return false end
    if ref.cell ~= tes3.player.cell then return true end
    return ref.position:distance(tes3.player.position) > distance
end

--- spot i of n: an arc behind the player (Attend Me's layout)
function core.warpSpot(i, n, playerPos, facing)
    local angle = (i - (n + 1) / 2) * 0.35
    local fx, fy = math.sin(facing), math.cos(facing)
    local dist = 80
    local s = math.sin(angle)
    return tes3vector3.new(playerPos.x - fx * dist * 0.6 + fy * dist * s,
        playerPos.y - fy * dist * 0.6 - fx * dist * s, playerPos.z + 8)
end

return core
