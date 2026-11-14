local config = require("mwpluginpatches.config")

local lostHeirDelay = {}

local sourceMod = "t_lostheir.esp"
local topic = "A2_4_MiloGone"
local journalIndex = 1

local function journalRequirementsAreMet()
    return tes3.getJournalIndex({ id = topic }) >= journalIndex
end

local function onReferenceActivated(e)
    if not config.lostHeirDelayEnabled or not config.isLostHeirActive() then
        return
    end

    if not e or not e.reference then return end
    local src = e.reference.sourceMod
    if src and (src:lower() == sourceMod or src:lower() == "lostheir.esp") then
        if not journalRequirementsAreMet() then
            e.reference:disable()
        elseif e.reference.disabled and not (e.reference.data and e.reference.data.enabledAfterJournalUpdate) then
            if e.reference.supportsLuaData then
                e.reference.data.enabledAfterJournalUpdate = true
            end
            e.reference:enable()
        end
    end
end

function lostHeirDelay.init()
    if not config.lostHeirDelayEnabled or not config.isLostHeirActive() then
        return
    end

    event.register("referenceActivated", onReferenceActivated)
    mwse.log("[mwpluginpatches] The Lost Heir Delayer patch active.")
end

return lostHeirDelay
