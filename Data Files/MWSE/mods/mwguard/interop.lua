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
    local top = modKey:match("^([^/]+)/")
    return top ~= nil and this.logExemptMods[top] == true
end

return this
