--[[
    mwquicktoggle - pressing the quick key of an item that is already equipped unequips it and restores
    equipment that item displaced.

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

local defaults = { enabled = false, restoreDisplaced = true }
local config = mwse.loadConfig("mwquicktoggle", defaults)
if config.restoreDisplaced == nil then
    config.restoreDisplaced = defaults.restoreDisplaced
end
local qkhe = include("Pirate.QuickKeysHotbarExtended.config")
local armed, pending, blockSlot
local previous = setmetatable({}, { __mode = "k" })

local function equipmentSnapshot()
    local result = {}
    for _, stack in pairs(tes3.player.object.equipment) do
        result[#result + 1] = { item = stack.object, itemData = stack.itemData }
    end
    return result
end

local function rememberDisplaced(item, equipment)
    if not tes3.player.object:hasItemEquipped(item) then return end
    local displaced = {}
    for _, stack in ipairs(equipment) do
        if not tes3.player.object:hasItemEquipped(stack.item, stack.itemData) then
            displaced[#displaced + 1] = stack
        end
    end
    previous[item] = #displaced > 0 and displaced or nil
end

local function toggleOff(item)
    tes3.mobilePlayer:unequip({ item = item })
    local displaced = config.restoreDisplaced and previous[item] or nil
    previous[item] = nil
    for _, stack in ipairs(displaced or {}) do
        tes3.mobilePlayer:equip({ item = stack.item, itemData = stack.itemData })
    end
end

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
    armed, pending = nil, nil
    if not config.enabled or not slot or tes3.menuMode() or not tes3.mobilePlayer then return end
    local item = boundItem(slot)
    if item and TOGGLE[item.objectType] then
        if tes3.player.object:hasItemEquipped(item) then
            armed = { slot = slot, item = item }
        elseif config.restoreDisplaced then
            pending = { item = item, equipment = equipmentSnapshot() }
        end
    end
end

local function after()
    local a = armed
    local p = pending
    armed, pending = nil, nil
    if not tes3.mobilePlayer then return end
    if a then
        toggleOff(a.item)
        blockSlot = a.slot
        timer.delayOneFrame(function() blockSlot = nil end)
    elseif p then
        timer.delayOneFrame(function() rememberDisplaced(p.item, p.equipment) end)
    end
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

event.register("weaponReadied", function(e)
    if not config.enabled or not config.restoreDisplaced then return end
    if e.reference ~= tes3.player then return end
    local light = tes3.getEquippedItem({ actor = tes3.player, objectType = tes3.objectType.light })
    local displaced = light and previous[light.object]
    for _, stack in ipairs(displaced or {}) do
        if stack.item.objectType == tes3.objectType.armor and stack.item.slot == tes3.armorSlot.shield then
            toggleOff(light.object)
            return
        end
    end
end)

event.register("loaded", function()
    armed, pending, blockSlot = nil, nil, nil
    previous = setmetatable({}, { __mode = "k" })
end)

event.register("modConfigReady", function()
    local template = mwse.mcm.createTemplate({ name = "Quick Key Toggle",
        onClose = function() mwse.saveConfig("mwquicktoggle", config) end })
    local page = template:createSideBarPage({ label = "Settings" })
    page.sidebar:createInfo({ text = "Pressing the quick key of a weapon, armor, clothing or light that is "
        .. "already equipped unequips it and restores displaced equipment. Readying a weapon also replaces "
        .. "a toggled light with its remembered shield. Works with vanilla quick keys and QuickKeys Hotbar Extended." })
    page:createYesNoButton({
        label = "Quick keys unequip equipped items",
        description = "Press an equipped item's quick key again to unequip it.",
        variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
    })
    page:createYesNoButton({
        label = "Restore displaced equipment",
        description = "When unequipping an item via its quick key, or when readying a weapon with a toggled light, re-equip the equipment it replaced (such as a shield replaced by a lantern or two-handed weapon).",
        variable = mwse.mcm.createTableVariable({ id = "restoreDisplaced", table = config }),
    })
    template:register()
end)
