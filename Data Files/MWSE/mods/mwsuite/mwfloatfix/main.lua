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

    With MWSE\config\mwfloatfix_data.json (written by mwdialog_check --cell-conflicts) only the items it
    lists are checked: those resting on something a later mod moved, rescaled or deleted, or on land a
    later mod lowered. Without it, every loose item is checked as above.

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
    perFrame     = 12,      -- items checked per frame
    log          = true,
    blacklistKey = { keyCode = tes3.scanCode.delete, isShiftDown = true, isAltDown = false, isControlDown = false },
    blacklist    = {},
    whitelist    = {},
}
local config = mwse.loadConfig(CONFIG_NAME, defaults)
config.blacklist = config.blacklist or {}
config.whitelist = config.whitelist or {}

local ITEM_TYPES = {
    [tes3.objectType.miscItem] = true, [tes3.objectType.book] = true, [tes3.objectType.ingredient] = true,
    [tes3.objectType.alchemy] = true, [tes3.objectType.weapon] = true, [tes3.objectType.ammunition] = true,
    [tes3.objectType.armor] = true, [tes3.objectType.clothing] = true, [tes3.objectType.apparatus] = true,
    [tes3.objectType.lockpick] = true, [tes3.objectType.probe] = true, [tes3.objectType.repairItem] = true,
}
local ACTOR_TYPES = {
    [tes3.objectType.npc] = true, [tes3.objectType.creature] = true,
}

local checkedThisSession = setmetatable({}, { __mode = "k" })

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
local START_ABOVE = 6                    -- rays start this far above the item's bottom (inside the item)

local LOG_DIR = "Data Files\\MWSE\\logs"
local LOG_PATH = LOG_DIR .. "\\mwfloatfix.log"
local logFile
local function log(fmt, ...)
    if not config.log then return end
    if not logFile then
        pcall(function() lfs.mkdir(LOG_DIR) end)
        logFile = io.open(LOG_PATH, "w")
        if not logFile then return end
        logFile:write(os.date("mwfloatfix log, started %Y-%m-%d %H:%M:%S"), "\n")
    end
    local ok, line = pcall(string.format, fmt, ...)
    logFile:write(os.date("[%H:%M:%S] "), ok and line or tostring(fmt), "\n")
    logFile:flush()
end

local function checkRefValid(r)
    return not r.disabled and not r.deleted and r.sceneNode ~= nil and r.position ~= nil
end

local function isRefValid(ref)
    if not ref then return false end
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
                log("restored blacklisted %s to starting position in %s", ref.object.id, ref.cell and ref.cell.editorName or "?")
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

-- distance from the item's bottom down to the first surface under (x, y), or nil if none within reach
local function gapBelow(ref, x, y, bottom)
    local hit = tes3.rayTest({
        position = tes3vector3.new(x, y, bottom + START_ABOVE),
        direction = DOWN,
        maxDistance = config.maxDrop + START_ABOVE + config.tolerance,
        ignore = { ref },
    })
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

            local hit = tes3.rayTest({
                position = pos,
                direction = dir,
                maxDistance = maxReach + wallReach,
                ignore = { ref },
            })

            if hit and not isActor(hit.reference) then
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
            local hit = tes3.rayTest({
                position = tes3vector3.new(pt[1], pt[2], zStart),
                direction = DOWN,
                maxDistance = (zStart - bottom) + 2,
                ignore = { ref },
            })
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
    local up = tes3.rayTest({
        position = centre,
        direction = tes3vector3.new(0, 0, 1),
        maxDistance = upReach,
        ignore = { ref },
    })
    if up and not isActor(up.reference) then
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

local function settle(ref)
    if not isCandidate(ref) then return end
    clearOldMarks(ref)
    checkedThisSession[ref] = true
    setRefData(ref, "mwfloatfixChecked", true)
    local corners = worldCorners(ref)
    if not corners then return end
    local bottom = bottomOf(corners)
    if underWater(ref, bottom) then return end
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
    local nearest
    for _, s in ipairs(samples) do
        local g = gapBelow(ref, s[1], s[2], bottom)
        if g then
            if g <= config.tolerance then return end         -- resting on something
            if not nearest or g < nearest then nearest = g end
        end
    end
    if not nearest or nearest > config.maxDrop then return end  -- nothing below within reach
    local centre = tes3vector3.new(cx, cy, cz)
    local top = -math.huge
    for _, c in ipairs(corners) do if c.z > top then top = c.z end end

    if againstWall(ref, corners, centre, bottom, top) then return end
    if supportedByMount(ref, corners, centre, bottom, top) then return end
    local drop = nearest - 0.5                               -- leave half a unit, no sinking in
    ref.position = tes3vector3.new(ref.position.x, ref.position.y, ref.position.z - drop)  -- sets modified
    local id = ref.object.id:lower()
    config.whitelist[id] = true
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
local function rebuildKeys()
    blackKeys, blackIds = {}, {}
    for _, e in ipairs(blacklist.entries) do
        blackKeys[e.key] = true
        if e.id then blackIds[e.id:lower()] = true end
    end
