--[[
    mwmouseguard - Multi-Monitor Mouse & Scroll Bleed Protection Suite Tool
    
    In multi-monitor setups (especially with MGE XE borderless windowed mode), the Windows OS
    cursor drifts across display boundaries onto secondary monitors. Because Windows enables
    "Scroll inactive windows when I hover over them" by default, mousewheel scrolling inside
    Morrowind simultaneously scrolls whatever background window is open on the second display.

    mwmouseguard clips the OS cursor to Morrowind's window while Morrowind is the foreground window,
    preventing any drift or scroll bleed to other screens. It automatically releases the cursor
    as soon as you Alt-Tab or press the Windows key.
]]

local config = require("mwmouseguard.config")
local ffi = require("ffi")

pcall(ffi.cdef, [[
    typedef void* HWND;
    typedef unsigned long DWORD;
    typedef int BOOL;

    typedef struct {
        long left;
        long top;
        long right;
        long bottom;
    } RECT;

    typedef struct {
        long x;
        long y;
    } POINT;

    HWND GetForegroundWindow(void);
    DWORD GetCurrentProcessId(void);
    DWORD GetWindowThreadProcessId(HWND hWnd, DWORD *lpdwProcessId);
    BOOL GetClientRect(HWND hWnd, RECT *lpRect);
    BOOL ClientToScreen(HWND hWnd, POINT *lpPoint);
    BOOL ClipCursor(const RECT *lpRect);
]])

local user32 = ffi.load("user32")
local kernel32 = ffi.load("kernel32")
local myPid = kernel32.GetCurrentProcessId()

local isClipped = false
local cachedHwnd = nil
local screenRect = ffi.new("RECT")
local clientRect = ffi.new("RECT")
local ptTopLeft = ffi.new("POINT")
local pidBuf = ffi.new("DWORD[1]")

local function releaseCursor()
    if isClipped then
        pcall(function() user32.ClipCursor(nil) end)
        isClipped = false
        cachedHwnd = nil
    end
end

local function applyClip(hwnd)
    if user32.GetClientRect(hwnd, clientRect) ~= 0 then
        ptTopLeft.x = clientRect.left
        ptTopLeft.y = clientRect.top
        user32.ClientToScreen(hwnd, ptTopLeft)

        screenRect.left = ptTopLeft.x
        screenRect.top = ptTopLeft.y
        screenRect.right = ptTopLeft.x + (clientRect.right - clientRect.left)
        screenRect.bottom = ptTopLeft.y + (clientRect.bottom - clientRect.top)

        if screenRect.right > screenRect.left and screenRect.bottom > screenRect.top then
            user32.ClipCursor(screenRect)
            isClipped = true
            cachedHwnd = hwnd
        end
    end
end

local function checkCursorLock()
    if not config.enabled then
        if isClipped then releaseCursor() end
        return
    end

    local fg = user32.GetForegroundWindow()
    if fg == nil then
        if isClipped then releaseCursor() end
        return
    end

    user32.GetWindowThreadProcessId(fg, pidBuf)
    if pidBuf[0] ~= myPid then
        -- Morrowind lost focus (Alt-Tab, task switch, Win key)
        if isClipped then releaseCursor() end
        return
    end

    -- Morrowind is foreground
    local inMenu = tes3.menuMode()
    if inMenu and not config.lockInMenus then
        if isClipped then releaseCursor() end
        return
    elseif not inMenu and not config.lockInGame then
        if isClipped then releaseCursor() end
        return
    end

    -- If not clipped or foreground window changed, clip now
    if not isClipped or fg ~= cachedHwnd then
        applyClip(fg)
    end
end

-- Check cursor containment every 0.35s rather than polling Win32 FFI every frame
timer.start({
    type = timer.real,
    duration = 0.35,
    iterations = -1,
    callback = function()
        pcall(checkCursorLock)
    end,
})

event.register(tes3.event.menuEnter, function()
    if not config.lockInMenus then releaseCursor() end
end)

event.register(tes3.event.menuExit, function()
    pcall(checkCursorLock)
end)

local function onInitialized()
    mwse.log("[mwmouseguard] Initialized cursor & scroll containment protection.")
end
event.register(tes3.event.initialized, onInitialized)

event.register(tes3.event.modConfigReady, function()
    require("mwmouseguard.mcm")
end)
