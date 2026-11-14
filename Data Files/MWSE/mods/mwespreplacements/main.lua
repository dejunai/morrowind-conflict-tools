local config = require("mwespreplacements.config")
local equipment = require("mwespreplacements.tweaks.equipment")
local visuals = require("mwespreplacements.tweaks.visuals")
local scripts = require("mwespreplacements.tweaks.scripts")

local function onInitialized()
    if not config.enabled then
        mwse.log("[ESP Replacements] Mod is disabled in config.")
        return
    end

    mwse.log("[ESP Replacements] Initializing ESP replacement tweaks...")

    local okEquip, errEquip = pcall(equipment.apply, config)
    if not okEquip then
        mwse.log("[ESP Replacements] Error in equipment tweaks: %s", tostring(errEquip))
    end

    local okVis, errVis = pcall(visuals.apply, config)
    if not okVis then
        mwse.log("[ESP Replacements] Error in visual tweaks: %s", tostring(errVis))
    end

    local okScr, errScr = pcall(scripts.apply, config)
    if not okScr then
        mwse.log("[ESP Replacements] Error in script tweaks: %s", tostring(errScr))
    end

    mwse.log("[ESP Replacements] Initialized successfully.")
end

event.register(tes3.event.initialized, onInitialized)

-- Load MCM
require("mwespreplacements.mcm")
