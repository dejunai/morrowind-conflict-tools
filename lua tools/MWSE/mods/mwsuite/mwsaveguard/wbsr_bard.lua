--[[
    mwsaveguard.wbsr_bard (CR-17): abot's WBSR (Well Behaved Sound Replacers) stops saves while a voiceover plays,
    so a reload can't start the same speech twice. A tavern bard (Bards of Bardenfell's DM_Bard_script and its
    siblings) sings with the engine Say command, files under Sound\Vo\Bard\, all larger than WBSR's
    minVoiceoverSize, and starts the next song as soon as the last one ends: WBSR's save block then holds for as
    long as you stay in the inn, and every save there is swallowed without a word.

    For a bard song only, the save handler WBSR registers is unregistered right after WBSR's addTempSound handler.
    WBSR's disableSave defers that register to enterFrame (priority 9147) when the engine is still saving or
    loading -- typical when a bard starts on the first frames after you load in an inn or a door autosave. The
    follow-up on enterFrame (9146) lifts that delayed block; a real speech keeps its save block. WBSR, Bards of
    Bardenfell and mwperformers are not changed, and event.register isn't wrapped: the save handler is found in
    MWSE's event table, by its source file.

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
-- anywhere in the path, so Sound\Vo\Bard\... counts the same as Vo\Bard\...
local BARD_PATH = "vo[\\/]+bard[\\/]"

-- bookends do not depend on finding WBSR's addTempSound by source (a wrapper can hide it).
-- onBefore is above stock WBSR (200000) and luafix G1 (9130); onAfter is below both.
-- pending enterFrame is just after WBSR's enterFrameLS (9147), same frame as the delayed register.
local BEFORE_PRI = 200001
local AFTER_PRI  = 9000
local PENDING_PRI = 9146

local opts                                           -- config, log, handlers (set by setup)
local state = { file = false, loaded = false, blockOff = false }
local bookends = nil                                 -- { priority = AFTER_PRI } while registered
local watching, before = false, nil
local released, toldMWSE = 0, false
local pending, pendingWas, pendingRef, pendingPath = false, nil, nil, nil
local pendingReg = false

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

local function voiceoverFlag(v)
    return v == true or v == 1
end

-- a tavern song (Vo\Bard\... or Sound\Vo\Bard\...), or a performer's own line under Vo\
function M.isBardVoiceover(path, ref, isVoiceover)
    if type(path) == "string" and path ~= "" then
        local lc = path:lower()
        if lc:find(BARD_PATH) then return true end
        return (voiceoverFlag(isVoiceover) or lc:find("vo[\\/]") ~= nil) and isBardRef(ref)
    end
    return voiceoverFlag(isVoiceover) and isBardRef(ref)
end

local function isOtherVoiceover(path, isVoiceover)
    if M.isBardVoiceover(path, nil, isVoiceover) then return false end
    if voiceoverFlag(isVoiceover) then return true end
    if type(path) ~= "string" or path == "" then return false end
    return path:lower():find("vo[\\/].+%.[wm][ap][v3]$") ~= nil
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

-- the MCM switch: saved even at the main menu, when no game (and no WBSR handlers) are loaded yet
function M.wanted()
    local v = opts.config.letBardSongsSave
    if v == nil then return state.file == true end   -- unset: on when WBSR is installed
    return v == true
end

function M.enabled()
    if not M.present() then return false end
    return M.wanted()
end

function M.status()
    if not state.file then return "WBSR isn't installed: this does nothing." end
    if not state.loaded then
        return "WBSR is installed. It isn't loaded yet (normal at the main menu); this setting is saved and used once a game is loaded."
    end
    if state.blockOff then return "WBSR is loaded, with its voiceover save block (shortBlockLoadSave) off." end
    return "WBSR is installed and loaded."
end

local function describe(ref)
    local ok, s = pcall(function()
        local name = ref.object.name
        local id = ref.id or ref.object.id
        return (name and name ~= "") and string.format("%s (%s)", name, tostring(id)) or tostring(id)
    end)
    return ok and s or "?"
end

local function alreadyWbsrSave(was)
    for _, h in ipairs(wbsrHandlers("save")) do
        if was and was[h.fn] then return true end
    end
    return false
end

local function releaseNew(was, ref, path)
    local lifted = false
    for _, h in ipairs(wbsrHandlers("save")) do
        if not (was and was[h.fn]) then              -- registered for this song: WBSR's save block
            local ok, err = pcall(event.unregister, "save", h.fn)
            if not ok then
                mwse.log("[mwsaveguard.wbsr_bard] Could not let saves through for a bard song: %s", tostring(err))
                return false
            end
            released = released + 1
            lifted = true
            opts.log("[mwsaveguard.wbsr_bard] Released WBSR's save block for a bard song: %s, path='%s'",
                describe(ref), tostring(path or ""))
            if not toldMWSE then
                toldMWSE = true
                mwse.log("[mwsaveguard.wbsr_bard] Released WBSR's save block for a bard song (%s, '%s'); "
                    .. "further releases are only in MWSE\\logs\\mwsaveguard.log", describe(ref),
                    tostring(path or ""))
            end
        end
    end
    return lifted
end

local onPendingFrame

local function stopPending()
    pending, pendingWas, pendingRef, pendingPath = false, nil, nil, nil
    if pendingReg then
        pcall(event.unregister, "enterFrame", onPendingFrame)
        pendingReg = false
    end
end

onPendingFrame = function()
    if not pending or not M.enabled() then
        stopPending()
        return
    end
    if releaseNew(pendingWas, pendingRef, pendingPath) then
        stopPending()
    end
end

local function armPending(was, e)
    pending, pendingWas = true, was
    pendingRef, pendingPath = e.reference, e.path
    if not pendingReg then
        event.register("enterFrame", onPendingFrame, { priority = PENDING_PRI })
        pendingReg = true
    end
end

local function onBefore(e)
    watching, before = false, nil
    if not M.enabled() then return end
    if M.isBardVoiceover(e.path, e.reference, e.isVoiceover) then
        before = {}
        for _, h in ipairs(opts.handlers("save")) do before[h.fn] = true end
        watching = true
        return
    end
    -- a real speech starting cancels a delayed lift from an earlier bard song
    if pending and isOtherVoiceover(e.path, e.isVoiceover) then
        stopPending()
    end
end

local function onAfter(e)
    if not watching then return end
    watching = false
    local was = before
    before = nil
    if releaseNew(was, e.reference, e.path) then
        stopPending()
        return
    end
    -- no new handler this tick: if a WBSR block was already there, a speech (or an earlier
    -- missed bard) is holding it -- do not lift. If not, disableSave may have deferred to enterFrameLS.
    if alreadyWbsrSave(was) then return end
    armPending(was, e)
end

local function placeBookends()
    if bookends then return end
    event.register("addTempSound", onBefore, { priority = BEFORE_PRI })
    event.register("addTempSound", onAfter, { priority = AFTER_PRI })
    bookends = { priority = AFTER_PRI }
end

local function refresh()
    M.detect()
    if M.enabled() then
        placeBookends()
    elseif bookends then
        pcall(event.unregister, "addTempSound", onBefore)
        pcall(event.unregister, "addTempSound", onAfter)
        bookends = nil
        stopPending()
    end
    watching, before = false, nil
end
M.refresh = refresh

function M.setWanted(v)
    opts.config.letBardSongsSave = v and true or false
    -- bookends go around WBSR's addTempSound handler, which it registers on the first load
    if tes3.player and tes3.mobilePlayer then
        refresh()
    end
end

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
        refresh()
    end, { priority = -100 })
    return M
end

function M.stats() return { released = released, bookends = bookends and bookends.priority } end

return M
