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

    Nothing is decided in advance from a generated list, so it works for any mods in any load order. The
    Mod Config menu can pick again for the place you're in. Off: everyone performs again.
    Performers that an older version hid (disabled) are shown again when their place is next visited.
    Decisions are written to Data Files\MWSE\logs\mwperformers.log.

    While it is on, a bard also stops singing while you talk to them, and holds their lute (Weapon
    Sheathing showed it on the back, as it is a shield). The performing animation (the lute) stops at the same
    moment, for any performer, and comes back when the dialogue ends; Animated Dialogue is not patched, it
    just finds the plain animation where it would have found the lute.
]]

local CONFIG_NAME = "mwperformers"
local config = mwse.loadConfig(CONFIG_NAME, { enabled = false, log = true, dialogueAnimation = true })

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
        elseif node and pcall(tes3.loadAnimation, { reference = ref, file = plainAnim(base) }) then
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
    if not cell or not cell.isInterior then return end
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
    sessionLogged = {}
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

local function skipScriptFrame(ref)
    local context = ref.context
    if context and context.state ~= nil and context.positiononce ~= nil then context.state = 1 end
end

local function keepQuiet()
    if quietBard and quietBard:valid() then skipScriptFrame(quietBard:getObject()) end
end

local function endQuiet()
    if not quietBard then return end
    quietBard = nil
    event.unregister(tes3.event.enterFrame, keepQuiet)
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
        if not pcall(tes3.loadAnimation, { reference = ref, file = plainAnim(base) }) then return nil end
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
    cancelBackstop()
    if not state or not state.handle:valid() then return end
    local ref = state.handle:getObject()
    if not ref or ref.disabled or ref.deleted or not ref.sceneNode then return end   -- gone: its animation goes with it
    local mobile = ref.mobile
    if ref.isDead == true or (mobile and mobile.isDead) then return end
    if state.plain then pcall(tes3.loadAnimation, { reference = ref }) end           -- its own performing animation again
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

-- the dialogue is over: now, or once Animated Dialogue has taken its last picture of the pose (it eases out of it)
local function onMenuExitAnimation()
    local state = pendingAnim
    if not state then return end
    if not state.ad then return restoreAnimation() end
    cancelBackstop()
    pcall(function()
        backstop = timer.start({ type = timer.real, duration = BACKSTOP, callback = restoreAnimation })
    end)
end

event.register(AD_STARTED, function() if pendingAnim then pendingAnim.ad = true end end, { priority = AD_LAST })
event.register(AD_ENDED, restoreAnimation, { priority = AD_LAST })
event.register(AD_INTERRUPTED, restoreAnimation, { priority = AD_LAST })
event.register(tes3.event.cellChanged, restoreAnimation)
event.register(tes3.event.loaded, function() pendingAnim = nil cancelBackstop() end)    -- the old references are gone

local function onMenuDialogActivated(e)
    local target = tes3ui.getServiceActor()
    if not target then
        local menu = e.element or tes3ui.findMenu("MenuDialog")
        target = menu and menu:getPropertyObject("PartHyperText_actor")
    end
    local ref = target and target.reference
    endQuiet()
    if pendingAnim and not (ref and sameRef(pendingAnim, ref)) then restoreAnimation() end
    if not config.enabled or not ref or not isBardRef(ref) then return end
    quietBard = tes3.makeSafeObjectHandle(ref)
    skipScriptFrame(ref)                 -- first, or the script starts the next song
    tes3.removeSound({ reference = ref })
    event.register(tes3.event.enterFrame, keepQuiet)
    log("%s: singing paused for the dialogue", describe(ref))
    beginAnimation(ref)                  -- before Animated Dialogue (priority), so it starts from the plain animation
end
event.register(tes3.event.uiActivated, onMenuDialogActivated, { filter = "MenuDialog", priority = 100 })
event.register(tes3.event.menuExit, function() endQuiet() onMenuExitAnimation() end)
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
        description = "Only one performer plays in each building. Off: everyone performs again as you visit each place.",
        variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
        callback = function() if tes3.player then settleActive() end end,
    })
    page:createOnOffButton({
        label = "Performers stop playing in dialogue",
        description = "While you talk to a performer, the lute (or drum) animation stops along with the singing, and "
            .. "it is back when the dialogue ends. Off: only the singing stops.",
        variable = mwse.mcm.createTableVariable({ id = "dialogueAnimation", table = config }),
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
