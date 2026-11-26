-- Magican't checks every frame (enterFrame) whether the player can afford the selected spell and updates the
-- HUD magic fill bar. Here that check is skipped while a menu is open; the bar catches up when the menu closes.
-- Replaces an old hand edit of tew\Magican't\main.lua; that file stays as released. By dej (dejunai).

local config = require("mwpluginpatches.config")
local intercept = require("mwpluginpatches.intercept")

local this = {}
local active = false

function this.init()
    if active then return true end
    if not (config.enabled and config.magicantMenuGuardEnabled and config.isMagicantInstalled()) then
        return false
    end
    active = intercept.skipWhen({
        label = "Magican't",
        source = "/mods/tew/magican't/main.lua",
        event = "enterFrame",
        what = "menu-mode guard",
        when = function() return tes3.menuMode() == true end,
    }) == true
    if active then
        mwse.log("[mwpluginpatches] Magican't: its fill-bar check is skipped while a menu is open.")
    end
    return active
end

return this
