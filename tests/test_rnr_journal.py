"""mwpluginpatches: the Ruins'n'Relics Old Journal intercept (patches/ruinesRelicsJournal.lua).

The mod's onLoadJournal is swapped for ours when it registers (the luafix log shim on line 1 is left alone): the journal is never added by the mod and its message
never shows. The book is created once in the Seyda Neen Census and Excise Office (new game) or added silently (a
character already past chargen). Once it is in the inventory, or the done flag is already set on load, every listener
of ours comes off and the mod's original loaded handler is never put back. The mod is faked with a small stand-in
written for the test; nothing of its is copied.
"""
import os
import subprocess

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MOD = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwpluginpatches").replace("\\", "/")
SUITE = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite").replace("\\", "/")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

FAKE_RNR = r"""event.register("loaded", function() shimRan = (shimRan or 0) + 1 end)
local journalid = "rnr_old_journal"
local function onLoadJournal(e)
    modRan = (modRan or 0) + 1
    tes3.messageBox("You have been given an old adventurers journal.")
    mwscript.addItem({ reference = tes3.player, item = journalid, count = 1 })
end
modLoadedHandler = onLoadJournal
event.register("loaded", onLoadJournal)
event.register("unequipped", function() unequippedRan = (unequippedRan or 0) + 1 end)
"""
FAKE_OTHER = r"""event.register("loaded", function() otherRan = (otherRan or 0) + 1 end)
"""


@pytest.fixture()
def mods(tmp_path):
    root = tmp_path / "mods"
    for rel, text in (("Ruines'n'relics/main.lua", FAKE_RNR), ("someOtherMod/main.lua", FAKE_OTHER)):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return str(root).replace("\\", "/")


