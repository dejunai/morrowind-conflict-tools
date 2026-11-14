--[[
    mwsoundguard v2 - stops one object from stacking the same sound over and over, whatever mod causes it.

    The case it was built for: on the chargen ship the lanterns (light_com_lantern_02_200_Boat) run the
    "Float" script. Expanded Sounds' Float does, every frame:
        if ( GetSoundPlaying "plx_ES_Water" == 0 )  PlayLoopSound3DVP "plx_ES_Water", 0.6, 1.0
    On these light objects the engine keeps answering "not playing" even after the loop has started, so
    a new copy of the loop is added every frame until the game falls over. tes3.getSoundPlaying asks the
    same engine function, so this mod cannot rely on it alone: it keeps its own record of what it let start.

    Rules, per (object, sound), for objects other than NPCs, creatures and the player; voice lines never:
      * looping sounds: the first start is let through. Another start of the same loop on the same object
        within loopGap seconds is a duplicate and is blocked, as is any start while the engine says it is
        playing. After suspectLimit duplicates in a row the pair is classified:
          - engine sees the loop playing -> from then on blocked only while the engine says it is playing
            (so a later StopSound + restart still works);
          - engine says it is NOT playing although it was started -> "runaway": every further start is
            blocked (the one copy keeps playing) until the object leaves the active cells or a save loads.
        More than maxLoopStarts starts within loopWindow seconds is also a runaway (slow stacking).
      * one-shot sounds: at most oneShotPerSecond starts per second; a restart within oneShotMinGap seconds
        while the engine says it is still playing is dropped. Sustained overruns are reported.
      * safety net: at most globalCap new object sounds per globalWindow seconds across the whole game.
    Every runaway is reported once per object type and sound: one line in MWSE.log, details (object, cell, sound, file, script and
    the plugins they come from) in Data Files\MWSE\logs\mwsoundguard.log, plus a summary there each minute.

    Config (MWSE\config\mwsoundguard.json, optional): see DEFAULTS below. exemptSounds = { ["sound id"] = true }.
    No per-frame handler; nothing is saved to the save game. Any error inside the guard lets the sound play.
]]

local DEFAULTS = {
    enabled = true,
    loopGap = 1.0,            -- s: a second start of the same loop on the same object this soon is a duplicate
    suspectLimit = 3,         -- this many duplicates of one loop -> runaway
    loopWindow = 10,          -- s
    maxLoopStarts = 4,        -- loop starts allowed per object and sound within loopWindow
    oneShotPerSecond = 8,     -- one-shot starts allowed per object and sound per second
    oneShotMinGap = 0.05,     -- s: restart of a still-playing one-shot this soon is dropped
    globalWindow = 0.05,      -- s
    globalCap = 32,           -- new object sounds allowed per globalWindow, all objects together
    summarySeconds = 60,
    mainLogReports = 10,      -- runaway lines written to MWSE.log; later ones go to the own log only
    trace = false,            -- log every allowed loop start on an object (diagnostics)
    traceLimit = 300,
    exemptSounds = {},        -- sound id (lower case) -> true
}

local config = DEFAULTS
do
    local ok, loaded = pcall(mwse.loadConfig, "mwsoundguard", DEFAULTS)
    if ok and type(loaded) == "table" then
        config = loaded
        for k, v in pairs(DEFAULTS) do
            if type(config[k]) ~= type(v) then config[k] = v end
        end
    end
    local ex = {}
    for k, v in pairs(config.exemptSounds) do
        if v and type(k) == "string" then ex[k:lower()] = true end
    end
    config.exemptSounds = ex
end

local clock = os.clock
local T_NPC, T_CREATURE = tes3.objectType.npc, tes3.objectType.creature

