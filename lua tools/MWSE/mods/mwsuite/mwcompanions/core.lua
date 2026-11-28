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

--- a guard is never a follower: any guard a follow package puts behind the player, and the one More Attentive
--- Guards has following a sneaking player. isGuard is a field of the actor's instance (tes3npcInstance, its mobile's
--- object), not of the base record: ref.baseObject.isGuard is always nil.
local function instanceIsGuard(ref)
    local ok, yes = pcall(function()
        local inst = (ref.mobile and ref.mobile.object) or ref.object
        return inst ~= nil and inst.isGuard == true
    end)
    return ok and yes
end

function core.isGuard(ref)
    if instanceIsGuard(ref) then return true end
    local mag = package.loaded["celediel.MoreAttentiveGuards.interop"]
    if mag and mag.getGuardFollower then
        local ok, g = pcall(mag.getGuardFollower)
        if ok and g and (g == ref or g == ref.mobile) then return true end
    end
    return false
end

-- the creatures the excluded plugins define, read from the plugin files themselves: not obj.sourceMod, which names the
-- last plugin to change a record (a creature-buff patch of abot's water life would hide them all)
local pluginCreatures = {}            -- lower-case base id -> plugin file name

local function u32(s, i)
    local a, b, c, d = s:byte(i, i + 3)
    return a + b * 256 + c * 65536 + d * 16777216
end

--- every CREA record's id in one plugin file (lower case), or nil when the file can't be read
function core.creatureIdsOf(path)
    local f = io.open(path, "rb")
    if not f then return nil end
    local data = f:read("*a")
    f:close()
    local ids, pos, n = {}, 1, #data
    while pos + 15 <= n do
        local tag, size = data:sub(pos, pos + 3), u32(data, pos + 4)
        local body, stop = pos + 16, pos + 16 + size
        if tag == "CREA" then
            local sp = body
            while sp + 7 < stop do
                local st, ss = data:sub(sp, sp + 3), u32(data, sp + 4)
                if st == "NAME" then
                    ids[#ids + 1] = data:sub(sp + 8, sp + 7 + ss):gsub("%z.*$", ""):lower()
                    break
                end
                sp = sp + 8 + ss
            end
        end
        pos = stop
    end
    return ids
end

--- rebuild the creature list from config.excludedPlugins (at start-up and when the Mod Config menu closes)
function core.rebuildPluginLists()
    pluginCreatures = {}
    local root = (type(tes3.installDirectory) == "string" and tes3.installDirectory ~= "")
        and (tes3.installDirectory .. "\\Data Files\\") or "Data Files\\"
    local plugins, count = 0, 0
    for name, on in pairs(config.excludedPlugins or {}) do
        if on and tes3.isModActive(name) then
            local ids = core.creatureIdsOf(root .. name)
            if ids then
                plugins = plugins + 1
                for _, id in ipairs(ids) do
                    if not pluginCreatures[id] then count = count + 1 end
                    pluginCreatures[id] = name
                end
            end
        end
    end
    mwse.log("[mwcompanions] %d creature(s) from %d excluded plugin(s) are never followers", count, plugins)
    return count
end

-- interop (mwpluginpatches' HUD Companion Health Bar mirror): the lists, read and changed by id ---------------------
local function dropAnyCase(t, id)
    for k in pairs(t) do
        if lower(k) == id then t[k] = nil end
    end
end

--- {lower-case id = true} of every actor that is never a follower: the blacklist and the excluded plugins'
--- creatures, less the whitelist
function core.neverFollowers()
    local out = {}
    for id, on in pairs(config.blacklist) do if on then out[lower(id)] = true end end
    for id in pairs(pluginCreatures) do out[id] = true end
    for id, on in pairs(config.whitelist) do if on then out[lower(id)] = nil end end
    return out
end

--- id is never a follower (it goes on the blacklist, and off the whitelist)
function core.exclude(id)
    id = lower(id)
    dropAnyCase(config.whitelist, id)
    config.blacklist[id] = true
end

--- id may be a follower again: off the blacklist, and on the whitelist when an excluded plugin defines it
function core.include(id)
    id = lower(id)
    dropAnyCase(config.blacklist, id)
    if pluginCreatures[id] then config.whitelist[id] = true end
end

function core.saveLists()
    mwse.saveConfig("mwcompanions", config)
end

--- never a follower: on the whitelist -> no; on the blacklist, or a creature an excluded plugin defines -> yes
function core.isBlacklisted(ref)
    local obj = ref.baseObject
    local id = lower(obj.id)
    if config.whitelist[id] or config.whitelist[obj.id] then return false end   -- the page keeps the id's own case
    if config.blacklist[id] or config.blacklist[obj.id] then return true end
    return pluginCreatures[id] ~= nil
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
