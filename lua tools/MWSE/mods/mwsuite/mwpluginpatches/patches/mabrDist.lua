-- Mabrigash Distribution's mabDist script hands out the helmets once and sets gv_mabrDist to 1, showing a
-- "Distributing Mabrigash" popup; that popup is held back here. The popup handlers are only registered while the
-- loaded game still has gv_mabrDist at 0, and come off once the popup has been held back. A thin loaded hook stays
-- so another save (or a new game) in the same session is checked again. By dej (dejunai).

local config = require("mwpluginpatches.config")
local intercept = require("mwpluginpatches.intercept")

local mabrDist = {}
local ready, armed = false, false

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

local onUIActivated

local FILTERS = { "MenuNotify1", "MenuNotify2", "MenuNotify3", "MenuMessage" }

local function disarm(reason)
    if not armed then return end
    armed = false
    for _, filter in ipairs(FILTERS) do
        event.unregister(tes3.event.uiActivated, onUIActivated, { filter = filter, priority = 1000 })
    end
    if reason then mwse.log("[mwpluginpatches] Mabrigash Distribution: %s", reason) end
end

local function arm()
    if armed then return end
    armed = true
    for _, filter in ipairs(FILTERS) do
        event.register(tes3.event.uiActivated, onUIActivated, { filter = filter, priority = 1000 })
    end
end

-- gv_mabrDist is 0 until the script has distributed; nil when the plugin doesn't have it (then stay as before)
local function distributed()
    local g = tes3.findGlobal("gv_mabrDist")
    return g ~= nil and g.value ~= nil and g.value ~= 0
end

onUIActivated = function(e)
    if checkAndSuppress(e.element, e) then
        intercept.afterDispatch(function() disarm("popup held back; handlers removed.") end)
    end
end

local function onLoaded()
    if not config.mabrDistSuppressionEnabled then disarm() return end
    if distributed() then
        disarm("already distributed in this save; popup handlers not kept loaded.")
    else
        arm()
    end
end

function mabrDist.init()
    if ready then return true end
    if not config.mabrDistSuppressionEnabled or not config.isMabrDistActive() then
        return false
    end
    event.register(tes3.event.loaded, onLoaded)
    ready = true
    if tes3.player then onLoaded() end
    mwse.log("[mwpluginpatches] Mabrigash Distribution popup suppression will arm on a load that has not distributed yet.")
    return true
end

return mabrDist
