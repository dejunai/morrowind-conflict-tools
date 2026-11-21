--[[
    mwcriminal: sneaking, theft and door locks in one place.
    One activate handler (priority 9300, above abot Door Locks and Modern Lockpicking so it decides first), one
    detectSneak handler and one book-menu hook. Each behavior has its own MCM switch; all start off.
]]
local config = require("mwcriminal.config")
local core = require("mwcriminal.core")

local NAME = "mwcriminal"
local function save() mwse.saveConfig(NAME, config) end

local ownedBookOpen = false   -- the book being opened is someone else's and the player is standing
local opener                  -- { ref, position, facing, cell } of the NPC who answered the last knock
local knockSound

local function lockedFeedback(ref)
    local isDoor = ref.object.objectType == tes3.objectType.door
    tes3.playSound({ sound = isDoor and "LockedDoor" or "LockedChest", reference = ref })
    if config.lockedNotification then tes3ui.showNotifyMenu(isDoor and "The door is locked." or "It is locked.") end
end

local function restoreOpener()
    if not opener then return end
    local o = opener
    opener = nil
    local ref = o.ref:valid() and o.ref:getObject()
    if ref then
        ref.position = o.position
        ref.facing = o.facing
    end
end

-- the NPC inside opens: they are moved in front of the arrival marker, facing the player
local function knock(door)
    local who = core.opener(door, tes3.worldController.hour.value)
    if not who then return false end
    restoreOpener()
    local marker = door.destination.marker
    if marker then
        opener = { ref = tes3.makeSafeObjectHandle(who), position = who.position:copy(), facing = who.facing,
            cell = door.destination.cell }
        who.position = marker.position + marker.forwardDirection * 72
        local facing = marker.facing + math.pi
        who.facing = facing > math.pi and facing - 2 * math.pi or facing
    end
    if knockSound then tes3.playSound({ sound = knockSound }) end
    tes3.unlock({ reference = door })
    door.data.mwcriminalLocked = nil
    tes3ui.showNotifyMenu(who.object.name .. " opens the door.")
    return true
end

local function onDoor(door)
    if core.isExit(door) then
        if config.interiorExit and tes3.getLocked({ reference = door }) then
            tes3.unlock({ reference = door })
            door.data.mwcriminalLocked = nil
        end
        return
    end
    if config.eveningLocks then
        local verdict = core.lockVerdict(door, tes3.worldController.hour.value)
        if verdict then core.applyVerdict(door, verdict) end
    end
    if not tes3.getLocked({ reference = door }) or core.hasKey(door) or core.isSneaking() then return end
    if config.knocking and door.destination and not door.object.script and knock(door) then return end
    if config.sneakToPick then
        lockedFeedback(door)
        return false
    end
end

local function takeSheet(ref, book)
    local owned = core.isOwned(ref)
    if owned and not core.isSneaking() then return false end
    local count = math.max(ref.stackSize or 1, 1)
    local owner = owned and tes3.getOwner({ reference = ref }) or nil
    -- the item data goes with the item: a world object left holding it is written twice by a save, which can crash it
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

local function addToBlacklist(ref)
    local key = core.blacklistKey(ref)
    if config.blacklist[key] then
        tes3.messageBox("%s is already on the mwcriminal blacklist.", ref.object.name or ref.object.id)
        return
    end
    config.blacklist[key] = string.format("%s (%s)", ref.object.name ~= "" and ref.object.name or ref.object.id,
        ref.cell.displayName or ref.cell.id)
    save()
    tes3.messageBox("%s added to the mwcriminal blacklist (remove it in the mod's settings).", config.blacklist[key])
end

local function onActivate(e)
    ownedBookOpen = false
    if not config.enabled or e.activator ~= tes3.player then return end
    local ref = e.target
    if tes3.worldController.inputController:isShiftDown() then
        addToBlacklist(ref)
        return false
    end
    if core.isBlacklisted(ref) then return end
    local obj = ref.object
    local t = obj.objectType
    if t == tes3.objectType.door then return onDoor(ref) end
    local sneaking = core.isSneaking()
    if t == tes3.objectType.container and tes3.getLocked({ reference = ref }) and not core.hasKey(ref) then
        if sneaking then return end
        if config.sneakToPick then
            lockedFeedback(ref)
            return false
        end
    end
    if t == tes3.objectType.book then
        if config.plainPaper and core.isBlankSheet(obj) then return takeSheet(ref, obj) end
        if config.readStanding and not sneaking and core.isOwned(ref) then
            ownedBookOpen = true
            return
        end
    end
    if config.sneakToSteal and not sneaking and core.isOwned(ref) then return false end
