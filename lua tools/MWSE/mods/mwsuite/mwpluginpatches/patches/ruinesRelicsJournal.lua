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
--   new game or chargen still pending   the journal is created in that cell straight away (tes3.createReference with
--                                       the cell, so it is there before the player walks in). If the game will not
--                                       create it in a cell that is not loaded yet, a cellChanged handler waits until
--                                       the player is in the office and creates it there, then removes itself.
--   a character already past chargen    nobody goes back to that desk, so the journal is added to the inventory, with
--                                       no message and no sound (the same thing the mod did, minus the pop-up).
--   already done                        tes3.player.data.mwsuite_rnrJournalPlaced is set once the journal is placed or
--                                       given. Nothing more happens on later loads. The mod's own old flag
--                                       (data.journalid.doOnce), or a journal already in the inventory, also counts.
--
-- Cost afterwards: our swapped-in handler stays registered (it has to, so the mod's can never come back; a new game
-- later in the same session needs it too). Each load it reads one flag and returns. The cellChanged handler exists
-- only while the journal is still waiting for the office. Stands down when the toggle is off, the mod is missing, or
-- rnr_old_journal is not in the load order (then nothing is added and no message shows).

local config = require("mwpluginpatches.config")
local intercept = require("mwpluginpatches.intercept")

local this = {}
local active = false
local waiting = false
local reportedMissing = false

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

local function createIn(cell)
    local ok, ref = pcall(tes3.createReference, {
        object = ITEM, cell = cell, scale = SCALE,
        position = { 145, -228, 263.9 }, orientation = { 0, 0, 1.5707964 },
    })
    if ok and ref then return ref end
    if not ok then log("Ruins'n'Relics: could not create the Old Journal in the office yet: %s", tostring(ref)) end
    return nil
end

local function stopWaiting()
    if not waiting then return end
    waiting = false
    local function drop()
        if not waiting then event.unregister(tes3.event.cellChanged, this.onCellChanged) end
    end
    intercept.afterDispatch(drop)
end

function this.onCellChanged()
    if not waiting then return end
    local data = get(tes3.player, "data")
    if type(data) ~= "table" then return end
    local cell = tes3.getPlayerCell and tes3.getPlayerCell()
    local id = get(cell, "id")
    if type(id) ~= "string" or id:lower() ~= CELL:lower() then return end
    if createIn(cell) then
        data[FLAG] = true
        log("Ruins'n'Relics: the Old Journal is on the table in the Census and Excise Office.")
        stopWaiting()
    end
end

-- what the mod's loaded handler did, without the pop-up
function this.onLoaded(e)
    local data = get(tes3.player, "data")
    if type(data) ~= "table" then return end
    stopWaiting()
    if data[FLAG] then return end
    if tes3.getObject(ITEM) == nil then
        if not reportedMissing then
            reportedMissing = true
            log("Ruins'n'Relics: %s is not in the load order; the journal is not handed out.", ITEM)
        end
        return
    end
    local old = get(data, "journalid")
    if hasJournal() or get(old, "doOnce") == true then
        data[FLAG] = true
        return
    end
    if not (get(e, "newGame") == true or charGenPending()) then
        local ok, err = pcall(tes3.addItem, { reference = tes3.player, item = ITEM, count = 1, playSound = false })
        if ok then
            data[FLAG] = true
            log("Ruins'n'Relics: the Old Journal was added to the inventory without a message.")
        else
            log("Ruins'n'Relics: could not add the Old Journal: %s", tostring(err))
        end
        return
    end
    if createIn(CELL) then
        data[FLAG] = true
        log("Ruins'n'Relics: the Old Journal is on the table in the Census and Excise Office.")
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
        wrap = function()
            return function(e)
                local ok, err = pcall(this.onLoaded, e)
                if not ok then log("Ruins'n'Relics: the journal placement raised an error: %s", tostring(err)) end
                return nil
            end
        end,
    }) == true
    if active then
        log("Ruins'n'Relics: no pop-up; the Old Journal goes on the table in the Census and Excise Office.")
    end
    return active
end

return this