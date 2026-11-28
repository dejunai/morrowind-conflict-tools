--[[
Personal Effects: its Census and Excise scripts, run in Lua (mwpluginpatches calls init when this patch is on and
Personal Effects is active). The ESP's records stay required. The class effects chest is unlocked and filled once,
the legacy scripts are stopped, Sellus Gravius and the door guard keep their facing, and duplicate chests and
player clones are cleaned up. The save keeps its "mwpersonaleffectsFilled" flag name, so a game saved with the
standalone mod is not refilled.
]]

local config = require("mwpluginpatches.config")

local personalEffectsFix = {}
local unlockLogged = false

local CLASS_CONTAINERS = {
    [-1] = { cont = "R0_pe_cont_other",       inv = "R0_pe_inventory_other" },
    [1]  = { cont = "R0_pe_cont_acrobat",     inv = "R0_pe_inventory_acrobat" },
    [2]  = { cont = "R0_pe_cont_agent",       inv = "R0_pe_inventory_agent" },
    [3]  = { cont = "R0_pe_cont_archer",      inv = "R0_pe_inventory_archer" },
    [4]  = { cont = "R0_pe_cont_assassin",    inv = "R0_pe_inventory_assassin" },
    [5]  = { cont = "R0_pe_cont_barbarian",   inv = "R0_pe_inventory_barbarian" },
    [6]  = { cont = "R0_pe_cont_bard",        inv = "R0_pe_inventory_bard" },
    [7]  = { cont = "R0_pe_cont_battlemage",  inv = "R0_pe_inventory_battlemage" },
    [8]  = { cont = "R0_pe_cont_crusader",    inv = "R0_pe_inventory_crusader" },
    [9]  = { cont = "R0_pe_cont_healer",      inv = "R0_pe_inventory_healer" },
    [10] = { cont = "R0_pe_cont_knight",      inv = "R0_pe_inventory_knight" },
    [11] = { cont = "R0_pe_cont_mage",        inv = "R0_pe_inventory_mage" },
    [12] = { cont = "R0_pe_cont_monk",        inv = "R0_pe_inventory_monk" },
    [13] = { cont = "R0_pe_cont_nightblade",  inv = "R0_pe_inventory_nightblade" },
    [14] = { cont = "R0_pe_cont_pilgrim",     inv = "R0_pe_inventory_pilgrim" },
    [15] = { cont = "R0_pe_cont_rogue",       inv = "R0_pe_inventory_rogue" },
    [16] = { cont = "R0_pe_cont_scout",       inv = "R0_pe_inventory_scout" },
    [17] = { cont = "R0_pe_cont_sorcerer",    inv = "R0_pe_inventory_sorcerer" },
    [18] = { cont = "R0_pe_cont_sorcerer",    inv = "R0_pe_inventory_sorcerer" },
    [19] = { cont = "R0_pe_cont_thief",       inv = "R0_pe_inventory_thief" },
    [20] = { cont = "R0_pe_cont_warrior",     inv = "R0_pe_inventory_warrior" },
    [21] = { cont = "R0_pe_cont_witchhunter", inv = "R0_pe_inventory_witchhunter" },
}

local CLASS_NAME_TO_INDEX = {
    ["acrobat"]     = 1,
    ["agent"]       = 2,
    ["archer"]      = 3,
    ["assassin"]    = 4,
    ["barbarian"]   = 5,
    ["bard"]        = 6,
    ["battlemage"]  = 7,
    ["crusader"]    = 8,
    ["healer"]      = 9,
    ["knight"]      = 10,
    ["mage"]        = 11,
    ["monk"]        = 12,
    ["nightblade"]  = 13,
    ["pilgrim"]     = 14,
    ["rogue"]       = 15,
    ["scout"]       = 16,
    ["sorcerer"]    = 17,
    ["spellsword"]  = 18,
    ["thief"]       = 19,
    ["warrior"]     = 20,
    ["witchhunter"] = 21,
}

