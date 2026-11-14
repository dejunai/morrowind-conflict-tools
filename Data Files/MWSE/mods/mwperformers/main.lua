--[[
    mwperformers - one band per inn

    When you enter an interior, it looks at the performers there: NPCs with a bard, lute or drummer
    animation, or a script named for it (Animated Morrowind, Bards of Bardenfell and the like). It sorts
    them by the mod that makes each one perform. If two or more mods put performers in the same place,
    the mod that loads last keeps its performers; the others' are hidden.

    Only performers a mod added itself are hidden (placed by the same mod that makes them perform). An
    inn's own NPC that an earlier mod turned into a bard is a person with a life there: left alone, and
    listed in the log.

    Nothing is decided in advance from a generated list, so it works for any mods in any load order: change
    your mods and the next visit decides again. Performers it hid are remembered on the player, not on
    each NPC. Hidden performers are only disabled, never deleted;
    the Mod Config menu can show them all again, or hide the doubles again.
    Decisions are written to Data Files\MWSE\logs\mwperformers.log.
]]

local CONFIG_NAME = "mwperformers"
local config = mwse.loadConfig(CONFIG_NAME, { enabled = true, log = true })

local ANIM_PATTERNS = { "bard", "lute", "drum", "perform", "musician" }
local SCRIPT_PATTERNS = { "bard", "lute", "drum", "perform", "musician", "minstrel" }

-- log ---------------------------------------------------------------------------------------------
local LOG_DIR = "Data Files\\MWSE\\logs"
local logFile
local function log(fmt, ...)
    if not config.log then return end
    if not logFile then
        pcall(function() lfs.mkdir(LOG_DIR) end)
        logFile = io.open(LOG_DIR .. "\\mwperformers.log", "w")
        if not logFile then return end
        logFile:write(os.date("mwperformers log, started %Y-%m-%d %H:%M:%S"), "\n")
    end
    local ok, line = pcall(string.format, fmt, ...)
    logFile:write(os.date("[%H:%M:%S] "), ok and line or tostring(fmt), "\n")
    logFile:flush()
end

-- load order --------------------------------------------------------------------------------------
local loadIndex
local function modIndex(name)
    if not loadIndex then
        loadIndex = {}
        for i, m in ipairs(tes3.getModList() or {}) do loadIndex[m:lower()] = i end
    end
    return name and loadIndex[name:lower()] or -1
end

-- who performs ------------------------------------------------------------------------------------
local function matches(text, patterns)
    if not text or text == "" then return false end
    text = text:lower()
    for _, p in ipairs(patterns) do
        if text:find(p, 1, true) then return true end
    end
    return false
end

-- the mod that makes this NPC perform, or nil if it isn't a performer
local function performingMod(ref)
    local obj = ref.object
    if not obj or obj.objectType ~= tes3.objectType.npc then return nil end
    local base = obj.baseObject or obj
    if matches(base.mesh, ANIM_PATTERNS) or (base.script and matches(base.script.id, SCRIPT_PATTERNS)) then
        return base.sourceMod
    end
    return nil
end

local function describe(ref)
    local name = ref.object.name
    return (name and name ~= "") and string.format("%s (%s)", name, ref.object.id) or ref.object.id
end

-- hidden performers are remembered on the player, not on each NPC. ref.data would write a lua table
-- into the save for every performer visited, including ones that are only logged.
local sessionLogged = {}

local function refKey(ref)
    local p = ref.startingPosition or ref.position
    local cell = ref.cell
    local where = "?"
    if cell then
        where = cell.isInterior and cell.id:lower() or string.format("#%d,%d", cell.gridX, cell.gridY)
    end
    return string.format("%s|%s|%d|%d|%d", where, ref.object.id:lower(),
        math.floor(p.x + 0.5), math.floor(p.y + 0.5), math.floor(p.z + 0.5))
end

local function hiddenMap(create)
    if not tes3.player then return nil end
    local all = tes3.player.data.mwperformers
    if not all then
        if not create then return nil end
        all = {}
        tes3.player.data.mwperformers = all
    end
    return all
end