end
rebuildKeys()

local function applyBlacklist(ref)
    if not ref or ref.disabled or not ref.object then return false end
    local baseId = resolveBaseId(ref) or ref.object.id:lower()
    if not blackIds[baseId] and not blackIds[ref.object.id:lower()] then return false end
    if not blackKeys[refKey(ref)] then return false end
    ref:disable()
    log("hid blacklisted %s in %s", ref.object.id, cellKey(ref.cell))
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
    local hit = tes3.rayTest({ position = tes3.getCameraPosition(), direction = tes3.getCameraVector(),
                               maxDistance = 3000, ignore = { tes3.player } })
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
    for _, cell in ipairs(tes3.getActiveCells()) do         -- bring it back if it's around
        for ref in cell:iterateReferences() do
            if ref.disabled and ref.object and refKey(ref) == e.key then
                ref:enable()
            end
        end
    end
    log("removed from the blacklist: %s", e.key)
    return e
end

-- MWSE\config\mwfloatfix_data.json (mwdialog_check --cell-conflicts): the loose items that could float, by
-- cell. When it is there only those are checked, and every other cell costs one table lookup.
local floatList                          -- cell key -> object id -> { {x, y, z}, ... }; nil: check everything
do
    local data = mwse.loadConfig("mwfloatfix_data")
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
    log("rescued %s from under water (%.0f) to %.0f, %.0f, %.0f", ref.baseObject.id, was,
        best.to[1], best.to[2], best.to[3])
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

