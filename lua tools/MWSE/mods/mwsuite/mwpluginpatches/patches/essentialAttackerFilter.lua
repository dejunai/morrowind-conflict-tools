-- Essential Indicators shows its "thread of prophecy" warning whenever an essential NPC takes damage,
-- whoever hits them. Here the warning is held back unless the hit came from the player, a creature the
-- player summoned, or the player's projectile or spell. Its damage handling is unchanged. Replaces part of
-- an old hand edit of Essential Indicators\main.lua; that file stays as released. By dej (dejunai).

local config = require("mwpluginpatches.config")
local intercept = require("mwpluginpatches.intercept")

local this = {}
local active = false
local SOURCE = "/mods/essential indicators/main.lua"
local PREFIX = "This character's death would result in the thread of prophecy"

local current -- the damage event being handled by Essential Indicators, nil otherwise

local function get(t, k)
    if t == nil then return nil end
    local ok, v = pcall(function() return t[k] end)
    if ok then return v end
    return nil
end

local function isPlayerReference(ref)
    return ref ~= nil and tes3.player ~= nil and ref == tes3.player
end

local function isPlayerMobile(mobile)
    if mobile == nil then return false end
    if tes3.mobilePlayer ~= nil and mobile == tes3.mobilePlayer then return true end
    return isPlayerReference(get(mobile, "reference"))
end

-- a summon effect the player cast on themself holds the summoned creature's reference
local function isPlayerSummon(ref)
    if ref == nil or tes3.mobilePlayer == nil then return false end
    local list = get(tes3.mobilePlayer, "activeMagicEffectList")
    if type(list) ~= "table" then return false end
    for _, effect in ipairs(list) do
        if get(effect, "isSummon") then
            local stack = get(get(effect, "effectInstance"), "createdData")
            if stack ~= nil and get(stack, "object") == ref then return true end
        end
    end
    return false
end

function this.isPlayerSide(e)
    if type(e) ~= "table" then return false end
    local attacker = get(e, "attacker")
    local attackerRef = get(e, "attackerReference") or get(attacker, "reference")
    if isPlayerMobile(attacker) or isPlayerReference(attackerRef) then return true end
    if isPlayerSummon(attackerRef) then return true end
    local projectile = get(e, "projectile")
    if projectile ~= nil then
        if isPlayerMobile(get(projectile, "firingMobile")) or isPlayerReference(get(projectile, "firingReference")) then
            return true
        end
    end
    local magic = get(e, "magicSourceInstance")
    if magic ~= nil and isPlayerReference(get(magic, "caster")) then return true end
    return false
end

local function finish(previous, ok, ...)
    current = previous
    if not ok then error((...), 0) end
    return ...
end

function this.init()
    if active then return true end
    if not (config.enabled and config.essentialAttackerFilterEnabled and config.isEssentialIndicatorsInstalled()) then
        return false
    end
    local wrapped = intercept.wrapHandlers({
        label = "Essential Indicators",
        source = SOURCE,
        event = "damage",
        what = "attacker check",
        wrap = function(original)
            return function(e, ...)
                local previous = current
                current = e
                return finish(previous, pcall(original, e, ...))
            end
        end,
    })
    local dropped = wrapped and intercept.messageBoxDrop({
        label = "Essential Indicators",
        source = SOURCE,
        prefix = PREFIX,
        when = function() return current ~= nil and not this.isPlayerSide(current) end,
    })
    active = wrapped == true and dropped == true
    if active then
        mwse.log("[mwpluginpatches] Essential Indicators: its essential-NPC warning shows only for the player's own hits.")
    end
    return active
end

return this
