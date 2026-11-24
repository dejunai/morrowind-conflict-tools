--[[
    mwsoundfix - the MWSE side of mwdialog_check --soundfix.

    --soundfix rewrites the scripts that started a sound only while GetSoundPlaying said it wasn't playing (this
    engine answers 0 for object sounds, so they restarted it every frame) into 'mwdialog_check - MWSoundFix.esp':
    each loop now starts once and keeps a flag (mwsfOn<n>), each one-shot a timer (mwsfT<n>). This helper does the
    two things MWScript can't:
      * on every game load (and a new game) it bumps the MWSF_Epoch global, so each patched script re-arms once:
        nothing it started survives a load;
      * in flag mode, when a reference with a patched script becomes active again (its cell loads), it zeroes that
        script's loop flags, so the loop the engine stopped when the cell unloaded starts again.
    Which scripts and flags: Data Files\MWSE\config\mwsoundfix_data.json, written by --soundfix.
    Idle (nothing registered) when the patch isn't active. It never blocks a sound and saves nothing of its own.
]]

local PATCH = "mwdialog_check - MWSoundFix.esp"
local flagsByScript = {}
local errors = 0

local function guarded(fn)
    return function(e)
        local ok, err = pcall(fn, e)
        if not ok then
            errors = errors + 1
            if errors == 1 then mwse.log("[mwsoundfix] error (ignored): %s", tostring(err)) end
        end
    end
end

local function onLoaded()
    local epoch = tes3.findGlobal("MWSF_Epoch")
    if epoch then epoch.value = (epoch.value % 32000) + 1 end
end

local function onReferenceActivated(e)
    local ref = e.reference
    local script = ref and ref.object and ref.object.script
    if not script then return end
    local flags = flagsByScript[script.id:lower()]
    if not flags then return end
    local context = ref.context                  -- nil until the reference's script has run with variables
    if not context then return end
    for _, name in ipairs(flags) do context[name] = 0 end
    ref.modified = true
end

local function start()
    if not tes3.findGlobal("MWSF_Epoch") then
        mwse.log("[mwsoundfix] idle: %s is not active", PATCH)
        return
    end
    local ok, data = pcall(mwse.loadConfig, "mwsoundfix_data")
    local count = 0
    if ok and type(data) == "table" and data.version == 1 and type(data.scripts) == "table" then
        for id, info in pairs(data.scripts) do
            if type(id) == "string" and type(info) == "table" and type(info.loopFlags) == "table" and #info.loopFlags > 0 then
                flagsByScript[id:lower()] = info.loopFlags
                count = count + 1
            end
        end
    else
        mwse.log("[mwsoundfix] mwsoundfix_data.json missing or unreadable: loops re-arm on loads only")
    end
    event.register(tes3.event.loaded, guarded(onLoaded))
    if count > 0 and not (type(data) == "table" and data.loopMode == "restart") then
        event.register(tes3.event.referenceActivated, guarded(onReferenceActivated))
    end
    mwse.log("[mwsoundfix] ready: %d script(s) with loop flags", count)
end

event.register(tes3.event.initialized, start)

-- a read-only MCM page: the scripts the patch repaired, by plugin (nothing to set)
local function registerMcm()
    local template = mwse.mcm.createTemplate({ name = "mwsoundfix" })
    local page = template:createPage({ label = "Repaired sound scripts" })
    local ok, data = pcall(mwse.loadConfig, "mwsoundfix_data")
    if not (ok and type(data) == "table" and type(data.scripts) == "table") then
        page:createInfo({ text = "No sound scripts are repaired yet. mwdialog_check --soundfix (or --fix) builds "
            .. PATCH .. ", and this page lists what it repaired." })
        template:register()
        return
    end
    local byPlugin, plugins, total = {}, {}, 0
    for id, info in pairs(data.scripts) do
        local owner = type(info) == "table" and info.owner or "?"
        if not byPlugin[owner] then byPlugin[owner] = {}; plugins[#plugins + 1] = owner end
        local repairs = type(info) == "table" and type(info.repairs) == "table" and table.concat(info.repairs, "; ") or ""
        table.insert(byPlugin[owner], id .. (repairs ~= "" and ("  -  " .. repairs) or ""))
        total = total + 1
    end
    table.sort(plugins, function(a, b) return a:lower() < b:lower() end)
    page:createInfo({ text = string.format("%d script(s) in %d plugin(s), built %s. These scripts used to restart "
        .. "their sound every frame; %s keeps their own state instead. %s", total, #plugins, tostring(data.built or "?"),
        PATCH, tes3.findGlobal("MWSF_Epoch") and "The patch is active." or "The patch is NOT active in this game.") })
    for _, owner in ipairs(plugins) do
        table.sort(byPlugin[owner])
        local cat = page:createCategory(string.format("%s (%d)", owner, #byPlugin[owner]))
        cat:createInfo({ text = table.concat(byPlugin[owner], "\n") })
    end
    template:register()
end

event.register(tes3.event.modConfigReady, registerMcm)

return { onLoaded = onLoaded, onReferenceActivated = onReferenceActivated, flagsByScript = flagsByScript }
