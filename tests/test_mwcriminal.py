"""mwcriminal: sneaking, theft and door locks, run under LuaJIT against stubbed MWSE."""
import os
import subprocess

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MODS = os.path.join(ROOT, "Data Files", "MWSE", "mods")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

HARNESS = r'''
handlers, sounds, notices, boxes, added, crimes = {}, {}, {}, {}, {}, {}
local shift = false
local saved
mwse = {
  loadConfig = function(name, defaults)
    if name ~= "mwcriminal" then return nil end
    local c = {}
    for k, v in pairs(defaults) do c[k] = v end
    c.blacklist = {}
    return c
  end,
  saveConfig = function(name, c) saved = c end,
  log = function() end,
}
lfs = { fileexists = function() return false end }
local V = {}
V.__index = V
function vec(x, y, z) return setmetatable({ x = x, y = y, z = z }, V) end
function V:copy() return vec(self.x, self.y, self.z) end
function V:distance(o) return math.sqrt((self.x - o.x) ^ 2 + (self.y - o.y) ^ 2 + (self.z - o.z) ^ 2) end
V.__add = function(a, b) return vec(a.x + b.x, a.y + b.y, a.z + b.z) end
V.__mul = function(a, s) return vec(a.x * s, a.y * s, a.z * s) end
local inventory = {}
tes3 = {
  objectType = { door = 1, npc = 2, container = 3, book = 4, faction = 5, creature = 6, sound = 7, miscItem = 8 },
  bookType = { book = 0, scroll = 1 },
  actorType = { creature = 1, npc = 2 },
  aiPackage = { follow = 3, escort = 2 },
  crimeType = { theft = 5 },
  event = setmetatable({}, { __index = function(_, k) return k end }),
  player = { object = { inventory = { contains = function(_, id) return inventory[id] end } } },
  mobilePlayer = { isSneaking = false, friendlyActors = {} },
  worldController = { hour = { value = 12 }, inputController = { isShiftDown = function() return shift end } },
  refs = {},
  getLocked = function(p) return p.reference.locked == true end,
  lock = function(p) p.reference.locked, p.reference.level = true, p.level end,
  unlock = function(p) p.reference.locked = false end,
  getOwner = function(p) return p.reference.owner end,
  hasOwnershipAccess = function(p) return not p.target.owner or p.target.access == true end,
  getReference = function(id) return tes3.refs[id] end,
  playSound = function(p) sounds[#sounds + 1] = p.sound end,
  addItem = function(p) added[#added + 1] = p end,
  setItemIsStolen = function() end,
  triggerCrime = function(p) crimes[#crimes + 1] = p end,
  makeSafeObjectHandle = function(r) return { valid = function() return true end, getObject = function() return r end } end,
  getSound = function() return nil end,
  getFileExists = function() return false end,
  messageBox = function(fmt, ...) boxes[#boxes + 1] = string.format(fmt, ...) end,
}
tes3ui = { showNotifyMenu = function(s) notices[#notices + 1] = s end, getPalette = function() return "red" end }
event = { register = function(name, fn, opts) handlers[name .. (opts and opts.filter or "")] = fn end }
eiColor = nil
package.preload["Essential Indicators.interop"] = function()
  return { registerColorOverride = function(r, g, b, a, id) eiColor = id end,
           deregisterColorOverride = function(id) if eiColor == id then eiColor = nil end end }
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
function reset() sounds, notices, boxes, added, crimes = {}, {}, {}, {}, {} end
'''


def run(body):
    script = HARNESS.replace("MODS", MODS) + body + '\nprint("ok")\n'
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stdout + out.stderr


def test_exits_keys_and_sneak_to_pick():
    run(r'''
local home = cell("Balmora, Home", true)
local exit = door(town, { from = home, locked = true })
check(activate(exit) == nil and not exit.locked, "locked exit to the exterior is unlocked and passes")
local locked = door(cell("Balmora, Tomb", true), { locked = true })
check(activate(locked) == false and sounds[1] == "LockedDoor", "standing at a locked door plays the locked sound")
check(#notices == 0, "no notice unless switched on")
config.lockedNotification = true; reset()
activate(locked)
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


def test_evening_locks():
    run(r'''
local owner = npc("hlaalo")
local inside = cell("Balmora, Hlaalo House", true, { owner })
local home = door(inside, { owner = owner.object })
hour(12)
check(activate(home) == nil and not home.locked, "home is open by day with its owner inside")
hour(23)
check(activate(home) == false and home.locked and home.level == 38, "home locks in the evening (too late for a knock)")
check(home.data.mwcriminalLocked, "mwcriminal remembers its own lock")
hour(9)
check(activate(home) == nil and not home.locked and not home.data.mwcriminalLocked, "its own lock is removed by day")

local away = npc("traveller")
local empty = door(cell("Balmora, Traveller House", true), { owner = away.object })
hour(12)
check(activate(empty) == false and empty.locked, "empty home of a living owner who is elsewhere is locked by day")

local corpse = npc("victim", { dead = true })
local deadHome = door(cell("Balmora, Victim House", true), { owner = corpse.object, locked = true })
hour(21)
check(activate(deadHome) == nil and not deadHome.locked, "a dead owner's home is unlocked, even a plugin lock")

local guild = { objectType = tes3.objectType.faction }
local hall = door(cell("Balmora, Guild of Fighters", true, { npc("smith") }), { owner = guild, access = true, locked = true })
check(activate(hall) == nil and not hall.locked, "faction houses open to members")

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
check(activate(house) == nil and not house.locked, "a willing resident opens the door")
check(notices[1] == "Host opens the door.", "the opener is named")
check(host.position.y == 72 and math.abs(host.facing) > 3, "the opener waits at the door, facing the player")
handlers.cellChanged({ previousCell = house.destination.cell })
check(host.position.x == 100 and host.position.y == 0, "the opener goes back when the player leaves")
house.locked = true; reset()
hour(23)
check(activate(house) == false and sounds[1] == "LockedDoor", "nobody answers late at night")
local rude = npc("rude", { disposition = 10 })
local cold = door(cell("Balmora, Rude House", true, { rude }), { locked = true })
hour(20); reset()
check(activate(cold) == false and #notices == 0, "an unfriendly resident doesn't open")
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
  local ref = { object = { id = opts.id or "x", isGuard = opts.guard }, data = {} }
  ref.object.objectType = tes3.objectType.npc
  return { reference = ref, actorType = opts.creature and tes3.actorType.creature or tes3.actorType.npc,
    hostileActors = opts.hostile and { { reference = tes3.player } } or {},
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
''')


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
