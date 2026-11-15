--[[
    Custom Class Persistence (mwcustomclasspersistence)
    Saves player-created classes from character generation and seamlessly
    adds them to the "Pick from a list" menu in future playthroughs.
]]--

local CONFIG_FILE = "savedCustomClasses"
local savedClasses = mwse.loadConfig(CONFIG_FILE, {}) or {}

local currentSelectedCustomClass = nil

local SPECIALIZATION_NAMES = {
    [tes3.specialization.combat] = "Combat",
    [tes3.specialization.magic] = "Magic",
    [tes3.specialization.stealth] = "Stealth",
}

local ATTRIBUTE_NAMES = {
    [0] = "Strength",
    [1] = "Intelligence",
    [2] = "Willpower",
    [3] = "Agility",
    [4] = "Speed",
    [5] = "Endurance",
    [6] = "Personality",
    [7] = "Luck",
}

local function reloadSavedClasses()
    savedClasses = mwse.loadConfig(CONFIG_FILE, {}) or {}
    return savedClasses
end

local function saveCustomClass(classData)
    if not classData or not classData.name or classData.name == "" then return end
    local lower = classData.name:lower():match("^%s*(.-)%s*$")
    if not lower or lower == "" then return end

    reloadSavedClasses()
    savedClasses[lower] = classData
    mwse.saveConfig(CONFIG_FILE, savedClasses)
    mwse.log("[mwcustomclasspersistence] Saved custom class '%s' to %s.json", classData.name, CONFIG_FILE)
end

local function isBaseGameClass(name)
    if not name or name == "" then return false end
    local lower = name:lower():match("^%s*(.-)%s*$")
    reloadSavedClasses()
    if savedClasses[lower] then
        return false
    end
    local dh = tes3.dataHandler
    local ndd = dh and dh.nonDynamicData
    if not ndd or not ndd.classes then return false end

    for class in tes3.iterate(ndd.classes) do
        if class.name and class.name:lower():match("^%s*(.-)%s*$") == lower then
            if class.id:lower() ~= "newclassid_chargen" then
                return true
            end
        end
    end
    return false
end

--- Applies custom class data to the player character and recalculates stats
local function applyCustomClassToPlayer(classData)
    if not classData or not tes3.player or not tes3.player.object then return end
    local pObj = tes3.player.object
    local pClass = pObj.class
    if not pClass then return end

    pClass.name = classData.name
    pClass.description = classData.description or ""
    pClass.specialization = classData.specialization or tes3.specialization.combat

    -- Set favorite attributes
    if classData.attributes and #classData.attributes >= 2 then
        pClass.attributes[1] = classData.attributes[1]
        pClass.attributes[2] = classData.attributes[2]
    end

    -- Set major and minor skills
    if classData.majorSkills then
        for i = 1, 5 do
            if classData.majorSkills[i] then
                pClass.majorSkills[i] = classData.majorSkills[i]
            end
        end
    end
    if classData.minorSkills then
        for i = 1, 5 do
            if classData.minorSkills[i] then
                pClass.minorSkills[i] = classData.minorSkills[i]
            end
        end
    end

    -- Recalculate player skill and attribute bases based on race, class, and specialization
    local race = pObj.race
    local isFemale = pObj.female
    if race then
        -- Set attributes: race base + 10 for favorite attributes
        for attrId = 0, 7 do
            local baseVal = race.baseAttributes[attrId + 1] and race.baseAttributes[attrId + 1][isFemale and 2 or 1] or 40
            if attrId == classData.attributes[1] or attrId == classData.attributes[2] then
                baseVal = baseVal + 10
            end
            tes3.setStatistic({
                reference = tes3.player,
                attribute = attrId,
                base = baseVal,
                current = baseVal,
            })
        end

        local majorSet = {}
        for _, id in ipairs(classData.majorSkills or {}) do majorSet[id] = true end
        local minorSet = {}
        for _, id in ipairs(classData.minorSkills or {}) do minorSet[id] = true end

        for skillId = 0, 26 do
            local val = 5
            -- Check race bonus
            for _, bonus in ipairs(race.skillBonuses or {}) do
                if bonus.skill == skillId then
                    val = val + (bonus.bonus or 0)
                end
            end
            -- Specialization bonus
            local skillObj = tes3.getSkill(skillId)
            if skillObj and skillObj.specialization == classData.specialization then
                val = val + 5
            end
            -- Major / Minor
            if majorSet[skillId] then
                val = val + 25
            elseif minorSet[skillId] then
                val = val + 10
            end

            tes3.setStatistic({
                reference = tes3.player,
                skill = skillId,
                base = val,
                current = val,
            })
        end

        -- Recalculate health, magicka, fatigue using live mobile stats
        local mob = tes3.mobilePlayer
        if mob and mob.attributes then
            local str = mob.attributes[tes3.attribute.strength + 1].base
            local endur = mob.attributes[tes3.attribute.endurance + 1].base
            local intell = mob.attributes[tes3.attribute.intelligence + 1].base
            local will = mob.attributes[tes3.attribute.willpower + 1].base
            local agi = mob.attributes[tes3.attribute.agility + 1].base

            local health = math.floor((str + endur) / 2)
            local magicka = math.floor(intell * (race.magickaMultiplier or 1.0))
            local fatigue = math.floor(str + will + agi + endur)

            tes3.setStatistic({ reference = tes3.player, name = "health", base = health, current = health })
            tes3.setStatistic({ reference = tes3.player, name = "magicka", base = magicka, current = magicka })
            tes3.setStatistic({ reference = tes3.player, name = "fatigue", base = fatigue, current = fatigue })
        end
    end

    mwse.log("[mwcustomclasspersistence] Successfully applied custom class '%s' to player.", classData.name)
