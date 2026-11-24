--[[mwdialog_luafix 4: A1]] --[[
    Graphic Herbalism Respawn Delay Patch
    Mod: Graphic Herbalism (MWSE)
    Graphic Herbalism shows a herb picked until the engine restocks it (the next day). This keeps a picked herb
    picked for config.herbRespawnDays days. It works with Graphic Herbalism's own state: ref.data.GH (1 picked,
    2 spoiled) and its "HerbalismSwitch" node (named children HARVESTED/PICKED, SPOILED, NORMAL; a mesh without one
    is hidden while picked).
--]]

local config = require("mwpluginpatches.config")

local this = {}

local DEFAULT_RESPAWN_DAYS = 3
local MIN_RESPAWN_DAYS = 1
local MAX_RESPAWN_DAYS = 90

local function isHerb(ref)
    return ref and ref.object and ref.object.objectType == tes3.objectType.container and ref.object.organic
        and ref.sceneNode ~= nil
end

local function today()
    return (tes3.getGlobal and tes3.getGlobal("DaysPassed")) or 0
end

local function respawnDays()
    local configured = tonumber(config.herbRespawnDays)
    if not configured then return DEFAULT_RESPAWN_DAYS end
    return math.max(MIN_RESPAWN_DAYS, math.min(MAX_RESPAWN_DAYS, math.floor(configured)))
end

-- Graphic Herbalism's look for a state: 0 normal, 1 picked, 2 spoiled.
local function showState(ref, index)
    local sceneNode = ref.sceneNode
    if not sceneNode then return end
    local switchNode = sceneNode:getObjectByName("HerbalismSwitch")
    if switchNode and switchNode.switchIndex ~= nil then
        local names = index == 1 and { "HARVESTED", "PICKED" } or index == 2 and { "SPOILED" } or { "NORMAL" }
        local target = index
        for _, name in ipairs(names) do
            local found = switchNode:getChildIndexByName(name)
            if type(found) == "number" and found >= 0 then
                target = found
                break
            end
        end
        switchNode.switchIndex = math.min(math.max(target, 0), #switchNode.children - 1)
        sceneNode.appCulled = false
    else
        sceneNode.appCulled = index > 0
    end
    sceneNode:update()
end

-- Graphic Herbalism fires containerClosed right after it picks a herb (ref.data.GH set): the day is noted then.
local function onContainerClosed(e)
    local ref = e.reference
    if isHerb(ref) and ref.data and (ref.data and ref.data.GH) and not (ref.data and ref.data.GH_harvestDay) then
        if ref.data then ref.data.GH_harvestDay = today() end
    end
end

-- A picked herb stays picked until its days have passed, whatever the engine's restock did meanwhile.
local function enforce(ref)
    if not isHerb(ref) or not ref.data or not ref.data.GH_harvestDay then return end
    if today() - ref.data.GH_harvestDay < respawnDays() then
        ref.data.GH = ref.data.GH or 1                  -- keeps "spoiled" (2) as it is
        ref.isEmpty = true
        showState(ref, ref.data.GH)
    else
        ref.data.GH_harvestDay = nil
        ref.data.GH = nil
        ref.isEmpty = false
        showState(ref, 0)
    end
end

local function onCellChanged()
    for _, cell in ipairs(tes3.getActiveCells()) do
        for ref in cell:iterateReferences(tes3.objectType.container) do
            enforce(ref)
        end
    end
end

local function onReferenceActivated(e)
    enforce(e.reference)
end

function this.init()
    event.register("containerClosed", onContainerClosed)
    -- after Graphic Herbalism's own handlers (priority 0), which reset a restocked herb
    event.register("cellChanged", onCellChanged, { priority = -100 })
    event.register("referenceActivated", onReferenceActivated, { priority = -100 })
    mwse.log("[mwpluginpatches] Graphic Herbalism respawn delay patch active (cooldown: %d days).", respawnDays())
end

this.enforce = enforce                                 -- for tests

return this
