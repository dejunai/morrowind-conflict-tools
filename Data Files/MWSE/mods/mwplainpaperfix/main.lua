--[[
    Plain Paper Fix (mwplainpaperfix)

    Activating a blank sheet (a scroll-type book with no text) puts it straight into the inventory instead of
    opening the empty scroll window. Nothing is scanned in advance: a sheet is tested the first time it is
    activated and, if blank, remembered. Sheets with writing or a picture, and all bound books, open as usual.
    Taking an owned sheet is theft, as it is from the scroll window's Take button.
]]

local NAME = "mwplainpaperfix"
local saved = mwse.loadConfig(NAME, {}) or {}
-- "blank", not the "whitelist" of earlier versions: those lists also hold maps and other picture-only scrolls
local config = { enabled = saved.enabled ~= false, requireSneakForOwned = saved.requireSneakForOwned ~= false, blank = saved.blank or {} }
local function save() mwse.saveConfig(NAME, config) end

local written = {}      -- ids found to have text, this session

local function isBlankSheet(book)
    if book.type ~= tes3.bookType.scroll then return false end
    local id = book.id:lower()
    if config.blank[id] then return true end
    if written[id] then return false end
    local raw = book.text or ""
    local text = raw:gsub("<[^>]*>", ""):gsub("%s+", "")
    if #text > 0 or raw:lower():find("<img", 1, true) then
        written[id] = true
        return false
    end
    config.blank[id] = true
    save()
    return true
end

local function onActivate(e)
    if not config.enabled or e.activator ~= tes3.player then return end
    local ref = e.target
    local book = ref and ref.object
    if not book or book.objectType ~= tes3.objectType.book then return end
    if not isBlankSheet(book) then return end
    local isOwned = not tes3.hasOwnershipAccess({ target = ref })
    if isOwned and config.requireSneakForOwned and not tes3.mobilePlayer.isSneaking then
        return false
    end
    local count = math.max(ref.stackSize or 1, 1)
    local owner = isOwned and tes3.getOwner({ reference = ref }) or nil

    -- the item data goes with the item, so it is unhooked from the world object before that is deleted; a world
    -- object left holding item data the inventory also holds is written twice by a save, which can crash it
    local itemData = ref.itemData
    ref.itemData = nil
    tes3.addItem({ reference = tes3.player, item = book, count = count, itemData = itemData })
    ref:delete()
    if owner then
        tes3.setItemIsStolen({ item = book, from = owner, stolen = true })
        tes3.triggerCrime({ type = tes3.crimeType.theft, victim = owner, value = book.value * count })
    end
    return false
end

event.register("activate", onActivate, { priority = 10 })

event.register("modConfigReady", function()
    local template = mwse.mcm.createTemplate({ name = "Plain Paper Fix", onClose = save })
    local page = template:createPage({ label = "Settings" })
    page:createYesNoButton({
        label = "Pick up blank sheets without opening them",
        variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
    })
    page:createYesNoButton({
        label = "Require sneaking to take owned blank sheets",
        description = "When enabled, activating an owned blank sheet without sneaking does not pick it up into inventory, respecting Accidental Theft Protection.",
        variable = mwse.mcm.createTableVariable({ id = "requireSneakForOwned", table = config }),
    })
    template:register()
end)
