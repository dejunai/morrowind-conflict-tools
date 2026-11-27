-- Ruins'n'Relics (The Wanderer and dietBob) hands the player an "Old Journal" (rnr_old_journal) from its `loaded`
-- handler, every time a game finishes loading that has no do-once flag, and tells you with a tes3.messageBox. On a
-- new game that is a pop-up in the middle of character creation, and the flag it keeps is written to e.reference,
-- a field the loaded event does not have.
-- Here that one handler is swapped for ours the moment the mod registers it (intercept.wrapHandlers; the mod's own
-- event.unregister / isRegistered still work on it). The mod's function never runs, so the journal is never added to
-- the inventory and the message is never shown. Its unequipped / itemDropped handlers are not touched, and its
-- files are not edited. By dej (dejunai).
--
-- The book is put where it can be found instead: on the table in Seyda Neen, Census and Excise Office, in front of the
-- release papers (chargen statssheet) Socucius Ergalla has the player sign. Cell, position and orientation are
-- fixed numbers, read from Morrowind.esm: the table (furn_com_r_table_01) has its top at z 261.3 and the free space on
-- it is a strip along its south edge, left of the Animated Morrowind shipping log and clear of the papers, the paper
-- and ink set and the chest, so the book lies there, long edge along x, at 0.8 scale (the octavo mesh is 32 x 39).
--
--   new game or chargen still pending   the journal is created in that cell (tes3.createReference with the cell, so
--                                       it is there before the player walks in). If the game will not create it in a
--                                       cell that is not loaded yet, a cellChanged handler waits until the player is
--                                       in the office and creates it there, then removes itself. An activate handler
--                                       filtered to that reference (and a has-item check on cellChanged / loaded)
--                                       watches until the book is picked up.
--   a character already past chargen    if the book is not already in the world, it is added to the inventory, with
--                                       no message and no sound. If it was already left on the table, it stays there
--                                       to be picked up (no second copy).
--   already done                        tes3.player.data.mwsuite_rnrJournalPlaced is set once the journal is in the
--                                       inventory (picked up, or added silently), or when a load finds it already
--                                       held, or the mod's own old flag (data.journalid.doOnce). Then every listener
--                                       of ours comes off.
--
-- Once the journal is in the inventory, or that done flag is already set on load, this intercept unloads completely:
-- the loaded wrapper, the cellChanged waiter and the activate pickup detector are all unregistered (afterDispatch,
-- the one-shot pattern used by Ahead of the Classes and Jiub). The mod's original loaded handler is never put back;
-- it is unregistered (or already replaced by our wrapper, which then comes off too). Nothing of ours stays resident.
-- A second new game in one session is blocked outright by mwexitguard/newgame.lua (MGE XE does not reset in-session),
-- so that case no longer comes up. Another save that still needs the journal, loaded in the same session, will not place
-- it and will not show the pop-up either; restarting the game re-arms. Stands down when the toggle is off, the mod is missing, or
-- rnr_old_journal is not in the load order (then nothing is added and no message shows).

local config = require("mwpluginpatches.config")
local intercept = require("mwpluginpatches.intercept")

local this = {}
local active = false
local waiting = false
local watchingPickup = false
local finished = false
local reportedMissing = false
local placedRef = nil

local SOURCE = "/mods/ruines'n'relics/main.lua"
local ITEM = "rnr_old_journal"
local CELL = "Seyda Neen, Census and Excise Office"
local SCALE = 0.8
local FLAG = "mwsuite_rnrJournalPlaced"

this.CELL, this.ITEM, this.FLAG = CELL, ITEM, FLAG

local function log(fmt, ...)
    local ok, text = pcall(string.format, fmt, ...)
    mwse.log("[mwpluginpatches] %s", ok and text or tostring(fmt))
end

local function get(t, k)
    if t == nil then return nil end
    local ok, v = pcall(function() return t[k] end)
    if ok then return v end
    return nil
end

local function markDone()
    local data = get(tes3.player, "data")
    if type(data) == "table" then data[FLAG] = true end
end

-- CharGenState is not -1 while character creation is in progress (the same test Ahead of the Classes uses)
local function charGenPending()
    local g = tes3.findGlobal and tes3.findGlobal("CharGenState")
    local v = get(g, "value")
    return v ~= nil and v ~= -1
end

local function hasJournal()
    local ok, n = pcall(tes3.getItemCount, { reference = tes3.player, item = ITEM })
    return ok and (tonumber(n) or 0) > 0
end

local function alreadyDone()
    local data = get(tes3.player, "data")
    if get(data, FLAG) == true then return true end
    if hasJournal() then return true end
    return get(get(data, "journalid"), "doOnce") == true
end

local function createIn(cell)
    local ok, ref = pcall(tes3.createReference, {
        object = ITEM, cell = cell, scale = SCALE,
        position = { 145, -228, 263.9 }, orientation = { 0, 0, 1.5707964 },
    })
    if ok and ref then return ref end
    if not ok then log("Ruins'n'Relics: could not create the Old Journal in the office yet: %s", tostring(ref)) end
    return nil
end

local function officeCell()
    if tes3.getCell then
        local ok, cell = pcall(tes3.getCell, { id = CELL })
        if ok and cell then return cell end
    end
    if tes3.getPlayerCell then
        local cell = tes3.getPlayerCell()
        local id = get(cell, "id")
        if type(id) == "string" and id:lower() == CELL:lower() then return cell end
    end
    return nil
end

