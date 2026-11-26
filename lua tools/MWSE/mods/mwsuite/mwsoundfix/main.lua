--[[
    mwsoundfix - the MWSE side of mwdialog_check --soundfix.

    --soundfix rewrites the scripts that started a sound only while GetSoundPlaying said it wasn't playing (this
    engine answers 0 for object sounds, so they restarted it every frame) into 'mwdialog_check - MWSoundFix.esp':
    each loop now starts once and keeps a flag (mwsfOn<n>), each one-shot a timer (mwsfT<n>). This helper does the
    two things MWScript can't:
      * on every game load (and a new game) it bumps the MWSF_Epoch global, so each patched script re-arms once:
        nothing it started survives a load;
      * in flag mode, when a reference with a patched script becomes active again (its cell loads), it zeroes that
        script's loop flags, so the loop the engine stopped when the cell unloaded starts again.
    Which scripts and flags: Data Files\MWSE\config\mwsoundfix_data.json, written by --soundfix.
    Idle (nothing registered) when the patch isn't active. It never blocks a sound and saves nothing of its own.
]]

local PATCH = "mwdialog_check - MWSoundFix.esp"
local flagsByScript = {}
local errors = 0
local PAGE_SIZE = 100
-- tes3ui Info labels trim ordinary leading spaces; four UTF-8 NBSPs keep a visible indent, then a bullet
local SOUND_INDENT = "\194\160\194\160\194\160\194\160- "
-- tes3ui font 1 is Century Gothic, distinct from font 0 (Magic Cards) used for body Info text
local HEADER_FONT = 1

local function guarded(fn)
    return function(e)
        local ok, err = pcall(fn, e)
        if not ok then
            errors = errors + 1
            if errors == 1 then mwse.log("[mwsoundfix] error (ignored): %s", tostring(err)) end
        end
    end
end

local function onLoaded()
    local epoch = tes3.findGlobal("MWSF_Epoch")
    if epoch then epoch.value = (epoch.value % 32000) + 1 end
end

local function onReferenceActivated(e)
    local ref = e.reference
    local script = ref and ref.object and ref.object.script
    if not script then return end
    local flags = flagsByScript[script.id:lower()]
    if not flags then return end
    local context = ref.context                  -- nil until the reference's script has run with variables
    if not context then return end
    for _, name in ipairs(flags) do context[name] = 0 end
    ref.modified = true
end

local function start()
    if not tes3.findGlobal("MWSF_Epoch") then
        mwse.log("[mwsoundfix] idle: %s is not active", PATCH)
        return
    end
    local ok, data = pcall(mwse.loadConfig, "mwsoundfix_data")
    local count = 0
    if ok and type(data) == "table" and data.version == 1 and type(data.scripts) == "table" then
        for id, info in pairs(data.scripts) do
            if type(id) == "string" and type(info) == "table" and type(info.loopFlags) == "table" and #info.loopFlags > 0 then
                flagsByScript[id:lower()] = info.loopFlags
                count = count + 1
            end
        end
    else
        mwse.log("[mwsoundfix] mwsoundfix_data.json missing or unreadable: loops re-arm on loads only")
    end
    event.register(tes3.event.loaded, guarded(onLoaded))
    if count > 0 and not (type(data) == "table" and data.loopMode == "restart") then
        event.register(tes3.event.referenceActivated, guarded(onReferenceActivated))
    end
    mwse.log("[mwsoundfix] ready: %d script(s) with loop flags", count)
end

event.register(tes3.event.initialized, start)

-- page the long repaired-script list: 100 script entries at a time (headers do not count), Previous / Next, "Page X of Y"
local function paginate(total, page, size)
    size = size or PAGE_SIZE
    total = tonumber(total) or 0
    if total < 0 then total = 0 end
    local pages = 1
    if total > 0 then pages = math.ceil(total / size) end
    page = math.floor(tonumber(page) or 1)
    if page < 1 then page = 1 end
    if page > pages then page = pages end
    local first, last = 0, 0
    if total > 0 then
        first = (page - 1) * size + 1
        last = math.min(total, page * size)
    end
    return {
        page = page,
        pages = pages,
        first = first,
        last = last,
        total = total,
        hasPrev = page > 1,
        hasNext = page < pages,
        label = string.format("Page %d of %d", page, pages),
    }
