--[[
    Plain Paper Fix (mwplainpaperfix)
    The essential classic mod by its original creator, modernized for MWSE 2.1+.
    Picks up plain paper, blank scrolls, and unwritten documents directly into inventory
    without triggering the reading window popup, while preserving normal reading for written notes.
]]--

local mcm = require("mwplainpaperfix.mcm")

local defaultConfig = {
    enabled = true,
    whitelist = {},
    blacklist = {},
}

local config = mwse.loadConfig("mwplainpaperfix", defaultConfig) or {}
-- Ensure sub-tables exist
config.whitelist = config.whitelist or {}
config.blacklist = config.blacklist or {}

local function hasReadableText(book)
    if not book or not book.text then return false end
    local clean = book.text:gsub("<[^>]*>", ""):gsub("%s+", "")
    return #clean > 0
end

local function onActivate(e)
    if not config.enabled then return end
    if e.activator ~= tes3.player then return end

    local ref = e.target
    if not ref or ref.disabled or ref.deleted then return end

    local obj = ref.object
    if not obj or obj.objectType ~= tes3.objectType.book then return end

    local id = obj.id:lower()

    -- Check whitelist status
    local isWhitelisted = config.whitelist and config.whitelist[id]
    if isWhitelisted == nil then
        -- Dynamic check for first-time encountered items
        if not (config.blacklist and config.blacklist[id]) then
            if not hasReadableText(obj) then
                isWhitelisted = true
                config.whitelist[id] = true
            else
                isWhitelisted = false
                config.blacklist[id] = true
            end
            mwse.saveConfig("mwplainpaperfix", config)
        end
    end

    if not isWhitelisted then
        return -- Item is blacklisted or contains text; read normally
    end

    -- Ownership & Sneak check: require sneak to take owned blank documents
    local isOwned = not tes3.hasOwnershipAccess({ target = ref })
    local isSneaking = (tes3.player.mobile and tes3.player.mobile.isSneaking)
        or (tes3.mobilePlayer and tes3.mobilePlayer.isSneaking)

    if isOwned and not isSneaking then
       -- tes3.messageBox({
       --     message = "You must sneak to take owned documents.",
       --     buttons = { "OK" }
       -- })
        return false -- Consume activation to prevent un-sneaked theft
    end

    -- Pick up directly into inventory
    local count = ref.stackSize or 1

    -- Crime check
    if isOwned then
        local owner = tes3.getOwner(ref)
        local totalValue = (obj.value or 1) * count
        timer.frame.delayOneFrame(function()
            tes3.triggerCrime({ type = tes3.crimeType.theft, victim = owner, value = totalValue })
        end)
    end

    -- Play pickup sound
    tes3.playSound({ sound = "Item Book Up" })

    -- Add to player inventory
    if ref.itemData then
        tes3.addItem({
            reference = tes3.player,
            item = obj,
            count = count,
            itemData = ref.itemData,
            playSound = false,
        })
    else
        tes3.addItem({
            reference = tes3.player,
            item = obj,
            count = count,
            playSound = false,
        })
    end

    -- Safely disable the picked-up reference
    ref:disable()

    return false -- Consume activation event to prevent reading window from opening
end

local function onModConfigReady()
    mcm.register(config, defaultConfig)
end

local function onInitialized()
    event.register("activate", onActivate, { priority = 10 })
    event.register("modConfigReady", onModConfigReady)

    -- First run scan if whitelist is empty
    if not next(config.whitelist) then
        mcm.scanAndClassify(config, false)
    end

    mwse.log("[mwplainpaperfix] Initialized successfully. Direct pickup active for %d whitelisted blank document(s).",
        table.size and table.size(config.whitelist) or 0)
end

event.register("initialized", onInitialized)
