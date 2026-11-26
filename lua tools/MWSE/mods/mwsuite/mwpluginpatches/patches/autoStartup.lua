-- AutoStartup answers Morrowind Comes Alive's and Ebonheart Underworks' setup questions once per save from the
-- MCM settings. Its popup and cell-change handlers are only registered while the loaded game still needs that
-- setup (MCA_Loaded not 1 or an invalid party size of 3; dd19rebirthConfig not 1), and come off once it is done.
-- The loaded hook stays so another save or a new game in the same session is checked again. By dej (dejunai).

local config = require("mwpluginpatches.config")
local intercept = require("mwpluginpatches.intercept")

local autoStartup = {}
local armed = false

local function runScript(cmd)
    tes3.runLegacyScript({ command = cmd })
end

function autoStartup.applyMCACustomization()
    -- 1. Companions & Ordinator Shareel
    local noComp = tes3.findGlobal("MCA_NoCompanions")
    if noComp then
        noComp.value = config.mcaCompanions and 0 or 1
    end
    if config.mcaCompanions then
        runScript('"_MCA_ordinator_shareel1"->Enable')
        runScript('"_MCA_ordinator_shareel2"->Enable')
    else
        runScript('"_MCA_ordinator_shareel1"->Disable')
        runScript('"_MCA_ordinator_shareel2"->Disable')
    end

    -- 2. Courtesans / Hookers
    if config.mcaCourtesans == "none" then
        runScript('RemoveFromLevCreature "_MCA_courtesans_female" "_MCA_courtesans_female_list" -1')
        runScript('RemoveFromLevCreature "_MCA_courtesans_male" "_MCA_courtesans_male_list" -1')
    elseif config.mcaCourtesans == "female" then
        runScript('RemoveFromLevCreature "_MCA_courtesans_male" "_MCA_courtesans_male_list" -1')
        runScript('AddToLevCreature "_MCA_courtesans_female" "_MCA_courtesans_female_list" 1')
    elseif config.mcaCourtesans == "male" then
        runScript('RemoveFromLevCreature "_MCA_courtesans_female" "_MCA_courtesans_female_list" -1')
        runScript('AddToLevCreature "_MCA_courtesans_male" "_MCA_courtesans_male_list" 1')
    else -- "all"
        runScript('AddToLevCreature "_MCA_courtesans_female" "_MCA_courtesans_female_list" 1')
        runScript('AddToLevCreature "_MCA_courtesans_male" "_MCA_courtesans_male_list" 1')
    end

    -- 3. Angry Tavern Patrons / Hostile Drunks
    if config.mcaHostileDrunks then
        runScript('AddToLevCreature "_MCA_drunkards_in" "_MCA_drunkards_hostile" 1')
    else
        runScript('RemoveFromLevCreature "_MCA_drunkards_in" "_MCA_drunkards_hostile" -1')
    end

    -- 4. Respawning hostile NPCs in caves & ruins
    if config.mcaRespawnCaves then
        runScript('AddToLevCreature "_MCA_in_daedric_ruin" "_MCA_daedra_worshippers" 1')
        runScript('AddToLevCreature "_MCA_in_shrine_malacath" "_MCA_orcs_and_goblins_random" 1')
        runScript('AddToLevCreature "_MCA_in_cave_bandits" "_MCA_bandits_all" 1')
        runScript('AddToLevCreature "_MCA_in_cave_dunmer" "_MCA_dunmer_thugs" 1')
        runScript('AddToLevCreature "_MCA_in_cave_witches" "_MCA_witches" 1')
        runScript('AddToLevCreature "_MCA_in_cave_wizards" "_MCA_wizards" 1')
    else
        runScript('RemoveFromLevCreature "_MCA_in_daedric_ruin" "_MCA_daedra_worshippers" -1')
        runScript('RemoveFromLevCreature "_MCA_in_shrine_malacath" "_MCA_orcs_and_goblins_random" -1')
        runScript('RemoveFromLevCreature "_MCA_in_cave_bandits" "_MCA_bandits_all" -1')
        runScript('RemoveFromLevCreature "_MCA_in_cave_dunmer" "_MCA_dunmer_thugs" -1')
        runScript('RemoveFromLevCreature "_MCA_in_cave_witches" "_MCA_witches" -1')
        runScript('RemoveFromLevCreature "_MCA_in_cave_wizards" "_MCA_wizards" -1')
    end

    -- 5. Bandit attacks on towns
    if config.mcaBanditAttacksTowns then
        runScript('AddToLevCreature "_MCA_ex_other" "_MCA_ex_bandits_towns" 1')
        runScript('AddToLevCreature "_MCA_ex_other_6th" "_MCA_ex_bandits_towns" 1')
    else
        runScript('RemoveFromLevCreature "_MCA_ex_other" "_MCA_ex_bandits_towns" -1')
        runScript('RemoveFromLevCreature "_MCA_ex_other_6th" "_MCA_ex_bandits_towns" -1')
    end

    -- 6. Angry Ashlanders at outcast campsites
    if config.mcaHostileAshlanders then
        runScript('AddToLevCreature "_MCA_ex_outcast_camp" "_MCA_ashlanders_outcasts" 1')
        runScript('AddToLevCreature "_MCA_ex_outcast_camp_mabrigash" "_MCA_mabrigash" 1')
    else
        runScript('RemoveFromLevCreature "_MCA_ex_outcast_camp" "_MCA_ashlanders_outcasts" -1')
        runScript('RemoveFromLevCreature "_MCA_ex_outcast_camp_mabrigash" "_MCA_mabrigash" -1')
    end

    -- 7. Bandits / Highwaymen at crossroads
    if config.mcaCrossroadBandits then
        runScript('AddToLevCreature "_MCA_ex_highwaymen" "_MCA_highwaymen" 1')
    else
        runScript('RemoveFromLevCreature "_MCA_ex_highwaymen" "_MCA_highwaymen" -1')
    end

    -- 8. Hostile party size
    local moreEnemies = tes3.findGlobal("MCA_MoreEnemies")
    if moreEnemies then
        moreEnemies.value = config.mcaPartySize or 0
    end