-- ---------------------------------------------------------------- state
-- refs[reference] = false (never guarded: actor) or { [sound object or temp path] = record }
local refs = setmetatable({}, { __mode = "k" })
local Q = {}                                   -- reused tes3.getSoundPlaying params (no allocation per call)
local gWindowStart, gCount, gBlocked = -1, 0, 0
local stats = { dupLoops = 0, runawayBlocks = 0, oneShotBlocks = 0, capBlocks = 0, runaways = 0, errors = 0 }
local pending = {}                             -- "object|sound" -> blocked since last summary (own log only)
local mainLines, traceLines = 0, 0

-- ---------------------------------------------------------------- logging
local LOG_DIR = "Data Files\\MWSE\\logs"
local logFile, logTried = nil, false

local function ownLog(fmt, ...)
    if not logFile then
        if logTried then return end
        logTried = true
        pcall(lfs.mkdir, LOG_DIR)
        logFile = io.open(LOG_DIR .. "\\mwsoundguard.log", "w")
        if not logFile then return end
        logFile:write(os.date("mwsoundguard log, session started %Y-%m-%d %H:%M:%S\n"))
    end
    logFile:write(string.format(fmt, ...), "\n")
    logFile:flush()
end

local function safe(f, ...)
    local ok, v = pcall(f, ...)
    if ok and v ~= nil then return v end
    return "?"
end

local function describe(ref, snd, path)
    local d = {}
    d.ref = safe(function() return ref.id end)
    d.obj = safe(function() return ref.object.id end)
    d.objMod = safe(function() return ref.object.sourceMod end)
    d.objType = safe(function() return table.find(tes3.objectType, ref.object.objectType) end)
    d.cell = safe(function() local c = ref.cell return c.editorName or c.id end)
    d.script = safe(function() return ref.object.script.id end)
    d.scriptMod = safe(function() return ref.object.script.sourceMod end)
    d.attached = safe(function() return ref.object.sound.id end)
    d.sound = snd and safe(function() return snd.id end) or tostring(path)
    d.file = snd and safe(function() return snd.filename end) or tostring(path)
    d.soundMod = snd and safe(function() return snd.sourceMod end) or "-"
    return d
end

local function keyName(ref, snd, path)
    return safe(function() return ref.object.id end) .. "|" .. (snd and safe(function() return snd.id end) or tostring(path))
end

local function enginePlaying(snd, ref)
    if not snd then return false end
    Q.sound, Q.reference = snd, ref
    local ok, r = pcall(tes3.getSoundPlaying, Q)
    Q.sound, Q.reference = nil, nil
    return ok and r == true
end

local reportedKeys = {}                        -- "object|sound" -> number of references reported

local function reportRunaway(ref, snd, path, rec, why)
    stats.runaways = stats.runaways + 1
    local name = rec.name or keyName(ref, snd, path)
    rec.name = name
    local seen = reportedKeys[name]
    if seen then                                 -- same object type and sound on another copy: short note only
        reportedKeys[name] = seen + 1
        if seen < 50 then
            ownLog("RUNAWAY again: %s on %s (%s)", name, safe(function() return ref.id end), why)
        end
        return
    end
    reportedKeys[name] = 1
    local d = describe(ref, snd, path)
    local playing = enginePlaying(snd, ref) and "yes" or "no"
    ownLog("RUNAWAY %s: %s (%s) on %s [object %s from %s, type %s] in cell %s; file %s (sound from %s); "
        .. "object's script %s (from %s); object's own sound %s; engine says playing: %s; %d start(s) in %.2f s",
        rec.loop and "loop" or "one-shot", d.sound, why, d.ref, d.obj, d.objMod, tostring(d.objType), d.cell, d.file,
        d.soundMod, d.script, d.scriptMod, d.attached, playing, rec.total, clock() - rec.first)
    if playing == "no" and rec.loop then
        ownLog("  note: the engine reports this loop as not playing, so a script that checks GetSoundPlaying "
            .. "before PlayLoopSound3D will keep asking; mwsoundguard keeps one copy and drops the rest.")
    end
    if mainLines < config.mainLogReports then
        mainLines = mainLines + 1
        mwse.log("[mwsoundguard] stopped %s from restarting %s over and over on %s in %s (object from %s, script %s); "
            .. "keeping one copy. Details: MWSE\\logs\\mwsoundguard.log", d.sound, rec.loop and "a loop" or "a sound",
            d.ref, d.cell, d.objMod, d.script)
    elseif mainLines == config.mainLogReports then
        mainLines = mainLines + 1
        mwse.log("[mwsoundguard] more runaway sounds; further reports only in MWSE\\logs\\mwsoundguard.log")
    end
