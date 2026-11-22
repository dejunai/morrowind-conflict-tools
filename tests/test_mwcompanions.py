"""mwcompanions: following, warping and follower combat, run under LuaJIT against stubbed MWSE."""
import os
import subprocess

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MODS = os.path.join(ROOT, "Data Files", "MWSE", "mods", "mwsuite")
ATTEND_ME = os.path.dirname(MODS)
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

HARNESS = r'''
handlers, timers, positioned, logs, delayed = {}, {}, {}, {}, {}
installed = false
lfs = { fileexists = function() return installed end }
userConfigs = { ["Easy Escort"] = { ignoreList = { ["ab01bluegill"] = true, ["imperial guard"] = true } } }
mwse = {
  loadConfig = function(name, defaults)
    if name ~= "mwcompanions" then return userConfigs[name] end
    local c = {}
    for k, v in pairs(defaults) do c[k] = v end
    c.blacklist = {}
    return c
  end,
  saveConfig = function() end,
  log = function(fmt, ...) logs[#logs + 1] = string.format(fmt, ...) end,
}
local V = {}
V.__index = V
function vec(x, y, z) return setmetatable({ x = x, y = y, z = z }, V) end
function V:copy() return vec(self.x, self.y, self.z) end
function V:distance(o) return math.sqrt((self.x - o.x) ^ 2 + (self.y - o.y) ^ 2 + (self.z - o.z) ^ 2) end
tes3vector3 = { new = vec }
timer = {
  simulate = 1,
  start = function(p) local t = { p = p, cancel = function(self) self.cancelled = true end }; timers[#timers + 1] = t; return t end,
  register = function(name, fn) handlers["timer:" .. name] = fn end,
  delayOneFrame = function(fn) delayed[#delayed + 1] = fn end,
}
local town = { id = "Balmora", isInterior = false }
tes3 = {
  objectType = { npc = 2, creature = 6 },
  actorType = { creature = 0, npc = 1 },
  aiPackage = { none = -1, wander = 0, travel = 1, escort = 2, follow = 3 },
  effect = { soultrap = 58 },
  event = setmetatable({}, { __index = function(_, k) return k end }),
  refs = {},
  menuMode = function() return false end,
  getReference = function(id) return tes3.refs[id] end,
  positionCell = function(p) positioned[#positioned + 1] = p; p.reference.position = p.position; p.reference.cell = p.cell end,
  setAIWander = function(p) p.reference.mobile.package = { type = tes3.aiPackage.wander } end,
  setAIFollow = function(p) p.reference.mobile.package = { type = tes3.aiPackage.follow, targetActor = tes3.mobilePlayer } end,
  isAffectedBy = function(p) return p.reference.soulTrapped == true end,
  makeSafeObjectHandle = function(r) return { valid = function() return not r.unloaded end, getObject = function() return r end } end,
}
tes3.mobilePlayer = { levitate = 0, waterWalking = 0, isSneaking = false, friendlyActors = {} }
tes3.player = { position = vec(0, 0, 0), facing = 0, orientation = vec(0, 0, 0), cell = town, mobile = tes3.mobilePlayer }
tes3.mobilePlayer.reference = tes3.player
event = { register = function(name, fn) handlers[name] = fn end, trigger = function() end }
package.path = [[MODS\?.lua;ATTENDME_PATH\?.lua;]] .. package.path
require("mwcompanions.main")
handlers.initialized()
config = require("mwcompanions.config")
core = require("mwcompanions.core")

-- an actor; opts.package = "follow" | "escort" | "wander" | nil, opts.companion = 1 puts the local on its script
function actor(id, opts)
  opts = opts or {}
  local script
  if opts.companion then script = { id = "s", context = { companion = 0 } } end
  local obj = { id = id, objectType = opts.creature and tes3.objectType.creature or tes3.objectType.npc,
    isGuard = opts.guard, script = opts.script or script }
  local ref = { id = id, baseObject = obj, object = obj, data = opts.data or {}, cell = opts.cell or town,
    position = opts.position or vec(100, 0, 0), attachments = { variables = { script = script and {} or nil } } }
  if script then
    if opts.creature then
      ref.context = setmetatable({}, { __index = function() error("context read on a creature") end })
    else
      ref.context = { companion = opts.companion }
    end
  end
  local mob = { reference = ref, canMove = true, canAct = true, inCombat = false, isDead = false, alarm = 50,
    actorType = opts.creature and tes3.actorType.creature or tes3.actorType.npc, levitate = 0, waterBreathing = 0,
    waterWalking = 0, friendlyFireHitCount = 2, actionData = {},
    acrobatics = { current = 30 }, athletics = { current = 30 },
    health = { current = 100, base = 200, normalized = 0.5 }, fatigue = { current = 100, currentRaw = 100, base = 300 } }
  if opts.package then
    mob.package = { type = tes3.aiPackage[opts.package], targetActor = opts.target or tes3.mobilePlayer }
  end
  mob.aiPlanner = { getActivePackage = function() return mob.package end }
  function mob:stopCombat() self.inCombat = false; self.stopped = true end
  function mob:startCombat(t) self.inCombat = true; self.fighting = t end
  ref.mobile = mob
  tes3.refs[id] = ref
  return mob
end
function party(...) tes3.mobilePlayer.friendlyActors = { ... } end
function on(...) config.enabled = true; for _, k in ipairs({ ... }) do config[k] = true end; handlers["mwcompanions:changed"]() end
function tick() for _, t in ipairs(timers) do if not t.cancelled and t.p.iterations == -1 then t.p.callback() end end end
function check(ok, message) if not ok then error(message, 2) end end
'''


