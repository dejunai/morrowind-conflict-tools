--[[
    mwcollide - doubled objects, hidden as cells load (interiors and exteriors)

    mwdialog_check --cell-conflicts writes MWSE\config\mwcollide_data.json: for each interior, the objects
    two plugins that don't know about each other both put in the same spot (the same object or the same
    model, within 64 units), leaving out pairs a patch covers, people and creatures. The copy from the
    plugin that loads earlier is listed; the later one stays.

    As each cell loads (exterior cells are listed as "#x,y"), the listed copies are hidden (disabled, never deleted). Change your mods, run
    --cell-conflicts (or --full) again, and the next visit follows the new list: anything no longer
    listed is shown again. The Mod Config menu turns it off (everything shows again) or re-applies it to
    where you are. What it does goes to Data Files\MWSE\logs\mwcollide.log.
]]

local CONFIG_NAME = "mwcollide"
local config = mwse.loadConfig(CONFIG_NAME, { enabled = false, log = true })

local LOG_DIR = "Data Files\\MWSE\\logs"
local logFile
local function log(fmt, ...)
    if not config.log then return end
    if not logFile then
        pcall(function() lfs.mkdir(LOG_DIR) end)
        logFile = io.open(LOG_DIR .. "\\mwcollide.log", "w")
        if not logFile then return end
        logFile:write(os.date("mwcollide log, started %Y-%m-%d %H:%M:%S"), "\n")
    end
    local ok, line = pcall(string.format, fmt, ...)
    logFile:write(os.date("[%H:%M:%S] "), ok and line or tostring(fmt), "\n")
    logFile:flush()
end

-- the list from mwdialog_check: cell -> { byKey = { "id|x|y|z" = entry }, ids = { id = true } } -------
-- (reviewed: ids lets a cell's references be skipped without building a key string for each one)
local lists = {}
local function loadData()
    lists = {}
    local data = mwse.loadConfig("mwcollide_data")
    if not data or not data.cells then
        log("no MWSE\\config\\mwcollide_data.json yet: run mwdialog_check.bat --cell-conflicts")
        return
    end
    local n = 0
    for cellId, entries in pairs(data.cells) do
        local set = { byKey = {}, ids = {} }
        for _, e in ipairs(entries) do
            if type(e.id) == "string" and type(e.pos) == "table" and #e.pos >= 3 then
                local id = e.id:lower()
                set.byKey[string.format("%s|%d|%d|%d", id, e.pos[1], e.pos[2], e.pos[3])] = e
                set.ids[id] = true
                n = n + 1
            end
        end
        lists[cellId:lower()] = set
    end
    log("list from %s: %d object(s) in %d cell(s)", tostring(data.generated), n, table.size(lists))
end

local function round(v) return math.floor(v + 0.5) end

local function refKey(ref)
    local p = ref.position
    return string.format("%s|%d|%d|%d", ref.object.id:lower(), round(p.x), round(p.y), round(p.z))
end

-- one interior --------------------------------------------------------------------------------------
-- what this mod hid is kept with the player (in the save), not on each object: reading ref.data would
-- give every object in the cell its own saved data
-- reviewed: created only when something is hidden (the original added an empty table to the save for
-- every cell ever visited, exteriors included)
local function hiddenIn(cellId, create)
    local all = tes3.player.data.mwcollide
    if not all then
        if not create then return nil end
        all = {}
        tes3.player.data.mwcollide = all
    end
    local mine = all[cellId]
    if not mine and create then
        mine = {}
        all[cellId] = mine
    end
    return mine
end

local function cellKey(cell)
    if cell.isInterior then return cell.id:lower() end
    return string.format("#%d,%d", cell.gridX, cell.gridY)
end

local function settleCell(cell)
    if not cell or not tes3.player then return 0, 0 end
    local cellId = cellKey(cell)
    local set = config.enabled and lists[cellId] or nil
    local mine = hiddenIn(cellId, false)
    if not set and (not mine or next(mine) == nil) then return 0, 0 end
    mine = mine or hiddenIn(cellId, true)
    local anyHidden = next(mine) ~= nil
    local hid, shown = 0, 0
    for ref in cell:iterateReferences() do
        local obj = ref.object
        if obj and not ref.deleted and ((set and set.ids[obj.id:lower()]) or (anyHidden and ref.disabled)) then
            local k = refKey(ref)
            local listed = set and set.byKey[k]
            if listed and not mine[k] and not ref.disabled then
                mine[k] = true
                anyHidden = true
                ref:disable()
                hid = hid + 1
                log("%s: hid %s from %s (%s's %s is in the same spot)", cell.editorName, ref.object.id,
                    listed.from, listed.kept, listed.keptObject)
            elseif mine[k] and not listed then
                mine[k] = nil
                ref:enable()
                shown = shown + 1
                log("%s: %s shown again (%s)", cell.editorName, ref.object.id,
                    config.enabled and "no longer on the list" or "switched off")
            end
        end
    end
    return hid, shown
end

local function settleActive()
    local hid, shown = 0, 0
    for _, cell in ipairs(tes3.getActiveCells()) do
        local ok, h, s = pcall(settleCell, cell)
        if ok then
            hid, shown = hid + (h or 0), shown + (s or 0)
        else
            log("error in %s: %s", tostring(cell.id), tostring(h))
        end
    end
    return hid, shown
end

event.register(tes3.event.initialized, loadData)
event.register(tes3.event.loaded, function()
    loadData()                                  -- pick up a list rewritten since the game started
    timer.delayOneFrame(settleActive)
end)
event.register(tes3.event.cellChanged, function()
    timer.delayOneFrame(settleActive)
end)

-- Mod Config menu -----------------------------------------------------------------------------------
event.register(tes3.event.modConfigReady, function()
    local template = mwse.mcm.createTemplate({ name = "Doubled Objects (mwcollide)" })
    template:saveOnClose(CONFIG_NAME, config)
    local page = template:createSideBarPage({
        label = "Settings",
        description = "Hides, as places load, the objects that two unrelated mods both put in the same "
            .. "spot - the earlier mod's copy; the later one stays. The list comes from mwdialog_check "
            .. "--cell-conflicts (MWSE\\config\\mwcollide_data.json). Hidden objects are only disabled.",
    })
    page:createOnOffButton({
        label = "Hide doubled objects",
        description = "Off: everything it hid is shown again, as each place is visited.",
        variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
        callback = function() if tes3.player then settleActive() end end,
    })
    page:createButton({
        buttonText = "Re-read the list and apply it here now",
        description = "After running --cell-conflicts again, or to apply the switch above without leaving.",
        callback = function()
            loadData()
            if tes3.player then
                local h, s = settleActive()
                tes3.messageBox("Doubled objects here: %d hidden, %d shown again.", h, s)
            end
        end,
    })
    page:createOnOffButton({
        label = "Write what it does to MWSE\\logs\\mwcollide.log",
        variable = mwse.mcm.createTableVariable({ id = "log", table = config }),
    })
    template:register()
end)
