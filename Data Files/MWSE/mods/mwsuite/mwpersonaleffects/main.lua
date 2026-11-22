local config = require("mwpersonaleffects.config")

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

local function restoreSellusFacing()
    local pCell = tes3.player and tes3.player.cell
    if not pCell or not pCell.id or not pCell.id:lower():find("census and excise") then
        return
    end

    local captain = tes3.getReference("chargen captain")
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

    local guard = tes3.getReference("chargen door guard")
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

    local baseCont = tes3.getReference("R0_pe_basecont")
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

    -- 2. Populate chest with class personal effects if empty
    local contObj = tes3.getObject(entry.cont)
    if contObj and contObj.inventory then
        local hasItems = false
        if baseCont.object and baseCont.object.inventory then
            for _ in pairs(baseCont.object.inventory) do
                hasItems = true
                break
            end
        end

        if not hasItems then
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
    if tes3.getObject(entry.inv) then
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
        if ref ~= baseCont and ref.baseObject and ref.baseObject.id:lower():find("^r0_pe_cont_") then
            if ref.object and ref.object.inventory then
                for _, stack in pairs(ref.object.inventory) do
                    tes3.addItem({
                        reference = baseCont,
                        item = stack.object,
                        count = stack.count,
                        playSound = false,
                    })
                end
            end
            ref:disable()
            ref.position = tes3vector3.new(ref.position.x, ref.position.y, ref.position.z - 10000)
            ref.modified = true
        end
    end

    baseCont.modified = true
    restoreSellusFacing()

    if not unlockLogged then
        unlockLogged = true
        mwse.log("[mwpersonaleffects] Personal effects chest unlocked and loaded for class '%s'.", classId)
    end
end

function personalEffectsFix.init()
    if not config.enabled or not config.isPersonalEffectsActive() then
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
    event.register(tes3.event.uiActivated, function(e)
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
    end, { filter = "MenuDialog" })

    -- Also ensure chest is unlocked and filled if activated directly
    event.register("activate", function(e)
        if e.target and e.target.baseObject and e.target.baseObject.id:lower() == "r0_pe_basecont" then
            if tes3.getJournalIndex({ id = "A1_1_FindSpymaster" }) >= 1 then
                handlePersonalEffectsUnlock()
            end
        end
    end)

    local function isClone(ref)
        if not ref or ref == tes3.player then return false end
        if ref.objectType ~= tes3.objectType.npc then return false end

        -- 0. Explicit match on PlayerSaveGame dynamic player duplicate
        local refId = ref.id and ref.id:lower()
        if refId and refId:find("playersavegame") then return true end

        -- 1. Base object ID is 'player'
        local baseId = ref.baseObject and ref.baseObject.id and ref.baseObject.id:lower()
        if baseId == "player" then return true end

        -- 2. Object matches player object
        if tes3.player and tes3.player.object and ref.object == tes3.player.object then
            return true
        end

        -- 3. Name matches player name or default engine 'Player'
        local playerName = tes3.player and tes3.player.object and tes3.player.object.name
        if ref.object and ref.object.name then
            if playerName and playerName ~= "" and ref.object.name == playerName then
                return true
            end
            if ref.object.name == "Player" then
                return true
            end
        end

        return false
    end

    local function purgeStaleClones()
        local cell = tes3.player and tes3.player.cell
        if cell and cell.id:lower():find("census and excise") then
            local toPurge = {}
            local purged = 0
            for ref in cell:iterateReferences(tes3.objectType.npc) do
                if isClone(ref) then
                    table.insert(toPurge, ref)
                end
            end
            for _, ref in ipairs(toPurge) do
                local refName = (ref.object and ref.object.name) or "Unknown"
                local refId = (ref.baseObject and ref.baseObject.id) or ref.id or "unknown"
                local ok, err = pcall(function()
                    ref.position = tes3vector3.new(ref.position.x, ref.position.y, ref.position.z - 10000)
                    ref:disable()
                    ref.modified = true
                end)
                if ok then
                    purged = purged + 1
                else
                    mwse.log("[mwpersonaleffects] Could not purge player clone '%s' [%s]: %s",
                        refName, refId, tostring(err))
                end
            end
            if purged > 0 then
                mwse.log("[mwpersonaleffects] Purged %d stale player clone(s) in %s.", purged, cell.id)
            end
        end
    end

    local function schedulePurge()
        local cell = tes3.player and tes3.player.cell
        if not cell or not cell.id or not cell.id:lower():find("census and excise") then
            return
        end
        purgeStaleClones()
        restoreSellusFacing()
        restoreDoorGuardFacing()
        timer.frame.delayOneFrame(function()
            local currentCell = tes3.player and tes3.player.cell
            if currentCell and currentCell.id and currentCell.id:lower():find("census and excise") then
                purgeStaleClones()
                restoreSellusFacing()
                restoreDoorGuardFacing()
            end
        end)
        timer.start({ duration = 0.5, type = timer.real, callback = function()
            local currentCell = tes3.player and tes3.player.cell
            if currentCell and currentCell.id and currentCell.id:lower():find("census and excise") then
                purgeStaleClones()
                restoreSellusFacing()
                restoreDoorGuardFacing()
            end
        end })
    end

    -- Clean up any stale player clone in Census and Excise (from in-game New Game restarts)
    event.register(tes3.event.loaded, schedulePurge)
    event.register(tes3.event.cellChanged, schedulePurge)

    -- Also purge when entering dialogue in Census & Excise
    event.register(tes3.event.uiActivated, function(e)
        purgeStaleClones()
    end, { filter = "MenuDialog" })

    -- Continuous background check while player is in Census & Excise
    -- MWSE cancels every timer just before `loaded`, so it is started again there
    local function startBackgroundCheck()
        timer.start({
            duration = 1.0,
            type = timer.real,
            iterations = -1,
            callback = function()
                local cell = tes3.player and tes3.player.cell
                if cell and cell.id:lower():find("census and excise") then
                    purgeStaleClones()
                    restoreDoorGuardFacing()
                end
            end
        })
    end
    startBackgroundCheck()
    event.register(tes3.event.loaded, startBackgroundCheck)

    mwse.log("[mwpersonaleffects] Personal Effects Sellus Gravius & Census Door Guard script overrides and facing fixes active.")
end

event.register(tes3.event.initialized, function()
    if config.enabled and config.isPersonalEffectsActive() then
        personalEffectsFix.init()
    end
end)
event.register(tes3.event.modConfigReady, function()
    require("mwpersonaleffects.mcm")
end)

return personalEffectsFix
