local config = require("mwcriminal.config")
local interop = require("mwcriminal.interop")

local inspectorUI = {}

local GUI_ID_MENU = tes3ui.registerID("mwcriminal:DetectionInspector")
local GUI_ID_BLACKLIST_MENU = tes3ui.registerID("mwcriminal:BlacklistMenu")
local GUI_ID_INPUT = tes3ui.registerID("mwcriminal:BlacklistInput")

local manualInputText = ""

function inspectorUI.close()
    local menu = tes3ui.findMenu(GUI_ID_MENU)
    local blMenu = tes3ui.findMenu(GUI_ID_BLACKLIST_MENU)
    if menu or blMenu then
        tes3ui.leaveMenuMode()
        if menu then menu:destroy() end
        if blMenu then blMenu:destroy() end
    end
end

local function addHeader(parent, text)
    local header = parent:createBlock({})
    header.widthProportional = 1.0
    header.autoHeight = true
    header.flowDirection = "left_to_right"
    header.borderBottom = 4

    local title = header:createLabel({ text = text })
    title.autoWidth = true
    title.autoHeight = true
    title.color = tes3ui.getPalette("header_color")

    local spacer = header:createBlock({})
    spacer.widthProportional = 1.0
    spacer.autoHeight = true

    local closeBtn = header:createButton({ text = "Close" })
    closeBtn.autoWidth = true
    closeBtn.autoHeight = true
    closeBtn:register("mouseClick", function()
        inspectorUI.close()
    end)
end

function inspectorUI.refresh()
    local menu = tes3ui.findMenu(GUI_ID_MENU)
    if menu then
        menu:destroy()
        inspectorUI.open()
    end
end

function inspectorUI.refreshBlacklist()
    local blMenu = tes3ui.findMenu(GUI_ID_BLACKLIST_MENU)
    if blMenu then
        blMenu:destroy()
        inspectorUI.openBlacklist()
    end
end