end

local function noteBlock(ref, snd, path, rec)
    rec.blocked = rec.blocked + 1
    local name = rec.name
    if not name then
        name = keyName(ref, snd, path)               -- computed once per object and sound
        rec.name = name
    end
    pending[name] = (pending[name] or 0) + 1
end

-- ---------------------------------------------------------------- core
local function guard(e)
    if e.block or e.isVoiceover then return end
    local ref = e.reference
    if not ref then return end                       -- UI, wind, 2D sounds: not tied to an object

    local per = refs[ref]
    if per == nil then
        local ot = ref.object.objectType
        if ot == T_NPC or ot == T_CREATURE then
            refs[ref] = false
            return
        end
        per = {}
        refs[ref] = per
    elseif per == false then
        return
    end

    local snd = e.sound
    local path = (not snd) and e.path or nil
    local key = snd or path
    if not key then return end

    local rec = per[key]
    local now = clock()
    local loop = e.flags == 1                         -- documented: 1 = looping, 0 = not

    if rec == nil then
        if snd and next(config.exemptSounds) and config.exemptSounds[snd.id:lower()] then
            per[key] = false
            return
        end
        rec = { loop = loop, first = now, last = -1e9, w0 = now, n = 0, suspect = 0, over = 0,
                total = 0, blocked = 0, runaway = false, reported = false, name = nil, mode = nil }
        per[key] = rec
    elseif rec == false then
        return                                        -- exempt sound
    end
    rec.total = rec.total + 1

    rec.loop = loop
    if loop then
        local mode = rec.mode
        if mode == "blind" then                       -- runaway the engine can't see: keep the one copy
            stats.runawayBlocks = stats.runawayBlocks + 1
            e.block = true
            noteBlock(ref, snd, path, rec)
            return
        end
        if mode == "engine" then                      -- engine sees this loop: trust it from now on
            if enginePlaying(snd, ref) then
                stats.dupLoops = stats.dupLoops + 1
                e.block = true
                noteBlock(ref, snd, path, rec)
                return
            end
        elseif now - rec.last < config.loopGap then
            rec.suspect = rec.suspect + 1
            stats.dupLoops = stats.dupLoops + 1
            e.block = true
            noteBlock(ref, snd, path, rec)
            if rec.suspect >= config.suspectLimit then
                if enginePlaying(snd, ref) then
                    rec.mode = "engine"
                    ownLog("duplicate loop starts: %s (engine sees it playing; extra starts are dropped)", keyName(ref, snd, path))
                else
                    rec.mode = "blind"
                    rec.runaway = true
                    reportRunaway(ref, snd, path, rec, string.format("%d restarts within %.1f s", rec.suspect, config.loopGap))
                end
            end
            return
        elseif enginePlaying(snd, ref) then           -- already playing on this object: a plain duplicate
            stats.dupLoops = stats.dupLoops + 1
            e.block = true
            noteBlock(ref, snd, path, rec)
            return
        else
            if now - rec.w0 > config.loopWindow then
                rec.w0, rec.n, rec.suspect = now, 0, 0
            end
            rec.n = rec.n + 1
            if rec.n > config.maxLoopStarts then
                rec.mode = "blind"
                rec.runaway = true
                e.block = true
                noteBlock(ref, snd, path, rec)
                reportRunaway(ref, snd, path, rec, string.format("%d starts within %d s", rec.n, config.loopWindow))
                return
            end
        end
    else
        if now - rec.w0 >= 1.0 then
            if rec.n > config.oneShotPerSecond then rec.over = rec.over + 1 else rec.over = 0 end
            rec.w0, rec.n = now, 0
        end
        rec.n = rec.n + 1
        if rec.n > config.oneShotPerSecond then
            stats.oneShotBlocks = stats.oneShotBlocks + 1
            e.block = true
            noteBlock(ref, snd, path, rec)
            if rec.over >= 2 and not rec.reported then
                rec.reported = true
                reportRunaway(ref, snd, path, rec, string.format("over %d starts per second for 3 s", config.oneShotPerSecond))
            end
            return
        end
        if now - rec.last < config.oneShotMinGap and enginePlaying(snd, ref) then
            stats.oneShotBlocks = stats.oneShotBlocks + 1
            e.block = true
            noteBlock(ref, snd, path, rec)
            return
        end
    end

    -- global safety net
    if now - gWindowStart >= config.globalWindow then
        gWindowStart, gCount = now, 0
    end
    gCount = gCount + 1
    if gCount > config.globalCap then
        stats.capBlocks = stats.capBlocks + 1
        gBlocked = gBlocked + 1
        e.block = true
        return
    end

    rec.last = now
    if loop and config.trace and traceLines < config.traceLimit then
        traceLines = traceLines + 1
        local d = describe(ref, snd, path)
        ownLog("trace: loop %s started on %s (%s, script %s) in %s", d.sound, d.ref, d.obj, d.script, d.cell)
    end
