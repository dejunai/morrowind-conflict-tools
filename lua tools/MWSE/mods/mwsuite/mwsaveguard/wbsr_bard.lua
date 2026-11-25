--[[
    mwsaveguard.wbsr_bard (CR-17): abot's WBSR (Well Behaved Sound Replacers) stops saves while a voiceover plays,
    so a reload can't start the same speech twice. A tavern bard (Bards of Bardenfell's DM_Bard_script and its
    siblings) sings with the engine Say command, files under Sound\Vo\Bard\, all larger than WBSR's
    minVoiceoverSize, and starts the next song as soon as the last one ends: WBSR's save block then holds for as
    long as you stay in the inn, and every save there is swallowed without a word.

    For a bard song only, the save handler WBSR registers in that same addTempSound event is unregistered right
    after WBSR's handler. WBSR still tracks the song as its voiceover (and still keeps sound replacers off it); a
    real speech keeps its save block. WBSR, Bards of Bardenfell and mwperformers are not changed, and event.register
    isn't wrapped: the new save handler is found in MWSE's event table, by its source file.

    Switch: mwsaveguard's MCM, "Let saves through while a bard sings". Unset, it is on when WBSR is installed and
    loaded, else off. With no WBSR this registers nothing at all.
]]

local M = {}

local WBSR_FILE = "Data Files\\MWSE\\mods\\abot\\WBSR\\main.lua"
local WBSR_SOURCE = "abot[/\\]wbsr[/\\]"            -- in a callback's source path, lower case
local WBSR_CONFIG = "abotWBSR"                       -- its MWSE\config\abotWBSR.json (read only)

-- the same names mwperformers treats as a bard or musician
local ANIM_PATTERNS = { "bard", "lute", "drum", "perform", "musician" }
local SCRIPT_PATTERNS = { "bard", "lute", "drum", "perform", "musician", "minstrel" }
local BARD_PATH = "^vo[\\/]+bard[\\/]"

local opts                                           -- config, log, handlers (set by setup)
local state = { file = false, loaded = false, blockOff = false }
local bookends = nil                                 -- { before = fn, after = fn, priority = p } while registered
local watching, before = false, nil
local released, toldMWSE = 0, false

local function matches(text, patterns)
    if type(text) ~= "string" or text == "" then return false end
    text = text:lower()
    for i = 1, #patterns do
        if text:find(patterns[i], 1, true) then return true end
    end
    return false
end

local function isBardRef(ref)
    local ok, yes = pcall(function()
        local obj = ref and ref.object
        if not obj then return false end
        local base = obj.baseObject or obj
        if base.objectType ~= tes3.objectType.npc then return false end
        return matches(base.mesh, ANIM_PATTERNS) or (base.script ~= nil and matches(base.script.id, SCRIPT_PATTERNS))
    end)
    return ok and yes
end

-- a tavern song (Vo\Bard\...), or a performer's own line under Vo\
function M.isBardVoiceover(path, ref, isVoiceover)
    if type(path) == "string" and path ~= "" then
        local lc = path:lower()
        if lc:find(BARD_PATH) then return true end
        return (isVoiceover == true or lc:find("^vo[\\/]") ~= nil) and isBardRef(ref)
    end
    return isVoiceover == true and isBardRef(ref)
end

local function installDir()
    local dir = tes3 and tes3.installDirectory
    return (type(dir) == "string" and dir ~= "") and (dir .. "\\") or ""
end

