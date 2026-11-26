--[[
    mwhangwatch - finds what a hang is doing.

    Writes Data Files\MWSE\logs\mwhangwatch.log, flushed after every line so it survives
    a hard hang (kill Morrowind.exe from Task Manager, then read the log).

    Every second:  fps, worst frame, process memory, player cell, inventory
                   size, and how many references / actors became active.
    Every 5 s, and on any slow frame:  a count of references in the loaded
                   cells by object id, with the ids that grew the most.
    Also logged:   new game / load, cell changes, menus opening, StartScript
                   (if this MWSE version reports it).
    Audio:         every sound the engine starts (sounds on references,
                   temporary/voice sounds, sound-buffer plays) and music
                   track changes, with the most frequent sounds listed at
                   each count. If the game stops right after a sound line,
                   that sound is the last thing the engine did.

    Sound blocking: every MWSE mod's addSound / addTempSound handler is
                   watched, and any handler that blocks a sound is named
                   ("BLOCKED by <mod file>:<line>"). A looping sound that is
                   re-added while it is already playing, or because it never
                   started, is flagged too.

    Memory:        a 32-bit Morrowind has 4 GB of address space in all. When
                   it is 80% used (the level can be set), a short on-screen
                   notice comes up (it never opens a menu or takes the mouse)
                   and one line goes to MWSE.log; the biggest users that can
                   be seen from inside the game go to the log: the textures of
                   everything in the loaded cells (by file size, largest
                   first, and by texture folder, which usually points at a
                   texture pack) and the loaded cells with the most objects.
                   The notice repeats each minute while memory stays high.
                   Off until it is turned on in the Mod Config menu; once on,
                   it works even with the rest of the watch turned off.

    Settings:      Mod Config menu -> Guard & Hang Watch (shared with mwguard):
                   turn the whole watch on or off, turn audio watching on or
                   off, set how many sound lines are written per second, and
                   turn the memory warning on or off and set its level.
                   Changes apply right away.

    If the log simply STOPS, the main thread is stuck inside the engine
    (no more frames at all). If it keeps going with falling fps, the growth
    lines show what is piling up.
]]

local LOG_DIR      = "Data Files\\MWSE\\logs"
local LOG_NAME     = LOG_DIR .. "\\mwhangwatch.log"
local CENSUS_EVERY = 5      -- seconds between reference counts
local SLOW_FRAME   = 0.25   -- a frame longer than this (seconds) forces a count
local TOP_N        = 12     -- ids to list per count
local EVENT_LINES  = 20     -- max lines per event type per second (rest are counted)
local SOUND_TOP    = 10     -- most frequent sounds listed with each count

local CONFIG_NAME  = "mwhangwatch"
local config = mwse.loadConfig(CONFIG_NAME, {
    enabled    = false,   -- the whole watch
    audio      = true,   -- sound events, music and sound-blocking mods
    soundLines = 40,     -- max sound lines per second (rest are counted)
    memWarn    = false,  -- warn on screen when memory is nearly used up (opt-in: on only once it is saved on)
    memLimit   = 80,     -- ... at this percentage of the 4 GB address space
})

local f                         -- the log is opened the first time the watch starts
local function openLog()
    if not f then pcall(lfs.mkdir, LOG_DIR) f = io.open(LOG_NAME, "w") end
end
local function watchOn() return config.enabled end
local function audioOn() return config.enabled and config.audio end

local function log(fmt, ...)
    if not f then return end
    local ok, line = pcall(string.format, fmt, ...)
    f:write(string.format("[%9.2f] ", os.clock()), ok and line or tostring(fmt), "\n")
    f:flush()
end

local guard = include("mwguard.interop")
local function memMB()
    -- address space, as the crash report counts it: getVirtualMemoryUsage (private bytes) never reached 95%
    local used = guard and guard.addressSpace and guard.addressSpace()
    if used then return used end
    if mwse.getVirtualMemoryUsage then
        local ok, v = pcall(mwse.getVirtualMemoryUsage)
        if ok and type(v) == "number" then return v / 1048576 end
    end
    return -1
end

local function cellName(cell)
    if not cell then return "-" end
    local ok, s = pcall(function() return cell.editorName or cell.id or cell.name end)
    return (ok and s) or tostring(cell)
