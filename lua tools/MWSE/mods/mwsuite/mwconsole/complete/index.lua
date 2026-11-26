--[[
    mwconsole ID index: built once per session (never per key), sorted lowercase IDs per kind, prefix lookup by
    binary search, substring search only on Tab with a cap. Each entry keeps its original case for insertion.
]]
local index = { built = false, buildMs = 0, count = 0 }

local kinds = {}            -- kind -> { keys = { lower... } (sorted), orig = { lower -> original } }
local providers = {}        -- kind -> function(prefix) -> list (extension API)
index.kinds = kinds

local function bucket(kind)
    local b = kinds[kind]
    if not b then
        b = { keys = {}, orig = {}, sorted = true }
        kinds[kind] = b
    end
    return b
end

--- add one ID (used by the builder and by objectCreated when that option is on)
function index.add(kind, id)
    if type(id) ~= "string" or id == "" then return end
    local b = bucket(kind)
    local low = id:lower()
    if b.orig[low] then return end
    b.orig[low] = id
    b.keys[#b.keys + 1] = low
    b.sorted = false
end

local function sortAll()
    for _, b in pairs(kinds) do
        if not b.sorted then
            table.sort(b.keys)
            b.sorted = true
        end
    end
end

local ITEM_TYPES = { "alchemy", "ammunition", "apparatus", "armor", "book", "clothing", "ingredient", "light",
                     "lockpick", "miscItem", "probe", "repairItem", "weapon", "leveledItem" }
local ACTOR_TYPES = { "npc", "creature", "leveledCreature" }

--- the game's data as a source: calls add(kind, id) for every object, spell, cell, faction, ...
function index.gameSource(add, opts)
    opts = opts or {}
    local typeKind = {}
    for _, t in ipairs(ITEM_TYPES) do if tes3.objectType[t] then typeKind[tes3.objectType[t]] = "item" end end
    for _, t in ipairs(ACTOR_TYPES) do if tes3.objectType[t] then typeKind[tes3.objectType[t]] = "actor" end end
    if tes3.objectType.spell then typeKind[tes3.objectType.spell] = "spell" end
    for obj in tes3.iterateObjects() do
        local id = obj.id
        local k = typeKind[obj.objectType]
        if k then add(k, id) end
        if k == "actor" and obj.objectType == tes3.objectType.creature then add("creature", id) end
        add("object", id)
    end
    local ndd = tes3.dataHandler and tes3.dataHandler.nonDynamicData
    if not ndd then return end
    local function each(list, kind, field, filter)
        if not list then return end
        pcall(function()
            for _, o in pairs(list) do
                if not filter or filter(o) then add(kind, o[field or "id"]) end
            end
        end)
    end
    each(ndd.spells, "spell")
    each(ndd.factions, "faction")
    each(ndd.globals, "global")
    each(ndd.scripts, "script")
    each(ndd.sounds, "sound")
    each(ndd.classes, "class")
    each(ndd.races, "race")
    each(ndd.regions, "region")
    pcall(function()
        for _, cell in pairs(ndd.cells) do
            if cell.isInterior then add("cell", cell.id) elseif cell.name and cell.name ~= "" then add("cell", cell.name) end
        end
    end)
    pcall(function()
        for _, d in pairs(ndd.dialogues) do
            if d.type == tes3.dialogueType.journal then add("quest", d.id)
            elseif opts.topics and d.type == tes3.dialogueType.topic then add("topic", d.id) end
        end
    end)
    pcall(function()
        for name in pairs(tes3.effect) do add("effect", name) end
    end)
end

--- build from a source function (default: the game). Returns the number of IDs and the time taken in ms.
function index.build(source, opts)
    for k in pairs(kinds) do kinds[k] = nil end
    local t0 = os.clock()
    local n = 0
    local function add(kind, id)
        if kind == "npc" then kind = "actor" end
        index.add(kind, id)
        n = n + 1
    end
    local ok, err = pcall(source or index.gameSource, add, opts)
    sortAll()
    index.built = true
    index.count = n
    index.buildMs = (os.clock() - t0) * 1000
    return ok, ok and n or err
end

function index.reset()
    for k in pairs(kinds) do kinds[k] = nil end
    index.built = false
    index.count = 0
end

local function lowerBound(keys, prefix)
    local lo, hi = 1, #keys + 1
    while lo < hi do
        local mid = math.floor((lo + hi) / 2)
        if keys[mid] < prefix then lo = mid + 1 else hi = mid end
    end
    return lo
end

--- IDs of a kind starting with prefix (case-insensitive), original case, at most limit
function index.prefix(kind, prefix, limit)
    limit = limit or 50
    local out = {}
    local p = (prefix or ""):lower()
    local b = kinds[kind]
    if b then
        if not b.sorted then sortAll() end
        local keys = b.keys
        local i = lowerBound(keys, p)
        local np = #p
        while i <= #keys and #out < limit do
            local k = keys[i]
            if k:sub(1, np) ~= p then break end
            out[#out + 1] = b.orig[k]
            i = i + 1
        end
    end
    local prov = providers[kind]
    if prov and #out < limit then
        local ok, extra = pcall(prov, prefix or "")
        if ok and type(extra) == "table" then
            for _, id in ipairs(extra) do
                if #out >= limit then break end
                if type(id) == "string" and id:lower():sub(1, #p) == p then out[#out + 1] = id end
            end
        end
    end
    return out
end

--- IDs of a kind containing text anywhere; only used on Tab; stops at limit or after budgetMs
function index.contains(kind, text, limit, budgetMs)
    limit = limit or 200
    local deadline = os.clock() + (budgetMs or 15) / 1000
    local out = {}
    local b = kinds[kind]
    if not b then return out end
    local t = (text or ""):lower()
    local keys = b.keys
    for i = 1, #keys do
        if keys[i]:find(t, 1, true) then
            out[#out + 1] = b.orig[keys[i]]
            if #out >= limit then break end
        end
        if i % 4096 == 0 and os.clock() > deadline then break end
    end
    return out
end

function index.size(kind)
    local b = kinds[kind]
    return b and #b.keys or 0
end

function index.registerProvider(kind, fn)
    providers[kind] = fn
end

function index.hasKind(kind) return kinds[kind] ~= nil or providers[kind] ~= nil end

return index
