--[[
    mwexitguard - Clean Fast Exit & Anti-Hang Suite Tool
    Part of the mwsuite.

    Eliminates Morrowind's notorious on-exit freeze and d3d8.dll / MGE XE renderer unloading crash.
    Intercepts MenuOptions exit, MenuMessage exit confirmation, and Alt+F4 to terminate the process
    immediately via Win32 ExitProcess(0), allowing Windows to reclaim all heap and GPU resources in 0 ms.
]]--

local config = require("mwexitguard.config")

local ffi = require("ffi")
ffi.cdef[[
    void ExitProcess(unsigned int uExitCode);
]]

local function fastExit()
    if config.logToMWSE then
        mwse.log("[mwexitguard] Terminating process cleanly via ExitProcess(0).")
    end
    ffi.C.ExitProcess(0)
end

local function promptExit()
    if not config.enabled then
        return
    end

    if config.skipConfirmation then
        fastExit()
        return
    end

    local prompt = tes3.findGMST(tes3.gmst.sExitGame)
    local yes = tes3.findGMST(tes3.gmst.sYes)
    local no = tes3.findGMST(tes3.gmst.sNo)

    tes3.messageBox({
        message = prompt and prompt.value or "Are you sure you want to exit?",
        buttons = { yes and yes.value or "Yes", no and no.value or "No" },
        callback = function(e)
            if e.button == 0 then
                fastExit()
            end
        end
    })
end

local function onMenuOptionsActivated(e)
    if not e.newlyCreated or not config.enabled then
        return
    end

    local exitBtn = e.element:findChild(tes3ui.registerID("MenuOptions_Exit_container"))
    if exitBtn then
        exitBtn:register("mouseClick", function()
            tes3.worldController.menuClickSound:play()
            promptExit()
        end)
    end
end

local function onMenuMessage(e)
    if not config.enabled then
        return
    end

    local exitPrompt = tes3.findGMST(tes3.gmst.sExitGame)
    local targetText = exitPrompt and exitPrompt.value:lower() or "exit"

    local msgElem = e.element:findChild(tes3ui.registerID("MenuMessage_message"))
    local text = msgElem and msgElem.text or ""
    if text == "" then
        for _, child in ipairs(e.element.children) do
            if child.text and child.text ~= "" then
                text = child.text
                break
            end
        end
    end

    if text:lower():find(targetText, 1, true) or text:lower():find("sure you want to exit", 1, true) then
        local btn0 = e.element:findChild(tes3ui.registerID("MenuMessage_button_0"))
        if btn0 then
            btn0:register("mouseClick", function()
                fastExit()
            end)
        end
    end
end

local function onKeyDown(e)
    if config.enabled and config.enableAltF4 and e.keyCode == tes3.scanCode.f4 and e.isAltDown then
        promptExit()
        return false
    end
end

local function onInitialized()
    event.register("uiActivated", onMenuOptionsActivated, { filter = "MenuOptions" })
    event.register("uiActivated", onMenuMessage, { filter = "MenuMessage" })
    event.register("keyDown", onKeyDown, { filter = tes3.scanCode.f4 })   -- only F4 presses reach it

    mwse.log("[mwexitguard] Initialized clean fast exit protection suite tool.")
end

event.register("initialized", onInitialized)

event.register("modConfigReady", function()
    require("mwexitguard.mcm")
end)