--- Opens the main Stealth Detection Inspector.
--- Lists ONLY actors actively detecting the player (not blacklisted, not companions).
function inspectorUI.open()
    local blMenu = tes3ui.findMenu(GUI_ID_BLACKLIST_MENU)
    if blMenu then blMenu:destroy() end

    local existing = tes3ui.findMenu(GUI_ID_MENU)
    if existing then
        inspectorUI.close()
        return
    end

    local menu = tes3ui.createMenu({ id = GUI_ID_MENU, fixedFrame = true })
    menu.text = "Stealth Detection Inspector (mwcriminal)"
    menu.width = 680
    menu.height = 520
    menu.minWidth = 550
    menu.minHeight = 400
    menu.positionX = 0.5
    menu.positionY = 0.5

    local mainBlock = menu:createBlock({})
    mainBlock.widthProportional = 1.0
    mainBlock.heightProportional = 1.0
    mainBlock.flowDirection = "top_to_bottom"

    -- Header
    addHeader(mainBlock, "STEALTH DETECTION INSPECTOR")

    local sub = mainBlock:createLabel({
        text = "Actively monitors actors detecting you. Blacklisted entities and companions are excluded."
    })
    sub.wrapText = true
    sub.borderBottom = 8

    -- 1. Look Target Quick-Action Card
    local lookTarget = tes3.getPlayerTarget()
    if lookTarget and lookTarget.object and (lookTarget.object.objectType == tes3.objectType.npc or lookTarget.object.objectType == tes3.objectType.creature) then
        local tBox = mainBlock:createThinBorder({})
        tBox.widthProportional = 1.0
        tBox.autoHeight = true
        tBox.paddingAllSides = 6
        tBox.borderBottom = 8

        local tRow = tBox:createBlock({})
        tRow.widthProportional = 1.0
        tRow.autoHeight = true
        tRow.flowDirection = "left_to_right"

        local tInfo = tRow:createBlock({})
        tInfo.widthProportional = 1.0
        tInfo.autoHeight = true
        tInfo.flowDirection = "top_to_bottom"

        local tBaseId = lookTarget.object.id:lower()
        local tName = lookTarget.object.name or tBaseId
        local tIsComp = lookTarget.mobile and interop.isCompanion(lookTarget.mobile)
        local tIsBl = interop.isBlacklisted(lookTarget)

        local tLbl1 = tInfo:createLabel({ text = string.format("Crosshair Target: %s [%s]", tName, tBaseId) })
        tLbl1.color = tes3ui.getPalette("active_color")

        local tDist = lookTarget.position:distance(tes3.player.position)
        local tDetected = lookTarget.mobile and lookTarget.mobile.isPlayerDetected
        local statusStr = tIsComp and "COMPANION" or (tIsBl and "BLACKLISTED" or (tDetected and "ALERTED / DETECTING" or "Clear"))
        local tLbl2 = tInfo:createLabel({
            text = string.format("Type: %s | Status: %s | Distance: %d units",
                lookTarget.object.objectType == tes3.objectType.creature and "Creature" or "NPC",
                statusStr,
                math.floor(tDist))
        })
        tLbl2.color = tDetected and tes3ui.getPalette("health_color") or tes3ui.getPalette("journal_finished_quest_color")

        local tBtnBlock = tRow:createBlock({})
        tBtnBlock.autoWidth = true
        tBtnBlock.autoHeight = true
        tBtnBlock.childAlignY = 0.5

        local tBtn = tBtnBlock:createButton({ text = tIsBl and "Unblacklist Target" or "Blacklist Target" })
        tBtn:register("mouseClick", function()
            if tIsBl then
                interop.unblacklistEntity(tBaseId)
                tes3.messageBox("Unblacklisted '%s' (%s).", tName, tBaseId)
            else
                interop.blacklistEntity(tBaseId)
                if lookTarget.mobile then
                    lookTarget.mobile.isPlayerDetected = false
                    lookTarget.mobile.isPlayerHidden = true
                end
                interop.clearSuspicion(lookTarget)
                tes3.messageBox("Blacklisted '%s' (%s) from stealth detection.", tName, tBaseId)
            end
            inspectorUI.refresh()
        end)
    end

    -- 2. Active Detectors List (ONLY what is actively detecting the player)
    local activeDetectors = {}
    local seen = {}

    local nearby = tes3.findActorsInProximity({ reference = tes3.player, range = 2500 })
    if nearby then
        for _, mob in ipairs(nearby) do
            local ref = mob.reference
            if ref and ref:isValid() and mob ~= tes3.mobilePlayer and not seen[ref] then
                seen[ref] = true
                local isComp = interop.isCompanion(mob)
                local isBl = interop.isBlacklisted(mob)
                local isDet = mob.isPlayerDetected == true

                -- Filter out blacklisted entities and companions: ONLY list active detectors!
                if isDet and not isBl and not isComp then
                    table.insert(activeDetectors, {
                        ref = ref,
                        mob = mob,
                        dist = ref.position:distance(tes3.player.position),
                    })
                end
            end
        end
    end

    table.sort(activeDetectors, function(a, b)
        return a.dist < b.dist
    end)

    local actHeader = mainBlock:createLabel({
        text = string.format("Actively Detecting You (%d):", #activeDetectors)
    })
    actHeader.color = (#activeDetectors > 0)
        and tes3ui.getPalette("health_color")
        or tes3ui.getPalette("header_color")
    actHeader.borderBottom = 4

    local scrollPane = mainBlock:createVerticalScrollPane({})
    scrollPane.widthProportional = 1.0
    scrollPane.minHeight = 160
    scrollPane.heightProportional = 1.0
    scrollPane.borderBottom = 8

    local scrollContent = scrollPane:getContentElement()
    scrollContent.widthProportional = 1.0
    scrollContent.autoHeight = true

    if #activeDetectors == 0 then
        local emptyBorder = scrollContent:createThinBorder({})
        emptyBorder.widthProportional = 1.0
        emptyBorder.autoHeight = true
        emptyBorder.paddingAllSides = 8

        local lbl = emptyBorder:createLabel({
            text = "You are undetected. No active actors are detecting you."
        })
        lbl.color = tes3ui.getPalette("journal_finished_quest_color")
    else
        for _, item in ipairs(activeDetectors) do
            local ref = item.ref
            local mob = item.mob
            local baseId = ref.object.id:lower()
            local name = ref.object.name or baseId
            local isCreature = (ref.object.objectType == tes3.objectType.creature)

            local itemBorder = scrollContent:createThinBorder({})
            itemBorder.widthProportional = 1.0
            itemBorder.autoHeight = true
            itemBorder.paddingAllSides = 4
            itemBorder.borderBottom = 2

            local itemRow = itemBorder:createBlock({})
            itemRow.widthProportional = 1.0
            itemRow.autoHeight = true
            itemRow.flowDirection = "left_to_right"

            local infoCol = itemRow:createBlock({})
            infoCol.widthProportional = 1.0
            infoCol.autoHeight = true
            infoCol.flowDirection = "top_to_bottom"

            local nameLabel = infoCol:createLabel({
                text = string.format("%s [%s]  (%s)", name, baseId, isCreature and "Creature" or "NPC")
            })
            nameLabel.color = tes3ui.getPalette("health_color")

            local detLabel = infoCol:createLabel({
                text = string.format("Status: ALERTED / DETECTING | Distance: %d units", math.floor(item.dist))
            })
            detLabel.color = tes3ui.getPalette("journal_finished_quest_color")

            local btnCol = itemRow:createBlock({})
            btnCol.autoWidth = true
            btnCol.autoHeight = true
            btnCol.childAlignY = 0.5

            local bBtn = btnCol:createButton({ text = "Blacklist" })
            bBtn:register("mouseClick", function()
                interop.blacklistEntity(baseId)
                mob.isPlayerDetected = false
                mob.isPlayerHidden = true
                interop.clearSuspicion(ref)
                tes3.messageBox("Blacklisted '%s' (%s).", name, baseId)
                inspectorUI.refresh()
            end)
        end
    end

    -- 3. Footer Bar
    local footer = mainBlock:createBlock({})
    footer.widthProportional = 1.0
    footer.autoHeight = true
    footer.flowDirection = "left_to_right"

    local blCount = 0
    if config.companionBlacklist then
        for _ in pairs(config.companionBlacklist) do blCount = blCount + 1 end
    end

    local blBtn = footer:createButton({ text = "Open Blacklist" })
    blBtn.autoWidth = true
    blBtn.autoHeight = true
    blBtn.borderRight = 8
    blBtn:register("mouseClick", function()
        inspectorUI.openBlacklist()
    end)

    local summaryLbl = footer:createLabel({
        text = string.format("(Custom Blacklisted: %d | Creature Auto-Blacklist: %s)",
            blCount, config.blacklistAllCreatures and "ON" or "OFF")
    })
    summaryLbl.childAlignY = 0.5
    summaryLbl.color = tes3ui.getPalette("disabled_color")

    local fSpacer = footer:createBlock({})
    fSpacer.widthProportional = 1.0
    fSpacer.autoHeight = true

    local refreshBtn = footer:createButton({ text = "Refresh" })
    refreshBtn.autoWidth = true
    refreshBtn.autoHeight = true
    refreshBtn.borderRight = 8
    refreshBtn:register("mouseClick", function()
        inspectorUI.refresh()
    end)

    if not tes3ui.menuMode() then
        tes3ui.enterMenuMode(GUI_ID_MENU)
    end
end

--- Opens the separate Blacklist Management UI.
function inspectorUI.openBlacklist()
    local inspMenu = tes3ui.findMenu(GUI_ID_MENU)
    if inspMenu then inspMenu:destroy() end

    local existing = tes3ui.findMenu(GUI_ID_BLACKLIST_MENU)
    if existing then
        inspectorUI.close()
        return
    end

    local menu = tes3ui.createMenu({ id = GUI_ID_BLACKLIST_MENU, fixedFrame = true })
    menu.text = "Stealth Detection Blacklist (mwcriminal)"
    menu.width = 680
    menu.height = 540
    menu.minWidth = 550
    menu.minHeight = 420
    menu.positionX = 0.5
    menu.positionY = 0.5

    local mainBlock = menu:createBlock({})
    mainBlock.widthProportional = 1.0
    mainBlock.heightProportional = 1.0
    mainBlock.flowDirection = "top_to_bottom"

    -- Header
    addHeader(mainBlock, "STEALTH DETECTION BLACKLIST")

    local sub = mainBlock:createLabel({
        text = "Entities in this blacklist are completely ignored by stealth detection and cannot reveal you."
    })
    sub.wrapText = true
    sub.borderBottom = 8

    -- 1. Global Creature Blacklist Quick Toggle
    local filterBox = mainBlock:createThinBorder({})
    filterBox.widthProportional = 1.0
    filterBox.autoHeight = true
    filterBox.paddingAllSides = 6
    filterBox.borderBottom = 8

    local filterRow = filterBox:createBlock({})
    filterRow.widthProportional = 1.0
    filterRow.autoHeight = true
    filterRow.flowDirection = "left_to_right"

    local filterBtn = filterRow:createButton({
        text = string.format("Blacklist All Creatures: [%s]", config.blacklistAllCreatures and "ENABLED" or "DISABLED")
    })
    filterBtn.autoWidth = true
    filterBtn.autoHeight = true
    filterBtn:register("mouseClick", function()
        config.blacklistAllCreatures = not config.blacklistAllCreatures
        mwse.saveConfig("mwcriminal", config)
        if config.blacklistAllCreatures then
            tes3.messageBox("All creatures are now blacklisted from stealth detection.")
        else
            tes3.messageBox("Creatures will now detect sneaking normally.")
        end
        inspectorUI.refreshBlacklist()
    end)

    local filterLbl = filterRow:createLabel({
        text = config.blacklistAllCreatures
            and "  (All animals, monsters, roosters, and ambient critters are ignored)"
            or "  (Creatures detect sneaking normally. Click to ignore all creatures.)"
    })
    filterLbl.childAlignY = 0.5
    filterLbl.color = config.blacklistAllCreatures
        and tes3ui.getPalette("journal_finished_quest_color")
        or tes3ui.getPalette("normal_color")

    -- 2. Manual Blacklist Entry Input
    local manualBox = mainBlock:createThinBorder({})
    manualBox.widthProportional = 1.0
    manualBox.autoHeight = true
    manualBox.paddingAllSides = 6
    manualBox.borderBottom = 8

    local manualTitle = manualBox:createLabel({ text = "Add Entity ID to Blacklist:" })
    manualTitle.color = tes3ui.getPalette("header_color")
    manualTitle.borderBottom = 4

    local manualRow = manualBox:createBlock({})
    manualRow.widthProportional = 1.0
    manualRow.autoHeight = true
    manualRow.flowDirection = "left_to_right"

    local inputBorder = manualRow:createThinBorder({})
    inputBorder.widthProportional = 1.0
    inputBorder.height = 28
    inputBorder.paddingAllSides = 4
    inputBorder.borderRight = 8

    local textInput = inputBorder:createTextInput({ id = GUI_ID_INPUT })
    textInput.text = manualInputText
    textInput.widthProportional = 1.0
    textInput.autoHeight = true
    textInput:register("textUpdated", function(e)
        manualInputText = textInput.text or ""
    end)

    local addBtn = manualRow:createButton({ text = "Add to Blacklist" })
    addBtn.autoWidth = true
    addBtn.autoHeight = true
    addBtn:register("mouseClick", function()
        local raw = manualInputText:match("^%s*(.-)%s*$")
        if raw and raw ~= "" then
            interop.blacklistEntity(raw)
            tes3.messageBox("Added '%s' to detection blacklist.", raw:lower())
            manualInputText = ""
            inspectorUI.refreshBlacklist()
        end
    end)

    -- 3. Blacklisted Entities Scroll List
    local blList = {}
    if config.companionBlacklist then
        for id, active in pairs(config.companionBlacklist) do
            if active then
                table.insert(blList, id)
            end
        end
    end
    table.sort(blList)

    local listHeader = mainBlock:createLabel({
        text = string.format("Custom Blacklisted IDs (%d):", #blList)
    })
    listHeader.color = tes3ui.getPalette("header_color")
    listHeader.borderBottom = 4

    local scrollPane = mainBlock:createVerticalScrollPane({})
    scrollPane.widthProportional = 1.0
    scrollPane.minHeight = 140
    scrollPane.heightProportional = 1.0
    scrollPane.borderBottom = 8

    local scrollContent = scrollPane:getContentElement()
    scrollContent.widthProportional = 1.0
    scrollContent.autoHeight = true

    if #blList == 0 then
        local emptyBorder = scrollContent:createThinBorder({})
        emptyBorder.widthProportional = 1.0
        emptyBorder.autoHeight = true
        emptyBorder.paddingAllSides = 8

        local lbl = emptyBorder:createLabel({ text = "No custom blacklisted entities." })
        lbl.color = tes3ui.getPalette("disabled_color")
    else
        for _, id in ipairs(blList) do
            local itemBorder = scrollContent:createThinBorder({})
            itemBorder.widthProportional = 1.0
            itemBorder.autoHeight = true
            itemBorder.paddingAllSides = 4
            itemBorder.borderBottom = 2

            local itemRow = itemBorder:createBlock({})
            itemRow.widthProportional = 1.0
            itemRow.autoHeight = true
            itemRow.flowDirection = "left_to_right"

            local infoCol = itemRow:createBlock({})
            infoCol.widthProportional = 1.0
            infoCol.autoHeight = true
            infoCol.flowDirection = "top_to_bottom"

            local obj = tes3.getObject(id)
            local displayName = (obj and obj.name and obj.name ~= "") and string.format("%s [%s]", obj.name, id) or string.format("[%s]", id)
            local typeStr = ""
            if obj then
                if obj.objectType == tes3.objectType.creature then
                    typeStr = " (Creature)"
                elseif obj.objectType == tes3.objectType.npc then
                    typeStr = " (NPC)"
                end
            end

            local nameLabel = infoCol:createLabel({ text = displayName .. typeStr })
            nameLabel.color = tes3ui.getPalette("normal_color")

            local btnCol = itemRow:createBlock({})
            btnCol.autoWidth = true
            btnCol.autoHeight = true
            btnCol.childAlignY = 0.5

            local removeBtn = btnCol:createButton({ text = "Unblacklist" })
            removeBtn:register("mouseClick", function()
                interop.unblacklistEntity(id)
                tes3.messageBox("Unblacklisted '%s'.", id)
                inspectorUI.refreshBlacklist()
            end)
        end
    end

    -- 4. Footer Bar
    local footer = mainBlock:createBlock({})
    footer.widthProportional = 1.0
    footer.autoHeight = true
    footer.flowDirection = "left_to_right"

    local backBtn = footer:createButton({ text = "Back to Detectors" })
    backBtn.autoWidth = true
    backBtn.autoHeight = true
    backBtn.borderRight = 8
    backBtn:register("mouseClick", function()
        inspectorUI.open()
    end)

    local fSpacer = footer:createBlock({})
    fSpacer.widthProportional = 1.0
    fSpacer.autoHeight = true

    if #blList > 0 then
        local clearBtn = footer:createButton({ text = "Clear All" })
        clearBtn.autoWidth = true
        clearBtn.autoHeight = true
        clearBtn.borderRight = 8
        clearBtn:register("mouseClick", function()
            config.companionBlacklist = {}
            mwse.saveConfig("mwcriminal", config)
            tes3.messageBox("Detection blacklist cleared.")
            inspectorUI.refreshBlacklist()
        end)
    end

    if not tes3ui.menuMode() then
        tes3ui.enterMenuMode(GUI_ID_BLACKLIST_MENU)
    end
end

return inspectorUI
