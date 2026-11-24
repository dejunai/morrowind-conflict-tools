--[[
    mwguard.interop - for other MWSE mods. mwguard only ever slows down handlers a player opted in by
    name; a mod that must never be slowed (camera, physics, animation, UI) can say so itself:

        local guard = include("mwguard.interop")      -- nil when mwguard isn't installed
        if guard then guard.exempt("myMod") end        -- the folder name under MWSE\mods
        -- or, for one handler only:
        if guard then guard.exemptFunction(onSimulate) end

    Call it before registering the handlers (at the top of main.lua). Exempt always wins over the
    player's opt-in list.

    Log spam guard: past a few lines, a mod's print / mwse.log / logger output moves from MWSE.log to
    MWSE\logs\<mod>.log. A mod whose MWSE.log output matters (a diagnostics or report mod) can stay:

        if guard then guard.exemptLog("myMod") end
]]
local this = {
    exemptMods = {},                                        -- lower-case mod key -> true
    exemptFunctions = setmetatable({}, { __mode = "k" }),   -- function -> true
    logExemptMods = {},                                     -- lower-case mod key -> true
}

function this.exempt(modKey)
    if type(modKey) == "string" and modKey ~= "" then
        this.exemptMods[modKey:lower():gsub("\\", "/")] = true
    end
end

function this.exemptFunction(fn)
    if type(fn) == "function" then this.exemptFunctions[fn] = true end
end

function this.isExempt(modKey, fn)
    if fn and this.exemptFunctions[fn] then return true end
    if not modKey then return false end
    modKey = modKey:lower()
    if this.exemptMods[modKey] then return true end
    local suiteMod = modKey:match("^mwsuite/([^/]+)")
    if suiteMod and this.exemptMods[suiteMod] then return true end
    local top = modKey:match("^([^/]+)/")                   -- "abot/WBSR" is covered by "abot"
    return top ~= nil and this.exemptMods[top] == true
end

function this.exemptLog(modKey)
    if type(modKey) == "string" and modKey ~= "" then
        this.logExemptMods[modKey:lower():gsub("\\", "/")] = true
    end
end

function this.isLogExempt(modKey)
    if type(modKey) ~= "string" then return false end
    modKey = modKey:lower()
    if this.logExemptMods[modKey] then return true end
    local suiteMod = modKey:match("^mwsuite/([^/]+)")
    if suiteMod and this.logExemptMods[suiteMod] then return true end
    local top = modKey:match("^([^/]+)/")
    return top ~= nil and this.logExemptMods[top] == true
end

-- Address space: what a 32-bit Morrowind runs out of (the figure MWSE's crash report gives as "Virtual Memory
-- Usage"). mwse.getVirtualMemoryUsage is private bytes only, which leaves out DLLs, mapped files and DXVK's
-- mappings, so it stays far below this. Returns used MB, total MB; nil if Windows can't be asked.
local okFfi, ffi = pcall(require, "ffi")
local memStatus
if okFfi then
    pcall(ffi.cdef, [[
        typedef struct { uint32_t dwLength; uint32_t dwMemoryLoad; uint64_t ullTotalPhys; uint64_t ullAvailPhys;
            uint64_t ullTotalPageFile; uint64_t ullAvailPageFile; uint64_t ullTotalVirtual; uint64_t ullAvailVirtual;
            uint64_t ullAvailExtendedVirtual; } mwguard_MEMORYSTATUSEX;
        int GlobalMemoryStatusEx(mwguard_MEMORYSTATUSEX *lpBuffer);
    ]])
    local ok, buf = pcall(ffi.new, "mwguard_MEMORYSTATUSEX")
    if ok then
        buf.dwLength = ffi.sizeof(buf)
        memStatus = buf
    end
end

function this.addressSpace()
    if not memStatus then return nil end
    local ok, r = pcall(ffi.C.GlobalMemoryStatusEx, memStatus)
    if not ok or r == 0 then return nil end
    local total = tonumber(memStatus.ullTotalVirtual) / 1048576
    return total - tonumber(memStatus.ullAvailVirtual) / 1048576, total
end

return this
