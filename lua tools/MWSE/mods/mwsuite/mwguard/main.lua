--[[
    mwguard (Passive Profiler & Issue Logger)

    Passively observes and profiles MWSE Lua mods to identify performance bottlenecks
    and bad practices WITHOUT intercepting, throttling, or altering other mods.

    1. Extreme Priorities:
       Notices and logs when any mod registers an event handler with |priority| >= priorityLimit
       (naming the mod, file, line, and priority). Priorities are NOT clamped or modified.
    2. Per-Frame Handler Profiling:
       Times per-frame handlers (simulate, simulated, enterFrame) at a lightweight sample rate
       (1 out of every sampleEvery frames) using microsecond-resolution hardware counters.
       Other mods' handlers run at full speed every single frame—no frames are ever skipped,
       and event data is never altered.
    3. Performance Reports & Issue Notices:
       Every reportSeconds, handlers taking over costMs (default 0.75 ms average) are logged
       to MWSE.log as notices. A complete ranked breakdown of all top per-frame consumers is
       written to Data Files\MWSE\logs\mwguard.log.
    4. Non-Intrusive Logging:
       Other mods' logs and error tracebacks remain in MWSE.log.
    5. Timestamps on MWSE.log (EnableLogTimestamps, off by default):
       MWSE 2.1 has no timestamp setting for MWSE.log, so when this is on, global print and mwse.log are
       wrapped once, as mwguard loads (before other mods). The style is logTimestampMode (default
       "wallclock"): wall clock ("[17:42:33] ") or "elapsed" whole seconds since start ("[000042] ",
       six digits; the width stays fixed until 999999 s, about 11.5 days, then the number grows).
       Nothing else about a line changes. The Mod Config menu is "Guard & Hang Watch", shared with
       mwhangwatch.
]]

local CONFIG_NAME = "mwguard"
local defaults = {
    enabled = false,
    priorityLimit = 10000,
    sampleEvery = 8,             -- time 1 call in every N (statistically accurate, near-zero overhead)
    reportSeconds = 30,          -- interval between reports (seconds)
    reportTop = 10,              -- top N consumers written to mwguard.log
    costMs = 0.75,               -- average ms per call to flag as a bottleneck
    logNoticeToMWSE = true,      -- output summary notices of costly handlers to MWSE.log
    showAddressSpace = true,     -- on-screen address-space percentage, profiling on or off
    EnableLogTimestamps = false, -- prefix every MWSE.log line (style: logTimestampMode)
    logTimestampMode = "wallclock", -- "wallclock" ([17:42:33]) or "elapsed" ([000042] since start)
    exemptMods = {
        "mwguard", "mwcriminal", "mwcompanions", "mwhangwatch", "mwfloatfix", "mwstranded", "mwcollide",
        "mwperformers", "mwinfoloop", "mwsoundguard", "mwsoundfix", "mwsaveguard", "mwwarnsuppression",
        "mwpersonaleffects", "mwpluginpatches", "mwconsole", "mwmouseguard",
        "mwteleportguard", "mwexitguard", "mwcustomclasspersistence", "mwquicktoggle"
    },
    perFrameHints = {
        "e%.delta", "camera", "velocity", "orientation", "position%s*=", "rotation", "animat",
        "drag", "mouse", "lerp", "smooth", "interpolat", "fade", "tes3ui", "menu", "controls",
        "keybind", "inputcontroller", "positioncell"
    },
}

local config = mwse.loadConfig(CONFIG_NAME, defaults)

