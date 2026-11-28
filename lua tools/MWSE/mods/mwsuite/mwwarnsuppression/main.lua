--[[
    mwwarnsuppression
    Author: dej (dejunai)

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
        description = "mwwarnsuppression removes harmless, repeated warnings from MWSE.log and Warnings.txt, so real "
            .. "problems are easier to spot. Real warnings (missing meshes or textures, dialogue errors, missing "
            .. "masters) are never hidden.",
    })

    page:createOnOffButton({
        label = "Enabled",
        description = "On: hides only the warning groups selected below. Off: all warnings are shown.",
        variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
    })

    page:createOnOffButton({
        label = "Suppress Body Part Missing Warnings",
        description = "Hides the game's repeated 'Not able to find <body part> part in <item>' warning, and the long "
            .. "error trace it causes in MWSE.log, when some armor or clothing is worn or picked up.",
        variable = mwse.mcm.createTableVariable({ id = "suppressBodyPartWarnings", table = config }),
    })

    page:createOnOffButton({
        label = "Suppress Shutdown Cache Warnings",
        description = "Hides the long, harmless lists the game writes to Warnings.txt when you quit ('Texture count' "
            .. "and model-loader lists). Warnings from while you play are kept.",
        variable = mwse.mcm.createTableVariable({ id = "suppressShutdownWarnings", table = config }),
    })

    template:register()
end)

mwse.log("[mwwarnsuppression] Initialized successfully.")

