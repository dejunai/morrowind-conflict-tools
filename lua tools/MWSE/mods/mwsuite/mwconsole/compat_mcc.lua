--[[
    mwconsole stand-in for More Console Commands' interop module, so mods written for MCC work unchanged:
      include("JosephMcKean.commands.interop") -> registerCommand(cmd), registerCommands(list), data.commands,
      data.aliases, data.getCurrentRef(), getCurrentRef(), run(text)
    Only the public API shape is matched; everything behind it is mwconsole's registry.

    Guest mode: when the real MCC is installed its module wins, mwconsole doesn't publish this, and mwconsole's own
    copies of MCC's commands are not registered.
]]
local registry = require("mwconsole.registry")
local log = require("mwconsole.log")

local MODULE = "JosephMcKean.commands.interop"
local REAL_FILE = "Data Files\\MWSE\\mods\\JosephMcKean\\commands\\interop.lua"

local compat = {}

--- the source of a registration: the calling mod's folder, read from the stack
local function callerSource(level)
    local info = debug.getinfo(level or 3, "S")
    local src = info and info.source or ""
    src = src:gsub("\\", "/")
    local mod = src:match("[Mm][Oo][Dd][Ss]/mwsuite/([^/]+)/") or src:match("[Mm][Oo][Dd][Ss]/(.-)/[^/]+%.lua$")
        or src:match("/([^/]+)/[^/]+%.lua$")
    return mod or "unknown"
end
compat.callerSource = callerSource

local data = {
    commands = registry.commands,     -- the live tables: pairs() works as with MCC (LuaJIT has no __pairs)
    aliases = registry.aliases,
    getCurrentRef = function() return tes3ui.getConsoleReference() end,
}

local interop = { data = data, mwconsole = true }

function interop.getCurrentRef() return tes3ui.getConsoleReference() end

function interop.registerCommand(cmd)
    local ok, msg = registry.register(cmd, { source = callerSource(3), kind = "mod" })
    if not ok then log.warn("%s", tostring(msg)) end
    return ok
end

function interop.registerCommands(list)
    if type(list) ~= "table" then return end
    local src = callerSource(3)
    for _, cmd in ipairs(list) do
        local ok, msg = registry.register(cmd, { source = src, kind = "mod" })
        if not ok then log.warn("%s", tostring(msg)) end
    end
end

function interop.run(text)
    event.trigger("UIEXP:consoleCommand", { command = text, context = "lua" }, { filter = "lua" })
end

compat.interop = interop
compat.data = data
compat.published = false

--- true when the real MCC is installed (its files exist, or its module is already loaded)
function compat.realMccPresent()
    local loaded = package.loaded[MODULE]
    if type(loaded) == "table" and not loaded.mwconsole then return true end
    local ok, attr = pcall(function() return lfs.attributes(REAL_FILE) end)
    return ok and attr ~= nil
end

function compat.publish()
    if compat.realMccPresent() then
        log.warn("More Console Commands is installed: mwconsole runs in guest mode (its MCC commands are not added)")
        return false
    end
    package.loaded[MODULE] = interop
    package.loaded["JosephMcKean.commands.data"] = data
    compat.published = true
    return true
end

function compat.unpublish()
    if package.loaded[MODULE] == interop then package.loaded[MODULE] = nil end
    if package.loaded["JosephMcKean.commands.data"] == data then package.loaded["JosephMcKean.commands.data"] = nil end
    compat.published = false
end

return compat
