-- Party Alchemy shows a "Switched to module: [...]" debug message on initialized, at the main menu, every
-- start. Only that message, and only from Party Alchemy's main.lua, is held back. Replaces an old hand edit
-- of partyAlchemy\main.lua; that file stays as released. By dej (dejunai).
-- The message only comes from Party Alchemy's initialized handler, so the rule is taken off again once every
-- initialized handler has run: nothing of it stays for the rest of the session.

local config = require("mwpluginpatches.config")
local intercept = require("mwpluginpatches.intercept")

local this = {}
local active = false
local rule
local LAST = -9999         -- after every other initialized handler (Party Alchemy's runs at the default, 0)

function this.unload()
    if rule then intercept.removeMessageBoxDrop(rule) end
    rule = nil
    active = false
end

function this.init()
    if active then return true end
    if not (config.enabled and config.partyAlchemyModuleBoxEnabled and config.isPartyAlchemyInstalled()) then
        return false
    end
    rule = {
        label = "Party Alchemy",
        source = "/mods/partyalchemy/main.lua",
        prefix = "Switched to module:",
    }
    active = intercept.messageBoxDrop(rule) == true
    if active then
        event.register(tes3.event.initialized, this.unload, { priority = LAST })
        mwse.log("[mwpluginpatches] Party Alchemy: its 'Switched to module' message is hidden (until initialized ends).")
    else
        rule = nil
    end
    return active
end

return this
