local this = {}

local function hasReadableText(book)
    if not book or not book.text then return false end
    local clean = book.text:gsub("<[^>]*>", ""):gsub("%s+", "")
    return #clean > 0
end

function this.scanAndClassify(config, force)
    local dh = tes3.dataHandler
    local ndd = dh and dh.nonDynamicData
    if not ndd or not ndd.books then return 0, 0 end

    config.whitelist = config.whitelist or {}
    config.blacklist = config.blacklist or {}

    local countWhite = 0
    local countBlack = 0

    for book in tes3.iterate(tes3.dataHandler.nonDynamicData.books) do
        local id = book.id:lower()
        local name = (book.name or ""):lower()
        local mesh = (book.mesh or ""):lower()
        local isScroll = (book.type == 1) or (book.type == tes3.bookType.scroll)
        local isPaper = isScroll
            or id:find("paper") or id:find("scroll") or id:find("blank") or id:find("ledger") or id:find("template") or id:find("note")
            or name:find("paper") or name:find("scroll") or name:find("blank") or name:find("note")
            or mesh:find("paper") or mesh:find("scroll")
            or not hasReadableText(book)

        if isPaper then
            if force or (config.whitelist[id] == nil and config.blacklist[id] == nil) then
                if hasReadableText(book) then
                    config.blacklist[id] = true
                    config.whitelist[id] = nil
                    countBlack = countBlack + 1
                else
                    config.whitelist[id] = true
                    config.blacklist[id] = nil
                    countWhite = countWhite + 1
                end
            end
        end
    end

    mwse.saveConfig("mwplainpaperfix", config)
    return countWhite, countBlack
end

local function getCandidates(config)
    local candidates = {}
    local seen = {}
    if config.whitelist then
        for id in pairs(config.whitelist) do
            if not seen[id] then
                table.insert(candidates, id)
                seen[id] = true
            end
        end
    end
    if config.blacklist then
        for id in pairs(config.blacklist) do
            if not seen[id] then
                table.insert(candidates, id)
                seen[id] = true
            end
        end
    end
    table.sort(candidates)
    return candidates
end

function this.register(config, defaultConfig)
    local template = mwse.mcm.createTemplate({
        name = "Plain Paper Fix",
        config = config,
        defaultConfig = defaultConfig,
        showDefaultSetting = true,
        onClose = function()
            mwse.saveConfig("mwplainpaperfix", config)
        end,
    })

    -- Page 1: Settings
    local settingsPage = template:createSideBarPage({
        label = "Settings",
        description = [[Plain Paper Fix

Eliminates the reading window popup when picking up plain paper, blank scrolls, and empty documents in the world, picking them directly into your inventory.

• Whitelist: All paper objects without text (blank paper, blank scrolls, templates, blank ledgers across base game, DLCs, Tamriel Data, TR_Mainland, and other landmass mods) are whitelisted for direct inventory pickup.
• Blacklist: All paper objects containing written text (letters, notes, reports) are blacklisted so they open the normal reading window.

Use the "Paper & Scroll Filter" page to interactively move items between the Whitelist and Blacklist.]],
        showReset = true,
    })

    settingsPage:createYesNoButton({
        label = "Enable mod",
        description = "Toggle Plain Paper Fix on or off.",
        configKey = "enabled",
    })

    settingsPage:createButton({
        label = "Re-scan All Plugins for Blank vs Text Paper",
        description = "Scans all loaded plugins and automatically classifies every paper object: unwritten papers go to the Whitelist, written papers go to the Blacklist.",
        buttonText = "Re-scan Now",
        callback = function()
            local w, b = this.scanAndClassify(config, true)
            tes3.messageBox({
                message = string.format("Scan complete!\n• Whitelisted (Blank): %d\n• Blacklisted (Written): %d", w, b),
                buttons = { "OK" }
            })
        end,
    })

    -- Page 2: Whitelist & Blacklist (Exclusions Page)
    template:createExclusionsPage({
        label = "Paper & Scroll Filter",
        description = [[Interactively manage which papers, scrolls, and documents are picked up directly into inventory versus opening the reading window.

• Whitelist (Left - Direct Pickup): Any item here will bypass the reading window and be placed directly into your inventory.
• Blacklist (Right - Read Normally): Any item here will open the normal scroll/book reading menu when activated.

Click on any item in either list to interactively transfer it across. Use the search bar to filter by ID or name.]],
        leftListLabel = "Whitelist (Direct Pickup)",
        rightListLabel = "Blacklist (Read Normally)",
        showAllBlocked = false,
        variable = mwse.mcm.createTableVariable({
            id = "whitelist",
            table = config,
        }),
        filters = {
            {
                label = "All Papers, Scrolls & Documents",
                callback = function()
                    return getCandidates(config)
                end,
            },
        },
    })

    mwse.mcm.register(template)
end

return this