local function nextRef(cell)
    local iter = get(cell, "iterateReferences")
    if type(iter) ~= "function" then return function() return nil end end
    local kind = tes3.objectType and tes3.objectType.book
    local ok, a, b, c = pcall(iter, cell, kind)
    if not ok or type(a) ~= "function" then
        ok, a, b, c = pcall(iter, cell)
    end
    if not ok or type(a) ~= "function" then return function() return nil end end
    return function()
        local step, ref = pcall(a, b, c)
        if not step then return nil end
        c = ref
        return ref
    end
end

local function findWorldJournal()
    local cell = officeCell()
    if not cell then return nil end
    local step = nextRef(cell)
    while true do
        local ref = step()
        if ref == nil then return nil end
        local obj = get(ref, "object") or get(ref, "baseObject")
        local id = get(obj, "id") or get(ref, "id")
        if type(id) == "string" and id:lower() == ITEM:lower() then
            if not get(ref, "deleted") and not get(ref, "disabled") and not get(ref, "isDeleted") then
                return ref
            end
        end
    end
end

local function drop(eventId, fn, options)
    if type(fn) ~= "function" or type(event) ~= "table" or type(event.unregister) ~= "function" then return end
    pcall(event.unregister, eventId, fn, options)
end

-- every listener of ours comes off; the mod's original loaded handler is never put back
local function unloadListeners()
    waiting = false
    watchingPickup = false
    local ref = placedRef
    placedRef = nil
    intercept.afterDispatch(function()
        drop(tes3.event.cellChanged, this.onCellChanged)
        drop(tes3.event.activate, this.onActivate)
        if ref then drop(tes3.event.activate, this.onActivate, { filter = ref }) end
        drop(tes3.event.loaded, this.ourLoaded)
        drop(tes3.event.loaded, this.originalLoaded)
    end)
end

function this.finish()
    if finished then return end
    finished = true
    markDone()
    unloadListeners()
end

function this.onActivate(e)
    if finished then return end
    intercept.afterDispatch(function()
        if hasJournal() then
            log("Ruins'n'Relics: the Old Journal was picked up; this intercept has unloaded.")
            this.finish()
        end
    end)
end

local function watch(ref)
    if finished or ref == nil then return end
    if watchingPickup and placedRef == ref then return end
    if watchingPickup and placedRef and placedRef ~= ref then
        drop(tes3.event.activate, this.onActivate, { filter = placedRef })
        drop(tes3.event.activate, this.onActivate)
        watchingPickup = false
    end
    placedRef = ref
    local ok = pcall(event.register, tes3.event.activate, this.onActivate, { filter = ref })
    if not ok then
        ok = pcall(event.register, tes3.event.activate, this.onActivate)
    end
    watchingPickup = ok and true or false
end


local function stopWaiting()
    waiting = false
end

local function placedOnTable(ref)
    stopWaiting()
    event.register(tes3.event.cellChanged, this.onCellChanged)
    watch(ref)
    log("Ruins'n'Relics: the Old Journal is on the table in the Census and Excise Office.")
end

function this.onCellChanged()
    if finished then return end
    if hasJournal() then
        this.finish()
        return
    end
    if waiting then
        local cell = tes3.getPlayerCell and tes3.getPlayerCell()
        local id = get(cell, "id")
        if type(id) == "string" and id:lower() == CELL:lower() then
            local ref = createIn(cell)
            if ref then placedOnTable(ref) end
        end
        return
    end
    if watchingPickup then return end
    local ref = findWorldJournal()
    if ref then watch(ref) end
end

-- what the mod's loaded handler did, without the pop-up
function this.onLoaded(e)
    if finished then return end
    local data = get(tes3.player, "data")
    if type(data) ~= "table" then return end
    stopWaiting()
    if alreadyDone() then
        log("Ruins'n'Relics: the Old Journal is already settled; this intercept has unloaded.")
        this.finish()
        return
    end
    if tes3.getObject(ITEM) == nil then
        if not reportedMissing then
            reportedMissing = true
            log("Ruins'n'Relics: %s is not in the load order; the journal is not handed out.", ITEM)
        end
        unloadListeners()
        return
    end
    local existing = findWorldJournal()
    if existing then
        event.register(tes3.event.cellChanged, this.onCellChanged)
        watch(existing)
        return
    end
    if not (get(e, "newGame") == true or charGenPending()) then
        local ok, err = pcall(tes3.addItem, { reference = tes3.player, item = ITEM, count = 1, playSound = false })
        if ok then
            log("Ruins'n'Relics: the Old Journal was added to the inventory without a message; this intercept has unloaded.")
            this.finish()
        else
            log("Ruins'n'Relics: could not add the Old Journal: %s", tostring(err))
        end
        return
    end
    local ref = createIn(CELL)
    if ref then
        placedOnTable(ref)
        return
    end
    waiting = true
    event.register(tes3.event.cellChanged, this.onCellChanged)
    this.onCellChanged()
end

function this.init()
    if active then return true end
    if not (config.enabled and config.ruinesRelicsJournalEnabled and config.isRuinesRelicsInstalled()) then
        return false
    end
    active = intercept.wrapHandlers({
        label = "Ruins'n'Relics",
        source = SOURCE,
        event = "loaded",
        what = "journal placement (no pop-up)",
        wrap = function(original)
            this.originalLoaded = original
            this.ourLoaded = function(e)
                local ok, err = pcall(this.onLoaded, e)
                if not ok then log("Ruins'n'Relics: the journal placement raised an error: %s", tostring(err)) end
                return nil
            end
            return this.ourLoaded
        end,
    }) == true
    if active then
        log("Ruins'n'Relics: no pop-up; the Old Journal goes on the table in the Census and Excise Office.")
    end
    return active
end

return this