-- Party Alchemy shows a "Switched to module: [...]" debug message on initialized, at the main menu, every
-- start. Only that message, and only from Party Alchemy's main.lua, is held back. Replaces an old hand edit
-- of partyAlchemy\main.lua; that file stays as released. By dej (dejunai).

local config = require("mwpluginpatches.config")
local intercept = require("mwpluginpatches.intercept")

local this = {}
local active = false

function this.init()
    if active then return true end
    if not (config.enabled and config.partyAlchemyModuleBoxEnabled and config.isPartyAlchemyInstalled()) then
        return false
    end
    active = intercept.messageBoxDrop({
        label = "Party Alchemy",
        source = "/mods/partyalchemy/main.lua",
        prefix = "Switched to module:",
    }) == true
    if active then
        mwse.log("[mwpluginpatches] Party Alchemy: its 'Switched to module' message is hidden.")
    end
    return active
end

return this
