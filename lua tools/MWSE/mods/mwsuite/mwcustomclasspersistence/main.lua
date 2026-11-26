--[[
    Custom Class Persistence (mwcustomclasspersistence)

    A class made in the Create Class menu is saved to config\savedCustomClasses.json when the menu is accepted.
    In later games the saved classes are listed at the bottom of the "pick from a list" menu. Choosing one
    opens the game's own Create Class menu with its name, specialization, two attributes and ten skills already
    selected; pressing OK there makes the class exactly as the game does for a hand-made one. This mod never
    calculates or sets a stat itself and never edits a base-game class.

    How the Create Class menu keeps its choices (read from Morrowind.exe; the same in every build, because these
    are element names and record layout, not code addresses):
      - the class being built is the menu's "MenuCreateClass_Class" property; picking something writes straight
        into that record (specialization, attributes[1..2], skills[1..10] as minor1, major1, minor2, major2 ...)
      - each button also carries its choice: "MenuCreateClass_skill" / "MenuCreateClass_attriubte" (the game's
        own spelling) and shows the choice as its text
      - the name is the text of "MenuCreateClass_NameSpace"
]]

local CONFIG_FILE = "savedCustomClasses"
local CHARGEN_ID = "newclassid_chargen"
local SLOT = { "One", "Two", "Three", "Four", "Five" }
local log = function(fmt, ...) mwse.log("[mwcustomclasspersistence] " .. fmt, ...) end

local function trim(s) return (s or ""):match("^%s*(.-)%s*$") end
local function loadSaved() return mwse.loadConfig(CONFIG_FILE, {}) or {} end
-- settings live apart from the saved classes, which are a plain list
local settings = mwse.loadConfig("mwcustomclasspersistence", { enabled = false })

--- true when a class of the game or of a plugin already has this name (a saved custom class may be overwritten)
local function isKnownClassName(name)
    local lower = name:lower()
    for class in tes3.iterate(tes3.dataHandler.nonDynamicData.classes) do
        if class.id:lower() ~= CHARGEN_ID and trim(class.name):lower() == lower then return true end
    end
    return false
end

-- Create Class menu ---------------------------------------------------------------------------------

local pending   -- the saved class to put into the Create Class menu when it next opens

local function chargenClass(menu)
    local ok, class = pcall(menu.getPropertyObject, menu, "MenuCreateClass_Class")
    return (ok and class) or tes3.findClass("NewClassID_CharGen")
end

--- the class as it stands in the Create Class menu
local function capture(menu)
    local class = chargenClass(menu)
    local nameBox = menu:findChild("MenuCreateClass_NameSpace")
    if not (class and nameBox) then return nil end
    local data = {
        name = trim(nameBox.text),
        specialization = class.specialization,
        attributes = { class.attributes[1], class.attributes[2] },
        majorSkills = {},
        minorSkills = {},
    }
    for i = 1, 5 do
        data.minorSkills[i] = class.skills[2 * i - 1]
        data.majorSkills[i] = class.skills[2 * i]
    end
    return data
end