BOOT = r"""
local handlers, logs, boxes = {}, {}, {}
local function key(name, options)
  local filter = type(options) == "table" and options.filter or nil
  return tostring(name) .. "|" .. tostring(filter)
end
local function list(name, options) local k = key(name, options) handlers[k] = handlers[k] or {} return handlers[k] end
event = {
  register = function(name, fn, options)
    local l = list(name, options) for _, f in ipairs(l) do if f == fn then return end end l[#l + 1] = fn
  end,
  unregister = function(name, fn, options)
    local l = list(name, options) for i = #l, 1, -1 do if l[i] == fn then table.remove(l, i) end end
  end,
  isRegistered = function(name, fn, options)
    for _, f in ipairs(list(name, options)) do if f == fn then return true end end return false
  end,
}
function fire(name, e, options)
  e = e or {}
  local seen = {}
  local function run(l)
    for _, f in ipairs({ unpack(l) }) do if not seen[f] then seen[f] = true f(e) end end
  end
  if options ~= nil then
    run(list(name, options))
  else
    local prefix = tostring(name) .. "|"
    for k, l in pairs(handlers) do
      if k:sub(1, #prefix) == prefix then run(l) end
    end
  end
  return e
end
function count(name)
  local n, prefix = 0, tostring(name) .. "|"
  for k, l in pairs(handlers) do if k:sub(1, #prefix) == prefix then n = n + #l end end
  return n
end
mwse = { log = function(fmt, ...) logs[#logs + 1] = string.format(fmt, ...) end }
function logged(text) for _, l in ipairs(logs) do if l:find(text, 1, true) then return true end end return false end
mwscript = { addItem = function() mwscriptAdds = (mwscriptAdds or 0) + 1 end }
local ITEM_PRESENT = @@ITEM@@
created, added, worldRefs = {}, {}, {}
world = { createFails = false }
inventory = 0
globals = { CharGenState = { value = 10 } }
playerCell = { id = "Seyda Neen, Docks" }
tes3 = { event = setmetatable({}, { __index = function(_, k) return k end }), objectType = { book = "book" } }
tes3.player = { data = {} }
tes3.messageBox = function(first, ...) boxes[#boxes + 1] = type(first) == "table" and first.message or string.format(first, ...) end
tes3.findGlobal = function(id) return globals[id] end
tes3.getObject = function(id) if ITEM_PRESENT and id == "rnr_old_journal" then return { id = id } end end
tes3.getItemCount = function(p) return inventory end
tes3.getPlayerCell = function() return playerCell end
tes3.addItem = function(p) added[#added + 1] = p inventory = inventory + p.count return p.count end
tes3.getCell = function(p)
  local id = type(p) == "table" and p.id or p
  return {
    id = id,
    iterateReferences = function(self, typ)
      local list, i = worldRefs[id] or {}, 0
      return function()
        i = i + 1
        local r = list[i]
        while r and typ and r.kind and r.kind ~= typ do i = i + 1 r = list[i] end
        return r
      end
    end,
  }
end
tes3.createReference = function(p)
  if world.createFails then error("cell is not loaded") end
  local cellId = type(p.cell) == "table" and p.cell.id or p.cell
  local ref = { id = p.object, object = { id = p.object }, kind = "book", params = p, deleted = false, disabled = false }
  function ref:delete()
    self.deleted = true
    for _, list in pairs(worldRefs) do
      for i = #list, 1, -1 do if list[i] == self then table.remove(list, i) end end
    end
  end
  created[#created + 1] = ref
  worldRefs[cellId] = worldRefs[cellId] or {}
  worldRefs[cellId][#worldRefs[cellId] + 1] = ref
  return ref
end
tes3.setEnabled = function(p) if p.reference then p.reference.disabled = p.enabled == false end end
local config = setmetatable({
  enabled = true, ruinesRelicsJournalEnabled = @@FLAG@@,
  isRuinesRelicsInstalled = function() return @@INSTALLED@@ end,
}, { __index = function(_, k) if type(k) == "string" and k:match("^is") then return function() return false end end end })
table.insert(package.loaders, 2, function(name)
  if name == "mwpluginpatches.config" then return function() return config end end
  if name == "mwpluginpatches.intercept" then return assert(loadfile("@@MOD@@/intercept.lua")) end
  if name == "mwpluginpatches.patches.ruinesRelicsJournal" then return assert(loadfile("@@MOD@@/patches/ruinesRelicsJournal.lua")) end
end)
local patch = require("mwpluginpatches.patches.ruinesRelicsJournal")
local function load(rel) assert(loadfile("@@MODS@@/" .. rel))() end
local function newCharacter()
  tes3.player = { data = {} }
  inventory, created, added, worldRefs = 0, {}, {}, {}
  playerCell = { id = "Seyda Neen, Docks" }
end
local function ourListeners()
  local n = count("cellChanged") + count("activate")
  if event.isRegistered("loaded", patch.ourLoaded) then n = n + 1 end
  return n
end
"""


def run(script, mods, flag=True, installed=True, item=True):
    script = BOOT + script
    for key, value in (("@@MODS@@", mods), ("@@MOD@@", MOD), ("@@FLAG@@", str(flag).lower()),
                       ("@@INSTALLED@@", str(installed).lower()), ("@@ITEM@@", str(item).lower())):
        script = script.replace(key, value)
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stdout + out.stderr


def test_new_game_places_the_journal_and_the_mod_never_runs(mods):
    run(r"""
assert(patch.init() == true)
load("Ruines'n'relics/main.lua") load("someOtherMod/main.lua")
fire("loaded", { newGame = true })
assert(modRan == nil, "the mod's own handler ran")
assert(#boxes == 0, "a message box was shown")
assert(mwscriptAdds == nil and #added == 0, "the journal went into the inventory")
assert(#created == 1)
local p = created[1].params
assert(p.object == "rnr_old_journal" and p.cell == "Seyda Neen, Census and Excise Office")
assert(p.position[1] == 145 and p.position[2] == -228 and p.position[3] == 263.9)
assert(p.orientation[1] == 0 and p.orientation[2] == 0 and math.abs(p.orientation[3] - math.pi / 2) < 1e-4)
assert(p.scale == 0.8)
assert(tes3.player.data.mwsuite_rnrJournalPlaced == nil, "the done flag must wait until the book is picked up")
assert(count("loaded") == 3, "the log shim, our wrapper and the other mod's handler")
assert(shimRan == 1, "the luafix log shim must still run")
assert(count("activate") == 1 and count("cellChanged") == 1)
assert(otherRan == 1, "another mod's loaded handler must still run")
print("ok")
""", mods)


