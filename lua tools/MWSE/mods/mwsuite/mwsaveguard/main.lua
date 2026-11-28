local validator = require("mwsaveguard.validator")

-- Compatibility aliases for existing mods
package.loaded["corruptsaveguard.validator"] = validator
package.loaded["corruptsaveguard"] = true

local CONFIG_NAME = "mwsaveguard"
local defaults = {
	enabled = false,
	settleWindow = 5.0,
	validateOnLoad = true,
	copyNoticesToMWSELog = false,   -- every save's notices go to MWSE\logs\mwsaveguard.log; this copies them too
	cleanClones = true,
	retrySwallowedSaves = true,   -- a save another mod holds back is asked for again every second, for a while
}
local config = mwse.loadConfig(CONFIG_NAME, defaults)
-- an older build wrote "logToMWSE"; nothing reads it (copyNoticesToMWSELog is the switch), so it only looked
-- enabled. Drop it from the saved file once.
if config.logToMWSE ~= nil then
	config.logToMWSE = nil
	pcall(mwse.saveConfig, CONFIG_NAME, config)
end

-- Routine notices (each save requested, deferred, completed) go to their own log, one per session: in MWSE.log
-- they buried everything else. Problems (a corrupt save blocked, a save that failed, a player clone) still go to
-- MWSE.log too.
local LOG_DIR = "Data Files\\MWSE\\logs"
local logFile, logTried = nil, false

local function logMsg(fmt, ...)
	local line = string.format(fmt, ...)
	if not logFile and not logTried then
		logTried = true
		pcall(lfs.mkdir, LOG_DIR)
		logFile = io.open(LOG_DIR .. "\\mwsaveguard.log", "w")
		if logFile then
			logFile:write(os.date("mwsaveguard log, session started %Y-%m-%d %H:%M:%S\n"))
		end
	end
	if logFile then
		logFile:write(os.date("%H:%M:%S  "), line, "\n")
		logFile:flush()
	end
	if config.copyNoticesToMWSELog or not logFile then
		mwse.log("%s", line)
	end
end

----------------------------------------------------------------------------------------------------
-- 1. LOAD PROTECTION: Block corrupt/truncated saves before Morrowind engine loads them
----------------------------------------------------------------------------------------------------

local function restoreMainMenu()
	if tes3.onMainMenu() then
		local mainMenu = tes3ui.findMenu(tes3ui.registerID("MenuOptions"))
		if mainMenu then
			mainMenu.visible = true
		end
		local menuLoad = tes3ui.findMenu(tes3ui.registerID("MenuLoad"))
		if menuLoad then
			menuLoad.visible = true
		end
		tes3ui.enterMenuMode()
	end
end

local QUARANTINE_DIR = "saves\\quarantine"

--- Moves a rejected save to saves\quarantine\ (a rename: nothing is deleted). Returns the new path, or nil.
local function quarantine(path, baseName)
	if not path or not lfs.fileexists(path) then return nil end
	pcall(lfs.mkdir, QUARANTINE_DIR)
	local dest = QUARANTINE_DIR .. "\\" .. baseName
	if lfs.fileexists(dest) then                        -- an earlier quarantined save of the same name is kept
		dest = QUARANTINE_DIR .. "\\" .. os.date("%Y%m%d-%H%M%S ") .. baseName
	end
	local ok = os.rename(path, dest)
	return ok and dest or nil
end

