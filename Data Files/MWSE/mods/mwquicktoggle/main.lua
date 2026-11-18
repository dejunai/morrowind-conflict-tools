--[[
    mwquicktoggle - pressing the quick key of an item that is already equipped unequips it.

    Works with the vanilla quick keys and with mods that equip from the same keys. QuickKeys Hotbar Extended's
    three bars are read from its own data (its modifier keys pick the bar). How: before any other handler sees
    the key press, note whether the bound item is equipped; after every handler has run, unequip it if it was,
    and block the game's own quick-key test for that key this frame so it doesn't equip it straight back.
    Magic and enchanted-item slots are left alone (selecting a spell is not equipping).
]]

local TOGGLE = {
    [tes3.objectType.weapon] = true,     -- includes arrows, bolts and thrown weapons
    [tes3.objectType.armor] = true,
    [tes3.objectType.clothing] = true,
    [tes3.objectType.light] = true,
}

local qkhe = include("Pirate.QuickKeysHotbarExtended.config")
local armed, blockSlot

-- QuickKeys Hotbar Extended's bar for this press, or nil when it isn't handling the quick keys
local function qkheBar()
    local cf = qkhe and qkhe.mcm
    if not (cf and cf.HotBarExtended) then return nil end
    local ic = tes3.worldController.inputController
    local m2 = cf.modifierKey2 and ic:isKeyDown(cf.modifierKey2.keyCode)
    local m3 = cf.modifierKey3 and ic:isKeyDown(cf.modifierKey3.keyCode)
    if m2 and not m3 then return "quick2" end
    if m3 and not m2 then return "quickH" end
    return "quick_"
end

local function boundItem(slot)
    local bar = qkheBar()
    if bar then
        local d = tes3.player.data.quickKeys
        local s = d and d[bar] and d[bar][slot]
        if not s or s.isMagic or s.id == nil or s.id == 0 then return nil end
        return tes3.getObject(s.id)
    end
    if slot > 9 then return nil end
    local qk = tes3.getQuickKey({ slot = slot })
    if qk and qk.type == tes3.quickKeyType.item then return qk.item end
end

local function slotFor(code, mouse)
    for i = 1, 10 do
        local b = tes3.getInputBinding(tes3.keybind["quick" .. i])
        if b and b.code == code and (b.device == 1) == mouse then return i end
    end
end

local function before(slot)
    armed = nil
    if not slot or tes3.menuMode() or not tes3.mobilePlayer then return end
    local item = boundItem(slot)
    if item and TOGGLE[item.objectType] and tes3.player.object:hasItemEquipped(item) then
        armed = { slot = slot, item = item }
    end
end

local function after()
    local a = armed
    armed = nil
    if not a or not tes3.mobilePlayer then return end
    tes3.mobilePlayer:unequip({ item = a.item })
    blockSlot = a.slot
    timer.delayOneFrame(function() blockSlot = nil end)
end

event.register("keyDown", function(e) before(slotFor(e.keyCode, false)) end, { priority = 10000 })
event.register("keyDown", after, { priority = -10000 })
event.register("mouseButtonDown", function(e) before(slotFor(e.button, true)) end, { priority = 10000 })
event.register("mouseButtonDown", after, { priority = -10000 })

event.register("keybindTested", function(e)
    if blockSlot and e.result and e.keybind == tes3.keybind["quick" .. blockSlot] then
        e.result = false
    end
end)

event.register("loaded", function() armed, blockSlot = nil, nil end)