-- the references this fix uses, looked up when the Census and Excise office loads (a load or a cell change):
-- tes3.getReference scans every cell, so never from the activate handler or the background timer
local REF_IDS = { captain = "chargen captain", guard = "chargen door guard", baseCont = "R0_pe_basecont" }
local cached = {}
local function cacheRefs()
    cached = {}
    for key, id in pairs(REF_IDS) do
        local r = tes3.getReference(id)
        if r then cached[key] = tes3.makeSafeObjectHandle(r) end
    end
end
local function known(key)
    local h = cached[key]
    return h and h:valid() and h:getObject() or nil
end

local function restoreSellusFacing()
    local pCell = tes3.player and tes3.player.cell
    if not pCell or not pCell.id or not pCell.id:lower():find("census and excise") then
        return
    end

    local captain = known("captain")
    if captain and captain.cell == pCell and captain.sceneNode then
        local targetFacing = -math.pi / 2
        captain.facing = targetFacing
        captain.orientation = tes3vector3.new(0, 0, targetFacing)
        pcall(captain.updateSceneGraph, captain)
    end
end

local function restoreDoorGuardFacing()
    local pCell = tes3.player and tes3.player.cell
    if not pCell or not pCell.id or not pCell.id:lower():find("census and excise") then
        return
    end

    local guard = known("guard")
    if guard and guard.cell == pCell and guard.sceneNode then
        -- Do not snap facing while actively in dialogue with the door guard
        local menuDialog = tes3ui.findMenu(tes3ui.registerID("MenuDialog"))
        if menuDialog then
            local mobileActor = menuDialog:getPropertyObject("PartHyperText_actor")
            if mobileActor and mobileActor.reference == guard then
                return
            end
        end

        local targetFacing = math.pi -- 180 degrees: facing South directly into the room
        if math.abs(guard.facing - targetFacing) > 0.05 then
            guard.facing = targetFacing
            guard.orientation = tes3vector3.new(0, 0, targetFacing)
            pcall(guard.updateSceneGraph, guard)
        end
    end
end

--- Executes the chest placement, unlocking, and item distribution cleanly in Lua,
--- stopping and bypassing the legacy R0_pe_init_scr so Face 1605 -376 never executes.
local function handlePersonalEffectsUnlock()
    local cell = tes3.player and tes3.player.cell
    if not cell or not cell.id:lower():find("census and excise") then
        return
    end

    local baseCont = known("baseCont")
    if not baseCont then
        return
    end

    -- Determine class container
    local pClass = tes3.player and tes3.player.object and tes3.player.object.class
    local classId = pClass and pClass.id and pClass.id:lower() or ""
    local classIndex = CLASS_NAME_TO_INDEX[classId]
    local entry

    if classIndex and CLASS_CONTAINERS[classIndex] then
        entry = CLASS_CONTAINERS[classIndex]
    elseif pClass then
        -- Match custom classes by specialization!
        local spec = pClass.specialization
        if spec == tes3.specialization.combat then
            entry = CLASS_CONTAINERS[20] -- warrior
        elseif spec == tes3.specialization.magic then
            entry = CLASS_CONTAINERS[11] -- mage
        elseif spec == tes3.specialization.stealth then
            entry = CLASS_CONTAINERS[19] -- thief
        else
            entry = CLASS_CONTAINERS[-1] -- other
        end
    else
        entry = CLASS_CONTAINERS[-1]
    end

    -- 1. UNLOCK and REMOVE CRIME OWNERSHIP from the chest
    tes3.unlock({ reference = baseCont })
    if baseCont.lockNode then
        baseCont.lockNode.locked = false
        baseCont.lockNode.level = 0
    end
    tes3.setOwner({ reference = baseCont, remove = true })
    baseCont:enable()

    -- 2. Populate chest with class personal effects if empty: once per character (the receipt says so for a save
    -- from before the mark was kept)
    local data = tes3.player.data
    if tes3.getItemCount({ reference = tes3.player, item = entry.inv }) > 0 then
        data.mwpersonaleffectsFilled = true
    end
    local firstTime = not data.mwpersonaleffectsFilled
    local contObj = tes3.getObject(entry.cont)
    if contObj and contObj.inventory then
        local hasItems = false
        if baseCont.object and baseCont.object.inventory then
            for _ in pairs(baseCont.object.inventory) do
                hasItems = true
                break
            end
        end

        if not hasItems and firstTime then
            for _, stack in pairs(contObj.inventory) do
                tes3.addItem({
                    reference = baseCont,
                    item = stack.object,
                    count = stack.count,
                    playSound = false,
                })
            end
        end
    end

    -- 3. Add personal effects inventory receipt note to player
    data.mwpersonaleffectsFilled = true
    if firstTime and tes3.getObject(entry.inv) then
        if tes3.getItemCount({ reference = tes3.player, item = entry.inv }) == 0 then
            tes3.addItem({
                reference = tes3.player,
                item = entry.inv,
                count = 1,
                playSound = false,
            })
        end
    end

    -- 4. Play unlock sound
    tes3.playSound({ sound = "Open Lock", reference = tes3.player })

    -- 5. Delete any stray spawned duplicate chests from previous runs
    for ref in cell:iterateReferences(tes3.objectType.container) do
        if ref ~= baseCont and not ref.disabled and ref.baseObject and ref.baseObject.id:lower():find("^r0_pe_cont_") then
            tes3.transferInventory({ from = ref, to = baseCont, playSound = false, limitCapacity = false })
            ref:disable()
            ref.position = tes3vector3.new(ref.position.x, ref.position.y, ref.position.z - 10000)
            ref.modified = true
        end
    end

    baseCont.modified = true
    restoreSellusFacing()

    if not unlockLogged then
        unlockLogged = true
        mwse.log("[mwpluginpatches] Personal effects chest unlocked and loaded for class '%s'.", classId)
    end
