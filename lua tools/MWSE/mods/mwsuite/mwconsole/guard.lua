--[[
    mwconsole guard: the modal-safety rule.
    * isGameLoaded(): a character is in the world (not the main menu, not mid-load).
    * run(where, fn, ...): xpcall with a traceback; one log line per 10 s per entry point; one short message.
    * openWindow{...}: the only way mwconsole opens a window. Each window has one close(reason) path that is
      idempotent, unregisters what the window registered, destroys its elements, leaves menu mode once and only
      if this window entered it, and gives the console input focus back.
    * Every open window is closed when a save starts loading (and so before the main menu can come back), and when
      menu mode ends (a window can't be used without the cursor).
    * Esc closes only the window on top (the one opened last), so Esc in the effect inspector opened from the
      selection details window leaves the details window open.
]]
local log = require("mwconsole.log")

local guard = {}

guard.NOT_LOADED = "Load a game first. This needs a character in the world."

local gameLoaded = false
local windows = {}          -- id -> window record
local loadHandlerOn = false
local lastError = {}        -- where -> { time, suppressed }
local openSeq = 0           -- opening order, for "the window on top"

local function now() return os.clock() end

function guard.setLoaded(v) gameLoaded = v and true or false end

--- a character is in the world: the player and its mobile exist and `loaded` has fired since the last `load`.
--- (tes3.onMainMenu() isn't used: it can't tell a loaded save from character generation.)
function guard.isGameLoaded()
    return gameLoaded and tes3.player ~= nil and tes3.mobilePlayer ~= nil
end

--- shows the plain "load a game first" message; returns false so callers can `return guard.needGame()`
function guard.needGame(statusSetter)
    pcall(tes3.messageBox, guard.NOT_LOADED)
    if statusSetter then pcall(statusSetter, guard.NOT_LOADED) end
    return false
end

function guard.reportError(where, err)
    local rec = lastError[where]
    local t = now()
    if rec and t - rec.time < 10 then
        rec.suppressed = rec.suppressed + 1
        return
    end
    local extra = (rec and rec.suppressed > 0) and string.format(" (%d more since the last report)", rec.suppressed) or ""
    lastError[where] = { time = t, suppressed = 0 }
    log.error("%s: %s%s", where, tostring(err), extra)
end

--- run fn safely. Returns ok, result. Never raises.
function guard.run(where, fn, ...)
    local args, n = { ... }, select("#", ...)
    local ok, res = xpcall(function() return fn(unpack(args, 1, n)) end, debug.traceback)
    if not ok then
        guard.reportError(where, res)
        pcall(tes3.messageBox, string.format("mwconsole: couldn't %s. Details are in MWSE.log.", where))
    end
    return ok, res
end

-- windows -------------------------------------------------------------------------------------------------------

local onLoad
local function updateLoadHandler()
    local any = next(windows) ~= nil
    if any and not loadHandlerOn then
        event.register("load", onLoad, { priority = 10000 })
        loadHandlerOn = true
    elseif not any and loadHandlerOn then
        event.unregister("load", onLoad, { priority = 10000 })
        loadHandlerOn = false
    end
end

function guard.focusConsole()
    pcall(function()
        local console = tes3ui.findMenu("MenuConsole")
        if console and console.visible then
            local input = console:findChild("UIEXP:ConsoleInputBox") or console:findChild("MenuConsole_text_input")
            if input then tes3ui.acquireTextInput(input) end
        end
    end)
end

local Window = {}
Window.__index = Window

--- register an event for the life of this window
function Window:on(name, fn, opts)
    event.register(name, fn, opts)
    table.insert(self.events, { name, fn, opts })
end

--- register an element callback for the life of this window (only needed for elements outside the window)
function Window:onElement(element, name, fn, after)
    if after then element:registerAfter(name, fn) else element:registerBefore(name, fn) end
    table.insert(self.callbacks, { element, name, fn, after })
end

function Window:close(reason)
    if self.closed then return end
    self.closed = true
    self.reason = reason
    for i = #self.events, 1, -1 do
        local e = self.events[i]
        pcall(event.unregister, e[1], e[2], e[3])
    end
    self.events = {}
    for i = #self.callbacks, 1, -1 do
        local c = self.callbacks[i]
        pcall(function()
            if c[4] then c[1]:unregisterAfter(c[2], c[3]) else c[1]:unregisterBefore(c[2], c[3]) end
        end)
    end
    self.callbacks = {}
    if self.menu then pcall(function() self.menu:destroy() end) end
    self.menu = nil
    self.elements = {}
    if windows[self.id] == self then windows[self.id] = nil end
    if self.enteredMenuMode then
        self.enteredMenuMode = false
        pcall(function()
            if tes3ui.menuMode() then tes3ui.leaveMenuMode() end
        end)
    end
    if self.onClose then pcall(self.onClose, self, reason) end
    updateLoadHandler()
    if reason ~= "load" then guard.focusConsole() end
end

--[[ spec = {
      id = "mwconsole:Inspector", title = "...", where = "open the effect inspector",
      build = function(menu, win) end,   -- builds the contents; may be called again on refresh
      modal = true,                      -- enters menu mode
      needsGame = true, dragFrame = false, onClose = function(win, reason) end, statusSetter = fn }
   returns the window record or nil ]]
function guard.openWindow(spec)
    local where = spec.where or ("open " .. tostring(spec.id))
    if spec.needsGame ~= false and not guard.isGameLoaded() then
        guard.needGame(spec.statusSetter)
        return nil
    end
    local existing = windows[spec.id]
    if existing and existing.menu then
        -- one instance: refresh in place
        existing.build = spec.build or existing.build
        local ok = guard.run(where, function()
            existing.menu:destroyChildren()
            existing.build(existing.menu, existing)
            existing.menu:updateLayout()
        end)
        if not ok then existing:close("error") return nil end
        pcall(tes3ui.moveMenuToFront, existing.menu)
        return existing
    end
    openSeq = openSeq + 1
    local win = setmetatable({ id = spec.id, build = spec.build, onClose = spec.onClose, events = {}, seq = openSeq,
                               callbacks = {}, elements = {}, closed = false, enteredMenuMode = false }, Window)
    windows[spec.id] = win
    updateLoadHandler()
    local ok = guard.run(where, function()
        local wasMenuMode = tes3ui.menuMode()
        local params = { id = spec.id, modal = false }
        if spec.dragFrame then params.dragFrame = true else params.fixedFrame = true end
        win.menu = tes3ui.createMenu(params)
        if spec.title and win.menu.text ~= nil then pcall(function() win.menu.text = spec.title end) end
        win.build(win.menu, win)
        win.menu:updateLayout()
        if spec.modal ~= false then
            tes3ui.enterMenuMode(spec.id)
            win.enteredMenuMode = not wasMenuMode
        end
        win:on("keyDown", function(e)
            if win.closed or (type(e) == "table" and e.mwconsoleEscape) then return end
            if guard.topWindow() ~= win then return end
            if type(e) == "table" then e.mwconsoleEscape = true end     -- one window per Esc press
            win:close("escape")
        end, { filter = tes3.scanCode.escape })
        -- unregistered before this window leaves menu mode itself, so this only sees someone else leaving it
        win:on("menuExit", function()
            if not win.closed then win:close("menu mode ended") end
        end)
    end)
    if not ok then
        win:close("error")
        return nil
    end
    return win
end

function guard.getWindow(id) return windows[id] end

--- the open window opened last (the one Esc closes)
function guard.topWindow()
    local top
    for _, w in pairs(windows) do
        if not w.closed and (not top or w.seq > top.seq) then top = w end
    end
    return top
end

function guard.closeAll(reason)
    local list = {}
    for _, w in pairs(windows) do list[#list + 1] = w end
    for _, w in ipairs(list) do w:close(reason) end
end

function guard.openCount()
    local n = 0
    for _ in pairs(windows) do n = n + 1 end
    return n
end

onLoad = function()
    gameLoaded = false
    guard.closeAll("load")
end

return guard
