--[[
    mwfloatfix - settle floating loose items

    When a cell loads, every loose item in it (misc items, books, ingredients, potions, weapons, armor,
    clothing, tools...) is checked once: rays are cast straight down from under the item, at its middle
    and towards its four bottom corners. If none of them meets something within a few units, the item
    isn't resting on anything, so it is lowered onto the highest surface below it.

    Only items a plugin placed are checked: anything a script spawned or that was made in game is left alone.
    Left alone: items with nothing below them within reach (no floor found), items under water, items
    up against a wall (mounted weapons, shields) or hanging from something just above, lights (unless turned on in the menu),
    and anything already checked once (each item is checked the first time its cell loads).
    Moves are written to MWSE\logs\mwfloatfix.log.

    Only the items MWSE\config\mwfloatfix_data.json lists are checked (written by mwdialog_check --fix and
    --cell-conflicts): those resting on something a later mod moved, rescaled or deleted, or on land a later mod
    lowered. Work happens only in a cell a list names, as you enter it; once every listed item found there is
    handled the cell is marked done in the save and never checked again in that playthrough. Without the list (or
    with one made before a patch was rebuilt) no item is checked: one line in MWSE.log says so.

    With MWSE\config\mwfloatfix_rescue.json (written by mwdialog_check --fix) each person it lists who is
    under water near that spot in this save is put back on their footing, once per save: a save keeps where
    people are, so the patch's fix alone only helps a new game.

    Blacklist: look at an object (or click it with the console open) and press the blacklist key
    (Shift+Delete by default). After you confirm, that one object, in that spot, is hidden now and in
    every game from then on: for lanterns and ropes left hanging in the air where another mod took away
    the posts they hung from. The list is MWSE\config\mwfloatfix_blacklist.json; the Mod Config menu
    shows it and can bring the last one back.
]]

local CONFIG_NAME = "mwfloatfix"
local defaults = {
    enabled      = false,
    tolerance    = 4,       -- a gap up to this many units still counts as resting on something
    maxDrop      = 160,     -- never lower an item further than this (a gap larger than this is left alone)
    wallGap      = 6,       -- an item this close to a wall counts as mounted on it
    lights       = false,   -- carryable lights too (lanterns often hang on purpose)
    log          = true,
    blacklistKey = { keyCode = tes3.scanCode.delete, isShiftDown = true, isAltDown = false, isControlDown = false },
    blacklist    = {},
    whitelist    = {},
}
local config = mwse.loadConfig(CONFIG_NAME, defaults)
config.blacklist = config.blacklist or {}
config.whitelist = config.whitelist or {}
config.perFrame = nil          -- old setting (12 a frame); replaced by the fixed limits below

-- one item can cost up to ~44 ray casts: at most 2 items a frame, and stop once a frame has spent 2 ms
local MAX_PER_FRAME = 2
local FRAME_BUDGET = 0.002

