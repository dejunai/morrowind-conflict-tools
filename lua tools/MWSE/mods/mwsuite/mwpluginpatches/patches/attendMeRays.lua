-- Attend Me (MWSE) casts the same 65536-unit eye ray up to four times in one frame while its command wheel is open
-- (the Move, Loot and Action labels each cast one, the target HUD another). Nothing in the world moves inside one
-- simulate pass, so here, only while its simulate handler runs, a repeat of the same ray (same start, direction,
-- length and ignore list) gets the first answer's reference instead of a new cast. Those callers only read
-- .reference; MWSE reuses one result object per rayTest, so the reference is kept, not the result. Any other
-- rayTest (other options, or outside that handler) goes through untouched, tes3.rayTest is put back when the
-- handler returns (or fails), and the mod's files are not edited. By dej (dejunai).
--
-- Stays loaded: the handler runs every frame for the whole session. Stands down when actions.lua already has the
-- old luafix edit ("-- local fix (KP1)"), which does the same thing inside the file, so the two never stack.

local config = require("mwpluginpatches.config")
local intercept = require("mwpluginpatches.intercept")

local this = {}
local active = false
local SOURCE = "/mods/attendmemwse/actions.lua"
this.FILE = "AttendMeMWSE/actions.lua"
this.MARKER = "-- local fix (KP1)"

local PLAIN = { position = true, direction = true, maxDistance = true, ignore = true }

local function same3(a, b)
    if a == b then return true end
    if a == nil or b == nil then return false end
    return a.x == b.x and a.y == b.y and a.z == b.z
end

local function sameList(a, b)
    if a == b then return true end
    if type(a) ~= "table" or type(b) ~= "table" or #a ~= #b then return false end
    for i = 1, #a do
        if a[i] ~= b[i] then return false end
    end
    return true
end

-- a plain eye-ray call: a table with only position / direction / maxDistance / ignore, ignore a list
local function plain(p)
    if type(p) ~= "table" then return false end
    for k in pairs(p) do
        if not PLAIN[k] then return false end
    end
    return p.ignore == nil or type(p.ignore) == "table"
end

local function snapshot(v)
    if v == nil then return nil end
    return { x = v.x, y = v.y, z = v.z }
end

local function listCopy(t)
    if t == nil then return nil end
    local c = {}
    for i = 1, #t do c[i] = t[i] end
    return c
end

-- one memo per handler call: a few rays at most, so a short list is enough
local function sharedRays(original)
    local seen = {}
    return function(p, ...)
        if select("#", ...) > 0 or not plain(p) then return original(p, ...) end
        for i = 1, #seen do
            local s = seen[i]
            if s.maxDistance == p.maxDistance and same3(s.position, p.position) and same3(s.direction, p.direction)
                and sameList(s.ignore, p.ignore) then
                return s.hit or nil
            end
        end
        local hit = original(p)
        local ok, ref = pcall(function() return hit and hit.reference end)
        if not ok then return hit end
        seen[#seen + 1] = {
            position = snapshot(p.position), direction = snapshot(p.direction), maxDistance = p.maxDistance,
            ignore = listCopy(p.ignore), hit = hit and { reference = ref } or false,
        }
        return hit
    end
end

local function finish(previous, mine, ok, ...)
    if tes3.rayTest == mine then tes3.rayTest = previous end
    if not ok then error((...), 0) end
    return ...
end

function this.prepatched()
    return config.modFileHas(this.FILE, this.MARKER) == true
end

function this.init()
    if active then return true end
    if not (config.enabled and config.attendMeRaysEnabled and config.isAttendMeInstalled()) then
        return false
    end
    if this.prepatched() then
        mwse.log("[mwpluginpatches] Attend Me: actions.lua already shares its eye rays (old luafix KP1 edit); this intercept stands down.")
        return false
    end
    active = intercept.wrapHandlers({
        label = "Attend Me",
        source = SOURCE,
        event = "simulate",
        what = "shared eye ray",
        wrap = function(original)
            return function(e, ...)
                local previous = tes3.rayTest
                if type(previous) ~= "function" then return original(e, ...) end
                local mine = sharedRays(previous)
                tes3.rayTest = mine
                return finish(previous, mine, pcall(original, e, ...))
            end
        end,
    }) == true
    if active then
        mwse.log("[mwpluginpatches] Attend Me: its command wheel casts one eye ray per ignore set per frame.")
    end
    return active
end

return this
