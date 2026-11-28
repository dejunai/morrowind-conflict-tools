"""mwcriminal: sneaking, theft and door locks, run under LuaJIT against stubbed MWSE."""
import os
import subprocess

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MODS = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

HARNESS = r'''
handlers, sounds, soundAt, notices, boxes, added, crimes, timers, logs = {}, {}, {}, {}, {}, {}, {}, {}, {}
legacyConfigs, installed = {}, {}
local shift = false
local saved
mwse = {
  loadConfig = function(name, defaults)
    if name ~= "mwcriminal" then return legacyConfigs[name] end
    if not defaults then return nil end
    local c = {}
    for k, v in pairs(defaults) do c[k] = v end
    c.blacklist = {}
    return c
  end,
  saveConfig = function(name, c) saved = c end,
  log = function(fmt, ...) logs[#logs + 1] = string.format(fmt, ...) end,
}
lfs = { fileexists = function(path) return installed[path] == true end }
local V = {}
V.__index = V
function vec(x, y, z) return setmetatable({ x = x, y = y, z = z }, V) end
function V:copy() return vec(self.x, self.y, self.z) end
function V:distance(o) return math.sqrt((self.x - o.x) ^ 2 + (self.y - o.y) ^ 2 + (self.z - o.z) ^ 2) end
V.__add = function(a, b) return vec(a.x + b.x, a.y + b.y, a.z + b.z) end
V.__mul = function(a, s) return vec(a.x * s, a.y * s, a.z * s) end
local inventory = {}
tes3 = {
  scanCode = { k = 37 },
  objectType = { door = 1, npc = 2, container = 3, book = 4, faction = 5, creature = 6, sound = 7, miscItem = 8 },
  bookType = { book = 0, scroll = 1 },
  actorType = { creature = 1, npc = 2 },
  aiPackage = { follow = 3, escort = 2 },
  crimeType = { theft = 5 },
  event = setmetatable({}, { __index = function(_, k) return k end }),
  player = { object = { inventory = { contains = function(_, id) return inventory[id] end } } },
  mobilePlayer = { isSneaking = false, friendlyActors = {} },
  iterate = function(list)
    local index = 0
    return function() index = index + 1; return list[index] end
  end,
  menuMode = function() return false end,
  findActorsInProximity = function() return {} end,
  worldController = { hour = { value = 12 }, inputController = { isShiftDown = function() return shift end } },
  refs = {},
  getLocked = function(p) return p.reference.locked == true end,
  lock = function(p)
    local r = p.reference
    r.locked, r.level = true, p.level
    r.lockNode = r.lockNode or {}
    r.lockNode.level = p.level
  end,
  unlock = function(p) p.reference.locked = false end,
  getOwner = function(p) return p.reference.owner end,
  hasOwnershipAccess = function(p) return not p.target.owner or p.target.access == true end,
  getReference = function(id) return tes3.refs[id] end,
  playSound = function(p) sounds[#sounds + 1] = p.sound; soundAt[#soundAt + 1] = p.reference end,
  addItem = function(p) added[#added + 1] = p end,
  setItemIsStolen = function() end,
  triggerCrime = function(p) crimes[#crimes + 1] = p end,
  makeSafeObjectHandle = function(r) return { valid = function() return true end, getObject = function() return r end } end,
  getSound = function() return nil end,
  getFileExists = function() return false end,
  messageBox = function(fmt, ...) boxes[#boxes + 1] = string.format(fmt, ...) end,
}
timer = {
  simulate = "simulate",
  start = function(value)
    value.cancel = function(self) self.cancelled = true end
    timers[#timers + 1] = value
    return value
  end,
}
tes3ui = {
  showNotifyMenu = function(s) notices[#notices + 1] = s end,
  getPalette = function() return "red" end,
  registerID = function(id) return id end,
  findMenu = function() return nil end,
  menuMode = function() return false end,
}
event = { register = function(name, fn, opts) handlers[name .. (opts and opts.filter or "")] = fn end }
eiColor = nil
package.preload["Essential Indicators.interop"] = function()
  return { registerColorOverride = function(r, g, b, a, id) eiColor = id end,
           deregisterColorOverride = function(id) if eiColor == id then eiColor = nil end end }
end
package.preload["AttendMeMWSE.followers"] = function()
  return { isFollower = function(ref) return ref.data and ref.data.attendMe == true end }
end
package.path = [[MODS\?.lua;]] .. package.path
require("mwcriminal.main")
handlers.initialized()
config = require("mwcriminal.config")
config.enabled = true
for _, k in ipairs({ "sneakToSteal", "readStanding", "plainPaper", "companionDetection", "interiorExit",
    "sneakToPick", "eveningLocks", "knocking" }) do config[k] = true end

function cell(id, interior, actors, name)
  local c = { id = id, isInterior = interior, isOrBehavesAsExterior = not interior, name = name, actors = actors or {} }
  function c:iterateReferences()
    local i = 0
    return function() i = i + 1; return self.actors[i] end
  end
  return c
end
function npc(id, opts)
  opts = opts or {}
  local obj = { id = id, name = opts.name or id, objectType = tes3.objectType.npc, class = { id = opts.class or "commoner" },
    disposition = opts.disposition or 50, aiConfig = { fight = opts.fight or 30 }, faction = opts.faction }
  local r = { object = obj, baseObject = obj, position = vec(100, 0, 0), facing = 0, isDead = opts.dead }
  tes3.refs[id] = r
  return r
end
local town = cell("Balmora", false, {}, "Balmora")
function door(dest, opts)
  opts = opts or {}
  return { object = { id = "door", objectType = tes3.objectType.door, script = opts.script }, cell = opts.from or town,
    destination = { cell = dest, marker = { position = vec(0, 0, 0), forwardDirection = vec(0, 1, 0), facing = 0 } },
    owner = opts.owner, access = opts.access, locked = opts.locked, data = {}, position = vec(0, 0, 0),
    lockNode = opts.key and { key = { id = opts.key } } or nil }
end
function item(type, opts)
  opts = opts or {}
  return { object = { id = opts.id or "thing", name = "Thing", objectType = type, type = opts.bookType, text = opts.text,
    value = 5 }, owner = opts.owner, cell = town, position = vec(0, 0, 0), data = {}, itemData = "data",
    delete = function(self) self.deleted = true end }
end
function activate(target) return handlers.activate({ target = target, activator = tes3.player }) end
function hour(h) tes3.worldController.hour.value = h end
function sneak(on) tes3.mobilePlayer.isSneaking = on end
function setShift(on) shift = on end
function check(ok, message) if not ok then error(message, 2) end end
function reset() sounds, soundAt, notices, boxes, added, crimes = {}, {}, {}, {}, {}, {} end
function fireKnock()
  for i = #timers, 1, -1 do
    local t = timers[i]
    if t.duration == 3 and t.type == timer.simulate and not t.cancelled and t.callback then
      t.cancelled = true
      t.callback()
      return t
    end
  end
end
'''


