--[[
    No Accidental Theft - book reading fix.

    When an owned book or scroll in the world is opened without sneaking, its Take button is hidden (or tinted
    red, by setting), so reading it cannot turn into stealing it. Nothing about the book itself is touched.
]]
local config = require("mwpluginpatches.config")

local this = {}

local ownedOpen = false     -- the book being activated is someone else's and the player is not sneaking

local function onActivate(e)
    if e.activator ~= tes3.player then return end
    local object = e.target and e.target.object
    ownedOpen = object ~= nil and object.objectType == tes3.objectType.book
        and not tes3.mobilePlayer.isSneaking
        and not tes3.hasOwnershipAccess({ target = e.target })
end

local function onBookMenu(e)
    if not ownedOpen then return end
    ownedOpen = false
    if not config.noAccidentalTheftBookFixEnabled then return end
    local take = e.element:findChild("MenuBook_button_take") or e.element:findChild("MenuBook_PickupButton")
    if not take then return end
    if config.ownedBookTakeMode == "hidden" then
        take.visible = false
    else
        local red = tes3ui.getPalette("negative_color")
        take.color = red
        for _, child in ipairs(take.children) do child.color = red end
    end
    e.element:updateLayout()
end

function this.init()
    event.register("activate", onActivate, { priority = 100 })
    event.register("uiActivated", onBookMenu, { filter = "MenuBook" })
    event.register("uiActivated", onBookMenu, { filter = "MenuScroll" })
    mwse.log("[mwpluginpatches] No Accidental Theft - Book Reading Fix initialized.")
end

return this