local function wbsrHandlers(name)
    local out = {}
    for _, h in ipairs(opts.handlers(name)) do
        local info = debug.getinfo(h.fn, "S") or {}
        local src = (info.source or ""):lower()
        if src:find(WBSR_SOURCE) then out[#out + 1] = h end
    end
    return out
end

-- installed: its main.lua is there. Loaded: one of its callbacks is in MWSE's event table (a mod switched off in
-- MWSE's mod list never registers any).
local function wbsrLoaded()
    for _, name in ipairs({ "modConfigReady", "loaded", "initialized", "addTempSound", "cellChanged" }) do
        if #wbsrHandlers(name) > 0 then return true end
    end
    return false
end

function M.detect()
    state.file = lfs.attributes(installDir() .. WBSR_FILE) ~= nil
    state.loaded = state.file and wbsrLoaded() or false
    local ok, cfg = pcall(mwse.loadConfig, WBSR_CONFIG)
    state.blockOff = ok and type(cfg) == "table" and cfg.shortBlockLoadSave == false or false
    return state.file and state.loaded
end

function M.present() return state.file and state.loaded end

function M.enabled()
    if not M.present() then return false end
    local v = opts.config.letBardSongsSave
    if v == nil then return true end                 -- unset: on wherever WBSR is
    return v == true
end

function M.status()
    if not state.file then return "WBSR isn't installed: this does nothing." end
    if not state.loaded then return "WBSR is installed but isn't loaded: this does nothing." end
    if state.blockOff then return "WBSR is loaded, with its voiceover save block (shortBlockLoadSave) off." end
    return "WBSR is installed and loaded."
end

local function onBefore(e)
    watching, before = false, nil
    if not M.enabled() or not M.isBardVoiceover(e.path, e.reference, e.isVoiceover) then return end
    before = {}
    for _, h in ipairs(opts.handlers("save")) do before[h.fn] = true end
    watching = true
end

local function describe(ref)
    local ok, s = pcall(function()
        local name = ref.object.name
        local id = ref.id or ref.object.id
        return (name and name ~= "") and string.format("%s (%s)", name, tostring(id)) or tostring(id)
    end)
    return ok and s or "?"
end

local function onAfter(e)
    if not watching then return end
    watching = false
    local was = before
    before = nil
    for _, h in ipairs(wbsrHandlers("save")) do
        if not was[h.fn] then                        -- registered just now, for this song: WBSR's save block
            local ok, err = pcall(event.unregister, "save", h.fn)
            if not ok then
                mwse.log("[mwsaveguard.wbsr_bard] Could not let saves through for a bard song: %s", tostring(err))
                return
            end
            released = released + 1
            opts.log("[mwsaveguard.wbsr_bard] Released WBSR's save block for a bard song: %s, path='%s'",
                describe(e.reference), tostring(e.path or ""))
            if not toldMWSE then
                toldMWSE = true
                mwse.log("[mwsaveguard.wbsr_bard] Released WBSR's save block for a bard song (%s, '%s'); "
                    .. "further releases are only in MWSE\\logs\\mwsaveguard.log", describe(e.reference),
                    tostring(e.path or ""))
            end
        end
    end
end

-- around WBSR's own addTempSound handler (its highest one: 200000, 9130 once mwdialog_luafix lowered it)
local function placeBookends()
    local top
    for _, h in ipairs(wbsrHandlers("addTempSound")) do
        if type(h.priority) == "number" and (not top or h.priority > top) then top = h.priority end
    end
    if bookends and bookends.priority == top then return end
    if bookends then
        pcall(event.unregister, "addTempSound", onBefore, { priority = bookends.priority + 1 })
        pcall(event.unregister, "addTempSound", onAfter, { priority = bookends.priority - 1 })
        bookends = nil
    end
    if not top then return end
    event.register("addTempSound", onBefore, { priority = top + 1 })
    event.register("addTempSound", onAfter, { priority = top - 1 })
    bookends = { priority = top }
end

local function refresh()
    M.detect()
    if M.enabled() then
        placeBookends()
    elseif bookends then
        pcall(event.unregister, "addTempSound", onBefore)
        pcall(event.unregister, "addTempSound", onAfter)
        bookends = nil
    end
    watching, before = false, nil
end
M.refresh = refresh

-- opts: config (mwsaveguard's table: letBardSongsSave), log (mwsaveguard.log), handlers(name) -> { {fn, priority} }
function M.setup(o)
    opts = o
    -- WBSR registers its addTempSound handlers on the first load (its initOnce): look after it has run
    event.register("initialized", function()
        if M.detect() then
            mwse.log("[mwsaveguard.wbsr_bard] Initialized: WBSR found. Saves while a bard sings: %s.",
                M.enabled() and "let through" or "left to WBSR (switched off in mwsaveguard's MCM)")
        end
    end, { priority = -100 })
    event.register("loaded", function()
        if state.file then refresh() end
    end, { priority = -100 })
    return M
end

function M.stats() return { released = released, bookends = bookends and bookends.priority } end

return M
