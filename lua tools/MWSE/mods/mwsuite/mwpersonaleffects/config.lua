local NAME = "mwpersonaleffects"
local storedConfig = mwse.loadConfig(NAME)
local config = storedConfig or {}

if config.enabled == nil then
    local legacy = mwse.loadConfig("mwpluginpatches") or {}
    config.enabled = legacy.enabled == true and legacy.personalEffectsFixEnabled == true
end

function config.isPersonalEffectsActive()
    return tes3.isModActive("Personal Effects_MWSE.ESP")
        or tes3.isModActive("Personal Effects.ESP")
        or tes3.getObject("R0_pe_basecont") ~= nil
        or tes3.getScript("R0_pe_init_scr") ~= nil
end

function config.save()
    local plain = {}                    -- the functions on this table cannot go into JSON
    for k, v in pairs(config) do
        if type(v) ~= "function" then plain[k] = v end
    end
    mwse.saveConfig(NAME, plain)
end

return config