def run(body):
    script = HARNESS.replace("MODS", MODS).replace("ATTENDME_PATH", ATTEND_ME) + body + '\nprint("ok")\n'
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stdout + out.stderr


def test_who_is_a_follower():
    run(r'''
check(config.blacklist["ab01bluegill"] and config.blacklist["imperial guard"], "the suite's blacklist is imported")
check(core.followerKind(actor("hired", { package = "follow" })) == 1, "follow package on the player: follower")
check(core.followerKind(actor("julan", { package = "follow", companion = 1 })) == 2, "with companion = 1: companion")
check(core.followerKind(actor("waiting", { package = "wander", companion = 1 })) == 0, "told to wait: not followed up")
check(core.followerKind(actor("between", { companion = 1 })) == 2, "companion between packages")
check(core.followerKind(actor("pilgrim", { package = "escort" })) == 0, "escort quest NPC is not a follower")
check(core.isEscort(tes3.refs.pilgrim.mobile), "but is an escort")
check(core.followerKind(actor("other", { package = "follow", target = {} })) == 0, "following someone else")
check(core.followerKind(actor("watch", { package = "follow", guard = true })) == 0, "guards on a temporary follow")
check(core.followerKind(actor("imperial guard", { package = "follow" })) == 0, "blacklisted id")
check(core.followerKind(actor("ab01trout9", { package = "follow", creature = true })) == 0, "abot water life")
check(core.followerKind(actor("ab01guguarpackmount", { package = "follow", creature = true })) == 1, "the pack guar follows")
local fish = actor("fish", { package = "follow", creature = true, companion = 1 })
check(core.followerKind(fish) == 1, "a creature's companion local is never read (crash)")
local seat = actor("rider", { package = "follow", companion = 1, data = { rfuzzo_noscript = true } })
check(core.followerKind(seat) == 1, "a script-stripped Immersive Travel passenger is never read")
local stripped = actor("stripped", { companion = 1 })
stripped.reference.attachments.variables.script = nil
check(core.followerKind(stripped) == 0, "an instance whose script was removed is never read")
''')


def test_nothing_happens_while_off():
    run(r'''
local far = actor("far", { package = "follow", position = vec(5000, 0, 0) })
party(far)
handlers.loaded()
check(#timers == 0, "no timer while the mod is off")
config.warp = true
handlers.loaded()
check(#timers == 0, "no timer while only a switch is on")
local e = { mobile = far, attacker = tes3.mobilePlayer, damage = 10 }
config.noFriendlyFire = true
handlers.damage(e)
check(e.damage == 10, "no handler acts while the master switch is off")
''')


