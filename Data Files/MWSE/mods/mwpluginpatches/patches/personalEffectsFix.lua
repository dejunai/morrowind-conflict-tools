--[[mwdialog_luafix 3: F1]] local print, mwse, mwluafix_log = (function(_p, _m) local S = package.loaded["mwluafix_logshim:mwpluginpatches"] if type(S) == "table" and S.v == 3 then return S.print, S.mwse, S end S = { v = 3, redirected = 0, dropped = 0, collapsed = 0 } package.loaded["mwluafix_logshim:mwpluginpatches"] = S local C = { name = "mwpluginpatches", init = 0, after = 0, keep = { "error", "traceback", "exception", "fail", "warn", "stack", "attempt to", "assert", "invalid", "%.lua:%d+:", "^lua:", "initializ", "register", "start", "loaded", "ready", "version", "active" }, perSecond = 25, maxBytes = 2097152, keepOld = 1, flushSeconds = 2.0, errorRepeat = 0 } local G, MARK = _G, "mwdialog_luafix" local find, lower, sub, gsub, concat, fmt, date, select, tostring, pcall = string.find, string.lower, string.sub, string.gsub, table.concat, string.format, os.date, select, tostring, pcall local dir = "Data Files\\MWSE\\logs" local path, oldPath = dir .. "\\" .. C.name .. ".log", dir .. "\\" .. C.name .. ".old.log" local t0 = os.time() - math.floor(os.clock()) - 1 local init, run, started, redirected, f, dead, busy, fails = 0, 0, false, false, nil, false, false, 0 local bytes, dirty, last, lastN, sec, secN, dropped, errs, errKeys = 0, false, nil, 0, -1, 0, 0, {}, 0 local function isErr(t) local l = lower(#t > 4096 and sub(t, 1, 4096) or t) for i = 1, #C.keep do local ok, h = pcall(find, l, C.keep[i]) if ok and h then return true end end return false end local function out(s) f:write(date("[%H:%M:%S] "), s, "\n") bytes = bytes + #s + 12 dirty = true end local function pending() if lastN > 0 then out("[previous line repeated " .. lastN .. " more time(s)]") lastN = 0 end if dropped > 0 then out("[" .. dropped .. " line(s) dropped: more than " .. C.perSecond .. " in one second]") dropped = 0 end end local function flushAll() if f then pending() if dirty then dirty = false f:flush() end end end local function rotate() if f then pcall(f.close, f) f = nil end if C.keepOld > 0 then os.remove(oldPath) os.rename(path, oldPath) else os.remove(path) end f = io.open(path, "w") bytes, last = 0, nil if f then pcall(f.setvbuf, f, "full", 16384) f:write(date("[%Y-%m-%d %H:%M:%S] "), C.name, ": lines past its MWSE.log allowance (", MARK, ")\n") end return f end local function open() pcall(function() lfs.mkdir(dir) end) local ok, m = pcall(function() return lfs.attributes(path, "modification") end) if ok and type(m) == "number" and m >= t0 then path, oldPath = dir .. "\\" .. C.name .. ".luafix.log", dir .. "\\" .. C.name .. ".luafix.old.log" end return rotate() end local function toFile(t) if t == last then lastN = lastN + 1 S.collapsed = S.collapsed + 1 return end local s = os.time() if s ~= sec then sec, secN = s, 0 end secN = secN + 1 if C.perSecond > 0 and secN > C.perSecond then dropped = dropped + 1 S.dropped = S.dropped + 1 return end if bytes >= C.maxBytes and not rotate() then dead = true return end pending() last = t out(t) S.redirected = S.redirected + 1 if not started then dirty = false f:flush() end end S.start = function() if started then return end started = true pcall(flushAll) pcall(function() timer.start({ type = timer.real, duration = C.flushSeconds, iterations = -1, persist = false, callback = function() pcall(flushAll) end }) end) end local function route(t, force) if not started then local ok, v = pcall(function() return tes3.isInitialized() end) if ok and v then S.start() end end if force or isErr(t) then if C.errorRepeat > 0 then local k = gsub(sub(t, 1, (find(t, "\n", 1, true) or 201) - 1), "%d+", "#") local n = errs[k] or 0 if n == 0 then if errKeys >= 500 then errs, errKeys = {}, 0 end errKeys = errKeys + 1 end errs[k] = n + 1 if n >= C.errorRepeat then if f then toFile(t) end return false end end if not f and not dead then open() end if f then pending() out(t) dirty = false f:flush() end return true end local _, nl = gsub(t, "\n", "") nl = nl + 1 if not redirected then if started then if run + nl <= C.after then run = run + nl return true end elseif init + nl <= C.init then init = init + nl return true end redirected = true if not f and not open() then dead = true _p(fmt("[%s] %s writes a lot to MWSE.log, but %s can't be opened: leaving it here", MARK, C.name, path)) return true end _p(fmt("[%s] %s has written %d line(s) to MWSE.log; its further output goes to %s (errors still show here)", MARK, C.name, init + run, path)) end if dead or not f then return true end toFile(t) return false end local function fail(e) fails = fails + 1 if fails >= 10 then dead = true end if fails == 1 then pcall(_p, fmt("[%s] %s: log shim error (the line went to MWSE.log): %s", MARK, C.name, tostring(e))) end end local function decidePrint(n, ...) local t if n <= 1 then t = tostring((...)) else local parts = {} for i = 1, n do parts[i] = tostring((select(i, ...))) end t = concat(parts, "\t") end return route(t, false) end S.print = function(...) if busy or dead then return _p(...) end busy = true local ok, pass = pcall(decidePrint, select("#", ...), ...) busy = false if not ok then fail(pass) return _p(...) end if pass then return _p(...) end end local function decideLog(f0, ...) local ok, t = pcall(fmt, tostring(f0), ...) if not ok then t = tostring(f0) end return route(t, false) end S.mwse = setmetatable({ log = function(f0, ...) if busy or dead then return _m.log(f0, ...) end busy = true local ok, pass = pcall(decideLog, f0, ...) busy = false if not ok then fail(pass) pass = true end if pass then return _m.log(f0, ...) end end }, { __index = _m, __newindex = _m }) local function back(g, ok, ...) if G.print == S.print then G.print = g end if not ok then error((...), 0) end return ... end local wrapped = setmetatable({}, { __mode = "k" }) local LV = { trace = 5, debug = 4, info = 3 } local function wrap(lg) for name, lv in pairs(LV) do local orig = lg[name] if type(orig) == "function" then rawset(lg, name, function(self, ...) if dead or self ~= lg or G.print == S.print then return orig(self, ...) end local sd = type(lg.makeRecord) == "function" and type(lg.writeRecord) == "function" and lg.sharedData if sd and type(sd.level) == "number" then if sd.level < lv then return end local rec = lg:makeRecord(lv) local g = G.print G.print = S.print return back(g, pcall(lg.writeRecord, lg, rec, ...)) end local g = G.print G.print = S.print return back(g, pcall(orig, self, ...)) end) end end end S.wrap = function(lg) if type(lg) == "table" and not wrapped[lg] then wrapped[lg] = true pcall(wrap, lg) end return lg end S.flush = flushAll S.stats = function() return { init = init, run = run, redirected = redirected, dead = dead, path = path, fails = fails, started = started } end pcall(function() event.register("initialized", S.start) for _, ev in ipairs({ "loaded", "save", "menuEnter" }) do event.register(ev, function() pcall(flushAll) end) end end) pcall(function() local p = newproxy(true) getmetatable(p).__gc = function() pcall(flushAll) end S.gc = p end) return S.print, S.mwse, S end)(print, mwse) --[[/mwluafix_logshim]] local config = require("mwpluginpatches.config")

local personalEffectsFix = {}

local CLASS_CONTAINERS = {
    [-1] = { cont = "R0_pe_cont_other",       inv = "R0_pe_inventory_other" },
    [1]  = { cont = "R0_pe_cont_acrobat",     inv = "R0_pe_inventory_acrobat" },
    [2]  = { cont = "R0_pe_cont_agent",       inv = "R0_pe_inventory_agent" },
    [3]  = { cont = "R0_pe_cont_archer",      inv = "R0_pe_inventory_archer" },
    [4]  = { cont = "R0_pe_cont_assassin",    inv = "R0_pe_inventory_assassin" },
    [5]  = { cont = "R0_pe_cont_barbarian",   inv = "R0_pe_inventory_barbarian" },
    [6]  = { cont = "R0_pe_cont_bard",        inv = "R0_pe_inventory_bard" },
    [7]  = { cont = "R0_pe_cont_battlemage",  inv = "R0_pe_inventory_battlemage" },
    [8]  = { cont = "R0_pe_cont_crusader",    inv = "R0_pe_inventory_crusader" },
    [9]  = { cont = "R0_pe_cont_healer",      inv = "R0_pe_inventory_healer" },
    [10] = { cont = "R0_pe_cont_knight",      inv = "R0_pe_inventory_knight" },
    [11] = { cont = "R0_pe_cont_mage",        inv = "R0_pe_inventory_mage" },
    [12] = { cont = "R0_pe_cont_monk",        inv = "R0_pe_inventory_monk" },
    [13] = { cont = "R0_pe_cont_nightblade",  inv = "R0_pe_inventory_nightblade" },
    [14] = { cont = "R0_pe_cont_pilgrim",     inv = "R0_pe_inventory_pilgrim" },
    [15] = { cont = "R0_pe_cont_rogue",       inv = "R0_pe_inventory_rogue" },
    [16] = { cont = "R0_pe_cont_scout",       inv = "R0_pe_inventory_scout" },
    [17] = { cont = "R0_pe_cont_sorcerer",    inv = "R0_pe_inventory_sorcerer" },
    [18] = { cont = "R0_pe_cont_sorcerer",    inv = "R0_pe_inventory_sorcerer" },
    [19] = { cont = "R0_pe_cont_thief",       inv = "R0_pe_inventory_thief" },
    [20] = { cont = "R0_pe_cont_warrior",     inv = "R0_pe_inventory_warrior" },
    [21] = { cont = "R0_pe_cont_witchhunter", inv = "R0_pe_inventory_witchhunter" },
}

local CLASS_NAME_TO_INDEX = {
    ["acrobat"]     = 1,
    ["agent"]       = 2,
    ["archer"]      = 3,
    ["assassin"]    = 4,
    ["barbarian"]   = 5,
    ["bard"]        = 6,
    ["battlemage"]  = 7,
    ["crusader"]    = 8,
    ["healer"]      = 9,
    ["knight"]      = 10,
    ["mage"]        = 11,
    ["monk"]        = 12,
    ["nightblade"]  = 13,
    ["pilgrim"]     = 14,
    ["rogue"]       = 15,
    ["scout"]       = 16,
    ["sorcerer"]    = 17,
    ["spellsword"]  = 18,
    ["thief"]       = 19,
    ["warrior"]     = 20,
    ["witchhunter"] = 21,
}

local function restoreSellusFacing()
    local pCell = tes3.player and tes3.player.cell
    if not pCell or not pCell.id or not pCell.id:lower():find("census and excise") then
        return
    end

    local captain = tes3.getReference("chargen captain")
    if captain and captain.cell == pCell and captain.sceneNode then
        local targetFacing = -math.pi / 2
        captain.facing = targetFacing
        captain.orientation = tes3vector3.new(0, 0, targetFacing)
        pcall(captain.updateSceneGraph, captain)
    end
end

local function restoreDoorGuardFacing()
    local pCell = tes3.player and tes3.player.cell
    if not pCell or not pCell.id or not pCell.id:lower():find("census and excise") then
        return
    end

    local guard = tes3.getReference("chargen door guard")
    if guard and guard.cell == pCell and guard.sceneNode then
        -- Do not snap facing while actively in dialogue with the door guard
        local menuDialog = tes3ui.findMenu(tes3ui.registerID("MenuDialog"))
        if menuDialog then
            local mobileActor = menuDialog:getPropertyObject("PartHyperText_actor")
            if mobileActor and mobileActor.reference == guard then
                return
            end
        end

        local targetFacing = math.pi -- 180 degrees: facing South directly into the room
        if math.abs(guard.facing - targetFacing) > 0.05 then
            guard.facing = targetFacing
            guard.orientation = tes3vector3.new(0, 0, targetFacing)
            pcall(guard.updateSceneGraph, guard)
        end
    end
end

--- Executes the chest placement, unlocking, and item distribution cleanly in Lua,
--- stopping and bypassing the legacy R0_pe_init_scr so Face 1605 -376 never executes.
local function handlePersonalEffectsUnlock()
    local cell = tes3.player and tes3.player.cell
    if not cell or not cell.id:lower():find("census and excise") then
        return
    end

    local baseCont = tes3.getReference("R0_pe_basecont")
    if not baseCont then
        return
    end

    -- Determine class container
    local pClass = tes3.player and tes3.player.object and tes3.player.object.class
    local classId = pClass and pClass.id and pClass.id:lower() or ""
    local classIndex = CLASS_NAME_TO_INDEX[classId]
    local entry

    if classIndex and CLASS_CONTAINERS[classIndex] then
        entry = CLASS_CONTAINERS[classIndex]
    elseif pClass then
        -- Match custom classes by specialization!
        local spec = pClass.specialization
        if spec == tes3.specialization.combat then
            entry = CLASS_CONTAINERS[20] -- warrior
        elseif spec == tes3.specialization.magic then
            entry = CLASS_CONTAINERS[11] -- mage
        elseif spec == tes3.specialization.stealth then
            entry = CLASS_CONTAINERS[19] -- thief
        else
            entry = CLASS_CONTAINERS[-1] -- other
        end
    else
        entry = CLASS_CONTAINERS[-1]
    end

    -- 1. UNLOCK and REMOVE CRIME OWNERSHIP from the chest
    tes3.unlock({ reference = baseCont })
    if baseCont.lockNode then
        baseCont.lockNode.locked = false
        baseCont.lockNode.level = 0
    end
    tes3.setOwner({ reference = baseCont, remove = true })
    baseCont:enable()

    -- 2. Populate chest with class personal effects if empty
    local contObj = tes3.getObject(entry.cont)
    if contObj and contObj.inventory then
        local hasItems = false
        if baseCont.object and baseCont.object.inventory then
            for _ in pairs(baseCont.object.inventory) do
                hasItems = true
                break
            end
        end

        if not hasItems then
            for _, stack in pairs(contObj.inventory) do
                tes3.addItem({
                    reference = baseCont,
                    item = stack.object,
                    count = stack.count,
                    playSound = false,
                })
            end
        end
    end

    -- 3. Add personal effects inventory receipt note to player
    if tes3.getObject(entry.inv) then
        if tes3.getItemCount({ reference = tes3.player, item = entry.inv }) == 0 then
            tes3.addItem({
                reference = tes3.player,
                item = entry.inv,
                count = 1,
                playSound = false,
            })
        end
    end

    -- 4. Play unlock sound
    tes3.playSound({ sound = "Open Lock", reference = tes3.player })

    -- 5. Delete any stray spawned duplicate chests from previous runs
    for ref in cell:iterateReferences(tes3.objectType.container) do
        if ref ~= baseCont and ref.baseObject and ref.baseObject.id:lower():find("^r0_pe_cont_") then
            if ref.object and ref.object.inventory then
                for _, stack in pairs(ref.object.inventory) do
                    tes3.addItem({
                        reference = baseCont,
                        item = stack.object,
                        count = stack.count,
                        playSound = false,
                    })
                end
            end
            ref:disable()
            ref.position = tes3vector3.new(ref.position.x, ref.position.y, ref.position.z - 10000)
            ref.modified = true
        end
    end

    baseCont.modified = true
    restoreSellusFacing()

    mwse.log("[mwpluginpatches] Personal effects chest unlocked, ownership cleared, and loaded with items for class '%s'.", classId)
end

function personalEffectsFix.init()
    if not config.personalEffectsFixEnabled or not config.isPersonalEffectsActive() then
        return
    end

    -- Completely override legacy mwscript R0_pe_init_scr with our Lua handler
    mwse.overrideScript("R0_pe_init_scr", function()
        handlePersonalEffectsUnlock()
        mwscript.stopScript({ script = "R0_pe_init_scr" })
    end)

    -- Completely override R0_pe_basecont_scr (the legacy script containing 'PlaceAtPC Player 1 128 1')
    mwse.overrideScript("R0_pe_basecont_scr", function()
        mwscript.stopScript({ script = "R0_pe_basecont_scr" })
    end)

    -- Completely override R0_pe_MWSE_scr
    mwse.overrideScript("R0_pe_MWSE_scr", function()
        mwscript.stopScript({ script = "R0_pe_MWSE_scr" })
    end)

    -- Guard against Sellus Gravius and Door Guard rotating when dialogue ends, and trigger unlock
    event.register(tes3.event.uiActivated, function(e)
        local mobileActor = e.element:getPropertyObject("PartHyperText_actor")
        local ref = mobileActor and mobileActor.reference
        if ref and ref.baseObject then
            local refId = ref.baseObject.id:lower()
            if refId == "chargen captain" then
                e.element:registerAfter(tes3.uiEvent.destroy, function()
                    timer.frame.delayOneFrame(function()
                        restoreSellusFacing()
                        if tes3.getJournalIndex({ id = "A1_1_FindSpymaster" }) >= 1 then
                            handlePersonalEffectsUnlock()
                        end
                    end)
                end)
            elseif refId == "chargen door guard" then
                e.element:registerAfter(tes3.uiEvent.destroy, function()
                    timer.frame.delayOneFrame(function()
                        restoreDoorGuardFacing()
                    end)
                end)
            end
        end
    end, { filter = "MenuDialog" })

    -- Also ensure chest is unlocked and filled if activated directly
    event.register("activate", function(e)
        if e.target and e.target.baseObject and e.target.baseObject.id:lower() == "r0_pe_basecont" then
            if tes3.getJournalIndex({ id = "A1_1_FindSpymaster" }) >= 1 then
                handlePersonalEffectsUnlock()
            end
        end
    end)

    local function isClone(ref)
        if not ref or ref == tes3.player then return false end
        if ref.objectType ~= tes3.objectType.npc then return false end

        -- 0. Explicit match on PlayerSaveGame dynamic player duplicate
        local refId = ref.id and ref.id:lower()
        if refId and refId:find("playersavegame") then return true end

        -- 1. Base object ID is 'player'
        local baseId = ref.baseObject and ref.baseObject.id and ref.baseObject.id:lower()
        if baseId == "player" then return true end

        -- 2. Object matches player object
        if tes3.player and tes3.player.object and ref.object == tes3.player.object then
            return true
        end

        -- 3. Name matches player name or default engine 'Player'
        local playerName = tes3.player and tes3.player.object and tes3.player.object.name
        if ref.object and ref.object.name then
            if playerName and playerName ~= "" and ref.object.name == playerName then
                return true
            end
            if ref.object.name == "Player" then
                return true
            end
        end

        return false
    end

    local function purgeStaleClones()
        local cell = tes3.player and tes3.player.cell
        if cell and cell.id:lower():find("census and excise") then
            local toPurge = {}
            for ref in cell:iterateReferences(tes3.objectType.npc) do
                if isClone(ref) then
                    table.insert(toPurge, ref)
                end
            end
            for _, ref in ipairs(toPurge) do
                local refName = (ref.object and ref.object.name) or "Unknown"
                local refId = (ref.baseObject and ref.baseObject.id) or ref.id or "unknown"
                mwse.log("[mwpluginpatches] Detected and purged player clone '%s' [%s] at (%.1f, %.1f, %.1f) in %s",
                    refName, refId, ref.position.x, ref.position.y, ref.position.z, cell.id)
                pcall(function()
                    ref.position = tes3vector3.new(ref.position.x, ref.position.y, ref.position.z - 10000)
                    ref:disable()
                    ref.modified = true
                end)
            end
        end
    end

    local function schedulePurge()
        local cell = tes3.player and tes3.player.cell
        if not cell or not cell.id or not cell.id:lower():find("census and excise") then
            return
        end
        purgeStaleClones()
        restoreSellusFacing()
        restoreDoorGuardFacing()
        timer.frame.delayOneFrame(function()
            local currentCell = tes3.player and tes3.player.cell
            if currentCell and currentCell.id and currentCell.id:lower():find("census and excise") then
                purgeStaleClones()
                restoreSellusFacing()
                restoreDoorGuardFacing()
            end
        end)
        timer.start({ duration = 0.5, type = timer.real, callback = function()
            local currentCell = tes3.player and tes3.player.cell
            if currentCell and currentCell.id and currentCell.id:lower():find("census and excise") then
                purgeStaleClones()
                restoreSellusFacing()
                restoreDoorGuardFacing()
            end
        end })
    end

    -- Clean up any stale player clone in Census and Excise (from in-game New Game restarts)
    event.register(tes3.event.loaded, schedulePurge)
    event.register(tes3.event.cellChanged, schedulePurge)

    -- Also purge when entering dialogue in Census & Excise
    event.register(tes3.event.uiActivated, function(e)
        purgeStaleClones()
    end, { filter = "MenuDialog" })

    -- Continuous background check while player is in Census & Excise
    -- MWSE cancels every timer just before `loaded`, so it is started again there
    local function startBackgroundCheck()
        timer.start({
            duration = 1.0,
            type = timer.real,
            iterations = -1,
            callback = function()
                local cell = tes3.player and tes3.player.cell
                if cell and cell.id:lower():find("census and excise") then
                    purgeStaleClones()
                    restoreDoorGuardFacing()
                end
            end
        })
    end
    startBackgroundCheck()
    event.register(tes3.event.loaded, startBackgroundCheck)

    mwse.log("[mwpluginpatches] Personal Effects Sellus Gravius & Census Door Guard script overrides and facing fixes active.")
end

return personalEffectsFix
