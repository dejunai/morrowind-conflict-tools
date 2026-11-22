local NAME = "mwcriminal"

-- every switch defaults off (tests\test_guards_default_off.py): the mod does nothing until turned on in its MCM
local defaults = {
    enabled = false,
    sneakToSteal = false,       -- owned things need sneaking (Accidental Theft Protection)
    readStanding = false,       -- owned books open standing, Take is red (NAT book fix)
    plainPaper = false,         -- blank sheets skip the scroll window (mwplainpaperfix)
    plainPaperRequireSneak = true,
    companionDetection = false, -- companions, creatures and blacklisted actors never detect
    includeCreatures = true,
    includeEscorts = true,
    blacklistAllCreatures = true,
    companionBlacklist = {},
    inspectorKey = {
        keyCode = tes3.scanCode.k,
        isShiftDown = false,
        isAltDown = false,
        isControlDown = false,
    },
    debugMode = false,
    interiorExit = false,       -- doors out to an exterior are never locked
    sneakToPick = false,        -- locked doors/containers need sneaking to pick
    lockedNotification = false, -- "Locked" notice next to the locked sound
    lockedCrosshair = false,    -- Essential Indicators crosshair tinted on locked targets without a key
    eveningLocks = false,       -- owned/occupied homes lock in the evening (abot Door Locks)
    knocking = false,           -- a standing activation of a locked door knocks (abot Door Locks)
    openHour = 7,
    closeHour = 19,
    knockUntilHour = 22,
    lockLevel = 38,
    highLockLevel = 58,
    publicNames = { "tavern", "inn", "club", "cornerclub", "temple", "shrine", "chapel", "guild", "plaza",
        "district", "market", "waistworks", "underworks", "canton", "council", "hall", "fort" },
    highSecurityNames = { "bank", "vault" },
    blacklist = {},             -- key -> label; "obj:<id>" or "ref:<cell>|<id>|<x>,<y>"
    imported = false,
}

local config = mwse.loadConfig(NAME, defaults) or defaults
local storedConfig = mwse.loadConfig(NAME)
local hasStoredConfig = storedConfig ~= nil
if lfs and lfs.fileexists then
    hasStoredConfig = lfs.fileexists("Data Files\\MWSE\\config\\mwcriminal.json")
end
for key, value in pairs(defaults) do
    if config[key] == nil then config[key] = value end
end
config.companionBlacklist = config.companionBlacklist or {}
config.blacklist = config.blacklist or {}
config.inspectorKey = config.inspectorKey or defaults.inspectorKey

local shouldSave = false
if not config.plainPaperSettingsImported then
    config.plainPaperSettingsImported = true
    local paper = mwse.loadConfig("mwplainpaperfix")
    if paper then
        if not storedConfig or storedConfig.plainPaper == nil then
            config.plainPaper = paper.enabled == true
        end
        if not storedConfig or storedConfig.plainPaperRequireSneak == nil then
            config.plainPaperRequireSneak = paper.requireSneakForOwned ~= false
        end
        if not hasStoredConfig and paper.enabled == true then
            config.enabled = paper.enabled == true
        end
    end
    shouldSave = true
end

if not config.bookFixSettingsImported then
    config.bookFixSettingsImported = true
    local patches = mwse.loadConfig("mwpluginpatches")
    if patches and patches.enabled == true and patches.noAccidentalTheftBookFixEnabled == true then
        if not storedConfig or storedConfig.readStanding == nil then
            config.readStanding = true
        end
        if not hasStoredConfig then config.enabled = patches.enabled == true end
    end
    shouldSave = true
end

if not config.imported then
    config.imported = true
    local atp = mwse.loadConfig("noAccidentalTheft")
    for id, on in pairs(atp and atp.blacklist or {}) do
        if on then config.blacklist["obj:" .. tostring(id):lower()] = tostring(id) end
    end
    shouldSave = true
end

if not config.companionSettingsImported then
    config.companionSettingsImported = true
    local sneak = mwse.loadConfig("mwcompanionsneak")
    if sneak then
        local importedAny = false
        for id, on in pairs(sneak.blacklist or {}) do
            if on then
                config.companionBlacklist[tostring(id):lower()] = true
                importedAny = true
            end
        end
        if not importedAny then
            config.companionBlacklist["_rooster300000000"] = true
            config.companionBlacklist["_chicken_stationary00000000"] = true
            local so = mwse.loadConfig("Stealth_Overhaul")
            for id, on in pairs(so and so.blacklist or {}) do
                if on then config.companionBlacklist[tostring(id):lower()] = true end
            end
        end
        config.includeCreatures = sneak.includeCreatures ~= false
        config.includeEscorts = sneak.includeEscorts ~= false
        config.blacklistAllCreatures = sneak.blacklistAllCreatures ~= false
        config.inspectorKey = sneak.inspectorKey or config.inspectorKey
        config.debugMode = sneak.debugMode == true
        if not hasStoredConfig and sneak.enabled == true then
            config.enabled = sneak.enabled == true
            config.companionDetection = true
        end
    end
    shouldSave = true
end

if shouldSave then
    mwse.saveConfig(NAME, config)
end

return config