def test_the_mods_own_unregister_and_is_registered_still_work(mods):
    run(r"""
assert(patch.init() == true)
load("Ruines'n'relics/main.lua")
assert(event.isRegistered("loaded", modLoadedHandler) == true)
event.unregister("loaded", modLoadedHandler)
assert(event.isRegistered("loaded", modLoadedHandler) == false)
assert(count("loaded") == 1, "the log shim stays registered")
print("ok")
""", mods)


def test_its_other_handlers_are_left_alone(mods):
    run(r"""
assert(patch.init() == true)
load("Ruines'n'relics/main.lua")
fire("unequipped", {})
assert(unequippedRan == 1)
print("ok")
""", mods)


def test_placed_once_and_reload_does_not_create_a_second_copy(mods):
    run(r"""
assert(patch.init() == true)
load("Ruines'n'relics/main.lua")
fire("loaded", { newGame = true })
fire("loaded", { newGame = false })
fire("loaded", { newGame = true })
assert(#created == 1 and #added == 0)
assert(tes3.player.data.mwsuite_rnrJournalPlaced == nil)
assert(count("activate") == 1)
print("ok")
""", mods)


def test_pickup_unloads_every_listener_and_never_restores_the_original(mods):
    run(r"""
assert(patch.init() == true)
load("Ruines'n'relics/main.lua") load("someOtherMod/main.lua")
fire("loaded", { newGame = true })
assert(count("activate") == 1 and count("loaded") == 3)
assert(event.isRegistered("activate", patch.onActivate, { filter = "rnr_old_journal" }) == true)
inventory = 1
fire("activate", { target = created[1] }, { filter = "rnr_old_journal" })
assert(tes3.player.data.mwsuite_rnrJournalPlaced == true)
assert(count("activate") == 0 and count("cellChanged") == 0)
assert(event.isRegistered("loaded", modLoadedHandler) == false)
assert(event.isRegistered("loaded", patch.ourLoaded) == false)
assert(count("loaded") == 2, "the log shim and the other mod's loaded handler should remain")
assert(shimRan == 1)
assert(#boxes == 0 and modRan == nil)
fire("loaded", { newGame = true })   -- a second new game in this session: we stay unloaded
assert(#created == 1 and #added == 0 and otherRan == 2 and shimRan == 2 and modRan == nil)
print("ok")
""", mods)


def test_character_past_chargen_gets_it_silently_and_unloads(mods):
    run(r"""
assert(patch.init() == true)
load("Ruines'n'relics/main.lua")
globals.CharGenState.value = -1
fire("loaded", { newGame = false })
assert(#created == 0 and #boxes == 0 and modRan == nil)
assert(#added == 1 and added[1].item == "rnr_old_journal" and added[1].count == 1 and added[1].playSound == false)
assert(tes3.player.data.mwsuite_rnrJournalPlaced == true)
assert(ourListeners() == 0)
assert(event.isRegistered("loaded", modLoadedHandler) == false)
fire("loaded", { newGame = false })
assert(#added == 1)
print("ok")
""", mods)


def test_chargen_still_pending_on_a_loaded_save_places_it_in_the_office(mods):
    run(r"""
assert(patch.init() == true)
load("Ruines'n'relics/main.lua")
fire("loaded", { newGame = false })   -- CharGenState is 10: character creation is not over
assert(#created == 1 and #added == 0)
assert(tes3.player.data.mwsuite_rnrJournalPlaced == nil)
assert(count("activate") == 1)
print("ok")
""", mods)


def test_a_journal_already_held_or_flagged_by_the_mod_unloads_without_a_duplicate(mods):
    run(r"""
assert(patch.init() == true)
load("Ruines'n'relics/main.lua")
inventory = 1
fire("loaded", { newGame = false })
assert(#created == 0 and #added == 0 and tes3.player.data.mwsuite_rnrJournalPlaced == true)
assert(ourListeners() == 0)
newCharacter()
tes3.player.data.journalid = { doOnce = true }   -- the mod's own old flag
fire("loaded", { newGame = true })               -- already unloaded this session
assert(#created == 0 and #added == 0)
print("ok")
""", mods)


