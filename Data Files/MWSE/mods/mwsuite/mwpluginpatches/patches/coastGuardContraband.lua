--[[
    Seyda Neen Coast Guard: Contraband Bulk Turn-In & Selective Retention
    Mod: Vvardenfell Distribution - Seyda Neen Coast Guard.ESP
--]]

local config = require("mwpluginpatches.config")

local coastGuardContraband = {}

local CONTRABAND_ITEMS = {
    {
        id = "potion_skooma_01",
        name = "Skooma",
        bounty = 50,
        infoId = "394419472248279556",
        configKey = "coastGuardTurnInSkooma",
        unitName = "bottle",
        unitNamePlural = "bottles",
    },
    {
        id = "ingred_raw_ebony_01",
        name = "Raw Ebony",
        bounty = 20,
        infoId = "2346497772141610621",
        configKey = "coastGuardTurnInRawEbony",
        unitName = "chunk",
        unitNamePlural = "chunks",
    },
    {
        id = "ingred_raw_glass_01",
        name = "Raw Glass",
        bounty = 20,
        infoId = "23200382773445447",
        configKey = "coastGuardTurnInRawGlass",
        unitName = "piece",
        unitNamePlural = "pieces",
    },
    {
        id = "ingred_moon_sugar_01",
        name = "Moon Sugar",
        bounty = 5,
        infoId = "219407933038216236",
        configKey = "coastGuardTurnInMoonSugar",
        unitName = "portion",
        unitNamePlural = "portions",
    },
    {
        id = "misc_6th_ash_statue_01",
        name = "Ash Statue",
        bounty = 25,
        infoId = "1640947703220407",
        configKey = "coastGuardTurnInAshStatues",
        unitName = "statue",
        unitNamePlural = "statues",
    },
}

local VAMPIRE_DUST_DEF = {
    id = "ingred_vampire_dust_01",
    name = "Vampire Dust",
    bounty = 50,
    configKey = "coastGuardTurnInVampireDust",
    unitName = "portion",
    unitNamePlural = "portions",
}

local FALLBACK_INFO_ID = "115807095757923365"

local function getActiveContrabandDef(infoId)
    for _, item in ipairs(CONTRABAND_ITEMS) do
        if item.infoId == infoId then
            return item
        end
    end
    return nil
end

local function hasAnyActiveContraband()
    for _, item in ipairs(CONTRABAND_ITEMS) do
        if config[item.configKey] ~= false then
            local count = tes3.getItemCount({ reference = tes3.player, item = item.id })
            if count > 0 then
                return true
            end
        end
    end
    if config.coastGuardTurnInVampireDust then
        local count = tes3.getItemCount({ reference = tes3.player, item = VAMPIRE_DUST_DEF.id })
        if count > 0 then
            return true
        end
    end
    return false
end

-- Pending bulk state between infoGetText and infoResponse. infoGetText also fires when anything else reads a
-- response's text (UI Expansion, other mods), so the turn-in is tied to the response that armed it.
local pendingBulk = nil

local function onInfoFilter(e)
    if not e.passes then return end
    if not config.coastGuardContrabandEnabled then return end

    local dialogue = e.dialogue
    if not dialogue or dialogue.id:lower() ~= "contraband" then return end

    local infoId = tostring(e.info.id)
    local item = getActiveContrabandDef(infoId)

    if item then
        -- User disabled turning in this specific type -> keep it in inventory
        if config[item.configKey] == false then
            e.passes = false
            return
        end

        local count = tes3.getItemCount({ reference = tes3.player, item = item.id })
        if count <= 0 then
            e.passes = false
            return
        end
        return
    end

    if infoId == FALLBACK_INFO_ID then
        -- Optional Vampire Dust turn-in
        if config.coastGuardTurnInVampireDust then
            local vCount = tes3.getItemCount({ reference = tes3.player, item = VAMPIRE_DUST_DEF.id })
            if vCount > 0 then
                return
            end
        end

        -- If player has 0 active/enabled contraband left, hide the topic
        if config.coastGuardHideExhausted and not hasAnyActiveContraband() then
            e.passes = false
            return
        end
    end
end

