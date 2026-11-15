local config = require("mwpluginpatches.config")

local noAccidentalTheftBookFix = {}

local currentBookTarget = nil
local isOwnedBookReading = false

--- Ensures all books across active plugins are present in noAccidentalTheft's blacklist
--- so that opening them to read while standing is never blocked by accidentalTheftProtection.
local function syncBlacklistWithBooks()
    local atpConfig = mwse.loadConfig("noAccidentalTheft")
    if not atpConfig then return end
    atpConfig.blacklist = atpConfig.blacklist or {}

    local added = 0
    for book in tes3.iterate(tes3.dataHandler.nonDynamicData.books) do
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
        local isSneaking = tes3.player.mobile and tes3.player.mobile.isSneaking
        isOwnedBookReading = isOwned and not isSneaking
    else
        currentBookTarget = nil
        isOwnedBookReading = false
    end
end

local function handleBookUI(menu, isScroll)
    if not config.noAccidentalTheftBookFixEnabled then return end
    if not isOwnedBookReading or not currentBookTarget then return end

    -- Find the Take button in Book or Scroll menus
    local takeBtn = menu:findChild("MenuBook_button_take")
        or menu:findChild("MenuBook_PickupButton")
        or menu:findChild("MenuScroll_Pickup")

    if not takeBtn then
        for child in table.traverse({ menu }) do
            if child.id and (child.id:lower():find("take") or child.id:lower():find("pickup")) then
                takeBtn = child
                break
            end
        end
    end

    if takeBtn then
        local mode = config.ownedBookTakeMode or "disabled"

        if mode == "hidden" then
            takeBtn.visible = false
        else
            -- Disabled, greyed out, and red-tinted
            takeBtn.disabled = true
            takeBtn.alpha = 0.35
            takeBtn.color = tes3ui.getPalette("negative_color")

            -- Intercept and block mouse clicks and shortcut keys
            takeBtn:registerBefore("mouseClick", function()
                tes3.messageBox({
                    message = string.format("You cannot take an owned %s without sneaking.", isScroll and "scroll" or "book"),
                    buttons = { "OK" }
                })
                return false
            end)

            -- Show clear tooltip on hover
            takeBtn:register("help", function(e)
                local tooltip = tes3ui.createTooltipMenu()
                local label = tooltip:createLabel({ text = "Owned: Must sneak to take" })
                label.color = tes3ui.getPalette("negative_color")
            end)
        end

        menu:updateLayout()
    end

    -- Clean up reference state when the reading menu is closed
    menu:registerAfter(tes3.uiEvent.destroy, function()
        isOwnedBookReading = false
        currentBookTarget = nil
    end)
end

function noAccidentalTheftBookFix.init()
    if not config.noAccidentalTheftBookFixEnabled then return end

    -- Sync blacklist on startup so all books are allowed to be opened while standing
    syncBlacklistWithBooks()

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
