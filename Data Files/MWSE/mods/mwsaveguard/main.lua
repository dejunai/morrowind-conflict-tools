local validator = require("mwsaveguard.validator")

-- Compatibility aliases for existing mods
package.loaded["corruptsaveguard.validator"] = validator
package.loaded["corruptsaveguard"] = true

local CONFIG_NAME = "mwsaveguard"
local defaults = {
	enabled = true,
	settleWindow = 5.0,
	validateOnLoad = true,
	logToMWSE = true,
	cleanClones = true,
}
local config = mwse.loadConfig(CONFIG_NAME, defaults)

local function logMsg(fmt, ...)
	if config.logToMWSE then
		mwse.log(fmt, ...)
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
	if ref.objectType ~= tes3.objectType.npc then
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

	-- 2. Exact identity clone: matching player name AND identical race/head/hair/class
	local playerObj = tes3.player.object
	local refObj = ref.object
	if playerObj and refObj then
		local pName = playerObj.name
		local rName = refObj.name
		if rName and (rName == "Player" or (pName and pName ~= "" and rName == pName)) then
			if baseId and baseId:find("^player") then
				return true
			end
			if refObj.race == playerObj.race and
			   refObj.head == playerObj.head and
			   refObj.hair == playerObj.hair and
			   refObj.class == playerObj.class then
				return true
			end
		end
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
local pendingSave = nil
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
	pendingSave, deferTimer = nil, nil        -- MWSE cancelled the timer before this event
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

-- Forward declaration
local function sanitizeCellReferences()
	local ok, activeCells = pcall(tes3.getActiveCells)
	if not ok or not activeCells then return end

	for _, cell in ipairs(activeCells) do
		for ref in cell:iterateReferences() do
			if ref and ref.attachments then
				local hasScript = (ref.baseObject and ref.baseObject.script) or (ref.object and ref.object.script)
				if not hasScript then
					local pOk, vars = pcall(function() return ref.attachments.variables end)
					if pOk and vars ~= nil then
						pcall(function() ref.attachments.variables = nil end)
					end
				end
			end
		end
	end
end

local executeDeferredSave

executeDeferredSave = function()
	deferTimer = nil
	if not pendingSave then
		return
	end

	-- Do not save on main menu
	if tes3.onMainMenu() then
		pendingSave = nil
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
		pendingSave = nil
		return
	end

	-- Purge duplicate clones and sanitize cell references right before writing deferred save
	purgePlayerClones()
	sanitizeCellReferences()

	local target = pendingSave
	pendingSave = nil

	isExecutingDeferredSave = true
	logMsg("[mwsaveguard] World settled. Executing deferred save: '%s'...", tostring(target.filename or "save"))

	local saveParams = {}
	if target.filename and target.filename ~= "" then
		saveParams.file = target.filename
	end
	if target.name and target.name ~= "" then
		saveParams.name = target.name
	end

	local ok, err = pcall(tes3.saveGame, saveParams)
	isExecutingDeferredSave = false

	if not ok then
		mwse.log("[mwsaveguard] Error executing deferred save: %s", tostring(err))
	end
end

--- @param e saveEventData
local function onSave(e)
	if not config.enabled then
		return
	end

	-- Always purge duplicate player clones and sanitize references before save proceeds or gets queued
	purgePlayerClones()
	sanitizeCellReferences()

	-- If our own deferred execution triggered this, allow it straight through
	if isExecutingDeferredSave then
		return
	end

	local dh = tes3.dataHandler
	local ndd = dh and dh.nonDynamicData
	local isVolatileTransition = ndd and ndd.isSavingOrLoading

	local window = tonumber(config.settleWindow) or 5.0
	local now = os.clock()
	local cellElapsed = now - lastCellChangeTime
	local charGenElapsed = now - lastCharGenFinishTime

	-- Calculate the minimum elapsed time across all settling triggers
	local minElapsed = math.min(cellElapsed, charGenElapsed)

	if minElapsed < window or isVolatileTransition then
		-- Suppress immediate save during volatile transitions / load screens to prevent corruption/crash
		e.block = true
		e.claim = true

		local remaining = math.max(0.5, window - minElapsed)
		pendingSave = {
			filename = e.filename,
			name = e.name,
		}
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
end

-- Priority 10000 ensures this intercepts before any other save handlers (like SSS or native)
event.register("save", onSave, { priority = 10000 })

-- While a save is waiting, the options menu (Esc) stays shut: quitting or loading from it would lose that save.
local function onOptionsMenu()
	if not config.enabled or not pendingSave or tes3.onMainMenu() then return end
	if os.clock() - pendingSince > PENDING_MAX then return end      -- never hold the menu shut for long
	timer.frame.delayOneFrame(function()
		if not pendingSave then return end
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
		description = "mwsaveguard is a core protection tool for Morrowind saves:\n\n1. Settling Window: Defers autosaves or quicksaves following cell transitions and chargen completion until actors, inventories, and custom Lua data stabilize, eliminating save-time freeze and crash bugs.\n\n2. Player Clone Purge: Detects and deletes duplicate player clone actors left in active cells from fresh starts or transitions, preventing the 50% save freeze and CTD.\n\n3. Load Integrity: Pre-scans save files to intercept and quarantine truncated or corrupted files before the engine attempts to load them.",
	})

	page:createOnOffButton({
		label = "Enable Save Guard",
		description = "Enables or disables mwsaveguard protection.",
		variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
	})

	page:createSlider({
		label = "World Settling Window (seconds)",
		description = "How long mwsaveguard will defer saves following cell change or chargen completion while the scene stabilizes (default: 5.0 seconds).",
		min = 1.0,
		max = 10.0,
		step = 0.5,
		decimalPlaces = 1,
		variable = mwse.mcm.createTableVariable({ id = "settleWindow", table = config }),
	})

	page:createOnOffButton({
		label = "Auto-Purge Duplicate Player Clones",
		description = "Detects and purges duplicate player clone actors across active cells, preventing the 50% save freeze and crash bug.",
		variable = mwse.mcm.createTableVariable({ id = "cleanClones", table = config }),
	})

	page:createOnOffButton({
		label = "Validate Saves on Load",
		description = "Validates save files on load to catch corrupted saves before they crash Morrowind.",
		variable = mwse.mcm.createTableVariable({ id = "validateOnLoad", table = config }),
	})

	page:createOnOffButton({
		label = "Log Notices to MWSE.log",
		description = "Outputs notices to MWSE.log when a save is deferred or an issue is caught.",
		variable = mwse.mcm.createTableVariable({ id = "logToMWSE", table = config }),
	})

	template:register()
end)

mwse.log("[mwsaveguard] Initialized successfully. Core save integrity and settling delay guard active.")