-- timestamps on MWSE.log: wrap print and mwse.log once, before other mods load (mwguard's load priority), so
-- their lines (and the luafix log shim's, which forwards through the print it finds) carry the time too
local function installLogTimestamps()
    if config.EnableLogTimestamps ~= true or rawget(_G, "__mwsuite_log_timestamps") then return end
    local origPrint = print
    if type(origPrint) ~= "function" then return end
    rawset(_G, "__mwsuite_log_timestamps", true)
    local select, tostring, concat, format, date, time = select, tostring, table.concat, string.format, os.date, os.time
    local logStart = time()
    local function stamp()
        if config.logTimestampMode == "elapsed" then
            return format("[%06d] ", math.max(0, time() - logStart))
        end
        return date("[%H:%M:%S] ")
    end
    print = function(...)
        local n = select("#", ...)
        local body
        if n <= 1 then
            body = tostring((...))
        else
            local t = {}
            for i = 1, n do t[i] = tostring((select(i, ...))) end
            body = concat(t, "\t")
        end
        return origPrint(stamp() .. body)
    end
    mwse.log = function(fmt, ...)
        local ok, msg = pcall(format, tostring(fmt), ...)
        return origPrint(stamp() .. (ok and msg or tostring(fmt)))
    end
end
pcall(installLogTimestamps)
-- read once: off at start-up means no hooks at all (switching it on takes effect after a restart)
local active = config.enabled == true
if not active then
    mwse.log("[mwguard] profiling is off (MWSE\\config\\mwguard.json): no handlers are wrapped. The Mod Config "
        .. "menu can turn it on (after a restart).")
end

local interop = include("mwguard.interop") or {
    isExempt = function() return false end, exemptMods = {}, exemptFunctions = {},
}

-- logging ----------------------------------------------------------------------------------------
local LOG_DIR = "Data Files\\MWSE\\logs"
local function origLog(fmt, ...)
    local ok, s = pcall(string.format, fmt, ...)
    print(ok and s or tostring(fmt))
end

local logFile
local function flog(fmt, ...)
    if not logFile then
        pcall(function() lfs.mkdir(LOG_DIR) end)
        logFile = io.open(LOG_DIR .. "\\mwguard.log", "w")
        if not logFile then return end
        logFile:write(os.date("mwguard profiler session started %Y-%m-%d %H:%M:%S\n"))
    end
    local ok, s = pcall(string.format, fmt, ...)
    logFile:write(os.date("[%H:%M:%S] "), ok and s or tostring(fmt), "\n")
    logFile:flush()
end
if active then
    flog("mwguard started in passive profiling mode (MWSE build %s)", tostring(mwse.buildNumber or "?"))
    mwse.log("[mwguard] Initialized first (load priority 1000000): passive profiler and event monitor active.")
end

-- microsecond clock ------------------------------------------------------------------------------
local now = os.clock
do
    local ok = pcall(function()
        local ffi = require("ffi")
        ffi.cdef([[
            int QueryPerformanceCounter(int64_t *count);
            int QueryPerformanceFrequency(int64_t *freq);
        ]])
        local buf = ffi.new("int64_t[1]")
        ffi.C.QueryPerformanceFrequency(buf)
        local freq = tonumber(buf[0])
        if not freq or freq <= 0 then error("no performance counter") end
        now = function()
            ffi.C.QueryPerformanceCounter(buf)
            return tonumber(buf[0]) / freq
        end
    end)
    if not ok then flog("high resolution clock not available: using os.clock (1 ms steps)") end
end

-- source attribution -----------------------------------------------------------------------------
local modDirHasMain = {}
local sourceCache = {}
local function modOfSource(source)
    local cached = sourceCache[source]
    if cached ~= nil then return cached or nil end
    local src = source:gsub("^@", ""):gsub("/", "\\")
    local i = src:lower():find("\\mwse\\mods\\", 1, true)
    if not i then
        sourceCache[source] = false
        return nil
    end
    local rel = src:sub(i + #"\\mwse\\mods\\")
    local parts = {}
    for p in rel:gmatch("[^\\]+") do parts[#parts + 1] = p end
    local mod = parts[1] or "?"
    if #parts >= 3 then
        local dir = src:sub(1, i - 1) .. "\\MWSE\\mods\\" .. mod
        if modDirHasMain[dir] == nil then
            modDirHasMain[dir] = lfs.fileexists(dir .. "\\main.lua") and true or false
        end
        if mod:lower() == "mwsuite" or not modDirHasMain[dir] then mod = mod .. "/" .. parts[2] end
    end
    local m = { mod = mod, low = mod:lower(), file = rel, path = src }
    sourceCache[source] = m
    return m
end

local originCache = setmetatable({}, { __mode = "k" })
local function origin(fn)
    local cached = originCache[fn]
    if cached ~= nil then return cached or nil end
    local info = debug.getinfo(fn, "S")
    local m = modOfSource(info and info.source or "")
    if not m then
        originCache[fn] = false
        return nil
    end
    local w = {
        mod = m.mod, low = m.low, file = m.file, path = m.path,
        first = info.linedefined or 0, last = info.lastlinedefined or 0
    }
    w.where = string.format("%s:%d", w.file, w.first)
    originCache[fn] = w
    return w
end

local exemptList = {}
for _, m in ipairs(config.exemptMods or {}) do exemptList[tostring(m):lower()] = true end
local function exempt(w, fn)
    local suiteMod = w.low:match("^mwsuite/([^/]+)")
    if suiteMod and exemptList[suiteMod] then return true end
    if exemptList[w.low] or exemptList[w.low:match("^([^/]+)/") or ""] then return true end
    return interop.isExempt(w.mod, fn)
end

-- per-frame hints (informative annotation only) --------------------------------------------------
local function perFrameHint(w)
    local f = io.open(w.path, "r")
    if not f then return "source not readable" end
    local lines, n = {}, 0
    local first, last = math.max(1, w.first), math.max(w.first, w.last)
    for line in f:lines() do
        n = n + 1
        if n >= first and n <= last then
            lines[#lines + 1] = line
        end
        if n >= first and n >= last then break end
    end
    f:close()
    if n == 0 then return "source not readable" end
    local body = table.concat(lines, "\n"):lower()
    for _, pat in ipairs(config.perFrameHints or {}) do
        local ok, found = pcall(string.find, body, pat)
        if ok and found then return pat end
    end
    return nil
end

-- 1. extreme priorities observation --------------------------------------------------------------
local extremes = {} -- "event|sign" -> { [mod] = priority }
local function checkPriority(eventType, options, w)
    if not config.enabled then return options end
    local p = options and options.priority
    if type(p) ~= "number" or math.abs(p) < (config.priorityLimit or 10000) then return options end
    local k = eventType .. (p > 0 and "|+" or "|-")
    extremes[k] = extremes[k] or {}
    extremes[k][w and w.mod or "?"] = p
    flog("PRIORITY %-28s %-40s %s priority %d", w and w.mod or "?", w and w.where or "?", eventType, p)
    return options -- NEVER clamp: return original options unchanged
end

-- 2. passive per-frame profiling -----------------------------------------------------------------
local PER_FRAME = { simulate = true, simulated = true, enterFrame = true }
local stats = {}
local wrappers = {}
for et in pairs(PER_FRAME) do wrappers[et] = setmetatable({}, { __mode = "k" }) end

local function makeWrapper(eventType, callback, w)
    local st = {
        event = eventType, w = w, calls = 0, sampled = 0, time = 0, peak = 0,
        hint = perFrameHint(w)
    }
    local wrapper
    wrapper = function(e)
        if not config.enabled then
            return callback(e)
        end
        st.calls = st.calls + 1
        local every = config.sampleEvery or 8
        if every < 1 then every = 1 end
        if st.calls % every ~= 0 then
            return callback(e)
        end
        local t0 = now()
        local r = callback(e)
        local dt = now() - t0
        st.sampled = st.sampled + 1
        st.time = st.time + dt
        if dt > st.peak then st.peak = dt end
        return r
    end
    stats[wrapper] = st
    return wrapper
end

local origRegister, origUnregister, origIsRegistered = event.register, event.unregister, event.isRegistered

if active then
    event.register = function(eventType, callback, options)
        if type(callback) ~= "function" or type(eventType) ~= "string" then
            return origRegister(eventType, callback, options)
        end
        local w = origin(callback)
        if not w or exempt(w, callback) then return origRegister(eventType, callback, options) end
        checkPriority(eventType, options, w)
        if not PER_FRAME[eventType]
            or (options and (options.doOnce or options.filter ~= nil or options.unregisterOnLoad)) then
            return origRegister(eventType, callback, options)
        end
        local byCb = wrappers[eventType]
        local wrapper = byCb[callback]
        if not wrapper then
            wrapper = makeWrapper(eventType, callback, w)
            byCb[callback] = wrapper
        end
        return origRegister(eventType, wrapper, options)
    end

    event.unregister = function(eventType, callback, options)
        local byCb = wrappers[eventType]
        local wrapper = byCb and type(callback) == "function" and byCb[callback]
        if wrapper then
            origUnregister(eventType, wrapper, options)
            if origIsRegistered(eventType, callback, options) then
                origUnregister(eventType, callback, options)
            end
            -- release it: the wrapper holds the callback, so the weak key alone never lets either go (LuaJIT)
            if not origIsRegistered(eventType, wrapper) then
                byCb[callback] = nil
                stats[wrapper] = nil
            end
            return
        end
        return origUnregister(eventType, callback, options)
    end

    event.isRegistered = function(eventType, callback, options)
        local byCb = wrappers[eventType]
        local wrapper = byCb and type(callback) == "function" and byCb[callback]
        if wrapper and origIsRegistered(eventType, wrapper, options) then return true end
        return origIsRegistered(eventType, callback, options)
    end
end

-- 3. periodic performance reports ----------------------------------------------------------------
local function report()
    if not config.enabled then return end
    local list = {}
    for _, st in pairs(stats) do
        if st.sampled > 0 then
            st.avg = (st.time / st.sampled) * 1000 -- in ms
            st.totalEstimatedMs = st.avg * st.calls
            list[#list + 1] = st
        end
    end
    table.sort(list, function(a, b) return a.totalEstimatedMs > b.totalEstimatedMs end)

    local notices = {}
    local threshold = config.costMs or 0.75
    for i, st in ipairs(list) do
        local isCostly = st.avg >= threshold
        if isCostly then
            notices[#notices + 1] = string.format("%s (%s, avg %.2f ms)", st.w.mod, st.event, st.avg)
        end
        if i <= (config.reportTop or 10) or isCostly then
            flog("PERF %-26s %-10s %-38s avg %6.3f ms | peak %6.2f ms | calls %5d | est %6.1f ms%s%s",
                st.w.mod, st.event, st.w.where, st.avg, st.peak * 1000, st.calls, st.totalEstimatedMs,
                isCostly and " [HIGH CPU]" or "",
                st.hint and (" (hint: '" .. st.hint .. "')") or "")
        end
        st.calls, st.sampled, st.time, st.peak = 0, 0, 0, 0
    end

    if #notices > 0 and config.logNoticeToMWSE then
        origLog("[mwguard] NOTICE: %d costly per-frame handler(s) (> %.2f ms): %s (details in MWSE\\logs\\mwguard.log)",
            #notices, threshold, table.concat(notices, ", "))
    end
end

local function priorityReport()
    for k, mods in pairs(extremes) do
        local n, names = 0, {}
        for m, p in pairs(mods) do
            n = n + 1
            names[#names + 1] = string.format("%s (%d)", m, p)
        end
        table.sort(names)
        origLog("[mwguard] NOTICE: %d mod(s) use extreme priority on %s: %s",
            n, k:gsub("|", " "), table.concat(names, ", "))
    end
end

local function startReportTimer()
    if not active then return end
    timer.start({
        type = timer.real,
        duration = config.reportSeconds or 30,
        iterations = -1,
        persist = false,
        callback = report
    })
end
-- MWSE cancels every timer right before `loaded`, so the one from `initialized` only covers the main menu
origRegister(tes3.event.loaded, startReportTimer)

origRegister(tes3.event.initialized, function()
    priorityReport()
    startReportTimer()
    if active then
        local n = 0
        for _ in pairs(stats) do n = n + 1 end
        origLog("[mwguard] active as passive profiler (measuring %d handlers; details in MWSE\\logs\\mwguard.log)", n)
    end
end, { priority = -100000 })

-- address-space readout (shown whether or not profiling is on) ----------------------------------
local HUD_MENU_ID = tes3ui.registerID("mwguard:addressSpaceMenu")
local HUD_ID = tes3ui.registerID("mwguard:addressSpace")
local hudTimer
local hudErrLogged = false

local function getHudMenu()
    return tes3ui.findHelpLayerMenu(HUD_MENU_ID)
end

local function updateHud()
    local menu = getHudMenu()
    if config.showAddressSpace == false then
        if menu then menu:destroy() end
        return
    end
    if not interop.addressSpace then return end
    local used, total = interop.addressSpace()
    if not used or not total or total <= 0 then return end
    local text = string.format("%.0f", used / total * 100)
    if not menu then
        local created = tes3ui.createHelpLayerMenu({ id = HUD_MENU_ID })
        menu = getHudMenu() or created
        if not menu then return end
        menu.autoWidth = true
        menu.autoHeight = true
        menu.absolutePosAlignX = 0.99
        menu.absolutePosAlignY = 0.01
        menu.consumeMouseEvents = false
    end
    local label = menu:findChild(HUD_ID)
    if not label then
        label = menu:createLabel({ id = HUD_ID })
        label.consumeMouseEvents = false
    elseif label.text == text then
        return
    end
    label.text = text
    menu:updateLayout()
end

local function safeUpdateHud()
    local ok, err = pcall(updateHud)
    if not ok and not hudErrLogged then
        hudErrLogged = true
        mwse.log("[mwguard] address-space HUD error: %s", tostring(err))
    end
end

local function startHudTimer()
    if hudTimer then
        pcall(function() hudTimer:cancel() end)
        hudTimer = nil
    end
    hudTimer = timer.start({ type = timer.real, duration = 1, iterations = -1, callback = safeUpdateHud })
    safeUpdateHud()
end

origRegister(tes3.event.initialized, startHudTimer)
origRegister(tes3.event.loaded, startHudTimer)          -- MWSE cancels every timer right before `loaded`
origRegister(tes3.event.uiActivated, safeUpdateHud, { filter = "MenuMulti" })

-- Mod Config Menu: one "Guard & Hang Watch" entry, shared with mwhangwatch --------------------
event.register(tes3.event.modConfigReady, function()
    local hang = include("mwhangwatch.mcm")
    local template = mwse.mcm.createTemplate({ name = "Guard & Hang Watch" })
    template.onClose = function()
        mwse.saveConfig(CONFIG_NAME, config)
        if hang and hang.config then
            mwse.saveConfig("mwhangwatch", hang.config)
            if hang.applySettings then hang.applySettings() end
            if hang.startMemCheck then hang.startMemCheck() end
        end
    end

    local page1 = template:createSideBarPage({
        label = "Memory & Hang Log",
        description = "Memory tools show how full Morrowind's 4 GB limit is, and can warn you before a crash. "
            .. "The hang log writes what the game is doing to Data Files\\MWSE\\logs\\mwhangwatch.log, "
            .. "so a freeze, slowdown or sound problem can be tracked down.\n\n"
            .. "Memory tools work even with the hang log off. Hang log changes apply right away. "
            .. "The hang log starts fresh each time the game starts.",
    })
    local memory = page1:createCategory("Memory")
    memory:createOnOffButton({
        label = "Show address space on screen",
        description = "Shows a small number in the top-right corner: how full Morrowind's 4 GB memory limit is, in "
            .. "percent. The game crashes near 100%, so save and restart when it gets high. Works even with the "
            .. "profiler and the hang log off.",
        variable = mwse.mcm.createTableVariable({ id = "showAddressSpace", table = config }),
    })
    if hang and hang.addMemoryWarning and hang.config then
        hang.addMemoryWarning(memory)
    end
    if hang and hang.addHangLog and hang.config then
        hang.addHangLog(page1)
    end

    local page2 = template:createSideBarPage({
        label = "Lua Profiler",
        description = "The Lua profiler measures how much time other Lua mods take every frame and writes the "
            .. "slowest ones to MWSE\\logs\\mwguard.log, so you can find a mod that slows the game down. "
            .. "It only watches: it never changes or slows down other mods.\n\n"
            .. "Turn the profiler on and restart the game; turning it off stops the reports right away. "
            .. "While it is off at start-up, no handlers are wrapped.",
    })
    page2:createOnOffButton({
        label = "Enable Passive Profiler",
        description = "Turns the performance monitor on. Restart the game after turning it on; turning it off stops "
            .. "the reports right away. While it is off at start-up, no handlers are wrapped.",
        variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
    })
    page2:createSlider({
        label = "Flag handlers taking more than (ms)",
        description = "A mod that takes longer than this each frame, on average, is marked as slow in the log. Lower it "
            .. "to catch smaller slowdowns.",
        min = 0.25, max = 5.0, step = 0.25, decimalPlaces = 2,
        variable = mwse.mcm.createTableVariable({ id = "costMs", table = config }),
    })
    page2:createSlider({
        label = "Report interval (seconds)",
        description = "How often a new report is written to MWSE\\logs\\mwguard.log.",
        min = 10, max = 120, step = 5,
        variable = mwse.mcm.createTableVariable({ id = "reportSeconds", table = config }),
    })
    page2:createSlider({
        label = "Sample rate (1 in N frames)",
        description = "Only 1 frame in this many is timed, so the monitor itself doesn't slow the game. 8 is accurate "
            .. "enough; 1 times every frame.",
        min = 1, max = 32, step = 1,
        variable = mwse.mcm.createTableVariable({ id = "sampleEvery", table = config }),
    })
    page2:createOnOffButton({
        label = "Output notices to MWSE.log",
        description = "Also writes a short note to MWSE.log whenever a slow mod is found.",
        variable = mwse.mcm.createTableVariable({ id = "logNoticeToMWSE", table = config }),
    })
    page2:createOnOffButton({
        label = "Enable timestamps",
        description = "Prefixes every MWSE.log line with a timestamp. Off until you turn it on. Restart the game "
            .. "after turning this on or off.\n\n"
            .. "The style is set below: wall clock ([17:42:33]) or whole seconds since launch ([000042]).",
        variable = mwse.mcm.createTableVariable({ id = "EnableLogTimestamps", table = config }),
    })
    page2:createDropdown({
        label = "Timestamp style",
        description = "Wall clock writes the time of day, as [17:42:33]. Seconds since launch writes whole seconds "
            .. "since the game started, zero-padded to six digits ([000042]); the width stays fixed until "
            .. "999999 seconds (about 11.5 days), then the number grows.\n\n"
            .. "If timestamps are already on, a change of style applies to the next log line. Turning timestamps "
            .. "on or off still needs a restart.",
        options = {
            { label = "Wall clock", value = "wallclock" },
            { label = "Seconds since launch", value = "elapsed" },
        },
        variable = mwse.mcm.createTableVariable({ id = "logTimestampMode", table = config }),
    })
    template:register()
end)