def test_warp():
    run(r'''
local near = actor("near", { package = "follow", position = vec(500, 0, 0) })
local far = actor("far", { package = "follow", position = vec(5000, 0, 0) })
local away = actor("away", { package = "follow", cell = { id = "Balmora, Inn", isInterior = true } })
local fighter = actor("fighter", { package = "follow", companion = 1, position = vec(9000, 0, 0) }); fighter.inCombat = true
local ally = actor("ally", { package = "follow", position = vec(9000, 0, 0) }); ally.inCombat = true
local waiter = actor("waiter", { package = "wander", companion = 1, position = vec(9000, 0, 0) })
local crew = actor("crew", { package = "follow", position = vec(9000, 0, 0), data = { rfuzzo_invincible = true } })
party(near, far, away, fighter, ally, waiter, crew)
on("warp")
check(#timers == 1 and timers[1].p.duration == 1, "one 1 s timer")
tick()
local moved = {}
for _, p in ipairs(positioned) do moved[p.reference.id] = true end
check(moved.far and moved.away and moved.ally, "far, other-cell and fighting plain followers warp")
check(not moved.near, "within the distance: stays")
check(not moved.fighter, "a companion in a fight stays in it")
check(not moved.waiter, "a waiting companion stays")
check(not moved.crew, "Immersive Travel actors stay")
for _, p in ipairs(positioned) do
  check(p.cell == town and p.position:distance(tes3.player.position) < 100, "behind the player, in the player's cell")
end
''')


def test_attend_me_recruits_are_followers_but_wait_and_move_commands_are_respected():
    run(r'''
local recruit = actor("recruit", { package = "wander", data = { attendMeCompanion = true },
  position = vec(5000, 0, 0) })
local attendMeFollowers = require("AttendMeMWSE.followers")
attendMeFollowers.init({ blacklist = {} })
check(core.followerKind(recruit) == 2 and core.isFollower(recruit), "Attend Me recruits count as companions")
check(not core.shouldWarp(recruit, 2, 2000), "Attend Me wait/wander commands are not overridden by warping")
on("assist")
party(recruit)
local bandit = actor("bandit")
handlers.combatStarted({ actor = bandit, target = tes3.mobilePlayer })
check(not recruit.inCombat, "Attend Me wait orders are not overridden by automatic assist")
recruit.package = { type = tes3.aiPackage.follow, targetActor = tes3.mobilePlayer }
check(core.shouldWarp(recruit, 2, 2000), "an actively-following Attend Me recruit can be warped")
handlers.combatStarted({ actor = bandit, target = tes3.mobilePlayer })
check(recruit.inCombat, "actively-following Attend Me companions can still assist")
''')


def test_attend_me_auto_teleport_takes_precedence_over_mwcompanions_warp():
    run(r'''
userConfigs.AttendMeMWSE = { teleportFollowers = true }
local attendMeFollowers = require("AttendMeMWSE.followers")
attendMeFollowers.init({ blacklist = {} })
local attendMeTeleport = require("AttendMeMWSE.teleport")
attendMeTeleport.init(userConfigs.AttendMeMWSE, attendMeFollowers)
local far = actor("recruit", { package = "follow", data = { attendMeCompanion = true },
  position = vec(5000, 0, 0) })
party(far)
on("warp")
tick()
check(#positioned == 0, "Attend Me owns automatic teleportation while it is enabled")
''')


def test_levitate_and_traits():
    run(r'''
local f = actor("f", { package = "follow" })
party(f)
on("levitateWater", "followerTraits")
tes3.mobilePlayer.levitate = 1
tick()
check(f.levitate == 1 and f.isFlying and f.reference.data.mwcompanionsLevitate, "levitates with the player")
check(f.alarm == 0 and f.waterBreathing == 1 and f.acrobatics.current == 150 and f.athletics.current == 220, "traits")
tes3.mobilePlayer.levitate = 0
tick()
check(f.levitate == 0 and not f.isFlying and not f.reference.data.mwcompanionsLevitate, "and lands with the player")
local own = actor("own", { package = "follow" }); own.waterWalking = 1
party(own)
tick()
check(own.waterWalking == 1, "an effect the follower has of its own is left alone")
''')