def run(body):
    script = HARNESS.replace("MODS", MODS) + body + '\nprint("ok")\n'
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stdout + out.stderr


def run_config(body, stored_config, paper_config="nil", patches_config="nil"):
    prelude = r'''
local storedConfig = STORED_CONFIG
local paperConfig = PAPER_CONFIG
local patchesConfig = PATCHES_CONFIG
local saved
local legacy = {
  enabled = true,
  includeCreatures = false,
  includeEscorts = false,
  blacklistAllCreatures = false,
  blacklist = { ["Custom_NPC"] = true },
  inspectorKey = { keyCode = 12, isShiftDown = true, isAltDown = false, isControlDown = true },
  debugMode = true,
}
tes3 = { scanCode = { k = 37 } }
mwse = {
  loadConfig = function(name, defaults)
    if name == "mwcriminal" then
      if not defaults then return storedConfig end
      local config = {}
      for key, value in pairs(defaults) do config[key] = value end
      for key, value in pairs(storedConfig or {}) do config[key] = value end
      return config
    end
    if name == "mwcompanionsneak" then return legacy end
    if name == "mwplainpaperfix" then return paperConfig end
    if name == "mwpluginpatches" then return patchesConfig end
    return nil
  end,
  saveConfig = function(name, config) saved = config end,
}
lfs = { fileexists = function() return storedConfig ~= nil end }
package.path = [[MODS\?.lua;]] .. package.path
function check(ok, message) if not ok then error(message, 2) end end
'''
    script = (prelude.replace("STORED_CONFIG", stored_config).replace("PAPER_CONFIG", paper_config)
              .replace("PATCHES_CONFIG", patches_config)
              .replace("MODS", MODS) + body + '\nprint("ok")\n')
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stdout + out.stderr


def test_overlap_warnings_require_installed_mods():
    run(r'''
legacyConfigs.noAccidentalTheft = { enabled = true }
legacyConfigs.abotDoor_Locks = { modEnabled = true }
handlers.initialized()
check(#logs == 0, "orphaned configs must not produce warnings")
installed["Data Files\\MWSE\\mods\\mer\\accidentalTheftProtection\\main.lua"] = true
installed["Data Files\\MWSE\\mods\\abot\\Door Locks\\main.lua"] = true
handlers.initialized()
local text = table.concat(logs, "\n")
check(text:find("Accidental Theft Protection", 1, true), "installed theft mod must warn")
check(text:find("abot Door Locks", 1, true), "installed door mod must warn")
logs = {}
legacyConfigs.noAccidentalTheft.enabled = false
legacyConfigs.abotDoor_Locks.modEnabled = false
handlers.initialized()
check(#logs == 0, "disabled installed mods must not warn")
''')