--- puts a saved class into the Create Class menu; false (and nothing half-done that matters) when it cannot
local function prefill(menu, data)
    local class = chargenClass(menu)
    if not class then return false, "the menu has no class record" end

    local function button(id, text, property, value)
        local el = menu:findChild(id)
        if not el then error("no " .. id) end
        el.text = text
        if property then el:setPropertyInt(property, value) end
    end

    local ok, err = pcall(function()
        class.specialization = data.specialization
        button("MenuCreateClass_Special", tes3.getSpecializationName(data.specialization))
        for i = 1, 2 do
            class.attributes[i] = data.attributes[i]
            button("MenuCreateClass_Attribute" .. SLOT[i], tes3.getAttributeName(data.attributes[i]),
                "MenuCreateClass_attriubte", data.attributes[i])
        end
        for i = 1, 5 do
            class.skills[2 * i - 1] = data.minorSkills[i]
            class.skills[2 * i] = data.majorSkills[i]
            button("MenuCreateClass_MinorSkill" .. SLOT[i], tes3.getSkillName(data.minorSkills[i]),
                "MenuCreateClass_skill", data.minorSkills[i])
            button("MenuCreateClass_MajorSkill" .. SLOT[i], tes3.getSkillName(data.majorSkills[i]),
                "MenuCreateClass_skill", data.majorSkills[i])
        end
        button("MenuCreateClass_NameSpace", data.name)
    end)
    if not ok then return false, tostring(err) end

    -- the record must now read back as the saved class
    local now = capture(menu)
    for i = 1, 5 do
        if now.majorSkills[i] ~= data.majorSkills[i] or now.minorSkills[i] ~= data.minorSkills[i] then
            return false, "the class record did not take the skills"
        end
    end
    if now.attributes[1] ~= data.attributes[1] or now.attributes[2] ~= data.attributes[2] then
        return false, "the class record did not take the attributes"
    end
    menu:updateLayout()
    return true
end

local function onMenuCreateClass(e)
    if not settings.enabled then return end
    local menu = e.element

    if pending then
        local data = pending
        pending = nil
        local ok, err = prefill(menu, data)
        if ok then
            log("'%s' loaded into the Create Class menu.", data.name)
        else
            log("Could not load '%s' into the Create Class menu: %s", data.name, err)
            tes3.messageBox("The saved class '%s' could not be loaded. Check every choice before accepting.", data.name)
        end
    end

    local okButton = menu:findChild("MenuCreateClass_Okbutton")
    if not okButton then return end
    okButton:registerBefore("mouseClick", function()
        local data = capture(menu)
        if not data or data.name == "" then return end      -- the game reports a missing name itself
        if isKnownClassName(data.name) then
            tes3.messageBox({
                message = string.format("'%s' is already the name of a class. Choose a different name.", data.name),
                buttons = { tes3.findGMST(tes3.gmst.sOK).value },
            })
            return false
        end
        -- the game still checks the class (two different attributes, no skill twice); it is saved only if the
        -- menu was accepted, which is when it is gone
        timer.delayOneFrame(function()
            if tes3ui.findMenu("MenuCreateClass") then return end
            local saved = loadSaved()
            saved[data.name:lower()] = data
            mwse.saveConfig(CONFIG_FILE, saved)
            log("Saved custom class '%s'.", data.name)
        end, timer.real)
    end)
end

-- Choose Class menu ---------------------------------------------------------------------------------

--- sets the text of the menu's elements called `name`, in order (the game makes one label per attribute and skill)
local function setTexts(menu, name, texts)
    local id, n = tes3ui.registerID(name), 0
    local function walk(el)
        for _, child in ipairs(el.children) do
            if child.id == id then
                n = n + 1
                if texts[n] then child.text = texts[n] end
            end
            walk(child)
        end
    end
    walk(menu)
end

