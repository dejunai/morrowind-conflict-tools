--[[
    mwperformers - one performer per inn

    When you enter an interior, it looks at the performers there: NPCs with a bard, lute or drummer
    animation, or a script named for it (Animated Morrowind, Bards of Bardenfell and the like), whichever mod
    added them or made them perform - an inn's own NPC turned into a bard counts the same as a new one.
    Where two or more perform in the same place, one is picked at random to keep performing; the pick is
    remembered for that place on the player (so it is the same on every visit in that game). The others stop
    performing: their song script is held (MWSE's scriptExecute event), their song is stopped, and one with a
    performing animation stands with the normal one. Nobody is removed, hidden or disabled, and they can
    still be talked to.

    It works only in the interiors MWSE\config\mwperformers_data.json lists (written by mwdialog_check --fix and
    --cell-conflicts: each interior with performers placed in it, and who); anywhere else it does nothing. A listed
    performer not found in the place is logged once a session. Without the list it handles no one, and one line in
    MWSE.log says so. The Mod Config menu can pick again for the place you're in. Off: everyone performs again.
    Performers that an older version hid (disabled) are shown again when their place is next visited.
    Decisions are written to Data Files\MWSE\logs\mwperformers.log.

    While it is on, a bard also stops singing while you talk to them, and holds their lute (Weapon
    Sheathing showed it on the back, as it is a shield). The performing animation (the lute) stops at the same
    moment, for any performer, and comes back when the dialogue ends; Animated Dialogue is not patched, it
    just finds the plain animation where it would have found the lute. After the dialogue he stands plainly for
    a pause (3 s of game time by default, Mod Config slider) before the animation restarts.
    MWSE throws "Animation file failed to load" for a plain animation (it has no override layer) AFTER it has
    swapped the model, so that throw counts as loaded and the restore (tes3.loadAnimation{reference}) always
    runs; menuExit / cellChanged are a backstop for any performer left plain.
]]

local CONFIG_NAME = "mwperformers"
local config = mwse.loadConfig(CONFIG_NAME, { enabled = false, log = true, dialogueAnimation = true, restoreDelay = 3 })

-- MWSE\config\mwperformers_data.json (mwdialog_check): interior id -> the performers placed there
local known
do
    local data = mwse.loadConfig("mwperformers_data")
    if data and type(data.cells) == "table" then
        known = {}
        for cellId, list in pairs(data.cells) do
            if type(cellId) == "string" and type(list) == "table" then known[cellId:lower()] = list end
        end
    else
        mwse.log("[mwperformers] MWSE\\config\\mwperformers_data.json is missing: no performers are handled "
            .. "(mwdialog_check --fix, or --cell-conflicts, writes it)")
    end
end
local function isKnown(cell)
    return known ~= nil and cell ~= nil and cell.isInterior == true and known[cell.id:lower()] ~= nil
end

local ANIM_PATTERNS = { "bard", "lute", "drum", "perform", "musician" }
local SCRIPT_PATTERNS = { "bard", "lute", "drum", "perform", "musician", "minstrel" }

-- log ---------------------------------------------------------------------------------------------
local LOG_DIR = "Data Files\\MWSE\\logs"
local logFile
local function log(fmt, ...)
    if not config.log then return end
    if not logFile then
        pcall(function() lfs.mkdir(LOG_DIR) end)
        logFile = io.open(LOG_DIR .. "\\mwperformers.log", "w")
        if not logFile then return end
        logFile:write(os.date("mwperformers log, started %Y-%m-%d %H:%M:%S"), "\n")
    end
    local ok, line = pcall(string.format, fmt, ...)
    logFile:write(os.date("[%H:%M:%S] "), ok and line or tostring(fmt), "\n")
    logFile:flush()
end

-- who performs ------------------------------------------------------------------------------------
local function matches(text, patterns)
    if not text or text == "" then return false end
    text = text:lower()
    for _, p in ipairs(patterns) do
        if text:find(p, 1, true) then return true end
    end
    return false
end

local function baseOf(ref)
    local obj = ref and ref.object
    if not obj then return nil end
    return obj.baseObject or obj
end

local function hasPerformingAnim(base) return matches(base.mesh, ANIM_PATTERNS) end
local function performingScript(base)
    local script = base.script
    if script and matches(script.id, SCRIPT_PATTERNS) then return script end
    return nil
end

-- a performer, whoever added it or made it perform
local function isPerformer(ref)
    local base = baseOf(ref)
    if not base or base.objectType ~= tes3.objectType.npc then return false end
    return hasPerformingAnim(base) or performingScript(base) ~= nil
end

local function describe(ref)
    local name = ref.object.name
    return (name and name ~= "") and string.format("%s (%s)", name, ref.object.id) or ref.object.id
end

-- remembered on the player, not on each NPC: ref.data would write a lua table into the save for every
-- performer visited
local function cellTag(ref)
    local cell = ref.cell
    if not cell then return "?" end
    return cell.isInterior and cell.id:lower() or string.format("#%d,%d", cell.gridX, cell.gridY)
end

-- the key an older version saved: startingPosition is not valid for NPCs (MWSE docs), so it can't be relied on
local function oldKey(ref)
    local p = ref.startingPosition or ref.position
    return string.format("%s|%s|%d|%d|%d", cellTag(ref), ref.object.id:lower(),
        math.floor(p.x + 0.5), math.floor(p.y + 0.5), math.floor(p.z + 0.5))
end

-- the plugin that placed it and its reference number there: stable across moves and load-order changes
local function refKey(ref)
    local form = ref.sourceFormId
    if not form or form == 0 then return oldKey(ref) end
    return string.format("%s|%s|%s|%d", cellTag(ref), ref.object.id:lower(), tostring(ref.sourceMod or ""):lower(), form)
end

local function playerData(name, create)
    if not tes3.player then return nil end
    local data = tes3.player.data
    local t = data[name]
    if not t and create then
        t = {}
        data[name] = t
    end
    return t
end

-- older versions hid the doubles (disabled them) and kept their keys in player.data.mwperformers: each is
-- shown again when its place is visited, and the old table goes once it is empty
local function migrateHidden(ref)
    local old = playerData("mwperformers", false)
    if not old then return false end
    local k = refKey(ref)
    if not old[k] then
        k = oldKey(ref)
        if not old[k] then return false end
    end
    old[k] = nil
    if ref.disabled then ref:enable() end
    log("%s: %s shown again (an older version had hidden it)", ref.cell and ref.cell.editorName or "?", describe(ref))
    if next(old) == nil then tes3.player.data.mwperformers = nil end
    return true
end

-- the stopped performers ---------------------------------------------------------------------------
-- held: reference -> true. Their song scripts are skipped through scriptExecute, registered with each
-- script as its filter, so no other script in the game reaches this mod. Each pass over the cells in view
-- builds these afresh; what the last pass held and this one doesn't is let go at the end of it.
local function weak() return setmetatable({}, { __mode = "k" }) end
local held, animStopped = weak(), weak()  -- animStopped: reference -> the scene node its animation was changed on
local touched = weak()                    -- reference -> its safe handle: a performer whose animation a dialogue swapped, until it is given back
local heldScripts = {}                    -- script -> true, while a scriptExecute filter is registered
local prevAnim, prevScripts = weak(), {}  -- the last pass's, while a pass runs

local function onScriptExecute(e)
    local ref = e.reference
    if ref and held[ref] then
        e.block = true
        return false
    end
end

local function holdScript(script)
    if heldScripts[script] or not tes3.event.scriptExecute then return end
    heldScripts[script] = true
    if prevScripts[script] then
        prevScripts[script] = nil         -- registered already
    else
        event.register(tes3.event.scriptExecute, onScriptExecute, { filter = script })
    end
end

-- MWSE logs "An unhandled exception occurred: Animation file failed to load." from its C++ side for every plain-animation
-- swap, even inside pcall (the plain animation has no custom animation layer, which MWSE checks for after it has
-- already swapped the model). The swap works; the entry is harmless. So the entry is never a mystery in MWSE.log,
-- a notice naming the NPC and the file is written just before it, always (not only when the mod's own log is on).
local function noticeExpectedThrow(ref, file)
    local ok, who = pcall(describe, ref)
    local text = string.format(
        "[mwperformers] NOTICE: stopping the performance of %s by loading the plain animation '%s'. This animation "
        .. "has no custom (override) animation file, so MWSE will log 'An unhandled exception occurred: Animation "
        .. "file failed to load.' immediately after this line. That entry is expected and harmless: the plain "
        .. "animation is applied, and playback and the restore of the performer's own animation are unaffected. "
        .. "No action is needed.",
        ok and who or "an NPC", tostring(file))
    pcall(mwse.log, "%s", text)
    log("%s", text)
end

local function plainAnim(base)
    local race = base.race
    if race and race.isBeast then return "base_animkna.nif" end
    return base.female and "base_anim_female.nif" or "base_anim.nif"
end

local function stopPerforming(ref)
    local base = baseOf(ref)
    held[ref] = true
    local script = performingScript(base)
    if script then holdScript(script) end
    if hasPerformingAnim(base) then
        local node = ref.sceneNode
        if node and prevAnim[ref] == node then
            animStopped[ref] = node           -- still standing plainly from the last pass
        elseif node then
            -- MWSE swaps the model first and only then looks for an override layer; a plain animation has none, so it
            -- throws "Animation file failed to load" with the plain animation loaded all the same. Count it as loaded.
            local file = plainAnim(base)
            noticeExpectedThrow(ref, file)
            pcall(tes3.loadAnimation, { reference = ref, file = file })
            animStopped[ref] = ref.sceneNode
        end
    end
    pcall(tes3.removeSound, { reference = ref })     -- a song it had started
end

local function letGo(ref)
    if ref.isValid and not ref:isValid() then return end
    if ref.sceneNode and prevAnim[ref] == ref.sceneNode then
        pcall(tes3.loadAnimation, { reference = ref })   -- back to its own, performing, animation
    end
end

local function beginPass()
    prevAnim, prevScripts = animStopped, heldScripts
    held, animStopped, heldScripts = weak(), weak(), {}
end

local function endPass()
    for ref in pairs(prevAnim) do
        if not animStopped[ref] then letGo(ref) end
    end
    for script in pairs(prevScripts) do
        event.unregister(tes3.event.scriptExecute, onScriptExecute, { filter = script })
    end
    prevAnim, prevScripts = weak(), {}
end

-- the decision for one cell -----------------------------------------------------------------------
local sessionLogged = {}
local missingLogged = {}                  -- interior id -> true: its missing performers were logged this session

-- the performers the list names for this place that aren't in it (a script or an unlisted mod took them away)
local function logMissing(cell)
    local cellId = cell.id:lower()
    if missingLogged[cellId] then return end
    missingLogged[cellId] = true
    local here = {}
    for ref in cell:iterateReferences(tes3.objectType.npc) do
        local base = baseOf(ref)
        if base and not ref.deleted then here[base.id:lower()] = (here[base.id:lower()] or 0) + 1 end
    end
    for _, e in ipairs(known[cellId]) do
        local id = type(e.id) == "string" and e.id:lower()
        if id then
            if (here[id] or 0) > 0 then
                here[id] = here[id] - 1
            else
                log("%s: %s is listed (placed by %s) but isn't here", cell.editorName, id, tostring(e.from or "?"))
            end
        end
    end
end

local function performersIn(cell)
    local list = {}
    for ref in cell:iterateReferences(tes3.objectType.npc) do
        if not ref.deleted and isPerformer(ref) then
            migrateHidden(ref)
            if not ref.disabled and ref.isDead ~= true then list[#list + 1] = ref end
        end
    end
    return list
end

local function settleCell(cell, again)
    if not isKnown(cell) then return end
    logMissing(cell)
    local list = performersIn(cell)
    if not config.enabled or #list < 2 then return end
    local cellId = cell.id:lower()
    local picks = playerData("mwperformers_pick", true)
    local chosen
    if not again then
        for _, ref in ipairs(list) do
            if refKey(ref) == picks[cellId] then chosen = ref break end
        end
    end
    if not chosen then
        chosen = list[math.random(#list)]
        picks[cellId] = refKey(chosen)
        log("%s: %s picked to perform, of %d performers", cell.editorName, describe(chosen), #list)
    end
    for _, ref in ipairs(list) do
        if ref ~= chosen then
            stopPerforming(ref)
            if not sessionLogged[ref] then
                sessionLogged[ref] = true
                log("%s: %s stops performing (%s performs here)", cell.editorName, describe(ref), describe(chosen))
            end
        end
    end
end

-- again: pick anew in the cells in view (the Mod Config menu's button)
local function settleActive(again)
    beginPass()
    for _, cell in ipairs(tes3.getActiveCells()) do
        local ok, err = pcall(settleCell, cell, again)
        if not ok then log("error in %s: %s", tostring(cell.editorName), tostring(err)) end
    end
    endPass()
end

event.register(tes3.event.cellChanged, function()
    timer.delayOneFrame(function() settleActive() end)     -- after the cell's references are all in place
end)
event.register(tes3.event.loaded, function()
    sessionLogged, missingLogged = {}, {}
    held, animStopped, heldScripts, prevAnim = weak(), weak(), heldScripts, weak()   -- the old references are gone
    timer.delayOneFrame(function() settleActive() end)
end)

-- bard audio & visual fixes -----------------------------------------------------------------------
local isBardRef = isPerformer

-- AM_Lute is a shield: with "show unreadied shields on back" Weapon Sheathing hangs it on the bard's back and hides
-- his hand's shield bone. A lute shield goes on that mod's exclusion list, which it reads each time it draws one.
event.register(tes3.event.initialized, function()
    if not config.enabled then return end
    local sheathing = include("weaponSheathing.config")
    if not sheathing or type(sheathing.blocked) ~= "table" then return end
    for obj in tes3.iterateObjects(tes3.objectType.armor) do
        if obj.slot == tes3.armorSlot.shield and obj.mesh and obj.mesh:lower():find("misc_de_lute", 1, true) then
            sheathing.blocked[obj.id:lower()] = true
        end
    end
end)

-- The singing scripts have no MenuMode check, so cutting the song only makes them Say the next. All begin
-- "if ( state ) / set state to 0 / return": state is set again each frame of the dialogue, so each is skipped.
-- positionOnce tells that script family from another script's own "state".
local quietBard                          -- safe handle, only while the dialogue is open
local quietScript                        -- its script, while a scriptExecute filter skips it

local function skipScriptFrame(ref)
    local context = ref.context
    if context and context.state ~= nil and context.positiononce ~= nil then context.state = 1 end
end

-- the bard's own script is skipped while the dialogue is open (its filter: only that script reaches this)
local function keepQuiet(e)
    if quietBard and quietBard:valid() and e.reference == quietBard:getObject() then
        e.block = true
        return false
    end
end

local function endQuiet()
    if quietScript then
        event.unregister(tes3.event.scriptExecute, keepQuiet, { filter = quietScript })
        quietScript = nil
    end
    quietBard = nil
end

-- The performing animation. The lute is not the script's doing: it is the NPC's own animation (an animation mesh such
-- as Animated Morrowind's, loaded into MWSE's "override layer"). The game freezes animations in menu mode, but
-- Animated Dialogue's "Preserve Custom NPC Animations" keeps an override animation going on purpose (it steps the
-- skeleton through that animation's own loop every frame of the dialogue), so cutting the song left the bard playing.
-- When the singing is cut, the performer is given the plain animation (the one a stopped performer stands with) and
-- an idle; our uiActivated handler has a higher priority than Animated Dialogue's, so it begins with that plain
-- animation and keeps it going. When the dialogue ends the performer gets its own animation back, and the groups it
-- was playing. Nothing of Animated Dialogue is touched: only its events are listened to, last in line.
local AD_STARTED = "tauer.animatedDialogue.dialogueStarted"
local AD_ENDED = "tauer.animatedDialogue.dialogueEnded"
local AD_INTERRUPTED = "tauer.animatedDialogue.dialogueInterrupted"
local AD_LAST = -5000                         -- after everything Animated Dialogue does at the end of a dialogue
local BACKSTOP = 1.5                          -- seconds: the animation comes back even if that mod's end never arrives

local pendingAnim                             -- { handle, plain, groups, ad }: the performer whose animation is stopped
local backstop                                -- real-time timer for the above
local settle                                  -- game-time timer: the pause after the dialogue before the animation restarts
local RESTORE_DELAY = 3                       -- seconds of game time (the Mod Config slider's default; 0 = at once)

local function idleGroup() return tes3.animationGroup and tes3.animationGroup.idle or 0 end

-- a group that is really playing something: 0 is the neutral idle, 255 "nothing" (the shield arm), 150 and up unused
local function active(group)
    if type(group) == "number" and group > 0 and group < 150 then return group end
    return nil
end

-- what each body section is playing: lower, upper, shield (the order of tes3.playAnimation's parameters)
local function currentGroups(ref)
    local data = ref.animationData
    local cur = data and data.currentAnimGroups
    if not cur then return nil end
    return { cur[1], cur[2], cur[3] }
end

local function cancelBackstop()
    if backstop then
        pcall(function() backstop:cancel() end)
        backstop = nil
    end
end

local function cancelSettle()
    if settle then
        pcall(function() settle:cancel() end)
        settle = nil
    end
end

local function cancelTimers() cancelBackstop() cancelSettle() end

local function restoreDelay()
    local d = tonumber(config.restoreDelay)
    if not d then return RESTORE_DELAY end
    return math.max(0, math.min(d, 10))
end

local loggedPlainThrow = false

local function stopAnimation(ref)
    if animStopped[ref] or held[ref] then return nil end     -- already standing plainly: nothing to stop or give back
    local data = ref.animationData
    if not (ref.sceneNode and data) then return nil end
    local base = baseOf(ref)
    local groups = currentGroups(ref)
    local plain = hasPerformingAnim(base) or data.hasOverrideAnimations == true
    local performing = groups and (active(groups[1]) or active(groups[2]) or active(groups[3]))
    if not plain and not performing then return nil end      -- a script performer between songs: nothing playing
    local state = { handle = tes3.makeSafeObjectHandle(ref), groups = groups }
    if plain then
        -- The plain animation is a base animation, with no override layer, so MWSE's loadAnimation swaps the model and
        -- then throws "Animation file failed to load" (its check for an override layer fails). The performer has the
        -- plain animation on him all the same: count it as loaded, or restoreAnimation never gives his own back.
        touched[ref] = state.handle
        local file = plainAnim(base)
        noticeExpectedThrow(ref, file)
        local ok, err = pcall(tes3.loadAnimation, { reference = ref, file = file })
        if not ok and not loggedPlainThrow then
            loggedPlainThrow = true
            log("%s: MWSE says '%s' for the plain animation; it is on him all the same", describe(ref), tostring(err))
        end
        state.plain = true
    end
    pcall(tes3.playAnimation, { reference = ref, group = idleGroup() })
    -- the dialogue is a menu mode, where nothing steps the animation: draw the first frame of the idle now
    pcall(function() ref.animationData.actorNode:update({ controllers = true, children = true, time = 0 }) end)
    return state
end

local function restoreAnimation()
    local state = pendingAnim
    pendingAnim = nil
    cancelTimers()
    if not state or not state.handle:valid() then return end
    local ref = state.handle:getObject()
    if not ref or ref.disabled or ref.deleted or not ref.sceneNode then             -- gone: its animation goes with it
        if ref then touched[ref] = nil end
        return
    end
    local mobile = ref.mobile
    if ref.isDead == true or (mobile and mobile.isDead) then touched[ref] = nil return end
    if state.plain then pcall(tes3.loadAnimation, { reference = ref }) end           -- its own performing animation again
    touched[ref] = nil
    local g = state.groups or {}
    local lower, upper, shield = active(g[1]), active(g[2]), active(g[3])
    local p = { reference = ref, shield = shield }
    if lower and lower == upper then
        p.group = lower
    else
        p.lower, p.upper = lower, upper
    end
    if not (lower or upper or shield) then
        if not state.plain then return end
        p.group = idleGroup()                                                       -- restarts the idle, now the lute
    end
    if not (mobile and mobile.inCombat) then pcall(tes3.playAnimation, p) end       -- a fight is the AI's to animate
    log("%s: performing animation restored after the dialogue", describe(ref))
end

local function sameRef(state, ref)
    return state and state.handle:valid() and state.handle:getObject() == ref
end

-- Backstop: a performer whose animation a dialogue swapped, who is not being held plain on purpose and whose
-- dialogue no longer has him, goes back to his own animation (whatever stopped restoreAnimation from reaching him).
local function healTouched()
    for ref in pairs(touched) do
        local live = pendingAnim and sameRef(pendingAnim, ref)
        if not live and not held[ref] and not animStopped[ref] then
            local handle = touched[ref]
            touched[ref] = nil
            local ok, here = pcall(function()
                return handle and handle:valid() and ref.sceneNode ~= nil and not ref.disabled and not ref.deleted
                    and ref.isDead ~= true and not (ref.mobile and ref.mobile.isDead)
            end)
            if ok and here then
                pcall(tes3.loadAnimation, { reference = ref })
                log("%s: his own animation given back (backstop)", describe(ref))
            end
        end
    end
end

local function beginAnimation(ref)
    if not config.dialogueAnimation or sameRef(pendingAnim, ref) then return end
    restoreAnimation()                                   -- another's, if one is still stopped
    local ok, state = pcall(stopAnimation, ref)
    if not ok then
        log("%s: stopping the performing animation failed: %s", describe(ref), tostring(state))
    elseif state then
        pendingAnim = state
        log("%s: performing animation stopped for the dialogue%s", describe(ref), state.plain and " (plain animation)" or "")
    end
end

-- The dialogue is over. He keeps standing with the plain animation and idle for a moment (restoreDelay seconds of
-- game time, so it does not run in a menu), then gets his own animation back. One timer at a time; a new dialogue,
-- his death, a cell change or a load cancels it (the cell change and the load restore him first where they can).
-- Without a usable timer he is restored at once: he never stays plain.
local function scheduleRestore()
    local state = pendingAnim
    if not state then return end
    if settle then return end                                    -- already counting: never stacked
    local delay = restoreDelay()
    if delay <= 0 then restoreAnimation() return endQuiet() end
    cancelBackstop()
    local ok = pcall(function()
        settle = timer.start({ type = timer.simulate, duration = delay, callback = function()
            settle = nil
            restoreAnimation()
            endQuiet()                                           -- his script runs again only now
            healTouched()                                        -- and whoever the restore missed
        end })
    end)
    if not ok or not settle then settle = nil restoreAnimation() return endQuiet() end
end

-- the dialogue is over: now, or once Animated Dialogue has taken its last picture of the pose (it eases out of it)
local function onMenuExitAnimation()
    local state = pendingAnim
    if not state or settle then return end
    if not state.ad then return scheduleRestore() end
    cancelBackstop()
    pcall(function()
        backstop = timer.start({ type = timer.real, duration = BACKSTOP, callback = function()
            backstop = nil
            scheduleRestore()
        end })
    end)
end

event.register(AD_STARTED, function() if pendingAnim then pendingAnim.ad = true end end, { priority = AD_LAST })
event.register(AD_ENDED, scheduleRestore, { priority = AD_LAST })
event.register(AD_INTERRUPTED, scheduleRestore, { priority = AD_LAST })
event.register(tes3.event.cellChanged, function() restoreAnimation() endQuiet() healTouched() end)
event.register(tes3.event.loaded, function() pendingAnim = nil touched = weak() cancelTimers() end)    -- the old references are gone
-- he died while waiting: nothing to give back (a dead performer's animation is left as it is)
event.register(tes3.event.death, function(e)
    if pendingAnim and e.reference and sameRef(pendingAnim, e.reference) then
        local ref = e.reference
        pendingAnim = nil
        cancelTimers()
        touched[ref] = nil
        endQuiet()
    end
end)

local function onMenuDialogActivated(e)
    local target = tes3ui.getServiceActor()
    if not target then
        local menu = e.element or tes3ui.findMenu("MenuDialog")
        target = menu and menu:getPropertyObject("PartHyperText_actor")
    end
    local ref = target and target.reference
    endQuiet()
    if pendingAnim and not (ref and sameRef(pendingAnim, ref)) then restoreAnimation() end
    if pendingAnim then cancelTimers() end                -- the same performer again: he stays plain for this one too
    if not config.enabled or not ref or not isKnown(ref.cell) or not isBardRef(ref) then return end
    quietBard = tes3.makeSafeObjectHandle(ref)
    skipScriptFrame(ref)                 -- first, or the script starts the next song
    tes3.removeSound({ reference = ref })
    local script = baseOf(ref).script
    if script and tes3.event.scriptExecute then
        quietScript = script
        if not event.isRegistered(tes3.event.scriptExecute, keepQuiet, { filter = script }) then
            event.register(tes3.event.scriptExecute, keepQuiet, { filter = script })
        end
    end
    log("%s: singing paused for the dialogue", describe(ref))
    beginAnimation(ref)                  -- before Animated Dialogue (priority), so it starts from the plain animation
end
event.register(tes3.event.uiActivated, onMenuDialogActivated, { filter = "MenuDialog", priority = 100 })
-- The bard's script stays held until his animation is back: the restore (tes3.loadAnimation) rebuilds him, the engine
-- forgets the song he was singing (SayDone turns true while it plays on), and a script already running again would
-- start a second song over it. Held until then, the first song after the dialogue starts once, after the restore.
event.register(tes3.event.menuExit, function()
    if not pendingAnim then endQuiet() end
    onMenuExitAnimation()
    healTouched()
end)
event.register(tes3.event.loaded, endQuiet)

-- Mod Config menu ---------------------------------------------------------------------------------
event.register(tes3.event.modConfigReady, function()
    local template = mwse.mcm.createTemplate({ name = "One Band Per Inn" })
    template:saveOnClose(CONFIG_NAME, config)
    local page = template:createSideBarPage({
        label = "Settings",
        description = "When two or more bards or musicians perform in the same building, one is picked at random to "
            .. "keep playing (the same one on every visit in this game) and the others stop: their song stops and "
            .. "they go back to standing normally. Nobody is hidden or removed. Choices are written to "
            .. "MWSE\\logs\\mwperformers.log."
            .. "\n\nAlso, while it is on, bards stop singing while you talk to them, and hold their lute instead "
            .. "of Weapon Sheathing showing it on their back (the lute part takes effect after a restart).",
    })
    page:createOnOffButton({
        label = "One performer per place",
        description = "On: one performer plays per building. Off: all performers resume as you revisit each building.",
        variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
        callback = function() if tes3.player then settleActive() end end,
    })
    page:createOnOffButton({
        label = "Performers stop playing in dialogue",
        description = "While you talk to a performer, the lute (or drum) animation stops along with the singing, and "
            .. "it is back when the dialogue ends. Off: only the singing stops.",
        variable = mwse.mcm.createTableVariable({ id = "dialogueAnimation", table = config }),
    })
    page:createSlider({
        label = "Pause before the animation restarts (seconds)",
        description = "After a dialogue with a performer ends, he stands for this long (game time, it does not run "
            .. "in a menu) before the lute or drum animation starts again. 0 = at once. Default 3.",
        min = 0, max = 10, step = 0.5, jump = 1, decimalPlaces = 1,
        variable = mwse.mcm.createTableVariable({ id = "restoreDelay", table = config }),
    })
    page:createButton({
        buttonText = "Pick again here now",
        description = "Picks a different performer, at random, for the building you're in (or applies the switch "
            .. "above here without leaving).",
        callback = function()
            if not (tes3.player and tes3.mobilePlayer) then
                tes3.messageBox("Load a game first: this picks a performer in the place you are in.")
                return
            end
            local ok, err = pcall(settleActive, true)
            if not ok then
                mwse.log("[mwperformers] picking again failed: %s", tostring(err))
                tes3.messageBox("mwperformers: that didn't work. The reason is in MWSE.log.")
                return
            end
            tes3.messageBox("Performers here: " .. (config.enabled and "one picked to perform." or "all perform."))
        end,
    })
    page:createOnOffButton({
        label = "Write decisions to MWSE\\logs\\mwperformers.log",
        description = "Keeps a record of which performer was picked and which were stopped or started again in the "
            .. "log file.",
        variable = mwse.mcm.createTableVariable({ id = "log", table = config }),
    })
    template:register()
end)