local ITEM_TYPES = {
    [tes3.objectType.miscItem] = true, [tes3.objectType.book] = true, [tes3.objectType.ingredient] = true,
    [tes3.objectType.alchemy] = true, [tes3.objectType.weapon] = true, [tes3.objectType.ammunition] = true,
    [tes3.objectType.armor] = true, [tes3.objectType.clothing] = true, [tes3.objectType.apparatus] = true,
    [tes3.objectType.lockpick] = true, [tes3.objectType.probe] = true, [tes3.objectType.repairItem] = true,
}
local ITEM_TYPE_LIST = { tes3.objectType.light }     -- for iterateReferences: what this mod can move
for t in pairs(ITEM_TYPES) do ITEM_TYPE_LIST[#ITEM_TYPE_LIST + 1] = t end
local ACTOR_TYPES = {
    [tes3.objectType.npc] = true, [tes3.objectType.creature] = true,
}

local checkedThisSession = setmetatable({}, { __mode = "k" })
local configDirty = false                -- the whitelist grew since the config was last written

-- reviewed: marks live in ref.tempData (this session only), never in ref.data. For an item, ref.data is
-- the item's own itemData: a mark there went into the save for every loose item ever loaded, and an item
-- carrying data no longer stacks with its plain twins once picked up. An item that was lowered rests on
-- the floor afterwards, so checking it again next session costs a few rays and changes nothing.
local function readTemp(r, k) return r.tempData[k] end
local function writeTemp(r, k, v) r.tempData[k] = v end

local function getRefData(ref, key)
    if not ref then return nil end
    local ok, v = pcall(readTemp, ref, key)
    return ok and v or nil
end

local function setRefData(ref, key, val)
    if not ref then return false end
    return (pcall(writeTemp, ref, key, val))
end

local queue, queued, qHead = {}, {}, 1    -- reviewed: a read index instead of table.remove(queue, 1)
local sorted = false
local settleAt = 0                       -- don't start until the cell has finished loading
local DOWN = tes3vector3.new(0, 0, -1)
local UP = tes3vector3.new(0, 0, 1)
local START_ABOVE = 6                    -- rays start this far above the item's bottom (inside the item)

local LOG_DIR = "Data Files\\MWSE\\logs"
local LOG_PATH = LOG_DIR .. "\\mwfloatfix.log"
local logFile
local function openLog()
    if logFile or not config.log then return end
    pcall(function() lfs.mkdir(LOG_DIR) end)
    logFile = io.open(LOG_PATH, "w")
    if logFile then logFile:write(os.date("mwfloatfix log, started %Y-%m-%d %H:%M:%S"), "\n") end
end
local function log(fmt, ...)
    if not config.log or not logFile then return end
    local ok, line = pcall(string.format, fmt, ...)
    logFile:write(os.date("[%H:%M:%S] "), ok and line or tostring(fmt), "\n")
    logFile:flush()
end

local function atPos(ref)
    local p = ref and (ref.startingPosition or ref.position)
    if not p then return "" end
    return string.format(" (at %.0f, %.0f, %.0f)", p.x, p.y, p.z)
end

local function checkRefValid(r)
    return not r.disabled and not r.deleted and r.sceneNode ~= nil and r.position ~= nil
end

-- isValid() says whether the reference still exists, without the cost of a pcall on every check
local function isRefValid(ref)
    if not ref then return false end
    if ref.isValid then
        if not ref:isValid() then return false end
        return checkRefValid(ref)
    end
    local ok, valid = pcall(checkRefValid, ref)
    return ok and valid
end

local function getRefObject(r) return r.object end
local function getSourceMod(r) return r.sourceMod end

local function isCandidate(ref)
    if not isRefValid(ref) then return false end
    if checkedThisSession[ref] then return false end
    -- only what a plugin placed: a script's spawns (birds, dropped loot) and anything made in game have no sourceMod
    local okSrc, src = pcall(getSourceMod, ref)
    if not okSrc or not src then return false end
    local ok, obj = pcall(getRefObject, ref)
    if not ok or not obj then return false end

    local id = obj.id:lower()
    if config.blacklist and config.blacklist[id] then
        pcall(function()
            if ref.startingPosition and ref.position.z < (ref.startingPosition.z - 0.5) then
                ref.position = tes3vector3.new(ref.startingPosition.x, ref.startingPosition.y, ref.startingPosition.z)
                log("restored blacklisted %s to starting position in %s%s", ref.object.id, ref.cell and ref.cell.editorName or "?", atPos(ref))
            end
        end)
        checkedThisSession[ref] = true
        return false
    end

    local t = obj.objectType
    if t == tes3.objectType.light then
        if not (config.lights and obj.canCarry) then return false end
    elseif not ITEM_TYPES[t] then
        return false
    end
    if getRefData(ref, "mwfloatfixChecked") then return false end
    return true
end

-- the item's eight bounding box corners in the world
local function worldCorners(ref)
    local node = ref.sceneNode
    if not node then return nil end
    local bb = (node.createBoundingBox and node:createBoundingBox()) or (ref.object and ref.object.boundingBox)
    if not bb or not bb.min or not bb.max then return nil end
    local t = node.worldTransform
    if not t or not t.rotation or not t.scale or not t.translation then return nil end
    local lo, hi = bb.min, bb.max
    local out = {}
    for _, x in ipairs({ lo.x, hi.x }) do
        for _, y in ipairs({ lo.y, hi.y }) do
            for _, z in ipairs({ lo.z, hi.z }) do
                out[#out + 1] = t.rotation * tes3vector3.new(x, y, z) * t.scale + t.translation
            end
        end
    end
    return out
end

local function bottomOf(corners)
    local z = math.huge
    for _, c in ipairs(corners) do if c.z < z then z = c.z end end
    return z
end

local function isActor(hitRef)
    return hitRef and hitRef.object and ACTOR_TYPES[hitRef.object.objectType]
end

-- every ray reuses one parameter table and one ignore list (no new tables per ray). A ray is first cast at
-- the statics only (tes3.game.worldObjectRoot: far fewer nodes than the whole world, no skinned actors); only
-- when that can't settle the question is it cast at the whole world as before, so the answers are unchanged:
-- a static found is always "something is there", which is all the rooted ray is ever used to conclude.
local rayParams = { ignore = {} }
local function castRay(ref, pos, dir, maxDistance, root)
    rayParams.position, rayParams.direction, rayParams.maxDistance, rayParams.root = pos, dir, maxDistance, root
    rayParams.ignore[1] = ref
    local hit = tes3.rayTest(rayParams)
    rayParams.ignore[1], rayParams.position, rayParams.root = nil, nil, nil     -- hold no reference or node
    return hit
end
local function staticsRoot()
    return tes3.game and tes3.game.worldObjectRoot or nil
end

-- a non-actor surface along the ray, or nil: the statics first, then the whole world
local function solidHit(ref, pos, dir, maxDistance)
    local root = staticsRoot()
    if root then
        local hit = castRay(ref, pos, dir, maxDistance, root)
        if hit then return hit end
    end
    local hit = castRay(ref, pos, dir, maxDistance, nil)
    if hit and not isActor(hit.reference) then return hit end
    return nil
end

-- distance from the item's bottom down to the first surface under (x, y), or nil if none within reach
local function gapBelow(ref, x, y, bottom)
    local pos = tes3vector3.new(x, y, bottom + START_ABOVE)
    local reach = config.maxDrop + START_ABOVE + config.tolerance
    local root = staticsRoot()
    if root then                                  -- resting on a static: the usual answer, from the cheap ray
        local hit = castRay(ref, pos, DOWN, reach, root)
        if hit and hit.distance - START_ABOVE <= config.tolerance then return hit.distance - START_ABOVE end
    end
    local hit = castRay(ref, pos, DOWN, reach, nil)
    if not hit or isActor(hit.reference) then return nil end
    return hit.distance - START_ABOVE
end

-- up against a wall or mounted on a wall bracket:
-- Casts horizontal rays at multiple heights in 8 radial compass directions
local function againstWall(ref, corners, centre, bottom, top)
    local wallReach = math.max(config.wallGap, 22) -- Sconces/brackets extend 12-20 units from wall

    -- Maximum horizontal radial reach of the object
    local maxReach = 0
    for _, c in ipairs(corners) do
        local d = math.sqrt((c.x - centre.x)^2 + (c.y - centre.y)^2)
        if d > maxReach then maxReach = d end
    end

    -- Test at multiple heights: midsection, collar (near top), and lower (above bottom)
    local testHeights = { centre.z }
    if (top - bottom) > 8 then
        table.insert(testHeights, top - 4)
        table.insert(testHeights, bottom + 6)
    end

    for _, z in ipairs(testHeights) do
        -- 8 radial compass directions (0, 45, 90, 135, 180, 225, 270, 315 degrees)
        for i = 0, 7 do
            local rad = i * (math.pi / 4)
            local dir = tes3vector3.new(math.cos(rad), math.sin(rad), 0)
            local pos = tes3vector3.new(centre.x, centre.y, z)

            if solidHit(ref, pos, dir, maxReach + wallReach) then
                return true
            end
        end
    end

    return false
end

-- Checks if an item is supported by or resting inside a wall sconce, bracket, ring, or hook
local function supportedByMount(ref, corners, centre, bottom, top)
    local height = top - bottom
    if height < 2 then return false end

    -- 1. Mid-body and upper-collar downward raycasts:
    -- When a torch, lantern, or item rests inside a wall sconce, cup, or ring,
    -- the bracket holds it at its neck or midsection, while the handle extends below.
    -- Casting down from collar height (top - height * 0.25) or mid-body (centre.z)
    -- will hit the sconce ring or bracket at a height well above the bottom.
    local testHeights = { centre.z }
    if height > 10 then
        table.insert(testHeights, top - math.min(8, height * 0.25))
    end

    local radius = 0
    for _, c in ipairs(corners) do
        local d = math.sqrt((c.x - centre.x)^2 + (c.y - centre.y)^2)
        if d > radius then radius = d end
    end
    radius = math.max(3, radius * 0.8)

    for _, zStart in ipairs(testHeights) do
        -- Check center and 4 surrounding points around the item's perimeter
        local checkPoints = { { centre.x, centre.y } }
        for a = 0, 3 do
            local rad = a * (math.pi / 2)
            checkPoints[#checkPoints + 1] = {
                centre.x + math.cos(rad) * radius,
                centre.y + math.sin(rad) * radius
            }
        end

        for _, pt in ipairs(checkPoints) do
            local pos, reach = tes3vector3.new(pt[1], pt[2], zStart), (zStart - bottom) + 2
            local root = staticsRoot()
            local hit = root and castRay(ref, pos, DOWN, reach, root)
            if not (hit and zStart - hit.distance > bottom + config.tolerance) then   -- else: the whole world
                hit = castRay(ref, pos, DOWN, reach, nil)
            end
            if hit and not isActor(hit.reference) then
                local hitZ = zStart - hit.distance
                -- If it hits a static surface inside the bracket/sconce higher than the bottom, it is supported!
                if hitZ > (bottom + config.tolerance) then
                    return true
                end
            end
        end
    end

    -- 2. Hanging hook/mount check above top:
    local upReach = (top - centre.z) + math.max(config.wallGap, 20)
    if solidHit(ref, centre, UP, upReach) then
        return true
    end

    return false
end

local function underWater(ref, bottom)
    local cell = ref.cell
    if not cell then return false end
    if cell.isInterior then
        return cell.hasWater and cell.waterLevel and bottom < cell.waterLevel
    end
    return bottom < (cell.waterLevel or 0)
end

-- marks the original version left in item data: removed when the item is next seen, so its item data
-- can become empty again (only read through ref.itemData, which is nil for plain items: nothing created)
local function clearOldMarks(ref)
    pcall(function()
        local idata = ref.itemData
        local d = idata and idata.data
        if d and (d.mwfloatfixChecked ~= nil or d.mwfloatfixOrigZ ~= nil or d.mwfloatfixHidden ~= nil) then
            d.mwfloatfixChecked, d.mwfloatfixOrigZ, d.mwfloatfixHidden = nil, nil, nil
        end
    end)
end

-- an item is marked checked only once the rays have given an answer: one whose model or cell wasn't ready
-- (no bounding box, a ray test that failed) is tried again a little later, a few times
local SKIP_LOG_MAX, RETRIES = 200, 3
local skipLines = 0
local retries = setmetatable({}, { __mode = "k" })
local requeue                            -- set with the queue below

local function logSkip(ref, why)
    if skipLines >= SKIP_LOG_MAX then return end
    skipLines = skipLines + 1
    pcall(function()
        log("left %s in %s: %s%s", ref.object.id, ref.cell and ref.cell.editorName or "?", why, atPos(ref))
    end)
    if skipLines == SKIP_LOG_MAX then log("(no more skip lines this session)") end
end

local function markChecked(ref)
    checkedThisSession[ref] = true
    setRefData(ref, "mwfloatfixChecked", true)
end

local function tryLater(ref, why)
    local n = (retries[ref] or 0) + 1
    retries[ref] = n
    if n <= RETRIES and requeue then
        requeue(ref)
    else
        markChecked(ref)
        logSkip(ref, why .. " (gave up after " .. RETRIES .. " tries)")
    end
end

local function settle(ref)
    if not isCandidate(ref) then return end
    clearOldMarks(ref)
    local corners = worldCorners(ref)
    if not corners then return tryLater(ref, "no bounding box yet") end
    local bottom = bottomOf(corners)
    if underWater(ref, bottom) then
        markChecked(ref)
        return logSkip(ref, "under water")
    end
    local cx, cy, cz = 0, 0, 0
    for _, c in ipairs(corners) do cx, cy, cz = cx + c.x, cy + c.y, cz + c.z end
    cx, cy, cz = cx / 8, cy / 8, cz / 8
    -- middle, and 70% of the way to each bottom corner (the corners themselves overhang edges)
    local samples = { { cx, cy } }
    for _, c in ipairs(corners) do
        if c.z < bottom + 1 then
            samples[#samples + 1] = { cx + (c.x - cx) * 0.7, cy + (c.y - cy) * 0.7 }
        end
    end
    local nearest, answered = nil, 0
    for _, s in ipairs(samples) do
        local ok, g = pcall(gapBelow, ref, s[1], s[2], bottom)
        if ok then
            answered = answered + 1
            if g then
                if g <= config.tolerance then return markChecked(ref) end      -- resting on something
                if not nearest or g < nearest then nearest = g end
            end
        end
    end
    if answered == 0 then return tryLater(ref, "the ray test failed") end
    markChecked(ref)
    if not nearest then return logSkip(ref, "no floor found within reach") end
    if nearest > config.maxDrop then
        return logSkip(ref, string.format("the floor is %.0f units down, more than %d", nearest, config.maxDrop))
    end
    local centre = tes3vector3.new(cx, cy, cz)
    local top = -math.huge
    for _, c in ipairs(corners) do if c.z > top then top = c.z end end

    if againstWall(ref, corners, centre, bottom, top) then return logSkip(ref, "up against a wall (mounted)") end
    if supportedByMount(ref, corners, centre, bottom, top) then return logSkip(ref, "hanging from something above") end
    local drop = nearest - 0.5                               -- leave half a unit, no sinking in
    ref.position = tes3vector3.new(ref.position.x, ref.position.y, ref.position.z - drop)  -- sets modified
    local id = ref.object.id:lower()
    if not config.whitelist[id] then
        config.whitelist[id] = true
        configDirty = true                       -- written at the next save, only when something was added
    end
    log("lowered %s by %.0f units in %s (at %.0f, %.0f, %.0f)", ref.object.id, drop,
        ref.cell and ref.cell.editorName or "?", ref.position.x, ref.position.y, ref.position.z)
end


-- blacklist -------------------------------------------------------------------------
-- One entry per object in one spot: the cell, the object id, and where its plugin puts it. So the
-- same entry matches in every new game, and a rope blacklisted on one pier leaves every other rope be.
local BLACKLIST_NAME = "mwfloatfix_blacklist"
local blacklist = mwse.loadConfig(BLACKLIST_NAME, { entries = {} })
blacklist.entries = blacklist.entries or {}
local blackKeys = {}
local function cellKey(cell)
    if not cell then return "?" end
    if cell.isInterior then return cell.id:lower() end
    return string.format("%s (%d, %d)", (cell.name or ""):lower(), cell.gridX, cell.gridY)
end
-- reviewed: where its plugin put it (startingPosition: unchanged by this mod lowering it, or by anything
-- else moving it), so no saved "original z" is needed. Same key as before for anything not yet moved.
local blackIds = {}                      -- object id -> true: most references are skipped without a key
local function resolveBaseId(ref)
    if not ref or not ref.object then return nil end
    local id = ref.object.id:lower()
    if tes3.player and tes3.player.data and tes3.player.data.leavethelightsoff then
        local rev = tes3.player.data.leavethelightsoff.reverse
        if rev and rev[id] then
            return rev[id]:lower()
        end
    end
    return id
end

local function refKey(ref)
    local p = ref.startingPosition or ref.position
    local baseId = resolveBaseId(ref) or ref.object.id:lower()
    return string.format("%s|%s|%d|%d|%d", cellKey(ref.cell), baseId,
                         math.floor(p.x + 0.5), math.floor(p.y + 0.5), math.floor(p.z + 0.5))
end
local blackCells = {}                    -- cellKey -> true: a cell with a blacklisted object in it
local function rebuildKeys()
    blackKeys, blackIds, blackCells = {}, {}, {}
    for _, e in ipairs(blacklist.entries) do
        blackKeys[e.key] = true
        if e.id then blackIds[e.id:lower()] = true end
        local c = type(e.key) == "string" and e.key:match("^(.-)|")
        if c then blackCells[c] = true end
    end
end
rebuildKeys()

local function applyBlacklist(ref)
    if not ref or ref.disabled or not ref.object then return false end
    local baseId = resolveBaseId(ref) or ref.object.id:lower()
    if not blackIds[baseId] and not blackIds[ref.object.id:lower()] then return false end
    if not blackKeys[refKey(ref)] then return false end
    ref:disable()
    log("hid blacklisted %s in %s%s", ref.object.id, cellKey(ref.cell), atPos(ref))
    return true
end

local consoleRef                         -- what the console last had selected
if tes3.event.consoleReferenceChanged then
    event.register(tes3.event.consoleReferenceChanged, function(e) consoleRef = e.reference end)
end

-- what the player means: the console's selection while the console is open, else what the camera is
-- looking at (statics included, so ropes can be picked), up to 3000 units away
local function pickTarget()
    local console = tes3ui.findMenu("MenuConsole")
    if console and console.visible and consoleRef and consoleRef.cell then return consoleRef end
    -- two roots: what can be picked up (items, carryable lanterns) and the statics (ropes, fixed lights)
    local pos, dir, hit = tes3.getCameraPosition(), tes3.getCameraVector(), nil
    for _, root in ipairs({ tes3.game.worldPickRoot, tes3.game.worldObjectRoot }) do
        local h = tes3.rayTest({ position = pos, direction = dir, maxDistance = 3000, root = root,
                                 ignore = { tes3.player } })
        if h and h.reference and (not hit or h.distance < hit.distance) then hit = h end
    end
    if hit and hit.reference and hit.reference ~= tes3.player then return hit.reference end
    if consoleRef and consoleRef.cell then return consoleRef end
    return nil
end

local function describe(ref)
    local name = ref.object.name
    return (name and name ~= "") and string.format("%s (%s)", name, ref.object.id) or ref.object.id
end

local function addToBlacklist(ref)
    local baseId = resolveBaseId(ref) or ref.object.id
    local key = refKey(ref)
    -- listed already, yet showing (something switched it back on): the new entry replaces the old
    for i = #blacklist.entries, 1, -1 do
        if blacklist.entries[i].key == key then
            table.remove(blacklist.entries, i)
        end
    end
    local srcObj = tes3.getObject(baseId) or ref.object
    local srcMod = ref.sourceMod or (srcObj and srcObj.sourceMod) or "?"
    table.insert(blacklist.entries, { key = key, id = baseId, cell = cellKey(ref.cell),
                                      mod = srcMod, added = os.date("%Y-%m-%d %H:%M") })
    mwse.saveConfig(BLACKLIST_NAME, blacklist)
    rebuildKeys()
    ref:disable()
    log("blacklisted %s in %s (key %s, from %s)", baseId, cellKey(ref.cell), key, srcMod)
    tes3.messageBox("Hidden in every game from now on: %s", describe(ref))
end

local function onBlacklistKey(e)
    if not tes3.player then return end
    local k = config.blacklistKey
    if e.keyCode ~= k.keyCode or (k.isShiftDown and not e.isShiftDown) or (k.isAltDown and not e.isAltDown)
            or (k.isControlDown and not e.isControlDown) then
        return
    end
    local ref = pickTarget()
    if not ref then
        tes3.messageBox("Nothing to blacklist: look at the object, or click it with the console open.")
        return
    end
    if ref.object.objectType == tes3.objectType.npc or ref.object.objectType == tes3.objectType.creature then
        tes3.messageBox("%s is a character; the blacklist is for things like lanterns and ropes.", describe(ref))
        return
    end
    tes3.messageBox({
        message = string.format("Hide %s here in every game from now on?\n(%s)", describe(ref), cellKey(ref.cell)),
        buttons = { "Hide it", "Cancel" },
        callback = function(b) if b.button == 0 then addToBlacklist(ref) end end,
    })
end
event.register(tes3.event.keyDown, onBlacklistKey)

local function undoLast()
    local e = table.remove(blacklist.entries)
    if not e then return nil end
    mwse.saveConfig(BLACKLIST_NAME, blacklist)
    rebuildKeys()
    for _, cell in ipairs(tes3.player and tes3.getActiveCells() or {}) do   -- bring it back if it's around
        for ref in cell:iterateReferences() do
            if ref.disabled and ref.object and refKey(ref) == e.key then
                ref:enable()
            end
        end
    end
    log("removed from the blacklist: %s", e.key)
    return e
end

-- FNV-1a (32 bit) of a file, as eight hex digits; nil when it can't be read. The same sum mwdialog_check writes.
local function fnv1aFile(path)
    local okBit, bit = pcall(require, "bit")
    if not okBit then return nil end
    local f = io.open(path, "rb")
    if not f then return nil end
    local bxor, lshift, byte = bit.bxor, bit.lshift, string.byte
    local h = 2166136261
    while true do
        local chunk = f:read(65536)
        if not chunk then break end
        for i = 1, #chunk do
            h = bxor(h, byte(chunk, i)) % 4294967296
            h = (lshift(h, 24) % 4294967296 + h * 403) % 4294967296      -- h * 16777619, mod 2^32, exactly
        end
    end
    f:close()
    return string.format("%08x", h)
end

-- MWSE\config\mwfloatfix_data.json (mwdialog_check --cell-conflicts): the loose items that could float, by
-- cell. When it is there only those are checked, and every other cell costs one table lookup.
local floatList                          -- cell key -> object id -> { {x, y, z}, ... }; nil: nothing is checked
do
    local data = mwse.loadConfig("mwfloatfix_data")
    -- the list was worked out against the generated patches (Cell Fixes first: it has the last word on what is
    -- where and what is gone). If one was rebuilt or removed since, the list may miss what floats now: check
    -- every loose item instead, as without the file, until mwdialog_check --fix writes it again.
    -- Not by file time: mwdialog_check sets its plugins' dates to fix the load order, so a date never says
    -- when a patch was built. Each source's size, and for Cell Fixes a content hash (FNV-1a), say whether it
    -- is the very file the list was made from.
    local stale, why
    if data and type(data.sources) == "table" then
        local root = (type(tes3.installDirectory) == "string" and tes3.installDirectory ~= "")
            and (tes3.installDirectory .. "\\Data Files\\") or "Data Files\\"
        for name, s in pairs(data.sources) do
            if type(s) == "table" then
                local path = root .. name
                local a = lfs.attributes(path)
                if not a then
                    stale, why = name, "is gone"
                elseif a.size ~= s.size then
                    stale, why = name, "was rebuilt (its size changed)"
                elseif type(s.fnv1a) == "string" and fnv1aFile(path) ~= s.fnv1a:lower() then
                    stale, why = name, "was rebuilt (its contents changed)"
                elseif s.fnv1a == nil and string.lower(name) == "mwdialog_check cell fixes.esp" then
                    stale, why = name, "has no content stamp in the list (an older mwdialog_check wrote it)"
                end
                if stale then break end
            end
        end
    end
    if stale then
        mwse.log("[mwfloatfix] mwfloatfix_data.json doesn't match %s, which %s: no items are checked until "
            .. "mwdialog_check --fix (or --cell-conflicts) writes it again", stale, why)
        data = nil
    elseif not data then
        mwse.log("[mwfloatfix] MWSE\\config\\mwfloatfix_data.json is missing: no items are checked "
            .. "(mwdialog_check --fix, or --cell-conflicts, writes it)")
    end
    if data and type(data.cells) == "table" then
        floatList = {}
        for cellId, entries in pairs(data.cells) do
            local set = {}
            for _, e in ipairs(entries) do
                if type(e.id) == "string" and type(e.pos) == "table" and #e.pos >= 3 then
                    local id = e.id:lower()
                    set[id] = set[id] or {}
                    table.insert(set[id], e.pos)
                end
            end
            floatList[cellId:lower()] = set
        end
    end
end

local function listKey(cell)
    if cell.isInterior then return cell.id:lower() end
    return string.format("#%d,%d", cell.gridX, cell.gridY)
end

local lastCell, lastSet
local function isListed(ref)
    local cell = ref.cell
    if not cell then return false end
    if cell ~= lastCell then lastCell, lastSet = cell, floatList[listKey(cell)] end
    local spots = lastSet and ref.object and lastSet[ref.object.id:lower()]
    if not spots then return false end
    local p = ref.startingPosition or ref.position
    for _, s in ipairs(spots) do
        if math.abs(p.x - s[1]) <= 4 and math.abs(p.y - s[2]) <= 4 and math.abs(p.z - s[3]) <= 4 then return true end
    end
    return false
end

-- MWSE\config\mwfloatfix_rescue.json (mwdialog_check --fix): people saves keep under water, and where they
-- stand. startingPosition can't be used to know them (it is invalid for actors), so: object id and near the spot.
local RESCUE_KEY, RESCUE_NEAR, RESCUE_BELOW = "mwfloatfixRescued", 512, -32
local rescues = {}                       -- base object id -> { { from, to, key }, ... }
local drowning = {}
do
    local data = mwse.loadConfig("mwfloatfix_rescue")
    if data and type(data.npcs) == "table" then
        for _, e in ipairs(data.npcs) do
            if type(e.id) == "string" and type(e.from) == "table" and #e.from >= 3
                    and type(e.to) == "table" and #e.to >= 3 then
                local id = e.id:lower()
                rescues[id] = rescues[id] or {}
                table.insert(rescues[id], { from = e.from, to = e.to, key = string.format("%s|%d|%d|%d|%d|%d|%d", id,
                    e.from[1], e.from[2], e.from[3], e.to[1], e.to[2], e.to[3]) })
            end
        end
    end
end

local rescueCells = {}                   -- list key ("#x,y") -> true: where a listed person stands or is put
for _, list in pairs(rescues) do
    for _, e in ipairs(list) do
        for _, at in ipairs({ e.from, e.to }) do
            rescueCells[string.format("#%d,%d", math.floor(at[1] / 8192), math.floor(at[2] / 8192))] = true
        end
    end
end

local function noteRescue(ref)
    if not config.enabled or next(rescues) == nil then return end
    local obj = ref.object
    if not obj or obj.objectType ~= tes3.objectType.npc then return end
    local base = ref.baseObject
    if not base or not rescues[base.id:lower()] then return end
    drowning[#drowning + 1] = tes3.makeSafeObjectHandle(ref)
    settleAt = os.clock() + 1.0                     -- wait until the cell around them has loaded
end

local function rescue(ref)
    local cell = ref.cell
    if not cell or cell.isInterior or ref.isDead == true then return end
    local p = ref.position
    if p.z >= RESCUE_BELOW then return end
    local saved = tes3.player.data
    local done = saved[RESCUE_KEY] or {}
    local best, nearest = nil, RESCUE_NEAR
    for _, e in ipairs(rescues[ref.baseObject.id:lower()]) do
        if not done[e.key] then
            local d = math.min(math.sqrt((p.x - e.from[1]) ^ 2 + (p.y - e.from[2]) ^ 2),
                               math.sqrt((p.x - e.to[1]) ^ 2 + (p.y - e.to[2]) ^ 2))
            if d <= nearest then best, nearest = e, d end
        end
    end
    if not best then return end
    local was, o = p.z, ref.orientation
    if not tes3.positionCell({ reference = ref, position = { best.to[1], best.to[2], best.to[3] },
                               orientation = { o.x, o.y, o.z } }) then return end
    done[best.key] = true
    saved[RESCUE_KEY] = done
    log("rescued %s in %s from under water (%.0f) to %.0f, %.0f, %.0f", ref.baseObject.id,
        ref.cell and ref.cell.editorName or "?", was, best.to[1], best.to[2], best.to[3])
end

local function runRescues()
    local list = drowning
    drowning = {}
    for _, handle in ipairs(list) do
        if handle:valid() then
            local ok, err = pcall(rescue, handle:getObject())
            if not ok then log("error rescuing: %s", tostring(err)) end
        end
    end
end

-- known cells ------------------------------------------------------------------------------------
-- Work happens only in a cell a list names, as it becomes active: an item-list cell not yet done in this
-- playthrough, a blacklisted object's cell, a listed person's cell. Once every listed item found in a cell has
-- been handled, the cell is marked done in the save and never looked at again in that playthrough.
local DONE_KEY = "mwfloatfixDone"                   -- tes3.player.data: list key -> true
local pending = {}                                  -- list key -> { [ref] = true }: its items still queued
local cellOf = setmetatable({}, { __mode = "k" })   -- queued item -> its list key

local function doneCells()
    local d = tes3.player and tes3.player.data
    if not d then return nil end
    d[DONE_KEY] = d[DONE_KEY] or {}
    return d[DONE_KEY]
end

local function enqueue(ref, key)
    if not config.enabled or queued[ref] or not key then return end
    local ok, listed = pcall(isListed, ref)
    if not ok or not listed then return end
    if not isCandidate(ref) then return end
    queued[ref] = true
    cellOf[ref] = key
    if pending[key] then pending[key][ref] = true end
    queue[#queue + 1] = ref
    sorted = false
    settleAt = os.clock() + 1.0                     -- wait until the cell around it has loaded
end
requeue = function(ref) enqueue(ref, cellOf[ref]) end   -- a retry of an item whose model wasn't ready

local function markDone(key)
    pending[key] = nil
    local done = doneCells()
    if done then done[key] = true end
    log("%s: every listed item handled; not checked again in this game", key)
end

-- an item is through (not queued again for a retry): its cell is done once none of its items is left
local function finished(ref)
    if queued[ref] then return end
    local key = cellOf[ref]
    local set = key and pending[key]
    if not set then return end
    set[ref] = nil
    if next(set) == nil then markDone(key) end
end

-- an item gone from the queue unchecked (its cell unloaded): that cell is not done, its next visit starts over
local function left(ref)
    local key = cellOf[ref]
    if key then pending[key] = nil end
end

local syncSimulate
local keep = {}                                     -- reused while the queue is sorted (no new tables per frame)
local function zOf(ref) local p = ref.position return (p and p.z) or 0 end
local function lowerFirst(a, b) return zOf(a) < zOf(b) end
local function clear(t) for i = #t, 1, -1 do t[i] = nil end end
local function onSimulate()
    if drowning[1] and tes3.player and os.clock() >= settleAt then runRescues() end
    if qHead > #queue or os.clock() < settleAt then return end
    -- lowest items first, so a book resting on a fallen book lands on it, not through it
    if not sorted then
        local n = 0
        for i = qHead, #queue do
            local ref = queue[i]
            if ref and isRefValid(ref) and isCandidate(ref) then
                n = n + 1
                keep[n] = ref
            elseif ref then
                queued[ref] = nil               -- gone (its cell unloaded): queued again when it comes back
                left(ref)
            end
        end
        clear(queue)
        for i = 1, n do queue[i], keep[i] = keep[i], nil end
        table.sort(queue, lowerFirst)
        qHead, sorted = 1, true
    end
    local started = os.clock()
    for _ = 1, MAX_PER_FRAME do
        local ref = queue[qHead]
        if not ref or os.clock() - started >= FRAME_BUDGET then break end
        queue[qHead] = false
        qHead = qHead + 1
        queued[ref] = nil
        if isRefValid(ref) then
            local ok, err = pcall(settle, ref)
            if not ok then log("error checking %s%s: %s", tostring(ref.object and ref.object.id), atPos(ref), tostring(err)) end
            finished(ref)
        else
            left(ref)
        end
    end
    if qHead > #queue then
        clear(queue)
        qHead, sorted = 1, false
        if not drowning[1] then timer.delayOneFrame(function() syncSimulate() end) end   -- not during the dispatch
    end
end

-- simulate is registered only while there is something to do (an item queued, a person to rescue)
syncSimulate = function()
    local want = qHead <= #queue or drowning[1] ~= nil
    local has = event.isRegistered(tes3.event.simulate, onSimulate)
    if want and not has then
        event.register(tes3.event.simulate, onSimulate)
    elseif not want and has then
        event.unregister(tes3.event.simulate, onSimulate)
    end
end

local function scanActiveCells()
    if not tes3.player then return end
    local done = doneCells() or {}
    for _, cell in ipairs(tes3.getActiveCells()) do
        local key = listKey(cell)
        if blackCells[cellKey(cell)] then
            for ref in cell:iterateReferences() do applyBlacklist(ref) end
        end
        if config.enabled and rescueCells[key] then
            for ref in cell:iterateReferences(tes3.objectType.npc) do noteRescue(ref) end
        end
        if config.enabled and floatList and floatList[key] and not done[key] and not pending[key] then
            pending[key] = {}
            for ref in cell:iterateReferences(ITEM_TYPE_LIST) do
                if not ref.disabled then enqueue(ref, key) end
            end
            if next(pending[key]) == nil then markDone(key) end
        end
    end
    syncSimulate()
end

-- without any list there is nothing to do in any cell: no handler stays loaded for it
local anyList = floatList ~= nil or next(rescues) ~= nil or next(blacklist.entries) ~= nil
if anyList then
    -- a cell change keeps the queue: anything that has gone since is skipped as it comes up
    event.register(tes3.event.cellChanged, function()
        sorted = false
        settleAt = os.clock() + 1.0
        scanActiveCells()
    end)
    event.register(tes3.event.loaded, function()
        queue, queued, qHead, drowning, pending = {}, {}, 1, {}, {}
        checkedThisSession = setmetatable({}, { __mode = "k" })
        settleAt = os.clock() + 2.0
        openLog()
        scanActiveCells()
    end)
end

local function restoreBlacklistedInActiveCells()
    for _, cell in ipairs(tes3.getActiveCells()) do
        for ref in cell:iterateReferences(ITEM_TYPE_LIST) do
            pcall(function()
                if isRefValid(ref) and ref.object and ref.startingPosition then
                    local id = ref.object.id:lower()
                    if config.blacklist and config.blacklist[id] then
                        if ref.position.z < (ref.startingPosition.z - 0.5) then
                            ref.position = tes3vector3.new(ref.startingPosition.x, ref.startingPosition.y, ref.startingPosition.z)
                            log("restored blacklisted %s to starting position in %s%s", ref.object.id, ref.cell and ref.cell.editorName or "?", atPos(ref))
                        end
                    end
                end
            end)
        end
    end
end

local function recheckActiveCells()
    openLog()                                       -- the log may have been switched on
    restoreBlacklistedInActiveCells()
    checkedThisSession = setmetatable({}, { __mode = "k" })
    scanActiveCells()                               -- cells done in this game stay done
end

local function getMovedItems()
    local set = {}
    if config.whitelist then
        for id in pairs(config.whitelist) do
            set[id] = true
        end
    end
    if config.blacklist then
        for id, blocked in pairs(config.blacklist) do
            if blocked then
                set[id] = true
            end
        end
    end
    local list = {}
    for id in pairs(set) do
        list[#list + 1] = id
    end
    table.sort(list)
    return list
end

-- the config is written when the Mod Config menu closes, and at a save only when an item was added to the
-- whitelist since (not on every save)
event.register(tes3.event.save, function()
    if not configDirty then return end
    configDirty = false
    timer.delayOneFrame(function() mwse.saveConfig(CONFIG_NAME, config) end, timer.real)   -- not while the game saves
end)

-- Mod Config menu ---------------------------------------------------------------
event.register(tes3.event.modConfigReady, function()
    local template = mwse.mcm.createTemplate({ name = "Floating Item Fix" })
    template.onClose = function()
        configDirty = false
        mwse.saveConfig(CONFIG_NAME, config)
        recheckActiveCells()
    end
    local page = template:createSideBarPage({
        label = "Settings",
        description = "Some loose items (books, bottles, plates) end up floating a little above the table or "
            .. "floor, usually because another mod moved what they sat on. This lowers each one onto the surface "
            .. "below it, once, the first time you visit the place. Items hanging on a wall or hook, items under "
            .. "water, and items with nothing below them are left alone. Each move is written to "
            .. "MWSE\\logs\\mwfloatfix.log."
            .. "\n\nOnly the items listed in MWSE\\config\\mwfloatfix_data.json are checked (that list is made by "
            .. "mwdialog_check --fix or --cell-conflicts), and only in their cells: once a place's items are done it "
            .. "is not checked again in this game. Without the list nothing is checked."
            .. "\n\nPeople listed in MWSE\\config\\mwfloatfix_rescue.json (made by mwdialog_check --fix) who are "
            .. "stuck under water in this save are put back on their dock or ledge, once per save.",
    })
    page:createOnOffButton({ label = "Enabled", description = "Turns the fix on: floating items are lowered as each place loads, and stuck people "
            .. "are rescued. Off: nothing is moved (items already lowered stay where they are).",
        variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }) })
    page:createSlider({ label = "Still resting when the gap is up to (units)", min = 1, max = 16, step = 1,
        description = "An item this close to the surface below already counts as resting on it and is left alone. "
            .. "Raise it if items that look fine get nudged; lower it to also catch items that hover only slightly.",
        variable = mwse.mcm.createTableVariable({ id = "tolerance", table = config }) })
    page:createSlider({ label = "Lower an item by at most (units)", min = 16, max = 512, step = 8,
        description = "The farthest an item will be lowered. An item floating higher than this is left where it "
            .. "is. Raise it if items floating high above the floor aren't being fixed.",
        variable = mwse.mcm.createTableVariable({ id = "maxDrop", table = config }) })
    page:createSlider({ label = "Counts as mounted on a wall within (units)", min = 0, max = 32, step = 1,
        description = "An item this close to a wall, or with a hook just above it, counts as hanging there and is "
            .. "never lowered. Values under 22 make no difference: walls are always checked out to 22 units and "
            .. "hooks to 20. Raise it if wall-mounted things (shields, weapons, torches in sconces) still get dropped.",
        variable = mwse.mcm.createTableVariable({ id = "wallGap", table = config }) })
    if not floatList then                -- the list never names lights
        page:createOnOffButton({ label = "Also carryable lights", description = "Also lowers floating lanterns and torches that you can pick up. Off by default, because "
            .. "many lanterns are meant to hang. Only used when the MWSE\\config\\mwfloatfix_data.json list isn't "
            .. "loaded: while that list is used, this switch is hidden and lights are never checked.",
            variable = mwse.mcm.createTableVariable({ id = "lights", table = config }) })
    end
    page:createOnOffButton({ label = "Write moves to MWSE\\logs\\mwfloatfix.log",
        description = "Keeps a record of every item lowered (and why others were left alone) in the log file. "
            .. "Turn off if you don't need it.",
        variable = mwse.mcm.createTableVariable({ id = "log", table = config }) })
    page:createKeyBinder({ label = "Hide object hotkey",
        description = "Look at an object (or click it with the console open) and press this key. After you confirm, "
            .. "that one object in that spot is hidden in this game and every new game. Meant for lanterns or ropes "
            .. "left hanging in mid-air after another mod removed what held them. Bring it back on the Hidden Objects page.",
        allowCombinations = true, variable = mwse.mcm.createTableVariable({ id = "blacklistKey", table = config }) })

    template:createExclusionsPage({
        label = "Moved / Never move",
        description = "Items this mod has lowered are listed on the right.\n\n"
            .. "• Click an item on the right to put it on the Never move list: it is left alone from now on, and put back where its mod placed it if it was lowered.\n"
            .. "• Click an item on the left to allow it to be moved again.",
        leftListLabel = "Never move",
        rightListLabel = "Moved before (allowed)",
        showAllBlocked = true,
        variable = mwse.mcm.createTableVariable({
            id = "blacklist",
            table = config,
        }),
        filters = {
            {
                label = "Moved Items",
                callback = getMovedItems,
            },
        },
    })

    local bpage = template:createPage({ label = "Hidden Objects" })
    bpage:createInfo({ text = "Objects you hid with the hide key, in every game. To hide one, look at it (or click it with the "
        .. "console open) and press the hide key. The list is kept in MWSE\\config\\mwfloatfix_blacklist.json." })
    local listInfo = bpage:createInfo({ text = "" })
    local function refreshList()
        local lines = {}
        for i, e in ipairs(blacklist.entries) do
            lines[#lines + 1] = string.format("%d. %s  -  %s  (%s, added %s)", i, e.id, e.cell, e.mod or "?", e.added or "?")
        end
        listInfo.text = #lines > 0 and table.concat(lines, "\n") or "(empty)"
        if listInfo.elements and listInfo.elements.info then listInfo.elements.info.text = listInfo.text end
    end
    refreshList()
    bpage:createButton({ buttonText = "Bring back the last one",
        description = "Shows the most recently hidden object again, in every game.", callback = function()
        local ok, e = pcall(undoLast)
        if not ok then
            mwse.log("[mwfloatfix] bringing back the last hidden object failed: %s", tostring(e))
            tes3.messageBox("mwfloatfix: that didn't work. The reason is in MWSE.log.")
            return
        end
        tes3.messageBox(e and ("Back in every game: " .. e.id .. " (" .. e.cell .. ")") or "The list is empty.")
        pcall(refreshList)
    end })
    template:register()
end)
