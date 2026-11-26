-- MWSE Containers Extended looks up an item's linked container with tes3.getReference (a search through every
-- cell's references) on every inventory tile update, tooltip, equip and equipped event. Here, only while those
-- handlers of its main.lua run, tes3.getReference for a plain id is answered from a safe handle kept per id; it is
-- looked up again when that handle is no longer valid or the reference was deleted, and the kept handles are
-- dropped when a save loads. Any other call goes through untouched, tes3.getReference is put back when the handler
-- returns (or fails), and the mod's files are not edited. By dej (dejunai).
--
-- Stays loaded: those handlers run whenever an inventory is open, all session. Stands down when main.lua already
-- has the old luafix edit ("-- local fix (KP4)"), which keeps the same handles inside the file.

local config = require("mwpluginpatches.config")
local intercept = require("mwpluginpatches.intercept")

local this = {}
local active = false
local SOURCE = "/mods/spammer/g7 containers/main.lua"
local EVENTS = { "itemTileUpdated", "uiObjectTooltip", "equip", "equipped" }
this.FILE = "Spammer/G7 Containers/main.lua"
this.MARKER = "-- local fix (KP4)"

local handles = {}

local function held(h)
    if h == nil then return nil end
    local ok, ref = pcall(function()
        if h:valid() then return h:getObject() end
        return nil
    end)
    if not ok or ref == nil then return nil end
    local okDeleted, deleted = pcall(function() return ref.deleted end)
    if not okDeleted or deleted then return nil end
    return ref
end

local function remember(ref)
    if ref == nil or type(tes3.makeSafeObjectHandle) ~= "function" then return nil end
    local ok, h = pcall(tes3.makeSafeObjectHandle, ref)
    return ok and h or nil
end

local function cachedLookup(original)
    return function(id, ...)
        if type(id) ~= "string" or select("#", ...) > 0 then return original(id, ...) end
        local ref = held(handles[id])
        if ref then return ref end
        ref = original(id)
        handles[id] = remember(ref)
        return ref
    end
end

local function finish(previous, mine, ok, ...)
    if tes3.getReference == mine then tes3.getReference = previous end
    if not ok then error((...), 0) end
    return ...
end

local function wrap(original)
    return function(e, ...)
        local previous = tes3.getReference
        if type(previous) ~= "function" then return original(e, ...) end
        local mine = cachedLookup(previous)
        tes3.getReference = mine
        return finish(previous, mine, pcall(original, e, ...))
    end
end

function this.clear()
    handles = {}
end

function this.prepatched()
    return config.modFileHas(this.FILE, this.MARKER) == true
end

function this.init()
    if active then return true end
    if not (config.enabled and config.g7ContainersLinkCacheEnabled and config.isG7ContainersInstalled()) then
        return false
    end
    if this.prepatched() then
        mwse.log("[mwpluginpatches] MWSE Containers Extended: main.lua already keeps its linked containers (old luafix KP4 edit); this intercept stands down.")
        return false
    end
    for _, name in ipairs(EVENTS) do
        if intercept.wrapHandlers({
            label = "MWSE Containers Extended", source = SOURCE, event = name,
            what = "linked-container cache", wrap = wrap,
        }) == true then
            active = true
        end
    end
    if active then
        event.register(tes3.event.load, this.clear)
        mwse.log("[mwpluginpatches] MWSE Containers Extended: a linked container is looked up once and kept, not searched for on every tile and tooltip.")
    end
    return active
end

return this
