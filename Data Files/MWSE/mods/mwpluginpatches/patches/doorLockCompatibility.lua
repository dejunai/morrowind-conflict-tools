local config = require("mwpluginpatches.config")

local this = {}
local bypassed = setmetatable({}, { __mode = "k" })

local function isDoor(ref)
    return ref and ref.object and ref.object.objectType == tes3.objectType.door
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

local function beforeActivate(e)
    local door = e.target
    if e.activator ~= tes3.player or not isDoor(door) then
        return
    end

    -- Conceptually, nobody locks you in after hours; they just want you to leave.
    -- When exiting an interior to the exterior, never require sneaking or lockpicking,
    -- even if the door is owned and locked.
    if isInteriorExit(door) then
        if tes3.getLocked({ reference = door }) then
            tes3.unlock({ reference = door })
        end
        door.data = door.data or {}
        if not door.data.ab01drlkbl then
            door.data.ab01drlkbl = 1
            bypassed[door] = true
        end
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
        door.data = door.data or {}
        if not door.data.ab01drlkbl then
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
        door.data.ab01drlkbl = nil
        bypassed[door] = nil
    end
end

function this.init()
    event.register(tes3.event.activate, beforeActivate, { priority = 9200 })
    event.register(tes3.event.activate, afterAbot, { priority = 9000 })
    mwse.log("[mwpluginpatches] Door lock compatibility active (owned-empty locking, free interior exits, sneak-to-pick, standing lock feedback).")
end

return this