end

local function onBookMenu(e)
    if not ownedBookOpen then return end
    ownedBookOpen = false
    local take = e.element:findChild("MenuBook_button_take") or e.element:findChild("MenuBook_PickupButton")
        or e.element:findChild("MenuScroll_Pickup")
    if not take then return end
    local red = tes3ui.getPalette("negative_color")
    take.color = red
    for _, child in ipairs(take.children) do child.color = red end
    e.element:updateLayout()
end

local function onDetectSneak(e)
    if not (config.enabled and config.companionDetection) or e.target ~= tes3.mobilePlayer then return end
    local d = e.detector
    if not d or not core.ignoredDetector(d) then return end
    e.isDetected = false
    d.isPlayerDetected = false
    d.isPlayerHidden = true
    local ok, so = pcall(require, "StormAtronach.SO.interop")
    if ok and so and so.clearSuspicion then pcall(so.clearSuspicion, d.reference) end
    return false   -- Stealth Overhaul (priority 1000) never sees it
end

-- Essential Indicators: the crosshair is tinted while it rests on something locked the player has no key for
local ei
local function onTargetChanged(e)
    if not ei then return end
    local ref = e.current
    local t = ref and ref.object.objectType
    if config.enabled and config.lockedCrosshair and (t == tes3.objectType.door or t == tes3.objectType.container)
        and tes3.getLocked({ reference = ref }) and not core.hasKey(ref) and not core.isBlacklisted(ref) then
        ei.registerColorOverride(1.0, 0.55, 0.1, 1.0, NAME, 900)
    else
        ei.deregisterColorOverride(NAME)
    end
end

local function onCellChanged(e)
    if opener and e.previousCell == opener.cell then restoreOpener() end
end

-- one MWSE.log line per switch that duplicates an original mod still switched on
local function warnOverlaps()
    local function on(name, key, default)
        local c = mwse.loadConfig(name)
        if c == nil then return default end
        return c[key] == true
    end
    local pp = mwse.loadConfig("mwpluginpatches") or {}
    local checks = {
        { config.plainPaper, on("mwplainpaperfix", "enabled", false), "mwplainpaperfix" },
        { config.sneakToSteal, on("noAccidentalTheft", "enabled", lfs.fileexists("Data Files\\MWSE\\mods\\mer\\accidentalTheftProtection\\main.lua")), "Accidental Theft Protection" },
        { config.readStanding, pp.enabled == true and pp.noAccidentalTheftBookFixEnabled == true, "mwpluginpatches book fix" },
        { config.companionDetection, on("mwcompanionsneak", "enabled", false), "mwcompanionsneak" },
        { config.interiorExit or config.sneakToPick, pp.enabled == true and pp.doorLockCompatibilityEnabled == true, "mwpluginpatches door lock compatibility" },
        { config.eveningLocks or config.knocking, on("abotDoor_Locks", "modEnabled", lfs.fileexists("Data Files\\MWSE\\mods\\abot\\Door Locks\\main.lua")), "abot Door Locks" },
    }
    for _, c in ipairs(checks) do
        if c[1] and c[2] then mwse.log("[mwcriminal] %s is still switched on and overlaps a mwcriminal switch: turn one off", c[3]) end
    end
end

event.register(tes3.event.initialized, function()
    knockSound = tes3.getSound("ab01KnockKnockSND")
    if not knockSound and tes3.getFileExists("Sound\\abot\\knockdoor.wav") then
        knockSound = tes3.createObject({ objectType = tes3.objectType.sound, id = "ab01KnockKnockSND",
            filename = "abot\\knockdoor.wav", volume = 1 })
    end
    event.register(tes3.event.activate, onActivate, { priority = 9300 })
    event.register(tes3.event.uiActivated, onBookMenu, { filter = "MenuBook" })
    event.register(tes3.event.uiActivated, onBookMenu, { filter = "MenuScroll" })
    event.register(tes3.event.detectSneak, onDetectSneak, { priority = 2000 })
    event.register(tes3.event.cellChanged, onCellChanged)
    local ok, interop = pcall(require, "Essential Indicators.interop")
    if ok and type(interop) == "table" then
        ei = interop
        event.register(tes3.event.activationTargetChanged, onTargetChanged)
        -- a lock picked or opened in a menu (Modern Lockpicking) leaves the same target in view
        event.register(tes3.event.menuExit, function() onTargetChanged({ current = tes3.getPlayerTarget() }) end)
    end
    if config.enabled then warnOverlaps() end
end)
event.register(tes3.event.loaded, function() opener = nil end)
event.register(tes3.event.modConfigReady, function() require("mwcriminal.mcm") end)