def test_when_the_cell_cannot_be_filled_yet_it_waits_then_watches_pickup(mods):
    run(r"""
assert(patch.init() == true)
load("Ruines'n'relics/main.lua")
world.createFails = true
fire("loaded", { newGame = true })
assert(#created == 0 and count("cellChanged") == 1)
assert(tes3.player.data.mwsuite_rnrJournalPlaced == nil)
fire("cellChanged", {})                  -- still on the docks
assert(#created == 0 and count("cellChanged") == 1)
world.createFails = false
playerCell = { id = "Seyda Neen, Census and Excise Office" }
fire("cellChanged", {})
assert(#created == 1 and created[1].params.cell == playerCell)
assert(tes3.player.data.mwsuite_rnrJournalPlaced == nil)
assert(count("cellChanged") == 1, "cellChanged stays as a pickup check")
assert(count("activate") == 1 and event.isRegistered("loaded", patch.ourLoaded) == true)
assert(#boxes == 0 and modRan == nil)
inventory = 1
fire("activate", { target = created[1] }, { filter = "rnr_old_journal" })
assert(tes3.player.data.mwsuite_rnrJournalPlaced == true)
assert(ourListeners() == 0)
print("ok")
""", mods)


def test_leaving_the_office_with_the_book_unloads(mods):
    run(r"""
assert(patch.init() == true)
load("Ruines'n'relics/main.lua")
fire("loaded", { newGame = true })
inventory = 1
playerCell = { id = "Seyda Neen, Docks" }
fire("cellChanged", {})
assert(tes3.player.data.mwsuite_rnrJournalPlaced == true)
assert(count("activate") == 0 and event.isRegistered("loaded", patch.ourLoaded) == false)
print("ok")
""", mods)


def test_a_new_game_before_unload_still_places_for_the_new_character(mods):
    run(r"""
assert(patch.init() == true)
load("Ruines'n'relics/main.lua")
world.createFails = true
fire("loaded", { newGame = true })
assert(count("cellChanged") == 1)
newCharacter()
world.createFails = false
fire("loaded", { newGame = true })
assert(count("cellChanged") == 1 and #created == 1)
assert(tes3.player.data.mwsuite_rnrJournalPlaced == nil)
print("ok")
""", mods)


def test_toggle_off_leaves_the_mod_as_it_is(mods):
    run(r"""
assert(patch.init() == false)
load("Ruines'n'relics/main.lua")
fire("loaded", { newGame = true })
assert(modRan == 1 and #boxes == 1 and #created == 0)
assert(event.isRegistered("loaded", modLoadedHandler) == true)
print("ok")
""", mods, flag=False)


def test_mod_not_installed_does_nothing(mods):
    run(r"""
assert(patch.init() == false)
assert(count("loaded") == 0 and #logs == 0)
print("ok")
""", mods, installed=False)


def test_item_missing_from_the_load_order_stands_down_without_a_message(mods):
    run(r"""
assert(patch.init() == true)
load("Ruines'n'relics/main.lua")
fire("loaded", { newGame = true })
assert(modRan == nil and #boxes == 0 and #created == 0 and #added == 0)
assert(tes3.player.data.mwsuite_rnrJournalPlaced == nil)
assert(logged("rnr_old_journal is not in the load order"))
assert(event.isRegistered("loaded", modLoadedHandler) == false)
assert(ourListeners() == 0)
fire("loaded", { newGame = true })
assert(#created == 0 and modRan == nil)
print("ok")
""", mods, item=False)


def test_a_failure_in_the_placement_is_logged_not_raised(mods):
    run(r"""
assert(patch.init() == true)
load("Ruines'n'relics/main.lua")
tes3.findGlobal = function() error("boom") end
tes3.getObject = function() error("boom") end
fire("loaded", { newGame = true })
assert(logged("raised an error") and #boxes == 0 and modRan == nil)
print("ok")
""", mods)


