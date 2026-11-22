--[[mwdialog_luafix 3: F1]] local print, mwse, mwluafix_log = (function(_p, _m) local S = package.loaded["mwluafix_logshim:mwwarnsuppression"] if type(S) == "table" and S.v == 3 then return S.print, S.mwse, S end S = { v = 3, redirected = 0, dropped = 0, collapsed = 0 } package.loaded["mwluafix_logshim:mwwarnsuppression"] = S local C = { name = "mwwarnsuppression", init = 0, after = 0, keep = { "error", "traceback", "exception", "fail", "warn", "stack", "attempt to", "assert", "invalid", "%.lua:%d+:", "^lua:", "initializ", "register", "start", "loaded", "ready", "version", "active" }, perSecond = 25, maxBytes = 2097152, keepOld = 1, flushSeconds = 2.0, errorRepeat = 0 } local G, MARK = _G, "mwdialog_luafix" local find, lower, sub, gsub, concat, fmt, date, select, tostring, pcall = string.find, string.lower, string.sub, string.gsub, table.concat, string.format, os.date, select, tostring, pcall local dir = "Data Files\\MWSE\\logs" local path, oldPath = dir .. "\\" .. C.name .. ".log", dir .. "\\" .. C.name .. ".old.log" local t0 = os.time() - math.floor(os.clock()) - 1 local init, run, started, redirected, f, dead, busy, fails = 0, 0, false, false, nil, false, false, 0 local bytes, dirty, last, lastN, sec, secN, dropped, errs, errKeys = 0, false, nil, 0, -1, 0, 0, {}, 0 local function isErr(t) local l = lower(#t > 4096 and sub(t, 1, 4096) or t) for i = 1, #C.keep do local ok, h = pcall(find, l, C.keep[i]) if ok and h then return true end end return false end local function out(s) f:write(date("[%H:%M:%S] "), s, "\n") bytes = bytes + #s + 12 dirty = true end local function pending() if lastN > 0 then out("[previous line repeated " .. lastN .. " more time(s)]") lastN = 0 end if dropped > 0 then out("[" .. dropped .. " line(s) dropped: more than " .. C.perSecond .. " in one second]") dropped = 0 end end local function flushAll() if f then pending() if dirty then dirty = false f:flush() end end end local function rotate() if f then pcall(f.close, f) f = nil end if C.keepOld > 0 then os.remove(oldPath) os.rename(path, oldPath) else os.remove(path) end f = io.open(path, "w") bytes, last = 0, nil if f then pcall(f.setvbuf, f, "full", 16384) f:write(date("[%Y-%m-%d %H:%M:%S] "), C.name, ": lines past its MWSE.log allowance (", MARK, ")\n") end return f end local function open() pcall(function() lfs.mkdir(dir) end) local ok, m = pcall(function() return lfs.attributes(path, "modification") end) if ok and type(m) == "number" and m >= t0 then path, oldPath = dir .. "\\" .. C.name .. ".luafix.log", dir .. "\\" .. C.name .. ".luafix.old.log" end return rotate() end local function toFile(t) if t == last then lastN = lastN + 1 S.collapsed = S.collapsed + 1 return end local s = os.time() if s ~= sec then sec, secN = s, 0 end secN = secN + 1 if C.perSecond > 0 and secN > C.perSecond then dropped = dropped + 1 S.dropped = S.dropped + 1 return end if bytes >= C.maxBytes and not rotate() then dead = true return end pending() last = t out(t) S.redirected = S.redirected + 1 if not started then dirty = false f:flush() end end S.start = function() if started then return end started = true pcall(flushAll) pcall(function() timer.start({ type = timer.real, duration = C.flushSeconds, iterations = -1, persist = false, callback = function() pcall(flushAll) end }) end) end local function route(t, force) if not started then local ok, v = pcall(function() return tes3.isInitialized() end) if ok and v then S.start() end end if force or isErr(t) then if C.errorRepeat > 0 then local k = gsub(sub(t, 1, (find(t, "\n", 1, true) or 201) - 1), "%d+", "#") local n = errs[k] or 0 if n == 0 then if errKeys >= 500 then errs, errKeys = {}, 0 end errKeys = errKeys + 1 end errs[k] = n + 1 if n >= C.errorRepeat then if f then toFile(t) end return false end end if not f and not dead then open() end if f then pending() out(t) dirty = false f:flush() end return true end local _, nl = gsub(t, "\n", "") nl = nl + 1 if not redirected then if started then if run + nl <= C.after then run = run + nl return true end elseif init + nl <= C.init then init = init + nl return true end redirected = true if not f and not open() then dead = true _p(fmt("[%s] %s writes a lot to MWSE.log, but %s can't be opened: leaving it here", MARK, C.name, path)) return true end _p(fmt("[%s] %s has written %d line(s) to MWSE.log; its further output goes to %s (errors still show here)", MARK, C.name, init + run, path)) end if dead or not f then return true end toFile(t) return false end local function fail(e) fails = fails + 1 if fails >= 10 then dead = true end if fails == 1 then pcall(_p, fmt("[%s] %s: log shim error (the line went to MWSE.log): %s", MARK, C.name, tostring(e))) end end local function decidePrint(n, ...) local t if n <= 1 then t = tostring((...)) else local parts = {} for i = 1, n do parts[i] = tostring((select(i, ...))) end t = concat(parts, "\t") end return route(t, false) end S.print = function(...) if busy or dead then return _p(...) end busy = true local ok, pass = pcall(decidePrint, select("#", ...), ...) busy = false if not ok then fail(pass) return _p(...) end if pass then return _p(...) end end local function decideLog(f0, ...) local ok, t = pcall(fmt, tostring(f0), ...) if not ok then t = tostring(f0) end return route(t, false) end S.mwse = setmetatable({ log = function(f0, ...) if busy or dead then return _m.log(f0, ...) end busy = true local ok, pass = pcall(decideLog, f0, ...) busy = false if not ok then fail(pass) pass = true end if pass then return _m.log(f0, ...) end end }, { __index = _m, __newindex = _m }) local function back(g, ok, ...) if G.print == S.print then G.print = g end if not ok then error((...), 0) end return ... end local wrapped = setmetatable({}, { __mode = "k" }) local LV = { trace = 5, debug = 4, info = 3 } local function wrap(lg) for name, lv in pairs(LV) do local orig = lg[name] if type(orig) == "function" then rawset(lg, name, function(self, ...) if dead or self ~= lg or G.print == S.print then return orig(self, ...) end local sd = type(lg.makeRecord) == "function" and type(lg.writeRecord) == "function" and lg.sharedData if sd and type(sd.level) == "number" then if sd.level < lv then return end local rec = lg:makeRecord(lv) local g = G.print G.print = S.print return back(g, pcall(lg.writeRecord, lg, rec, ...)) end local g = G.print G.print = S.print return back(g, pcall(orig, self, ...)) end) end end end S.wrap = function(lg) if type(lg) == "table" and not wrapped[lg] then wrapped[lg] = true pcall(wrap, lg) end return lg end S.flush = flushAll S.stats = function() return { init = init, run = run, redirected = redirected, dead = dead, path = path, fails = fails, started = started } end pcall(function() event.register("initialized", S.start) for _, ev in ipairs({ "loaded", "save", "menuEnter" }) do event.register(ev, function() pcall(flushAll) end) end end) pcall(function() local p = newproxy(true) getmetatable(p).__gc = function() pcall(flushAll) end S.gc = p end) return S.print, S.mwse, S end)(print, mwse) --[[/mwluafix_logshim]] --[[
    mwwarnsuppression
    Author: Antigravity

    Combines and manages engine warning suppression features:
      1. Body Part Warnings: Suppresses repetitive "Not able to find <BodyPart> part in <Item>"
         engine warning and associated MWSE Lua stack trace spam in MWSE.log.
      2. Shutdown Cache Warnings: Suppresses NetImmerse texture cache refcount leak dumps
         and ModelLoader NIF/KF dumps in Warnings.txt on game exit.

    Both features can be toggled independently via the Mod Config Menu (MCM) or config file.
    Legitimate warnings (missing meshes, textures, dialogue errors, missing masters) remain untouched.
]]--

