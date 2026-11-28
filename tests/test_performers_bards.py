"""mwperformers, in LuaJIT with stub MWSE calls. One performer per inn: of every performer in an interior
(whichever mod added it or made it perform) one picked at random performs, the pick kept on the player; the
others' song scripts are held through scriptExecute (filtered by script), their song stops and a performing
animation goes back to the plain one; nobody is disabled, and bards an older version hid come back. In dialogue the bard's script is kept on its own
one-frame skip (`if ( state )`, none of them has a MenuMode check) and the song is cut, and the performing (lute)
animation is stopped at the same moment, before Animated Dialogue begins, and given back when the dialogue ends.
AM_Lute is a shield, so Weapon Sheathing hung it on his back and hid the hand: lute shields go on that mod's exclusion list."""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MOD = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwperformers", "main.lua")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

SCRIPT = r"""
local handlers, stopped, speaker = {}, 0, nil
local function flt(opts) return opts and opts.filter end
event = {
  register = function(name, fn, opts)
    handlers[name] = handlers[name] or {}; table.insert(handlers[name], { fn = fn, filter = flt(opts) })
  end,
  unregister = function(name, fn, opts)
    for i = #(handlers[name] or {}), 1, -1 do
      local h = handlers[name][i]
      if h.fn == fn and h.filter == flt(opts) then table.remove(handlers[name], i) end
    end
  end,
  isRegistered = function(name, fn, opts)
    for _, h in ipairs(handlers[name] or {}) do if h.fn == fn and h.filter == flt(opts) then return true end end
    return false
  end,
}
local function fire(name, e)          -- a scriptExecute handler sees only its filter's script
  e = e or {}
  local copy = {}
  for i, h in ipairs(handlers[name] or {}) do copy[i] = h end
  for _, h in ipairs(copy) do
    if name ~= "scriptExecute" or h.filter == e.script then h.fn(e) end
  end
end
local function count(name) return #(handlers[name] or {}) end
local armor = { { id = "AM_Lute", mesh = "m\\Misc_de_lute_01.nif", slot = 8 },
                { id = "detd_am_lute_armor", mesh = "m\\misc_de_lute_01.nif", slot = 8 },
                { id = "steel_shield", mesh = "a\\resolute_shield.nif", slot = 8 },
                { id = "lute_helm", mesh = "m\\misc_de_lute_01.nif", slot = 0 } }
local sheathing = { blocked = {} }
include = function(name) if name == "weaponSheathing.config" then return sheathing end end
tes3 = { objectType = { npc = 1, armor = 2 }, armorSlot = { shield = 8 },
         event = setmetatable({}, { __index = function(_, k) return k end }),
         getActiveCells = function() return {} end, getPlayerTarget = function() end,
         iterateObjects = function() local i = 0; return function() i = i + 1; return armor[i] end end,
         makeSafeObjectHandle = function(r)
           return { valid = function() return not r.gone end, getObject = function() return r end }
         end,
         removeSound = function() stopped = stopped + 1 end }
tes3ui = { getServiceActor = function() return speaker end, findMenu = function() end }
timer = { delayOneFrame = function() end }
local INN = { isInterior = true, id = "Balmora, Eight Plates", editorName = "Balmora, Eight Plates" }
local DATA = { cells = { ["balmora, eight plates"] = { { id = "someone" } } } }
mwse = { log = function() end, saveConfig = function() end, loadConfig = function(name, d)
  if name == "mwperformers_data" then return DATA end
  d.enabled = ENABLED; d.log = false; return d end }
dofile([[MOD]])
local function check(ok, what) if not ok then error(what, 2) end end
local function npc(script, context, cell)
  local base = { objectType = 1, id = "someone", mesh = "base_anim.nif", script = script and { id = script } }
  return { reference = { object = { id = base.id, baseObject = base, objectType = 1 }, context = context, cell = cell or INN } }
end

fire("initialized")
if not ENABLED then
  check(next(sheathing.blocked) == nil, "switched off: another mod's settings are left alone")
  speaker = npc("DM_Bard_script", { state = 0, positiononce = 1 })
  fire("uiActivated")
  check(stopped == 0 and speaker.reference.context.state == 0, "switched off: no bard is silenced")
  print("ok")
  return
end
check(sheathing.blocked.am_lute and sheathing.blocked.detd_am_lute_armor, "lute shields stay in the hand")
check(not sheathing.blocked.steel_shield and not sheathing.blocked.lute_helm, "other armour is sheathed as usual")

local bard = { state = 0, positiononce = 1, reposition = 0 }
speaker = npc("DM_Bard_script", bard)
local ref, script = speaker.reference, speaker.reference.object.baseObject.script
local function runs(r) local e = { reference = r, script = script }; fire("scriptExecute", e); return not e.block end
fire("uiActivated")
check(bard.state == 1 and stopped == 1, "the song stops and the script skips its frame")
check(count("enterFrame") == 0, "no frame handler")
for _ = 1, 3 do check(not runs(ref), "his script is skipped through the dialogue") end
check(runs({}), "the same script on another NPC still runs")
fire("uiActivated")                           -- back from barter
check(count("scriptExecute") == 1, "one script handler, however often the dialogue shows")
fire("menuExit")
check(runs(ref) and count("scriptExecute") == 0, "he sings again afterwards, and no script handler is left")

fire("uiActivated")
fire("loaded")
check(runs(ref) and count("scriptExecute") == 0, "loading a save ends it")

local quest = { state = 5 }
speaker = npc("my_bard_quest", quest)
fire("uiActivated")
check(quest.state == 5, "another script's own 'state' is never written")
fire("menuExit")

stopped = 0
speaker = npc("guard_script", { state = 0, positiononce = 1 })
fire("uiActivated")
check(stopped == 0, "someone who doesn't perform is left alone")
local elsewhere = { state = 0, positiononce = 1 }
speaker = npc("DM_Bard_script", elsewhere, { isInterior = true, id = "Some Other Inn", editorName = "Some Other Inn" })
fire("uiActivated")
check(stopped == 0 and elsewhere.state == 0, "a bard in an interior the list doesn't name is left alone")
print("ok")
"""


