local this = {}
local bypassed = setmetatable({}, { __mode = "k" })

local function isArrilleCell(cell)
    return cell and cell.id and cell.id:find("Arrille's Tradehouse")
end

local function isRented()
    local rentGlobal = (tes3.getGlobal and tes3.getGlobal("Rent_Arrille"))
        or (tes3.findGlobal and tes3.findGlobal("Rent_Arrille") and tes3.findGlobal("Rent_Arrille").value)
    return rentGlobal == 1
end

local function setDisabled(ref, disabled)
    if disabled and not ref.disabled then
        ref:disable()
    elseif not disabled and ref.disabled then
        ref:enable()
    end
end

local function unlockRental(ref)
    if tes3.getLocked({ reference = ref }) then
        tes3.unlock({ reference = ref })
    end
    if ref.lockNode then ref.lockNode.locked = false end
end

local function bypassAbot(ref)
    if ref.data and not ref.data.ab01drlkbl then
        ref.data.ab01drlkbl = 1
        bypassed[ref] = true
    end
end

local function syncArrilleInnDoors(cell)
    cell = cell or (tes3.player and tes3.player.cell)
    if not isArrilleCell(cell) then return end
    local rented = isRented()
    for ref in cell:iterateReferences(tes3.objectType.door) do
        local objId = ref.object and ref.object.id and ref.object.id:lower()
        if objId == "dim_com_m_trapdoor_b" then
            setDisabled(ref, rented)
        elseif objId == "rent_arrille_door" and rented then
            unlockRental(ref)
        end
    end
end

local function beforeActivate(e)
    local door = e.target
    if e.activator ~= tes3.player or not (door and door.object
        and door.object.objectType == tes3.objectType.door) then return end
    local objId = door.object.id and door.object.id:lower()
    if objId ~= "dim_com_m_trapdoor_b" and objId ~= "rent_arrille_door" then return end
    local cell = door.cell or (tes3.player and tes3.player.cell)
    if not isArrilleCell(cell) or not isRented() then return end

    if objId == "dim_com_m_trapdoor_b" then
        setDisabled(door, true)
        for ref in cell:iterateReferences(tes3.objectType.door) do
            if ref.object and ref.object.id and ref.object.id:lower() == "rent_arrille_door" then
                unlockRental(ref)
                bypassAbot(ref)
                tes3.player:activate(ref)
                return false
            end
        end
    else
        unlockRental(door)
        bypassAbot(door)
    end
end

local function afterAbot(e)
    local door = e.target
    if bypassed[door] then
        if door.data then door.data.ab01drlkbl = nil end
        bypassed[door] = nil
    end
end

this.syncArrilleInnDoors = syncArrilleInnDoors

function this.init()
    event.register(tes3.event.activate, beforeActivate, { priority = 9400 })
    event.register(tes3.event.activate, afterAbot, { priority = 9000 })
    event.register(tes3.event.cellChanged, function(e) syncArrilleInnDoors(e and e.cell) end, { priority = 0 })
    mwse.log("[mwpluginpatches] Arrille's Tradehouse duplicate-door compatibility active.")
end

return this
