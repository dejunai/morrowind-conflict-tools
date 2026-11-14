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
       Global print is left untouched. Other mods' logs and error tracebacks remain in MWSE.log.
]]

local CONFIG_NAME = "mwguard"
local defaults = {
    enabled = true,
    priorityLimit = 10000,
    sampleEvery = 8,             -- time 1 call in every N (statistically accurate, near-zero overhead)
    reportSeconds = 30,          -- interval between reports (seconds)
    reportTop = 10,              -- top N consumers written to mwguard.log
    costMs = 0.75,               -- average ms per call to flag as a bottleneck
    logNoticeToMWSE = true,      -- output summary notices of costly handlers to MWSE.log
    exemptMods = {
        "mwguard", "mwhangwatch", "mwfloatfix", "mwstranded", "mwcollide",
        "mwperformers", "mwinfoloop", "mwsoundguard"
    },
    perFrameHints = {
        "e%.delta", "camera", "velocity", "orientation", "position%s*=", "rotation", "animat",
        "drag", "mouse", "lerp", "smooth", "interpolat", "fade", "tes3ui", "menu", "controls",
        "keybind", "inputcontroller", "positioncell"
    },
}

local config = mwse.loadConfig(CONFIG_NAME, defaults)
if not config.enabled then
    mwse.log("[mwguard] profiling is off (MWSE\\config\\mwguard.json). The Mod Config menu can turn it on.")
end

local interop = include("mwguard.interop") or {
    isExempt = function() return false end, exemptMods = {}, exemptFunctions = {},
}

-- logging ----------------------------------------------------------------------------------------
local function origLog(fmt, ...)
    local ok, s = pcall(string.format, fmt, ...)
    print(ok and s or tostring(fmt))
end

local LOG_DIR = "Data Files\\MWSE\\logs"
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
flog("mwguard started in passive profiling mode (MWSE build %s)", tostring(mwse.buildNumber or "?"))

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
        if not modDirHasMain[dir] then mod = mod .. "/" .. parts[2] end
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
    if exemptList[w.low] or exemptList[w.low:match("^([^/]+)/") or ""] then return true end
    return interop.isExempt(w.mod, fn)
end

-- per-frame hints (informative annotation only) --------------------------------------------------
local fileLines = {}
local function perFrameHint(w)
    local lines = fileLines[w.path]
    if lines == nil then
        lines = {}
        local f = io.open(w.path, "r")
        if f then
            for l in f:lines() do lines[#lines + 1] = l end
            f:close()
        end
        fileLines[w.path] = lines
    end
    if #lines == 0 then return "source not readable" end
    local body = table.concat(lines, "\n", math.max(1, w.first), math.min(#lines, math.max(w.first, w.last))):lower()
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
    stats[#stats + 1] = st

    return function(e)
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
end

local origRegister, origUnregister, origIsRegistered = event.register, event.unregister, event.isRegistered

event.register = function(eventType, callback, options)
    if type(callback) ~= "function" or type(eventType) ~= "string" then
        return origRegister(eventType, callback, options)
    end
    local w = origin(callback)
    if not w or exempt(w, callback) then return origRegister(eventType, callback, options) end
    checkPriority(eventType, options, w)
    if not PER_FRAME[eventType] or (options and (options.doOnce or options.filter ~= nil or options.unregisterOnLoad)) then
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

-- 3. periodic performance reports ----------------------------------------------------------------
local function report()
    if not config.enabled then return end
    local list = {}
    for _, st in ipairs(stats) do
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
    if config.enabled then
        origLog("[mwguard] active as passive profiler (measuring %d handlers; details in MWSE\\logs\\mwguard.log)",
            #stats)
    end
end, { priority = -100000 })

-- Mod Config Menu --------------------------------------------------------------------------------
event.register(tes3.event.modConfigReady, function()
    local template = mwse.mcm.createTemplate({ name = "mwguard" })
    template:saveOnClose(CONFIG_NAME, config)
    local page = template:createSideBarPage({
        label = "Settings",
        description = "mwguard profiles MWSE per-frame handlers and logs extreme priorities and performance bottlenecks to MWSE\\logs\\mwguard.log without affecting, throttling, or modifying other mods.",
    })
    page:createOnOffButton({
        label = "Enable Passive Profiler",
        description = "Turns performance monitoring on or off.",
        variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
    })
    page:createSlider({
        label = "Flag handlers taking more than (ms)",
        description = "Handlers averaging more than this duration per call will be flagged as high CPU in mwguard.log.",
        min = 0.25, max = 5.0, step = 0.25, decimalPlaces = 2,
        variable = mwse.mcm.createTableVariable({ id = "costMs", table = config }),
    })
    page:createSlider({
        label = "Report interval (seconds)",
        description = "How often performance summaries are written to MWSE\\logs\\mwguard.log.",
        min = 10, max = 120, step = 5,
        variable = mwse.mcm.createTableVariable({ id = "reportSeconds", table = config }),
    })
    page:createSlider({
        label = "Sample rate (1 in N frames)",
        description = "Timing every single frame adds measurement overhead. Sampling 1 in 8 frames is statistically accurate with zero measurable CPU impact.",
        min = 1, max = 32, step = 1,
        variable = mwse.mcm.createTableVariable({ id = "sampleEvery", table = config }),
    })
    page:createOnOffButton({
        label = "Output notices to MWSE.log",
        description = "When high-CPU handlers are detected, output a brief notice to the main MWSE.log.",
        variable = mwse.mcm.createTableVariable({ id = "logNoticeToMWSE", table = config }),
    })
    template:register()
end)
