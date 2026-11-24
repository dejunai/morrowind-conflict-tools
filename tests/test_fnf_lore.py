"""Friends & Frens' converted vanilla NPCs get their generic dialogue back, and nobody else does."""
import os
import subprocess

import pytest

from conftest import plugin, rec, sub, z

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MOD = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwpluginpatches").replace("\\", "/")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

SCRIPT = r"""
local function engine(t, newindex)          -- engine objects are userdata
  local u = newproxy(true); local mt = getmetatable(u); mt.__index = t; mt.__newindex = newindex; return u end
local handlers = {}
event = { register = function(n, f) handlers[n] = f end }
mwse = { log = function() end }
local vars = { localstate = { "state" }, nolore = { "NoLore" }, aa_partnerstealth = { "nolore" }, ["other"] = { "nolore" } }
local function script(id)
  return engine({ id = id, getVariableData = function()
    local out = {} for _, name in ipairs(vars[id:lower()]) do out[name] = { value = 0 } end return out end })
end
tes3 = { event = setmetatable({}, { __index = function(_, k) return k end }), objectType = { npc = 1, door = 2 },
  getScript = function(id) return vars[id:lower()] and script(id) or nil end }
local config = setmetatable({ enabled = true, friendsAndFrensLoreEnabled = ENABLED, isFriendsAndFrensActive = function() return true end },
  { __index = function(_, k) if k:match("^is") then return function() return false end end end })
table.insert(package.loaders, 2, function(name)
  if name == "mwpluginpatches.config" then return function() return config end end
  if name == "mwpluginpatches.patches.friendsAndFrensLore" then return assert(loadfile("MOD/patches/friendsAndFrensLore.lua")) end
  if name:match("^mwpluginpatches%.patches%.") then return function() return { init = function() end } end end
end)
assert(loadfile("MOD/main.lua"))()
handlers.initialized()
local function npc(id, scriptId, value)
  local saved = { nolore = value or 0 }
  local context = engine(saved, function(_, k, v) saved[k] = v end)
  local fields = { baseObject = engine({ id = id, objectType = 1, script = script(scriptId) }), context = context }
  return engine(fields, function(_, k, v) fields[k] = v end), saved, fields
end
local function nolore(id, scriptId, value, how)
  local ref, saved, fields = npc(id, scriptId, value)
  if handlers.mobileActivated then
    if how == "talk" then handlers.activate({ target = ref }) else handlers.mobileActivated({ reference = ref }) end
  end
  return saved.nolore, fields.modified
end
local value, modified = nolore("Fargoth", "aa_partnerStealth")
if ENABLED then
  assert(value == 1 and modified, "converted, had a script without nolore")
  assert(nolore("Okur", "aa_partnerStealth") == 1, "converted, had no script")
  assert(nolore("Fargoth", "aa_partnerStealth", 0, "talk") == 1, "also on talking")
  assert(nolore("Umbra", "aa_partnerStealth") == 0, "was meant to have no lore")
  assert(nolore("Gone", "aa_partnerStealth") == 0, "its vanilla script can't be found")
  assert(nolore("aa_comp_jiub", "aa_partnerStealth") == 0, "the mod's own companion")
  assert(nolore("Fargoth", "other") == 0, "some other mod's script")
  local v, touched = nolore("Fargoth", "aa_partnerStealth", 5)
  assert(v == 5 and not touched, "a value someone set")
  handlers.activate({ target = engine({ baseObject = engine({ id = "door", objectType = 2 }) }) })
  handlers.mobileActivated({ reference = engine({ baseObject = engine({ id = "Fargoth", objectType = 1, script = script("aa_partnerStealth") }) }) })
else
  assert(value == 0 and not modified, "switched off")
end
"""


@pytest.mark.parametrize("enabled", [True, False])
def test_only_converted_vanilla_npcs_get_their_lore_back(tmp_path, enabled):
    def npc(id_, script=None):
        return rec("NPC_", sub("NAME", z(id_)) + (sub("SCRI", z(script)) if script else b""))

    data = tmp_path / "Data Files"
    data.mkdir()
    plugin(data / "Morrowind.esm", [], [npc("fargoth", "LocalState"), rec("MISC", sub("NAME", z("padding"))),
                                       npc("okur"), npc("umbra"), npc("gone", "missing_script")])
    plugin(data / "Tribunal.esm", [], [npc("umbra", "NoLore")])          # the last vanilla master decides
    script = SCRIPT.replace("MOD", MOD).replace("ENABLED", str(enabled).lower())
    got = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=tmp_path)
    assert got.returncode == 0, got.stderr
