local equipment = {}

local function safeApply(name, fn)
    local ok, err = pcall(fn)
    if not ok then
        mwse.log("[ESP Replacements] Warning applying %s: %s", name, tostring(err))
    end
end

function equipment.apply(config)
    if not config.enabled then return end

    -- 1. Adamantium Axe Stats (speed, weight, damages, enchant capacity)
    if config.adamantiumAxe1H then
        safeApply("Adamantium Axe", function()
            local axe = tes3.getObject("adamantium_axe")
            if axe and axe.objectType == tes3.objectType.weapon then
                -- Note: weapon.type is read-only in MWSE sol bindings; safely attempt if exposed
                pcall(function() axe.type = tes3.weaponType.axeOneHand end)
                axe.speed = 1.25
                axe.weight = 35.0
                axe.chopMin = 1
                axe.chopMax = 30
                axe.slashMin = 1
                axe.slashMax = 25
                axe.thrustMin = 1
                axe.thrustMax = 6
                axe.enchantCapacity = 100
            end
        end)
    end

    -- 2. Aesliip's Ring Fortify Magicka (replaces Aeslip's Ring Fortify Maximum Magicka.ESP)
    if config.aesliipRingMagicka then
        safeApply("Aesliip's Ring", function()
            local ench = tes3.getObject("bm_aesliip")
            if ench and ench.objectType == tes3.objectType.enchantment then
                local eff = ench.effects[2]
                if eff then
                    eff.id = tes3.effect.fortifyMaximumMagicka
                    eff.rangeType = tes3.effectRange.self
                    eff.min = 5
                    eff.max = 5
                    eff.duration = 1
                    eff.radius = 0
                end
            end
        end)
    end

    -- 3. Foeburner Cast On Strike Fix (replaces MWFoeburner Fix.ESP)
    if config.foeburnerCastOnStrike then
        safeApply("Foeburner Fix", function()
            local ench = tes3.getObject("foeburner_en")
            if not ench then
                ench = tes3.createObject({
                    objectType = tes3.objectType.enchantment,
                    id = "foeburner_en",
                    castType = tes3.enchantmentType.onStrike,
                    chargeCost = 12,
                    maxCharge = 120,
                })
            end
            if ench then
                ench.castType = tes3.enchantmentType.onStrike
                ench.chargeCost = 12
                ench.maxCharge = 120
                local eff = ench.effects[1]
                if eff then
                    eff.id = tes3.effect.fireDamage
                    eff.rangeType = tes3.effectRange.target
                    eff.min = 15
                    eff.max = 50
                    eff.duration = 0
                    eff.radius = 0
                end
                local weap = tes3.getObject("foeburner")
                if weap and weap.objectType == tes3.objectType.weapon then
                    weap.enchantment = ench
                end
            end
        end)
    end

    -- 4. Cutting Room Floor - Umbra Sword Restoration (replaces Cutting Room Floor - Umbra.esp)
    if config.crfUmbraRestoration then
        safeApply("CRF Umbra Restoration", function()
            for _, id in ipairs({ "longsword_umbra_unique", "longsword_umbra_unique_x" }) do
                local w = tes3.getObject(id)
                if w and w.objectType == tes3.objectType.weapon then
                    w.reach = 1.0
                    w.speed = 1.35
                    w.chopMin = 10
                    w.chopMax = 50
                    w.slashMin = 10
                    w.slashMax = 45
                    w.thrustMin = 10
                    w.thrustMax = 40
                    w.weight = 40.0
                    w.value = 110000
                    w.maxCondition = 6500
                    w.enchantCapacity = 2500
                end
            end
        end)
    end

    -- 5. Protective Masks Redux (replaces Protective Masks Redux.ESP)
    if config.protectiveMasks then
        safeApply("Protective Masks", function()
            local ench = tes3.getObject("protective_masks")
            if not ench then
                ench = tes3.createObject({
                    objectType = tes3.objectType.enchantment,
                    id = "protective_masks",
                    castType = tes3.enchantmentType.constant,
                    chargeCost = 0,
                    maxCharge = 0,
                })
            end
            if ench then
                ench.castType = tes3.enchantmentType.constant
                -- Effect 1: Resist Blight Disease (95)
                local eff1 = ench.effects[1]
                if eff1 then
                    eff1.id = tes3.effect.resistBlightDisease
                    eff1.rangeType = tes3.effectRange.self
                    eff1.min = 10
                    eff1.max = 10
                    eff1.duration = 1
                    eff1.radius = 0
                end
                -- Effect 2: Resist Common Disease (94)
                local eff2 = ench.effects[2]
                if eff2 then
                    eff2.id = tes3.effect.resistCommonDisease
                    eff2.rangeType = tes3.effectRange.self
                    eff2.min = 10
                    eff2.max = 10
                    eff2.duration = 1
                    eff2.radius = 0
                end
                -- Effect 3: Resist Corprus Disease (97)
                local eff3 = ench.effects[3]
                if eff3 then
                    eff3.id = tes3.effect.resistCorprusDisease
                    eff3.rangeType = tes3.effectRange.self
                    eff3.min = 10
                    eff3.max = 10
                    eff3.duration = 1
                    eff3.radius = 0
                end

                local helms = { "chitin helm", "netch_leather_boiled_helm", "dust_adept_helm", "chitin_mask_helm" }
                for _, hid in ipairs(helms) do
                    local helm = tes3.getObject(hid)
                    if helm and helm.objectType == tes3.objectType.armor then
                        helm.enchantment = ench
                    end
                end
            end
        end)
    end

    -- 6. Sheogorath's Signet Unique Visuals (replaces DM_SheoSignet.ESP)
    if config.sheogorathSignetVisuals then
        safeApply("Sheogorath's Signet", function()
            local ring = tes3.getObject("Sheogorath's Signet Ring")
            if ring and ring.objectType == tes3.objectType.clothing then
                ring.mesh = "dmar\\obl\\DM_SheoSignetUni.nif"
                ring.icon = "DMAR\\DM_SheoSignet.dds"
            end
        end)
    end

    -- 7. Psy Iron Mesh Improvement Unique Weapons (replaces Psy_IronMeshImprove_Uniques_BME.esp)
    if config.psyIronUniqueVisuals then
        safeApply("Psy Iron Uniques", function()
            local uniques = {
                { id = "we_temreki", mesh = "psy\\Psy_W_Temreki.nif", icon = "psy\\Tx_Temreki.dds" },
                { id = "banhammer_unique", mesh = "psy\\w_Banhammer_iron.nif", icon = "psy\\Tx_Banhammer_iron.dds" },
                { id = "lightofday_unique", mesh = "psy\\Psy_W_LoD_Mace_Ebony.nif", icon = "psy\\Tx_LoD_Mace_Ebony.dds" },
                { id = "bm_saber_seasplitter", mesh = "psy\\Psy_W_SeaSplitter.nif", icon = "psy\\Tx_SeaSplitter_Saber.dds" },
            }
            for _, u in ipairs(uniques) do
                local item = tes3.getObject(u.id)
                if item and item.objectType == tes3.objectType.weapon then
                    item.mesh = u.mesh
                    item.icon = u.icon
                end
            end
        end)
    end

    -- 8. Eltonbrand Unique Visuals (replaces Eltonbrand Replacer.ESP)
    if config.eltonbrandVisuals then
        safeApply("Eltonbrand Replacer", function()
            local elton = tes3.getObject("katana_bluebrand_unique")
            if elton and elton.objectType == tes3.objectType.weapon then
                elton.mesh = "TM\\eltonbrand.nif"
                elton.icon = "TM\\eltonbrand.dds"
            end
        end)
    end

    -- 9. Colovian Fur Helm Entertainer & BTBGI Stats (replaces Entertainers Expanded - BTBGI.esp)
    if config.colovianFurHelmEntertainer then
        safeApply("Colovian Fur Helm", function()
            local helm = tes3.getObject("fur_colovian_helm")
            if helm and helm.objectType == tes3.objectType.armor then
                helm.weight = 1.0
                helm.value = 25
                helm.maxCondition = 70
                helm.armorRating = 5
                local s = tes3.getScript("hatScript")
                if s then
                    helm.script = s
                end
            end
        end)
    end

    -- 10. Party Alchemy Item Registration (replaces mwse_PartyAlchemy.esp)
    if config.partyAlchemyItem then
        safeApply("Party Alchemy Item", function()
            local flask = tes3.getObject("misc_pa_flask")
            if not flask then
                tes3.createObject({
                    objectType = tes3.objectType.miscItem,
                    id = "misc_pa_flask",
                    name = "*Administer Potion",
                    mesh = "m\\Misc_flask_01.NIF",
                    icon = "k\\magic_alchemy.dds",
                    weight = 1.0,
                    value = 15,
                })
            end
        end)
    end
end

return equipment
