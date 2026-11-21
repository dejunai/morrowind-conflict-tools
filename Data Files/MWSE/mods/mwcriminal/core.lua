--[[
    mwcriminal core: the ownership, lock and detection questions every feature asks. Everything is answered on
    demand when the player activates something; nothing is cached, scanned per frame or kept in a growing table.
]]
local config = require("mwcriminal.config")

local core = {}

-- keyring items whose container holds the keys (as abot Door Locks reads them)
local KEYRINGS = { g7_inventory_keys = "g7_container_KEYS", invhlp_keyring = "invhlp_keyring_rc" }
-- unowned interiors that are never someone's home, even with people inside
local SKIP_NAMES = { "cave", "cavern", "grotto", "tomb", "crypt", "barrow", "ruin", "ruins", "sewer", "sewers", "ship",
    "propylon", "mine", "stronghold", "yurt", "tent", "warehouse", "daedric", "shrine" }

function core.matchesAny(name, words)
    name = (name or ""):lower()
    for _, w in ipairs(words) do
        if name:find("%f[%w]" .. w .. "%f[%W]") then return true end
    end
    return false
end

function core.isSneaking()
    return tes3.mobilePlayer ~= nil and tes3.mobilePlayer.isSneaking
end

function core.isOwned(ref)
    return not tes3.hasOwnershipAccess({ target = ref })
end

function core.isOutside(cell)
    return cell ~= nil and (not cell.isInterior or cell.isOrBehavesAsExterior == true)
end

-- a door from a true interior to the outside
function core.isExit(door)
    local dest = door.destination and door.destination.cell
    local src = door.cell
    return dest ~= nil and src ~= nil and not core.isOutside(src) and core.isOutside(dest)
end

local function alive(ref)
    return not ref.disabled and not ref.deleted and ref.isDead ~= true
end

