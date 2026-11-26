--[[ mwconsole log: its own file MWSE\logs\mwconsole.log (suite style), plus one MWSE.log line for errors. ]]
local config = require("mwconsole.config")

local log = {}
local LOG_DIR = "Data Files\\MWSE\\logs"
local LEVELS = { ERROR = 1, WARN = 2, INFO = 3, DEBUG = 4 }
local file

local function write(level, fmt, ...)
    local want = LEVELS[config.logLevel or "WARN"] or 2
    if LEVELS[level] > want then return end
    local ok, line = pcall(string.format, fmt, ...)
    line = ok and line or tostring(fmt)
    if not file then
        pcall(function() lfs.mkdir(LOG_DIR) end)
        file = io.open(LOG_DIR .. "\\mwconsole.log", "w")
        if file then file:write(os.date("mwconsole log, started %Y-%m-%d %H:%M:%S"), "\n") end
    end
    if file then
        file:write(os.date("[%H:%M:%S] "), level, " ", line, "\n")
        file:flush()
    end
    return line
end

function log.debug(fmt, ...) write("DEBUG", fmt, ...) end
function log.info(fmt, ...) write("INFO", fmt, ...) end
function log.warn(fmt, ...) write("WARN", fmt, ...) end

--- errors also leave one line in MWSE.log, so they are found where people look first
function log.error(fmt, ...)
    local ok, line = pcall(string.format, fmt, ...)
    line = ok and line or tostring(fmt)
    write("ERROR", "%s", line)
    mwse.log("[mwconsole] %s", line)
end

return log
