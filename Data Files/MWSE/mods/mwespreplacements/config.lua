local configPath = "esp_replacements"

local defaultConfig = {
    enabled = true,

    -- Equipment & Item Tweaks
    adamantiumAxe1H = true,
    aesliipRingMagicka = true,
    foeburnerCastOnStrike = true,
    crfUmbraRestoration = true,
    protectiveMasks = true,
    sheogorathSignetVisuals = true,
    psyIronUniqueVisuals = true,
    eltonbrandVisuals = true,
    colovianFurHelmEntertainer = true,
    partyAlchemyItem = true,

    -- Lighting & Visual Fixes
    streetlightColorFix = true,
    tidrRedBulbs = true,
    bodyPartsFirstPersonHands = true,

    -- Pure Lua Script Fixes
    stolenGoldbrandEltonbrandFix = true,
    sothaSilExpandedNoteFix = true,
    sobiturLevel40CheckFix = true,
}

local config = mwse.loadConfig(configPath, defaultConfig)

function config.save()
    local plain = {}                    -- the functions on this table cannot go into JSON
    for k, v in pairs(config) do
        if type(v) ~= "function" then plain[k] = v end
    end
    mwse.saveConfig(configPath, plain)
end

function config.resetToDefaults()
    for k, v in pairs(defaultConfig) do
        config[k] = v
    end
    config.save()
end

return config
