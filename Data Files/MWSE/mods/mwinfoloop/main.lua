--[[
  mwinfoloop 2.0 - finds dialogue response lists that go round in a circle, and keeps them from freezing the game.

  1. Startup check (once per install state). When the main menu first opens, every topic's response list, as the
     game holds it after all plugins are merged, is walked once. The walk is capped at the list's own node count
     (+1), so a circular list is proven circular without ever spinning. Results go to
     Data Files\MWSE\config\mwinfoloop_cache.json, keyed by the load order (file names, sizes, dates), the MWSE
     build and this mod's version. On a match the check is skipped and no pop-up is shown.
     While the check runs, a small pop-up replaces the main menu; the check is spread over frames so the pop-up
     actually draws. Clicking the pop-up skips the check; a watchdog ends it after 60 s; any error ends it. The
     main menu always comes back.
  2. Live guard. Only infoFilter (one call per candidate line, as the game tries them) and dialogueFiltered.
     No per-frame work. Per call: a few comparisons and one counter, no tables, no disk access.
     A walk that tries more lines than the topic has nodes is going round in a circle: one line is let through,
     which is the only way an infoFilter handler can end the walk (blocking a line only moves the walk on).
     Topics the check found circular get an exact revisit test instead of the counter.
  3. Optional: a response picked again and again through Choice answers (a conversation that loops) is logged;
     with breakChoiceLoops on, it is skipped for the rest of that conversation.

  The INFO ids (INAM) are not kept in memory by the game; asking for info.id reads the plugin from disk. So ids
  are only looked up for lines that get reported, never per evaluated line.

  Log: Data Files\MWSE\logs\mwinfoloop.log (new each session, capped at 5 MB).
]]

local VERSION = "2.0.0"
local CACHE_VERSION = 2
local CACHE_NAME = "mwinfoloop_cache" -- Data Files\MWSE\config\mwinfoloop_cache.json
local LOG_DIR = "Data Files\\MWSE\\logs"
local LOG_PATH = LOG_DIR .. "\\mwinfoloop.log"
local LOG_CAP = 5 * 1024 * 1024
local MAX_IDS = 40 -- per reported topic, ids listed in the log/cache

local lfs = lfs or require("lfs")

local M = {} -- returned for the test harness; MWSE ignores a main.lua return value

local config = mwse.loadConfig("mwinfoloop", {
    enabled = true,
    startupCheck = true,
    liveGuard = true,
    breakWithLine = true,    -- let one line through when a walk goes round in a circle
    liveTrace = false,       -- log every picked response (id lookups hit the disk; human speed only)
    breakChoiceLoops = false, -- skip a response picked choiceLoopLimit times in a row via Choice answers
    choiceLoopLimit = 8,
    scanBudgetMs = 20,       -- time spent checking per frame while the pop-up is up
})
M.config = config

---------------------------------------------------------------------------------------------------------------
-- log
---------------------------------------------------------------------------------------------------------------
local logFile, logBytes, logDisabled = nil, 0, false

local function openLog()
    if logFile or logDisabled then return logFile end
    pcall(lfs.mkdir, LOG_DIR)
    local ok, fh = pcall(io.open, LOG_PATH, "w")
    if ok and fh then
        logFile = fh
    else
        logDisabled = true
    end
    return logFile
end

local function log(fmt, ...)
    local fh = openLog()
    if not fh or logBytes > LOG_CAP then return end
    local ok, msg = pcall(string.format, fmt, ...)
    if not ok then msg = tostring(fmt) end
    local line = os.date("%H:%M:%S ") .. msg .. "\n"
    logBytes = logBytes + #line
    pcall(fh.write, fh, line)
    if logBytes > LOG_CAP then
        pcall(fh.write, fh, "log size cap reached, no more lines this session\n")
    end
end

local function flushLog()
    if logFile then pcall(logFile.flush, logFile) end
end

-- id of an info: reads the plugin from disk (see header) - only for reported lines
local function infoId(info)
    local ok, id = pcall(function() return info.id end)
    return ok and id and tostring(id) or "?"
end

local function infoSource(info)
    local ok, m = pcall(function() return info.sourceMod end)
    return ok and m or "?"
end

