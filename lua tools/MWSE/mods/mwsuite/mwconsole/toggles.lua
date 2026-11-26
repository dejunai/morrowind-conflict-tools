--[[
    mwconsole quick toggles: ResetActors, ToggleCollision, ToggleMenus on keys. Off by default with no keys bound.
    Never fire while typing or in any menu (tes3.menuMode() covers the console and every text field), and only on an
    exact modifier match. Style "press": one press runs the command. Style "hold": key-down runs it, key-up runs it
    again (collision and menus only), so the state can't drift.
]]
local config = require("mwconsole.config")
local guard = require("mwconsole.guard")

local toggles = {}

toggles.LIST = {
    { key = "ra", command = "ResetActors", hold = false, label = "Reset actors" },
    { key = "tcl", command = "ToggleCollision", hold = true, label = "Toggle collision" },
    { key = "tm", command = "ToggleMenus", hold = true, label = "Toggle HUD" },
}

local registered = { down = false, up = false }
local held = {}

local function bound(t)
    local k = config.toggles[t.key]
    return type(k) == "table" and type(k.keyCode) == "number" and k.keyCode > 0
end

function toggles.anyBound()
    for _, t in ipairs(toggles.LIST) do if bound(t) then return true end end
    return false
end

function toggles.run(command)
    local source = tes3.compilerSource and tes3.compilerSource.console or nil
    return tes3.runLegacyScript({ command = command, source = source })
end

local function blocked()
    if tes3.menuMode() then return true end
    if not guard.isGameLoaded() then return true end
    return false
end

local function matches(t, e)
    return bound(t) and tes3.isKeyEqual({ actual = e, expected = config.toggles[t.key] })
end

function toggles.onKeyDown(e)
    if not config.enabled or not config.toggles.on or blocked() then return end
    for _, t in ipairs(toggles.LIST) do
        if matches(t, e) and not held[t.key] then
            guard.run("run " .. t.command, toggles.run, t.command)
            if config.toggles.style == "hold" and t.hold then held[t.key] = true end
        end
    end
end

function toggles.onKeyUp(e)
    if not config.enabled or not config.toggles.on then return end
    for _, t in ipairs(toggles.LIST) do
        if held[t.key] and e.keyCode == config.toggles[t.key].keyCode then
            held[t.key] = nil
            guard.run("run " .. t.command, toggles.run, t.command)   -- runs even in a menu: puts the state back
        end
    end
end

--- (re)register keyDown/keyUp only when the switches are on and a key is bound
function toggles.update()
    local want = config.enabled and config.toggles.on and toggles.anyBound()
    local wantUp = want and config.toggles.style == "hold"
    if want and not registered.down then
        event.register("keyDown", toggles.onKeyDown)
        registered.down = true
    elseif not want and registered.down then
        event.unregister("keyDown", toggles.onKeyDown)
        registered.down = false
    end
    if wantUp and not registered.up then
        event.register("keyUp", toggles.onKeyUp)
        registered.up = true
    elseif not wantUp and registered.up then
        event.unregister("keyUp", toggles.onKeyUp)
        registered.up = false
    end
end

function toggles.isRegistered() return registered.down, registered.up end

return toggles