@pytest.mark.parametrize("enabled", ["true", "false"])
def test_bards_hold_their_lute_and_are_quiet_in_dialogue(enabled):
    script = SCRIPT.replace("ENABLED", enabled).replace("[[MOD]]", "[[" + MOD + "]]")
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stderr + out.stdout


CELL_SCRIPT = r"""
local handlers, filtered = {}, {}
local function key(opts) return opts and opts.filter end
event = {
  register = function(name, fn, opts)
    if key(opts) then
      filtered[name] = filtered[name] or {}
      filtered[name][key(opts)] = fn
    else
      handlers[name] = handlers[name] or {}; table.insert(handlers[name], fn)
    end
  end,
  unregister = function(name, fn, opts)
    if key(opts) then if filtered[name] then filtered[name][key(opts)] = nil end return end
    for i = #(handlers[name] or {}), 1, -1 do if handlers[name][i] == fn then table.remove(handlers[name], i) end end
  end,
  isRegistered = function(name, fn)
    for _, h in ipairs(handlers[name] or {}) do if h == fn then return true end end
    return false
  end,
}
local function fire(name, e)
  local copy = {}
  for i, fn in ipairs(handlers[name] or {}) do copy[i] = fn end
  for _, fn in ipairs(copy) do fn(e or {}) end
end
local function count(t) local n = 0 for _ in pairs(t or {}) do n = n + 1 end return n end
local delayed = {}
timer = { delayOneFrame = function(f) delayed[#delayed + 1] = f end }
local function runFrame() local d = delayed; delayed = {} for _, f in ipairs(d) do f() end end
local sounds, anims = {}, {}
local cell = { isInterior = true, id = "Balmora, Eight Plates", editorName = "Balmora, Eight Plates" }
local refs = {}
local n = 0
local function npc(id, mesh, script, mod, disabled)
  n = n + 1
  local base = { objectType = 1, id = id, name = id, mesh = mesh, script = script and { id = script }, sourceMod = mod }
  local r = { object = { id = id, name = id, baseObject = base, objectType = 1 }, cell = cell, sourceMod = mod,
              sourceFormId = n, disabled = disabled or false, sceneNode = { n = 1 },
              position = { x = n, y = 0, z = 0 } }
  r.enable = function(self) self.disabled = false end
  r.disable = function(self) error("nobody is disabled") end
  r.isValid = function() return true end
  refs[#refs + 1] = r
  return r
end
local raflod = npc("raflod", "base_anim.nif", "bard_script_vanilla_tweak", "Morrowind.esm")      -- a converted inn NPC
local lutist = npc("am_lutist", "am\\anim_lute.nif", nil, "Animated Morrowind.esp")               -- animation only
local singer = npc("bob_singer", "base_anim.nif", "DM_Bard_script", "Bards of Bardenfell.esp", true) -- hidden by v1
local patron = npc("patron", "base_anim.nif", "patron_script", "Morrowind.esm")
cell.iterateReferences = function(self, filter) local i = 0 return function() i = i + 1 return refs[i] end end
local player = { data = { mwperformers = { ["balmora, eight plates|bob_singer|bards of bardenfell.esp|3"] = true } } }
tes3 = { objectType = { npc = 1, armor = 2 }, armorSlot = { shield = 8 },
         event = setmetatable({}, { __index = function(_, k) return k end }),
         getActiveCells = function() return { cell } end, getPlayerTarget = function() end,
         iterateObjects = function() return function() end end,
         makeSafeObjectHandle = function(r) return { valid = function() return true end, getObject = function() return r end } end,
         removeSound = function(p) sounds[p.reference] = (sounds[p.reference] or 0) + 1 end,
         loadAnimation = function(p) anims[p.reference] = p.file or "own"; p.reference.sceneNode = { n = 2 } end,
         player = player }
tes3ui = { getServiceActor = function() end, findMenu = function() end }
include = function() end
local cfg
local DATA = { cells = { ["balmora, eight plates"] = { { id = "raflod" }, { id = "am_lutist" }, { id = "bob_singer" } } } }
mwse = { log = function() end, saveConfig = function() end, loadConfig = function(name, d)
  if name == "mwperformers_data" then return DATA end
  d.enabled = true; d.log = false; cfg = d; return d end }
local picks = { 2, 1, 3 }
math.random = function(m) local p = table.remove(picks, 1) assert(p <= m) return p end
dofile([[MOD]])
local function check(ok, what) if not ok then error(what, 2) end end
local function blocked(ref)
  local f = filtered.scriptExecute and filtered.scriptExecute[ref.object.baseObject.script]
  if not f then return false end
  local e = { reference = ref }
  local r = f(e)
  return e.block == true and r == false
end

fire("loaded"); runFrame()
check(not singer.disabled and player.data.mwperformers == nil, "the bard v1 hid is back, and its old table is gone")
local chosen = player.data.mwperformers_pick["balmora, eight plates"]
check(chosen == "balmora, eight plates|am_lutist|animated morrowind.esp|2", "the random pick is kept on the player: " .. tostring(chosen))
check(not blocked(lutist) and anims[lutist] == nil and sounds[lutist] == nil, "the pick performs")
check(blocked(raflod) and sounds[raflod] == 1, "a converted Morrowind.esm bard stops (its script is held, song stopped)")
check(blocked(singer) and sounds[singer] == 1, "another mod's bard stops")
check(not (filtered.scriptExecute or {})[patron.object.baseObject.script], "no one else's script is filtered")
check(count(filtered.scriptExecute) == 2, "one filter per held song script")
for _, r in ipairs(refs) do check(not r.disabled, "nobody is disabled: " .. r.object.id) end

-- the next visit keeps the same pick (no new random number), and nothing is redone
fire("cellChanged"); runFrame()
check(player.data.mwperformers_pick["balmora, eight plates"] == chosen and #picks == 2, "same pick on the next visit")

-- a new pick (the stored one cleared, as the Mod Config menu's "Pick again" does): the lute player stops now
player.data.mwperformers_pick["balmora, eight plates"] = nil
fire("cellChanged"); runFrame()
check(player.data.mwperformers_pick["balmora, eight plates"] == "balmora, eight plates|raflod|morrowind.esm|1", "picked again")
check(not blocked(raflod) and anims[lutist] == "base_anim.nif" and sounds[lutist] == 1, "the lute player stops performing")
local reloads = 0
local la = tes3.loadAnimation
tes3.loadAnimation = function(p) reloads = reloads + 1; return la(p) end
fire("cellChanged"); runFrame()
check(reloads == 0 and blocked(singer) and not blocked(raflod), "an unchanged decision reloads no animation")

-- switched off: everyone performs again, and no scriptExecute filter is left
cfg.enabled = false
fire("cellChanged"); runFrame()
check(count(filtered.scriptExecute) == 0, "no filter left when off")
check(anims[lutist] == "own" and reloads == 1, "the lute player has its own animation back")
for _, r in ipairs(refs) do check(not r.disabled, "nobody is disabled: " .. r.object.id) end
print("ok")
"""


