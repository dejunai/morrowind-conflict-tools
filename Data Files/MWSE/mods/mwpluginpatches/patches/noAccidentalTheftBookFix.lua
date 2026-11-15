local config = require("mwpluginpatches.config")

local noAccidentalTheftBookFix = {}

local currentBookTarget = nil
local isOwnedBookReading = false

local id_MenuBook = tes3ui.registerID("MenuBook")
local id_MenuScroll = tes3ui.registerID("MenuScroll")
local id_MenuBook_button_take = tes3ui.registerID("MenuBook_button_take")
local id_MenuBook_PickupButton = tes3ui.registerID("MenuBook_PickupButton")
local id_MenuBook_button_take_idle = tes3ui.registerID("MenuBook_button_take_idle")
local id_MenuBook_button_take_over = tes3ui.registerID("MenuBook_button_take_over")
local id_MenuBook_button_take_pressed = tes3ui.registerID("MenuBook_button_take_pressed")
local id_MenuScroll_Pickup = tes3ui.registerID("MenuScroll_Pickup")

--- Ensures all books across active plugins are present in noAccidentalTheft's blacklist
--- so that opening them to read while standing is never blocked by accidentalTheftProtection.
local function syncBlacklistWithBooks()
    local dh = tes3.dataHandler
    local ndd = dh and dh.nonDynamicData
    if not ndd or not ndd.books then return end

    local atpConfig = mwse.loadConfig("noAccidentalTheft")
    if not atpConfig then return end
    atpConfig.blacklist = atpConfig.blacklist or {}

    local added = 0
    for book in tes3.iterate(ndd.books) do
        local id = book.id:lower()
        if not atpConfig.blacklist[id] then
            atpConfig.blacklist[id] = true
            added = added + 1
        end
    end

    if added > 0 then
        mwse.saveConfig("noAccidentalTheft", atpConfig)
        mwse.log("[noAccidentalTheftBookFix] Synchronized %d books with noAccidentalTheft blacklist.", added)
    end
end

local function onActivate(e)
    if not config.noAccidentalTheftBookFixEnabled then return end
    if e.activator ~= tes3.player then return end
    if not e.target or not e.target.object then return end

    if e.target.object.objectType == tes3.objectType.book then
        currentBookTarget = e.target
        local isOwned = not tes3.hasOwnershipAccess({ target = e.target })
        local isSneaking = (tes3.player.mobile and tes3.player.mobile.isSneaking)
            or (tes3.mobilePlayer and tes3.mobilePlayer.isSneaking)
        isOwnedBookReading = isOwned and not isSneaking
    else
        currentBookTarget = nil
        isOwnedBookReading = false
    end
end

local function applyRedTint(el, redColor)
    if not el then return end
    el.color = redColor
    if el.children then
        for _, child in ipairs(el.children) do
            applyRedTint(child, redColor)
        end
    end
end

local function findTakeButton(menu)
    local btn = menu:findChild(id_MenuBook_button_take)
        or menu:findChild(id_MenuBook_PickupButton)
        or menu:findChild(id_MenuScroll_Pickup)

    if btn then return btn end

    -- Check specific child images
    local idle = menu:findChild(id_MenuBook_button_take_idle)
    if idle and idle.parent then return idle.parent end

    -- Fallback search across all descendants
    local function searchChildren(el)
        if not el then return nil end
        local elName = el.name and el.name:lower() or ""
        if elName:find("take") or elName:find("pickup") then
            return el
        end
        if el.contentPath and el.contentPath:lower():find("take") then
            return el
        end
        if el.children then
            for _, child in ipairs(el.children) do
                local found = searchChildren(child)
                if found then return found end
            end
        end
        return nil
    end

    return searchChildren(menu)
end

local function handleBookUI(menu, isScroll)
    if not config.noAccidentalTheftBookFixEnabled then return end
    if not isOwnedBookReading or not currentBookTarget then return end

    local takeBtn = findTakeButton(menu)
    if not takeBtn then return end

    local mode = config.ownedBookTakeMode or "disabled"

    if mode == "hidden" then
        takeBtn.visible = false
    else
        local redColor = tes3ui.getPalette("negative_color") or { 0.9, 0.2, 0.2 }

        -- Disable and redden the take icon / button
        takeBtn.disabled = true
        takeBtn.alpha = 0.55
        applyRedTint(takeBtn, redColor)

        -- If specific child images exist, tint them directly
        local idleImg = takeBtn:findChild(id_MenuBook_button_take_idle)
        if idleImg then
            idleImg.color = redColor
            idleImg.alpha = 0.55
        end
        local overImg = takeBtn:findChild(id_MenuBook_button_take_over)
        if overImg then
            overImg.color = redColor
            overImg.alpha = 0.55
        end
        local pressedImg = takeBtn:findChild(id_MenuBook_button_take_pressed)
        if pressedImg then
            pressedImg.color = redColor
            pressedImg.alpha = 0.55
        end

        local function blockAction()
            tes3.messageBox({
                message = string.format("You cannot take an owned %s without sneaking.", isScroll and "scroll" or "book"),
                buttons = { "OK" }
            })
            return false
        end

        -- Block mouse click on takeBtn and all children
        takeBtn:registerBefore("mouseClick", blockAction)
        if takeBtn.children then
            for _, child in ipairs(takeBtn.children) do
                child:registerBefore("mouseClick", blockAction)
            end
        end

        -- Retain red tint on mouse hover / leave
        takeBtn:register("mouseOver", function()
            applyRedTint(takeBtn, redColor)
        end)
        takeBtn:register("mouseLeave", function()
            applyRedTint(takeBtn, redColor)
        end)

        -- Tooltip on hover
        local function addTooltip(el)
            el:register("help", function()
                local tooltip = tes3ui.createTooltipMenu()
                local label = tooltip:createLabel({ text = "Owned: Must sneak to take" })
                label.color = redColor
            end)
        end

        addTooltip(takeBtn)
        if takeBtn.children then
            for _, child in ipairs(takeBtn.children) do
                addTooltip(child)
            end
        end
    end

    menu:updateLayout()

    -- Clean up reference state when the reading menu is closed
    menu:registerAfter(tes3.uiEvent.destroy, function()
        isOwnedBookReading = false
        currentBookTarget = nil
    end)
end

function noAccidentalTheftBookFix.init()
    if not config.noAccidentalTheftBookFixEnabled then return end

    -- Sync blacklist on game loaded so all books are allowed to be opened while standing
    event.register("loaded", syncBlacklistWithBooks)

    -- Track activation before accidentalTheftProtection executes
    event.register("activate", onActivate, { priority = 100 })

    -- Modify Book and Scroll UIs when opened
    event.register("uiActivated", function(e)
        handleBookUI(e.element, false)
    end, { filter = "MenuBook" })

    event.register("uiActivated", function(e)
        handleBookUI(e.element, true)
    end, { filter = "MenuScroll" })

    mwse.log("[mwpluginpatches] No Accidental Theft - Book Reading Fix initialized.")
end

return noAccidentalTheftBookFix
