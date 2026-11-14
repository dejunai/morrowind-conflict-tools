--[[
    mwstranded - objects left in the void when another mod rebuilt an interior   (reviewed version)

    mwdialog_check --cell-conflicts writes MWSE\config\mwstranded_data.json: for each interior a plugin
    rebuilt, the objects another plugin placed for the old layout that are now cut off from the new one.
    As the interior loads:
      move   brought into the rebuilt layout. In order of preference:
               1. "to" in the data file: the spot the Python tool worked out (the old layout's offset to the
                  new one, or the same anchor object in the new layout). Used as given, then set on the floor.
               2. a free path grid node of the rebuilt layout, walking out from the arrival along the grid
                  (path grid nodes are the places the rebuilding mod itself marked as walkable floor)
               3. a ring around the arrival (the old method), each spot checked for floor and headroom
             doors go flat against the nearest wall around the arrival
      hide   unscripted scenery is disabled, never deleted
      leave  listed only

    Changes from the original:
      - objects are matched by where their plugin put them (ref.startingPosition) rather than where they
        stand now, so an item a physics mod nudged is still recognised (actors still use a tolerance)
      - nothing is written to the save for interiors that are not on the list
      - rays: returnNormal = true (without it the wall test never passed, so doors were never set against
        a wall), a maxDistance on every ray, and root = the cell's static objects (floors and walls only,
        not actors, items or the object itself)
      - objects are set down by their bounding box (a crate's middle is no longer put at floor height)
      - spots are checked: floor below (an upward-facing surface), headroom above, and kept apart
      - location markers are never touched
      - "shown again" uses startingPosition (actors: where they stand) and the same rounding as the Python tool (round half to even)
]]

local CONFIG_NAME = "mwstranded"
local config = mwse.loadConfig(CONFIG_NAME, { enabled = true, move = true, hide = true, log = true })

local LOG_DIR = "Data Files\\MWSE\\logs"
local logFile
local function log(fmt, ...)
    if not config.log then return end
    if not logFile then
        pcall(function() lfs.mkdir(LOG_DIR) end)
        logFile = io.open(LOG_DIR .. "\\mwstranded.log", "w")
        if not logFile then return end
        logFile:write(os.date("mwstranded log, started %Y-%m-%d %H:%M:%S"), "\n")
    end
    local ok, line = pcall(string.format, fmt, ...)
    logFile:write(os.date("[%H:%M:%S] "), ok and line or tostring(fmt), "\n")
    logFile:flush()
end

local DOWN = tes3vector3.new(0, 0, -1)
local UP = tes3vector3.new(0, 0, 1)
local ACTOR_TOL, OBJECT_TOL = 96, 3
local MIN_SPACING = 56          -- objects brought in are kept this far apart
local KEEP_CLEAR = 72           -- and this far from the arrival spot, so the player doesn't land on them
local HEADROOM_ACTOR = 120

-- Python's round(): half to even, so keys built here match the tool's ------------------------------
local function pyRound(v)
    local f = math.floor(v)
    local d = v - f
    if d > 0.5 then return f + 1 end
    if d < 0.5 then return f end
    return (f % 2 == 0) and f or f + 1
end

local function key(id, x, y, z)
    return string.format("%s|%d|%d|%d", id, x, y, z)
end

-- the list: cell id (lower) -> { arrival = {x,y,z,rz} or nil, byId = { id = { entry, ... } } } ----------
local lists = {}
local function loadData()
    lists = {}
    local data = mwse.loadConfig("mwstranded_data")
    if not data or not data.cells then
        log("no MWSE\\config\\mwstranded_data.json yet: run mwdialog_check.bat --cell-conflicts")
        return
    end
    local n = 0
    for cellId, c in pairs(data.cells) do
        local byId = {}
        for _, e in ipairs(c.objects or {}) do
            if e.action ~= "leave" and type(e.id) == "string" and type(e.pos) == "table" and #e.pos >= 3 then
                local id = e.id:lower()
                e.key = key(id, e.pos[1], e.pos[2], e.pos[3])   -- built once, here
                byId[id] = byId[id] or {}
                table.insert(byId[id], e)
                n = n + 1
            end
        end
        lists[cellId:lower()] = { arrival = c.arrival, byId = byId }
    end
    log("list from %s: %d object(s) to move or hide in %d interior(s)", tostring(data.generated), n,
        table.size(lists))
end

local function isActor(obj)
    local t = obj.objectType
    return t == tes3.objectType.npc or t == tes3.objectType.creature
end

