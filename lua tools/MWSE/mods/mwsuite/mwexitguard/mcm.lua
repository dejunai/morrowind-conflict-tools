local config = require("mwexitguard.config")

local template = mwse.mcm.createTemplate({ name = "Exit Guard" })
template.onClose = function() config.save() end

local page = template:createSideBarPage({
    label = "Settings",
})

page.sidebar:createInfo({
    text = [[mwexitguard is a stability tool in the mwsuite intended to avoid the Morrowind on-exit hang and MGE XE d3d8.dll crash.

The Problem:
In vanilla Morrowind with MGE XE and large modlists, choosing "Exit Game" triggers an exhaustive, single-threaded teardown of all loaded cells and gigabytes of merged distant land static meshes. This causes a 15-30 second CPU freeze, followed by an access violation crash (0xC0000005) when MGE XE's renderer unloading loop invokes ->Release() on a dangling COM DirectX resource.

The Solution:
Because all game data is already saved to disk when you save/quicksave (nothing is saved on exit), mwexitguard intercepts the confirmed exit event and instantly terminates the process via Win32 ExitProcess(0). The Windows kernel immediately and safely reclaims all RAM and GPU resources in <1 ms with zero hang, zero black screen, and zero crash.]]
})

page:createYesNoButton({
    label = "Enable Exit Guard",
    description = "When enabled, cleanly terminates the process on confirmed exit, bypassing the broken deallocation loop. Restart Morrowind after enabling so the Exit button hook is installed.",
    variable = mwse.mcm.createTableVariable({
        id = "enabled",
        table = config,
    }),
})

page:createYesNoButton({
    label = "Skip Confirmation Dialog",
    description = "If enabled, clicking 'Exit Game' from the menu immediately closes the game without showing the 'Are you sure you want to exit?' confirmation dialog. Default is off for safety.",
    variable = mwse.mcm.createTableVariable({
        id = "skipConfirmation",
        table = config,
    }),
})

page:createYesNoButton({
    label = "Enable Clean Alt+F4",
    description = "When enabled, pressing Alt+F4 triggers the clean exit routine instead of the native hanging shutdown.",
    variable = mwse.mcm.createTableVariable({
        id = "enableAltF4",
        table = config,
    }),
})

page:createYesNoButton({
    label = "Log to MWSE.log",
    description = "Write a notice to MWSE.log when a clean fast exit occurs.",
    variable = mwse.mcm.createTableVariable({
        id = "logToMWSE",
        table = config,
    }),
})

template:register()