end

function autoStartup.applyStartupConfig()
    -- 1. Morrowind Comes Alive (MCA)
    if config.mcaEnabled and config.isMcaActive() then
        local mcaLoaded = tes3.findGlobal("MCA_Loaded")
        if mcaLoaded and mcaLoaded.value ~= 1 then
            mcaLoaded.value = 1

            tes3.addTopic({ topic = "travel together" })
            tes3.addTopic({ topic = "Orders" })
            tes3.addTopic({ topic = "healing" })

            local fightingBandits = tes3.findGlobal("MCA_FightingBandits")
            if fightingBandits then
                fightingBandits.value = 0
            end

            autoStartup.applyMCACustomization()
            mwscript.stopScript({ script = "MCA_setup" })
            mwse.log("[mwpluginpatches] Silently initialized Morrowind Comes Alive (MCA) with configured settings.")
        elseif mcaLoaded then
            local partySize = tes3.findGlobal("MCA_MoreEnemies")
            if partySize and partySize.value == 3 then
                partySize.value = config.mcaPartySize
                mwse.log("[mwpluginpatches] Repaired invalid MCA party size in this save.")
            end
        end
    end

    -- 2. Ebonheart Underworks
    if config.euEnabled and config.isEbonheartUnderworksActive() then
        local dd19cfg = tes3.findGlobal("dd19rebirthConfig")
        if dd19cfg and dd19cfg.value ~= 1 then
            dd19cfg.value = 1

            local reb = tes3.findGlobal("dd19rebirth")
            if reb then
                reb.value = config.euRebirth and 1 or 0
            end

            local noThief = tes3.findGlobal("dd19noThief")
            if noThief then
                noThief.value = config.euThiefBranch and 1 or 0
            end

            mwscript.stopScript({ script = "dd19_rebirthConfigScript" })
            mwse.log("[mwpluginpatches] Silently initialized Ebonheart Underworks with configured settings.")
        end
    end
end