end

local function collectEntries(data)
    local byPlugin, plugins, entries = {}, {}, {}
    for id, info in pairs(data.scripts) do
        local owner = type(info) == "table" and info.owner or "?"
        if not byPlugin[owner] then byPlugin[owner] = {}; plugins[#plugins + 1] = owner end
        local repairs = type(info) == "table" and type(info.repairs) == "table" and table.concat(info.repairs, "; ") or ""
        table.insert(byPlugin[owner], id .. (repairs ~= "" and ("  -  " .. repairs) or ""))
    end
    table.sort(plugins, function(a, b) return a:lower() < b:lower() end)
    for _, owner in ipairs(plugins) do
        table.sort(byPlugin[owner])
        for _, line in ipairs(byPlugin[owner]) do
            entries[#entries + 1] = { owner = owner, line = line }
        end
    end
    return entries, plugins
end

local function pluginCounts(entries)
    local n = {}
    for _, e in ipairs(entries) do
        n[e.owner] = (n[e.owner] or 0) + 1
    end
    return n
end

-- one group per plugin visible on this page; headers do not count toward PAGE_SIZE
-- a plugin that started on an earlier page repeats its title as "Name (cont.)"
local function pageGroups(entries, nav)
    local groups, counts = {}, pluginCounts(entries)
    if nav.total == 0 or nav.first == 0 then return groups end
    local current
    for i = nav.first, nav.last do
        local e = entries[i]
        if not current or current.owner ~= e.owner then
            local continued = i > 1 and entries[i - 1].owner == e.owner
            current = {
                owner = e.owner,
                continued = continued and true or false,
                title = continued and (e.owner .. " (cont.)")
                    or string.format("%s (%d)", e.owner, counts[e.owner] or 0),
                lines = {},
            }
            groups[#groups + 1] = current
        end
        current.lines[#current.lines + 1] = SOUND_INDENT .. e.line
    end
    return groups
end

local function formatPageText(entries, nav)
    local groups = pageGroups(entries, nav)
    local parts = {}
    for i, g in ipairs(groups) do
        if i > 1 then parts[#parts + 1] = "" end
        parts[#parts + 1] = g.title
        for _, line in ipairs(g.lines) do
            parts[#parts + 1] = line
        end
    end
    return table.concat(parts, "\n")
end

local function setInfoText(comp, text)
    if not comp then return end
    comp.text = text
    local el = comp.elements and comp.elements.info
    if el then
        el.text = text
        pcall(function()
            local menu = el.getTopLevelMenu and el:getTopLevelMenu()
            if menu and menu.updateLayout then menu:updateLayout() end
        end)
    end
end

local function setButtonOn(btn, on)
    if not btn then return end
    if on then
        pcall(function() if btn.enable then btn:enable() end end)
    else
        pcall(function() if btn.disable then btn:disable() end end)
    end
end

local function styleHeader(self)
    local label = self.elements and self.elements.label
    if not label then return end
    pcall(function()
        -- Category:enable already uses headerColor; set it again after a rebuild, and use font 1
        if tes3ui and tes3ui.getPalette then
            local pal = tes3.palette and tes3.palette.headerColor or "header_color"
            label.color = tes3ui.getPalette(pal)
        end
        label.font = HEADER_FONT
    end)
end

local function styleSoundList(self)
    local el = self.elements and self.elements.info
    if not el then return end
    -- Info labels may still collapse leading spaces: keep a left border as well as the NBSP indent in the text
    el.borderLeft = 16
    el.wrapText = true
end

local function destroyChildren(box)
    if not (box and box.children) then return end
    for i = #box.children, 1, -1 do
        local child = box.children[i]
        if child and child.destroy then pcall(function() child:destroy() end) end
    end
end

-- a read-only MCM page: the scripts the patch repaired, by plugin (nothing to set)
-- Plugin names are MCM Category headers again (headerColor + font 1), as they were before paging,
-- so they stay distinct from the body Info used for the sound/script lines.
local function registerMcm()
    local template = mwse.mcm.createTemplate({ name = "mwsoundfix" })
    local page = template:createPage({ label = "Repaired sound scripts" })
    local ok, data = pcall(mwse.loadConfig, "mwsoundfix_data")
    if not (ok and type(data) == "table" and type(data.scripts) == "table") then
        page:createInfo({ text = "No sound scripts are repaired yet. mwdialog_check --soundfix (or --fix) builds "
            .. PATCH .. ", and this page lists what it repaired." })
        template:register()
        return
    end
    local entries, plugins = collectEntries(data)
    local total = #entries
    local currentPage = 1
    local pageInfo, prevBtn, nextBtn, listHost

    local function nav()
        return paginate(total, currentPage, PAGE_SIZE)
    end

    local function apply()
        local n = nav()
        currentPage = n.page
        setInfoText(pageInfo, n.label)
        setButtonOn(prevBtn, n.hasPrev)
        setButtonOn(nextBtn, n.hasNext)
        if not listHost then return end
        local box = listHost.elements and listHost.elements.subcomponentsContainer
        destroyChildren(box)
        listHost.components = {}
        local groups = pageGroups(entries, n)
        for i, g in ipairs(groups) do
            local cat = listHost:createCategory({
                label = g.title,
                postCreate = styleHeader,
            })
            local text = table.concat(g.lines, "\n")
            if i < #groups then text = text .. "\n" end   -- blank line before the next mod header, not after the last
            cat:createInfo({ text = text, postCreate = styleSoundList })
            if box then pcall(function() cat:create(box) end) end
        end
        pcall(function()
            local root = box or (listHost.elements and listHost.elements.outerContainer)
            local menu = root and root.getTopLevelMenu and root:getTopLevelMenu()
            if menu and menu.updateLayout then menu:updateLayout() end
        end)
    end

    page:createInfo({ text = string.format("%d script(s) in %d plugin(s), built %s. These scripts used to restart "
        .. "their sound every frame; %s keeps their own state instead. %s", total, #plugins, tostring(data.built or "?"),
        PATCH, tes3.findGlobal("MWSF_Epoch") and "The patch is active." or "The patch is NOT active in this game.") })
    pageInfo = page:createInfo({ text = nav().label })
    prevBtn = page:createButton({
        buttonText = "Previous",
        description = "Show the previous 100 repaired scripts. Disabled on the first page.",
        callback = function()
            if currentPage > 1 then currentPage = currentPage - 1; apply() end
        end,
    })
    nextBtn = page:createButton({
        buttonText = "Next",
        description = "Show the next 100 repaired scripts. Disabled on the last page.",
        callback = function()
            local n = nav()
            if currentPage < n.pages then currentPage = currentPage + 1; apply() end
        end,
    })
    -- unlabeled host: each visible plugin is a Category (header font/color) with the sound lines under it
    listHost = page:createCategory({
        postCreate = function() apply() end,
    })
    apply()
    template:register()
end

event.register(tes3.event.modConfigReady, registerMcm)

return {
    onLoaded = onLoaded,
    onReferenceActivated = onReferenceActivated,
    flagsByScript = flagsByScript,
    PAGE_SIZE = PAGE_SIZE,
    HEADER_FONT = HEADER_FONT,
    SOUND_INDENT = SOUND_INDENT,
    paginate = paginate,
    collectEntries = collectEntries,
    pageGroups = pageGroups,
    formatPageText = formatPageText,
}