local CONFIG_NAME = "mwwarnsuppression"
local defaults = {
    enabled = false,
    suppressBodyPartWarnings = true,
    suppressShutdownWarnings = true,
}
local config = mwse.loadConfig(CONFIG_NAME, defaults)

local locate = require("mwwarnsuppression.locate")
local ffi = require("ffi")

local origBytes = {}

-- Where the code to patch is in THIS Morrowind.exe (see locate.lua): found once, the first time it is needed.
local sites
local function findSites()
    if sites then return sites end
    sites = {}
    local ok, err = pcall(function()
        pcall(ffi.cdef, "void* GetModuleHandleA(const char* name);")
        local base = tonumber(ffi.cast("uintptr_t", ffi.C.GetModuleHandleA(nil)))
        local function read(rva, length)
            return ffi.string(ffi.cast("const char*", base + rva), length)
        end
        local image = { data = {} }
        for _, sec in ipairs(locate.sections(read)) do
            if sec.name == ".text" then
                image.text, image.textAddress = read(sec.rva, sec.size), base + sec.rva
            elseif sec.name == ".rdata" or sec.name == ".data" then
                image.data[#image.data + 1] = { bytes = read(sec.rva, sec.size), address = base + sec.rva }
            end
        end
        if image.text then sites = locate.find(image) end
    end)
    if not ok then mwse.log("[mwwarnsuppression] Could not read the executable's code: %s", tostring(err)) end
    local LABEL = { bodyPart = "BodyPart" }        -- shown as the game spells it in the warning
    for _, name in ipairs({ "bodyPart", "texture", "nif", "kf" }) do
        local label = LABEL[name] or name
        if sites[name] then
            mwse.log("[mwwarnsuppression] %s: found at 0x%X.", label, sites[name].address)
        else
            mwse.log("[mwwarnsuppression] %s: not found in this Morrowind.exe (another build or already patched); left alone.", label)
        end
    end
    return sites
end

local function readOriginalBytes(address, length)
    local bytes = {}
    local ptr = ffi.cast("const uint8_t*", address)
    for i = 0, length - 1 do
        bytes[i + 1] = ptr[i]
    end
    return bytes
end

-- Writes (enable) or puts back (not enable) one located patch. Returns true when the code was changed.
local function patch(name, enable)
    local site = findSites()[name]
    if not site then return false end
    if enable then
        if origBytes[name] then return false end          -- already applied
        origBytes[name] = readOriginalBytes(site.address, site.length)
        if site.bytes then
            mwse.memory.writeBytes({ address = site.address, bytes = site.bytes })
        else
            mwse.memory.writeNoOperation({ address = site.address, length = site.length })
        end
        return true
    elseif origBytes[name] then
        mwse.memory.writeBytes({ address = site.address, bytes = origBytes[name] })
        origBytes[name] = nil
        return true
    end
    return false
end

local function applyBodyPartPatch(enable)
    if patch("bodyPart", enable) then
        mwse.log(enable and "[mwwarnsuppression] 'Not able to find <BodyPart> part' warnings suppressed."
            or "[mwwarnsuppression] Body part warnings restored.")
    end
end

local function sanitizeWarningsFile()
    local path = "Warnings.txt"
    local file = io.open(path, "r")
    if not file then
        return
    end

    local lines = {}
    local pruned = 0
    for line in file:lines() do
        if line:find('^Texture ".*" count %d+%.') then
            pruned = pruned + 1
        elseif line:find("^ModelList still has %d+ %a+ files%.") then
            pruned = pruned + 1
        elseif line:find("^%s*%d+ %- ") then
            pruned = pruned + 1
        else
            table.insert(lines, line)
        end
    end
    file:close()

    if pruned > 0 then
        if #lines == 0 then
            os.remove(path)
            mwse.log("[mwwarnsuppression] Pruned %d shutdown leak spam lines from Warnings.txt (file was otherwise clean).", pruned)
        else
            local outFile = io.open(path, "w")
            if outFile then
                for _, l in ipairs(lines) do
                    outFile:write(l, "\n")
                end
                outFile:close()
                mwse.log("[mwwarnsuppression] Pruned %d shutdown leak spam lines from Warnings.txt; retained %d genuine warnings.", pruned, #lines)
            end
        end
    end
end

local function applyShutdownPatch(enable)
    local changed = false
    for _, name in ipairs({ "texture", "nif", "kf" }) do
        changed = patch(name, enable) or changed
    end
    if enable then sanitizeWarningsFile() end
    if changed then
        mwse.log(enable and "[mwwarnsuppression] Shutdown texture and model cache dumps suppressed."
            or "[mwwarnsuppression] Shutdown cache warnings restored.")
    end
end

local function onInitialized()
    if not config.enabled then return end
    if config.suppressBodyPartWarnings then
        applyBodyPartPatch(true)
    end
    if config.suppressShutdownWarnings then
        applyShutdownPatch(true)
    end
end
event.register("initialized", onInitialized)

-- Mod Config Menu
event.register(tes3.event.modConfigReady, function()
    local template = mwse.mcm.createTemplate({ name = "mwwarnsuppression" })
    template:saveOnClose(CONFIG_NAME, config)
    template.onClose = function()
        mwse.saveConfig(CONFIG_NAME, config)
        applyBodyPartPatch(config.enabled and config.suppressBodyPartWarnings)
        applyShutdownPatch(config.enabled and config.suppressShutdownWarnings)
    end

    local page = template:createSideBarPage({
        label = "Settings",
        description = "mwwarnsuppression cleans harmless engine warning spam from MWSE.log and Warnings.txt without hiding genuine mod issues or errors.\n\nToggle features on or off as desired.",
    })

    page:createOnOffButton({
        label = "Enabled",
        description = "Off: no warning is suppressed and the game's code is left as it is.",
        variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
    })

    page:createOnOffButton({
        label = "Suppress Body Part Missing Warnings",
        description = "Suppresses Morrowind's repetitive 'Not able to find <BodyPart> part in <Item>' warning, which triggers intrusive Lua stack traces in MWSE.log when certain armor or clothing items are equipped or added.",
        variable = mwse.mcm.createTableVariable({ id = "suppressBodyPartWarnings", table = config }),
    })

    page:createOnOffButton({
        label = "Suppress Shutdown Cache Warnings",
        description = "Suppresses benign engine shutdown dumps in Warnings.txt ('Texture count' refcount leaks and ModelLoader NIF/KF dumps) while preserving all genuine in-game warnings.",
        variable = mwse.mcm.createTableVariable({ id = "suppressShutdownWarnings", table = config }),
    })

    template:register()
end)

mwse.log("[mwwarnsuppression] Initialized successfully.")