end

local function invCount()
    if not tes3.player then return -1 end
    local ok, n = pcall(function()
        local c = 0
        for _, stack in pairs(tes3.player.object.inventory) do
            c = c + math.abs(stack.count or 1)
        end
        return c
    end)
    return ok and n or -1
end

-- per-second counters --------------------------------------------------------
local frames, worst, lastSecond = 0, 0, os.clock()
local counters = {}            -- event name -> count this second
local lines = {}               -- event name -> lines written this second

local function bump(name)
    counters[name] = (counters[name] or 0) + 1
    lines[name] = (lines[name] or 0) + 1
    return lines[name] <= EVENT_LINES
end

-- reference census -------------------------------------------------------------
local lastCounts, lastCensus = nil, -1e9
local soundSummary            -- defined in the audio section below
local blockSummary            -- defined in the sound-blocking section below

local function census(reason)
    lastCensus = os.clock()
    if not tes3.player then return end
    local ok, err = pcall(function()
        local counts, total, disabled, mobiles = {}, 0, 0, 0
        local names = {}
        for _, cell in ipairs(tes3.getActiveCells() or {}) do
            names[#names + 1] = cellName(cell)
            for ref in cell:iterateReferences() do
                total = total + 1
                local id = (ref.object and ref.object.id) or "?"
                counts[id] = (counts[id] or 0) + 1
                if ref.disabled then disabled = disabled + 1 end
                if ref.mobile then mobiles = mobiles + 1 end
            end
        end
        log("CENSUS (%s): %d refs, %d disabled, %d actors, cells: %s",
            reason, total, disabled, mobiles, table.concat(names, " | "))

        local list = {}
        for id, n in pairs(counts) do
            local grew = lastCounts and (n - (lastCounts[id] or 0)) or 0
            list[#list + 1] = { id = id, n = n, grew = grew }
        end
        if lastCounts then
            table.sort(list, function(a, b) return a.grew > b.grew end)
            local any = false
            for i = 1, math.min(TOP_N, #list) do
                if list[i].grew > 0 then
                    any = true
                    log("    grew +%-6d now %-6d %s", list[i].grew, list[i].n, list[i].id)
                end
            end
            if not any then log("    no reference growth since last count") end
        end
        table.sort(list, function(a, b) return a.n > b.n end)
        for i = 1, math.min(TOP_N, #list) do
            log("    most   %-6d %s", list[i].n, list[i].id)
        end
        lastCounts = counts
        soundSummary()
        blockSummary()
    end)
    if not ok then log("CENSUS failed: %s", tostring(err)) end
end

-- audio ------------------------------------------------------------------------
local soundTally, lastSound = {}, "-"

local function field(fn)
    local ok, v = pcall(fn)
    if ok and v ~= nil then return v end
    return nil
end

local function soundId(e)
    return field(function() return e.sound.id end)
        or field(function() return e.sound.filename end)
        or field(function() return e.path end)
        or field(function() return tostring(e.sound) end)
        or "?"
end

local function describeSound(kind, e, id)
    local ref = field(function() return e.reference.object.id end)
        or field(function() return e.reference.id end) or "-"
    local parts = { kind, id, "on " .. tostring(ref) }
    local vol = field(function() return e.volume end)
    if type(vol) == "number" then parts[#parts + 1] = string.format("vol %.2f", vol) end
    local pitch = field(function() return e.pitch end)
    if type(pitch) == "number" and math.abs(pitch - 1) > 0.001 then
        parts[#parts + 1] = string.format("pitch %.2f", pitch)
    end
    if field(function() return e.loop end) then parts[#parts + 1] = "LOOP" end
    if field(function() return e.isVoiceover end) then parts[#parts + 1] = "voice" end
    local flags = field(function() return e.flags end)
    if flags then parts[#parts + 1] = "flags " .. tostring(flags) end
    return table.concat(parts, "  ")
end

local function flagsLoop(e)
    local fl = field(function() return e.flags end)
    return type(fl) == "number" and fl % 2 == 1 and e.reference ~= nil and e.sound ~= nil
end

local function onSound(kind)
    return function(e)
        if not audioOn() then return end
        local id = soundId(e)
        soundTally[id] = (soundTally[id] or 0) + 1
        lastSound = id
        counters.sounds = (counters.sounds or 0) + 1
        lines.sounds = (lines.sounds or 0) + 1
        if lines.sounds <= (config.soundLines or 40) then
            local line = describeSound(kind, e, id)
            -- for a looping sound on a reference: was it already playing when it was re-added?
            if kind ~= "buffer" and (field(function() return e.loop end) or flagsLoop(e)) then
                local playing = field(function()
                    return tes3.getSoundPlaying({ sound = e.sound, reference = e.reference })
                end)
                line = line .. "  already playing: " .. tostring(playing)
            end
            log("  sound: %s", line)
        end
    end
end

soundSummary = function()
    local list = {}
    for id, n in pairs(soundTally) do list[#list + 1] = { id = id, n = n } end
    if #list == 0 then return end
    table.sort(list, function(a, b) return a.n > b.n end)
    for i = 1, math.min(SOUND_TOP, #list) do
        log("    sound  %-6d %s", list[i].n, list[i].id)
    end
    soundTally = {}
end

-- who blocks sounds -------------------------------------------------------------
-- MWSE keeps event handlers in local tables inside core\lib\event.lua. We reach
-- them through the debug library and wrap each addSound/addTempSound handler so
-- we can see which one blocks a sound. event.register/unregister/isRegistered
-- are patched to translate between a mod's own function and our wrapper, so
-- mods can still unregister their handlers normally.
local generalEvents, filteredEvents, eventPriorities, doOnceCallbacks
do
    local function upvalue(fn, name)
        if type(fn) ~= "function" then return nil end
        for i = 1, 200 do
            local n, v = debug.getupvalue(fn, i)
            if n == nil then return nil end
            if n == name then return v end
        end
    end
    local ok = pcall(function()
        -- mwguard loads first and replaces event.register with its own function, which keeps MWSE's
        -- as the upvalue origRegister: follow that back to the real one
        local register = event.register
        for _ = 1, 8 do
            if upvalue(register, "getEventTable") then break end
            local inner = upvalue(register, "origRegister")
            if type(inner) ~= "function" then break end
            register = inner
        end
        local getEventTable = upvalue(register, "getEventTable")
        generalEvents = upvalue(getEventTable, "generalEvents")
        filteredEvents = upvalue(getEventTable, "filteredEvents")
        eventPriorities = upvalue(register, "eventPriorities")
        doOnceCallbacks = upvalue(register, "doOnceCallbacks")
    end)
    if not (ok and generalEvents and eventPriorities) then generalEvents = nil end
end

local WATCHED = { "addSound", "addTempSound" }
local wrapOf, origOf, ours = {}, {}, {}
local audioStarted = false               -- set by startAudio / stopAudio below
local blockTally = {}

local function sourceOf(fn)
    local info = debug.getinfo(fn, "S")
    if not info then return "?" end
    local src = (info.short_src or info.source or "?"):gsub("^.-[/\\]mods[/\\]", "")
    return string.format("%s:%s", src, tostring(info.linedefined))
end

local function noteBlock(eventType, src, e, claimed)
    local id = soundId(e)
    local key = src .. "  " .. id
    blockTally[key] = (blockTally[key] or 0) + 1
    counters.blocked = (counters.blocked or 0) + 1
    lines.blocked = (lines.blocked or 0) + 1
    if lines.blocked <= EVENT_LINES then
        local ref = field(function() return e.reference.object.id end) or "-"
        log("  BLOCKED by %s: %s %s on %s%s", src, eventType, id, tostring(ref), claimed and " (claimed)" or "")
    end
end

local function wrapList(eventType, list)
    for i, cb in ipairs(list) do
        if not origOf[cb] and not ours[cb] then
            local src = sourceOf(cb)
            local w = function(e)
                local before = e.block
                local r = cb(e)
                if audioOn() and (r ~= nil or (e.block and not before)) then noteBlock(eventType, src, e, r ~= nil) end
                return r
            end
            eventPriorities[w] = eventPriorities[cb] or 0
            wrapOf[cb], origOf[w] = w, cb
            list[i] = w
        end
    end
end

local function wrapAll()
    if not generalEvents or not audioStarted then return end
    for _, et in ipairs(WATCHED) do
        if generalEvents[et] then wrapList(et, generalEvents[et]) end
        if filteredEvents and filteredEvents[et] then
            for _, list in pairs(filteredEvents[et]) do wrapList(et, list) end
        end
    end
end

local function listHandlers()
    if not generalEvents then
        log("(could not reach MWSE's event tables; blocking mods will not be named)")
        return
    end
    for _, et in ipairs(WATCHED) do
        local n = 0
        for _, cb in ipairs(generalEvents[et] or {}) do
            local orig = origOf[cb] or cb
            if not ours[orig] then
                n = n + 1
                log("  %s handler: %s (priority %s)", et, sourceOf(orig), tostring(eventPriorities[cb]))
            end
        end
        for filter, list in pairs((filteredEvents or {})[et] or {}) do
            for _, cb in ipairs(list) do
                n = n + 1
                log("  %s handler [filter %s]: %s", et, tostring(filter), sourceOf(origOf[cb] or cb))
            end
        end
        if n == 0 then log("  %s: no other handlers", et) end
    end
end

-- the audio watch turned off: every handler goes back to the mod's own function, so nothing of ours is left
-- running in a sound event
local function unwrapAll()
    if not generalEvents then return end
    local function unwrapList(list)
        for i, cb in ipairs(list) do
            local orig = origOf[cb]
            if orig then
                list[i] = orig
                eventPriorities[cb] = nil
            end
        end
    end
    for _, et in ipairs(WATCHED) do
        if generalEvents[et] then unwrapList(generalEvents[et]) end
        if filteredEvents and filteredEvents[et] then
            for _, list in pairs(filteredEvents[et]) do unwrapList(list) end
        end
    end
    wrapOf, origOf = {}, {}
end

local unpatchEventFunctions = function() end
local function patchEventFunctions()   -- keep register/unregister/isRegistered working with wrapped handlers
    if not generalEvents then return end
    local realRegister, realUnregister, realIsRegistered = event.register, event.unregister, event.isRegistered
    local function resolve(cb)
        if wrapOf[cb] then return wrapOf[cb] end
        local once = doOnceCallbacks and doOnceCallbacks[cb]   -- doOnce: MWSE stores a replacement function
        if once and wrapOf[once] then return wrapOf[once] end
        return cb
    end
    event.unregister = function(et, cb, opts) return realUnregister(et, resolve(cb), opts) end
    event.isRegistered = function(et, cb, opts) return realIsRegistered(et, resolve(cb), opts) end
    event.register = function(et, cb, opts)
        local w = resolve(cb)
        if w ~= cb and realIsRegistered(et, w, opts) then return end   -- already registered (as our wrapper)
        local r = realRegister(et, cb, opts)
        for _, name in ipairs(WATCHED) do
            if et == name then wrapAll() break end
        end
        return r
    end
    local ourRegister, ourUnregister, ourIsRegistered = event.register, event.unregister, event.isRegistered
    -- put MWSE's (or mwguard's) functions back, unless another mod has replaced ours since: then ours stay,
    -- and with no wrappers left they only pass calls through
    unpatchEventFunctions = function()
        if event.register == ourRegister then event.register = realRegister end
        if event.unregister == ourUnregister then event.unregister = realUnregister end
        if event.isRegistered == ourIsRegistered then event.isRegistered = realIsRegistered end
        unpatchEventFunctions = function() end
    end
end

blockSummary = function()
    local list = {}
    for key, n in pairs(blockTally) do list[#list + 1] = { key = key, n = n } end
    if #list == 0 then return end
    table.sort(list, function(a, b) return a.n > b.n end)
    for i = 1, math.min(SOUND_TOP, #list) do
        log("    blocked %-6d %s", list[i].n, list[i].key)
    end
    blockTally = {}
end

-- frame hook -------------------------------------------------------------------
local function onFrame(e)
    if not watchOn() then return end
    local dt = e.delta or 0
    frames = frames + 1
    if dt > worst then worst = dt end

    if dt > SLOW_FRAME then
        log("SLOW FRAME %.3fs (menuMode=%s)", dt, tostring(e.menuMode))
        if os.clock() - lastCensus > 1 then census("slow frame") end
    end

    local now = os.clock()
    if now - lastSecond >= 1 then
        local extra = {}
        for name, n in pairs(counters) do extra[#extra + 1] = name .. "=" .. n end
        table.sort(extra)
        log("fps %5.1f  worst %.3fs  mem %.0f MB  lua %.0f KB  cell %s  inv %d  last sound %s  %s",
            frames / (now - lastSecond), worst, memMB(), collectgarbage("count"),
            cellName(tes3.player and tes3.player.cell), invCount(), lastSound,
            table.concat(extra, " "))
        frames, worst, lastSecond = 0, 0, now
        counters, lines = {}, {}
    end

    if now - lastCensus >= CENSUS_EVERY then census("periodic") end
end

-- memory monitor ------------------------------------------------------------------
local ADDRESS_SPACE_MB = 4096          -- a 32-bit (4 GB aware) Morrowind can address 4 GB in all
local MEM_REPEAT       = 60            -- seconds between warnings while memory stays over the line
local MEM_TOP          = 10            -- textures listed in the log
local memArmed, memLastWarn, memLastCheck = true, -1e9, -1e9

local lfsOk, lfsLib = pcall(require, "lfs")
if not lfsOk then lfsLib = rawget(_G, "lfs") end

local function texturePath(name)
    local p = string.lower((string.gsub(name, "/", "\\")))
    if string.sub(p, 1, 11) == "data files\\" then return p end
    if string.sub(p, 1, 9) == "textures\\" then return "data files\\" .. p end
    return "data files\\textures\\" .. p
end

local function fileSize(p)                -- bytes on disk, or nil (in a BSA, or not found)
    if not lfsLib then return nil end
    for _, cand in ipairs({ p, (string.gsub(p, "%.%w+$", ".dds")) }) do   -- the game swaps in a .dds
        local ok, s = pcall(lfsLib.attributes, cand, "size")
        if ok and type(s) == "number" then return s end
    end
    return nil
end

local MAP_FIELDS = { "baseMap", "darkMap", "detailMap", "glossMap", "glowMap", "bumpMap" }

local function addTexture(seen, tex)
    local ok, name = pcall(function() return tex.fileName end)
    if not ok or type(name) ~= "string" or name == "" then return end
    local key = string.lower(name)
    local t = seen[key]
    if not t then
        t = { name = name, uses = 0, size = fileSize(texturePath(name)) }
        seen[key] = t
    end
    t.uses = t.uses + 1
end

local function walkNode(node, seen, depth)
    if node == nil or depth > 48 then return end
    local ok, prop = pcall(function() return node:getProperty(ni.propertyType.texturing) end)
    if ok and prop then
        for _, field in ipairs(MAP_FIELDS) do
            local okm, map = pcall(function() return prop[field] end)
            if okm and map then
                local okt, tex = pcall(function() return map.texture end)
                if okt and tex then addTexture(seen, tex) end
            end
        end
    end
    local okc, children = pcall(function() return node.children end)
    if okc and children then
        for i = 1, #children do
            local okn, child = pcall(function() return children[i] end)
            if okn and child then walkNode(child, seen, depth + 1) end
        end
    end
end

local function memOffenders()
    local seen, cells = {}, {}
    local okc, active = pcall(tes3.getActiveCells)
    if okc and active then
        for _, cell in ipairs(active) do
            local n = 0
            local okr = pcall(function()
                for ref in cell:iterateReferences() do
                    n = n + 1
                    local oks, node = pcall(function() return ref.sceneNode end)
                    if oks and node then walkNode(node, seen, 0) end
                end
            end)
            cells[#cells + 1] = { name = cellName(cell), refs = n, ok = okr }
        end
    end
    if tes3.player then
        local oks, node = pcall(function() return tes3.player.sceneNode end)
        if oks and node then walkNode(node, seen, 0) end
    end
    local list, folders, total, unknown = {}, {}, 0, 0
    for _, t in pairs(seen) do
        list[#list + 1] = t
        if t.size then
            total = total + t.size
            local rel = string.match(string.lower(texturePath(t.name)), "^data files\\textures\\(.*)$") or t.name
            local folder = string.match(rel, "^([^\\]+)\\") or "(Textures folder itself)"
            folders[folder] = (folders[folder] or 0) + t.size
        else
            unknown = unknown + 1
        end
    end
    table.sort(list, function(a, b) return (a.size or -1) > (b.size or -1) end)
    local flist = {}
    for name, size in pairs(folders) do flist[#flist + 1] = { name = name, size = size } end
    table.sort(flist, function(a, b) return a.size > b.size end)
    table.sort(cells, function(a, b) return a.refs > b.refs end)
    return list, flist, cells, total, unknown
end

local MEM_TOAST_SECONDS = 8            -- how long the on-screen notice stays up

local function memWarning(mb, pct)
    -- 1. a toast, not a modal: a message box with buttons enters menu mode, and one that alt-tab hides (or
    --    that comes back every minute) left the cursor stuck as if a menu were open. A toast has no buttons,
    --    takes no input and goes away by itself.
    pcall(tes3.playSound, { sound = "Health Damage" })
    local text = string.format("mwhangwatch: memory at %.0f%% (%.2f of %.2f GB). Save soon: a 32-bit "
        .. "Morrowind crashes when it runs out.", pct, mb / 1024, ADDRESS_SPACE_MB / 1024)
    if not pcall(tes3.messageBox, { message = text, duration = MEM_TOAST_SECONDS }) then
        pcall(tes3.messageBox, text)
    end
    -- the same, as one line in MWSE.log, so a late session at the limit still shows in MWSE.log
    pcall(mwse.log, "[mwhangwatch] MEMORY WARNING: %.0f%% used (%.0f of %d MB). Details: MWSE\\logs\\mwhangwatch.log",
        pct, mb, ADDRESS_SPACE_MB)

    -- 2. Safely log detailed diagnostics to mwhangwatch.log in protected call
    pcall(function()
        openLog()
        local list, flist, cells, total, unknown = memOffenders()
        log("MEMORY WARNING: %.0f%% used (%.0f of %d MB). A 32-bit Morrowind crashes when it runs out.",
            pct, mb, ADDRESS_SPACE_MB)
        log("  textures of everything in the loaded cells: %d, %.0f MB on disk (%d more are in BSAs, size unknown)",
            #list, total / 1048576, unknown)
        for i = 1, math.min(MEM_TOP, #list) do
            local t = list[i]
            if not t.size then break end
            log("    %6.1f MB  x%-4d %s", t.size / 1048576, t.uses, t.name)
        end
        log("  by texture folder (usually a texture pack):")
        for i = 1, math.min(8, #flist) do
            log("    %6.0f MB  %s", flist[i].size / 1048576, flist[i].name)
        end
        log("  loaded cells by number of objects:")
        for i = 1, math.min(6, #cells) do
            log("    %6d  %s", cells[i].refs, cells[i].name)
        end
        log("  lua %.0f KB. The rest of the memory is the engine, MGE XE (distant land) and DXVK, which a mod "
            .. "can't see into.", collectgarbage("count"))
    end)
end

local function memCheck()
    if not config.memWarn then return end
    local now = os.time()
    if now - memLastCheck < 1 then return end            -- once a second is plenty
    memLastCheck = now
    local mb = memMB()
    if mb < 0 then return end
    local pct = mb / ADDRESS_SPACE_MB * 100
    local limit = config.memLimit or 80
    if pct < limit - 3 then                              -- well below again: warn afresh next time
        memArmed = true
        return
    end
    if pct < limit then return end
    if not memArmed and now - memLastWarn < MEM_REPEAT then return end
    memArmed, memLastWarn = false, now
    memWarning(mb, pct)
end

-- event hooks --------------------------------------------------------------------
-- each group's handlers are remembered, so turning the watch or the audio watch off unregisters them
local watchRegs, audioRegs = {}, {}
local function reg(name, fn, group)
    local ev = tes3.event[name]
    if ev then
        event.register(ev, fn)
        if group then group[#group + 1] = { ev, fn } end
    else
        log("(event %s not available in this MWSE)", name)
    end
end
local function unregAll(group)
    for i = #group, 1, -1 do
        local r = group[i]
        if not event.isRegistered or event.isRegistered(r[1], r[2]) then event.unregister(r[1], r[2]) end
        group[i] = nil
    end
end

local function guarded(fn)            -- run only while the watch is on
    return function(e) if watchOn() then return fn(e) end end
end


-- now playing: sounds already running (loops start when a cell loads, before the audio watch can see
-- them). Checks every sound against the player and every object within NOW_RANGE, spread over frames.
local NOW_RANGE, NOW_PER_FRAME = 4000, 12000
local nowScan, onNowScanFrame
local function startNowPlaying(reason)
    if not tes3.player then return end
    local sounds = {}
    for snd in tes3.iterateObjects(tes3.objectType.sound) do sounds[#sounds + 1] = snd end
    local p, refs = tes3.player.position, {}
    for _, cell in ipairs(tes3.getActiveCells()) do
        for r in cell:iterateReferences() do
            if r ~= tes3.player and not r.disabled and not r.deleted and r.position:distance(p) < NOW_RANGE then
                refs[#refs + 1] = r
            end
        end
    end
    table.sort(refs, function(a, b) return a.position:distance(p) < b.position:distance(p) end)
    table.insert(refs, 1, tes3.player)
    nowScan = { sounds = sounds, refs = refs, i = 1, found = 0, from = p:copy(), query = {} }
    log("NOW PLAYING (%s): checking %d sounds on you and %d objects within %d units",
        reason, #sounds, #refs - 1, NOW_RANGE)
    event.unregister(tes3.event.enterFrame, onNowScanFrame)
    event.register(tes3.event.enterFrame, onNowScanFrame)
end

local function stepNowPlaying()
    local sc = nowScan
    if not sc then return end
    local budget = NOW_PER_FRAME
    local q = sc.query                       -- one params table for every check (no garbage per call)
    while budget > 0 and sc.i <= #sc.refs do
        local r = sc.refs[sc.i]
        sc.i = sc.i + 1
        budget = budget - #sc.sounds
        if r and r.object then
            for _, snd in ipairs(sc.sounds) do
                q.sound, q.reference = snd, r
                local ok, on = pcall(tes3.getSoundPlaying, q)
                if ok and on then
                    sc.found = sc.found + 1
                    local pos = r.position
                    log("  playing: %-28s %-45s on %s (%s, defined by %s) %d units away at %d, %d, %d",
                        snd.id, tostring(snd.filename), r.object.id, tostring(r.object.objectType and
                        table.find(tes3.objectType, r.object.objectType) or "?"),
                        tostring(r.object.sourceMod or "?"), pos:distance(sc.from), pos.x, pos.y, pos.z)
                end
            end
        end
    end
    if sc.i > #sc.refs then
        log("NOW PLAYING done: %d sound(s) playing", sc.found)
        nowScan = nil
    end
end

onNowScanFrame = function()
    if nowScan then
        pcall(stepNowPlaying)
    end
    if not nowScan then
        event.unregister(tes3.event.enterFrame, onNowScanFrame)
    end
end

local watchStarted = false

local function startWatch()
    if watchStarted then return end
    watchStarted = true
    openLog()
    log("mwhangwatch started; MWSE build %s", tostring(mwse.buildNumber or mwse.version or "?"))

    reg("loaded", guarded(function(e)
        log("LOADED newGame=%s file=%s", tostring(e.newGame), tostring(e.filename))
        if audioStarted then wrapAll() if audioOn() then listHandlers() end end
        lastCounts = nil
        census("after load")
    end), watchRegs)

    reg("cellChanged", guarded(function(e)
        log("CELL %s -> %s", cellName(e.previousCell), cellName(e.cell))
        census("cell change")
        if audioOn() then
            timer.start({ type = timer.real, duration = 2, callback = function() startNowPlaying("cell change") end })
        end
    end), watchRegs)

    reg("referenceActivated", guarded(function(e)
        if bump("refsActivated") then
            local r = e.reference
            log("  ref active: %s (%s)", r and r.object and r.object.id or "?", r and cellName(r.cell) or "-")
        end
    end), watchRegs)

    reg("mobileActivated", guarded(function(e)
        if bump("actorsActivated") then
            local r = e.reference
            log("  actor active: %s", r and r.object and r.object.id or "?")
        end
    end), watchRegs)

    reg("uiActivated", guarded(function(e)
        if bump("menus") then
            log("  menu: %s", e.element and e.element.name or "?")
        end
    end), watchRegs)

    reg("startGlobalScript", guarded(function(e)
        if bump("startScript") then
            local s = e.script
            log("  StartScript %s", s and (s.id or tostring(s)) or "?")
        end
    end), watchRegs)

    reg("enterFrame", onFrame, watchRegs)
end

local function startAudio()
    if audioStarted then return end
    audioStarted = true
    local onRef, onTemp = onSound("ref"), onSound("temp")
    ours[onRef], ours[onTemp] = true, true
    patchEventFunctions()
    event.register(tes3.event.addSound, onRef, { priority = 1000000000 })      -- first: see every request
    event.register(tes3.event.addTempSound, onTemp, { priority = 1000000000 })
    audioRegs[#audioRegs + 1] = { tes3.event.addSound, onRef }
    audioRegs[#audioRegs + 1] = { tes3.event.addTempSound, onTemp }
    reg("soundObjectPlay", onSound("buffer"), audioRegs)

    reg("musicSelectTrack", function(e)
        if not audioOn() then return end
        log("  music: selecting track (situation %s)", tostring(field(function() return e.situation end)))
    end, audioRegs)

    reg("musicChangeTrack", function(e)
        if not audioOn() then return end
        log("  music: now playing %s", tostring(field(function() return e.music end)
            or field(function() return e.path end) or "?"))
    end, audioRegs)
    wrapAll()
end

-- off really is off: no handler of ours stays registered, no mod's sound handler stays wrapped
local function stopAudio()
    if not audioStarted then return end
    audioStarted = false
    unregAll(audioRegs)
    unwrapAll()
    unpatchEventFunctions()
    for k in pairs(ours) do ours[k] = nil end
end

local function stopWatch()
    if not watchStarted then return end
    watchStarted = false
    unregAll(watchRegs)
    nowScan = nil
    if event.isRegistered(tes3.event.enterFrame, onNowScanFrame) then
        event.unregister(tes3.event.enterFrame, onNowScanFrame)
    end
end

-- apply the settings (at startup and whenever they change in the Mod Config menu)
local appliedWatch, appliedAudio
local function applySettings()
    local w, a = watchOn() and true or false, audioOn() and true or false
    if w ~= appliedWatch then
        if w then
            startWatch()
            frames, worst, lastSecond = 0, 0, os.clock()
            counters, lines = {}, {}
            if appliedWatch ~= nil then log("watch enabled") end
            if tes3.player then census("watch enabled") end
        elseif appliedWatch ~= nil then
            log("watch disabled")
            stopWatch()
        end
        appliedWatch = w
    end
    if a ~= appliedAudio then
        if a then
            startAudio()
            log("audio watch on (up to %d sound lines per second)", config.soundLines or 40)
            listHandlers()
            if tes3.player then startNowPlaying("audio watch turned on") end
        elseif appliedAudio ~= nil then
            if audioStarted then log("audio watch off") end
            stopAudio()
        end
        appliedAudio = a
    end
end

event.register(tes3.event.initialized, applySettings)
-- the memory check has its own 1.0s timer, so it works with the rest of the watch turned off without per-frame overhead
-- MWSE cancels every timer just before `loaded`, so it is started again there
local memTimer = nil
local function startMemCheck()
    if memTimer then
        pcall(function() memTimer:cancel() end)
        memTimer = nil
    end
    if not config.memWarn then return end        -- opt-in: nothing runs until the warning is turned on
    memTimer = timer.start({
        type = timer.real,
        duration = 1.0,
        iterations = -1,
        callback = function() pcall(memCheck) end,
    })
end
startMemCheck()
event.register(tes3.event.loaded, startMemCheck)


-- Settings for the shared "Guard & Hang Watch" MCM (registered by mwguard).
local hooks = include("mwhangwatch.mcm")
if hooks then
    hooks.config = config
    hooks.applySettings = applySettings
    hooks.startMemCheck = startMemCheck
end
