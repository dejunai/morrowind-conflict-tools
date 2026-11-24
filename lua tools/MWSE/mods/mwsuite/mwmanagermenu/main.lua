--[[
    mwmanagermenu - one Mod Config Menu entry for the mw* suite.

    Each suite mod registers its own settings page, exactly as it does on its own. This mod loads before them
    and catches those registrations: instead of an entry per suite mod in the Mod Config Menu's list there is one,
    "MW Conflict Tools", with a tab for each suite mod. A tab shows that mod's own page, built by that mod's own code,
    and its settings are saved by that mod's own save, so nothing about the suite mods is changed or copied.

    Without this mod (or with a suite mod it does not know) every mod simply has its own entry again.
]]

local NAME = "MW Conflict Tools"
local PER_ROW = 4

-- the suite, in tab order (tests/test_unified_menu.py checks this against reference/mwse-lua-guards/mods)
local SUITE = {
    "mwsaveguard", "mwteleportguard", "mwmouseguard", "mwwarnsuppression", "mwpersonaleffects",
    "mweffectinspector", "mwpluginpatches", "mwfloatfix", "mwcollide", "mwstranded",
    "mwperformers", "mwinfoloop", "mwsoundguard", "mwhangwatch", "mwguard",
    "mwexitguard", "mwquicktoggle", "mwcustomclasspersistence",
    "mwcriminal", "mwcompanions",
}
local isSuite = {}
for _, mod in ipairs(SUITE) do isSuite[mod] = true end

local captured = {}             -- suite mod folder -> the settings package it registered

-- the MWSE\mods folder of the Lua file that is registering a settings page
local function registeringMod()
    for level = 2, 12 do
        local info = debug.getinfo(level, "S")
        if not info then return nil end
        local src = (info.source or ""):lower():gsub("/", "\\")
        local mod = src:match("\\mwse\\mods\\mwsuite\\([^\\]+)\\")
            or src:match("^@?mwse\\mods\\mwsuite\\([^\\]+)\\")
            or src:match("\\mwse\\mods\\([^\\]+)\\") or src:match("^@?mwse\\mods\\([^\\]+)\\")
        if mod and mod ~= "mwmanagermenu" then return mod end
    end
end

local register = mwse.registerModConfig
function mwse.registerModConfig(name, package)
    local mod = registeringMod()
    if mod and isSuite[mod] and type(package) == "table" and not captured[mod] then
        package.name = name
        captured[mod] = package
        return
    end
    return register(name, package)
end

-- the one entry -----------------------------------------------------------------------------------
local shown                     -- the suite mod whose page is on screen
local root                      -- the menu's container for this entry

local function closeShown(container)
    local package = shown and captured[shown]
    if package and package.onClose then
        local ok, err = pcall(package.onClose, container)   -- that mod saves its settings
        if not ok then mwse.log("[mwmanagermenu] %s's settings save failed: %s", tostring(shown), tostring(err)) end
    end
end

local build
local function show(mod)
    if mod == shown then return end
    closeShown(root)
    shown = mod
    build()
end

build = function()
    root:destroyChildren()
    local row
    local count = 0
    for _, mod in ipairs(SUITE) do
        local package = captured[mod]
        if package then
            if count % PER_ROW == 0 then
                row = root:createBlock({})
                row.flowDirection = "left_to_right"
                row.widthProportional = 1.0
                row.autoHeight = true
            end
            count = count + 1
            local button = row:createButton({ text = package.name or mod })
            if mod == shown then button.widget.state = 4 end             -- tes3.uiState.active: the open tab
            button:register("help", function()
                local tooltip = tes3ui.createTooltipMenu()
                tooltip:createLabel({ text = "Open settings for " .. (package.name or mod) .. "." })
                tooltip:updateLayout()
            end)
            button:register("mouseClick", function() show(mod) end)
        end
    end
    local body = root:createBlock({})
    body.flowDirection = "top_to_bottom"
    body.widthProportional = 1.0
    body.heightProportional = 1.0
    local package = captured[shown]
    if package and package.onCreate then
        local ok, err = pcall(package.onCreate, body)
        if not ok then mwse.log("[mwmanagermenu] %s's settings page failed: %s", tostring(shown), tostring(err)) end
    end
    local top = root.getTopLevelMenu and root:getTopLevelMenu()
    if top then top:updateLayout() end
end

local combined = {
    onCreate = function(container)
        root = container
        if not (shown and captured[shown]) then
            shown = nil
            for _, mod in ipairs(SUITE) do
                if captured[mod] then shown = mod break end
            end
        end
        build()
    end,
    onClose = function(container)
        closeShown(container)
        root = nil
    end,
    onSearch = function(text)
        for _, package in pairs(captured) do
            if package.onSearch then
                local ok, hit = pcall(package.onSearch, text)
                if ok and hit then return true end
            end
        end
        return false
    end,
}

-- after every suite mod has registered (they do it on this same event, at the default priority)
event.register("modConfigReady", function()
    if next(captured) then
        local aggregate = { name = NAME, pages = {} }
        for _, mod in ipairs(SUITE) do
            local template = captured[mod] and captured[mod].template
            if template then
                for _, page in ipairs(template.pages) do
                    aggregate.pages[#aggregate.pages + 1] = page
                end
            end
        end
        aggregate.onClose = function(container)
            for _, mod in ipairs(SUITE) do
                local template = captured[mod] and captured[mod].template
                if template and template.onClose then
                    local ok, err = pcall(template.onClose, container)
                    if not ok then mwse.log("[mwmanagermenu] %s's keybind save failed: %s", mod, tostring(err)) end
                end
            end
        end
        combined.template = aggregate
        register(NAME, combined)
        mwse.log("[mwmanagermenu] %d suite mod(s) under one Mod Config Menu entry: %s", table.size(captured), NAME)
    end
end, { priority = -1000 })

return { captured = captured, combined = combined, suite = SUITE }