def test_one_performer_per_inn_without_disabling_anyone():
    script = CELL_SCRIPT.replace("[[MOD]]", "[[" + MOD + "]]")
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stderr + out.stdout


ANIM_SCRIPT = r"""
-- an event system with priorities, as MWSE has: higher first, then the order registered
local handlers = {}
local seq = 0
event = {
  register = function(name, fn, opts)
    seq = seq + 1
    handlers[name] = handlers[name] or {}
    table.insert(handlers[name], { fn = fn, p = opts and opts.priority or 0, n = seq })
  end,
  unregister = function(name, fn)
    for i = #(handlers[name] or {}), 1, -1 do if handlers[name][i].fn == fn then table.remove(handlers[name], i) end end
  end,
  isRegistered = function(name, fn)
    for _, h in ipairs(handlers[name] or {}) do if h.fn == fn then return true end end
    return false
  end,
}
local function fire(name, e)
  local list = {}
  for i, h in ipairs(handlers[name] or {}) do list[i] = h end
  table.sort(list, function(a, b) if a.p ~= b.p then return a.p > b.p end return a.n < b.n end)
  for _, h in ipairs(list) do h.fn(e or {}) end
end
local AD_START, AD_END, AD_INT = "tauer.animatedDialogue.dialogueStarted", "tauer.animatedDialogue.dialogueEnded", "tauer.animatedDialogue.dialogueInterrupted"
local calls, speaker = {}, nil
local timers = {}
timer = { real = 2, simulate = 1, delayOneFrame = function() end,
          start = function(t) local h = { cb = t.callback, cancelled = false, type = t.type, duration = t.duration }
                              h.cancel = function() h.cancelled = true end
                              timers[#timers + 1] = h return h end }
local function fireTimers() local l = timers timers = {} for _, h in ipairs(l) do if not h.cancelled then h.cb() end end end
local function live() local n, last = 0, nil for _, h in ipairs(timers) do if not h.cancelled then n = n + 1 last = h end end return n, last end
tes3 = { objectType = { npc = 1, armor = 2 }, armorSlot = { shield = 8 }, animationGroup = { idle = 0 },
         event = setmetatable({}, { __index = function(_, k) return k end }),
         getActiveCells = function() return {} end,
         iterateObjects = function() return function() end end,
         makeSafeObjectHandle = function(r) return { valid = function() return not r.gone end, getObject = function() return r end } end,
         removeSound = function() end,
         loadAnimation = function(p) calls[#calls + 1] = "load:" .. tostring(p.file or "own") end,
         playAnimation = function(p)
           local s = "play"
           for _, k in ipairs({ "group", "lower", "upper", "shield" }) do if p[k] ~= nil then s = s .. " " .. k .. "=" .. p[k] end end
           calls[#calls + 1] = s
         end }
tes3ui = { getServiceActor = function() return speaker end, findMenu = function() end }
include = function() end
MWLOG = {}
local seen = {}                              -- another mod's handler (Animated Dialogue's), registered before ours
event.register("uiActivated", function() seen[#seen + 1] = calls[1] end)
local INN = { isInterior = true, id = "Balmora, Eight Plates", editorName = "Balmora, Eight Plates" }
local DATA = { cells = { ["balmora, eight plates"] = { { id = "bard" } } } }
mwse = { loadConfig = function(name, d) if name == "mwperformers_data" then return DATA end d.enabled = true; d.log = false; d.dialogueAnimation = DIALOGUE_ANIMATION; CFG = d; return d end, saveConfig = function() end, log = function(fmt, ...) MWLOG[#MWLOG + 1] = string.format(fmt, ...) end }
dofile([[MOD]])
local function check(ok, what) if not ok then error(what .. " / " .. table.concat(calls, ", "), 2) end end
local function last() return calls[#calls] end

local function performer(mesh, script, groups, override, extra)
  local base = { objectType = 1, id = "bard", mesh = mesh, script = script and { id = script } }
  local ref = { object = { id = "bard", baseObject = base, objectType = 1 }, context = { state = 0, positiononce = 1 }, cell = INN,
                sceneNode = {}, animationData = { currentAnimGroups = groups, hasOverrideAnimations = override,
                  actorNode = { update = function(_, o) calls[#calls + 1] = "update" .. (o.time and (" t=" .. o.time) or "") end } },
                mobile = {} }
  for k, v in pairs(extra or {}) do ref[k] = v end
  return { reference = ref }
end
local function reset() calls = {} timers = {} end

fire("initialized")

-- 1. a lute player with Animated Dialogue: stopped before it starts, given back once its dialogue has ended
speaker = performer("am\\anim_lute.nif", nil, { 0, 0, 255 }, true)
fire("uiActivated")
check(calls[1] == "load:base_anim.nif" and calls[2] == "play group=0" and calls[3] == "update t=0", "stopped to the plain animation, idle")
local n = #calls
fire(AD_START, {})                          -- Animated Dialogue begins: it finds the plain animation
check(#calls == n, "the start of Animated Dialogue changes nothing")
fire("uiActivated")                         -- back from barter
check(#calls == n, "a second activation of the same dialogue does not stop it again")
fire("menuExit")
check(#calls == n and #timers == 1, "with Animated Dialogue the end is left to it, with a backstop timer")
fire(AD_END, {})
check(#calls == n and live() == 1, "the dialogue is over: he stays plain for a moment, one timer")
local _, soft = live()
check(soft.type == 1 and soft.duration == 3, "a game-time timer of 3 s: " .. tostring(soft.type) .. "/" .. tostring(soft.duration))
fireTimers()
check(calls[n + 1] == "load:own" and calls[n + 2] == "play group=0" and #calls == n + 2, "its own animation back, idle restarted: " .. tostring(calls[n + 1]))
fireTimers()
check(#calls == n + 2, "nothing more once it is back")

-- 2. no Animated Dialogue (or it isn't handling this one): back when the menu closes
reset()
speaker = performer("am\\anim_lute.nif", nil, { 0, 0, 255 }, true)
fire("uiActivated")
fire("menuExit")
check(#calls == 3 and live() == 1, "he stands plain while the pause runs")
fireTimers()
check(calls[1] == "load:base_anim.nif" and calls[4] == "load:own", "restored after the pause")
local n2 = #calls
fire("menuExit"); fireTimers()
check(#calls == n2, "once")

-- 3. the backstop restores it if Animated Dialogue never ends
reset()
speaker = performer("am\\anim_lute.nif", nil, { 0, 0, 255 }, true)
fire("uiActivated"); fire(AD_START, {}); fire("menuExit")
local n3 = #calls
fireTimers()                                 -- the backstop: the end never came; the pause starts then
check(#calls == n3 and live() == 1, "backstop starts the pause")
fireTimers()
check(calls[n3 + 1] == "load:own", "backstop restores")

-- 4. a script performer playing a group (no override animation): idle, then the same groups
reset()
speaker = performer("base_anim.nif", "DM_Bard_script", { 5, 5, 255 }, false)
fire("uiActivated")
check(calls[1] == "play group=0" and not calls[1]:find("load"), "no animation file is swapped for a group player")
fire(AD_START, {}); fire(AD_END, {}); fireTimers()
check(last() == "play group=5", "the same group again: " .. last())
reset()
speaker = performer("base_anim.nif", "DM_Bard_script", { 0, 7, 3 }, false)
fire("uiActivated"); fire("menuExit"); fireTimers()
check(last() == "play upper=7 shield=3", "body sections kept apart: " .. last())

-- 5. a script performer between songs, nothing playing: left alone
reset()
speaker = performer("base_anim.nif", "DM_Bard_script", { 0, 0, 255 }, false)
fire("uiActivated"); fire("menuExit")
check(#calls == 0, "nothing playing, nothing touched")

-- 6. edge cases: dead, gone, a fight, another dialogue, load
reset()
speaker = performer("am\\anim_lute.nif", nil, { 0, 0, 255 }, true)
fire("uiActivated")
speaker.reference.mobile.isDead = true
local n6 = #calls
fire("menuExit"); fireTimers()
check(#calls == n6, "a performer who died is not given anything")
reset()
speaker = performer("am\\anim_lute.nif", nil, { 0, 0, 255 }, true)
fire("uiActivated")
speaker.reference.gone = true
n6 = #calls
fire("menuExit"); fireTimers()
check(#calls == n6, "a performer who is gone is not touched")
reset()
speaker = performer("am\\anim_lute.nif", nil, { 4, 4, 255 }, true)
fire("uiActivated")
speaker.reference.mobile.inCombat = true
fire("menuExit"); fireTimers()
check(calls[4] == "load:own" and #calls == 4, "in a fight his own animation is back, but nothing is started for him")
reset()
speaker = performer("am\\anim_lute.nif", nil, { 0, 0, 255 }, true)
fire("uiActivated")
local other = performer("base_anim.nif", "guard_script", { 0, 0, 255 }, false)
speaker = other
fire("uiActivated")
check(calls[4] == "load:own", "talking to someone else gives the first his animation back")
reset()
speaker = performer("am\\anim_lute.nif", nil, { 0, 0, 255 }, true)
fire("uiActivated"); fire("loaded")
local n7 = #calls
fire("menuExit"); fire(AD_END, {}); fireTimers()
check(#calls == n7, "loading a save forgets it")
reset()
speaker = performer("am\\anim_lute.nif", nil, { 0, 0, 255 }, true)
fire("uiActivated"); fire("cellChanged")
check(calls[4] == "load:own", "a cell change gives it back")

-- 7. someone who doesn't perform
reset()
speaker = performer("base_anim.nif", "guard_script", { 0, 0, 255 }, false)
fire("uiActivated"); fire("menuExit")
check(#calls == 0, "not a performer: untouched")

-- 8. the order: Animated Dialogue's uiActivated handler (priority 0, registered before or after ours) finds the
-- plain animation already in place
reset()
seen = {}
speaker = performer("am\\\\anim_lute.nif", nil, { 0, 0, 255 }, true)
fire("uiActivated")
check(seen[1] == "load:base_anim.nif", "ours ran before another mod's uiActivated handler")

-- 9. the pause after the dialogue: plain and idle meanwhile, one timer, cancelled by what ends his wait
local function dialogueEnded(groups)
  fire("loaded")                           -- whatever an earlier case left pending
  reset()
  speaker = performer("am\\anim_lute.nif", nil, groups or { 0, 0, 255 }, true)
  fire("uiActivated"); fire("menuExit")
end
dialogueEnded()
local m = #calls
check(m == 3 and live() == 1, "waiting, plain")
fire("menuExit"); fire("menuExit"); fire(AD_END, {}); fire(AD_INT, {})
check(live() == 1 and #calls == m, "timers are never stacked")
fireTimers()
check(calls[m + 1] == "load:own" and #calls == m + 2, "restarts after the pause")

dialogueEnded()                              -- he is talked to again during the pause: it is cancelled
m = #calls
fire("uiActivated")
check(live() == 0 and #calls == m, "a new dialogue cancels the pause and stops nothing twice")
fire("menuExit")
check(live() == 1, "and the next end starts a new one")
fireTimers()
check(calls[m + 1] == "load:own", "restored after that")

dialogueEnded()                              -- he dies during the pause
m = #calls
fire("death", { reference = speaker.reference })
check(live() == 0 and #calls == m, "death cancels the pause")
fire("menuExit"); fireTimers()
check(#calls == m, "and he is left as he is")

dialogueEnded()                              -- a cell change: restored at once, the timer is gone
m = #calls
fire("cellChanged")
check(calls[m + 1] == "load:own" and live() == 0, "a cell change restores him and cancels the pause")

dialogueEnded()                              -- a load
m = #calls
fire("loaded")
check(live() == 0 and #calls == m, "a load cancels the pause")
fire("menuExit"); fireTimers()
check(#calls == m, "and forgets him")

dialogueEnded()                              -- another one's death does nothing
m = #calls
fire("death", { reference = performer("base_anim.nif", nil, {}, false).reference })
check(live() == 1, "someone else dying leaves the pause alone")

-- the setting: 0 is at once, anything silly is clamped, and a timer that cannot start restores at once
CFG.restoreDelay = 0
dialogueEnded()
check(calls[4] == "load:own" and live() == 0, "0 s: at once")
CFG.restoreDelay = 99
dialogueEnded()
local _, long = live()
check(long.duration == 10, "clamped to 10 s")
CFG.restoreDelay = "x"
dialogueEnded()
_, long = live()
check(long.duration == 3, "an unusable value means 3 s")
CFG.restoreDelay = 3
local realStart = timer.start
timer.start = function() error("no timer") end
dialogueEnded()
check(calls[4] == "load:own", "no timer to wait with: he is not left plain")
timer.start = realStart

-- 10. one song after the dialogue: his script stays held until his animation is back. The restore (loadAnimation)
-- rebuilds him and the engine forgets the song he sings (SayDone turns true while it plays on): a script already
-- running again started a second song over it (2026-11-27, Raflod the Braggart)
reset()
local function held() return #(handlers.scriptExecute or {}) end
speaker = performer("am\anim_lute.nif", "DM_Bard_script", { 0, 0, 255 }, true)
fire("uiActivated")
check(held() == 1, "his script is held in the dialogue")
fire("menuExit")
check(held() == 1 and live() == 1, "still held while he stands plain: a song now would overlap the restore")
fireTimers()
check(calls[#calls - 1] == "load:own" and held() == 0, "released only once his animation is back")
print("ok")
"""


