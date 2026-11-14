local visuals = {}

local function safeApply(name, fn)
    local ok, err = pcall(fn)
    if not ok then
        mwse.log("[ESP Replacements] Warning applying %s: %s", name, tostring(err))
    end
end

function visuals.apply(config)
    if not config.enabled then return end

    -- 1. Streetlight Color Fix (replaces LightFix.ESP)
    if config.streetlightColorFix then
        safeApply("Streetlight Fix", function()
            local light = tes3.getObject("light_de_streetlight_01_223")
            if light and light.objectType == tes3.objectType.light then
                light.radius = 223
                if light.color then
                    light.color[1] = 245
                    light.color[2] = 140
                    light.color[3] = 40
                    light.color[4] = 255
                end
            end
        end)
    end

    -- 2. Dwemer Red Bulb Fix (replaces TIDR - Red Lights TR.ESP)
    if config.tidrRedBulbs then
        safeApply("Dwemer Red Bulb Fix", function()
            local bulb = tes3.getObject("light_dwe_bulb00")
            if bulb and bulb.objectType == tes3.objectType.light then
                bulb.radius = 600
                if bulb.color then
                    bulb.color[1] = 255
                    bulb.color[2] = 164
                    bulb.color[3] = 164
                    bulb.color[4] = 255
                end
            end
        end)
    end

    -- 3. Body Parts First Person Hands Fix (replaces Body Parts Fixes.ESP)
    if config.bodyPartsFirstPersonHands then
        safeApply("Body Parts Hand Fixes", function()
            local bodyParts = {
                { id = "b_n_high elf_m_upper leg", mesh = "b\\b_n_high elf_m_upper leg.nif" },
                { id = "b_n_dark elf_m_hand.1st", mesh = "b\\b_n_dark elf_m_hands.1st.nif" },
                { id = "b_n_imperial_f_hands.1st", mesh = "b\\b_n_imperial_f_hands.1st.nif" },
                { id = "b_n_nord_m_hands.1st", mesh = "b\\b_n_nord_m_hands.1st.nif" },
                { id = "b_n_redguard_m_hands.1st", mesh = "b\\b_n_redguard_m_hands.1st.nif" },
            }
            for _, bp in ipairs(bodyParts) do
                local part = tes3.getObject(bp.id)
                if part and part.objectType == tes3.objectType.bodyPart then
                    part.mesh = bp.mesh
                end
            end
        end)
    end
end

return visuals
