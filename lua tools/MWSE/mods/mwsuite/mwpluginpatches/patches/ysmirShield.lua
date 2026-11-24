local config = require("mwpluginpatches.config")

local ysmirShield = {}

local combatSpellId = "exo_nord_combat_shield"
local combatSpell = nil

local function isNordNPC(mobile)
    if not mobile or not mobile.reference then
        return false
    end
    -- Do not auto-cast on player; player controls their own magic
    if mobile == tes3.mobilePlayer then
        return false
    end
    local obj = mobile.reference.baseObject
    if not obj or obj.objectType ~= tes3.objectType.npc then
        return false
    end
    local race = obj.race
    return (race and race.id:lower() == "nord")
end

local function onCombatStarted(e)
    if not config.ysmirShieldEnabled or not config.isYsmirActive() then
        return
    end

    local actor = e.actor
    if not isNordNPC(actor) or not combatSpell or actor.isDead then
        return
    end

    if not actor:isAffectedByObject(combatSpell) then
        tes3.cast({
            reference = actor.reference,
            target = actor.reference,
            spell = combatSpell,
            instant = true,
            alwaysSucceeds = true,
        })
    end
end

local function onCombatStopped(e)
    if not config.ysmirShieldEnabled or not config.isYsmirActive() then
        return
    end

    local actor = e.actor
    if not isNordNPC(actor) or not combatSpell then
        return
    end

    -- Dismiss combat shield once fight ends so NPCs do not stand around in bubbles
    if actor:isAffectedByObject(combatSpell) then
        tes3.removeEffects({
            reference = actor.reference,
            effect = tes3.effect.shield,
            castType = tes3.spellType.spell,
        })
    end
end

function ysmirShield.init()
    if not config.ysmirShieldEnabled or not config.isYsmirActive() then
        return
    end

    -- 1. Ensure the passive racial ability never emits a persistent shield bubble
    local ysmirPassive = tes3.getObject("exo_nord_ysmirshield")
    if ysmirPassive then
        for _, effect in ipairs(ysmirPassive.effects) do
            if effect.id == tes3.effect.shield then
                effect.id = -1
                effect.min = 0
                effect.max = 0
            end
        end
    end

    -- 2. Create the combat-only shield spell
    combatSpell = tes3.getObject(combatSpellId)
    if not combatSpell then
        combatSpell = tes3.createObject({
            objectType = tes3.objectType.spell,
            id = combatSpellId,
            name = "Ysmir's Shield",
            type = tes3.spellType.spell,
        })

        local eff = combatSpell.effects[1]
        eff.id = tes3.effect.shield
        eff.rangeType = tes3.effectRange.self
        eff.min = 20
        eff.max = 20
        eff.duration = 60
    end

    event.register("combatStarted", onCombatStarted)
    event.register("combatStopped", onCombatStopped)

    mwse.log("[mwpluginpatches] Ysmir's Combat Shield fix active (Nord visual bubble suppressed outside combat).")
end

return ysmirShield