def test_exits_keys_and_sneak_to_pick():
    run(r'''
local home = cell("Balmora, Home", true)
local exit = door(town, { from = home, locked = true })
check(activate(exit) == nil and not exit.locked, "locked exit to the exterior is unlocked and passes")
config.knocking = false
local locked = door(cell("Balmora, Tomb", true), { locked = true })
check(activate(locked) == false and sounds[1] == "LockedDoor", "standing at a locked door plays the locked sound")
check(#notices == 0, "no notice unless switched on")
config.lockedNotification = true; reset()
activate(locked)
check(sounds[1] == "LockedDoor", "locked sound still plays when the notice is on")
check(notices[1] == "The door is locked.", "optional notice for players without sound")
local keyed = door(cell("Balmora, Tomb", true), { locked = true, key = "tomb_key" })
inventory.tomb_key = true
check(activate(keyed) == nil, "the key holder passes standing")
sneak(true)
check(activate(locked) == nil, "sneaking passes to the lockpicking")
sneak(false); reset()
local chest = item(tes3.objectType.container); chest.locked = true
check(activate(chest) == false and sounds[1] == "LockedChest", "locked containers need sneaking too")
''')


def test_owned_doors_allow_keys_without_sneaking():
    run(r'''
local owner = npc("house_owner")
local home = cell("Balmora, House", true)
config.knocking = false
inventory.house_key = true
local locked = door(home, { owner = owner.object, locked = true, key = "house_key" })
check(activate(locked) == nil and #sounds == 0, "standing key holder passes an owned locked door")
local unlocked = door(home, { owner = owner.object, key = "house_key" })
config.eveningLocks = false
check(activate(unlocked) == nil and not unlocked.locked, "standing key holder passes an owned unlocked door")
inventory.house_key = nil
local missing = door(home, { owner = owner.object, locked = true, key = "house_key" })
check(activate(missing) == false, "an owned locked door still requires sneaking without its key")
reset()
inventory.g7_inventory_keys = true
tes3.refs.g7_container_KEYS = { object = { inventory = { contains = function(_, id) return id == "house_key" end } } }
check(activate(missing) == nil and #sounds == 0, "a key in the keyring also permits standing")
''')


def test_evening_locks():
    run(r'''
local owner = npc("hlaalo")
local inside = cell("Balmora, Hlaalo House", true, { owner })
local home = door(inside, { owner = owner.object })
hour(12)
check(activate(home) == nil and not home.locked, "home is open by day with its owner inside")
hour(23)
check(activate(home) == false and home.locked and home.level == 38, "home locks in the evening (too late for a knock)")
fireKnock()
check(home.locked and boxes[1] == "There is no response.", "a night knock gets no answer after the wait")
check(home.data.mwcriminalLocked, "mwcriminal remembers its own lock")
hour(9)
check(activate(home) == nil and not home.locked and not home.data.mwcriminalLocked, "its own lock is removed by day")

local away = npc("traveller")
local empty = door(cell("Balmora, Traveller House", true), { owner = away.object })
hour(12)
check(activate(empty) == false and empty.locked, "empty home of a living owner who is elsewhere is locked by day")
fireKnock()

local corpse = npc("victim", { dead = true })
local deadHome = door(cell("Balmora, Victim House", true), { owner = corpse.object, locked = true })
hour(21)
check(activate(deadHome) == nil and not deadHome.locked, "a dead owner's home is unlocked, even a plugin lock")

local guild = { objectType = tes3.objectType.faction }
local hall = door(cell("Balmora, Guild of Fighters", true, { npc("smith") }), { owner = guild, access = true, locked = true })
activate(hall)
fireKnock()
check(not hall.locked, "faction houses open to members")

local pub = door(cell("Balmora, Eight Plates", true, { npc("pub", { class = "Publican" }) }))
hour(23)
check(activate(pub) == nil and not pub.locked, "public places never lock")

local vacant = door(cell("Balmora, Vacant Shack", true))
check(activate(vacant) == nil and not vacant.locked, "empty unowned interior stays open")

local plugin = door(cell("Balmora, Quiet House", true, { npc("resident") }), { locked = true })
hour(12)
config.knocking = false
activate(plugin)
check(plugin.locked, "a plugin's lock is never removed by the daytime rule")
config.knocking = true

local scripted = door(cell("Balmora, Quest House", true, { npc("q") }), { script = {} })
hour(21)
check(activate(scripted) == nil and not scripted.locked, "scripted doors are left to their script")

local cellar = door(cell("Balmora, Home: Cellar", true, { npc("c") }), { from = cell("Balmora, Home", true) })
check(activate(cellar) == nil and not cellar.locked, "doors inside a home never lock the player in")

local wild = door(cell("Bandit Cave", true, { npc("bandit") }), { from = cell(nil, false, {}, nil) })
check(activate(wild) == nil and not wild.locked, "wilderness interiors aren't anyone's home")
''')