function core.livingNPCs(cell)
    local list = {}
    for ref in cell:iterateReferences(tes3.objectType.npc) do
        if alive(ref) then list[#list + 1] = ref end
    end
    return list
end

function core.isPublic(cell)
    if not cell then return false end
    if core.matchesAny(cell.id, config.publicNames) then return true end
    for _, ref in ipairs(core.livingNPCs(cell)) do
        local class = ref.object.class
        if class and class.id:lower():find("publican", 1, true) then return true end
    end
    return false
end

-- the town part of a cell name: "Balmora" for "Balmora, Hlaalo Manor" and for the exterior "Balmora"
local function place(cell)
    local name = cell.isInterior and cell.id or cell.name
    if not name then return nil end
    return (name:match("^([^,:]+)") or name):lower()
end

function core.npcAlive(npc)
    local ref = tes3.getReference(npc.id)
    return not (ref and ref.isDead == true)   -- an owner that can't be found is treated as alive
end

local function inside(npc, cell)
    for _, ref in ipairs(core.livingNPCs(cell)) do
        if ref.baseObject == npc or ref.object == npc then return true end
    end
    return false
end

function core.isEvening(hour)
    return hour < config.openHour or hour >= config.closeHour
end

function core.hasKey(ref)
    local key = ref.lockNode and ref.lockNode.key
    if not key then return false end
    local inv = tes3.player.object.inventory
    if inv:contains(key.id) then return true end
    for ring, holder in pairs(KEYRINGS) do
        if inv:contains(ring) then
            local box = tes3.getReference(holder)
            if box and box.object.inventory and box.object.inventory:contains(key.id) then return true end
        end
    end
    return false
end

--[[ What the evening rule wants for a door into an interior:
    "open"   unlock any lock (dead owner, faction member)
    "unlock" remove mwcriminal's own lock
    "lock"   lock it if it isn't
    nil      not a door mwcriminal manages ]]
function core.lockVerdict(door, hour)
    local dest = door.destination and door.destination.cell
    local src = door.cell
    if not dest or not src or core.isOutside(dest) or dest == src then return nil end
    if door.object.script then return nil end             -- quest and lock-script doors keep their own logic
    if not (core.isOutside(src) or core.isPublic(src)) then return nil end   -- never lock the player in a home
    if core.isPublic(dest) then return "unlock" end
    local owner = tes3.getOwner({ reference = door })
    if owner and owner.objectType == tes3.objectType.faction then
        if tes3.hasOwnershipAccess({ target = door }) then return "open" end
    elseif owner and owner.objectType == tes3.objectType.npc then
        if not core.npcAlive(owner) then return "open" end
        if tes3.hasOwnershipAccess({ target = door }) then return "unlock" end
        if not inside(owner, dest) then return "lock" end  -- home empty, owner alive elsewhere
        return core.isEvening(hour) and "lock" or "unlock"
    end
    local here = place(src)
    if not here or place(dest) ~= here or core.matchesAny(dest.id, SKIP_NAMES) then return nil end
    if #core.livingNPCs(dest) == 0 then return "unlock" end
    return core.isEvening(hour) and "lock" or "unlock"
end

-- applies the verdict; returns true when the door is locked afterwards
function core.applyVerdict(door, verdict)
    local ours = door.data.mwcriminalLocked
    local locked = tes3.getLocked({ reference = door })
    if locked and (verdict == "open" or (verdict == "unlock" and ours)) then
        tes3.unlock({ reference = door })
        door.data.mwcriminalLocked = nil
        return false
    end
    if verdict == "lock" and not locked then
        local level = core.matchesAny(door.destination.cell.id, config.highSecurityNames) and config.highLockLevel
            or config.lockLevel
        tes3.lock({ reference = door, level = level })
        door.data.mwcriminalLocked = true
        return true
    end
    if not locked then door.data.mwcriminalLocked = nil end
    return locked
end

-- who opens when the player knocks: awake hours, friendly enough, nearest to the arrival marker
function core.opener(door, hour)
    local dest = door.destination
    local night = hour >= config.knockUntilHour or hour < config.openHour
    local best, bestDist
    for _, ref in ipairs(core.livingNPCs(dest.cell)) do
        local obj = ref.object
        local member = obj.faction ~= nil and obj.faction.playerJoined
        local fight = obj.aiConfig and obj.aiConfig.fight or 100
        local disposition = obj.disposition or obj.baseDisposition or 0
        local willing = member or (not night and disposition >= 33)
        if willing and fight <= 75 and not obj.id:lower():find("child", 1, true) then
            local d = dest.marker and ref.position:distance(dest.marker.position) or 0
            if not best or d < bestDist then best, bestDist = ref, d end
        end
    end
    return best
end

function core.isBlankSheet(book)
    if book.type ~= tes3.bookType.scroll then return false end
    local raw = book.text or ""
    return #raw:gsub("<[^>]*>", ""):gsub("%s+", "") == 0 and not raw:lower():find("<img", 1, true)
end

-- doors and containers don't move, so one placed object is its cell, id and rounded spot
-- shortcut: two identical doors within 64 units share a key, upgrade to sourceFormId if that ever bites
function core.blacklistKey(ref)
    local t = ref.object.objectType
    local id = ref.object.id:lower()
    if t == tes3.objectType.door or t == tes3.objectType.container then
        local p = ref.position
        return string.format("ref:%s|%s|%d,%d", (ref.cell.id or ""):lower(), id, math.floor(p.x / 64 + 0.5),
            math.floor(p.y / 64 + 0.5))
    end
    return "obj:" .. id
end

function core.isBlacklisted(ref)
    return config.blacklist[core.blacklistKey(ref)] ~= nil or config.blacklist["obj:" .. ref.object.id:lower()] ~= nil
end

local function followsPlayer(mobile)
    local planner = mobile.aiPlanner
    local ok, package = pcall(function() return planner and planner:getActivePackage() end)
    if not ok or not package then return false end
    if package.type ~= tes3.aiPackage.follow and package.type ~= tes3.aiPackage.escort then return false end
    local target = package.targetActor
    return target == tes3.mobilePlayer or (target ~= nil and target.reference == tes3.player)
end

-- a detector whose sight never counts: creatures, companions, blacklisted actors; never guards or attackers
function core.ignoredDetector(mobile)
    local ref = mobile.reference
    if not ref or mobile.isDead then return false end
    if core.isBlacklisted(ref) then return true end
    for _, actor in ipairs(mobile.hostileActors or {}) do
        if actor.reference == tes3.player then return false end
    end
    if ref.object.isGuard then return false end
    if mobile.actorType == tes3.actorType.creature then return true end
    if followsPlayer(mobile) or (ref.data and ref.data.attendMeCompanion == true) then return true end
    for _, friend in ipairs(tes3.mobilePlayer.friendlyActors or {}) do
        if friend == mobile then return true end
    end
    local ok, companion = pcall(function() return ref.context and ref.context.companion end)
    return ok and companion == 1
end

return core