-- Intercept any messagebox popups that might slip through before globals are set
local function onMenuMessage(e)
    local msgElem = e.element:findChild(tes3ui.registerID("MenuMessage_message"))
    if not msgElem or not msgElem.text then return end

    local text = msgElem.text:lower()

    -- MCA questionnaire
    if config.mcaEnabled and config.isMcaActive() and (text:find("morrowind comes alive") or text:find("mca")) then
        if text:find("welcome to morrowind comes alive") then
            local btn1 = e.element:findChild(tes3ui.registerID("MenuMessage_button_1"))
            if btn1 then
                btn1:triggerEvent("mouseClick")
                autoStartup.applyStartupConfig()
                return
            end
        end

        local btn0 = e.element:findChild(tes3ui.registerID("MenuMessage_button_0"))
        if btn0 then
            btn0:triggerEvent("mouseClick")
            autoStartup.applyStartupConfig()
            return
        end
    end

    -- Ebonheart Underworks prompts
    if config.euEnabled and config.isEbonheartUnderworksActive() and text:find("ebonheart underworks") then
        if text:find("morrowind rebirth installed") then
            local targetIdx = config.euRebirth and 1 or 0
            local btn = e.element:findChild(tes3ui.registerID("MenuMessage_button_" .. targetIdx))
            if btn then
                btn:triggerEvent("mouseClick")
                autoStartup.applyStartupConfig()
                return
            end
        elseif text:find("thief branch") then
            local targetIdx = config.euThiefBranch and 1 or 0
            local btn = e.element:findChild(tes3ui.registerID("MenuMessage_button_" .. targetIdx))
            if btn then
                btn:triggerEvent("mouseClick")
                autoStartup.applyStartupConfig()
                return
            end
        end
    end
end

-- whether the loaded game still needs the setup this patch does (rule-based, from the mods' own globals)
function autoStartup.pending()
    if config.mcaEnabled and config.isMcaActive() then
        local mcaLoaded = tes3.findGlobal("MCA_Loaded")
        if mcaLoaded and mcaLoaded.value ~= 1 then return true end
        local partySize = tes3.findGlobal("MCA_MoreEnemies")
        if mcaLoaded and partySize and partySize.value == 3 and config.mcaPartySize ~= 3 then return true end
    end
    if config.euEnabled and config.isEbonheartUnderworksActive() then
        local dd19cfg = tes3.findGlobal("dd19rebirthConfig")
        if dd19cfg and dd19cfg.value ~= 1 then return true end
    end
    return false
end

local onMessageArmed, onCellChangedArmed

local function disarm(reason)
    if not armed then return end
    armed = false
    event.unregister(tes3.event.uiActivated, onMessageArmed, { filter = "MenuMessage" })
    event.unregister(tes3.event.cellChanged, onCellChangedArmed)
    if reason then mwse.log("[mwpluginpatches] AutoStartup: %s", reason) end
end

local function checkDone()
    if armed and not autoStartup.pending() then
        intercept.afterDispatch(function()
            if armed and not autoStartup.pending() then disarm("setup done; handlers removed.") end
        end)
    end
end

onMessageArmed = function(e)
    onMenuMessage(e)
    checkDone()
end

onCellChangedArmed = function()
    autoStartup.applyStartupConfig()
    checkDone()
end

local function arm()
    if armed then return end
    armed = true
    event.register(tes3.event.uiActivated, onMessageArmed, { filter = "MenuMessage" })
    event.register(tes3.event.cellChanged, onCellChangedArmed)
end

autoStartup.isArmed = function() return armed end

function autoStartup.init()
    if not config.mcaEnabled and not config.euEnabled then
        return
    end

    event.register(tes3.event.loaded, function()
        autoStartup.applyStartupConfig()
        if not autoStartup.pending() then
            disarm("setup already done in this save; handlers not kept loaded.")
            return
        end
        arm()
        timer.start({
            type = timer.simulate,
            duration = 0.5,
            iterations = 5,
            callback = function()
                autoStartup.applyStartupConfig()
                if armed and not autoStartup.pending() then disarm("setup done; handlers removed.") end
            end,
        })
    end)
    mwse.log("[mwpluginpatches] AutoStartup patch active (MCA: %s, Ebonheart Underworks: %s).",
        config.mcaEnabled and config.isMcaActive() and "enabled" or "disabled",
        config.euEnabled and config.isEbonheartUnderworksActive() and "enabled" or "disabled")
end

return autoStartup
