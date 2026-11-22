--[[mwdialog_luafix 3: F1]] local print, mwse, mwluafix_log = (function(_p, _m) local S = package.loaded["mwluafix_logshim:mweffectinspector"] if type(S) == "table" and S.v == 3 then return S.print, S.mwse, S end S = { v = 3, redirected = 0, dropped = 0, collapsed = 0 } package.loaded["mwluafix_logshim:mweffectinspector"] = S local C = { name = "mweffectinspector", init = 0, after = 0, keep = { "error", "traceback", "exception", "fail", "warn", "stack", "attempt to", "assert", "invalid", "%.lua:%d+:", "^lua:", "initializ", "register", "start", "loaded", "ready", "version", "active" }, perSecond = 25, maxBytes = 2097152, keepOld = 1, flushSeconds = 2.0, errorRepeat = 0 } local G, MARK = _G, "mwdialog_luafix" local find, lower, sub, gsub, concat, fmt, date, select, tostring, pcall = string.find, string.lower, string.sub, string.gsub, table.concat, string.format, os.date, select, tostring, pcall local dir = "Data Files\\MWSE\\logs" local path, oldPath = dir .. "\\" .. C.name .. ".log", dir .. "\\" .. C.name .. ".old.log" local t0 = os.time() - math.floor(os.clock()) - 1 local init, run, started, redirected, f, dead, busy, fails = 0, 0, false, false, nil, false, false, 0 local bytes, dirty, last, lastN, sec, secN, dropped, errs, errKeys = 0, false, nil, 0, -1, 0, 0, {}, 0 local function isErr(t) local l = lower(#t > 4096 and sub(t, 1, 4096) or t) for i = 1, #C.keep do local ok, h = pcall(find, l, C.keep[i]) if ok and h then return true end end return false end local function out(s) f:write(date("[%H:%M:%S] "), s, "\n") bytes = bytes + #s + 12 dirty = true end local function pending() if lastN > 0 then out("[previous line repeated " .. lastN .. " more time(s)]") lastN = 0 end if dropped > 0 then out("[" .. dropped .. " line(s) dropped: more than " .. C.perSecond .. " in one second]") dropped = 0 end end local function flushAll() if f then pending() if dirty then dirty = false f:flush() end end end local function rotate() if f then pcall(f.close, f) f = nil end if C.keepOld > 0 then os.remove(oldPath) os.rename(path, oldPath) else os.remove(path) end f = io.open(path, "w") bytes, last = 0, nil if f then pcall(f.setvbuf, f, "full", 16384) f:write(date("[%Y-%m-%d %H:%M:%S] "), C.name, ": lines past its MWSE.log allowance (", MARK, ")\n") end return f end local function open() pcall(function() lfs.mkdir(dir) end) local ok, m = pcall(function() return lfs.attributes(path, "modification") end) if ok and type(m) == "number" and m >= t0 then path, oldPath = dir .. "\\" .. C.name .. ".luafix.log", dir .. "\\" .. C.name .. ".luafix.old.log" end return rotate() end local function toFile(t) if t == last then lastN = lastN + 1 S.collapsed = S.collapsed + 1 return end local s = os.time() if s ~= sec then sec, secN = s, 0 end secN = secN + 1 if C.perSecond > 0 and secN > C.perSecond then dropped = dropped + 1 S.dropped = S.dropped + 1 return end if bytes >= C.maxBytes and not rotate() then dead = true return end pending() last = t out(t) S.redirected = S.redirected + 1 if not started then dirty = false f:flush() end end S.start = function() if started then return end started = true pcall(flushAll) pcall(function() timer.start({ type = timer.real, duration = C.flushSeconds, iterations = -1, persist = false, callback = function() pcall(flushAll) end }) end) end local function route(t, force) if not started then local ok, v = pcall(function() return tes3.isInitialized() end) if ok and v then S.start() end end if force or isErr(t) then if C.errorRepeat > 0 then local k = gsub(sub(t, 1, (find(t, "\n", 1, true) or 201) - 1), "%d+", "#") local n = errs[k] or 0 if n == 0 then if errKeys >= 500 then errs, errKeys = {}, 0 end errKeys = errKeys + 1 end errs[k] = n + 1 if n >= C.errorRepeat then if f then toFile(t) end return false end end if not f and not dead then open() end if f then pending() out(t) dirty = false f:flush() end return true end local _, nl = gsub(t, "\n", "") nl = nl + 1 if not redirected then if started then if run + nl <= C.after then run = run + nl return true end elseif init + nl <= C.init then init = init + nl return true end redirected = true if not f and not open() then dead = true _p(fmt("[%s] %s writes a lot to MWSE.log, but %s can't be opened: leaving it here", MARK, C.name, path)) return true end _p(fmt("[%s] %s has written %d line(s) to MWSE.log; its further output goes to %s (errors still show here)", MARK, C.name, init + run, path)) end if dead or not f then return true end toFile(t) return false end local function fail(e) fails = fails + 1 if fails >= 10 then dead = true end if fails == 1 then pcall(_p, fmt("[%s] %s: log shim error (the line went to MWSE.log): %s", MARK, C.name, tostring(e))) end end local function decidePrint(n, ...) local t if n <= 1 then t = tostring((...)) else local parts = {} for i = 1, n do parts[i] = tostring((select(i, ...))) end t = concat(parts, "\t") end return route(t, false) end S.print = function(...) if busy or dead then return _p(...) end busy = true local ok, pass = pcall(decidePrint, select("#", ...), ...) busy = false if not ok then fail(pass) return _p(...) end if pass then return _p(...) end end local function decideLog(f0, ...) local ok, t = pcall(fmt, tostring(f0), ...) if not ok then t = tostring(f0) end return route(t, false) end S.mwse = setmetatable({ log = function(f0, ...) if busy or dead then return _m.log(f0, ...) end busy = true local ok, pass = pcall(decideLog, f0, ...) busy = false if not ok then fail(pass) pass = true end if pass then return _m.log(f0, ...) end end }, { __index = _m, __newindex = _m }) local function back(g, ok, ...) if G.print == S.print then G.print = g end if not ok then error((...), 0) end return ... end local wrapped = setmetatable({}, { __mode = "k" }) local LV = { trace = 5, debug = 4, info = 3 } local function wrap(lg) for name, lv in pairs(LV) do local orig = lg[name] if type(orig) == "function" then rawset(lg, name, function(self, ...) if dead or self ~= lg or G.print == S.print then return orig(self, ...) end local sd = type(lg.makeRecord) == "function" and type(lg.writeRecord) == "function" and lg.sharedData if sd and type(sd.level) == "number" then if sd.level < lv then return end local rec = lg:makeRecord(lv) local g = G.print G.print = S.print return back(g, pcall(lg.writeRecord, lg, rec, ...)) end local g = G.print G.print = S.print return back(g, pcall(orig, self, ...)) end) end end end S.wrap = function(lg) if type(lg) == "table" and not wrapped[lg] then wrapped[lg] = true pcall(wrap, lg) end return lg end S.flush = flushAll S.stats = function() return { init = init, run = run, redirected = redirected, dead = dead, path = path, fails = fails, started = started } end pcall(function() event.register("initialized", S.start) for _, ev in ipairs({ "loaded", "save", "menuEnter" }) do event.register(ev, function() pcall(flushAll) end) end end) pcall(function() local p = newproxy(true) getmetatable(p).__gc = function() pcall(flushAll) end S.gc = p end) return S.print, S.mwse, S end)(print, mwse) --[[/mwluafix_logshim]] local config = require("mweffectinspector.config")

local inspector = {}

local GUI_ID_WINDOW = tes3ui.registerID("mweffectinspector:Window")

local spellTypeNames = {
    [0] = "Spell",
    [1] = "Ability (Constant)",
    [2] = "Blight",
    [3] = "Disease",
    [4] = "Curse",
    [5] = "Power",
}

function inspector.getTargetRef()
    local consoleRef = tes3ui.getConsoleReference()
    if consoleRef then
        return consoleRef
    end
    local menuConsole = tes3ui.findMenu("MenuConsole")
    if menuConsole then
        local currentRef = menuConsole:getPropertyObject("MenuConsole_current_ref")
        if currentRef then
            return currentRef
        end
    end
    return tes3.getPlayerTarget() or tes3.player
end

local function logConsole(str)
    if tes3ui.log then
        tes3ui.log(str)
    elseif tes3ui.logToConsole then
        tes3ui.logToConsole(str, false)
    end
end

local function logBoth(summaryLines, str)
    table.insert(summaryLines, str)
    logConsole(str)
    if config.logToMWSE then
        mwse.log("[mweffectinspector] %s", str)
    end
end

function inspector.closeWindow()
    local menu = tes3ui.findMenu(GUI_ID_WINDOW)
    if menu then
        menu:destroy()
        tes3ui.leaveMenuMode()
    end
end

function inspector.openWindow(targetRef)
    local ref = targetRef or inspector.getTargetRef()
    if not ref then
        tes3.messageBox("mweffectinspector: No target reference found.")
        return
    end

    local existing = tes3ui.findMenu(GUI_ID_WINDOW)
    if existing then
        existing:destroy()
    end

    local menu = tes3ui.createMenu({ id = GUI_ID_WINDOW, fixedFrame = true })
    menu.text = "Magic Effect & VFX Inspector (mweffectinspector)"
    menu.width = 720
    menu.height = 560
    menu.minWidth = 580
    menu.minHeight = 420
    menu.positionX = 0.5
    menu.positionY = 0.5

    local mainBlock = menu:createBlock({})
    mainBlock.widthProportional = 1.0
    mainBlock.heightProportional = 1.0
    mainBlock.flowDirection = "top_to_bottom"

    -- 1. Target Header Card
    local obj = ref.object
    local name = (obj and obj.name) or ref.id
    local refId = ref.id
    local baseId = (obj and obj.id) or "unknown"
    local cellName = ref.cell and (ref.cell.editorName or ref.cell.displayName or ref.cell.id) or "Unknown Cell"
    local mobile = ref.mobile

    local headerBox = mainBlock:createThinBorder({})
    headerBox.widthProportional = 1.0
    headerBox.autoHeight = true
    headerBox.paddingAllSides = 8
    headerBox.borderBottom = 6
    headerBox.flowDirection = "top_to_bottom"

    local titleRow = headerBox:createBlock({})
    titleRow.widthProportional = 1.0
    titleRow.autoHeight = true
    titleRow.flowDirection = "left_to_right"

    local targetTitle = titleRow:createLabel({ text = string.format("Target: %s", name) })
    targetTitle.color = tes3ui.getPalette("header_color")
    targetTitle.widthProportional = 1.0

    local metaText = string.format("Base: %s  |  Ref: %s  |  Cell: %s", baseId, refId, cellName)
    local metaLbl = headerBox:createLabel({ text = metaText })
    metaLbl.color = tes3ui.getPalette("journal_finished_quest_color")

    if mobile then
        local hCur = math.floor(mobile.health and mobile.health.current or 0)
        local hMax = math.floor(mobile.health and mobile.health.base or 0)
        local mCur = math.floor(mobile.magicka and mobile.magicka.current or 0)
        local mMax = math.floor(mobile.magicka and mobile.magicka.base or 0)
        local fCur = math.floor(mobile.fatigue and mobile.fatigue.current or 0)
        local fMax = math.floor(mobile.fatigue and mobile.fatigue.base or 0)
        local statLbl = headerBox:createLabel({
            text = string.format("Health: %d/%d  |  Magicka: %d/%d  |  Fatigue: %d/%d", hCur, hMax, mCur, mMax, fCur, fMax)
        })
        statLbl.color = tes3ui.getPalette("active_color")
    end

    -- 2. Scrollable Body
    local scroll = mainBlock:createVerticalScrollPane({})
    scroll.widthProportional = 1.0
    scroll.heightProportional = 1.0
    scroll.borderBottom = 8

    local content = scroll:getContentElement()
    content.flowDirection = "top_to_bottom"
    content.widthProportional = 1.0

    local function addSectionHeader(titleText)
        local sec = content:createBlock({})
        sec.widthProportional = 1.0
        sec.autoHeight = true
        sec.borderTop = 6
        sec.borderBottom = 4
        local lbl = sec:createLabel({ text = string.format("--- %s ---", titleText) })
        lbl.color = tes3ui.getPalette("header_color")
    end

    -- Active Magic Effects
    addSectionHeader("ACTIVE MAGIC EFFECTS")
    local activeCount = 0
    if mobile and mobile.activeMagicEffectList then
        for _, actEff in ipairs(mobile.activeMagicEffectList) do
            activeCount = activeCount + 1
            local mgef = tes3.getMagicEffect(actEff.effectId)
            local effName = (mgef and mgef.name) or string.format("Effect #%s", tostring(actEff.effectId))
            local src = actEff.instance and actEff.instance.source
            local srcName = (src and src.name) or "Unknown Source"
            local srcId = (src and src.id) or "unknown"
            local caster = actEff.instance and actEff.instance.caster
            local casterName = caster and (caster.object and caster.object.name or caster.id) or "Unknown Caster"
            local mag = actEff.magnitude or 0
            local dur = math.floor(actEff.duration or 0)

            local itemBox = content:createThinBorder({})
            itemBox.widthProportional = 1.0
            itemBox.autoHeight = true
            itemBox.paddingAllSides = 4
            itemBox.borderBottom = 3
            itemBox.flowDirection = "left_to_right"

            local effLabel = itemBox:createLabel({
                text = string.format(" * %s (%d pts, %ds left)", effName, mag, dur)
            })
            effLabel.color = tes3ui.getPalette("active_color")
            effLabel.widthProportional = 1.0

            local srcLabel = itemBox:createLabel({
                text = string.format("Source: %s [%s]  (Caster: %s)", srcName, srcId, casterName)
            })
            srcLabel.color = tes3ui.getPalette("normal_color")
        end
    end
    if activeCount == 0 then
        local none = content:createLabel({ text = "  (No active magic effects)" })
        none.color = tes3ui.getPalette("journal_finished_quest_color")
    end

    -- Spells & Innate Abilities
    if config.showSpells then
        addSectionHeader("SPELLS & INNATE ABILITIES")
        local spellCount = 0
        local spellsList = tes3.getSpells{ target = ref } or (obj and obj.spells)
        if spellsList then
            for _, spell in pairs(spellsList) do
                spellCount = spellCount + 1
                local typeStr = spellTypeNames[spell.castType] or "Spell"
                local effectDescs = {}
                for _, eff in ipairs(spell.effects or {}) do
                    if eff and eff.id and eff.id >= 0 then
                        local mgef = tes3.getMagicEffect(eff.id)
                        local mName = (mgef and mgef.name) or tostring(eff.id)
                        local magStr = tostring(eff.min)
                        if eff.max and eff.max ~= eff.min then
                            magStr = string.format("%d-%d", eff.min, eff.max)
                        end
                        table.insert(effectDescs, string.format("%s %s pts", mName, magStr))
                    end
                end
                local effDescStr = #effectDescs > 0 and table.concat(effectDescs, ", ") or "None"

                local sBox = content:createThinBorder({})
                sBox.widthProportional = 1.0
                sBox.autoHeight = true
                sBox.paddingAllSides = 4
                sBox.borderBottom = 3
                sBox.flowDirection = "left_to_right"

                local sNameLbl = sBox:createLabel({ text = string.format("[%s] %s", typeStr, spell.name or spell.id) })
                sNameLbl.color = tes3ui.getPalette("active_color")
                sNameLbl.widthProportional = 1.0

                local sEffLbl = sBox:createLabel({ text = effDescStr })
                sEffLbl.color = tes3ui.getPalette("normal_color")
            end
        end
        if spellCount == 0 then
            local none = content:createLabel({ text = "  (No spells or innate abilities)" })
            none.color = tes3ui.getPalette("journal_finished_quest_color")
        end
    end

    -- Equipped Items & Enchantments
    if config.showEquipment and obj and obj.equipment then
        addSectionHeader("EQUIPPED ITEMS & ENCHANTMENTS")
        local equipCount = 0
        for _, stack in pairs(obj.equipment) do
            local itemObj = stack.object
            if itemObj and itemObj.enchantment then
                equipCount = equipCount + 1
                local ench = itemObj.enchantment
                local enchDesc = {}
                for _, eff in ipairs(ench.effects or {}) do
                    if eff and eff.id and eff.id >= 0 then
                        local mgef = tes3.getMagicEffect(eff.id)
                        table.insert(enchDesc, string.format("%s %d pts", (mgef and mgef.name) or tostring(eff.id), eff.min or 0))
                    end
                end

                local eBox = content:createThinBorder({})
                eBox.widthProportional = 1.0
                eBox.autoHeight = true
                eBox.paddingAllSides = 4
                eBox.borderBottom = 3
                eBox.flowDirection = "left_to_right"

                local eNameLbl = eBox:createLabel({ text = string.format(" * %s", itemObj.name or itemObj.id) })
                eNameLbl.color = tes3ui.getPalette("active_color")
                eNameLbl.widthProportional = 1.0

                local eDescLbl = eBox:createLabel({ text = table.concat(enchDesc, ", ") })
                eDescLbl.color = tes3ui.getPalette("normal_color")
            end
        end
        if equipCount == 0 then
            local none = content:createLabel({ text = "  (No enchanted equipment)" })
            none.color = tes3ui.getPalette("journal_finished_quest_color")
        end
    end

    -- Attached VFX & Scene Nodes
    if config.showVFXNodes and ref.sceneNode then
        addSectionHeader("ATTACHED SCENE NODES & VFX")
        local vfxCount = 0
        local function checkNode(node)
            if not node then return end
            local nName = node.name or ""
            local low = nName:lower()
            local isParticle = node:isInstanceOfType(tes3.niType.NiParticleSystem) or node:isInstanceOfType(tes3.niType.NiParticles)
            if isParticle or low:find("vfx") or low:find("magic") or low:find("shield") or low:find("spell") or low:find("aura") or low:find("effect") or low:find("light") then
                vfxCount = vfxCount + 1
                local typeName = node:isInstanceOfType(tes3.niType.NiNode) and "NiNode" or (isParticle and "ParticleSystem" or "Geometry")

                local vBox = content:createThinBorder({})
                vBox.widthProportional = 1.0
                vBox.autoHeight = true
                vBox.paddingAllSides = 3
                vBox.borderBottom = 2
                local vLbl = vBox:createLabel({ text = string.format("  [%s] '%s'", typeName, nName) })
                vLbl.color = tes3ui.getPalette("active_color")
            end
            if node.children then
                for _, child in ipairs(node.children) do
                    checkNode(child)
                end
            end
        end
        checkNode(ref.sceneNode)
        if vfxCount == 0 then
            local none = content:createLabel({ text = "  (No lingering VFX nodes detected)" })
            none.color = tes3ui.getPalette("journal_finished_quest_color")
        end
    end

    -- 3. Bottom Button Row
    local btnRow = mainBlock:createBlock({})
    btnRow.widthProportional = 1.0
    btnRow.autoHeight = true
    btnRow.flowDirection = "left_to_right"

    local purgeBtn = btnRow:createButton({ text = "Purge Active Effects" })
    purgeBtn:register("mouseClick", function()
        inspector.clearEffects(ref)
        inspector.openWindow(ref)
    end)

    local refreshBtn = btnRow:createButton({ text = "Refresh" })
    refreshBtn.borderLeft = 8
    refreshBtn:register("mouseClick", function()
        inspector.openWindow(ref)
    end)

    local closeSpacer = btnRow:createBlock({})
    closeSpacer.widthProportional = 1.0
    closeSpacer.autoHeight = true

    local closeBtn = btnRow:createButton({ text = "Close" })
    closeBtn:register("mouseClick", function()
        inspector.closeWindow()
    end)

    menu:updateLayout()
    tes3ui.enterMenuMode(GUI_ID_WINDOW)
end

function inspector.inspectEffects(targetRef)
    local ref = targetRef or inspector.getTargetRef()
    if not ref then
        logConsole("[mweffectinspector] Error: No target reference found.")
        return
    end

    local mobile = ref.mobile
    local obj = ref.object
    local name = (obj and obj.name) or ref.id
    local refId = ref.id
    local baseId = obj and obj.id or "unknown"
    local cellName = ref.cell and (ref.cell.editorName or ref.cell.id) or "Unknown Cell"

    local summaryLines = {}

    logBoth(summaryLines, "========================================")
    logBoth(summaryLines, string.format("INSPECTING: %s (Base: %s | Ref: %s)", name, baseId, refId))
    logBoth(summaryLines, string.format("Location: %s", cellName))
    logBoth(summaryLines, "========================================")

    -- Open the graphical UI window
    inspector.openWindow(ref)
end

function inspector.clearEffects(targetRef)
    local ref = targetRef or inspector.getTargetRef()
    if not ref then
        logConsole("[mweffectinspector] Error: No target reference found.")
        return
    end

    local name = (ref.object and ref.object.name) or ref.id
    local mobile = ref.mobile
    local count = 0
    if mobile and mobile.activeMagicEffectList then
        for _, actEff in ipairs(mobile.activeMagicEffectList) do
            count = count + 1
            if actEff.instance then
                pcall(function() actEff.instance:cancel() end)
            end
        end
    end

    tes3.removeEffects{ reference = ref }

    local msg = string.format("[mweffectinspector] Purged %d active magic effect(s) from %s (%s).", count, name, ref.id)
    logConsole(msg)
    if config.logToMWSE then
        mwse.log(msg)
    end
    tes3.messageBox(string.format("Purged %d active magic effect(s) from %s.", count, name))
end

return inspector
