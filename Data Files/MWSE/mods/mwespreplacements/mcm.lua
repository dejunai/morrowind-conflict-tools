local config = require("mwespreplacements.config")

local function registerModConfig()
    local template = mwse.mcm.createTemplate{ name = "ESP Replacements" }
    template.onClose = function() config.save() end   -- not saveOnClose: config holds functions
    template:register()

    -- Page 1: Equipment & Items
    local equipPage = template:createSideBarPage{ label = "Equipment & Items" }
    equipPage.description = "ESP Replacements: Equipment & Items\n\nThese options replace standalone equipment and weapon tweak ESP plugins with pure MWSE-Lua data modifications applied at startup."

    equipPage:createOnOffButton{
        label = "Master Toggle: Enable All Replacements",
        description = "Global toggle for all ESP replacement tweaks in this mod.",
        variable = mwse.mcm.createTableVariable{ id = "enabled", table = config },
    }

    local equipCategory = equipPage:createCategory{ label = "Equipment & Weapon Tweaks" }

    equipCategory:createOnOffButton{
        label = "Adamantium Axe Stats",
        description = "Replaces stats from 'Adamantium Axe 1H.ESP'.\n\nApplies speed 1.25, weight 35, enchant capacity 100, chop 1-30, slash 1-25.",
        variable = mwse.mcm.createTableVariable{ id = "adamantiumAxe1H", table = config },
    }

    equipCategory:createOnOffButton{
        label = "Aesliip's Ring Magicka Multiplier Fix",
        description = "Replaces 'Aeslip\'s Ring Fortify Maximum Magicka.ESP'.\n\nRestores the intended Fortify Maximum Magicka 0.5x INT constant effect to Aesliip's Ring from Bloodmoon.",
        variable = mwse.mcm.createTableVariable{ id = "aesliipRingMagicka", table = config },
    }

    equipCategory:createOnOffButton{
        label = "Foeburner Cast On Strike Fix",
        description = "Replaces 'MWFoeburner Fix.ESP'.\n\nFixes Foeburner's enchantment so it deals 15-50 points of Fire Damage on strike (12 cost, 120 charge).",
        variable = mwse.mcm.createTableVariable{ id = "foeburnerCastOnStrike", table = config },
    }

    equipCategory:createOnOffButton{
        label = "Cutting Room Floor - Umbra Sword Restoration",
        description = "Replaces 'Cutting Room Floor - Umbra.esp'.\n\nRestores original cut stats for Umbra Sword (reach 1.0, speed 1.35, damage 10-50, value 110000, condition 6500, enchant capacity 2500).",
        variable = mwse.mcm.createTableVariable{ id = "crfUmbraRestoration", table = config },
    }

    equipCategory:createOnOffButton{
        label = "Protective Ash Masks (Disease & Blight Resistance)",
        description = "Replaces 'Protective Masks Redux.ESP'.\n\nAdds constant effect 10% resistance to Blight, Common Disease, and Corprus to Chitin, Boiled Netch, and Telvanni Dust Adept helmets.",
        variable = mwse.mcm.createTableVariable{ id = "protectiveMasks", table = config },
    }

    equipCategory:createOnOffButton{
        label = "Sheogorath's Signet Ring Unique Visuals",
        description = "Replaces 'DM_SheoSignet.ESP'.\n\nGives Sheogorath's Signet Ring its custom Oblivion-style model and inventory icon.",
        variable = mwse.mcm.createTableVariable{ id = "sheogorathSignetVisuals", table = config },
    }

    equipCategory:createOnOffButton{
        label = "Psy Iron Mesh Improvement Uniques",
        description = "Replaces 'Psy_IronMeshImprove_Uniques_BME.esp'.\n\nGives unique visual models and inventory icons to Temreki, Banhammer, Light of Day, and Seasplitter.",
        variable = mwse.mcm.createTableVariable{ id = "psyIronUniqueVisuals", table = config },
    }

    equipCategory:createOnOffButton{
        label = "Eltonbrand Unique Visuals",
        description = "Replaces 'Eltonbrand Replacer.ESP'.\n\nGives the secret katana Eltonbrand its unique sword model and inventory icon.",
        variable = mwse.mcm.createTableVariable{ id = "eltonbrandVisuals", table = config },
    }

    equipCategory:createOnOffButton{
        label = "Colovian Fur Helm Entertainer & Stats",
        description = "Replaces 'Entertainers Expanded - BTBGI.esp'.\n\nAttaches hatScript to Colovian Fur Helm for the Entertainer comedy act and applies balanced stats (weight 1, value 25, condition 70, AR 5).",
        variable = mwse.mcm.createTableVariable{ id = "colovianFurHelmEntertainer", table = config },
    }

    equipCategory:createOnOffButton{
        label = "Party Alchemy Item Registration",
        description = "Replaces 'mwse_PartyAlchemy.esp'.\n\nDynamically creates the misc_pa_flask (*Administer Potion) item for Party Alchemy in memory, rendering the dummy plugin unnecessary.",
        variable = mwse.mcm.createTableVariable{ id = "partyAlchemyItem", table = config },
    }

    -- Page 2: Lighting & Visuals
    local visualPage = template:createSideBarPage{ label = "Lighting & Visuals" }
    visualPage.description = "ESP Replacements: Lighting & Visuals\n\nReplaces mesh and lighting fix plugins."

    local visualCategory = visualPage:createCategory{ label = "Lighting & Body Meshes" }

    visualCategory:createOnOffButton{
        label = "Streetlight Radius & Color Fix",
        description = "Replaces 'LightFix.ESP'.\n\nAdjusts light_de_streetlight_01_223 to radius 223 and warm amber color (245, 140, 40).",
        variable = mwse.mcm.createTableVariable{ id = "streetlightColorFix", table = config },
    }

    visualCategory:createOnOffButton{
        label = "Dwemer Red Bulb Light Fix",
        description = "Replaces 'TIDR - Red Lights TR.ESP'.\n\nAdjusts Dwemer light bulb light_dwe_bulb00 to radius 600 and red glow (255, 164, 164).",
        variable = mwse.mcm.createTableVariable{ id = "tidrRedBulbs", table = config },
    }

    visualCategory:createOnOffButton{
        label = "First-Person Hand Models Fix",
        description = "Replaces 'Body Parts Fixes.ESP'.\n\nFixes first-person hand meshes and upper leg models for Dunmer, High Elf, Imperial, Nord, and Redguard.",
        variable = mwse.mcm.createTableVariable{ id = "bodyPartsFirstPersonHands", table = config },
    }

    -- Page 3: Scripts & Quest Fixes
    local scriptPage = template:createSideBarPage{ label = "Scripts & Quests" }
    scriptPage.description = "ESP Replacements: Script & Quest Bug Fixes\n\nReplaces script-fix plugins with lightweight native MWSE event hooks. Zero savegame pollution, zero plugin slots used."

    local scriptCategory = scriptPage:createCategory{ label = "Lua Script Bug Fixes" }

    scriptCategory:createOnOffButton{
        label = "Stolen Goldbrand Eltonbrand Fix",
        description = "Replaces 'Stolen Goldbrand Eltonbrand Fix.ESP'.\n\nUses an in-engine simulation hook so the Eltonbrand easter egg upgrade also recognizes stolen Goldbrand (katana_goldbrand_unique_x).",
        variable = mwse.mcm.createTableVariable{ id = "stolenGoldbrandEltonbrandFix", table = config },
    }

    scriptCategory:createOnOffButton{
        label = "Sotha Sil Expanded Farmer Note Fix",
        description = "Replaces 'Sotha Sil Expanded - Script Fix.esp'.\n\nAdvances journal Sotha_farmer1 to index 20 upon reading or taking the farmer note.",
        variable = mwse.mcm.createTableVariable{ id = "sothaSilExpandedNoteFix", table = config },
    }

    scriptCategory:createOnOffButton{
        label = "DA Sobitur Level 40 Sleep Check Fix",
        description = "Replaces 'DA_Sobitur_Quest_Part_1 Clean - Script Fix.esp'.\n\nUses a sleep hook to properly deliver Aryon's note upon resting at level 40+.",
        variable = mwse.mcm.createTableVariable{ id = "sobiturLevel40CheckFix", table = config },
    }
end

event.register(tes3.event.modConfigReady, registerModConfig)
