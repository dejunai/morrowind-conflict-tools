--[[
    mwexitguard / newgame - no second New Game in one Morrowind session.
    Part of the mwsuite. By dej (dejunai).

    MGE XE does not unload and reset when a game is started over inside a running session, and neither do many Lua
    mods, so a New Game after a save has been loaded (or after a first New Game) cannot be trusted to behave. Once a
    game has been loaded in this session, New Game is blocked until Morrowind is restarted. Loading a save is never
    blocked, and the first New Game from the title screen after launch works as always.

    Two layers, so the block does not depend on the button:
      * the `load` event with newGame == true is blocked (and claimed, so no other mod sees a new game begin). That is
        the one place every way into a new game passes: the menu button, another mod calling tes3.newGame(), and a
        tes3.newGame() typed into the MWSE Lua console.
      * the New Game button of MenuOptions (MenuOptions_New_container) is dimmed, shows a short tooltip, and its click
        shows a one-line message instead of the game's own confirmation. The menu is touched only when it opens
        (uiActivated filtered to MenuOptions, and menuEnter), and only once a game has been loaded.
    The session is marked used by the first `loaded` event (a loaded save or a new game, both fire it).

    Idea: Petethegoat's "Continue" (Nexus Mods Morrowind 45952, public domain) has an option to hide the New Game
    button while in game; this builds on that idea. The code here is our own.

    Switched on or off with blockNewGameInSession (mwexitguard's MCM page); it is read when the game starts, so the
    setting needs a restart. When it is off, nothing is registered here.
]]--

local config = require("mwexitguard.config")

local this = {}

local MENU = "MenuOptions"
local NEW_BUTTON = "MenuOptions_New_container"
local DONE = "mwexitguard:newGameBlocked"        -- property set on the button once it has been patched
local DIM = 0.4

this.MESSAGE = "New Game is off while Morrowind is running a game. Restart Morrowind to start a new game "
    .. "(MGE XE can't reset in-session)."
this.TOOLTIP = "Restart Morrowind to start a new game."

local used = false                                -- a save has been loaded, or a new game started, this session
local registered = false

function this.isUsed() return used end

local function active()
    return used and config.blockNewGameInSession ~= false
end

local function toast()
    pcall(tes3.messageBox, this.MESSAGE)
end

-- the title screen after a death shows the main menu again: keep it up so the player is not left without it
local function restoreMainMenu()
    if not tes3.onMainMenu() then return end
    local menu = tes3ui.findMenu(tes3ui.registerID(MENU))
    if menu then menu.visible = true end
    tes3ui.enterMenuMode()
end

local function dim(element)
    pcall(function() element.alpha = DIM end)
    for _, child in ipairs(element.children or {}) do dim(child) end
end

local function wire(element, click, tooltip)
    element:register("mouseClick", click)
    element:register("help", tooltip)
    for _, child in ipairs(element.children or {}) do wire(child, click, tooltip) end
end

local function onClick()
    pcall(function() tes3.worldController.menuClickSound:play() end)
    toast()
end

local function onTooltip()
    local tip = tes3ui.createTooltipMenu()
    tip:createLabel({ text = this.TOOLTIP })
end

--- puts the block on a MenuOptions element (once per element); returns true if the button was patched
function this.patchMenu(menu)
    if not menu then return false end
    local button = menu:findChild(tes3ui.registerID(NEW_BUTTON))
    if not button then return false end
    if button:getPropertyBool(DONE) then return true end
    button:setPropertyBool(DONE, true)
    dim(button)
    wire(button, onClick, onTooltip)
    pcall(function() menu:updateLayout() end)
    return true
end

function this.onUiActivated(e)
    if active() then this.patchMenu(e.element) end
end

function this.onMenuEnter()
    if not active() then return end
    this.patchMenu(tes3ui.findMenu(tes3ui.registerID(MENU)))
end

function this.onLoad(e)
    if e.newGame ~= true or not active() then return end
    toast()
    pcall(restoreMainMenu)
    mwse.log("[mwexitguard] New Game blocked: a game was already loaded in this session; restart Morrowind.")
    return false
end

function this.onLoaded()
    used = true
    this.onMenuEnter()
end

function this.init()
    if registered or config.blockNewGameInSession == false then return false end
    registered = true
    event.register("load", this.onLoad, { priority = 9100 })
    event.register("loaded", this.onLoaded)
    event.register("uiActivated", this.onUiActivated, { filter = MENU })
    event.register("menuEnter", this.onMenuEnter)
    mwse.log("[mwexitguard] New Game will be blocked once a game is loaded (restart Morrowind to start another).")
    return true
end

return this