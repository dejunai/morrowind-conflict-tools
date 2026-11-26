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

-- page the long repaired-script list: 100 entries at a time, Previous / Next, "Page X of Y"
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

local function formatPageText(entries, nav)
    if nav.total == 0 or nav.first == 0 then return "" end
    local parts, current, count, buf = {}, nil, 0, nil
    local function flush()
        if current then
            parts[#parts + 1] = string.format("%s (%d)", current, count)
            parts[#parts + 1] = table.concat(buf, "\n")
        end
    end
    for i = nav.first, nav.last do
        local e = entries[i]
        if current ~= e.owner then
            flush()
            current, count, buf = e.owner, 0, {}
        end
        count = count + 1
        buf[#buf + 1] = e.line
    end
    flush()
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

-- a read-only MCM page: the scripts the patch repaired, by plugin (nothing to set)
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
    local pageInfo, listInfo, prevBtn, nextBtn

    local function nav()
        return paginate(total, currentPage, PAGE_SIZE)
    end

    local function apply()
        local n = nav()
        currentPage = n.page
        setInfoText(pageInfo, n.label)
        setInfoText(listInfo, formatPageText(entries, n))
        setButtonOn(prevBtn, n.hasPrev)
        setButtonOn(nextBtn, n.hasNext)
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
        postCreate = function() apply() end,
    })
    nextBtn = page:createButton({
        buttonText = "Next",
        description = "Show the next 100 repaired scripts. Disabled on the last page.",
        callback = function()
            local n = nav()
            if currentPage < n.pages then currentPage = currentPage + 1; apply() end
        end,
        postCreate = function() apply() end,
    })
    listInfo = page:createInfo({ text = formatPageText(entries, nav()) })
    apply()
    template:register()
end

event.register(tes3.event.modConfigReady, registerMcm)

return {
    onLoaded = onLoaded,
    onReferenceActivated = onReferenceActivated,
    flagsByScript = flagsByScript,
    PAGE_SIZE = PAGE_SIZE,
    paginate = paginate,
    collectEntries = collectEntries,
    formatPageText = formatPageText,
}