-- the listed entry this reference is, if any. Non-actors: where their plugin placed them
-- (startingPosition, which a later nudge doesn't change). Actors: where they stand, within a step or two.
local function entryFor(set, ref)
    local obj = ref.object
    local cands = set.byId[obj.id:lower()]
    if not cands then return nil end
    local actor = isActor(obj)
    local p = (not actor and ref.startingPosition) or ref.position
    local tol = actor and ACTOR_TOL or OBJECT_TOL
    for _, e in ipairs(cands) do
        local dx, dy, dz = p.x - e.pos[1], p.y - e.pos[2], p.z - e.pos[3]
        if dx * dx + dy * dy + dz * dz <= tol * tol then return e end
    end
end

-- per-interior record in the save, created only when something is done there
local function doneIn(cellId, create)
    local all = tes3.player.data.mwstranded
    if not all then
        if not create then return nil end
        all = {}
        tes3.player.data.mwstranded = all
    end
    local d = all[cellId]
    if not d and create then
        d = { hidden = {}, moved = {} }
        all[cellId] = d
    end
    return d
end

-- placement helpers ---------------------------------------------------------------------------------
local function rayStatics(cell, from, dir, maxDistance, normal)
    return tes3.rayTest({ position = from, direction = dir, maxDistance = maxDistance,
        root = cell.staticObjectsRoot, returnNormal = normal or nil })
end

-- the floor under (x, y), searched from zTop down; nil when there is none within reach (the void)
local function floorAt(cell, x, y, zTop)
    local hit = rayStatics(cell, tes3vector3.new(x, y, zTop), DOWN, 512, true)
    if not hit or not hit.intersection then return nil end
    if hit.normal and hit.normal.z < 0.7 then return nil end         -- a slope or a wall, not a floor
    return hit.intersection.z
end

local function headroom(cell, x, y, z, need)
    local hit = rayStatics(cell, tes3vector3.new(x, y, z + 2), UP, need, false)
    return hit == nil
end

-- the height to give the reference so the bottom of its model rests at floorZ
local function restingZ(obj, floorZ)
    if isActor(obj) then return floorZ end
    local bb = obj.boundingBox
    if bb and bb.min then return floorZ - bb.min.z + 0.5 end
    return floorZ + 1
end

local function farFrom(x, y, taken, arrival)
    local ax, ay = x - arrival[1], y - arrival[2]
    if ax * ax + ay * ay < KEEP_CLEAR * KEEP_CLEAR then return false end
    for _, q in ipairs(taken) do
        local dx, dy = q.x - x, q.y - y
        if dx * dx + dy * dy < MIN_SPACING * MIN_SPACING then return false end
    end
    return true
end

-- a usable spot at (x, y) near height zHint: floor below, room above, clear of the others
local function tryAt(cell, obj, x, y, zHint, taken, arrival)
    if not farFrom(x, y, taken, arrival) then return nil end
    local fz = floorAt(cell, x, y, zHint + 96)
    if not fz then return nil end
    if isActor(obj) and not headroom(cell, x, y, fz, HEADROOM_ACTOR) then return nil end
    return tes3vector3.new(x, y, restingZ(obj, fz))
end

-- path grid nodes of the rebuilt layout in walking order from the arrival (breadth first along the grid).
-- Computed once per settle. Nodes the grid has off the ground are rejected by the floor test later.
local function gridOrder(cell, arrival)
    local grid = cell.pathGrid
    if not grid then return {} end
    local nodes = grid.nodes
    if not nodes or #nodes == 0 then return {} end
    local ax, ay, az = arrival[1], arrival[2], arrival[3]
    local start, best = nil, math.huge
    for _, node in ipairs(nodes) do
        local p = node.position
        local d = (p.x - ax) ^ 2 + (p.y - ay) ^ 2 + ((p.z - az) * 2) ^ 2
        if d < best then start, best = node, d end
    end
    local order, seen, queue, head = {}, { [start] = true }, { start }, 1
    while head <= #queue and #order < 256 do
        local node = queue[head]
        head = head + 1
        order[#order + 1] = node.position:copy()
        for _, nb in ipairs(node.connectedNodes or {}) do
            if not seen[nb] then
                seen[nb] = true
                queue[#queue + 1] = nb
            end
        end
    end
    return order
end

-- the old ring around the arrival, as a last resort, with each spot checked
local function ringSpot(cell, obj, arrival, taken)
    for i = 1, 48 do
        local ring = math.floor((i - 1) / 8)
        local radius = KEEP_CLEAR + 16 + 48 * ring
        local angle = (i - 1) * (math.pi / 4) + ring * 0.4 + (arrival[4] or 0)
        local dir = tes3vector3.new(math.sin(angle), math.cos(angle), 0)
        local from = tes3vector3.new(arrival[1], arrival[2], arrival[3] + 64)
        local wall = rayStatics(cell, from, dir, radius + 24, false)
        if not wall then                                -- nothing in the way out to that spot
            local spot = tryAt(cell, obj, arrival[1] + dir.x * radius, arrival[2] + dir.y * radius,
                arrival[3], taken, arrival)
            if spot then return spot end
        end
    end
end

-- a door: flat against the nearest wall around the arrival, facing out of it
local function wallSpot(cell, ref, arrival, taken)
    local from = tes3vector3.new(arrival[1], arrival[2], arrival[3] + 64)
    local hits = {}
    for k = 0, 15 do
        local a = k * math.pi / 8
        local dir = tes3vector3.new(math.sin(a), math.cos(a), 0)
        local hit = rayStatics(cell, from, dir, 1024, true)
        if hit and hit.intersection and hit.normal and hit.distance >= 96 and math.abs(hit.normal.z) < 0.3 then
            hits[#hits + 1] = hit
        end
    end
    table.sort(hits, function(p, q) return p.distance < q.distance end)
    local bb = ref.object.boundingBox
    local sx = bb and (bb.max.x - bb.min.x) or 16
    local sy = bb and (bb.max.y - bb.min.y) or 16
    local thin, turn = math.min(sx, sy), (sx < sy) and (math.pi / 2) or 0
    for _, h in ipairs(hits) do
        local n = tes3vector3.new(h.normal.x, h.normal.y, 0):normalized()
        local p = h.intersection
        local x, y = p.x + n.x * (thin / 2 + 2), p.y + n.y * (thin / 2 + 2)
        if farFrom(x, y, taken, arrival) then
            local fz = floorAt(cell, x, y, p.z + 32)
            if fz then
                return tes3vector3.new(x, y, restingZ(ref.object, fz)), math.atan2(n.x, n.y) + turn
            end
        end
    end
end

-- where a listed object goes, and which way it faces
local function placeFor(cell, ref, e, arrival, ctx)
    local obj = ref.object
    if type(e.to) == "table" and #e.to >= 3 then                  -- worked out by the Python tool
        local fz = floorAt(cell, e.to[1], e.to[2], e.to[3] + 64)
        local z = fz and restingZ(obj, fz) or e.to[3]
        return tes3vector3.new(e.to[1], e.to[2], z), e.to[4], "as worked out by mwdialog_check"
    end
    if obj.objectType == tes3.objectType.door then
        local to, rz = wallSpot(cell, ref, arrival, ctx.taken)
        if to then return to, rz, "against a wall" end
    end
    ctx.grid = ctx.grid or gridOrder(cell, arrival)
    while ctx.gridNext <= #ctx.grid do
        local p = ctx.grid[ctx.gridNext]
        ctx.gridNext = ctx.gridNext + 1
        local spot = tryAt(cell, obj, p.x, p.y, p.z, ctx.taken, arrival)
        if spot then return spot, nil, "on the path grid" end
    end
    local spot = ringSpot(cell, obj, arrival, ctx.taken)
    if spot then return spot, nil, "near the way in" end
    return nil
end

local function settleCell(cell)
    if not cell or not cell.isInterior or not tes3.player then return 0, 0, 0 end
    local cellId = cell.id:lower()
    local set = config.enabled and lists[cellId] or nil
    local done = doneIn(cellId, false)
    if not set and (not done or next(done.hidden) == nil) then return 0, 0, 0 end
    done = done or doneIn(cellId, true)
    local moved, hid, shown = 0, 0, 0
    local arrival = set and set.arrival
    local ctx = { taken = {}, gridNext = 1 }
    local todo = {}                                    -- collect first: never move refs while iterating
    for ref in cell:iterateReferences() do
        local obj = ref.object
        if obj and not ref.deleted and not obj.isLocationMarker then
            local e = set and entryFor(set, ref)
            if e and e.action == "hide" and config.hide then
                if not done.hidden[e.key] and not ref.disabled then todo[#todo + 1] = { ref, e, "hide" } end
            elseif e and e.action == "move" and config.move and arrival then
                if not done.moved[e.key] then todo[#todo + 1] = { ref, e, "move" } end
            elseif ref.disabled and next(done.hidden) then
                -- hidden earlier but no longer on the list (or switched off): show it again.
                -- startingPosition is where the plugin put it; a later nudge must not change the key
                local p = (not isActor(obj) and ref.startingPosition) or ref.position
                local k = key(obj.id:lower(), pyRound(p.x), pyRound(p.y), pyRound(p.z))
                if done.hidden[k] then todo[#todo + 1] = { ref, k, "show" } end
            end
        end
    end
    for _, t in ipairs(todo) do
        local ref, e, what = t[1], t[2], t[3]
        if what == "hide" then
            done.hidden[e.key] = true
            ref:disable()
            hid = hid + 1
            log("%s: hid %s from %s (cut off from the rebuilt layout)", cell.editorName, ref.object.id, e.from)
        elseif what == "show" then
            done.hidden[e] = nil
            ref:enable()
            shown = shown + 1
            log("%s: %s shown again", cell.editorName, ref.object.id)
        else
            local to, rz, how = placeFor(cell, ref, e, arrival, ctx)
            if to then
                done.moved[e.key] = true
                ctx.taken[#ctx.taken + 1] = to
                local face = rz or math.atan2(arrival[1] - to.x, arrival[2] - to.y)
                if isActor(ref.object) then
                    tes3.positionCell({ reference = ref, cell = cell, position = to,
                        orientation = tes3vector3.new(0, 0, face) })
                else
                    ref.position = to                  -- sets the reference as modified
                    if ref.object.objectType == tes3.objectType.door or rz then
                        ref.orientation = tes3vector3.new(0, 0, face)
                    end
                end
                moved = moved + 1
                log("%s: brought %s from %s to %.0f, %.0f, %.0f (%s; was at %d, %d, %d)", cell.editorName,
                    ref.object.id, e.from, to.x, to.y, to.z, how, e.pos[1], e.pos[2], e.pos[3])
            else
                log("%s: no free spot for %s from %s: left where it is (tried again next visit)",
                    cell.editorName, ref.object.id, e.from)
            end
        end
    end
    return moved, hid, shown
end

local function settleActive()
    local m, h, s = 0, 0, 0
    for _, cell in ipairs(tes3.getActiveCells()) do
        local ok, a, b, c = pcall(settleCell, cell)
        if ok then
            m, h, s = m + (a or 0), h + (b or 0), s + (c or 0)
        else
            log("error in %s: %s", tostring(cell.id), tostring(a))
        end
    end
    return m, h, s
end

local function settleSoon()
    if tes3.player and tes3.player.cell and tes3.player.cell.isInterior then
        timer.delayOneFrame(settleActive)
    end
end

event.register(tes3.event.initialized, loadData)
event.register(tes3.event.loaded, function()
    loadData()
    settleSoon()
end)
event.register(tes3.event.cellChanged, settleSoon)

-- Mod Config menu -----------------------------------------------------------------------------------
event.register(tes3.event.modConfigReady, function()
    local template = mwse.mcm.createTemplate({ name = "Stranded Objects (mwstranded)" })
    template:saveOnClose(CONFIG_NAME, config)
    local page = template:createSideBarPage({
        label = "Settings",
        description = "When a mod rebuilds an interior, other mods' objects made for the old layout end up "
            .. "in the void. As such a place loads, this brings the people, creatures, containers and loose "
            .. "items into the rebuilt layout, and hides the cut-off scenery. The list comes from "
            .. "mwdialog_check --cell-conflicts (MWSE\\config\\mwstranded_data.json).",
    })
    page:createOnOffButton({
        label = "On",
        description = "Off: nothing more is moved or hidden, and what it hid shows again as places load. "
            .. "Moved things stay where they were put.",
        variable = mwse.mcm.createTableVariable({ id = "enabled", table = config }),
        callback = function() if tes3.player then settleActive() end end,
    })
    page:createOnOffButton({
        label = "Bring people, creatures, containers and items into the rebuilt layout",
        variable = mwse.mcm.createTableVariable({ id = "move", table = config }),
    })
    page:createOnOffButton({
        label = "Hide cut-off scenery",
        variable = mwse.mcm.createTableVariable({ id = "hide", table = config }),
        callback = function() if tes3.player then settleActive() end end,
    })
    page:createButton({
        buttonText = "Re-read the list and apply it here now",
        callback = function()
            loadData()
            if tes3.player then
                local m, h, s = settleActive()
                tes3.messageBox("Stranded objects here: %d brought in, %d hidden, %d shown again.", m, h, s)
            end
        end,
    })
    page:createOnOffButton({
        label = "Write what it does to MWSE\\logs\\mwstranded.log",
        variable = mwse.mcm.createTableVariable({ id = "log", table = config }),
    })
    template:register()
end)