local function onInfoGetText(e)
    if not config.coastGuardContrabandEnabled then return end

    local dialogue = e.dialogue
    if not dialogue or dialogue.id:lower() ~= "contraband" then return end

    local infoId = tostring(e.info.id)
    local item = getActiveContrabandDef(infoId)

    if item then
        local count = tes3.getItemCount({ reference = tes3.player, item = item.id })
        if count > 0 then
            local turnInCount = config.coastGuardBulkTurnIn and count or 1
            local totalBounty = turnInCount * item.bounty
            local unitStr = turnInCount == 1 and item.unitName or item.unitNamePlural

            pendingBulk = {
                infoId = infoId,
                item = item.id,
                name = item.name,
                count = turnInCount,
                bounty = item.bounty,
                totalBounty = totalBounty,
                unit = unitStr,
                isVanillaScripted = true,
            }

            if config.coastGuardBulkTurnIn and turnInCount > 1 then
                if item.id == "potion_skooma_01" then
                    e.text = string.format(
                        "Is that skooma? Good find - I don't know if you raided some poor soul's stash or took it off a smuggler's corpse, and I don't much care, I'm just happy to see it out of circulation. Here, %d drakes for all %d %s, good work.",
                        totalBounty, turnInCount, unitStr
                    )
                elseif item.id == "ingred_raw_ebony_01" then
                    e.text = string.format(
                        "Raw ebony? Must be glad to be rid of all this weight. Here's %d drakes for all %d %s, anything else to report?",
                        totalBounty, turnInCount, unitStr
                    )
                elseif item.id == "ingred_raw_glass_01" then
                    e.text = string.format(
                        "Raw glass, hm? I'm surprised, there isn't too much in circulation among smugglers recently. Here's %d drakes for all %d %s, anything else to turn in?",
                        totalBounty, turnInCount, unitStr
                    )
                elseif item.id == "ingred_moon_sugar_01" then
                    e.text = string.format(
                        "Is that moon sugar? We don't get enough of this dropped off, most adventurers prefer pawning the stuff. Damn cats. Here's %d drakes for all %d %s, anything else?",
                        totalBounty, turnInCount, unitStr
                    )
                elseif item.id == "misc_6th_ash_statue_01" then
                    e.text = string.format(
                        "Another one of these wretched things? I don't know exactly what the significance of these statues is, but we've been told to destroy any we come across. Here - %d gold for all %d %s, thank you for your service. Anything else to report?",
                        totalBounty, turnInCount, unitStr
                    )
                end
            end
        end
        return
    end

    if infoId == FALLBACK_INFO_ID and config.coastGuardTurnInVampireDust then
        local count = tes3.getItemCount({ reference = tes3.player, item = VAMPIRE_DUST_DEF.id })
        if count > 0 then
            local turnInCount = config.coastGuardBulkTurnIn and count or 1
            local totalBounty = turnInCount * VAMPIRE_DUST_DEF.bounty
            local unitStr = turnInCount == 1 and VAMPIRE_DUST_DEF.unitName or VAMPIRE_DUST_DEF.unitNamePlural

            pendingBulk = {
                infoId = infoId,
                item = VAMPIRE_DUST_DEF.id,
                name = VAMPIRE_DUST_DEF.name,
                count = turnInCount,
                bounty = VAMPIRE_DUST_DEF.bounty,
                totalBounty = totalBounty,
                unit = unitStr,
                isVanillaScripted = false,
            }

            e.text = string.format(
                "Vampire dust? Foul stuff, tainted by dark sorcery and undeath. The Temple and the Legion will be glad to see it destroyed. Here's %d drakes for all %d %s, good work. Anything else to report?",
                totalBounty, turnInCount, unitStr
            )
        end
    end
end

local function onInfoResponse(e)
    if not config.coastGuardContrabandEnabled then return end
    if not pendingBulk then return end

    local turnIn = pendingBulk
    pendingBulk = nil
    if tostring(e.info.id) ~= turnIn.infoId then return end    -- another response: this one's text was only read

    local extraCount = turnIn.isVanillaScripted and (turnIn.count - 1) or turnIn.count
    local extraBounty = extraCount * turnIn.bounty

    if extraCount > 0 then
        tes3.removeItem({
            reference = tes3.player,
            item = turnIn.item,
            count = extraCount,
            playSound = false,
        })
        tes3.addItem({
            reference = tes3.player,
            item = "gold_001",
            count = extraBounty,
            playSound = true,
        })
    elseif not turnIn.isVanillaScripted and turnIn.count == 1 then
        tes3.removeItem({
            reference = tes3.player,
            item = turnIn.item,
            count = 1,
            playSound = false,
        })
        tes3.addItem({
            reference = tes3.player,
            item = "gold_001",
            count = turnIn.bounty,
            playSound = true,
        })
    end

    tes3.messageBox({
        message = string.format("Turned in %d %s for %d gold.", turnIn.count, turnIn.name, turnIn.totalBounty),
    })

    -- Refresh dialogue topic list
    timer.delayOneFrame(function()
        local menu = tes3ui.findMenu(tes3ui.registerID("MenuDialog"))
        if menu then
            menu:update()
        end
    end)
end

function coastGuardContraband.init()
    event.register("infoFilter", onInfoFilter)
    event.register("infoGetText", onInfoGetText)
    event.register("infoResponse", onInfoResponse)
end

return coastGuardContraband
