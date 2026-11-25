"""mwperformers, in LuaJIT with stub MWSE calls. One performer per inn: of every performer in an interior
(whichever mod added it or made it perform) one picked at random performs, the pick kept on the player; the
others' song scripts are held through scriptExecute (filtered by script), their song stops and a performing
animation goes back to the plain one; nobody is disabled, and bards an older version hid come back. In dialogue the bard's script is kept on its own
one-frame skip (`if ( state )`, none of them has a MenuMode check) and the song is cut. AM_Lute is a shield, so
Weapon Sheathing hung it on his back and hid the hand: lute shields go on that mod's exclusion list."""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.path.join(ROOT, "tools", "luajit", "luajit.exe")
MOD = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwperformers", "main.lua")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

SCRIPT = r"""
local handlers, stopped, speaker = {}, 0, nil
event = {
  register = function(name, fn) handlers[name] = handlers[name] or {}; table.insert(handlers[name], fn) end,
  unregister = function(name, fn)
    for i = #(handlers[name] or {}), 1, -1 do if handlers[name][i] == fn then table.remove(handlers[name], i) end end
  end,
}
local function fire(name, e)
  local copy = {}
  for i, fn in ipairs(handlers[name] or {}) do copy[i] = fn end
  for _, fn in ipairs(copy) do fn(e or {}) end
end
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
mwse = { loadConfig = function(_, d) d.enabled = ENABLED; d.log = false; return d end, saveConfig = function() end }
dofile([[MOD]])
local function check(ok, what) if not ok then error(what, 2) end end
local function npc(script, context)
  local base = { objectType = 1, id = "someone", mesh = "base_anim.nif", script = script and { id = script } }
  return { reference = { object = { id = base.id, baseObject = base, objectType = 1 }, context = context } }
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
fire("uiActivated")
check(bard.state == 1 and stopped == 1, "the song stops and the script skips its frame")
for _ = 1, 3 do
  bard.state = 0                              -- what the script does when it skips
  fire("enterFrame")
  check(bard.state == 1, "it skips every frame of the dialogue")
end
fire("uiActivated")                           -- back from barter
check(#handlers.enterFrame == 1, "one frame handler, however often the dialogue shows")
fire("menuExit")
bard.state = 0
fire("enterFrame")
check(bard.state == 0 and #handlers.enterFrame == 0, "he sings again afterwards, and no frame handler is left")

fire("uiActivated")
bard.state = 0
fire("loaded")
fire("enterFrame")
check(bard.state == 0, "loading a save ends it")

local quest = { state = 5 }
speaker = npc("my_bard_quest", quest)
fire("uiActivated")
fire("enterFrame")
check(quest.state == 5, "another script's own 'state' is never written")
fire("menuExit")

stopped = 0
speaker = npc("guard_script", { state = 0, positiononce = 1 })
fire("uiActivated")
check(stopped == 0, "someone who doesn't perform is left alone")
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
mwse = { loadConfig = function(_, d) d.enabled = true; d.log = false; cfg = d; return d end, saveConfig = function() end }
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