local function dialId(dial)
    local ok, id = pcall(function() return dial.id end)
    return ok and id and tostring(id) or "?"
end

---------------------------------------------------------------------------------------------------------------
-- load-order fingerprint
---------------------------------------------------------------------------------------------------------------
local loadIndex = {} -- lower-case plugin name -> position in the load order

local function fingerprint()
    local dh = tes3.dataHandler
    local nd = dh and dh.nonDynamicData
    local mods = nd and nd.activeMods
    if not mods then return nil end
    local parts = { "v=" .. VERSION, "c=" .. CACHE_VERSION, "mwse=" .. tostring(mwse.buildNumber or "?") }
    local attr = {}
    for i = 1, #mods do
        local gf = mods[i]
        local name = gf and gf.filename or "?"
        loadIndex[name:lower()] = i
        -- the engine's own directory scan (no disk access); lfs as the second opinion. Hard links share both.
        local size, mtime = 0, 0
        pcall(function() size, mtime = gf.fileSize or 0, gf.modifiedTime or 0 end)
        local a = lfs.attributes("Data Files\\" .. name, attr)
        local lsize = a and a.size or 0
        local lmod = a and a.modification or 0
        parts[#parts + 1] = string.format("%s:%.0f:%.0f:%.0f:%.0f", name:lower(), size, mtime, lsize, lmod)
    end
    return table.concat(parts, "|")
end
M.fingerprint = fingerprint

---------------------------------------------------------------------------------------------------------------
-- cache
---------------------------------------------------------------------------------------------------------------
local function loadCache()
    local ok, data = pcall(json.loadfile, "config\\" .. CACHE_NAME)
    if ok and type(data) == "table" and data.version == CACHE_VERSION and type(data.fingerprint) == "string" then
        return data
    end
    return nil
end

local function saveCache(data)
    local ok, err = pcall(mwse.saveConfig, CACHE_NAME, data)
    if not ok then log("could not save the cache: %s", tostring(err)) end
    return ok
end

---------------------------------------------------------------------------------------------------------------
-- what is known about each topic this session
---------------------------------------------------------------------------------------------------------------
-- status by topic id: "clean" (ends within its node count), "cyclic", or nil (unknown: no check this session)
local status = {}
local statusKnown = false -- true once a check ran or a cache matched: topics not listed are clean
-- per-dialogue runtime data, built on first use: { count, tail, cyclic, cap }
local meta = setmetatable({}, { __mode = "k" })

local function applyResults(anomalies)
    status = {}
    for id, a in pairs(anomalies or {}) do
        status[id] = (a.kind == "cycle") and "cyclic" or "clean"
    end
    statusKnown = true
    meta = setmetatable({}, { __mode = "k" })
end

local function getMeta(dial)
    local m = meta[dial]
    if m then return m end
    m = { count = 0, cyclic = false, tail = nil, cap = 64 }
    local ok, n = pcall(function() return #dial.info end)
    m.count = ok and n or 0
    local st = status[dialId(dial)]
    if st == "cyclic" then
        m.cyclic = true
    elseif statusKnown and m.count > 0 then
        -- known to end: the last node is the tail; reaching it means the walk is over
        local okT, t = pcall(function() return dial.info[m.count] end)
        if okT then m.tail = t end
    end
    -- known clean: more than count+1 tries in one walk is impossible. Unknown: allow several back-to-back
    -- walks of the same topic (all failing) before calling it a circle.
    m.cap = m.tail and (m.count + 1) or (m.count * 8 + 64)
    meta[dial] = m
    return m
end

---------------------------------------------------------------------------------------------------------------
-- startup check
---------------------------------------------------------------------------------------------------------------
-- Walks one topic. seen/pos are shared tables keyed by the info userdata (MWSE keeps one userdata per object,
-- so identity works); stamp = topic number, so nothing has to be cleared between topics.
local order = {}
local function walkTopic(dial, stamp, seen, pos)
    local okC, count = pcall(function() return #dial.info end)
    if not okC or type(count) ~= "number" then return { kind = "error", error = "no info list" }, 0 end
    local n, dupes, firstRepeatAt = 0, 0, nil
    for _, info in pairs(dial.info) do
        n = n + 1
        order[n] = info
        if seen[info] == stamp then
            dupes = dupes + 1
            firstRepeatAt = firstRepeatAt or n
        else
            seen[info] = stamp
            pos[info] = n
        end
        if n > count then break end -- more steps than nodes: proven circular, stop
    end
    if n <= count then
        if n < count then
            return { kind = "short", count = count, walked = n }, n -- list ends before its node count
        end
        if dupes > 0 then
            return { kind = "duplicate", count = count, walked = n, repeats = dupes, at = firstRepeatAt }, n
        end
        return nil, n -- clean
    end
    -- The first line seen twice is where the circle is re-entered; the line before it holds the closing link.
    local r = firstRepeatAt or n
    local entry = order[r]
    local j = pos[entry] or 1
    local members = {}
    for k = j, math.min(r - 1, j + MAX_IDS - 1) do members[#members + 1] = order[k] end
    return { kind = "cycle", count = count, walked = n, prefix = j - 1, length = r - j,
        entry = entry, closer = order[r - 1] or entry, members = members }, n
end
M.walkTopic = walkTopic

-- turns a walkTopic result into what is logged and cached (ids looked up here, only for problem topics)
local function describe(id, r)
    local out = { kind = r.kind, count = r.count, walked = r.walked }
    if r.kind == "cycle" then
        out.prefix, out.length = r.prefix, r.length
        out.members = {}
        for i, info in ipairs(r.members) do
            out.members[i] = { id = infoId(info), plugin = infoSource(info) }
        end
        -- break point: the link that closes the circle, from `closer` back to `entry`. Blame the later plugin.
        local fromP, toP = infoSource(r.closer), infoSource(r.entry)
        local fi = loadIndex[tostring(fromP):lower()] or 0
        local ti = loadIndex[tostring(toP):lower()] or 0
        out.breakAt = { from = infoId(r.closer), to = infoId(r.entry), plugin = (fi >= ti) and fromP or toP }
        log("CIRCLE in topic '%s': %d nodes, after %d line(s) the list goes round %d line(s) for ever",
            id, r.count, r.prefix, r.length)
        for _, m in ipairs(out.members) do log("    %s  (%s)", m.id, m.plugin) end
        log("    closing link: %s -> %s; likely introduced by %s (run the Python tool's PNAM fix on it)",
            out.breakAt.from, out.breakAt.to, out.breakAt.plugin)
    elseif r.kind == "duplicate" then
        out.repeats = r.repeats
        log("topic '%s': the same response is listed %d extra time(s) (first at line %d); harmless, ends normally",
            id, r.repeats, r.at or 0)
    elseif r.kind == "short" then
        log("topic '%s': list ends after %d of %d nodes (a broken link)", id, r.walked, r.count)
    else
        log("topic '%s': could not be read (%s)", id, tostring(r.error))
    end
    return out
end

local scan = nil -- running check state
M.state = function() return { scan = scan, status = status, statusKnown = statusKnown } end

local POPUP_ID = "mwinfoloop:Checking"
local function popupId() return tes3ui.registerID(POPUP_ID) end

local function destroyPopup()
    pcall(function()
        local m = tes3ui.findMenu(popupId())
        if m then m:destroy() end
    end)
end

local function showMainMenu(menu)
    pcall(function()
        local mo = menu or tes3ui.findMenu("MenuOptions")
        if mo then
            mo.visible = true
            mo:updateLayout()
        end
    end)
end

local finishScan -- forward

local function createPopup()
    local ok, err = pcall(function()
        local menu = tes3ui.createMenu({ id = popupId(), fixedFrame = true, modal = true })
        local block = menu:createBlock()
        block.flowDirection = "top_to_bottom"
        block.autoWidth = true
        block.autoHeight = true
        block.childAlignX = 0.5
        block.paddingAllSides = 10
        block:createLabel({ text = "mwinfoloop: checking dialogue for loops..." })
        local progress = block:createLabel({ id = tes3ui.registerID("mwinfoloop:Progress"), text = "" })
        progress.borderTop = 4
        local hint = block:createLabel({ text = "(click to skip)" })
        hint.borderTop = 4
        pcall(function() hint.color = tes3ui.getPalette("disabled_color") end)
        menu:register("mouseClick", function() finishScan("skipped") end)
        menu:updateLayout()
        scan.progress = progress
        scan.popup = menu
    end)
    if not ok then log("pop-up failed (%s); checking without it", tostring(err)) end
end

local function scanChunk()
    local s = scan
    local budget = (tonumber(config.scanBudgetMs) or 20) / 1000
    local t0 = os.clock()
    while s.index < #s.dials do
        s.index = s.index + 1
        local dial = s.dials[s.index]
        local okW, r, walked = pcall(walkTopic, dial, s.index, s.seen, s.pos)
        if not okW then r, walked = { kind = "error", error = r }, 0 end
        s.infos = s.infos + (walked or 0)
        if r then
            local id = dialId(dial)
            s.anomalies[id] = describe(id, r)
            s.problems = s.problems + 1
        end
        if os.clock() - t0 >= budget then break end
    end
    if s.progress then
        pcall(function()
            s.progress.text = string.format("%d / %d topics", s.index, #s.dials)
            s.popup:updateLayout()
        end)
    end
    return s.index >= #s.dials
end

local scheduleStep -- forward
local function step()
    if not scan or scan.finished then return end
    local ok, done = pcall(scanChunk)
    if not ok then
        log("check failed: %s", tostring(done))
        finishScan("error")
    elseif done then
        finishScan("done")
    else
        scheduleStep()
    end
end

scheduleStep = function()
    local ok, t = pcall(timer.frame.delayOneFrame, step)
    if not ok or not t then
        -- no frame timer: finish in one go rather than leave the main menu hidden
        log("frame timer unavailable (%s); finishing the check in one go", tostring(t))
        while scan and not scan.finished do
            local okC, done = pcall(scanChunk)
            if not okC then finishScan("error") break end
            if done then finishScan("done") break end
        end
    end
end

finishScan = function(reason)
    local s = scan
    if not s or s.finished then return end
    s.finished = true
    destroyPopup()
    showMainMenu(s.mainMenu)
    if s.watchdog then pcall(function() s.watchdog:cancel() end) end
    local secs = os.clock() - s.started
    if reason == "done" then
        local cyc = 0
        for _, a in pairs(s.anomalies) do if a.kind == "cycle" then cyc = cyc + 1 end end
        applyResults(s.anomalies)
        saveCache({ version = CACHE_VERSION, modVersion = VERSION, fingerprint = s.fingerprint,
            checked = os.date("%Y-%m-%d %H:%M:%S"), topics = #s.dials, infos = s.infos,
            circular = cyc, problems = s.problems, anomalies = s.anomalies })
        log("checked %d topics (%d responses) in %.2f s: %d circular, %d other problem(s)",
            #s.dials, s.infos, secs, cyc, s.problems - cyc)
        pcall(mwse.log, "[mwinfoloop] checked %d topics in %.2f s: %d circular list(s)%s", #s.dials, secs, cyc,
            s.problems > 0 and " (see MWSE\\logs\\mwinfoloop.log)" or "")
        if cyc > 0 then
            pcall(tes3ui.showNotifyMenu, "mwinfoloop: %d dialogue topic(s) loop; they are guarded. See MWSE\\logs\\mwinfoloop.log", cyc)
        end
    else
        -- partial results still guard this session; nothing is cached, so the next launch checks again
        local partial = {}
        for id, a in pairs(s.anomalies) do partial[id] = a end
        status = {}
        for id, a in pairs(partial) do status[id] = (a.kind == "cycle") and "cyclic" or "clean" end
        statusKnown = false
        log("check ended early (%s) after %d of %d topics, %.2f s; it runs again next launch",
            reason, s.index, #s.dials, secs)
        pcall(mwse.log, "[mwinfoloop] dialogue check ended early (%s); it runs again next launch", reason)
    end
    s.seen, s.pos, s.dials = nil, nil, {}
    for k in pairs(order) do order[k] = nil end
    flushLog()
end

local function startScan(mainMenu, fp)
    scan = { dials = {}, index = 0, seen = {}, pos = {}, anomalies = {}, problems = 0, infos = 0,
        started = os.clock(), fingerprint = fp, mainMenu = mainMenu, finished = false }
    local ok, err = pcall(function()
        for _, dial in pairs(tes3.dataHandler.nonDynamicData.dialogues) do
            scan.dials[#scan.dials + 1] = dial
        end
    end)
    if not ok then
        log("could not list the topics: %s", tostring(err))
        scan.finished = true
        return
    end
    log("checking %d topics (load order changed or no cache)", #scan.dials)
    if mainMenu then pcall(function() mainMenu.visible = false end) end
    createPopup()
    pcall(function()
        scan.watchdog = timer.start({ type = timer.real, duration = 60, callback = function() finishScan("timeout") end })
    end)
    scheduleStep()
end
M.startScan = startScan

local pendingFingerprint = nil
local checkedThisSession = false

event.register(tes3.event.initialized, function()
    if not config.enabled then return end
    local okF, fp = pcall(fingerprint)
    if not okF then log("fingerprint failed: %s", tostring(fp)) fp = nil end
    local cache = loadCache()
    if fp and cache and cache.fingerprint == fp then
        applyResults(cache.anomalies)
        checkedThisSession = true
        log("load order unchanged since %s: %d topics, %d circular (cached, no check needed)",
            tostring(cache.checked), cache.topics or 0, cache.circular or 0)
        if (cache.circular or 0) > 0 then
            pcall(mwse.log, "[mwinfoloop] %d circular topic(s) from the cache are guarded", cache.circular)
        end
    else
        pendingFingerprint = fp or ""
    end
    flushLog()
end)

event.register(tes3.event.uiActivated, function(e)
    if checkedThisSession or tes3.player or not config.enabled then return end
    checkedThisSession = true
    if not config.startupCheck or not pendingFingerprint then return end
    startScan(e.element, pendingFingerprint)
end, { filter = "MenuOptions" })

-- a save loaded before the check finished (quick-load mods): stop it and restore everything
event.register(tes3.event.load, function()
    if scan and not scan.finished then finishScan("game loaded") end
end)

---------------------------------------------------------------------------------------------------------------
-- live guard
---------------------------------------------------------------------------------------------------------------
local cur = { dial = nil, ref = nil, steps = 0, m = nil, ended = true, lastInfo = nil, lastPassed = false,
    lastTime = 0, pass = 0 }
local visited = {}       -- info -> pass number; used only for topics known to be circular
local reported = {}      -- dialogue -> true, one log entry per topic per session
local guardErrors = 0
local CLICK_ANSWER = (tes3.dialogueFilterContext and tes3.dialogueFilterContext.clickAnswer) or 1
local answer = { info = nil, repeats = 0 }
local blocked = nil      -- info -> true, only with breakChoiceLoops

local function resetConversation()
    cur.dial, cur.ref, cur.ended, cur.lastInfo = nil, nil, true, nil
    answer.info, answer.repeats = nil, 0
    blocked = nil
end
M.resetConversation = resetConversation

local function breakWalk(e, dial, info, why)
    if not reported[dial] then
        reported[dial] = true
        log("!LOOP! topic '%s': %s at %s (%s) after %d tries%s", dialId(dial), why, infoId(info), infoSource(info),
            cur.steps, config.breakWithLine and "; let this line through to end it" or "")
        flushLog()
    end
    if config.breakWithLine then
        e.passes = true
        cur.ended = true
    end
end

local function onInfoFilter(e)
    local dial, info = e.dialogue, e.info
    if not dial or not info then return end
    if blocked and blocked[info] then e.passes = false end

    local now = os.clock()
    local ref = e.reference
    if cur.ended or cur.lastPassed or dial ~= cur.dial or ref ~= cur.ref or now - cur.lastTime > 0.05
        or (cur.m and cur.lastInfo == cur.m.tail and cur.m.tail ~= nil) then
        -- a new walk
        cur.dial, cur.ref, cur.steps, cur.ended = dial, ref, 0, false
        cur.m = getMeta(dial)
        cur.pass = cur.pass + 1
    end
    cur.lastTime = now
    cur.steps = cur.steps + 1
    local m = cur.m
    if m.cyclic then
        if visited[info] == cur.pass then
            breakWalk(e, dial, info, "a known circular list came round again")
        else
            visited[info] = cur.pass
        end
    elseif cur.steps > m.cap then
        breakWalk(e, dial, info, string.format("more tries than the list has lines (%d)", m.count))
    end
    cur.lastInfo = info
    cur.lastPassed = e.passes == true
end

event.register(tes3.event.infoFilter, function(e)
    if not (config.enabled and config.liveGuard) or guardErrors > 20 then return end
    local ok, err = pcall(onInfoFilter, e)
    if not ok then
        guardErrors = guardErrors + 1
        log("live guard error %d: %s", guardErrors, tostring(err))
        if guardErrors > 20 then log("live guard switched off for this session after 20 errors") end
    end
end, { priority = -10 }) -- after other mods, so it sees (and has) the final word on `passes`

event.register(tes3.event.dialogueFiltered, function(e)
    cur.ended = true
    if not config.enabled then return end
    local ok, err = pcall(function()
        if e.context ~= CLICK_ANSWER then return end
        if e.info == answer.info then
            answer.repeats = answer.repeats + 1
        else
            answer.info, answer.repeats = e.info, 1
        end
        local limit = tonumber(config.choiceLoopLimit) or 8
        if answer.repeats == limit then
            log("conversation loop? topic '%s': response %s (%s) picked %d times in a row via Choice answers%s",
                dialId(e.dialogue), infoId(e.info), infoSource(e.info), limit,
                config.breakChoiceLoops and "; skipping it for the rest of this conversation" or "")
            flushLog()
            if config.breakChoiceLoops then
                blocked = blocked or {}
                blocked[e.info] = true
            end
        end
    end)
    if not ok then log("dialogueFiltered handler error: %s", tostring(err)) end
end)

event.register(tes3.event.uiActivated, function() resetConversation() end, { filter = "MenuDialog" })
event.register(tes3.event.menuExit, function() resetConversation() flushLog() end)

event.register(tes3.event.infoResponse, function(e)
    if not (config.enabled and config.liveTrace) then return end
    pcall(function()
        local cmd = (e.command or ""):gsub("[\r\n]+", " | "):sub(1, 200)
        log("  picked %s (%s) script: %s", infoId(e.info), infoSource(e.info), cmd)
    end)
end)

M.onInfoFilter = onInfoFilter
M.applyResults = applyResults
M.finishScan = function(r) finishScan(r) end

---------------------------------------------------------------------------------------------------------------
-- settings
---------------------------------------------------------------------------------------------------------------
event.register(tes3.event.modConfigReady, function()
    local template = mwse.mcm.createTemplate({ name = "mwinfoloop", config = config })
    template:saveOnClose("mwinfoloop", config)
    local page = template:createSideBarPage({
        label = "Settings",
        description = "Finds dialogue response lists that go round in a circle and keeps them from freezing the "
            .. "game. Log: Data Files\\MWSE\\logs\\mwinfoloop.log. Version " .. VERSION .. ".",
    })
    page:createOnOffButton({ label = "Enabled", configKey = "enabled",
        description = "Master switch." })
    page:createOnOffButton({ label = "Check all topics when the load order changes", configKey = "startupCheck",
        description = "Checks every topic once at the main menu, with a small pop-up. Skipped while the load order, "
            .. "file sizes and dates are unchanged." })
    page:createOnOffButton({ label = "Guard conversations", configKey = "liveGuard",
        description = "Watches the lines the game tries while you talk and ends a walk that goes round in a circle." })
    page:createOnOffButton({ label = "Let a line through to end a circle", configKey = "breakWithLine",
        description = "The only way to end a circular walk from Lua. Off = only log it (the game will freeze)." })
    page:createOnOffButton({ label = "Skip responses repeated through Choice answers", configKey = "breakChoiceLoops",
        description = "When the same response is picked many times in a row via Choice answers, skip it for the "
            .. "rest of the conversation. Off = only log it." })
    page:createOnOffButton({ label = "Log every picked response", configKey = "liveTrace",
        description = "For debugging. Each picked line costs one small disk read for its id." })
    page:createButton({
        label = "Check again at next launch",
        buttonText = "Clear cache",
        description = "Forgets the cached result so the next launch checks every topic again.",
        callback = function()
            pcall(mwse.saveConfig, CACHE_NAME, { version = 0 })
            tes3.messageBox("mwinfoloop: the next launch checks every topic again.")
        end,
    })
    template:register()
end)

return M
