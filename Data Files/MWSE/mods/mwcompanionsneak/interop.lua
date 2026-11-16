local config = require("mwcompanionsneak.config")

local interop = {}

local soInterop = nil
pcall(function()
    soInterop = require("StormAtronach.SO.interop")
end)

--- Checks if an actor is currently fighting the player.
--- @param mobile tes3mobileActor
--- @return boolean
local function actorFightsPlayer(mobile)
    if not mobile or not mobile.inCombat then return false end
    local hostiles = mobile.hostileActors
    if hostiles then
        for _, actor in ipairs(hostiles) do
            if actor and actor.reference == tes3.player then
                return true
            end
        end
    end
    return false
end

--- Determines whether a mobile actor is a follower / companion of the player.
--- @param mobile tes3mobileActor|nil
--- @return boolean
function interop.isCompanion(mobile)
    if not mobile or mobile == tes3.mobilePlayer then return false end

    -- Verify valid live reference
    local ref = mobile.reference
    if not ref or not ref:isValid() or ref.disabled or mobile.isDead then
        return false
    end

    -- If the actor is actively fighting the player, they are an enemy, not a companion
    if actorFightsPlayer(mobile) then
        return false
    end

    -- Filter creature companions if disabled by configuration
    if not config.includeCreatures and mobile.actorType == tes3.actorType.creature then
        return false
    end

    -- Guards are never companions
    local obj = ref.baseObject or ref.object
    if obj then
        if obj.isGuard then return false end
        local class = obj.class
        if class and (class.id:lower():find("guard") or (class.name and class.name:lower():find("guard"))) then
            return false
        end
    end

    -- 1. Active AI Package check (follow or escort targeting player)
    local planner = mobile.aiPlanner
    if planner then
        local ok, package = pcall(function() return planner:getActivePackage() end)
        if ok and package then
            local ptype = package.type
            local isFollow = (ptype == tes3.aiPackage.follow)
            local isEscort = (config.includeEscorts and ptype == tes3.aiPackage.escort)

            if isFollow or isEscort then
                local targetActor = package.targetActor
                if targetActor == tes3.mobilePlayer or (targetActor and targetActor.reference == tes3.player) then
                    return true
                end
                local target = package.target
                if target == tes3.player or target == tes3.mobilePlayer then
                    return true
                end
            end
        end
    end

    -- 2. Player's friendlyActors table check
    if tes3.mobilePlayer and tes3.mobilePlayer.friendlyActors then
        for friendly in tes3.iterate(tes3.mobilePlayer.friendlyActors) do
            if friendly == mobile then
                return true
            end
        end
    end

    -- 3. Attend Me custom marker
    if ref.data and ref.data.attendMeCompanion == true then
        return true
    end

    -- 4. Attend Me interop check
    local hasAttendMe, attendMe = pcall(require, "AttendMeMWSE.followers")
    if hasAttendMe and attendMe and attendMe.isFollower then
        local ok, isFol = pcall(attendMe.isFollower, ref)
        if ok and isFol then
            return true
        end
    end

    -- 5. Safe script local variable check for NPCs ('companion' variable convention)
    if mobile.actorType == tes3.actorType.npc then
        local base = ref.baseObject
        if base and base.script then
            local s = base.script
            local hasCompanionVar = false
            local lists = { s.shortVariableNames, s.longVariableNames, s.shortVarNames, s.longVarNames }
            for _, list in ipairs(lists) do
                if type(list) == "table" then
                    for _, n in pairs(list) do
                        if type(n) == "string" and n:lower() == "companion" then
                            hasCompanionVar = true
                            break
                        end
                    end
                end
                if hasCompanionVar then break end
            end

            if hasCompanionVar and ref.context then
                local ok, val = pcall(function() return ref.context.companion end)
                if ok and val == 1 then
                    return true
                end
            end
        end
    end

    return false
end

--- Determines whether an actor or reference is blacklisted from stealth detection.
--- Supports automatic creature blacklisting and custom entity ID blacklisting.
--- @param actor tes3mobileActor|tes3reference|nil
--- @return boolean
function interop.isBlacklisted(actor)
    if not actor then return false end
    local ref = actor.reference or actor
    if not ref or not ref.object then return false end

    -- 1. Automatic creature blacklist
    if config.blacklistAllCreatures then
        local obj = ref.object
        if obj.objectType == tes3.objectType.creature or (obj.baseObject and obj.baseObject.objectType == tes3.objectType.creature) then
            return true
        end
        if actor.actorType == tes3.actorType.creature then
            return true
        end
    end

    -- 2. Custom entity ID blacklist
    local bl = config.blacklist
    if bl then
        local baseId = ref.object.id and ref.object.id:lower()
        if baseId and bl[baseId] then
            return true
        end
        local instId = ref.id and ref.id:lower()
        if instId and bl[instId] then
            return true
        end
    end

    return false
end

--- Adds an entity ID to the blacklist and saves config.
--- @param id string
function interop.blacklistEntity(id)
    if not id or id == "" then return end
    config.blacklist = config.blacklist or {}
    config.blacklist[id:lower()] = true
    mwse.saveConfig("mwcompanionsneak", config)
end

--- Removes an entity ID from the blacklist and saves config.
--- @param id string
function interop.unblacklistEntity(id)
    if not id or id == "" or not config.blacklist then return end
    config.blacklist[id:lower()] = nil
    mwse.saveConfig("mwcompanionsneak", config)
end

--- Clears suspicion for an actor in active stealth overhauls if present.
--- @param ref tes3reference
function interop.clearSuspicion(ref)
    if not ref then return end
    if soInterop and soInterop.isEnabled() then
        pcall(soInterop.clearSuspicion, ref)
    end
end

return interop
