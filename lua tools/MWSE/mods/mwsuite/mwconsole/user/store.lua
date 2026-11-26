--[[
    mwconsole user scripts storage, under MWSE\config\mwconsole (never the mod folder):
      user_commands.json      index { version, commands = { name = { aliases, description, args, context,
                              needsGame, on, code | file, override, created, modified } } }
      scripts\<name>.lua      longer scripts; scripts\removed\ holds removed ones
    Writes are atomic: *.tmp first, the old file becomes user_commands.json.bak, then the rename.
    A corrupt index is renamed to user_commands.json.bad-<time> and loading continues empty.
]]
local log = require("mwconsole.log")

local store = {}

-- captured at load, so the sandbox given to user scripts can't change what the store uses
local ioOpen, osRemove, osRename, osDate, osTime = io.open, os.remove, os.rename, os.date, os.time

store.BASE = "Data Files\\MWSE\\config\\mwconsole"
store.INDEX = store.BASE .. "\\user_commands.json"
store.SCRIPTS = store.BASE .. "\\scripts"
store.REMOVED = store.SCRIPTS .. "\\removed"

store.data = { version = 1, commands = {} }
store.warning = nil

local function mkdirs()
    for _, d in ipairs({ "Data Files\\MWSE\\config", store.BASE, store.SCRIPTS, store.REMOVED }) do
        pcall(lfs.mkdir, d)
    end
end
store.mkdirs = mkdirs

local function exists(path)
    local f = ioOpen(path, "rb")
    if f then f:close() return true end
    return false
end
store.exists = exists

local function readAll(path)
    local f = ioOpen(path, "rb")
    if not f then return nil end
    local s = f:read("*a")
    f:close()
    return s
end
store.readAll = readAll

--- writes text to path through path.tmp; keeps one .bak of the previous file when keepBak
function store.atomicWrite(path, text, keepBak)
    mkdirs()
    local tmp = path .. ".tmp"
    local f, err = ioOpen(tmp, "wb")
    if not f then return false, "can't write " .. tmp .. ": " .. tostring(err) end
    local okW, errW = f:write(text)
    f:close()
    if not okW then
        osRemove(tmp)
        return false, "write failed: " .. tostring(errW)
    end
    local bak = path .. ".bak"
    if exists(path) then
        if keepBak then
            osRemove(bak)
            osRename(path, bak)
        else
            osRemove(path)
        end
    end
    local okR, errR = osRename(tmp, path)
    if not okR then
        if keepBak and exists(bak) and not exists(path) then osRename(bak, path) end
        return false, "rename failed: " .. tostring(errR)
    end
    return true
end

function store.load()
    store.warning = nil
    store.data = { version = 1, commands = {} }
    local text = readAll(store.INDEX)
    if not text or text:match("^%s*$") then return true end
    local ok, decoded = pcall(json.decode, text)
    if not ok or type(decoded) ~= "table" or (decoded.commands ~= nil and type(decoded.commands) ~= "table") then
        local bad = store.INDEX .. ".bad-" .. osDate("%Y%m%d-%H%M%S")
        osRename(store.INDEX, bad)
        store.warning = "user_commands.json couldn't be read; it was kept as " .. bad .. " and no user commands were loaded"
        log.error("%s", store.warning)
        return false, store.warning
    end
    decoded.commands = decoded.commands or {}
    decoded.version = decoded.version or 1
    store.data = decoded
    return true
end

function store.save()
    local ok, text = pcall(json.encode, store.data, { indent = true })
    if not ok then return false, tostring(text) end
    local okW, err = store.atomicWrite(store.INDEX, text, true)
    if not okW then log.error("saving user commands: %s", tostring(err)) end
    return okW, err
end

function store.get(name) return store.data.commands[name] end

function store.put(name, entry)
    entry.modified = osDate("%Y-%m-%d %H:%M:%S")
    entry.created = entry.created or entry.modified
    store.data.commands[name] = entry
end

function store.remove(name) store.data.commands[name] = nil end

function store.scriptPath(file) return store.SCRIPTS .. "\\" .. file end

function store.readScript(entry)
    if entry.code then return entry.code end
    if entry.file then
        local text = readAll(store.scriptPath(entry.file))
        if not text then return nil, "script file missing: " .. store.scriptPath(entry.file) end
        return text
    end
    return nil, "no code"
end

function store.writeTemplate(name)
    local file = name .. ".lua"
    local path = store.scriptPath(file)
    if not exists(path) then
        local text = table.concat({
            "-- mwconsole user command: " .. name,
            "-- Runs when you type `" .. name .. "` in the lua console. Edit this file, then type `alias reload`.",
            "-- Available: ... and args (the words typed after the name), argc, ref (console selection), player,",
            "-- target (crosshair), print (console), log (MWSE.log), num(s, default), cmd(name, ...), mw(line), json.",
            "-- Developer feature: what a script does can't be undone. Back up your saves.",
            "",
            'print("' .. name .. ': edit " .. "' .. path:gsub("\\", "\\\\") .. '")',
            "",
        }, "\n")
        local ok, err = store.atomicWrite(path, text, false)
        if not ok then return nil, err end
    end
    return file, path
end

--- moves a script file to scripts\removed (never deleted)
function store.retireScript(file)
    mkdirs()
    local from = store.scriptPath(file)
    if not exists(from) then return true end
    local to = store.REMOVED .. "\\" .. file:gsub("%.lua$", "") .. "-" .. osTime() .. ".lua"
    return osRename(from, to)
end

return store