@pytest.mark.parametrize("on", ["true", "false"])
def test_performing_animation_stops_in_dialogue_and_comes_back(on):
    script = ANIM_SCRIPT.replace("DIALOGUE_ANIMATION", on).replace("[[MOD]]", "[[" + MOD + "]]")
    if on == "false":
        script = script.split("fire(\"initialized\")")[0] + """fire("initialized")
speaker = { reference = { cell = { isInterior = true, id = "Balmora, Eight Plates" }, object = { id = "bard", baseObject = { objectType = 1, id = "bard", mesh = "am\\\\anim_lute.nif" }, objectType = 1 },
  context = { state = 0, positiononce = 1 }, sceneNode = {}, animationData = { currentAnimGroups = { 0, 0, 255 }, hasOverrideAnimations = true } } }
speaker.reference.object.baseObject.script = { id = "DM_Bard_script" }
fire("uiActivated"); fire("menuExit")
if #calls ~= 0 then error("switched off: no animation touched / " .. table.concat(calls, ", ")) end
if #(handlers.scriptExecute or {}) ~= 0 then error("no animation to wait for: his script runs again when the menu closes") end
print("ok")
"""
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stderr + out.stdout


KNOWN_SCRIPT = r"""
local handlers, logged, lines = {}, {}, {}
event = { register = function(name, fn) handlers[name] = handlers[name] or {}; table.insert(handlers[name], fn) end,
          unregister = function() end, isRegistered = function() return false end }
local function fire(name, e) for _, fn in ipairs(handlers[name] or {}) do fn(e or {}) end end
local inn = { isInterior = true, id = "Balmora, Eight Plates", editorName = "Balmora, Eight Plates" }
local refs = { { object = { id = "raflod", name = "Raflod", baseObject = { objectType = 1, id = "raflod", mesh = "base_anim.nif",
                 script = { id = "DM_Bard_script" } }, objectType = 1 }, cell = inn, position = { x = 0, y = 0, z = 0 } } }
function inn:iterateReferences() local i = 0 return function() i = i + 1 return refs[i] end end
tes3 = { objectType = { npc = 1, armor = 2 }, armorSlot = { shield = 8 }, event = setmetatable({}, { __index = function(_, k) return k end }),
         getActiveCells = function() return { inn } end, iterateObjects = function() return function() end end,
         player = { data = {} } }
timer = { delayOneFrame = function(f) f() end }
include = function() end
lfs = { mkdir = function() end }
io.open = function() return { write = function(_, ...) for _, s in ipairs({ ... }) do lines[#lines + 1] = s end end,
                              flush = function() end } end
mwse = { log = function(fmt, ...) logged[#logged + 1] = string.format(fmt, ...) end, saveConfig = function() end,
         loadConfig = function(name, d)
           if name == "mwperformers_data" then return DATA end
           d.enabled = true; d.log = true; return d end }
dofile([[MOD]])
fire("loaded")
fire("cellChanged")
print("logged=" .. table.concat(logged, " | "))
print("lines=" .. table.concat(lines, ""))
"""


def _known(data):
    script = KNOWN_SCRIPT.replace("DATA end", data + " end").replace("[[MOD]]", "[[" + MOD + "]]")
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr + out.stdout
    return out.stdout


def test_without_the_list_no_one_is_handled_and_mwse_log_says_so_once():
    out = _known("nil")
    assert out.count("mwperformers_data.json is missing: no performers are handled") == 1
    assert "lines=\n" in out or out.rstrip().endswith("lines=")              # its own log: nothing decided


def test_a_listed_performer_who_is_not_there_is_logged_once():
    out = _known('{ cells = { ["balmora, eight plates"] = { { id = "raflod" }, { id = "ghost_bard", from = "Bards.esp" } } } }')
    assert out.count("ghost_bard is listed (placed by Bards.esp) but isn't here") == 1
    assert "raflod is listed" not in out