-- the decision for one cell -----------------------------------------------------------------------
local function settleCell(cell)
    if not cell or not cell.isInterior then return end
    local byMod, mods = {}, {}
    for ref in cell:iterateReferences(tes3.objectType.npc) do
        if not ref.deleted then
            local mod = performingMod(ref)
            if mod then
                local key = mod:lower()
                if not byMod[key] then
                    byMod[key] = {}
                    mods[#mods + 1] = mod
                end
                table.insert(byMod[key], ref)
            end
        end
    end

    -- show everything again: switched off, or only one mod performs here now
    local function restoreAll()
        local mine = hiddenMap(false)
        if not mine then return end
        for _, refs in pairs(byMod) do
            for _, ref in ipairs(refs) do
                local k = refKey(ref)
                if mine[k] then
                    mine[k] = nil
                    ref:enable()
                    log("%s: %s shown again", cell.editorName, describe(ref))
                end
            end
        end
    end
    if not config.enabled or #mods < 2 then
        restoreAll()
        return
    end

    table.sort(mods, function(a, b) return modIndex(a) > modIndex(b) end)
    local keep = mods[1]
    for i = 2, #mods do
        local mod = mods[i]
        for _, ref in ipairs(byMod[mod:lower()]) do
            local placedBy = ref.sourceMod
            if placedBy and placedBy:lower() == mod:lower() then
                if not ref.disabled then
                    ref:disable()
                    local mine = hiddenMap(true)
                    mine[refKey(ref)] = true
                    log("%s: hid %s from %s (%s loads later and keeps its performers)",
                        cell.editorName, describe(ref), mod, keep)
                end
            elseif not sessionLogged[ref] then
                sessionLogged[ref] = true
                log("%s: left %s - %s's NPC that %s makes perform (only added performers are hidden)",
                    cell.editorName, describe(ref), tostring(placedBy), mod)
            end
        end
    end
    -- the keeper's performers are visible (in case an earlier decision hid them)
    local mine = hiddenMap(false)
    for _, ref in ipairs(byMod[keep:lower()]) do
        local k = refKey(ref)
        if mine and mine[k] then
            mine[k] = nil
            ref:enable()
            log("%s: %s shown again (%s now loads last)", cell.editorName, describe(ref), keep)
        end
    end
end

local function settleActive()
    for _, cell in ipairs(tes3.getActiveCells()) do
        local ok, err = pcall(settleCell, cell)
        if not ok then log("error in %s: %s", tostring(cell.editorName), tostring(err)) end
    end
end

event.register(tes3.event.cellChanged, function()
    timer.delayOneFrame(settleActive)          -- after the cell's references are all in place
end)
event.register(tes3.event.loaded, function()
    loadIndex = nil
    sessionLogged = {}
    timer.delayOneFrame(settleActive)
end)

-- Mod Config menu ---------------------------------------------------------------------------------
event.register(tes3.event.modConfigReady, function()
    local template = mwse.mcm.createTemplate({ name = "One Band Per Inn" })
    template:saveOnClose(CONFIG_NAME, config)
    local page = template:createSideBarPage({
        label = "Settings",
        description = "Where two or more mods put performers in the same interior, the mod that loads last "
            .. "keeps its performers and the others' are hidden (disabled, never deleted). Decided on each "
            .. "visit, so it follows your load order. Decisions go to MWSE\\logs\\mwperformers.log.",
    })
    page:createOnOffButton({
        label = "Hide doubled performers",
        description = "Off: every performer is shown again, as each place is visited.",
        variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
        callback = function() if tes3.player then settleActive() end end,
    })
    page:createButton({
        buttonText = "Decide again here now",
        description = "Apply the setting above to the place you're in, without leaving it.",
        callback = function()
            if tes3.player then
                settleActive()
                tes3.messageBox("Performers here: " .. (config.enabled and "doubles hidden." or "all shown."))
            end
        end,
    })
    page:createOnOffButton({
        label = "Write decisions to MWSE\\logs\\mwperformers.log",
        variable = mwse.mcm.createTableVariable({ id = "log", table = config }),
    })
    template:register()
end)
