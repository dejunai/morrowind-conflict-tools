local NAME = "mwcompanions"

-- abot's water life and birds give their creatures follow/escort packages of their own: never followers
local DEFAULT_PLUGINS = {
    ["abotWaterLife.esm"] = true,
    ["abotWaterLifeTRaddon.esp"] = true,
    ["abotWhereAreAllBirdsGoing.esp"] = true,
}

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
    sheatheAfterCombat = false, -- companions put their weapon away once neither they nor the player fight
    muteOnCellChange = false,  -- followers' Attack/Hello lines are muted right after a cell change (Smart Companions muteCC)
    noSneakActivate = false,   -- activating a follower while sneaking does nothing (Smart Companions)
    -- who is never a follower: every creature a listed plugin defines, and each actor on the blacklist; the whitelist
    -- wins over both. (listsVersion is not a default: a config without it is an older one, migrated below.)
    excludedPlugins = DEFAULT_PLUGINS,   -- plugin file name -> true
    blacklist = {},            -- lower-case base id -> true
    whitelist = {},            -- lower-case base id -> true: never excluded
}

local config = mwse.loadConfig(NAME, defaults)

-- version 1 took Easy Escort's / Attend Me's ignore list (170 ids, nearly all abot's water life and birds) into the
-- blacklist; the plugin list does that job now, so that copy goes, once
if config.listsVersion == nil then
    config.blacklist = {}
    config.whitelist = config.whitelist or {}
    if type(config.excludedPlugins) ~= "table" or next(config.excludedPlugins) == nil then
        config.excludedPlugins = {}
        for k, v in pairs(DEFAULT_PLUGINS) do config.excludedPlugins[k] = v end
    end
    config.imported = nil
    config.listsVersion = 2
    mwse.saveConfig(NAME, config)
end

return config
