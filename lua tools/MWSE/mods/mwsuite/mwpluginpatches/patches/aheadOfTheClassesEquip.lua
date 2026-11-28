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
-- Every skipped call is logged with the item id and name, its slot and the reason (repeat, or which item holds the
-- slot), and so is any equip the engine itself refused (tes3.equip returned false).
--
-- The intercept is not kept loaded after it has done its job. It arms only when CharGenState is pending (the same
-- global AotC watches, value ~= -1) and removes its timer.start wrap, tes3.equip wrap and simulate handler once the
-- equip callback has finished (or failed), or 1 s after chargen ends if that callback never ran, or immediately on
-- a save load where chargen is already done. A thin loaded handler stays so a new game started later in the same
-- session can re-arm. timer.start and tes3.equip are restored only when our wrapper is still the current function;
-- if something else wrapped after us, we leave it and our function becomes a pass-through.

local config = require("mwpluginpatches.config")
local intercept = require("mwpluginpatches.intercept")

local this = {}
local ready = false        -- init has registered the loaded hook
local armed = false        -- timer.start is wrapped and we are waiting for the equip pass
local watching = false     -- simulate is registered
local SOURCE = "/mods/danae/classes/main.lua"
local AFTER_CHARGEN = 1.0  -- seconds after CharGenState becomes -1, if AotC's 0.7 s timer never ran

local depth = 0
local savedEquip
local claimed
local equipped, skipped = 0, 0
local savedStart
local ourStart
local afterChargen = nil   -- seconds since we last saw CharGenState == -1 while armed, or nil
local sawPending = false

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

-- same test Ahead of the Classes uses: CharGenState is not -1 while chargen is in progress
local function charGenPending()
    local g = tes3.findGlobal and tes3.findGlobal("CharGenState")
    local v = get(g, "value")
    return v ~= nil and v ~= -1
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

-- an item as "id (name)" for the log
local function label(obj)
    local id, name = get(obj, "id"), get(obj, "name")
    if id == nil then return tostring(obj) end
    if name == nil or name == "" or name == id then return tostring(id) end
    return string.format("%s (%s)", tostring(id), tostring(name))
end

