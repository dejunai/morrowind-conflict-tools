local config = require("mwpluginpatches.config")

local mabrDist = {}

local idMenuMessage_message = tes3ui.registerID("MenuMessage_message")
local idMenuNotify_message = tes3ui.registerID("MenuNotify_message")

local function checkAndSuppress(menu, e)
    if not menu then return end

    local text = nil
    local el = menu:findChild(idMenuNotify_message) or menu:findChild(idMenuMessage_message) or menu:findChild(-580)
    if el and el.text then
        text = el.text
    else
        text = menu.text
    end

    if text and text:find("Distributing Mabrigash") then
        menu.visible = false
        if e then e.claim = true end
        menu:destroy()
        return true
    end

    -- Fallback: check all direct children
    for _, child in ipairs(menu.children or {}) do
        if child.text and child.text:find("Distributing Mabrigash") then
            menu.visible = false
            if e then e.claim = true end
            menu:destroy()
            return true
        end
    end
end

local function onUIActivated(e)
    checkAndSuppress(e.element, e)
end

function mabrDist.init()
    if not config.mabrDistSuppressionEnabled or not config.isMabrDistActive() then
        return
    end

    for i = 1, 3 do
        event.register(tes3.event.uiActivated, onUIActivated, { filter = "MenuNotify" .. i, priority = 1000 })
    end
    event.register(tes3.event.uiActivated, onUIActivated, { filter = "MenuMessage", priority = 1000 })

    mwse.log("[mwpluginpatches] Mabrigash Distribution popup suppression active.")
end

return mabrDist