local function enqueue(ref)
    if not config.enabled or queued[ref] then return end
    if floatList then
        local ok, listed = pcall(isListed, ref)
        if not ok or not listed then return end
    end
    if not isCandidate(ref) then return end
    queued[ref] = true
    queue[#queue + 1] = ref
    sorted = false
    settleAt = os.clock() + 1.0                     -- wait until the cell around it has loaded
end

event.register(tes3.event.referenceActivated, function(e)
    if applyBlacklist(e.reference) then return end
    noteRescue(e.reference)
    enqueue(e.reference)
end)

event.register(tes3.event.cellChanged, function()
    queue, queued, qHead = {}, {}, 1
    sorted = true
    settleAt = os.clock() + 1.0
end)

event.register(tes3.event.loaded, function()
    queue, queued, qHead, drowning = {}, {}, 1, {}
    checkedThisSession = setmetatable({}, { __mode = "k" })
    settleAt = os.clock() + 2.0
    for _, cell in ipairs(tes3.getActiveCells()) do
        for ref in cell:iterateReferences() do
            if not applyBlacklist(ref) then
                noteRescue(ref)
                enqueue(ref)
            end
        end
    end
end)

event.register(tes3.event.simulate, function()
    if drowning[1] and tes3.player and os.clock() >= settleAt then runRescues() end
    if qHead > #queue or os.clock() < settleAt then return end
    -- lowest items first, so a book resting on a fallen book lands on it, not through it
    if not sorted then
        local rest = {}
        for i = qHead, #queue do
            local ref = queue[i]
            if isRefValid(ref) and isCandidate(ref) then
                local p = ref.position
                local z = (p and p.z) or 0
                rest[#rest + 1] = { ref = ref, z = z }
            end
        end
        table.sort(rest, function(a, b)
            return a.z < b.z
        end)
        local sortedRefs = {}
        for i = 1, #rest do
            sortedRefs[i] = rest[i].ref
        end
        queue, qHead, sorted = sortedRefs, 1, true
    end
    for _ = 1, config.perFrame do
        local ref = queue[qHead]
        if not ref then break end
        queue[qHead] = false
        qHead = qHead + 1
        queued[ref] = nil
        if isRefValid(ref) then
            local ok, err = pcall(settle, ref)
            if not ok then log("error checking %s: %s", tostring(ref.object and ref.object.id), tostring(err)) end
        end
    end
    if qHead > #queue then queue, qHead, sorted = {}, 1, false end
end)

local function restoreBlacklistedInActiveCells()
    for _, cell in ipairs(tes3.getActiveCells()) do
        for ref in cell:iterateReferences() do
            pcall(function()
                if isRefValid(ref) and ref.object and ref.startingPosition then
                    local id = ref.object.id:lower()
                    if config.blacklist and config.blacklist[id] then
                        if ref.position.z < (ref.startingPosition.z - 0.5) then
                            ref.position = tes3vector3.new(ref.startingPosition.x, ref.startingPosition.y, ref.startingPosition.z)
                            log("restored blacklisted %s to starting position in %s", ref.object.id, ref.cell and ref.cell.editorName or "?")
                        end
                    end
                end
            end)
        end
    end
end

local function recheckActiveCells()
    restoreBlacklistedInActiveCells()
    checkedThisSession = setmetatable({}, { __mode = "k" })
    for _, cell in ipairs(tes3.getActiveCells()) do
        for ref in cell:iterateReferences() do
            if not applyBlacklist(ref) then
                noteRescue(ref)
                enqueue(ref)
            end
        end
    end
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

event.register(tes3.event.save, function()
    mwse.saveConfig(CONFIG_NAME, config)
end)

-- Mod Config menu ---------------------------------------------------------------
event.register(tes3.event.modConfigReady, function()
    local template = mwse.mcm.createTemplate({ name = "Floating Item Fix" })
    template.onClose = function()
        mwse.saveConfig(CONFIG_NAME, config)
        recheckActiveCells()
    end
    local page = template:createSideBarPage({
        label = "Settings",
        description = "Lowers loose items that float above the surface under them, once, the first time "
            .. "their cell loads. Items against a wall, under water, or with no floor within reach are left "
            .. "alone. Each move is written to MWSE\\logs\\mwfloatfix.log."
            .. (floatList and "\n\nOnly the items in MWSE\\config\\mwfloatfix_data.json are checked (written by "
                .. "mwdialog_check --cell-conflicts)." or "")
            .. "\n\nPeople listed in MWSE\\config\\mwfloatfix_rescue.json (written by mwdialog_check --fix) who are "
            .. "under water in this save are put back on their dock or footing, once per save.",
    })
    page:createOnOffButton({ label = "Enabled", description = "Lower eligible floating objects when their cells load.",
        variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }) })
    page:createSlider({ label = "Still resting when the gap is up to (units)", min = 1, max = 16, step = 1,
        description = "Ignore small gaps up to this size to avoid moving items that already look properly placed.",
        variable = mwse.mcm.createTableVariable({ id = "tolerance", table = config }) })
    page:createSlider({ label = "Lower an item by at most (units)", min = 16, max = 512, step = 8,
        description = "Maximum distance to lower an item; larger gaps are left alone.",
        variable = mwse.mcm.createTableVariable({ id = "maxDrop", table = config }) })
    page:createSlider({ label = "Counts as mounted on a wall within (units)", min = 0, max = 32, step = 1,
        description = "Wall and hook detection distance for mounted items. The minimum checks are 22 units for walls and 20 for hooks.",
        variable = mwse.mcm.createTableVariable({ id = "wallGap", table = config }) })
    if not floatList then                -- the list never names lights
        page:createOnOffButton({ label = "Also carryable lights", description = "Include loose portable lights when checking for floating items.",
            variable = mwse.mcm.createTableVariable({ id = "lights", table = config }) })
    end
    page:createOnOffButton({ label = "Write moves to MWSE\\logs\\mwfloatfix.log",
        description = "Record each item lowered by the floating-item fix.",
        variable = mwse.mcm.createTableVariable({ id = "log", table = config }) })
    page:createKeyBinder({ label = "Hide key (look at an object, or click it in the console, then press)",
        description = "Hide the targeted object across games; use Hidden Objects to restore the most recently hidden one.",
        allowCombinations = true, variable = mwse.mcm.createTableVariable({ id = "blacklistKey", table = config }) })

    template:createExclusionsPage({
        label = "Whitelist / Blacklist",
        description = "Items moved by Floatfix are automatically added to the Whitelist.\n\n"
            .. "• Click any item in the Whitelist to move it to the Blacklist (Floatfix will leave it alone and restore its starting position if previously lowered).\n"
            .. "• Click any item in the Blacklist to move it back to the Whitelist.",
        leftListLabel = "Blacklist (Do Not Move)",
        rightListLabel = "Whitelist (Allowed / Moved)",
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
    bpage:createInfo({ text = "Objects permanently hidden using the hide key. Look at one (or click it with the console open) and "
        .. "press the hide key to add it. The list is MWSE\\config\\mwfloatfix_blacklist.json." })
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
        description = "Restore the most recently hidden object in every game.", callback = function()
        local e = undoLast()
        tes3.messageBox(e and ("Back in every game: " .. e.id .. " (" .. e.cell .. ")") or "The list is empty.")
        refreshList()
    end })
    template:register()
end)
