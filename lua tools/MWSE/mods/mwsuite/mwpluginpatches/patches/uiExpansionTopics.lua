--[[
UI Expansion colours the dialogue topics once, on MenuDialog's first preUpdate, and from there on only when one of
the rows it coloured is clicked. MenuDialog's uiActivated comes before the game has built any topic row: a mod that
lays the menu out right there (ImmersiveTravel does, for NPCs who offer travel) spends that one shot on an empty
list, and every topic stays amber for the whole conversation. Which handler runs first changes with the number of
handlers, as MWSE's sort doesn't keep the order of equal priorities.

So the handlers after this one on preUpdate wait until a topic row exists. The engine ignores what preUpdate
returns, and its own handler has already run by then. This handler never unregisters itself: two handlers doing
that inside one event is a crash (see RESUME).
]]

local this = {}

local FIRST = 1000000                       -- the element's preUpdate: before any painter
local FIRST_EVENT = 9999                    -- uiActivated: before any mod can lay the menu out

local function waitForTopics(e)
    if not e.source:findChild("MenuDialog_a_topic") then return false end
end

function this.init()
    event.register(tes3.event.uiActivated, function(e)
        if e.newlyCreated then e.element:registerAfter("preUpdate", waitForTopics, FIRST) end
    end, { filter = "MenuDialog", priority = FIRST_EVENT })
    mwse.log("[mwpluginpatches] UI Expansion: topic colours wait until the topic list exists.")
end

return this
