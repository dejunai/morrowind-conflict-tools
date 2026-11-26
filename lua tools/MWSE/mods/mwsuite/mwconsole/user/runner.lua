--[[
    mwconsole user script runner. Hygiene, not security:
    * each script has its own environment: reads fall through to the globals, assignments stay in the environment
    * safe mode blocks the riskiest functions (they raise "blocked in safe mode")
    * an instruction limit stops runaway scripts; JIT is turned off for the script's code so the hook sees loops
    * every run goes through xpcall; errors print one console line and a throttled log entry with the traceback
]]
local config = require("mwconsole.config")
local guard = require("mwconsole.guard")

local runner = {}

local realIo, realOs, realPackage, realRequire = io, os, package, require
local ALLOWED_WRITE_DIR = "data files/mwse/config/mwconsole/"

local function blocked(what)
    return function() error(what .. " is blocked in safe mode", 2) end
end

local function normalize(path)
    local p = tostring(path or ""):gsub("\\", "/"):lower()
    p = p:gsub("^%./", "")
    return p
end

function runner.writeAllowed(path)
    local p = normalize(path)
    if p:find("%.%.") then return false end
    return p:sub(1, #ALLOWED_WRITE_DIR) == ALLOWED_WRITE_DIR
end

local function makeSafeLibs()
    local safeOs = setmetatable({
        exit = blocked("os.exit"), execute = blocked("os.execute"),
        remove = blocked("os.remove"), rename = blocked("os.rename"),
    }, { __index = realOs })
    local safeIo = setmetatable({
        popen = blocked("io.popen"),
        open = function(path, mode)
            if mode and mode:find("[wa+]") and not runner.writeAllowed(path) then
                error("io.open for writing outside MWSE\\config\\mwconsole is blocked in safe mode", 2)
            end
            return realIo.open(path, mode)
        end,
    }, { __index = realIo })
    local safePackage = setmetatable({ loadlib = blocked("package.loadlib") }, { __index = realPackage })
    local safeRequire = function(name)
        if name == "ffi" then error('require("ffi") is blocked in safe mode', 2) end
        return realRequire(name)
    end
    return { os = safeOs, io = safeIo, package = safePackage, require = safeRequire }
end
local safeLibs = makeSafeLibs()

local envs = {}             -- name -> environment (kept between runs of the same command)
local compiled = {}         -- name -> { code, fn }

function runner.forget(name)
    envs[name] = nil
    compiled[name] = nil
end

local function newEnv()
    local env = {}
    setmetatable(env, {
        __index = function(_, k)
            if config.userScripts.safeMode then
                local s = safeLibs[k]
                if s ~= nil then return s end
            end
            return _G[k]
        end,
    })
    return env
end

--- compile only (syntax check). Returns fn or nil, message
function runner.compile(code, name)
    local fn, err = loadstring(code, "=user:" .. tostring(name))
    if not fn then return nil, err end
    return fn
end

--[[ run(name, code, args, io) -> ok, results...
     io = { print, ref, target, player, cmd = fn(name, ...), mw = fn(line), steps = millions } ]]
function runner.run(name, code, args, io)
    io = io or {}
    local c = compiled[name]
    if not c or c.code ~= code then
        local fn, err = runner.compile(code, name)
        if not fn then
            if io.print then io.print(string.format("%s: %s", name, tostring(err))) end
            return false, err
        end
        if jit and jit.off then jit.off(fn, true) end      -- hooks must see every loop
        c = { code = code, fn = fn }
        compiled[name] = c
    end
    local env = envs[name]
    if not env then env = newEnv() envs[name] = env end
    local out = io.print or function() end
    env.args = args
    env.argc = #args
    env.ref = io.ref
    env.player = tes3.player
    env.target = io.target
    env.print = function(...)
        local parts = {}
        for i = 1, select("#", ...) do parts[#parts + 1] = tostring((select(i, ...))) end
        out(table.concat(parts, "\t"))
    end
    env.log = function(fmt, ...)
        local ok, line = pcall(string.format, tostring(fmt), ...)
        mwse.log("[mwconsole:user:%s] %s", name, ok and line or tostring(fmt))
    end
    env.num = function(s, default) return tonumber(s) or default end
    env.cmd = io.cmd or function() error("cmd is not available here", 2) end
    env.mw = io.mw or function(line) return tes3.runLegacyScript({ command = line }) end
    env.json = json
    setfenv(c.fn, env)

    local limit = math.max(1, tonumber(io.steps or config.userScripts.maxInstructions) or 5) * 1000000
    local prevHook, prevMask, prevCount = debug.gethook()
    local function hook() error("script ran too long (more than " .. (limit / 1000000) .. " million steps)", 2) end
    debug.sethook(hook, "", limit)
    local res = { xpcall(c.fn, debug.traceback, unpack(args)) }
    if prevHook then debug.sethook(prevHook, prevMask, prevCount) else debug.sethook() end
    if not res[1] then
        local msg = tostring(res[2])
        out(string.format("%s: %s", name, msg:match("^[^\n]*")))
        guard.reportError("user:" .. name, msg)
        return false, msg
    end
    for i = 2, #res do out("> " .. tostring(res[i])) end
    return true, unpack(res, 2)
end

return runner