-- what the player wears now, merged with what this pass has already equipped; holders names who holds each slot
local function occupancy()
    local counts, shield, twoHanded, holders = {}, false, false, {}
    pcall(function()
        for _, stack in pairs(tes3.player.object.equipment) do
            local obj = get(stack, "object")
            local key, _, part = describe(obj)
            if key then
                counts[key] = (counts[key] or 0) + 1
                holders[key] = holders[key] or {}
                holders[key][#holders[key] + 1] = label(obj)
                if part == "shield" then shield = shield or label(obj)
                elseif part == "twoHanded" then twoHanded = twoHanded or label(obj) end
            end
        end
    end)
    if claimed then
        for key, n in pairs(claimed.counts) do
            if n > (counts[key] or 0) then
                counts[key] = n
                holders[key] = {}
                for _, who in ipairs(claimed.holders[key] or {}) do holders[key][#holders[key] + 1] = who end
            end
        end
        shield = shield or claimed.shield
        twoHanded = twoHanded or claimed.twoHanded
    end
    return counts, shield, twoHanded, holders
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
    local counts, shield, twoHanded, holders = occupancy()
    local reason
    local who = table.concat(holders[key] or {}, ", ")
    local me = label(item)
    if (counts[key] or 0) >= capacity then
        local repeated = false
        for _, h in ipairs(holders[key] or {}) do if h == me then repeated = true end end
        if repeated then
            reason = "repeat, already equipped in this slot"
        else
            reason = "slot occupied by " .. who
        end
    elseif part == "shield" and twoHanded then
        reason = "shield, but a two-handed weapon is held: " .. tostring(twoHanded)
    elseif part == "twoHanded" and shield then
        reason = "two-handed weapon, but a shield is held: " .. tostring(shield)
    end
    if reason then
        skipped = skipped + 1
        mwse.log("[mwpluginpatches] Ahead of the Classes: skipped %s, slot %s: %s.", me, key, reason)
        return false
    end
    local result = original(params, ...)
    if result == false then
        mwse.log("[mwpluginpatches] Ahead of the Classes: the engine refused %s, slot %s (tes3.equip returned false).", me, key)
    else
        equipped = equipped + 1
        claimed.counts[key] = (claimed.counts[key] or 0) + 1
        claimed.holders[key] = claimed.holders[key] or {}
        claimed.holders[key][#claimed.holders[key] + 1] = me
        if part == "shield" then claimed.shield = claimed.shield or me
        elseif part == "twoHanded" then claimed.twoHanded = claimed.twoHanded or me end
    end
    return result
end

local function restoreEquip()
    if tes3 and tes3.equip == guardedEquip and savedEquip ~= nil then
        tes3.equip = savedEquip
    end
end

local stopWatching, disarm, onLoaded

local function onSimulate(e)
    if not armed then
        intercept.afterDispatch(stopWatching)
        return
    end
    if charGenPending() then
        sawPending = true
        afterChargen = nil
        return
    end
    if not sawPending then
        intercept.afterDispatch(function()
            if armed then disarm("chargen already finished; equip intercept not kept loaded.") end
        end)
        return
    end
    afterChargen = (afterChargen or 0) + (type(e) == "table" and tonumber(e.delta) or 0)
    if afterChargen >= AFTER_CHARGEN then
        intercept.afterDispatch(function()
            if armed then disarm("chargen ended and its equip timer did not run; intercept removed.") end
        end)
    end
end

stopWatching = function()
    if not watching then return end
    watching = false
    event.unregister(tes3.event.simulate, onSimulate)
end

-- take the wraps off if we are still the current function; otherwise stay in the chain as a pass-through
disarm = function(reason)
    -- everything goes, the loaded hook too: mwexitguard blocks a second New Game in a session, so once chargen
    -- is over (or a saved game is loaded) nothing in this session needs it again
    if onLoaded then                             -- not inside the loaded dispatch it may be called from
        intercept.afterDispatch(function() event.unregister(tes3.event.loaded, onLoaded) end)
    end
    restoreEquip()
    claimed = nil
    depth = 0
    armed = false
    afterChargen, sawPending = nil, false
    stopWatching()
    if type(timer) == "table" and ourStart ~= nil and timer.start == ourStart and savedStart ~= nil then
        timer.start = savedStart
    end
    if reason then
        mwse.log("[mwpluginpatches] Ahead of the Classes: %s", reason)
    end
end

local function beginPass()
    depth = depth + 1
    if depth > 1 then return end
    claimed = { counts = {}, holders = {}, shield = false, twoHanded = false }
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
    restoreEquip()
    local n = skipped
    claimed = nil
    if n > 0 then
        mwse.log("[mwpluginpatches] Ahead of the Classes: equipped %d item(s) and skipped %d repeat or occupied-slot equip call(s).",
            equipped, n)
    end
end

local function finish(ok, ...)
    endPass()
    disarm("post-chargen equip pass finished; intercept removed.")
    if not ok then error((...), 0) end
    return ...
end

local function wrapCallback(callback)
    return function(...)
        beginPass()
        return finish(pcall(callback, ...))
    end
end

ourStart = function(params, ...)
    local start = savedStart
    if not armed or type(params) ~= "table" or type(params.callback) ~= "function" or not intercept.calledFrom(SOURCE) then
        return start(params, ...)
    end
    local copy = {}
    for k, v in pairs(params) do copy[k] = v end
    copy.callback = wrapCallback(params.callback)
    return start(copy, ...)
end


local function startWatching()
    if watching then return end
    watching = true
    event.register(tes3.event.simulate, onSimulate)
end

local function arm()
    if armed then return true end
    if type(timer) ~= "table" or type(timer.start) ~= "function" then return false end
    if timer.start ~= ourStart then
        savedStart = timer.start
        timer.start = ourStart
    end
    armed = true
    sawPending, afterChargen = true, nil
    startWatching()
    mwse.log("[mwpluginpatches] Ahead of the Classes: its post-chargen equip pass fills each slot with at most one item.")
    return true
end

-- a saved game: chargen is over (a game can't be saved during it), so the intercept goes at once
onLoaded = function(e)
    if not (config.enabled and config.aotcEquipOnceEnabled and config.isAheadOfTheClassesInstalled()) then
        disarm()
        return
    end
    if type(e) == "table" and e.newGame == false then
        disarm("a saved game: chargen is over; equip intercept not kept loaded.")
        return
    end
    if charGenPending() then
        arm()
    else
        disarm("chargen already finished; equip intercept not kept loaded.")
    end
end

function this.init()
    if ready then return true end
    if not (config.enabled and config.aotcEquipOnceEnabled and config.isAheadOfTheClassesInstalled()) then
        return false
    end
    if type(event) ~= "table" or type(event.register) ~= "function" then return false end
    event.register(tes3.event.loaded, onLoaded)
    ready = true
    -- a game already running (unusual at initialized): arm or unload now
    if tes3.player then onLoaded() end
    mwse.log("[mwpluginpatches] Ahead of the Classes: equip intercept will arm while chargen is pending, then unload.")
    return true
end

return this