def test_knocking_moves_the_opener():
    run(r'''
local host = npc("host", { name = "Host" })
local house = door(cell("Balmora, Host House", true, { host }))
host.object.disposition = 50
hour(20)
check(activate(house) == false and house.locked, "the knock waits before anyone opens")
check(sounds[1] == "LockedDoor" and soundAt[1] == house, "LockedDoor plays at the door at once")
check(#notices == 0 and #boxes == 0, "no answer yet")
check(timers[#timers].duration == 3 and timers[#timers].type == timer.simulate, "the wait is 3 s of game time")
fireKnock()
check(not house.locked, "a willing resident opens the door")
check(notices[1] == "Host opens the door.", "the opener is named")
check(host.position.y == 72 and math.abs(host.facing) > 3, "the opener waits at the door, facing the player")
handlers.cellChanged({ previousCell = house.destination.cell })
check(host.position.x == 100 and host.position.y == 0, "the opener goes back when the player leaves")
house.locked = true; reset()
hour(23)
check(activate(house) == false and sounds[1] == "LockedDoor", "the knock still plays late at night")
check(house.locked and #boxes == 0, "no response yet")
local waiting = #timers
activate(house)
check(#timers == waiting and #sounds == 1, "a second knock is ignored while one is waiting")
fireKnock()
check(house.locked and boxes[1] == "There is no response.", "after 3 s, nobody answers late at night")
local rude = npc("rude", { disposition = 10 })
local cold = door(cell("Balmora, Rude House", true, { rude }), { locked = true })
hour(20); reset()
check(activate(cold) == false and #notices == 0, "an unfriendly resident does not open at once")
fireKnock()
check(cold.locked and #notices == 0 and boxes[1] == "There is no response.", "an unfriendly resident does not open")
house.locked = true; reset()
hour(20)
activate(house)
handlers.loaded()
check(house.locked and #notices == 0 and #boxes == 0, "a load cancels a waiting knock")
house.locked = true; reset()
activate(house)
handlers.cellChanged({ previousCell = house.cell })
check(house.locked and #notices == 0 and #boxes == 0, "leaving the cell cancels a waiting knock")
''')


def test_theft_books_and_paper():
    run(r'''
local who = npc("owner")
local cup = item(tes3.objectType.miscItem, { owner = who.object })
check(activate(cup) == false, "owned item can't be taken standing")
sneak(true)
check(activate(cup) == nil, "sneaking lets the theft through")
sneak(false)

local book = item(tes3.objectType.book, { owner = who.object, bookType = 0, text = "Words" })
check(activate(book) == nil, "owned book opens standing")
local take = { color = nil, children = { {} } }
local menu = { findChild = function(_, id) return id == "MenuBook_button_take" and take or nil end, updateLayout = function() end }
handlers.uiActivatedMenuBook({ element = menu })
check(take.color == "red" and take.children[1].color == "red", "the Take button is red")

local sheet = item(tes3.objectType.book, { bookType = 1, text = "<BR>  " })
check(activate(sheet) == false and added[1] and added[1].itemData == "data" and sheet.deleted, "blank sheet goes to the inventory")
check(sheet.itemData == nil, "item data is unhooked before the world object is deleted")
reset()
local owned = item(tes3.objectType.book, { bookType = 1, text = "", owner = who.object })
check(activate(owned) == false and #added == 0, "owned blank sheet can't be taken standing")
sneak(true)
check(activate(owned) == false and #added == 1 and crimes[1], "sneaking takes it as theft")
sneak(false)
local map = item(tes3.objectType.book, { bookType = 1, text = '<IMG SRC="map.tga">' })
check(activate(map) == nil, "a picture-only scroll still opens")
config.plainPaperRequireSneak = false
config.sneakToSteal = false
reset()
local freelyTaken = item(tes3.objectType.book, { bookType = 1, text = "", owner = who.object })
check(activate(freelyTaken) == false and #added == 1 and crimes[1], "the legacy opt-out allows owned paper theft")
config.sneakToSteal = true
reset()
local protected = item(tes3.objectType.book, { bookType = 1, text = "", owner = who.object })
check(activate(protected) == false and #added == 0, "the theft protection still takes precedence")
''')


def test_blacklist_and_master_switch():
    run(r'''
local who = npc("owner")
local cup = item(tes3.objectType.miscItem, { id = "cup", owner = who.object })
setShift(true)
check(activate(cup) == false and boxes[1]:find("added", 1, true), "Shift+activate adds to the blacklist")
check(config.blacklist["obj:cup"], "items are listed by object id")
setShift(false)
check(activate(cup) == nil, "a blacklisted object is left to the engine")
local d = door(cell("Balmora, Tomb", true), { locked = true })
setShift(true); activate(d); setShift(false)
local key = next(config.blacklist, nil)
local refKey
for k in pairs(config.blacklist) do if k:find("^ref:") then refKey = k end end
check(refKey == "ref:balmora|door|0,0", "doors are listed per placed object: " .. tostring(refKey))
config.enabled = false
local other = item(tes3.objectType.miscItem, { id = "plate", owner = who.object })
check(activate(other) == nil, "nothing happens while the master switch is off")
''')