def test_a_handler_from_another_file_is_not_replaced(mods):
    run(r"""
assert(patch.init() == true)
event.register("loaded", function() directRan = true end)   -- registered from this chunk, not from the mod's file
load("someOtherMod/main.lua")
fire("loaded", { newGame = true })
assert(directRan == true and otherRan == 1)
print("ok")
""", mods)


def test_the_log_shim_is_not_wrapped_and_the_journal_is_placed_once(mods):
    run(r"""
assert(patch.init() == true)
load("Ruines'n'relics/main.lua")
fire("loaded", { newGame = true })
assert(shimRan == 1 and modRan == nil and #created == 1)
local n = 0
for _, l in ipairs(logs) do if l:find("the Old Journal is on the table", 1, true) then n = n + 1 end end
assert(n == 1, "claimed placement more than once")
worldRefs = {}
fire("loaded", { newGame = true })
assert(#created == 1)
n = 0
for _, l in ipairs(logs) do if l:find("the Old Journal is on the table", 1, true) then n = n + 1 end end
assert(n == 1)
print("ok")
""", mods)


def test_pickup_deletes_a_leftover_world_copy(mods):
    run(r"""
assert(patch.init() == true)
load("Ruines'n'relics/main.lua")
fire("loaded", { newGame = true })
local extra = tes3.createReference({
    object = "rnr_old_journal", cell = "Seyda Neen, Census and Excise Office",
    position = { 145, -228, 263.9 }, orientation = { 0, 0, 1.5707964 }, scale = 0.8,
})
assert(#created == 2)
inventory = 1
created[1]:delete()
fire("activate", { target = created[1] }, { filter = "rnr_old_journal" })
assert(tes3.player.data.mwsuite_rnrJournalPlaced == true)
assert(extra.deleted == true, "the leftover world copy was not removed")
assert(ourListeners() == 0)
print("ok")
""", mods)


def test_defaults_on_only_when_the_mod_is_installed(tmp_path):
    script = r"""
package.path = [[SUITE/?.lua;]] .. package.path
local present = false
lfs = { fileexists = function(path)
    return path:gsub("\\", "/") == "Data Files/MWSE/mods/Ruines'n'relics/main.lua" and present or false end }
mwse = { loadConfig = function() return nil end, saveConfig = function() end, log = function() end }
tes3 = setmetatable({}, { __index = function() return function() return nil end end })
package.loaded["mwpluginpatches.config"] = nil
local off = require("mwpluginpatches.config")
assert(not off.ruinesRelicsJournalEnabled and off.isRuinesRelicsInstalled() == false)
package.loaded["mwpluginpatches.config"] = nil
present = true
local on = require("mwpluginpatches.config")
assert(on.ruinesRelicsJournalEnabled == true and on.isRuinesRelicsInstalled() == true)
print("ok")
""".replace("SUITE", SUITE)
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=str(tmp_path))
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stdout + out.stderr


def test_wired_into_main_mcm_and_metadata():
    def read(*parts):
        with open(os.path.join(*parts), encoding="utf-8") as f:
            return f.read()
    main = read(MOD, "main.lua")
    assert 'require("mwpluginpatches.patches.ruinesRelicsJournal")' in main and "ruinesRelicsJournal }" in main
    assert 'id = "ruinesRelicsJournalEnabled"' in read(MOD, "mcm.lua")
    assert "Old Journal" in read(ROOT, "lua tools", "mwpluginpatches-metadata.toml")


def test_files_are_utf8_lf_without_bom():
    for rel in ("patches/ruinesRelicsJournal.lua", "config.lua", "main.lua", "mcm.lua"):
        with open(os.path.join(MOD, rel), "rb") as f:
            data = f.read()
        assert not data.startswith(b"\xef\xbb\xbf") and b"\r\n" not in data, rel
        data.decode("utf-8")
    with open(os.path.join(ROOT, "lua tools", "mwpluginpatches-metadata.toml"), "rb") as f:
        data = f.read()
    assert not data.startswith(b"\xef\xbb\xbf") and b"\r\n" not in data