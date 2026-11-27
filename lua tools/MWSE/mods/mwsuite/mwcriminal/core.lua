--[[
    mwcriminal core: the ownership, lock and detection questions every feature asks. Everything is answered on
    demand when the player activates something; nothing is scanned per frame or kept in a growing table (only
    the keyring containers are remembered, as safe handles).
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

-- A faction owner whose plugin left the rank at -1 ("any rank": 5244 placed things in Dej's load order, 2516 of
-- them in TR_Mainland, 45 in Morrowind.esm) is open to everyone through tes3.hasOwnershipAccess: MWSE compares the
-- player's rank, -1 for a non-member, with the requirement, and -1 >= -1. OpenMW asks for membership first, and so
-- does mwcriminal: -1 means any member, never a stranger. Members keep the vanilla exception (rank >= requirement).
local function factionOwner(ref)
    local ok, owner, rank = pcall(tes3.getOwner, { reference = ref })
    if not ok or not owner or owner.objectType ~= tes3.objectType.faction then return nil end
    return owner, tonumber(rank) or 0
end

function core.isFactionGap(ref)
    local owner, rank = factionOwner(ref)
    return owner ~= nil and rank < 0 and owner.playerJoined ~= true
end

function core.hasAccess(ref)
    return tes3.hasOwnershipAccess({ target = ref }) and not core.isFactionGap(ref)
end

function core.isOwned(ref)
    return not core.hasAccess(ref)
end

-- the -1 rank becomes 0, the lowest rank, on the thing the player looks at: a member keeps access, and the engine,
-- Quick Loot, UI Expansion and Stealth Overhaul (all asking tes3.hasOwnershipAccess) now see a stranger's take from
-- it, or from the container it is, as theft. The reference isn't marked changed for it: once the plugin's -1 is
-- back (a reload), it is fixed again the next time the thing is looked at.
function core.fixFactionRank(ref)
    if not ref then return false end
    local owner, rank = factionOwner(ref)
    if not owner or rank >= 0 then return false end
    local ok = pcall(function() ref.itemData.requirement = 0 end)
    return ok
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

-- the keyring's container, looked up once and then kept as a safe handle: hasKey runs each time the crosshair
-- lands on a locked container, and tes3.getReference searches every cell. A handle that has gone (a load) is
-- looked up again; a container that isn't found isn't remembered, so a keyring set up later is still seen.
local keyringBoxes = {}
local function keyringBox(id)
    local h = keyringBoxes[id]
    if h and h:valid() then return h:getObject() end
    keyringBoxes[id] = nil
    local box = tes3.getReference(id)
    if box and tes3.makeSafeObjectHandle then keyringBoxes[id] = tes3.makeSafeObjectHandle(box) end
    return box
end

function core.hasKey(ref)
    local key = ref.lockNode and ref.lockNode.key
    if not key then return false end
    local inv = tes3.player.object.inventory
    if inv:contains(key.id) then return true end
    for ring, holder in pairs(KEYRINGS) do
        if inv:contains(ring) then
            local box = keyringBox(holder)
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
        if core.hasAccess(door) then return "open" end
    elseif owner and owner.objectType == tes3.objectType.npc then
        if not core.npcAlive(owner) then return "open" end
        if core.hasAccess(door) then return "unlock" end
        if not inside(owner, dest) then return "lock" end  -- home empty, owner alive elsewhere
        return core.isEvening(hour) and "lock" or "unlock"
    end
    local here = place(src)
    if not here or place(dest) ~= here or core.matchesAny(dest.id, SKIP_NAMES) then return nil end
    if #core.livingNPCs(dest) == 0 then return "unlock" end
    return core.isEvening(hour) and "lock" or "unlock"
end

-- mwcriminal's own unlocks are marked: only those doors may lock again
function core.unlock(door)
    tes3.unlock({ reference = door })
    if door.data then
        door.data.mwcriminalLocked = nil
        door.data.mwcriminalUnlocked = true
    end
end

-- applies the verdict; returns true when the door is locked afterwards
function core.applyVerdict(door, verdict)
    local ours = (door.data and door.data.mwcriminalLocked)
    local locked = tes3.getLocked({ reference = door })
    if locked and (verdict == "open" or (verdict == "unlock" and ours)) then
        core.unlock(door)
        return false
    end
    if verdict == "lock" and not locked then
        -- a lock keeps its level when opened: one that is open without our mark was picked, or opened by a key,
        -- spell or script, and locking it again would undo that (the shack quest: 15 picked, relocked at 38)
        local level = math.abs(door.lockNode and door.lockNode.level or 0)
        if level > 0 and not (door.data and door.data.mwcriminalUnlocked) then
            if door.data then door.data.mwcriminalLocked = nil end
            return false
        end
        if level == 0 then
            level = core.matchesAny(door.destination.cell.id, config.highSecurityNames) and config.highLockLevel
                or config.lockLevel
        end
        tes3.lock({ reference = door, level = level })
        if door.data then
            door.data.mwcriminalLocked = true
            door.data.mwcriminalUnlocked = nil
        end
        return true
    end
    if not locked then if door.data then door.data.mwcriminalLocked = nil end end
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

local function actorFightsPlayer(mobile)
    if not mobile.inCombat then return false end
    for _, actor in ipairs(mobile.hostileActors or {}) do
        if actor and actor.reference == tes3.player then return true end
    end
    return false
end

local function isCreature(actor, ref)
    return actor.actorType == tes3.actorType.creature
        or (ref.object and ref.object.objectType == tes3.objectType.creature)
end

local function isGuard(ref)
    local obj = ref.baseObject or ref.object
    return obj and obj.isGuard == true
end

local function followsPlayer(mobile)
    local planner = mobile.aiPlanner
    local ok, package = pcall(function() return planner and planner:getActivePackage() end)
    if not ok or not package then return false end
    local isFollow = package.type == tes3.aiPackage.follow
    local isEscort = config.includeEscorts and package.type == tes3.aiPackage.escort
    if not isFollow and not isEscort then return false end
    local targetActor = package.targetActor
    if targetActor == tes3.mobilePlayer or (targetActor and targetActor.reference == tes3.player) then return true end
    return package.target == tes3.player or package.target == tes3.mobilePlayer
end

function core.isStealthBlacklisted(actor)
    if not actor then return false end
    local ref = actor.reference or actor
    if not ref or not ref.object then return false end
    if core.isExplicitlyStealthBlacklisted(ref) then return true end
    return config.blacklistAllCreatures and isCreature(actor, ref) or false
end

function core.isExplicitlyStealthBlacklisted(ref)
    if not ref or not ref.object then return false end
    local id = ref.object.id and ref.object.id:lower()
    local instanceId = ref.id and ref.id:lower()
    local blacklist = config.companionBlacklist or {}
    if (id and blacklist[id]) or (instanceId and blacklist[instanceId]) then return true end
    return false
end

function core.isCompanion(mobile)
    if not mobile or mobile == tes3.mobilePlayer then return false end
    local ref = mobile.reference
    if not ref or mobile.isDead or ref.disabled or ref.deleted then return false end
    if type(ref.isValid) == "function" and not ref:isValid() then return false end   -- isValid never raises
    if actorFightsPlayer(mobile) or isGuard(ref) then return false end
    if not config.includeCreatures and isCreature(mobile, ref) then return false end
    if followsPlayer(mobile) then return true end
    local friendlies = tes3.mobilePlayer.friendlyActors or {}
    if tes3.iterate then
        for friendly in tes3.iterate(friendlies) do
            if friendly == mobile then return true end
        end
    else
        for _, friendly in ipairs(friendlies) do
            if friendly == mobile then return true end
        end
    end
    if ref.data and ref.data.attendMeCompanion == true then return true end
    local hasAttendMe, attendMe = pcall(require, "AttendMeMWSE.followers")
    if hasAttendMe and attendMe and type(attendMe.isFollower) == "function" then
        local ok, isFollower = pcall(attendMe.isFollower, ref)
        if ok and isFollower then return true end
    end
    if mobile.actorType == tes3.actorType.npc then
        local base = ref.baseObject
        local script = base and base.script
        if script then
            local hasCompanionVar = false
            for _, list in pairs({ script.shortVariableNames, script.longVariableNames, script.shortVarNames,
                script.longVarNames }) do
                if type(list) == "table" then
                    for _, name in pairs(list) do
                        if type(name) == "string" and name:lower() == "companion" then
                            hasCompanionVar = true
                            break
                        end
                    end
                end
                if hasCompanionVar then break end
            end
            if hasCompanionVar and ref.context then
                local ok, value = pcall(function() return ref.context.companion end)
                if ok and value == 1 then return true end
            end
        end
    end
    return false
end

function core.ignoredDetector(mobile)
    local ref = mobile and mobile.reference
    if not ref or mobile.isDead then return false end
    if core.isExplicitlyStealthBlacklisted(ref) then return true end
    if actorFightsPlayer(mobile) or isGuard(ref) then return false end
    return core.isStealthBlacklisted(mobile) or core.isCompanion(mobile)
end

return core