def test_detection():
    run(r'''
local function mobile(opts)
  -- as in MWSE: isGuard is on the actor's instance, never on the base record
  local base = { id = opts.id or "x", objectType = tes3.objectType.npc }
  local ref = { baseObject = base, object = setmetatable({ isGuard = opts.guard }, { __index = base }), data = {} }
  return { reference = ref, actorType = opts.creature and tes3.actorType.creature or tes3.actorType.npc,
    hostileActors = opts.hostile and { { reference = tes3.player } } or {},
    inCombat = opts.hostile,
    aiPlanner = opts.follow and { getActivePackage = function() return { type = tes3.aiPackage.follow, targetActor = tes3.mobilePlayer } end } or nil }
end
local function detect(m)
  local e = { target = tes3.mobilePlayer, detector = m, isDetected = true }
  return handlers.detectSneak(e), e
end
local r, e = detect(mobile({ creature = true }))
check(r == false and e.isDetected == false and e.detector.isPlayerHidden, "creatures don't detect")
r, e = detect(mobile({ follow = true }))
check(r == false and e.isDetected == false, "followers don't detect")
r, e = detect(mobile({ creature = true, hostile = true }))
check(r == nil and e.isDetected, "an attacker still detects")
r, e = detect(mobile({ guard = true, follow = true }))
check(r == nil and e.isDetected, "guards still detect")
r, e = detect(mobile({}))
check(r == nil and e.isDetected, "ordinary NPCs still detect")

config.blacklistAllCreatures = false
config.includeCreatures = false
r, e = detect(mobile({ creature = true, follow = true }))
check(r == nil and e.isDetected, "creature followers can be excluded from companion handling")
config.includeCreatures = true
r, e = detect(mobile({ creature = true, follow = true }))
check(r == false and not e.isDetected, "creature followers can be included")

config.includeEscorts = false
local escortRef = { object = { id = "escort" }, data = {} }
local escort = { reference = escortRef, actorType = tes3.actorType.npc, hostileActors = {},
  aiPlanner = { getActivePackage = function() return { type = tes3.aiPackage.escort, targetActor = tes3.mobilePlayer } end } }
r, e = detect(escort)
check(r == nil and e.isDetected, "escort quest targets can be excluded")
config.includeEscorts = true
r, e = detect(escort)
check(r == false and not e.isDetected, "escort quest targets can be included")

local attendMe = mobile({})
attendMe.reference.data.attendMe = true
r, e = detect(attendMe)
check(r == false and not e.isDetected, "Attend Me interop recognizes recruited actors")

config.companionBlacklist["custom_npc"] = true
r, e = detect(mobile({ id = "CUSTOM_NPC" }))
check(r == false and not e.isDetected, "custom blacklist IDs are case-insensitive")

local follower = mobile({ follow = true })
tes3.mobilePlayer.isSneaking = true
tes3.mobilePlayer.friendlyActors = { follower }
handlers.loaded()
check(timers[1] and timers[1].duration == 0.35 and timers[1].iterations == -1, "sweep repeats every 0.35 seconds")
timers[1].callback()
check(follower.isPlayerHidden and not follower.isPlayerDetected, "sweep keeps followers hidden while sneaking")
''')


def test_companion_sweep_does_not_allocate_proximity_lists():
    """The 0.35 s sweep must not build a nearby-actor table: that lined up with 1+ GiB Lua storms."""
    run(r'''
local proximityCalls = 0
tes3.findActorsInProximity = function() proximityCalls = proximityCalls + 1; return {} end
local follower = { reference = { object = { id = "f" }, data = {} }, actorType = tes3.actorType.npc, hostileActors = {},
  aiPlanner = { getActivePackage = function() return { type = tes3.aiPackage.follow, targetActor = tes3.mobilePlayer } end } }
tes3.mobilePlayer.isSneaking = true
tes3.mobilePlayer.friendlyActors = { follower }
handlers.loaded()
local sweep = timers[#timers].callback
for _ = 1, 1000 do sweep() end
check(proximityCalls == 0, "sweep called findActorsInProximity " .. proximityCalls .. " times")
check(follower.isPlayerHidden and not follower.isPlayerDetected, "followers are still kept hidden")

-- a blacklisted stranger (not a friendly actor) is still suppressed through the detectSneak event
local chicken = { reference = { id = "chick00", object = { id = "chicken", objectType = tes3.objectType.creature }, data = {} },
  actorType = tes3.actorType.creature, hostileActors = {} }
local e = { target = tes3.mobilePlayer, detector = chicken, isDetected = true }
check(handlers.detectSneak(e) == false and not e.isDetected and chicken.isPlayerHidden,
  "blacklisted strangers are suppressed per detection event")

-- cost guard: a sweep while standing returns before touching any actor list and allocates nothing
tes3.mobilePlayer.isSneaking = false
collectgarbage("collect")
collectgarbage("stop")
local before = collectgarbage("count")
for _ = 1, 10000 do sweep() end
local grown = collectgarbage("count") - before
collectgarbage("restart")
check(grown < 1, string.format("10000 standing sweeps allocated %.1f KB", grown))
check(proximityCalls == 0, "no proximity scan at all")
''')


