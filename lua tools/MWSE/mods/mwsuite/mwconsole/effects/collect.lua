--[[
    mwconsole effects data (no UI): what magic is on a reference, and the purge.
    Remaining time is duration minus the instance's elapsed time (timeActive).
]]
local collect = {}

collect.SPELL_TYPES = { [0] = "Spell", [1] = "Ability", [2] = "Blight", [3] = "Disease", [4] = "Curse", [5] = "Power" }

local function effectName(id)
    local ok, mgef = pcall(tes3.getMagicEffect, id)
    return (ok and mgef and mgef.name) or string.format("Effect #%s", tostring(id))
end
collect.effectName = effectName

function collect.isActor(ref)
    if not ref then return false end
    if ref == tes3.player then return true end
    local obj = ref.baseObject or ref.object
    local t = obj and obj.objectType
    return t == tes3.objectType.npc or t == tes3.objectType.creature
end

--- still safe to touch: not deleted, still has a cell (loaded), not disabled since it was picked
function collect.isValid(ref)
    if not ref then return false end
    local ok, valid = pcall(function()
        if ref.deleted or ref.disabled then return false end
        if ref ~= tes3.player and not ref.cell then return false end
        return true
    end)
    return ok and valid
end

function collect.isDead(ref)
    local ok, dead = pcall(function() return ref.mobile and ref.mobile.isDead end)
    return ok and dead == true
end

function collect.active(ref)
    local out = {}
    local mobile = ref and ref.mobile
    if not mobile or not mobile.activeMagicEffectList then return out end
    for _, a in ipairs(mobile.activeMagicEffectList) do
        local inst = a.instance
        local src = inst and inst.source
        local caster = inst and inst.caster
        local elapsed = 0
        pcall(function() elapsed = a.effectInstance and a.effectInstance.timeActive or 0 end)
        local duration = a.duration or 0
        local remaining = duration > 0 and math.max(0, duration - elapsed) or 0
        local name = effectName(a.effectId)
        pcall(function()
            if a.attributeId and a.attributeId >= 0 and tes3.attributeName[a.attributeId] then
                name = name .. " (" .. tes3.attributeName[a.attributeId] .. ")"
            elseif a.skillId and a.skillId >= 0 and tes3.skillName[a.skillId] then
                name = name .. " (" .. tes3.skillName[a.skillId] .. ")"
            end
        end)
        out[#out + 1] = {
            effectId = a.effectId, name = name, magnitude = a.magnitude or 0, duration = duration,
            remaining = remaining, permanent = duration <= 0,
            sourceName = src and (src.name or src.id) or "unknown source", sourceId = src and src.id or "?",
            caster = caster and (caster.object and caster.object.name or caster.id) or "unknown",
        }
    end
    return out
end

local function effectsText(list, withRange)
    local parts = {}
    for _, eff in ipairs(list or {}) do
        if eff and eff.id and eff.id >= 0 then
            local mag = tostring(eff.min or 0)
            if withRange and eff.max and eff.max ~= eff.min then mag = string.format("%d-%d", eff.min, eff.max) end
            parts[#parts + 1] = string.format("%s %s pts", effectName(eff.id), mag)
        end
    end
    return #parts > 0 and table.concat(parts, ", ") or "no effects"
end
collect.effectsText = effectsText

function collect.spells(ref)
    local out = {}
    local ok, list = pcall(tes3.getSpells, { target = ref })
    if not ok or not list then list = ref.object and ref.object.spells end
    if not list then return out end
    pcall(function()
        for _, spell in pairs(list) do
            out[#out + 1] = { name = spell.name or spell.id, id = spell.id,
                              type = collect.SPELL_TYPES[spell.castType] or "Spell", effects = effectsText(spell.effects, true) }
        end
    end)
    table.sort(out, function(a, b) return a.type .. a.name < b.type .. b.name end)
    return out
end

function collect.enchantedEquipment(ref)
    local out = {}
    local obj = ref and ref.object
    if not obj or not obj.equipment then return out end
    pcall(function()
        for _, stack in pairs(obj.equipment) do
            local item = stack.object
            if item and item.enchantment then
                out[#out + 1] = { name = item.name or item.id, id = item.id, effects = effectsText(item.enchantment.effects) }
            end
        end
    end)
    return out
end

function collect.parseWords(text)
    local words = {}
    for w in tostring(text or ""):gmatch("[^,%s]+") do words[#words + 1] = w:lower() end
    return words
end

--- scene nodes that look like magic visuals: particle systems, or names containing one of the words
function collect.vfxNodes(ref, words, maxNodes)
    local out = {}
    local root = ref and ref.sceneNode
    if not root then return out end
    maxNodes = maxNodes or 400
    local visited = 0
    local function isType(node, name)
        local ok, r = pcall(function() return tes3.niType[name] and node:isInstanceOfType(tes3.niType[name]) end)
        return ok and r
    end
    local function walk(node, depth)
        if not node or visited >= 5000 or #out >= maxNodes then return end
        visited = visited + 1
        local name = node.name or ""
        local low = name:lower()
        local particle = isType(node, "NiParticleSystem") or isType(node, "NiParticles")
        local hit = particle
        if not hit then
            for _, w in ipairs(words) do if low:find(w, 1, true) then hit = true break end end
        end
        if hit then
            out[#out + 1] = { name = name, depth = depth,
                              type = particle and "particles" or (isType(node, "NiNode") and "node" or "geometry") }
        end
        local ok, children = pcall(function() return node.children end)
        if ok and children then
            for _, child in ipairs(children) do walk(child, depth + 1) end
        end
    end
    walk(root, 0)
    return out
end

--- removes every active effect, one effect ID at a time (tes3.removeEffects needs an effect or castType)
function collect.purge(ref)
    local active = collect.active(ref)
    local ids, seen = {}, {}
    for _, a in ipairs(active) do
        if a.effectId and not seen[a.effectId] then
            seen[a.effectId] = true
            ids[#ids + 1] = a.effectId
        end
    end
    local removed = 0
    for _, id in ipairs(ids) do
        local ok = pcall(tes3.removeEffects, { reference = ref, effect = id })
        if ok then removed = removed + 1 end
    end
    return #active, removed
end

return collect
