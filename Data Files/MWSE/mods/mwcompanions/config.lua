local NAME = "mwcompanions"

-- every switch defaults off (tests\test_guards_default_off.py): the mod does nothing until turned on in its MCM
local defaults = {
    enabled = false,
    warp = false,              -- followers far away or left in another cell warp behind the player (Smart Companions autoWarp)
    warpDistance = 2000,
    levitateWater = false,     -- followers levitate / water walk while the player does (Smart Companions warpLevitate/WaterWalk)
    followerTraits = false,    -- 0 alarm; NPCs: water breathing, acrobatics 150, athletics 220 (Smart Companions fixes)
    noFriendlyFire = false,    -- the player and followers can't hurt each other (Smart Companions, any follower, no aggro)
    resilient = false,         -- a follower collapses instead of dying (Smart Companions followersResiliency)
    collapseSeconds = 90,
    collapseHealth = 75,       -- percent of base health after the collapse
    assist = false,            -- companions attack whoever fights the player (Smart Companions autoAttack, companions only)
    escortSelfDefense = false, -- escorted NPCs fight only who attacks them, never in the player's defense
    escortProtection = false,  -- escorted NPCs can't die: fatigue drains to zero instead, they get up after the fight
    muteOnCellChange = false,  -- followers' Attack/Hello lines are muted right after a cell change (Smart Companions muteCC)
    noSneakActivate = false,   -- activating a follower while sneaking does nothing (Smart Companions)
    blacklist = {},            -- lower-case base id -> true: never a follower
    imported = false,
}

local config = mwse.loadConfig(NAME, defaults)

-- the blacklist the companion suite carried (Easy Escort's ignore list, the same 170 ids in Attend Me) is taken over once
if not config.imported then
    config.imported = true
    local escort = mwse.loadConfig("Easy Escort")
    local attend = mwse.loadConfig("AttendMeMWSE")
    for _, list in ipairs({ escort and escort.ignoreList or {}, attend and attend.blacklist or {} }) do
        for id, on in pairs(list) do
            if on then config.blacklist[tostring(id):lower()] = true end
        end
    end
    mwse.saveConfig(NAME, config)
end

return config
