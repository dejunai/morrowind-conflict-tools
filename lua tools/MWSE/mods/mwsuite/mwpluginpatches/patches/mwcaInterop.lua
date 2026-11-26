--[[
    MWCA interop stub for Animated Containers addons.

    Official MW Containers Animated ships an empty MWCA.interop table, but parks it
    off the MWSE load path. After the old MWCA Lua was removed, include("MWCA.interop")
    returned nil, so the OAAB and Garden of Dreams container addons did nothing, and
    Animated Containers Rewritten had no old-style rows to import.

    When this patch is on and one of those mods is present, an empty table is put in
    package.loaded["MWCA.interop"] (and package.preload) as soon as mwpluginpatches
    loads. That has to be now, not on initialized: the OAAB and Garden of Dreams
    addons call include("MWCA.interop") at file scope. Herbert reads the same table
    later, on initialized.

    A real Data Files\MWSE\mods\MWCA\interop.lua is left alone. By dejunai.
]]

local this = {}
local stub

local function fileExists(rel)
    return lfs and lfs.fileexists and lfs.fileexists(rel) or false
end

function this.realInteropPresent()
    return fileExists("Data Files/MWSE/mods/MWCA/interop.lua")
end

function this.init()
    if stub then
        return stub
    end
    if this.realInteropPresent() then
        mwse.log("[mwpluginpatches] MWCA interop file already present; not injecting a stub.")
        return nil
    end
    stub = {}
    package.preload["MWCA.interop"] = function()
        return stub
    end
    package.loaded["MWCA.interop"] = stub
    mwse.log("[mwpluginpatches] MWCA interop stub active (Animated Containers addons can register meshes).")
    return stub
end

return this