def test_friendly_fire():
    run(r'''
on("noFriendlyFire")
local f = actor("f", { package = "follow" })
local e = { mobile = f, attacker = tes3.mobilePlayer, damage = 10 }
handlers.damage(e)
check(e.damage == 0 and f.friendlyFireHitCount == 0, "the player's hit on a follower does nothing")
local foe = actor("foe")
e = { mobile = foe, attacker = tes3.mobilePlayer, damage = 10 }
handlers.damage(e)
check(e.damage == 10, "enemies are hurt")
local trapped = actor("trapped", { package = "follow" }); trapped.reference.soulTrapped = true
e = { mobile = trapped, attacker = tes3.mobilePlayer, damage = 10 }
handlers.damage(e)
check(e.damage == 10, "soul-trapping a follower still works")
local s = { caster = tes3.player, target = f.reference, effect = { object = { isHarmful = true, id = 14 } }, resistedPercent = 0 }
handlers.spellResist(s)
check(s.resistedPercent == 100, "harmful spells between friends are resisted")
s = { caster = tes3.player, target = f.reference, effect = { object = { isHarmful = false, id = 75 } }, resistedPercent = 0 }
handlers.spellResist(s)
check(s.resistedPercent == 0, "healing still lands")
''')


def test_collapse_instead_of_death():
    run(r'''
on("resilient")
local f = actor("f", { package = "follow" })
local enemy = actor("enemy"); enemy.actionData.target = f
local e = { mobile = f, attacker = enemy, damage = 150 }
handlers.damage(e)
check(e.damage == 0, "the killing blow is blocked")
check(f.fatigue.currentRaw < 0 and f.health.current == 150 and f.package.type == tes3.aiPackage.wander, "knocked out, waiting")
check(enemy.actionData.target == tes3.mobilePlayer, "the attacker turns to the player")
check(f.reference.data.mwcompanionsCollapsed, "flagged")
e = { mobile = f, attacker = enemy, damage = 50 }
handlers.damage(e)
check(e.damage == 0, "no damage while collapsed")
local t = timers[#timers]
check(t.p.callback == "mwcompanions:recover" and t.p.duration == 90, "a persistent recovery timer")
handlers["timer:mwcompanions:recover"]({ timer = { data = t.p.data } })
check(f.package.type == tes3.aiPackage.follow and f.fatigue.currentRaw == 300 and not f.reference.data.mwcompanionsCollapsed,
  "wakes up and follows again")
local foe = actor("foe")
e = { mobile = foe, attacker = tes3.mobilePlayer, damage = 150 }
handlers.damage(e)
check(e.damage == 150, "enemies die")
''')


def test_assist_and_escort_self_defense():
    run(r'''
on("assist", "escortSelfDefense")
local julan = actor("julan", { package = "follow", companion = 1 })
local hired = actor("hired", { package = "follow" })
local pilgrim = actor("pilgrim", { package = "escort", companion = 1 })
party(julan, hired, pilgrim)
local bandit = actor("bandit")
handlers.combatStarted({ actor = bandit, target = tes3.mobilePlayer })
check(julan.fighting == bandit, "a companion joins the player's fight")
check(not hired.fighting, "plain followers don't (companions only)")
check(not pilgrim.fighting, "an escort isn't sent in")
bandit.actionData.target = tes3.mobilePlayer
pilgrim.inCombat = true
handlers.combatStarted({ actor = pilgrim, target = bandit })
for _, fn in ipairs(delayed) do fn() end
check(pilgrim.stopped and not pilgrim.inCombat, "an escort that joins on its own is pulled out")
delayed = {}; pilgrim.stopped = nil
bandit.actionData.target = pilgrim
pilgrim.inCombat = true
handlers.combatStarted({ actor = pilgrim, target = bandit })
for _, fn in ipairs(delayed) do fn() end
check(not pilgrim.stopped and pilgrim.inCombat, "an escort attacked itself defends itself")
''')


def test_mute_and_sneak_activate():
    run(r'''
on("muteOnCellChange", "noSneakActivate")
local f = actor("f", { package = "follow" })
local stranger = actor("stranger")
handlers.cellChanged({ cell = town, previousCell = {} })
local e = { passes = true, dialogue = { id = "Hello" }, reference = f.reference }
handlers.infoFilter(e)
check(e.passes == false, "a follower's greeting right after a cell change is muted")
e = { passes = true, dialogue = { id = "Hello" }, reference = stranger.reference }
handlers.infoFilter(e)
check(e.passes == true, "others still greet")
tes3.mobilePlayer.isSneaking = true
check(handlers.activate({ activator = tes3.player, target = f.reference }) == false, "no pickpocketing a follower by accident")
check(handlers.activate({ activator = tes3.player, target = stranger.reference }) == nil, "others can be activated")
''')