--- @param e loadEventData
local function onPreLoad(e)
	if not config.enabled or not config.validateOnLoad then
		return
	end

	-- Ignore new game initialization
	if e.newGame then
		return
	end

	local filename = e.filename
	if not filename or filename == "" then
		return
	end

	local resolvedPath = validator.resolveSavePath(filename)
	local isValid, reason = validator.validateSave(resolvedPath)
	if isValid and reason ~= "Valid save" then
		mwse.log("[mwsaveguard] '%s': %s; loaded anyway.", tostring(resolvedPath), tostring(reason))
	end

	if not isValid then
		-- 1. Suppress native engine load call to prevent Morrowind.exe crash / dialog freeze
		e.block = true
		e.claim = true

		-- Notify any UI listeners (such as UI Expansion) that loading was aborted
		event.trigger("loadAborted")

		local saveBaseName = (resolvedPath and resolvedPath:match("([^\\]+)$")) or filename
		mwse.log("[mwsaveguard] INTERCEPTED corrupt save load: '%s' (%s). Load blocked.", tostring(resolvedPath), reason)

		-- 2. Move the save out of the way (never deleted): saves\quarantine\
		local movedTo = quarantine(resolvedPath, saveBaseName)
		if movedTo then
			mwse.log("[mwsaveguard] Quarantined: '%s' -> '%s'", tostring(resolvedPath), movedTo)
		else
			mwse.log("[mwsaveguard] Could not move '%s' to quarantine; it was left where it is.", tostring(resolvedPath))
		end

		-- 3. Restore UI / Main Menu so the user is never stuck or locked out
		restoreMainMenu()

		-- 4. Present user-facing error message
		local okText = "OK"
		local okGmst = tes3.findGMST(tes3.gmst.sOk)
		if okGmst and okGmst.value and #okGmst.value > 0 then
			okText = okGmst.value
		end

		local displayMsg = string.format("Save is corrupted and was not loaded.\n\nFile: %s\nReason: %s\n\n%s", saveBaseName, reason,
			movedTo and ("It was moved to " .. movedTo .. ".") or "It could not be moved to quarantine and was left in place.")
		tes3.messageBox({
			message = displayMsg,
			buttons = { okText },
			callback = function()
				restoreMainMenu()
			end
		})

		return false
	end
end

-- Priority -9000 ensures this runs right before native load call
event.register("load", onPreLoad, { priority = -9000 })


----------------------------------------------------------------------------------------------------
-- 2. PLAYER CLONE PROTECTION: Detect and purge duplicate player actors to prevent save CTD
----------------------------------------------------------------------------------------------------

local function isPlayerClone(ref)
	if not ref or not tes3.player or ref == tes3.player then
		return false
	end
	-- a reference's own objectType is "reference"; the NPC type is on its base object
	local base = ref.baseObject
	if not base or base.objectType ~= tes3.objectType.npc then
		return false
	end

	-- 0. Explicit match on PlayerSaveGame dynamic player duplicate
	local refId = ref.id and ref.id:lower()
	if refId and refId:find("playersavegame") then
		return true
	end

	-- 1. Direct object / baseObject match: only the player character can have the 'player' base record
	local baseId = ref.baseObject and ref.baseObject.id and ref.baseObject.id:lower()
	if baseId == "player" then
		return true
	end
	if tes3.player.object and (ref.object == tes3.player.object or ref.baseObject == tes3.player.baseObject) then
		return true
	end

	return false
end