def test_plain_paper_settings_migrate_without_overriding_existing_choices():
    run_config(r'''
local config = require("mwcriminal.config")
check(config.enabled and config.plainPaper and not config.plainPaperRequireSneak,
    "enabled legacy paper and its owned-paper preference migrate")
check(config.plainPaperSettingsImported and saved, "migration is saved once")
''', "nil", "{ enabled = true, requireSneakForOwned = false }")
    run_config(r'''
local config = require("mwcriminal.config")
check(not config.enabled and not config.plainPaper and config.plainPaperRequireSneak,
    "existing choices take precedence over legacy settings")
''', "{ enabled = false, plainPaper = false, plainPaperRequireSneak = true }",
        "{ enabled = true, requireSneakForOwned = false }")
    run_config(r'''
local config = require("mwcriminal.config")
check(not config.plainPaper and config.plainPaperRequireSneak, "completed migration is not repeated")
''', "{ enabled = false, plainPaper = false, plainPaperRequireSneak = true, plainPaperSettingsImported = true }",
        "{ enabled = true, requireSneakForOwned = false }")


def test_book_fix_migration_respects_existing_choices():
    legacy = "{ enabled = true, noAccidentalTheftBookFixEnabled = true }"
    run_config(r'''
local config = require("mwcriminal.config")
check(config.enabled and config.readStanding and config.bookFixSettingsImported, "enabled book fix migrates")
''', "nil", patches_config=legacy)
    run_config(r'''
local config = require("mwcriminal.config")
check(not config.enabled and not config.readStanding, "existing off settings are preserved")
''', "{ enabled = false, readStanding = false }", patches_config=legacy)
    run_config(r'''
local config = require("mwcriminal.config")
check(not config.readStanding, "disabled patch does not migrate")
''', "nil", patches_config="{ enabled = false, noAccidentalTheftBookFixEnabled = true }")


def test_companionsneak_settings_migrate_without_cross_enabling_objects():
    run_config(r'''
local config = require("mwcriminal.config")
check(config.enabled and config.companionDetection, "an enabled legacy detector enables the absorbed feature")
check(not config.includeCreatures and not config.includeEscorts and not config.blacklistAllCreatures,
  "legacy detector options are preserved")
check(config.companionBlacklist.custom_npc, "legacy IDs are imported into the companion blacklist")
check(config.blacklist["obj:custom_npc"] == nil, "sneak exclusions don't blacklist objects for other features")
check(config.inspectorKey.keyCode == 12 and config.debugMode, "legacy inspector and debug settings are preserved")
''', "nil")


def test_saved_mwcriminal_master_off_is_not_overridden_by_legacy_enable():
    run_config(r'''
local config = require("mwcriminal.config")
check(not config.enabled and not config.companionDetection, "an existing master-off choice takes precedence")
check(config.companionSettingsImported, "legacy options still migrate into an existing config")
''', '{ enabled = false, companionDetection = false, imported = true }')


def test_locked_crosshair_tint():
    run(r'''
config.lockedCrosshair = true
local locked = door(cell("Balmora, Tomb", true), { locked = true })
handlers.activationTargetChanged({ current = locked })
check(eiColor == "mwcriminal", "crosshair tinted on a locked door")
handlers.activationTargetChanged({ current = nil })
check(eiColor == nil, "tint removed when looking away")
local keyed = door(cell("Balmora, Tomb", true), { locked = true, key = "k" })
inventory.k = true
handlers.activationTargetChanged({ current = keyed })
check(eiColor == nil, "no tint when the player has the key")
handlers.activationTargetChanged({ current = locked })
locked.locked = false
tes3.getPlayerTarget = function() return locked end
handlers.menuExit()
check(eiColor == nil, "tint cleared after the lock is picked in a menu")
config.lockedCrosshair = false
locked.locked = true
handlers.activationTargetChanged({ current = locked })
check(eiColor == nil, "switch off: no tint")
''')