end

function personalEffectsFix.init()
    if not config.personalEffectsEnabled or not config.isPersonalEffectsActive() then
        return
    end

    -- Completely override legacy mwscript R0_pe_init_scr with our Lua handler
    mwse.overrideScript("R0_pe_init_scr", function()
        handlePersonalEffectsUnlock()
        mwscript.stopScript({ script = "R0_pe_init_scr" })
    end)

    -- Completely override R0_pe_basecont_scr (the legacy script containing 'PlaceAtPC Player 1 128 1')
    mwse.overrideScript("R0_pe_basecont_scr", function()
        mwscript.stopScript({ script = "R0_pe_basecont_scr" })
    end)

    -- Completely override R0_pe_MWSE_scr
    mwse.overrideScript("R0_pe_MWSE_scr", function()
        mwscript.stopScript({ script = "R0_pe_MWSE_scr" })
    end)

    -- Guard against Sellus Gravius and Door Guard rotating when dialogue ends, and trigger unlock
    local function onDialog(e)
        local mobileActor = e.element:getPropertyObject("PartHyperText_actor")
        local ref = mobileActor and mobileActor.reference
        if ref and ref.baseObject then
            local refId = ref.baseObject.id:lower()
            if refId == "chargen captain" then
                e.element:registerAfter(tes3.uiEvent.destroy, function()
                    timer.frame.delayOneFrame(function()
                        restoreSellusFacing()
                        if tes3.getJournalIndex({ id = "A1_1_FindSpymaster" }) >= 1 then
                            handlePersonalEffectsUnlock()
                        end
                    end)
                end)
            elseif refId == "chargen door guard" then
                e.element:registerAfter(tes3.uiEvent.destroy, function()
                    timer.frame.delayOneFrame(function()
                        restoreDoorGuardFacing()
                    end)
                end)
            end
        end
    end
    event.register(tes3.event.uiActivated, onDialog, { filter = "MenuDialog" })

    -- Also ensure chest is unlocked and filled if activated directly
    local function onActivate(e)
        if e.target and e.target.baseObject and e.target.baseObject.id:lower() == "r0_pe_basecont" then
            if tes3.getJournalIndex({ id = "A1_1_FindSpymaster" }) >= 1 then
                handlePersonalEffectsUnlock()
            end
        end
    end
    event.register("activate", onActivate)

    local function scheduleFacing()
        local cell = tes3.player and tes3.player.cell
        if not cell or not cell.id or not cell.id:lower():find("census and excise") then
            return
        end
        restoreSellusFacing()
        restoreDoorGuardFacing()
        timer.frame.delayOneFrame(function()
            local currentCell = tes3.player and tes3.player.cell
            if currentCell and currentCell.id and currentCell.id:lower():find("census and excise") then
                restoreSellusFacing()
                restoreDoorGuardFacing()
            end
        end)
        timer.start({ duration = 0.5, type = timer.real, callback = function()
            local currentCell = tes3.player and tes3.player.cell
            if currentCell and currentCell.id and currentCell.id:lower():find("census and excise") then
                restoreSellusFacing()
                restoreDoorGuardFacing()
            end
        end })
    end

    -- Background check once a second, only while the player is in Census & Excise: started when the player is
    -- there (a load or a cell change) and cancelled once they have left, so it is not kept running elsewhere.
    -- MWSE cancels every timer just before `loaded`, so the handle is dropped there.
    local backgroundTimer
    local function inCensusOffice()
        local cell = tes3.player and tes3.player.cell
        return cell ~= nil and cell.id ~= nil and cell.id:lower():find("census and excise") ~= nil
    end
    local function stopBackgroundCheck()
        if backgroundTimer then pcall(function() backgroundTimer:cancel() end) end
        backgroundTimer = nil
    end
    local function syncBackgroundCheck()
        if not inCensusOffice() then
            stopBackgroundCheck()
            return
        end
        if backgroundTimer then return end
        backgroundTimer = timer.start({
            duration = 1.0,
            type = timer.real,
            iterations = -1,
            callback = function()
                if inCensusOffice() then
                    restoreDoorGuardFacing()
                else
                    stopBackgroundCheck()
                end
            end
        })
    end
    personalEffectsFix.backgroundRunning = function() return backgroundTimer ~= nil end   -- for tests

    -- Everything here belongs to chargen. Its handlers go once it is over: at the end of chargen (CharGenState -1,
    -- set as the player leaves the office), and at once when a saved game loads (a game can't be saved during
    -- chargen). The loaded handler stays, so a New Game later in the same session gets them back. The script
    -- overrides above stay too: they cost nothing unless those scripts run again.
    local onLoaded, onCellChanged
    local unloaded = false
    local function unload(reason)
        if unloaded then return end
        unloaded = true
        event.unregister(tes3.event.uiActivated, onDialog, { filter = "MenuDialog" })
        event.unregister("activate", onActivate)
        event.unregister(tes3.event.cellChanged, onCellChanged)
        stopBackgroundCheck()
        cached = {}
        mwse.log("[mwpluginpatches] Personal Effects: %s; handlers removed.", reason)
    end
    personalEffectsFix.unloaded = function() return unloaded end   -- for tests
    local function charGenOver()
        local g = tes3.findGlobal("CharGenState")
        return g ~= nil and g.value == -1
    end
    local function reload()                         -- a New Game after a saved one: chargen again
        if not unloaded then return end
        unloaded = false
        event.register(tes3.event.uiActivated, onDialog, { filter = "MenuDialog" })
        event.register("activate", onActivate)
        event.register(tes3.event.cellChanged, onCellChanged)
    end
    onLoaded = function(e)
        backgroundTimer = nil                       -- cancelled by MWSE before loaded
        if not (e and e.newGame) then return unload("a saved game: chargen is over") end
        reload()
        if inCensusOffice() then cacheRefs() else cached = {} end
        scheduleFacing()
        syncBackgroundCheck()
    end
    onCellChanged = function()
        if not inCensusOffice() and charGenOver() then return unload("chargen is over") end
        if inCensusOffice() then cacheRefs() else cached = {} end
        scheduleFacing()
        syncBackgroundCheck()
    end
    event.register(tes3.event.loaded, onLoaded)
    event.register(tes3.event.cellChanged, onCellChanged)

    mwse.log("[mwpluginpatches] Personal Effects Sellus Gravius & Census Door Guard script overrides and facing fixes active.")
end

return personalEffectsFix