end

--- Formats skills list into text
local function formatSkillList(skillIds)
    local lines = {}
    for _, id in ipairs(skillIds or {}) do
        local skillObj = tes3.getSkill(id)
        local name = skillObj and skillObj.name
        if name then table.insert(lines, name) end
    end
    return table.concat(lines, "\n")
end

--- Updates MenuChooseClass display when a custom class is selected
local function displayCustomClassInChooseMenu(menu, classData)
    currentSelectedCustomClass = classData

    local selText = menu:findChild(tes3ui.registerID("MenuChooseClass_SelectedText"))
    if selText then selText.text = classData.name end

    local specText = menu:findChild(tes3ui.registerID("MenuChooseClass_SpecialText"))
    if specText then
        specText.text = SPECIALIZATION_NAMES[classData.specialization] or "Specialization"
    end

    local favText = menu:findChild(tes3ui.registerID("MenuChooseClass_FavoriteText"))
    if favText and classData.attributes then
        local a1 = ATTRIBUTE_NAMES[classData.attributes[1]] or "Strength"
        local a2 = ATTRIBUTE_NAMES[classData.attributes[2]] or "Agility"
        favText.text = string.format("%s, %s", a1, a2)
    end

    local majText = menu:findChild(tes3ui.registerID("MenuChooseClass_MajorText"))
    if majText then
        majText.text = formatSkillList(classData.majorSkills)
    end

    local minText = menu:findChild(tes3ui.registerID("MenuChooseClass_MinorText"))
    if minText then
        minText.text = formatSkillList(classData.minorSkills)
    end

    local descText = menu:findChild(tes3ui.registerID("MenuChooseClass_DescriptionText"))
    if descText then
        descText.text = classData.description or ""
    end

    menu:updateLayout()
end

--- Handles MenuChooseClass ("Pick from a list")
local function onMenuChooseClass(e)
    local menu = e.element
    local scroll = menu:findChild(tes3ui.registerID("MenuChooseClass_ClassScroll"))
    if not scroll then return end

    local content = scroll:getContentElement()
    if not content then return end

    currentSelectedCustomClass = nil
    reloadSavedClasses()

    -- When any built-in class is clicked, clear currentSelectedCustomClass
    for _, btn in ipairs(content.children) do
        btn:registerBefore("mouseClick", function()
            currentSelectedCustomClass = nil
        end)
    end

    -- Inject saved custom classes into the scroll list
    local sortedCustom = {}
    for _, data in pairs(savedClasses) do
        table.insert(sortedCustom, data)
    end
    table.sort(sortedCustom, function(a, b) return a.name:lower() < b.name:lower() end)

    if #sortedCustom > 0 then
        -- Add a divider label
        local div = content:createLabel({ text = "--- Custom Classes ---" })
        div.color = tes3ui.getPalette("header_color")
        div.borderTop = 6
        div.borderBottom = 4

        for _, classData in ipairs(sortedCustom) do
            local btn = content:createTextSelect({ text = classData.name .. " *" })
            btn:register("mouseClick", function()
                displayCustomClassInChooseMenu(menu, classData)
            end)
        end

        scroll.widget:contentsChanged()
    end

    -- Hook OK button: if a custom class is selected, apply it to player after native selection closes
    local okBtn = menu:findChild(tes3ui.registerID("MenuChooseClass_Okbutton"))
    if okBtn then
        okBtn:registerBefore("mouseClick", function()
            local selected = currentSelectedCustomClass
            if selected then
                timer.frame.delayOneFrame(function()
                    applyCustomClassToPlayer(selected)
                end)
            end
        end)
    end
