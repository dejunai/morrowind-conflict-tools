--[[
    mwconsole config: defaults, load, save.
    The whole mod is off until it is switched on in its MCM (suite rule). Sub-switches are named "on" so that the
    suite's default-off check only ever sees the master switch.
]]
local CONFIG_NAME = "mwconsole"

local function deepCopy(t)
    if type(t) ~= "table" then return t end
    local out = {}
    for k, v in pairs(t) do
        if type(v) ~= "function" then out[k] = deepCopy(v) end
    end
    return out
end

local defaults = {
    enabled = false,                  -- master switch (suite rule: off until turned on in the MCM)
    logLevel = "WARN",                -- ERROR / WARN / INFO / DEBUG, written to MWSE\logs\mwconsole.log
    commands = { on = true, inMwscript = true },
    console = { startLua = false },
    complete = { on = true, live = true, minChars = 2, prebuild = false, topics = false, runtimeObjects = false },
    panel = { on = true, requireCtrl = false, right = true, alpha = 0.85, objectVfx = false,
              widthPct = 35, heightPct = 75,
              hotkey = { keyCode = 23, isShiftDown = false, isAltDown = true, isControlDown = false } },  -- Alt+I
    effects = {
        showSpells = true, showEquipment = true, showVFX = true,
        vfxWords = "vfx, magic, shield, spell, aura, effect",
        logToMWSE = false,
    },
    toggles = { on = false, style = "press", ra = {}, tcl = {}, tm = {} },   -- keys unbound
    compat = { useMwcompanions = true, useMwexitguard = true },
    userScripts = { on = false, safeMode = true, allowOverride = false, maxInstructions = 5,
                    inlineLimit = 500, warningShown = false, consoleWarned = false, unsafeWarned = false },
}

local config = mwse.loadConfig(CONFIG_NAME, deepCopy(defaults)) or deepCopy(defaults)

-- the first build kept the hotkey under effects; it now opens the selection details window
if type(config.effects) == "table" and type(config.effects.hotkey) == "table" then
    if type(config.panel) ~= "table" then config.panel = {} end
    if config.panel.hotkey == nil then config.panel.hotkey = config.effects.hotkey end
    config.effects.hotkey = nil
end

-- mwse.loadConfig merges only the top level: fill missing keys of the nested tables too
local function fill(dst, src)
    for k, v in pairs(src) do
        if dst[k] == nil then
            dst[k] = deepCopy(v)
        elseif type(v) == "table" and type(dst[k]) == "table" and next(v) ~= nil then
            fill(dst[k], v)
        end
    end
end
fill(config, defaults)

config.defaults = defaults
config.deepCopy = deepCopy

function config.save()
    local plain = deepCopy(config)      -- functions on this table cannot go into JSON
    plain.defaults = nil
    mwse.saveConfig(CONFIG_NAME, plain)
end

function config.isOn()
    return config.enabled == true
end

return config
