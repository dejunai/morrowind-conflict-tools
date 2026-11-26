local this = {}

function this.register(config, applySettings)
    local template = mwse.mcm.createTemplate({ name = "mwsoundguard" })
    template.onClose = function()
        mwse.saveConfig("mwsoundguard", config)
        if applySettings then applySettings() end
    end

    local page = template:createSideBarPage({
        label = "Settings",
        description = "mwsoundguard stops sounds from piling up on objects, for example an ambient sound that a script "
            .. "restarts over and over until it roars or crackles.\n\n"
            .. "Changes take effect right away, no restart needed.",
    })

    page:createOnOffButton({
        label = "Enable Sound Guard",
        description = "Stops extra copies of the same looping sound, and rapid-fire repeats of short sounds, on objects "
            .. "(never on people or creatures).\n\n"
            .. "Off: no sound is touched.",
        variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
        callback = applySettings,
    })

    page:createSlider({
        label = "Loop sound duplicate threshold (seconds)",
        description = "If the same looping sound is started again on the same object within this many seconds, the extra "
            .. "start is dropped.\n\nDefault: 1.0 s",
        min = 0.1, max = 5.0, step = 0.1, jump = 0.5, decimalPlaces = 1,
        variable = mwse.mcm.createTableVariable({ id = "loopGap", table = config }),
    })

    page:createSlider({
        label = "Runaway duplicate count",
        description = "After this many dropped repeats, the sound is treated as a runaway: it is kept to one copy and "
            .. "reported in the log.\n\nDefault: 3",
        min = 1, max = 10, step = 1, jump = 2,
        variable = mwse.mcm.createTableVariable({ id = "suspectLimit", table = config }),
    })

    page:createSlider({
        label = "One-shot sounds per second limit",
        description = "The most times a short sound can start on one object each second. Mainly used for sounds whose "
            .. "length isn't known; a sound of known length simply can't restart while it is still playing.\n\nDefault: 8",
        min = 1, max = 30, step = 1, jump = 5,
        variable = mwse.mcm.createTableVariable({ id = "oneShotPerSecond", table = config }),
    })

    page:createOnOffButton({
        label = "Trace sound diagnostics",
        description = "For troubleshooting: logs every looping sound that is allowed to start, in "
            .. "Data Files\\MWSE\\logs\\mwsoundguard.log.\n\nDefault: Off",
        variable = mwse.mcm.createTableVariable({ id = "trace", table = config }),
    })

    page:createOnOffButton({
        label = "Name the Lua caller",
        description = "Notes which mod started or stopped each sound, so a runaway in "
            .. "Data Files\\MWSE\\logs\\mwsoundguard.log names the mod responsible.\n\n"
            .. "Takes effect when the guard is switched on (or at the next start).\n\nDefault: On",
        variable = mwse.mcm.createTableVariable({ id = "attributeCallers", table = config }),
        callback = applySettings,
    })

    page:createOnOffButton({
        label = "Watch actor loops (log only)",
        description = "Sounds on people and creatures are never blocked. With this on, a looping sound started again on "
            .. "the same NPC or creature is noted in mwsoundguard.log (with the mod that did it), to help find a mod "
            .. "that stacks sounds on actors or corpses. Nothing is blocked.\n\nDefault: Off",
        variable = mwse.mcm.createTableVariable({ id = "watchActors", table = config }),
    })

    template:register()
end

return this
