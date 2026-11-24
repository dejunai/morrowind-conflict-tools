local config = require("mweffectinspector.config")

local inspector = {}

local GUI_ID_WINDOW = tes3ui.registerID("mweffectinspector:Window")

local spellTypeNames = {
    [0] = "Spell",
    [1] = "Ability (Constant)",
    [2] = "Blight",
    [3] = "Disease",
    [4] = "Curse",
    [5] = "Power",
}

function inspector.getTargetRef()
    local consoleRef = tes3ui.getConsoleReference()
    if consoleRef then
        return consoleRef
    end
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

function inspector.closeWindow()
    local menu = tes3ui.findMenu(GUI_ID_WINDOW)
    if menu then
        menu:destroy()
        tes3ui.leaveMenuMode()
    end
end

function inspector.openWindow(targetRef)
    local ref = targetRef or inspector.getTargetRef()
    if not ref then
        tes3.messageBox("mweffectinspector: No target reference found.")
        return
    end

    local existing = tes3ui.findMenu(GUI_ID_WINDOW)
    if existing then
        existing:destroy()
    end

    local menu = tes3ui.createMenu({ id = GUI_ID_WINDOW, fixedFrame = true })
    menu.text = "Magic Effect & VFX Inspector (mweffectinspector)"
    menu.width = 720
    menu.height = 560
    menu.minWidth = 580
    menu.minHeight = 420
    menu.positionX = 0.5
    menu.positionY = 0.5

    local mainBlock = menu:createBlock({})
    mainBlock.widthProportional = 1.0
    mainBlock.heightProportional = 1.0
    mainBlock.flowDirection = "top_to_bottom"

    -- 1. Target Header Card
    local obj = ref.object
    local name = (obj and obj.name) or ref.id
    local refId = ref.id
    local baseId = (obj and obj.id) or "unknown"
    local cellName = ref.cell and (ref.cell.editorName or ref.cell.displayName or ref.cell.id) or "Unknown Cell"
    local mobile = ref.mobile

    local headerBox = mainBlock:createThinBorder({})
    headerBox.widthProportional = 1.0
    headerBox.autoHeight = true
    headerBox.paddingAllSides = 8
    headerBox.borderBottom = 6
    headerBox.flowDirection = "top_to_bottom"

    local titleRow = headerBox:createBlock({})
    titleRow.widthProportional = 1.0
    titleRow.autoHeight = true
    titleRow.flowDirection = "left_to_right"

    local targetTitle = titleRow:createLabel({ text = string.format("Target: %s", name) })
    targetTitle.color = tes3ui.getPalette("header_color")
    targetTitle.widthProportional = 1.0

    local metaText = string.format("Base: %s  |  Ref: %s  |  Cell: %s", baseId, refId, cellName)
    local metaLbl = headerBox:createLabel({ text = metaText })
    metaLbl.color = tes3ui.getPalette("journal_finished_quest_color")

    if mobile then
        local hCur = math.floor(mobile.health and mobile.health.current or 0)
        local hMax = math.floor(mobile.health and mobile.health.base or 0)
        local mCur = math.floor(mobile.magicka and mobile.magicka.current or 0)
        local mMax = math.floor(mobile.magicka and mobile.magicka.base or 0)
        local fCur = math.floor(mobile.fatigue and mobile.fatigue.current or 0)
        local fMax = math.floor(mobile.fatigue and mobile.fatigue.base or 0)
        local statLbl = headerBox:createLabel({
            text = string.format("Health: %d/%d  |  Magicka: %d/%d  |  Fatigue: %d/%d", hCur, hMax, mCur, mMax, fCur, fMax)
        })
        statLbl.color = tes3ui.getPalette("active_color")
    end

    -- 2. Scrollable Body
    local scroll = mainBlock:createVerticalScrollPane({})
    scroll.widthProportional = 1.0
    scroll.heightProportional = 1.0
    scroll.borderBottom = 8

    local content = scroll:getContentElement()
    content.flowDirection = "top_to_bottom"
    content.widthProportional = 1.0

    local function addSectionHeader(titleText)
        local sec = content:createBlock({})
        sec.widthProportional = 1.0
        sec.autoHeight = true
        sec.borderTop = 6
        sec.borderBottom = 4
        local lbl = sec:createLabel({ text = string.format("--- %s ---", titleText) })
        lbl.color = tes3ui.getPalette("header_color")
    end

    -- Active Magic Effects
    addSectionHeader("ACTIVE MAGIC EFFECTS")
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

            local itemBox = content:createThinBorder({})
            itemBox.widthProportional = 1.0
            itemBox.autoHeight = true
            itemBox.paddingAllSides = 4
            itemBox.borderBottom = 3
            itemBox.flowDirection = "left_to_right"

            local effLabel = itemBox:createLabel({
                text = string.format(" * %s (%d pts, %ds left)", effName, mag, dur)
            })
            effLabel.color = tes3ui.getPalette("active_color")
            effLabel.widthProportional = 1.0

            local srcLabel = itemBox:createLabel({
                text = string.format("Source: %s [%s]  (Caster: %s)", srcName, srcId, casterName)
            })
            srcLabel.color = tes3ui.getPalette("normal_color")
        end
    end
    if activeCount == 0 then
        local none = content:createLabel({ text = "  (No active magic effects)" })
        none.color = tes3ui.getPalette("journal_finished_quest_color")
    end

    -- Spells & Innate Abilities
    if config.showSpells then
        addSectionHeader("SPELLS & INNATE ABILITIES")
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
                local effDescStr = #effectDescs > 0 and table.concat(effectDescs, ", ") or "None"

                local sBox = content:createThinBorder({})
                sBox.widthProportional = 1.0
                sBox.autoHeight = true
                sBox.paddingAllSides = 4
                sBox.borderBottom = 3
                sBox.flowDirection = "left_to_right"

                local sNameLbl = sBox:createLabel({ text = string.format("[%s] %s", typeStr, spell.name or spell.id) })
                sNameLbl.color = tes3ui.getPalette("active_color")
                sNameLbl.widthProportional = 1.0

                local sEffLbl = sBox:createLabel({ text = effDescStr })
                sEffLbl.color = tes3ui.getPalette("normal_color")
            end
        end
        if spellCount == 0 then
            local none = content:createLabel({ text = "  (No spells or innate abilities)" })
            none.color = tes3ui.getPalette("journal_finished_quest_color")
        end
    end

    -- Equipped Items & Enchantments
    if config.showEquipment and obj and obj.equipment then
        addSectionHeader("EQUIPPED ITEMS & ENCHANTMENTS")
        local equipCount = 0
        for _, stack in pairs(obj.equipment) do
            local itemObj = stack.object
            if itemObj and itemObj.enchantment then
                equipCount = equipCount + 1
                local ench = itemObj.enchantment
                local enchDesc = {}
                for _, eff in ipairs(ench.effects or {}) do
                    if eff and eff.id and eff.id >= 0 then
                        local mgef = tes3.getMagicEffect(eff.id)
                        table.insert(enchDesc, string.format("%s %d pts", (mgef and mgef.name) or tostring(eff.id), eff.min or 0))
                    end
                end

                local eBox = content:createThinBorder({})
                eBox.widthProportional = 1.0
                eBox.autoHeight = true
                eBox.paddingAllSides = 4
                eBox.borderBottom = 3
                eBox.flowDirection = "left_to_right"

                local eNameLbl = eBox:createLabel({ text = string.format(" * %s", itemObj.name or itemObj.id) })
                eNameLbl.color = tes3ui.getPalette("active_color")
                eNameLbl.widthProportional = 1.0

                local eDescLbl = eBox:createLabel({ text = table.concat(enchDesc, ", ") })
                eDescLbl.color = tes3ui.getPalette("normal_color")
            end
        end
        if equipCount == 0 then
            local none = content:createLabel({ text = "  (No enchanted equipment)" })
            none.color = tes3ui.getPalette("journal_finished_quest_color")
        end
    end

    -- Attached VFX & Scene Nodes
    if config.showVFXNodes and ref.sceneNode then
        addSectionHeader("ATTACHED SCENE NODES & VFX")
        local vfxCount = 0
        local function checkNode(node)
            if not node then return end
            local nName = node.name or ""
            local low = nName:lower()
            local isParticle = node:isInstanceOfType(tes3.niType.NiParticleSystem) or node:isInstanceOfType(tes3.niType.NiParticles)
            if isParticle or low:find("vfx") or low:find("magic") or low:find("shield") or low:find("spell") or low:find("aura") or low:find("effect") or low:find("light") then
                vfxCount = vfxCount + 1
                local typeName = node:isInstanceOfType(tes3.niType.NiNode) and "NiNode" or (isParticle and "ParticleSystem" or "Geometry")

                local vBox = content:createThinBorder({})
                vBox.widthProportional = 1.0
                vBox.autoHeight = true
                vBox.paddingAllSides = 3
                vBox.borderBottom = 2
                local vLbl = vBox:createLabel({ text = string.format("  [%s] '%s'", typeName, nName) })
                vLbl.color = tes3ui.getPalette("active_color")
            end
            if node.children then
                for _, child in ipairs(node.children) do
                    checkNode(child)
                end
            end
        end
        checkNode(ref.sceneNode)
        if vfxCount == 0 then
            local none = content:createLabel({ text = "  (No lingering VFX nodes detected)" })
            none.color = tes3ui.getPalette("journal_finished_quest_color")
        end
    end

    -- 3. Bottom Button Row
    local btnRow = mainBlock:createBlock({})
    btnRow.widthProportional = 1.0
    btnRow.autoHeight = true
    btnRow.flowDirection = "left_to_right"

    local purgeBtn = btnRow:createButton({ text = "Purge Active Effects" })
    purgeBtn:register("mouseClick", function()
        inspector.clearEffects(ref)
        inspector.openWindow(ref)
    end)

    local refreshBtn = btnRow:createButton({ text = "Refresh" })
    refreshBtn.borderLeft = 8
    refreshBtn:register("mouseClick", function()
        inspector.openWindow(ref)
    end)

    local closeSpacer = btnRow:createBlock({})
    closeSpacer.widthProportional = 1.0
    closeSpacer.autoHeight = true

    local closeBtn = btnRow:createButton({ text = "Close" })
    closeBtn:register("mouseClick", function()
        inspector.closeWindow()
    end)

    menu:updateLayout()
    tes3ui.enterMenuMode(GUI_ID_WINDOW)
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

    -- Open the graphical UI window
    inspector.openWindow(ref)
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