end

--- Handles MenuStatReview (Final Chargen Review)
local function onMenuStatReview(e)
    local menu = e.element
    if currentSelectedCustomClass then
        local classLabel = menu:findChild(tes3ui.registerID("MenuStatReview_class"))
        if classLabel then
            classLabel.text = currentSelectedCustomClass.name
        end
        applyCustomClassToPlayer(currentSelectedCustomClass)
        menu:updateLayout()
    end

    -- When OK is clicked in StatReview, capture and auto-save the player's finalized custom class
    local okBtn = menu:findChild(tes3ui.registerID("MenuStatReview_Okbutton"))
    if okBtn then
        okBtn:registerBefore("mouseClick", function()
            timer.frame.delayOneFrame(function()
                local pObj = tes3.player and tes3.player.object
                local pClass = pObj and pObj.class
                if pClass and pClass.name and not isBaseGameClass(pClass.name) then
                    local data = {
                        name = pClass.name,
                        description = pClass.description or "",
                        specialization = pClass.specialization or tes3.specialization.combat,
                        attributes = { pClass.attributes[1], pClass.attributes[2] },
                        majorSkills = {},
                        minorSkills = {},
                    }
                    for i = 1, 5 do
                        table.insert(data.majorSkills, pClass.majorSkills[i])
                        table.insert(data.minorSkills, pClass.minorSkills[i])
                    end
                    saveCustomClass(data)
                end
            end)
        end)
    end
end

--- Handles MenuCreateClass (Saving newly created custom classes)
local function onMenuCreateClass(e)
    local menu = e.element
    local okBtn = menu:findChild(tes3ui.registerID("MenuCreateClass_Okbutton"))
    if not okBtn then return end

    okBtn:registerBefore("mouseClick", function()
        local nameElem = menu:findChild(tes3ui.registerID("MenuCreateClass_Classname"))
        local rawName = nameElem and (nameElem.text or ""):match("^%s*(.-)%s*$")
        if not rawName or rawName == "" then return end

        if isBaseGameClass(rawName) then
            tes3.messageBox({
                message = string.format("Cannot overwrite existing base class '%s'. Please choose a different name.", rawName),
                buttons = { "OK" }
            })
            return false
        end

        timer.frame.delayOneFrame(function()
            local pClass = tes3.player and tes3.player.object and tes3.player.object.class
            if pClass and pClass.name and pClass.name:lower():match("^%s*(.-)%s*$") == rawName:lower() then
                local data = {
                    name = pClass.name,
                    description = pClass.description or "",
                    specialization = pClass.specialization or tes3.specialization.combat,
                    attributes = { pClass.attributes[1], pClass.attributes[2] },
                    majorSkills = {},
                    minorSkills = {},
                }
                for i = 1, 5 do
                    table.insert(data.majorSkills, pClass.majorSkills[i])
                    table.insert(data.minorSkills, pClass.minorSkills[i])
                end

                saveCustomClass(data)
                tes3.messageBox("Custom class '%s' saved to Class Menu for future playthroughs.", data.name)
            end
        end)
    end)
end

--- Auto-captures custom classes from loaded save games
local function onLoaded(e)
    local pObj = tes3.player and tes3.player.object
    local pClass = pObj and pObj.class
    if pClass and pClass.name and not isBaseGameClass(pClass.name) then
        local data = {
            name = pClass.name,
            description = pClass.description or "",
            specialization = pClass.specialization or tes3.specialization.combat,
            attributes = { pClass.attributes[1], pClass.attributes[2] },
            majorSkills = {},
            minorSkills = {},
        }
        for i = 1, 5 do
            table.insert(data.majorSkills, pClass.majorSkills[i])
            table.insert(data.minorSkills, pClass.minorSkills[i])
        end
        saveCustomClass(data)
    end
end

local function onInitialized()
    event.register("uiActivated", onMenuChooseClass, { filter = "MenuChooseClass" })
    event.register("uiActivated", onMenuStatReview, { filter = "MenuStatReview" })
    event.register("uiActivated", onMenuCreateClass, { filter = "MenuCreateClass" })
    event.register("loaded", onLoaded)
    reloadSavedClasses()
    local count = 0
    for _ in pairs(savedClasses) do count = count + 1 end
    mwse.log("[mwcustomclasspersistence] Initialized successfully. Custom class persistence active with %d saved class(es).", count)
end

event.register("initialized", onInitialized)
