local this = {}

function this.register(config, applySettings)
    local template = mwse.mcm.createTemplate({ name = "mwsoundguard" })
    template.onClose = function()
        mwse.saveConfig("mwsoundguard", config)
        if applySettings then applySettings() end
    end

    local page = template:createSideBarPage({
        label = "Settings",
        description = "mwsoundguard prevents sound loops and one-shot spam from stacking infinitely on non-actor objects (such as runaway ambient scripts or light floats).\n\n"
            .. "Changes take effect immediately without restarting.",
    })

    page:createOnOffButton({
        label = "Enable Sound Guard",
        description = "When enabled, intercepts and throttles duplicate loop sounds and rapid one-shot sound spam on non-actor references.\n\n"
            .. "When disabled, soundguard ceases all sound interception and unregisters its hooks.",
        variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
        callback = applySettings,
    })

    page:createSlider({
        label = "Loop sound duplicate threshold (seconds)",
        description = "A second start of the same loop sound on the same object within this time is treated as a duplicate.\n\nDefault: 1.0s",
        min = 0.1, max = 5.0, step = 0.1, jump = 0.5, decimalPlaces = 1,
        variable = mwse.mcm.createTableVariable({ id = "loopGap", table = config }),
    })

    page:createSlider({
        label = "Runaway duplicate count",
        description = "Number of consecutive duplicate loop starts before classifying the sound as a runaway loop.\n\nDefault: 3",
        min = 1, max = 10, step = 1, jump = 2,
        variable = mwse.mcm.createTableVariable({ id = "suspectLimit", table = config }),
    })

    page:createSlider({
        label = "One-shot sounds per second limit",
        description = "Maximum one-shot starts allowed per object and sound per second.\n\nDefault: 8",
        min = 1, max = 30, step = 1, jump = 5,
        variable = mwse.mcm.createTableVariable({ id = "oneShotPerSecond", table = config }),
    })

    page:createOnOffButton({
        label = "Trace sound diagnostics",
        description = "Log every allowed loop start to Data Files\\MWSE\\logs\\mwsoundguard.log for audio troubleshooting.\n\nDefault: Off",
        variable = mwse.mcm.createTableVariable({ id = "trace", table = config }),
    })

    page:createOnOffButton({
        label = "Name the Lua caller",
        description = "Notes which Lua file and line called tes3.playSound or tes3.removeSound, so a runaway in "
            .. "Data Files\\MWSE\\logs\\mwsoundguard.log names the mod code that started it.\n\n"
            .. "Takes effect when the guard is switched on (or at the next start).\n\nDefault: On",
        variable = mwse.mcm.createTableVariable({ id = "attributeCallers", table = config }),
        callback = applySettings,
    })

    page:createOnOffButton({
        label = "Watch actor loops (log only)",
        description = "NPC and creature sounds are never blocked. With this on, a loop started again on the same "
            .. "actor within the loop window is written to mwsoundguard.log (with the Lua caller), so a mod that "
            .. "stacks loops on actors or corpses can be found. Nothing is blocked.\n\nDefault: Off",
        variable = mwse.mcm.createTableVariable({ id = "watchActors", table = config }),
    })

    template:register()
end

return this