def test_overlap_warning():
    run(r'''
userConfigs.abotSmart_Companions = { autoWarp = 2, followersResiliency = 0 }
config.enabled = true; config.warp = true; config.resilient = true
handlers.initialized()
check(#logs == 0, "orphaned configuration must not produce a warning")
installed = true
handlers.initialized()
local text = table.concat(logs, "\n")
check(text:find("Smart Companions warp", 1, true), "warns about the overlapping warp")
check(not text:find("Attend Me teleport", 1, true), "Attend Me teleport is coordinated, not treated as a conflict")
check(not text:find("resilient", 1, true), "no warning for an option that is off")
logs = {}; userConfigs.abotSmart_Companions.autoWarp = 0
handlers.initialized()
check(#logs == 0, "disabled installed options must not warn")
''')


def test_escorts_cannot_die():
    run(r'''
on("escortProtection")
local pilgrim = actor("pilgrim", { package = "escort" })
local bandit = actor("bandit"); bandit.actionData.target = pilgrim
pilgrim.hostileActors = { bandit }
local e = { mobile = pilgrim, attacker = bandit, damage = 150 }
handlers.damage(e)
check(e.damage == 0 and pilgrim.health.current == 100 and pilgrim.fatigue.currentRaw == 0, "fatigue drains instead of death")
check(bandit.actionData.target == tes3.mobilePlayer, "the attacker turns to the player")
e = { mobile = pilgrim, attacker = bandit, damage = 5 }
handlers.damage(e)
check(e.damage == 0, "no damage while down")
pilgrim.fatigue.currentRaw = 40
tick()
check(pilgrim.fatigue.currentRaw == 0, "stays down while the fight lasts")
bandit.isDead = true
tick()
check(pilgrim.fatigue.currentRaw == 300, "gets up when the fight is over")
e = { mobile = pilgrim, attacker = bandit, damage = 5 }
handlers.damage(e)
check(e.damage == 5, "takes normal hits again")
local hired = actor("hired", { package = "follow" })
e = { mobile = hired, attacker = bandit, damage = 150 }
handlers.damage(e)
check(e.damage == 150, "only escorts are protected by this switch")
''')


def test_a_downed_escort_whose_cell_unloads_is_dropped_without_touching_its_mobile():
    run(r'''
on("escortProtection")
local pilgrim = actor("pilgrim", { package = "escort" })
local bandit = actor("bandit"); bandit.actionData.target = pilgrim
pilgrim.hostileActors = { bandit }
handlers.damage({ mobile = pilgrim, attacker = bandit, damage = 150 })
check(pilgrim.fatigue.currentRaw == 0, "knocked down")
-- the cell unloads: the reference's handle is no longer valid and the old mobile must not be read
pilgrim.reference.unloaded = true
for k in pairs(pilgrim) do pilgrim[k] = nil end
setmetatable(pilgrim, { __index = function(_, k) error("stale mobile read: " .. tostring(k)) end })
tick()
local alive = 0
for _, t in ipairs(timers) do if not t.cancelled and t.p.iterations == -1 and t.p.duration == 0.5 then alive = alive + 1 end end
check(alive == 0, "nothing left to hold down: the timer stops")
''')


def test_companions_put_their_weapon_away_after_the_fight():
    run(r'''
local function armed(id, opts)
  local mob = actor(id, opts)
  mob.weaponReady = true
  return mob
end
local jiub = armed("jiub", { package = "follow", companion = 1 })
local fighter = armed("fighter", { package = "follow", companion = 1 }); fighter.inCombat = true
local hired = armed("hired", { package = "follow" })
party(jiub, fighter, hired)
local me = tes3.mobilePlayer
on("sheatheAfterCombat")
check(#timers == 1, "the 1 s timer runs for this switch")
me.weaponReady = true; tick()
check(jiub.weaponReady, "left alone while the player's weapon is out")
me.weaponReady, me.castReady = false, true; tick()
check(jiub.weaponReady, "left alone while the player's spell is readied")
me.castReady, me.inCombat = false, true; tick()
check(jiub.weaponReady, "left alone while the player fights")
me.inCombat = false; tick()
check(not jiub.weaponReady, "put away once nobody fights")
check(fighter.weaponReady, "a companion still fighting keeps it out")
check(hired.weaponReady, "only companions")
''')
