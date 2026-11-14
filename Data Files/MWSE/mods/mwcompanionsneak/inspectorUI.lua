local config = require("mwcompanionsneak.config")
local interop = require("mwcompanionsneak.interop")

local inspectorUI = {}

local GUI_ID_MENU = tes3ui.registerID("mwcompanionsneak:DetectionInspector")
local GUI_ID_INPUT = tes3ui.registerID("mwcompanionsneak:BlacklistInput")

local manualInputText = ""

function inspectorUI.close()
    local menu = tes3ui.findMenu(GUI_ID_MENU)
    if menu then
        tes3ui.leaveMenuMode()
        menu:destroy()
    end
end

function inspectorUI.refresh()
    local menu = tes3ui.findMenu(GUI_ID_MENU)
    if menu then
        inspectorUI.close()
        inspectorUI.open()
    end
end

function inspectorUI.open()
    if tes3ui.findMenu(GUI_ID_MENU) then
        inspectorUI.close()
        return
    end

    local menu = tes3ui.createMenu({ id = GUI_ID_MENU, fixedFrame = true })
    menu.text = "Stealth Detection Inspector (mwcompanionsneak)"
    menu.width = 700
    menu.height = 580
    menu.minWidth = 600
    menu.minHeight = 460
    menu.positionX = 0.5
    menu.positionY = 0.5

    -- Main layout container
    local mainBlock = menu:createBlock({})
    mainBlock.widthProportional = 1.0
    mainBlock.heightProportional = 1.0
    mainBlock.flowDirection = "top_to_bottom"

    -- Header title
    local title = mainBlock:createLabel({ text = "STEALTH DETECTION & COMPANION INSPECTOR" })
    title.color = tes3ui.getPalette("header_color")
    title.borderBottom = 4

    local sub = mainBlock:createLabel({
        text = "View nearby actors and companions. Auto-blacklist creatures, or blacklist false-positive entities (such as critters, ambient animals, or static actors) with one click."
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
        mwse.saveConfig("mwcompanionsneak", config)
        if config.blacklistAllCreatures then
            tes3.messageBox("All creatures are now blacklisted from stealth detection.")
        else
            tes3.messageBox("Creatures will now detect sneaking normally.")
        end
        inspectorUI.refresh()
    end)

    local filterLbl = filterRow:createLabel({
        text = config.blacklistAllCreatures
            and "  (All animals, monsters, roosters, and critters are ignored)"
            or "  (Creatures detect sneaking normally. Click to ignore all creatures.)"
    })
    filterLbl.childAlignY = 0.5
    filterLbl.color = config.blacklistAllCreatures
        and tes3ui.getPalette("journal_finished_quest_color")
        or tes3ui.getPalette("normal_color")

    -- 2. Look Target Quick-Action Card
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
        local statusStr = tIsComp and "COMPANION" or (tIsBl and "BLACKLISTED" or (tDetected and "DETECTING" or "Clear"))
        local tLbl2 = tInfo:createLabel({
            text = string.format("Type: %s | Status: %s | Distance: %d units",
                lookTarget.object.objectType == tes3.objectType.creature and "Creature" or "NPC",
                statusStr,
                math.floor(tDist))
        })
        tLbl2.color = tes3ui.getPalette("journal_finished_quest_color")

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

    -- 3. Active Nearby Detectors List
    local nearbyDetectors = {}
    local seen = {}

    local nearby = tes3.findActorsInProximity({ reference = tes3.player, range = 2500 })
    if nearby then
        for _, mob in ipairs(nearby) do
            local ref = mob.reference
            if ref and ref:isValid() and mob ~= tes3.mobilePlayer and not seen[ref] then
                seen[ref] = true
                table.insert(nearbyDetectors, {
                    ref = ref,
                    mob = mob,
                    isCompanion = interop.isCompanion(mob),
                    isBlacklisted = interop.isBlacklisted(mob),
                    isDetected = mob.isPlayerDetected == true,
                    dist = ref.position:distance(tes3.player.position),
                })
            end
        end
    end

    table.sort(nearbyDetectors, function(a, b)
        if a.isDetected ~= b.isDetected then return a.isDetected end
        return a.dist < b.dist
    end)

    local actHeader = mainBlock:createLabel({ text = string.format("Nearby Actors & Detectors (%d):", #nearbyDetectors) })
    actHeader.color = tes3ui.getPalette("header_color")
    actHeader.borderBottom = 4

    local scrollPane = mainBlock:createVerticalScrollPane({})
    scrollPane.widthProportional = 1.0
    scrollPane.minHeight = 160
    scrollPane.heightProportional = 1.0
    scrollPane.borderBottom = 8

    local scrollContent = scrollPane:getContentElement()
    scrollContent.widthProportional = 1.0
    scrollContent.autoHeight = true

    if #nearbyDetectors == 0 then
        local emptyBorder = scrollContent:createThinBorder({})
        emptyBorder.widthProportional = 1.0
        emptyBorder.autoHeight = true
        emptyBorder.paddingAllSides = 8
        local lbl = emptyBorder:createLabel({ text = "No active actors in range." })
        lbl.color = tes3ui.getPalette("disabled_color")
    else
        for _, item in ipairs(nearbyDetectors) do
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
            nameLabel.color = item.isCompanion and tes3ui.getPalette("magic_color")
                or (item.isBlacklisted and tes3ui.getPalette("disabled_color")
                or (item.isDetected and tes3ui.getPalette("health_color") or tes3ui.getPalette("normal_color")))

            local statusDesc = item.isCompanion and "COMPANION (Detection Suppressed)"
                or (item.isBlacklisted and "BLACKLISTED (Ignored)"
                or (item.isDetected and "ALERTED / DETECTING" or "Not Detecting"))

            local detLabel = infoCol:createLabel({
                text = string.format("Status: %s | Distance: %d units", statusDesc, math.floor(item.dist))
            })
            detLabel.color = tes3ui.getPalette("journal_finished_quest_color")

            local btnCol = itemRow:createBlock({})
            btnCol.autoWidth = true
            btnCol.autoHeight = true
            btnCol.childAlignY = 0.5

            if not item.isCompanion then
                local bBtn = btnCol:createButton({
                    text = item.isBlacklisted and "Unblacklist" or "Blacklist"
                })
                bBtn:register("mouseClick", function()
                    if item.isBlacklisted then
                        interop.unblacklistEntity(baseId)
                        tes3.messageBox("Unblacklisted '%s' (%s).", name, baseId)
                    else
                        interop.blacklistEntity(baseId)
                        mob.isPlayerDetected = false
                        mob.isPlayerHidden = true
                        interop.clearSuspicion(ref)
                        tes3.messageBox("Blacklisted '%s' (%s).", name, baseId)
                    end
                    inspectorUI.refresh()
                end)
            end
        end
    end

    -- 4. Manual Blacklist Entry Input
    local manualBox = mainBlock:createThinBorder({})
    manualBox.widthProportional = 1.0
    manualBox.autoHeight = true
    manualBox.paddingAllSides = 6
    manualBox.borderBottom = 8

    local manualTitle = manualBox:createLabel({ text = "Manual ID Blacklist:" })
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
    inputBorder.marginRight = 8

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
            inspectorUI.refresh()
        end
    end)

    -- 5. Footer Buttons
    local footer = mainBlock:createBlock({})
    footer.widthProportional = 1.0
    footer.autoHeight = true
    footer.flowDirection = "left_to_right"

    local blCount = 0
    if config.blacklist then
        for _ in pairs(config.blacklist) do blCount = blCount + 1 end
    end

    local blSummary = footer:createLabel({
        text = string.format("Custom Blacklisted IDs: %d", blCount)
    })
    blSummary.childAlignY = 0.5
    blSummary.color = tes3ui.getPalette("disabled_color")

    local fSpacer = footer:createBlock({})
    fSpacer.widthProportional = 1.0
    fSpacer.autoHeight = true

    if blCount > 0 then
        local clearBtn = footer:createButton({ text = "Clear Blacklist" })
        clearBtn.autoWidth = true
        clearBtn.autoHeight = true
        clearBtn.marginRight = 8
        clearBtn:register("mouseClick", function()
            config.blacklist = {}
            mwse.saveConfig("mwcompanionsneak", config)
            tes3.messageBox("Detection blacklist cleared.")
            inspectorUI.refresh()
        end)
    end

    local closeBtn = footer:createButton({ text = "Close" })
    closeBtn.autoWidth = true
    closeBtn.autoHeight = true
    closeBtn:register("mouseClick", function()
        inspectorUI.close()
    end)

    tes3ui.enterMenuMode(GUI_ID_MENU)
end

return inspectorUI