def test_blacklist_window_has_visible_close_button():
    script = r'''
local order, buttons = {}, {}
local activeMenu
local function element()
  local e = { handlers = {} }
  function e:createBlock() return element() end
  function e:createLabel() return element() end
  function e:createThinBorder() return element() end
  function e:createTextInput() return element() end
  function e:createVerticalScrollPane()
    order[#order + 1] = "scroll"
    return element()
  end
  function e:createButton(args)
    order[#order + 1] = "button:" .. args.text
    local button = element()
    button.text = args.text
    buttons[args.text] = button
    return button
  end
  function e:getContentElement() return self end
  function e:updateLayout() end
  function e:register(name, callback) self.handlers[name] = callback end
  function e:destroy() self.destroyed = true end
  return e
end
package.preload["mwcriminal.config"] = function()
  return { companionBlacklist = {}, blacklistAllCreatures = false }
end
package.preload["mwcriminal.interop"] = function() return {} end
tes3 = {
  getObject = function() return nil end,
  player = {},
  mobilePlayer = {},
  messageBox = function() end,
  event = { menuExit = "menuExit", load = "load", keyDown = "keyDown" },
  scanCode = { escape = 1 },
}
event = { register = function() end, unregister = function() end }
mwse = { log = function() end, saveConfig = function() end }
local inMenuMode, leaveCount = false, 0
tes3ui = {
  registerID = function(id) return id end,
  createMenu = function(args)
    activeMenu = element()
    activeMenu.id = args.id
    return activeMenu
  end,
  findMenu = function(id)
    if activeMenu and activeMenu.id == id and not activeMenu.destroyed then return activeMenu end
  end,
  getPalette = function() return "palette" end,
  menuMode = function() return inMenuMode end,
  enterMenuMode = function() inMenuMode = true end,
  leaveMenuMode = function() leaveCount = leaveCount + 1; inMenuMode = false end,
}
package.path = [[MODS\?.lua;]] .. package.path
function check(ok, message) if not ok then error(message, 2) end end
local inspectorUI = require("mwcriminal.inspectorUI")
inspectorUI.openBlacklist()
local closeIndex, scrollIndex
for index, action in ipairs(order) do
  if action == "button:Close" then closeIndex = index end
  if action == "scroll" then scrollIndex = index end
end
check(closeIndex and scrollIndex and closeIndex < scrollIndex,
  "the close button is built before scrollable blacklist content")
buttons.Close.handlers.mouseClick()
check(leaveCount == 1 and activeMenu.destroyed, "the visible close button exits the blacklist menu")
print("ok")
'''
    script = script.replace("MODS", MODS)
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stdout + out.stderr


def test_a_lock_the_player_opened_stays_open():
    run(r'''
local owner = npc("indrele rathryon", { disposition = 10 })
local shack = cell("Balmora, Indrele Rathryon's Shack", true, {})      -- the owner is out
local picked = door(shack, { owner = owner.object, locked = true })
picked.lockNode = { level = 15 }
sneak(true); activate(picked)
check(picked.locked and picked.lockNode.level == 15, "its own lock is left as it is")
picked.locked = false                                                  -- the minigame opens it
activate(picked)
check(not picked.locked, "a picked door stays unlocked")
check(picked.lockNode.level == 15, "and never takes mwcriminal's level")

local ours = door(shack, { owner = owner.object })
activate(ours)
check(ours.locked and ours.level == config.lockLevel, "an empty home with no lock gets mwcriminal's")
ours.locked = false                                                    -- picked
activate(ours)
check(not ours.locked, "mwcriminal's own lock stays picked too")

local host = npc("host", { disposition = 80 })
local home = cell("Balmora, Host's House", true, { host })
local theirs = door(home, { owner = host.object })
hour(20); sneak(false); activate(theirs)                               -- locked for the evening, knocked open
fireKnock()
check(not theirs.locked, "knocked open")
sneak(true); activate(theirs)
check(theirs.locked, "what mwcriminal opened itself may lock again")

local low = door(home, { owner = host.object })
low.lockNode, low.data.mwcriminalUnlocked = { level = 10 }, true
activate(low)
check(low.locked and low.lockNode.level == 10, "relocking keeps the door's own level")
''')


def test_suppressions_go_to_its_own_log():
    run(r'''
local written = {}
lfs.mkdir = function() end
io.open = function(path)
  check(path == "Data Files\\MWSE\\logs\\mwcriminal.log", "the log's path: " .. path)
  return { write = function(_, ...) written[#written + 1] = table.concat({ ... }) end, flush = function() end }
end
config.debugMode = true
handlers.detectSneak({ target = tes3.mobilePlayer, isDetected = true, detector = {
  reference = { id = "chicken00", object = { id = "chicken", objectType = tes3.objectType.creature }, data = {} },
  actorType = tes3.actorType.creature, hostileActors = {} } })
check(#logs == 0, "suppressions must stay out of MWSE.log")
check(table.concat(written):find("chicken00", 1, true), "the suppression is not in mwcriminal.log")
''')


