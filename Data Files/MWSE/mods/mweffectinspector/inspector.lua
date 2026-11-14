local config = require("mweffectinspector.config")

local inspector = {}

local spellTypeNames = {
    [0] = "Spell",
    [1] = "Ability (Constant)",
    [2] = "Blight",
    [3] = "Disease",
    [4] = "Curse",
    [5] = "Power",
}

function inspector.getTargetRef()
    local menuConsole = tes3ui.findMenu("MenuConsole")
    if menuConsole then
        local currentRef = menuConsole:getPropertyObject("MenuConsole_current_ref")
        if currentRef then
            return currentRef
        end
    end
    return tes3.getPlayerTarget() or tes3.player
end

local function logConsole(str)
    if tes3ui.log then
        tes3ui.log(str)
    elseif tes3ui.logToConsole then
        tes3ui.logToConsole(str, false)
    end
end

local function logBoth(summaryLines, str)
    table.insert(summaryLines, str)
    logConsole(str)
    if config.logToMWSE then
        mwse.log("[mweffectinspector] %s", str)
    end
end

function inspector.inspectEffects(targetRef)
    local ref = targetRef or inspector.getTargetRef()
    if not ref then
        logConsole("[mweffectinspector] Error: No target reference found.")
        return
    end

    local mobile = ref.mobile
    local obj = ref.object
    local name = (obj and obj.name) or ref.id
    local refId = ref.id
    local baseId = obj and obj.id or "unknown"
    local cellName = ref.cell and (ref.cell.editorName or ref.cell.id) or "Unknown Cell"

    local summaryLines = {}

    logBoth(summaryLines, "========================================")
    logBoth(summaryLines, string.format("INSPECTING: %s (Base: %s | Ref: %s)", name, baseId, refId))
    logBoth(summaryLines, string.format("Location: %s", cellName))
    logBoth(summaryLines, "========================================")

    -- 1. ACTIVE MAGIC EFFECTS
    logBoth(summaryLines, "\n--- ACTIVE MAGIC EFFECTS ---")
    local activeCount = 0
    if mobile and mobile.activeMagicEffectList then
        for _, actEff in ipairs(mobile.activeMagicEffectList) do
            activeCount = activeCount + 1
            local mgef = tes3.getMagicEffect(actEff.effectId)
            local effName = (mgef and mgef.name) or string.format("Effect #%s", tostring(actEff.effectId))
            local src = actEff.instance and actEff.instance.source
            local srcName = (src and src.name) or "Unknown Source"
            local srcId = (src and src.id) or "unknown"
            local caster = actEff.instance and actEff.instance.caster
            local casterName = caster and (caster.object and caster.object.name or caster.id) or "Unknown Caster"
            local mag = actEff.magnitude or 0
            local dur = math.floor(actEff.duration or 0)
            local line = string.format("  * %s: %s pts, %ss left | Source: '%s' (%s) | Caster: %s",
                effName, tostring(mag), tostring(dur), srcName, srcId, casterName)
            logBoth(summaryLines, line)
        end
    end
    if activeCount == 0 then
        logBoth(summaryLines, "  (None active)")
    end

    -- 2. INNATE SPELLS, ABILITIES, POWERS, BLIGHTS, DISEASES
    if config.showSpells then
        logBoth(summaryLines, "\n--- SPELLS & INNATE ABILITIES ---")
        local spellCount = 0
        local spellsList = tes3.getSpells{ target = ref } or (obj and obj.spells)
        if spellsList then
            for _, spell in pairs(spellsList) do
                spellCount = spellCount + 1
                local typeStr = spellTypeNames[spell.castType] or "Spell"
                local effectDescs = {}
                for _, eff in ipairs(spell.effects or {}) do
                    if eff and eff.id and eff.id >= 0 then
                        local mgef = tes3.getMagicEffect(eff.id)
                        local mName = (mgef and mgef.name) or tostring(eff.id)
                        local magStr = tostring(eff.min)
                        if eff.max and eff.max ~= eff.min then
                            magStr = string.format("%d-%d", eff.min, eff.max)
                        end
                        table.insert(effectDescs, string.format("%s %s pts", mName, magStr))
                    end
                end
                local effectsSummary = #effectDescs > 0 and table.concat(effectDescs, ", ") or "No effects"
                local line = string.format("  * [%s] %s (%s): %s", typeStr, spell.name or spell.id, spell.id, effectsSummary)
                logBoth(summaryLines, line)
            end
        end
        if spellCount == 0 then
            logBoth(summaryLines, "  (None)")
        end
    end

    -- 3. EQUIPPED ITEMS & ENCHANTMENTS
    if config.showEquipment then
        logBoth(summaryLines, "\n--- EQUIPPED ITEMS & ENCHANTMENTS ---")
        local equipCount = 0
        if obj and obj.equipment then
            for _, stack in pairs(obj.equipment) do
                equipCount = equipCount + 1
                local item = stack.object
                local enchant = item and item.enchantment
                local enchInfo = "Non-magical"
                if enchant then
                    local enchType = enchant.castType == 3 and "Constant Effect" or (enchant.castType == 1 and "On Strike" or "On Use")
                    local enchEffects = {}
                    for _, eff in ipairs(enchant.effects or {}) do
                        if eff and eff.id and eff.id >= 0 then
                            local mgef = tes3.getMagicEffect(eff.id)
                            local mName = (mgef and mgef.name) or tostring(eff.id)
                            table.insert(enchEffects, string.format("%s %s pts", mName, tostring(eff.min)))
                        end
                    end
                    enchInfo = string.format("[%s: %s] %s", enchType, enchant.id, table.concat(enchEffects, ", "))
                end
                local line = string.format("  * %s (%s): %s", item.name or item.id, item.id, enchInfo)
                logBoth(summaryLines, line)
            end
        end
        if equipCount == 0 then
            logBoth(summaryLines, "  (None)")
        end
    end

    -- 4. ATTACHED SCENE NODES & VFX
    if config.showVFXNodes and ref.sceneNode then
        logBoth(summaryLines, "\n--- ATTACHED SCENE NODES & VFX ---")
        local vfxCount = 0
        local function checkNode(node)
            if not node then return end
            local nName = node.name or ""
            local low = nName:lower()
            local isParticle = node:isInstanceOfType(tes3.niType.NiParticleSystem) or node:isInstanceOfType(tes3.niType.NiParticles)
            if isParticle or low:find("vfx") or low:find("magic") or low:find("shield") or low:find("spell") or low:find("aura") or low:find("effect") or low:find("light") then
                vfxCount = vfxCount + 1
                local typeName = node:isInstanceOfType(tes3.niType.NiNode) and "NiNode" or (isParticle and "ParticleSystem" or "Geometry")
                local line = string.format("  * [%s] '%s'", typeName, nName)
                logBoth(summaryLines, line)
            end
            if node.children then
                for _, child in ipairs(node.children) do
                    checkNode(child)
                end
            end
        end
        checkNode(ref.sceneNode)
        if vfxCount == 0 then
            logBoth(summaryLines, "  (No lingering VFX nodes detected)")
        end
    end

    logBoth(summaryLines, "========================================")

    -- 5. INTERACTIVE MESSAGEBOX POPUP
    if config.interactivePopup then
        local messageText = table.concat(summaryLines, "\n")
        tes3.messageBox({
            message = messageText:sub(1, 950),
            buttons = { "Close", "Purge / Dispel All Effects" },
            callback = function(btnEvent)
                if btnEvent.button == 1 then
                    inspector.clearEffects(ref)
                end
            end,
        })
    end
end

function inspector.clearEffects(targetRef)
    local ref = targetRef or inspector.getTargetRef()
    if not ref then
        logConsole("[mweffectinspector] Error: No target reference found.")
        return
    end

    local name = (ref.object and ref.object.name) or ref.id
    local mobile = ref.mobile
    local count = 0
    if mobile and mobile.activeMagicEffectList then
        for _, actEff in ipairs(mobile.activeMagicEffectList) do
            count = count + 1
            if actEff.instance then
                pcall(function() actEff.instance:cancel() end)
            end
        end
    end

    tes3.removeEffects{ reference = ref }

    local msg = string.format("[mweffectinspector] Purged %d active magic effect(s) from %s (%s).", count, name, ref.id)
    logConsole(msg)
    if config.logToMWSE then
        mwse.log(msg)
    end
    tes3.messageBox(string.format("Purged %d active magic effect(s) from %s.", count, name))
end

return inspector
