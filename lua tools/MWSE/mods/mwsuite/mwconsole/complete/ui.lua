--[[
    mwconsole completion UI: Tab / Shift+Tab on the console input, Ctrl+Left / Ctrl+Right to switch mode, and the
    suggestion line under the input. Attached once per console element (console_ui.markAttached).
]]
local config = require("mwconsole.config")
local console_ui = require("mwconsole.console_ui")
local engine = require("mwconsole.complete.engine")
local index = require("mwconsole.complete.index")

local ui = {}
ui.HINT = "mwconsole:Hint"
ui.LIVE_BUDGET_MS = 2

local state = nil           -- Tab cycle: { shown = text after the last fill, before, after, ctx, list, i, mode }

local function inputController()
    local ok, ic = pcall(function() return tes3.worldController.inputController end)
    return ok and ic or nil
end
local function shiftDown() local ic = inputController() return ic and ic:isShiftDown() or false end
local function ctrlDown() local ic = inputController() return ic and ic:isControlDown() or false end

local function setHint(menu, text)
    local hint = menu and menu:findChild(ui.HINT)
    if not hint then return end
    hint.text = text or ""
    hint.visible = text ~= nil and text ~= ""
end

function ui.ensureIndex()
    if not index.built then
        index.build(nil, { topics = config.complete.topics })
    end
end

--- Tab: fill in the next (or previous) candidate
function ui.complete(menu, input, backwards)
    local text = input.text or ""
    local mode = console_ui.getMode(menu)
    if state and state.shown == text and state.mode == mode and #state.list > 0 then
        state.i = backwards and (state.i - 2) % #state.list + 1 or state.i % #state.list + 1
    else
        ui.ensureIndex()
        local before, after = console_ui.splitCursor(text)
        local ctx = engine.analyze(before, mode)
        local list = engine.candidates(ctx, { limit = 200, substring = true, budgetMs = 15 })
        if #list == 0 then
            state = nil
            setHint(menu, "no matches")
            return false
        end
        state = { before = before, after = after, ctx = ctx, list = list, i = backwards and #list or 1, mode = mode }
    end
    local newBefore = engine.apply(state.before, state.ctx, state.list[state.i], mode)
    local newText = console_ui.joinCursor(newBefore, state.after)
    input.text = newText
    state.shown = newText
    setHint(menu, string.format("%s  (%d/%d, Tab next, Shift+Tab back)", state.list[state.i], state.i, #state.list))
    pcall(function() menu:updateLayout() end)
    return true
end

--- after a key: the best matches under the input, within a time budget
function ui.live(menu, input)
    if not config.complete.live then return end
    local t0 = os.clock()
    local before = console_ui.splitCursor(input.text or "")
    local mode = console_ui.getMode(menu)
    local ctx = engine.analyze(before, mode)
    if ctx.what == "none" or #ctx.prefix < (config.complete.minChars or 2) then
        setHint(menu, "")
        return
    end
    if engine.ID_KINDS[ctx.kind or ""] and not index.built then
        setHint(menu, "Tab for suggestions")
        return
    end
    local list = engine.candidates(ctx, { limit = 5 })
    if (os.clock() - t0) * 1000 > ui.LIVE_BUDGET_MS then
        setHint(menu, "Tab for suggestions")
        return
    end
    setHint(menu, #list > 0 and (table.concat(list, "   ") .. "   (Tab)") or "")
end

function ui.onKeyPress(menu, input, e)
    local key = e.data0
    if key == console_ui.KEY_TAB then
        if config.enabled and config.complete.on then
            pcall(ui.complete, menu, input, shiftDown())
        end
        return false                                   -- never insert a Tab character
    end
    if (key == console_ui.KEY_LEFT or key == console_ui.KEY_RIGHT) and ctrlDown() then
        console_ui.toggleMode(menu)
        return false
    end
    state = nil                                        -- any other key accepts the current fill
end

function ui.onKeyPressAfter(menu, input)
    if not config.enabled or not config.complete.on then return end
    if state and state.shown == input.text then return end
    pcall(ui.live, menu, input)
end

--- attach to a console menu once
function ui.attach(menu)
    local input = console_ui.findInput(menu)
    if not input then return false end
    local row = input.parent and input.parent.parent
    local host = row and row.parent or menu
    if not host:findChild(ui.HINT) then
        local hint = host:createLabel({ id = ui.HINT, text = "" })
        hint.visible = false
        pcall(function() hint.color = tes3ui.getPalette("disabled_color") end)
    end
    input:registerBefore("keyPress", function(e) return ui.onKeyPress(menu, input, e) end)
    input:registerAfter("keyPress", function() ui.onKeyPressAfter(menu, input) end)
    return true
end

function ui.resetCycle() state = nil end

return ui