FACTION = r'''
-- tes3.getOwner and tes3.hasOwnershipAccess as MWSE has them: owner and rank from the item data, and a player
-- rank of -1 outside the faction compared with the requirement
tes3.getOwner = function(p)
  local d = p.reference.itemData
  if type(d) ~= "table" or not d.owner then return nil end
  return d.owner, d.requirement
end
tes3.hasOwnershipAccess = function(p)
  local d = p.target.itemData
  if type(d) ~= "table" or not d.owner then return true end
  if d.owner.objectType == tes3.objectType.faction then
    return (d.owner.playerJoined and d.owner.playerRank or -1) >= d.requirement
  end
  return false
end
function faction(joined, rank) return { id = "Fighters Guild", name = "Fighters Guild", objectType = tes3.objectType.faction, playerJoined = joined, playerRank = joined and rank or -1 } end
function factionThing(type, guild, required)
  local t = item(type)
  t.itemData = { owner = guild, requirement = required }
  return t
end
local factionTarget
local register = event.register
event.register = function(name, fn, opts)
  if name == "activationTargetChanged" and opts and opts.priority == 1000 then factionTarget = fn end
  return register(name, fn, opts)
end
handlers.initialized()
function look(ref) factionTarget({ current = ref }) end
config.factionOwnership = true
'''


def test_faction_goods_at_rank_minus_one_are_owned_for_outsiders():
    run(FACTION + r'''
local outsider = faction(false)
local potion = factionThing(tes3.objectType.miscItem, outsider, -1)
check(tes3.hasOwnershipAccess({ target = potion }), "MWSE itself lets a stranger take it (the bug)")
check(activate(potion) == false, "standing, a stranger can't take a faction's rank -1 thing")
check(potion.itemData.requirement == 0, "activating it fixes the rank for the engine's own theft check")
check(not tes3.hasOwnershipAccess({ target = potion }), "so the engine now sees the take as theft")
sneak(true)
check(activate(potion) == nil, "sneaking, it can be stolen")
sneak(false)
local member = faction(true, 0)
check(activate(factionThing(tes3.objectType.miscItem, member, -1)) == nil, "any member takes it freely")
check(activate(factionThing(tes3.objectType.miscItem, member, 0)) == nil, "rank 0 requirement, rank 0 member: vanilla access")
check(activate(factionThing(tes3.objectType.miscItem, faction(true, 2), 3)) == false, "below the required rank it is theft")
check(activate(factionThing(tes3.objectType.miscItem, faction(true, 4), 3)) == nil, "at or above it, it is the member's")
check(activate(factionThing(tes3.objectType.miscItem, outsider, 0)) == false, "an outsider with a set rank: theft, as before")
config.factionOwnership = false
local left = factionThing(tes3.objectType.miscItem, outsider, -1)
check(activate(left) == false and left.itemData.requirement == -1,
  "with the switch off the data is left alone, and must-sneak still counts it as owned")
''')


def test_faction_containers_own_their_contents():
    run(FACTION + r'''
local chest = factionThing(tes3.objectType.container, faction(false), -1)
look(chest)
check(chest.itemData.requirement == 0, "looking at it fixes the rank before Quick Loot reads the owner")
check(not tes3.hasOwnershipAccess({ target = chest }),
  "Quick Loot, UI Expansion and the engine's contents menu now see its contents as the faction's")
check(activate(chest) == false, "standing, a faction chest doesn't open for a stranger")
sneak(true)
check(activate(chest) == nil, "sneaking, it opens to be robbed")
sneak(false)
local guildChest = factionThing(tes3.objectType.container, faction(true, 1), -1)
look(guildChest)
check(activate(guildChest) == nil and tes3.hasOwnershipAccess({ target = guildChest }), "a member opens it freely")
local npcChest = item(tes3.objectType.container)
npcChest.itemData = { owner = npc("arrille").object }
look(npcChest)
check(npcChest.itemData.requirement == nil and activate(npcChest) == false, "NPC owners are untouched")
look(nil)
config.enabled = false
local off = factionThing(tes3.objectType.container, faction(false), -1)
look(off)
check(off.itemData.requirement == -1, "nothing is changed while mwcriminal is off")
''')


def test_faction_doors_at_rank_minus_one_stay_locked_for_outsiders():
    run(FACTION + r'''
config.knocking = false
hour(22)
local hall = cell("Balmora, Redoran Quarters", true, { npc("guildguard") })
local quarters = door(hall, { locked = true })
quarters.itemData = { owner = faction(false), requirement = -1 }
quarters.owner = nil
config.factionOwnership = false
check(activate(quarters) == false and quarters.locked, "a stranger's guild door isn't opened for them")
local mine = door(hall, { locked = true })
mine.itemData = { owner = faction(true, 0), requirement = -1 }
check(activate(mine) == nil and not mine.locked, "a member's guild door opens")
''')


def test_faction_ownership_follows_must_sneak_to_steal_until_set():
    run_config(r'''
local config = require("mwcriminal.config")
check(config.factionOwnership == true, "an install with must-sneak on gets it on")
''', "{ sneakToSteal = true, imported = true, plainPaperSettingsImported = true, bookFixSettingsImported = true, companionSettingsImported = true }")
    run_config(r'''
local config = require("mwcriminal.config")
check(config.factionOwnership == false, "a fresh install starts off")
''', "nil")
    run_config(r'''
local config = require("mwcriminal.config")
check(config.factionOwnership == false, "a choice made in the MCM is kept")
''', "{ sneakToSteal = true, factionOwnership = false, imported = true }")