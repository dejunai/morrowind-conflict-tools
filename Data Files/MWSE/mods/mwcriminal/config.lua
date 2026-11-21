local NAME = "mwcriminal"

-- every switch defaults off (tests\test_guards_default_off.py): the mod does nothing until turned on in its MCM
local defaults = {
    enabled = false,
    sneakToSteal = false,       -- owned things need sneaking (Accidental Theft Protection)
    readStanding = false,       -- owned books open standing, Take is red (NAT book fix)
    plainPaper = false,         -- blank sheets skip the scroll window (mwplainpaperfix)
    companionDetection = false, -- companions, creatures and blacklisted actors never detect (mwcompanionsneak)
    interiorExit = false,       -- doors out to an exterior are never locked (doorLockCompatibility)
    sneakToPick = false,        -- locked doors/containers need sneaking to pick (doorLockCompatibility)
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

local config = mwse.loadConfig(NAME, defaults)

-- the lists of the mods being retired are taken over once
if not config.imported then
    config.imported = true
    local atp = mwse.loadConfig("noAccidentalTheft")
    local sneak = mwse.loadConfig("mwcompanionsneak")
    for _, list in ipairs({ atp and atp.blacklist or {}, sneak and sneak.blacklist or {} }) do
        for id, on in pairs(list) do
            if on then config.blacklist["obj:" .. tostring(id):lower()] = tostring(id) end
        end
    end
    mwse.saveConfig(NAME, config)
end

return config
