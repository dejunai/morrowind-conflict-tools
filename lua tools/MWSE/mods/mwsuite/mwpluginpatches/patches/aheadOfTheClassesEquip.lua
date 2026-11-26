-- Ahead of the Classes (Danae) gives the new character class gear when chargen ends: a 0.7 s timer runs startClass(),
-- whose addGear() adds the items and then loops pairs(tes3.player.object.inventory), calling tes3.equip on every
-- armor, weapon and clothing stack. Equipping changes the inventory while it is walked, so the same items come round
-- again (about 28 calls), and several items for one slot just swap each other in and out.
-- Here, only while that one timer callback runs, tes3.equip is guarded for the player: each slot takes at most one
-- item. A slot already filled, before the pass or by an earlier equip in it, is skipped, and a skipped item does not
-- use the slot up. The adding of gear is untouched, tes3.equip is put back when the callback returns (or fails), and
-- the mod's files are not edited. By dej (dejunai).
--
-- Slots come from the object itself, no id lists: armor by its armor slot, clothing by its clothing slot (two rings
-- fit, one per hand), weapons one in the weapon slot, arrows, bolts and thrown weapons one in the ammunition slot.
-- A two-handed weapon (or bow) and a shield do not go together: whichever came first stays, the other is skipped.

local config = require("mwpluginpatches.config")
local intercept = require("mwpluginpatches.intercept")

local this = {}
local active = false
local SOURCE = "/mods/danae/classes/main.lua"

local depth = 0        -- how many of the mod's timer callbacks are running (1 in practice)
local savedEquip       -- the tes3.equip that was in place when the pass began (kept, so a copy of the guard taken in the pass still works)
local claimed          -- this pass: { counts = { [slot key] = n }, shield = bool, twoHanded = bool }
local equipped, skipped = 0, 0

local function get(t, k)
    if t == nil then return nil end
    local ok, v = pcall(function() return t[k] end)
    if ok then return v end
    return nil
end

local function constant(group, name)
    local t = tes3 and tes3[group]
    if type(t) ~= "table" then return nil end
    return get(t, name)
end

-- the slot an item goes in: key, how many fit, and a part (shield / twoHanded) for the weapon-shield rule
local function describe(obj)
    local kind = get(obj, "objectType")
    if kind == nil then return nil end
    if kind == constant("objectType", "weapon") then
        local wt = get(obj, "type")
        if wt ~= nil and (wt == constant("weaponType", "arrow") or wt == constant("weaponType", "bolt")
            or wt == constant("weaponType", "marksmanThrown")) then
            return "ammo", 1
        end
        local two = get(obj, "isTwoHanded") == true
            or (wt ~= nil and (wt == constant("weaponType", "marksmanBow") or wt == constant("weaponType", "marksmanCrossbow")))
        return "weapon", 1, two and "twoHanded" or nil
    elseif kind == constant("objectType", "armor") then
        local slot = get(obj, "slot")
        if slot == nil then return nil end
        return "armor" .. tostring(slot), 1, (slot == constant("armorSlot", "shield")) and "shield" or nil
    elseif kind == constant("objectType", "clothing") then
        local slot = get(obj, "slot")
        if slot == nil then return nil end
        return "clothing" .. tostring(slot), (slot == constant("clothingSlot", "ring")) and 2 or 1
    end
    return nil
end

-- what the player wears now, merged with what this pass has already equipped
local function occupancy()
    local counts, shield, twoHanded = {}, false, false
    pcall(function()
        for _, stack in pairs(tes3.player.object.equipment) do
            local key, _, part = describe(get(stack, "object"))
            if key then
                counts[key] = (counts[key] or 0) + 1
                if part == "shield" then shield = true elseif part == "twoHanded" then twoHanded = true end
            end
        end
    end)
    if claimed then
        for key, n in pairs(claimed.counts) do
            if n > (counts[key] or 0) then counts[key] = n end
        end
        shield = shield or claimed.shield
        twoHanded = twoHanded or claimed.twoHanded
    end
    return counts, shield, twoHanded
end

local function isPlayer(params)
    local ref = get(params, "reference")
    if ref == nil then ref = get(get(params, "mobile"), "reference") end
    return ref ~= nil and tes3.player ~= nil and ref == tes3.player
end

local function guardedEquip(params, ...)
    local original = savedEquip or tes3.equip
    if depth == 0 or type(params) ~= "table" or not isPlayer(params) then
        return original(params, ...)
    end
    local item = get(params, "item")
    if type(item) == "string" then item = tes3.getObject(item) end
    local key, capacity, part = describe(item)
    if not key then return original(params, ...) end
    local counts, shield, twoHanded = occupancy()
    local full = (counts[key] or 0) >= capacity
        or (part == "shield" and twoHanded) or (part == "twoHanded" and shield)
    if full then
        skipped = skipped + 1
        return false
    end
    local result = original(params, ...)
    if result ~= false then
        equipped = equipped + 1
        claimed.counts[key] = (claimed.counts[key] or 0) + 1
        if part == "shield" then claimed.shield = true elseif part == "twoHanded" then claimed.twoHanded = true end
    end
    return result
end

local function beginPass()
    depth = depth + 1
    if depth > 1 then return end
    claimed = { counts = {}, shield = false, twoHanded = false }
    equipped, skipped = 0, 0
    if type(tes3.equip) == "function" and tes3.equip ~= guardedEquip then
        savedEquip = tes3.equip
        tes3.equip = guardedEquip
    end
end

local function endPass()
    depth = depth - 1
    if depth > 0 then return end
    depth = 0
    if tes3.equip == guardedEquip and savedEquip ~= nil then tes3.equip = savedEquip end
    local n = skipped
    claimed = nil
    if n > 0 then
        mwse.log("[mwpluginpatches] Ahead of the Classes: equipped %d item(s) and skipped %d repeat or occupied-slot equip call(s).",
            equipped, n)
    end
end

local function finish(ok, ...)
    endPass()
    if not ok then error((...), 0) end
    return ...
end

local function wrapCallback(callback)
    return function(...)
        beginPass()
        return finish(pcall(callback, ...))
    end
end

function this.init()
    if active then return true end
    if not (config.enabled and config.aotcEquipOnceEnabled and config.isAheadOfTheClassesInstalled()) then
        return false
    end
    if type(timer) ~= "table" or type(timer.start) ~= "function" then return false end
    local nativeStart = timer.start
    timer.start = function(params, ...)
        if type(params) == "table" and type(params.callback) == "function" and intercept.calledFrom(SOURCE) then
            local copy = {}
            for k, v in pairs(params) do copy[k] = v end
            copy.callback = wrapCallback(params.callback)
            return nativeStart(copy, ...)
        end
        return nativeStart(params, ...)
    end
    active = true
    mwse.log("[mwpluginpatches] Ahead of the Classes: its post-chargen equip pass fills each slot with at most one item.")
    return true
end

return this