local function purgePlayerClones()
	if not config.enabled or config.cleanClones == false then
		return 0
	end
	if not tes3.player then
		return 0
	end

	local ok, activeCells = pcall(tes3.getActiveCells)
	if not ok or not activeCells then
		return 0
	end

	local toPurge = {}
	for _, cell in ipairs(activeCells) do
		for ref in cell:iterateReferences(tes3.objectType.npc) do
			if isPlayerClone(ref) then
				table.insert(toPurge, {
					ref = ref,
					cellName = cell.editorName or cell.displayName or cell.id or "Unknown Cell",
				})
			end
		end
	end

	for _, entry in ipairs(toPurge) do
		local ref = entry.ref
		local refName = (ref.object and ref.object.name) or "Player"
		local refId = (ref.baseObject and ref.baseObject.id) or (ref.id or "unknown")
		mwse.log("[mwsaveguard] Detected duplicate player clone '%s' [%s] in %s. Disabling reference.",
			refName, refId, entry.cellName)

		pcall(function()
			ref.position = tes3vector3.new(ref.position.x, ref.position.y, ref.position.z - 10000)
			ref:disable()
			ref.modified = true
		end)
	end

	if #toPurge > 0 then
		logMsg("[mwsaveguard] Disabled %d duplicate player clone(s) across active cells to prevent save corruption.", #toPurge)
	end

	return #toPurge
end


----------------------------------------------------------------------------------------------------
-- 3. SAVE STALLING / SETTLING WINDOW: Prevent save crashes during volatile world transitions
----------------------------------------------------------------------------------------------------

local lastCellChangeTime = os.clock()
local lastCharGenFinishTime = os.clock()
local isExecutingDeferredSave = false
local pendingSaves = {}          -- in the order asked for, one per file name
local pendingSince = 0
local deferTimer = nil
local PENDING_MAX = 30          -- s: a deferred save older than this no longer holds the menu shut

local function onCellChanged(e)
	lastCellChangeTime = os.clock()
	purgePlayerClones()
	timer.delayOneFrame(function()
		purgePlayerClones()
	end)
end
event.register("cellChanged", onCellChanged)

local function onCharGenFinished(e)
	lastCharGenFinishTime = os.clock()
	purgePlayerClones()
end
event.register("charGenFinished", onCharGenFinished)

-- Also monitor on load so newly loaded games settle before autosaving
local function onLoaded(e)
	pendingSaves, deferTimer = {}, nil        -- MWSE cancelled the timer before this event
	lastCellChangeTime = os.clock()
	if e and e.newGame then
		lastCharGenFinishTime = 0
	else
		lastCharGenFinishTime = os.clock()
	end
	timer.delayOneFrame(function()
		purgePlayerClones()
	end)
end
event.register("loaded", onLoaded)

local executeDeferredSave

executeDeferredSave = function()
	deferTimer = nil
	if #pendingSaves == 0 then
		return
	end

	-- Do not save on main menu
	if tes3.onMainMenu() then
		pendingSaves = {}
		return
	end

	-- Wait if any background thread is loading or engine is in the middle of a transition
	local dh = tes3.dataHandler
	local isBackground = dh and dh.backgroundThreadRunning
	local ndd = dh and dh.nonDynamicData
	local isSavingOrLoading = ndd and ndd.isSavingOrLoading
	local inMenu = tes3ui.menuMode()

	if inMenu or isBackground or isSavingOrLoading then
		-- Re-check in 1.0 second until menus close and the engine is quiet
		deferTimer = timer.start({
			duration = 1.0,
			type = timer.real,
			callback = executeDeferredSave,
		})
		return
	end

	-- Check player vitality
	local mobile = tes3.mobilePlayer
	if not mobile or mobile.isDead or (mobile.health and mobile.health.current <= 0) then
		pendingSaves = {}
		return
	end

	-- Purge duplicate clones right before writing deferred save
	purgePlayerClones()

	local waiting = pendingSaves
	pendingSaves = {}

	isExecutingDeferredSave = true
	for _, target in ipairs(waiting) do
		logMsg("[mwsaveguard] World settled. Executing deferred save: '%s'...", tostring(target.filename or "save"))

		local saveParams = {}
		if target.filename and target.filename ~= "" then
			saveParams.file = target.filename
		end
		if target.name and target.name ~= "" then
			saveParams.name = target.name
		end

		local ok, err = pcall(tes3.saveGame, saveParams)
		if not ok then
			mwse.log("[mwsaveguard] Error executing deferred save: %s", tostring(err))
		end
	end
	isExecutingDeferredSave = false
end

local expectSave                        -- set below: watches that a save it let through reaches the last handler

--- @param e saveEventData
local function onSave(e)
	if not config.enabled then
		return
	end

	-- Always purge duplicate player clones before save proceeds or gets queued
	purgePlayerClones()

	local dh = tes3.dataHandler
	local ndd = dh and dh.nonDynamicData
	local isVolatileTransition = ndd and ndd.isSavingOrLoading

	local window = tonumber(config.settleWindow) or 5.0
	local now = os.clock()
	local cellElapsed = now - lastCellChangeTime
	local charGenElapsed = now - lastCharGenFinishTime
	local cell = tes3.player and tes3.player.cell

	logMsg(
		"[mwsaveguard] Save requested (name as asked, before any renamer): file='%s', name='%s', cell='%s', menu=%s, background=%s, volatile=%s, cellElapsed=%.1fs, deferred=%s",
		tostring(e.filename),
		tostring(e.name),
		tostring(cell and (cell.displayName or cell.id) or "<none>"),
		tostring(tes3ui.menuMode()),
		tostring(dh and dh.backgroundThreadRunning or false),
		tostring(isVolatileTransition or false),
		cellElapsed,
		tostring(isExecutingDeferredSave)
	)

	-- If our own deferred execution triggered this, allow it straight through
	if isExecutingDeferredSave then
		expectSave(e)
		return
	end

	-- Calculate the minimum elapsed time across all settling triggers
	local minElapsed = math.min(cellElapsed, charGenElapsed)

	if minElapsed < window or isVolatileTransition then
		-- Suppress immediate save during volatile transitions / load screens to prevent corruption/crash
		e.block = true
		e.claim = true

		local remaining = math.max(0.5, window - minElapsed)
		for i = #pendingSaves, 1, -1 do         -- the same file asked for again: the newer request counts
			if pendingSaves[i].filename == e.filename then table.remove(pendingSaves, i) end
		end
		pendingSaves[#pendingSaves + 1] = { filename = e.filename, name = e.name }
		pendingSince = now

		logMsg("[mwsaveguard] Intercepted save '%s' during world settling window (%.1fs remaining). Deferring save...", tostring(e.filename), remaining)

		if deferTimer then
			deferTimer:cancel()
		end

		deferTimer = timer.start({
			duration = remaining,
			type = timer.real,
			callback = executeDeferredSave,
		})

		return false
	end
	expectSave(e)
end

-- first: before any other save handler (like SSS or native); 9999 is the top of the band luafix keeps
-- every mod's priorities in
event.register("save", onSave, { priority = 9999 })

-- A save another mod swallows: MWSE stops calling save handlers at the first one that returns false (or claims
-- the event), so the engine never writes it and nothing says why. This handler runs last of all; when a save we
-- let through never reaches it, the next frame names the save handlers that were registered.
local SAVE_LAST_PRIORITY = -9999        -- the lowest priority mwguard calls ordinary (|p| < 10000)
local awaitingSave = nil                -- { filename, name, menu } of the last save onSave let through
local renamedTo = nil                   -- { filename, name } as the default-priority handlers (the renamers) left it
local retrying = nil                    -- a swallowed save being asked for again: { filename, name, menu, since, tries, timer }
local RETRY_EVERY, RETRY_MAX = 1.0, 20.0       -- s

-- A named upvalue of a function (nil when it has none, or it is a C function).
local function upvalue(fn, want)
	if type(fn) ~= "function" then return nil end
	for i = 1, 200 do
		local n, v = debug.getupvalue(fn, i)
		if n == nil then return nil end
		if n == want then return v end
	end
end

-- MWSE's own event.register: the one that holds getEventTable and eventPriorities. Other mods wrap event.register
-- and keep the one they wrapped under a name of their own (mwguard: origRegister, mwhangwatch: realRegister,
-- mwpluginpatches: nativeRegister), so this follows every function upvalue, breadth first, whatever it is called,
-- until it finds the one with both. (A wrapper's unregister / isRegistered upvalues have getEventTable but not
-- eventPriorities, so they are passed over.)
local function coreRegister(start)
	local queue, seen, head = { start }, {}, 1
	while head <= #queue and head <= 64 do
		local fn = queue[head]
		head = head + 1
		if type(fn) == "function" and not seen[fn] then
			seen[fn] = true
			if upvalue(fn, "getEventTable") and upvalue(fn, "eventPriorities") then return fn end
			for i = 1, 200 do
				local n, v = debug.getupvalue(fn, i)
				if n == nil then break end
				if type(v) == "function" and not seen[v] then queue[#queue + 1] = v end
			end
		end
	end
	return nil
end

-- { {fn, priority} } of an event's callbacks, highest priority first, read from MWSE's event table (empty when it
-- can't be read)
local function eventHandlers(name)
	local out = {}
	pcall(function()
		local register = coreRegister(event.register)
		if not register then return end
		local general = upvalue(upvalue(register, "getEventTable"), "generalEvents")
		local priorities = upvalue(register, "eventPriorities") or {}
		for _, cb in ipairs(general and general[name] or {}) do
			out[#out + 1] = { fn = cb, priority = priorities[cb] }
		end
	end)
	return out
end

local function saveHandlers()
	local out = {}
	for _, h in ipairs(eventHandlers("save")) do
		local info = debug.getinfo(h.fn, "S") or {}
		local src = (info.short_src or info.source or "?"):gsub("^.-[/\\]mods[/\\]", "")
		out[#out + 1] = string.format("%s:%s (priority %s)", src, tostring(info.linedefined), tostring(h.priority))
	end
	return out
end

-- WBSR's voiceover save block, lifted for tavern bards' songs only (mwsaveguard\wbsr_bard.lua). Nothing at all
-- without WBSR.
local wbsrBard = nil
do
	local ok, mod = pcall(require, "mwsaveguard.wbsr_bard")
	if ok and type(mod) == "table" then
		wbsrBard = mod.setup({ config = config, log = logMsg, handlers = eventHandlers })
	else
		mwse.log("[mwsaveguard] wbsr_bard.lua could not be loaded: %s", tostring(mod))
	end
end

-- Sophisticated Save System (and any other renamer) works at the default priority 0 and rewrites the file name
-- of a quicksave / autosave; this is just below it, so what it sees is the name after them.
local function onSaveRenamed(e)
	if awaitingSave then renamedTo = { filename = e.filename, name = e.name } end
end
event.register("save", onSaveRenamed, { priority = -1 })

local function onSaveLast(e)
	if e.block then return end          -- blocked without stopping the chain: still a swallowed save
	local asked = awaitingSave
	awaitingSave = nil
	if asked then
		logMsg("[mwsaveguard] Save goes ahead as: file='%s', name='%s' (requested as '%s')",
			tostring(e.filename), tostring(e.name), tostring(asked.filename))
	end
end
event.register("save", onSaveLast, { priority = SAVE_LAST_PRIORITY })

-- A swallowed save is asked for again every second, up to RETRY_MAX seconds (the usual holder is WBSR, for as long
-- as a voice line plays). One at a time: a newer request takes the place of an older one.
local function stopRetry()
	local r = retrying
	retrying = nil
	if r and r.timer then pcall(function() r.timer:cancel() end) end
end

local retryTick
local function armRetry(r)
	local ok, t = pcall(timer.start, { duration = RETRY_EVERY, type = timer.real, callback = retryTick })
	r.timer = ok and t or nil
	if not ok then retrying = nil end
end

retryTick = function()
	local r = retrying
	if not r then return end
	r.timer = nil
	if not tes3.player or tes3.onMainMenu() then
		retrying = nil
		return
	end
	if os.clock() - r.since > RETRY_MAX then
		retrying = nil
		logMsg("[mwsaveguard] Gave up on save '%s' after %.0f s: another mod kept holding it back.", tostring(r.filename), RETRY_MAX)
		pcall(tes3.messageBox, "mwsaveguard: the save did not go through; another mod kept holding it back. Details: MWSE\\logs\\mwsaveguard.log.")
		return
	end
	local dh = tes3.dataHandler
	local ndd = dh and dh.nonDynamicData
	-- not while the world is settling or a load is going on; menus only for a save that was asked for in one
	if (tes3ui.menuMode() and not r.menu) or (dh and dh.backgroundThreadRunning) or (ndd and ndd.isSavingOrLoading)
		or os.clock() - lastCellChangeTime < (tonumber(config.settleWindow) or 5.0) then
		armRetry(r)
		return
	end
	r.tries = r.tries + 1
	local params = {}
	if r.filename and r.filename ~= "" then params.file = r.filename end
	if r.name and r.name ~= "" then params.name = r.name end
	logMsg("[mwsaveguard] Asking again for save '%s' (try %d).", tostring(r.filename), r.tries)
	isExecutingDeferredSave = true
	local ok, err = pcall(tes3.saveGame, params)
	isExecutingDeferredSave = false
	if not ok then
		mwse.log("[mwsaveguard] Error asking again for a swallowed save: %s", tostring(err))
		retrying = nil
		return
	end
	-- "saved" ends it; a save held back again leaves it here, and the next tick tries once more
	if retrying == r then armRetry(r) end
end

local function startRetry(missed)
	if config.retrySwallowedSaves == false or not tes3.player then return end
	local r = retrying
	if r and r.tries > 0 and r.filename == missed.filename then return end      -- our own try, held back again: it goes on
	if r and missed.filename == "autosave" then return end                       -- an autosave never replaces a save you asked for
	if r then stopRetry() end
	r = { filename = missed.filename, name = missed.name, menu = missed.menu, since = os.clock(), tries = 0 }
	retrying = r
	armRetry(r)
	if retrying == r and missed.filename ~= "autosave" then
		pcall(tes3.messageBox, "mwsaveguard: another mod is holding saves back (usually a voice line playing). Trying again.")
	end
end

local function checkSaveReached()
	local missed = awaitingSave
	awaitingSave = nil
	local renamed = renamedTo
	renamedTo = nil
	if not missed then return end
	local handlers = saveHandlers()
	local asked = tostring(missed.filename or missed.name or "save")
	local renamers
	if renamed then
		renamers = string.format("yes, it was renamed to '%s', then a lower handler stopped it", tostring(renamed.filename))
	else
		renamers = "no, a handler above priority 0 stopped it first, so nothing renamed it"
	end
	mwse.log("[mwsaveguard] Save '%s' was swallowed by another mod: a save handler blocked it before the engine "
		.. "wrote it, and saving gave no message. Renamers reached: %s. Save handlers, highest priority first: %s",
		asked, renamers,
		#handlers > 0 and table.concat(handlers, "; ") or "(MWSE's event table could not be read)")
	logMsg("[mwsaveguard] Save swallowed by another mod: file='%s' (requested name; renamers reached: %s) (handlers: %s)",
		asked, renamers, #handlers > 0 and table.concat(handlers, "; ") or "?")
	startRetry(missed)
end

expectSave = function(e)
	awaitingSave = { filename = e.filename, name = e.name, menu = tes3ui.menuMode() }
	renamedTo = nil
	-- a real-time timer: a save from the options menu happens in menu mode, where simulate timers stand still
	local ok = pcall(timer.delayOneFrame, checkSaveReached, timer.real)
	if not ok then awaitingSave = nil end
end

local function onSaved(e)
	logMsg(
		"[mwsaveguard] Save completed: file='%s', name='%s'",
		tostring(e.filename),
		tostring(e.name)
	)
	local r = retrying
	if r then
		stopRetry()
		if isExecutingDeferredSave and r.tries > 0 then
			logMsg("[mwsaveguard] The save went through on try %d.", r.tries)
			pcall(tes3.messageBox, "mwsaveguard: saved.")
		end
	end
end
event.register("saved", onSaved)
event.register("loaded", function() stopRetry() end)       -- the old timers are gone with the old game

-- While a save is waiting, the options menu (Esc) stays shut: quitting or loading from it would lose that save.
local function onOptionsMenu()
	if not config.enabled or #pendingSaves == 0 or tes3.onMainMenu() then return end
	if os.clock() - pendingSince > PENDING_MAX then return end      -- never hold the menu shut for long
	timer.frame.delayOneFrame(function()
		if #pendingSaves == 0 then return end
		local menu = tes3ui.findMenu("MenuOptions")
		if menu then menu:destroy() end
		tes3ui.leaveMenuMode()
		tes3.messageBox("mwsaveguard: a delayed save is about to be written. The menu opens again in a few seconds.")
	end)
end
event.register("uiActivated", onOptionsMenu, { filter = "MenuOptions" })


----------------------------------------------------------------------------------------------------
-- 4. MOD CONFIG MENU
----------------------------------------------------------------------------------------------------

event.register(tes3.event.modConfigReady, function()
	local template = mwse.mcm.createTemplate({ name = "mwsaveguard" })
	template:saveOnClose(CONFIG_NAME, config)
	template.onClose = function()
		mwse.saveConfig(CONFIG_NAME, config)
	end

	local page = template:createSideBarPage({
		label = "Settings",
		description = "Save Guard helps prevent freezes while saving or loading.\n\n- Delays quicksaves and autosaves while a new area or character finishes loading.\n- Can remove stray copies of the player that make saves hang at 50%.\n- Can check saves before loading and stop a damaged one from opening.",
	})

	page:createOnOffButton({
		label = "Enable Save Guard",
		description = "On: delays saves during loading and enables the protection options below. Off: saves are handled normally.",
		variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
	})

	page:createSlider({
		label = "World Settling Window (seconds)",
		description = "How long a save waits after you go through a door or finish making your character. Raise it if saving right after a door still freezes. Default: 5 seconds.",
		min = 1.0,
		max = 10.0,
		step = 0.5,
		decimalPlaces = 1,
		variable = mwse.mcm.createTableVariable({ id = "settleWindow", table = config }),
	})

	page:createOnOffButton({
		label = "Auto-Purge Duplicate Player Clones",
		description = "Finds and removes stray copies of your character nearby, which can make saving freeze at 50% or crash.",
		variable = mwse.mcm.createTableVariable({ id = "cleanClones", table = config }),
	})

	page:createOnOffButton({
		label = "Validate Saves on Load",
		description = "Checks a save before it loads and stops it if it is damaged, instead of letting it crash the game.",
		variable = mwse.mcm.createTableVariable({ id = "validateOnLoad", table = config }),
	})

	page:createOnOffButton({
		label = "Also copy save notices to MWSE.log",
		description = "Every save's routine notices (requested, waiting, done) go to "
			.. "Data Files\\MWSE\\logs\\mwsaveguard.log. This copies them to MWSE.log too. Problems (a damaged "
			.. "save stopped, a failed save, a copy of your character removed) always go to MWSE.log.",
		variable = mwse.mcm.createTableVariable({ id = "copyNoticesToMWSELog", table = config }),
	})

	page:createOnOffButton({
		label = "Ask again for a save another mod held back",
		description = "Another mod can stop a save without a word (abot's WBSR does while a voice line plays). On: "
			.. "the save is asked for again every second for up to 20 seconds and you get a short note; the "
			.. "attempts are in Data Files\\MWSE\\logs\\mwsaveguard.log. Off: a held-back save is only logged.",
		variable = mwse.mcm.createTableVariable({ id = "retrySwallowedSaves", table = config }),
	})

	if wbsrBard then
		wbsrBard.detect()
		page:createOnOffButton({
			label = "Let saves through while a bard sings (WBSR)",
			description = "abot's Well Behaved Sound Replacers (WBSR) blocks saving while a voiceover plays. A tavern "
				.. "bard's songs (Bards of Bardenfell: Sound\\Vo\\Bard\\) count as voiceovers and follow one "
				.. "another, so in an inn with a bard every save was swallowed without a word. On: WBSR's save block "
				.. "is lifted for bard songs only; a real speech still blocks saving. Works whether or not the Save "
				.. "Guard above is enabled. On by default when WBSR is installed; without WBSR it does "
				.. "nothing. Can be turned on or off at the main menu; the lift itself waits until a game is loaded.\n\n" .. wbsrBard.status(),
			inGameOnly = false,
			variable = mwse.mcm.createCustom({
				inGameOnly = false,
				getter = function() return wbsrBard.wanted() end,
				setter = function(_, v)
					wbsrBard.setWanted(v)
				end,
			}),
		})
	end

	template:register()
end)

----------------------------------------------------------------------------------------------------
-- 4. The one-byte patch of Cell_static::saveReference that used to be here (jz -> jle at 0x004E19FD) is gone.
-- It made a save skip the script data of any reference whose script sits above 2 GB, and this executable is
-- large-address aware, so such addresses are valid: the patch silently dropped script variables from saves.
-- The crash it was written against came from a world object left holding item data that an inventory had
-- already taken (mwplainpaperfix).
----------------------------------------------------------------------------------------------------

mwse.log("[mwsaveguard] Initialized successfully. Core save integrity and settling delay active.")
