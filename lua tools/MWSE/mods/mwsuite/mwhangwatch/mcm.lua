--[[
    Hangwatch settings for the shared "Guard & Hang Watch" MCM, which mwguard registers.
    Hooks (config, applySettings, startMemCheck) are filled in by mwhangwatch.main when it loads.
]]
local this = {}

function this.addMemoryWarning(category)
    category:createOnOffButton({
        label = "Warn when memory runs low",
        description = "With the 4 GB patch, Morrowind has up to 4 GB of address space. When it is nearly full, a "
            .. "short message pops up so you can save before a crash, naming the biggest textures in the area "
            .. "(details in the hang log). The message goes away by itself and never opens a menu.\n\n"
            .. "Off until you turn it on here. Works even with the hang log turned off.",
        variable = mwse.mcm.createTableVariable({ id = "memWarn", table = this.config }),
        callback = function()
            if this.startMemCheck then this.startMemCheck() end
        end,
    })
    category:createSlider({
        label = "Memory warning level (%)",
        description = "How full the 4 GB has to be before the warning comes up. The default is 80%; raise it for "
            .. "fewer warnings, lower it for an earlier one.",
        min = 70, max = 99, step = 1, jump = 5,
        variable = mwse.mcm.createTableVariable({ id = "memLimit", table = this.config }),
    })
end

function this.addHangLog(page)
    local hang = page:createCategory("Hang log")
    hang:createOnOffButton({
        label = "Record a hang log",
        description = "Turns the log on: frame rate, memory, objects in nearby areas, area changes, menus, scripts "
            .. "and (if turned on below) sounds.\n\n"
            .. "Off: nothing is logged. The low-memory warning above has its own switch and works either way. "
            .. "Changes apply right away.",
        variable = mwse.mcm.createTableVariable({ id = "enabled", table = this.config }),
        callback = function()
            if this.applySettings then this.applySettings() end
        end,
    })
    hang:createOnOffButton({
        label = "Include audio in the log",
        description = "Also logs every sound the game starts, music changes, and which mods block or swap sounds "
            .. "(\"BLOCKED by ...\").\n\n"
            .. "This makes the log much bigger. Needs the watch above to be on.",
        variable = mwse.mcm.createTableVariable({ id = "audio", table = this.config }),
        callback = function()
            if this.applySettings then this.applySettings() end
        end,
    })
    hang:createSlider({
        label = "Sound lines per second",
        description = "The most sound lines written to the log each second; any more are only counted in the "
            .. "summaries. 0 = summaries only.",
        min = 0, max = 200, step = 5, jump = 20,
        variable = mwse.mcm.createTableVariable({ id = "soundLines", table = this.config }),
    })
end

return this