--- the two favoured-attribute labels are found by what they show, an attribute's name: their element names differ
local function setAttributeTexts(menu, texts)
    local names, found = {}, {}
    for _, id in pairs(tes3.attribute) do names[tes3.getAttributeName(id)] = true end
    local function walk(el)
        for _, child in ipairs(el.children) do
            if names[child.text] then found[#found + 1] = child end
            walk(child)
        end
    end
    walk(menu)
    if #found ~= 2 then
        log("Choose Class menu: expected 2 attribute labels, found %d.", #found)
        return
    end
    for i = 1, 2 do found[i].text = texts[i] end
end

local function showInChooseMenu(menu, data)
    local major, minor = {}, {}
    for i = 1, 5 do
        major[i] = tes3.getSkillName(data.majorSkills[i])
        minor[i] = tes3.getSkillName(data.minorSkills[i])
    end
    setTexts(menu, "MenuChooseClass_SpecialText", { tes3.getSpecializationName(data.specialization) })
    setAttributeTexts(menu, { tes3.getAttributeName(data.attributes[1]), tes3.getAttributeName(data.attributes[2]) })
    setTexts(menu, "MenuChooseClass_MajorText", major)
    setTexts(menu, "MenuChooseClass_MinorText", minor)
    setTexts(menu, "MenuChooseClass_DescriptionText",
        { string.format("%s - your saved custom class. OK opens it in the Create Class menu.", data.name) })
    menu:updateLayout()
end

local function validClass(data)
    return type(data) == "table" and type(data.name) == "string" and tonumber(data.specialization)
        and type(data.attributes) == "table" and #data.attributes == 2
        and type(data.majorSkills) == "table" and #data.majorSkills == 5
        and type(data.minorSkills) == "table" and #data.minorSkills == 5
end

local function onMenuChooseClass(e)
    pending = nil
    if not settings.enabled then return end
    local menu = e.element
    local scroll = menu:findChild("MenuChooseClass_ClassScroll")
    local content = scroll and scroll:getContentElement()
    if not content then return end

    local list = {}
    for _, data in pairs(loadSaved()) do
        if validClass(data) then list[#list + 1] = data end
    end
    if #list == 0 then return end
    table.sort(list, function(a, b) return a.name:lower() < b.name:lower() end)

    local selected, buttons = nil, {}
    local function mark()
        for data, button in pairs(buttons) do
            button.widget.state = (data == selected) and tes3.uiState.active or tes3.uiState.normal
        end
    end

    for _, child in ipairs(content.children) do     -- picking one of the game's classes drops ours
        child:registerBefore("mouseClick", function()
            selected = nil
            mark()
        end)
    end

    local header = content:createLabel({ text = "Saved custom classes" })
    header.color = tes3ui.getPalette("header_color")
    header.borderTop = 6
    for _, data in ipairs(list) do
        local button = content:createTextSelect({ text = data.name })
        buttons[data] = button
        button:register("mouseClick", function()
            selected = data
            mark()
            showInChooseMenu(menu, data)
        end)
    end
    scroll.widget:contentsChanged()

    local okButton = menu:findChild("MenuChooseClass_Okbutton")
    local backButton = menu:findChild("MenuChooseClass_Backbutton")
    if not (okButton and backButton) then return end
    okButton:registerBefore("mouseClick", function()
        if not selected then return end
        -- back to the "how do you want to choose" menu, then into Create Class, where the class is filled in
        pending = selected
        backButton:triggerEvent("mouseClick")
        timer.delayOneFrame(function()
            local choice = tes3ui.findMenu("MenuClassChoice")
            local create = choice and choice:findChild("MenuClassChoice_CreateClassbutton")
            if create then
                create:triggerEvent("mouseClick")
            elseif pending then
                tes3.messageBox("Choose to create a class: '%s' will be filled in for you.", pending.name)
            end
        end, timer.real)
        return false
    end)
end

event.register("uiActivated", onMenuChooseClass, { filter = "MenuChooseClass" })
event.register("uiActivated", onMenuCreateClass, { filter = "MenuCreateClass" })

event.register("modConfigReady", function()
    local template = mwse.mcm.createTemplate({ name = "Custom Class Persistence",
        onClose = function() mwse.saveConfig("mwcustomclasspersistence", settings) end })
    local page = template:createSideBarPage({ label = "Settings" })
    page.sidebar:createInfo({ text = "Classes made in the Create Class menu are saved and offered again at the "
        .. "bottom of the class list in later games. Picking one fills in the Create Class menu for you." })
    page:createYesNoButton({
        label = "Save and offer custom classes",
        description = "Saves the classes you make in the Create Class menu and lists them at the bottom of the class list "
            .. "in later new games, so you don't have to build them again.",
        variable = mwse.mcm.createTableVariable({ id = "enabled", table = settings }),
    })
    template:register()
end)
