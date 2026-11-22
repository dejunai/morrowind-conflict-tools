local config = require("mwpluginpatches.config")

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
