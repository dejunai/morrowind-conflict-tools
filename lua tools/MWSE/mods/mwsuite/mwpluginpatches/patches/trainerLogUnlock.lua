-- Trainer Log: the 27 training topics are added once per loaded game (on load, or when the first trainer is
-- talked to), and UI Expansion's training menu icons are scaled every time that menu opens. The topic hook on
-- MenuDialog is one-shot: it is registered only while the topics are still to be added and comes off once they
-- are. The icon scaling stays (it runs whenever a training menu opens). By dej (dejunai).

local config = require("mwpluginpatches.config")
local intercept = require("mwpluginpatches.intercept")

local trainerLogUnlock = {}
local dialogHooked = false

local TRAINING_TOPICS = {
    "Training - Acrobatics",
    "Training - Alchemy",
    "Training - Alteration",
    "Training - Armorer",
    "Training - Athletics",
    "Training - Axe",
    "Training - Block",
    "Training - Blunt Weapon",
    "Training - Conjuration",
    "Training - Destruction",
    "Training - Enchant",
    "Training - Hand-to-Hand",
    "Training - Heavy Armor",
    "Training - Illusion",
    "Training - Light Armor",
    "Training - Long Blade",
    "Training - Marksman",
    "Training - Medium Armor",
    "Training - Mercantile",
    "Training - Mysticism",
    "Training - Restoration",
    "Training - Security",
    "Training - Short Blade",
    "Training - Sneak",
    "Training - Spear",
    "Training - Speechcraft",
    "Training - Unarmored",
}

local unlocked = false

local id_skill_1 = tes3ui.registerID("UIEXP_MenuTraining_Skill1")
local id_skill_2 = tes3ui.registerID("UIEXP_MenuTraining_Skill2")
local id_skill_3 = tes3ui.registerID("UIEXP_MenuTraining_Skill3")

local function onMenuServiceTraining(e)
    local menu = e.element or tes3ui.findMenu("MenuServiceTraining")
    if not menu then return end

    local ids = { id_skill_1, id_skill_2, id_skill_3 }
    for _, btnId in ipairs(ids) do
        local block = menu:findChild(btnId)
        if block and block.children and block.children[1] then
            local border = block.children[1]
            if border.children then
                for _, child in ipairs(border.children) do
                    if child.type == tes3.uiElementType.image and child.contentPath then
                        local path = child.contentPath
                        if path:lower():find("icons") and (path:lower():find("/k/") or path:lower():find("\\k\\")) then
                            local rfdPath = path:gsub("[\\/][kK][\\/]", "/RFD/"):gsub("[\\/][kK][\\/]", "\\RFD\\")
                            if tes3.getFileExists(rfdPath) or lfs.attributes("Data Files/" .. rfdPath) or lfs.attributes("data files/" .. rfdPath) then
                                child.contentPath = rfdPath
                            end
                            child.width = 128
                            child.height = 128
                            child.scaleMode = true
                        end
                    end
                end
            end
        end
    end
    menu:updateLayout()
end

local onMenuDialog

local function hookDialog(on)
    if on and not dialogHooked then
        dialogHooked = true
        event.register(tes3.event.uiActivated, onMenuDialog, { filter = "MenuDialog" })
    elseif not on and dialogHooked then
        dialogHooked = false
        event.unregister(tes3.event.uiActivated, onMenuDialog, { filter = "MenuDialog" })
    end
end

local function unlockTopics()
    if unlocked then return end
    for _, topic in ipairs(TRAINING_TOPICS) do
        tes3.addTopic({ topic = topic })
    end
    unlocked = true
    mwse.log("[mwpluginpatches] Trainer Log: auto-unlocked 27 training topics.")
end

onMenuDialog = function(e)
    if unlocked then return end
    local serviceActor = tes3ui.getServiceActor()
    if serviceActor and serviceActor.reference and serviceActor.reference.baseObject then
        local ai = serviceActor.reference.baseObject.aiConfig
        if ai and ai.offersTraining then
            unlockTopics()
            intercept.afterDispatch(function() if unlocked then hookDialog(false) end end)
        end
    end
end

function trainerLogUnlock.dialogHooked() return dialogHooked end   -- for tests

function trainerLogUnlock.init()
    if not config.trainerLogUnlockEnabled or not config.isTrainerLogActive() then
        return
    end

    event.register(tes3.event.loaded, function()
        unlocked = false
        if config.trainerLogAutoUnlockOnLoad then
            unlockTopics()
        end
        hookDialog(not unlocked)
    end)

    event.register(tes3.event.uiActivated, onMenuServiceTraining, { filter = "MenuServiceTraining", priority = -10 })
    mwse.log("[mwpluginpatches] Trainer Log topic unlock and training icon scaling patches active.")
end

return trainerLogUnlock