end

-- ---------------------------------------------------------------- fail-open wrapper
local registered = false
local onSound

local function disableSelf(err)
    if registered then
        pcall(event.unregister, tes3.event.addSound, onSound, { priority = -100 })
        pcall(event.unregister, tes3.event.addTempSound, onSound, { priority = -100 })
        registered = false
    end
    pcall(mwse.log, "[mwsoundguard] turned itself off after repeated errors; last: %s", tostring(err))
end

onSound = function(e)
    local ok, err = pcall(guard, e)
    if not ok then
        stats.errors = stats.errors + 1
        if stats.errors == 1 then pcall(mwse.log, "[mwsoundguard] error (sound allowed): %s", tostring(err)) end
        if stats.errors >= 10 then disableSelf(err) end
    end
end

local function summary()
    local lines = {}
    for k, n in pairs(pending) do lines[#lines + 1] = string.format("  %s: %d blocked", k, n) end
    if #lines == 0 and gBlocked == 0 then return end
    table.sort(lines)
    ownLog("summary: duplicate loop starts %d, runaway blocks %d, one-shot blocks %d, global cap blocks %d (%d new)",
        stats.dupLoops, stats.runawayBlocks, stats.oneShotBlocks, stats.capBlocks, gBlocked)
    for _, l in ipairs(lines) do ownLog("%s", l) end
    pending = {}
    gBlocked = 0
end

local function forget(e)
    if e.reference then refs[e.reference] = nil end
end

local function reset()
    refs = setmetatable({}, { __mode = "k" })
end

if config.enabled then
    event.register(tes3.event.addSound, onSound, { priority = -100 })
    event.register(tes3.event.addTempSound, onSound, { priority = -100 })
    registered = true
    event.register(tes3.event.referenceDeactivated, forget)
    local function startSummaryTimer()
        timer.start({ type = timer.real, duration = config.summarySeconds, iterations = -1, persist = false, callback = summary })
    end
    event.register(tes3.event.loaded, function()
        reset()
        startSummaryTimer()                          -- MWSE cancels every timer right before `loaded`
    end)
    event.register(tes3.event.initialized, function()
        startSummaryTimer()
        mwse.log("[mwsoundguard] active (v2)")
    end)
end

-- for tests and other mods
return { config = config, stats = stats, refs = function() return refs end, summary = summary, guard = guard }
