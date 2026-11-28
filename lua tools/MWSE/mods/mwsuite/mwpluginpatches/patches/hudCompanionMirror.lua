--[[
    mwpluginpatches - HUD Companion Health Bar mirror

    mwcompanions keeps a list of actors that are never followers (its Excluded Plugins, Blacklist and Whitelist
    pages: abot's water life and birds follow the player on scripts of their own). HUD Companion Health Bar has a
    blacklist of its own and no interop, so those creatures got a health bar. This keeps the two lists the same:

    - an actor added to HUD Companion Health Bar's blacklist goes on mwcompanions' blacklist;
    - one taken off it may be a follower again in mwcompanions (off its blacklist, onto its whitelist when an
      excluded plugin defines it);
    - whatever mwcompanions adds or takes off (a new entry, a whitelisted creature, a plugin taken off) is added to
      or taken off HUD Companion Health Bar's blacklist, under the game's own spelling of the id (its check is
      case-sensitive).

    What each side held at the last sync is kept in MWSE\config\mwpluginpatches_hudmirror.json, so a change is
    known by the side it was made on. It syncs when a game loads, after mwcompanions' Mod Config menu closes, and
    when you leave the menus (after HUD Companion Health Bar's own menu). Neither mod's files are edited: its config
    table is the one its own code reads, and it is saved the way its menu saves it.
]]

local this = {}

local HUD_CONFIG = "Pirate.HUD Companion Health Bar.config"
local HUD_SAVE = "HUD_Companion_Health_Bar"
local STATE = "mwpluginpatches_hudmirror"

local function lowerSet(t)
    local out = {}
    for k, v in pairs(t or {}) do
        if v then out[tostring(k):lower()] = true end
    end
    return out
end

local function gameId(id)
    local ok, obj = pcall(tes3.getObject, id)
    return ok and obj and obj.id or id
end

local function dropAnyCase(t, id)
    for k in pairs(t) do
        if tostring(k):lower() == id then t[k] = nil end
    end
end

--- one sync of the two lists; returns (changes made to mwcompanions, changes made to HUD Companion Health Bar)
function this.sync()
    local okH, hud = pcall(require, HUD_CONFIG)
    local okC, comp = pcall(require, "mwcompanions.core")
    if not (okH and type(hud) == "table" and type(hud.mcm) == "table" and okC and type(comp) == "table"
            and comp.neverFollowers) then
        return 0, 0
    end
    hud.mcm.blackList = hud.mcm.blackList or {}
    local list = hud.mcm.blackList
    local state = mwse.loadConfig(STATE) or {}
    local first = type(state.hud) ~= "table" or type(state.mwc) ~= "table"
    local H, M = lowerSet(list), comp.neverFollowers()
    local toComp, toHud = 0, 0

    -- what was changed in HUD Companion Health Bar since the last sync goes to mwcompanions
    for id in pairs(H) do
        if not M[id] and (first or not state.hud[id]) then
            comp.exclude(id)
            toComp = toComp + 1
        end
    end
    if not first then
        for id in pairs(state.hud) do
            if not H[id] and M[id] then
                comp.include(id)
                toComp = toComp + 1
            end
        end
    end
    if toComp > 0 then
        comp.saveLists()
        M = comp.neverFollowers()
    end

    -- mwcompanions' list, as it is now, goes to HUD Companion Health Bar
    for id in pairs(M) do
        if not H[id] then
            list[gameId(id)] = true
            toHud = toHud + 1
        end
    end
    if not first then
        for id in pairs(state.mwc) do
            if not M[id] and H[id] then
                dropAnyCase(list, id)
                toHud = toHud + 1
            end
        end
    end
    if toHud > 0 then
        mwse.saveConfig(HUD_SAVE, hud.mcm)
    end
    mwse.saveConfig(STATE, { hud = lowerSet(list), mwc = M })
    if toComp + toHud > 0 then
        mwse.log("[mwpluginpatches] HUD Companion Health Bar mirror: %d change(s) to mwcompanions, %d to HUD Companion "
            .. "Health Bar", toComp, toHud)
    end
    return toComp, toHud
end

local function safeSync()
    local ok, err = pcall(this.sync)
    if not ok then mwse.log("[mwpluginpatches] HUD Companion Health Bar mirror failed: %s", tostring(err)) end
end

function this.init()
    event.register(tes3.event.loaded, safeSync)
    event.register("mwcompanions:changed", safeSync, { priority = -100 })   -- after mwcompanions rebuilds its list
    event.register(tes3.event.menuExit, safeSync)
    mwse.log("[mwpluginpatches] HUD Companion Health Bar blacklist mirrors mwcompanions' never-followers list.")
end

return this
