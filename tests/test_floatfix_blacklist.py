"""mwfloatfix's hide key on an object that is already listed replaces the old entry and hides it again (it used to
refuse: "already on the blacklist", with the object showing), and mwpluginpatches no longer has a hardcoded
trapdoor fix switching a hidden object back on."""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
SUITE = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite")

SCRIPT = r"""
local handlers, saved, prompt, shown = {}, nil, nil, nil
local KEY = "seyda neen, arrille's tradehouse|dim_com_m_trapdoor_b|-566|-435|512"
local list = { entries = {
  { key = KEY, id = "dim_com_m_trapdoor_b", mod = "old.esp", added = "2026-11-19 20:54" },
  { key = "other|rope|1|2|3", id = "rope", mod = "Squat.esp", added = "2026-11-09 23:00" },
  { key = KEY, id = "DIM_com_m_trapdoor_b", mod = "older.esp", added = "2026-11-01 10:00" },
} }
event = { register = function(name, fn)
  handlers[name] = handlers[name] or {}
  table.insert(handlers[name], fn)
end,
  unregister = function(name, fn)
    for i = #(handlers[name] or {}), 1, -1 do if handlers[name][i] == fn then table.remove(handlers[name], i) end end
  end,
  isRegistered = function(name, fn)
    for _, h in ipairs(handlers[name] or {}) do if h == fn then return true end end
    return false
  end }
timer = { real = 1, delayOneFrame = function(f) f() end }
local function fire(name, e) for _, fn in ipairs(handlers[name] or {}) do fn(e) end end
local cell = { isInterior = true, id = "Seyda Neen, Arrille's Tradehouse", editorName = "Arrille's" }
local pos = { x = -566.2, y = -434.8, z = 512 }
local ref = { object = { id = "dim_com_m_trapdoor_b", objectType = 20, name = "Trap Door" }, cell = cell,
              position = pos, startingPosition = pos, sourceMod = "Squat.esp", disabled = false }
function ref:disable() self.disabled = true end
function ref:enable() self.disabled = false end
function cell:iterateReferences()
  local done = false
  return function() if not done then done = true; return ref end end
end
tes3 = { objectType = setmetatable({ npc = 14, creature = 15 }, { __index = function(_, k) return k end }),
         scanCode = { delete = 211 }, event = setmetatable({}, { __index = function(_, k) return k end }),
         player = { data = {} }, getActiveCells = function() return { cell } end, getObject = function() end,
         messageBox = function(p) if type(p) == "table" then prompt = p else shown = p end end }
tes3ui = { findMenu = function() return { visible = true } end }
tes3vector3 = { new = function(x, y, z) return { x = x, y = y, z = z } end }
mwse = { log = function() end, saveConfig = function(name, value) if name == "mwfloatfix_blacklist" then saved = value end end,
         loadConfig = function(name, defaults)
           if name == "mwfloatfix" then defaults.enabled = true; defaults.log = false end
           if name == "mwfloatfix_blacklist" then return list end
           return defaults
         end }
dofile([[MOD]])
local function check(ok, what) if not ok then error(what, 2) end end

fire("consoleReferenceChanged", { reference = ref })
fire("keyDown", { keyCode = 211, isShiftDown = true })
check(prompt and prompt.callback, "asks before hiding")
prompt.callback({ button = 0 })
check(ref.disabled, "hidden again")
check(saved and #saved.entries == 2, "every older entry for it is replaced")
check(saved.entries[1].id == "rope", "other entries are kept")
check(saved.entries[2].key == KEY and saved.entries[2].mod == "Squat.esp"
      and saved.entries[2].added ~= "2026-11-19 20:54", "the new entry is the last one")
ref.disabled = false
fire("loaded", {})
check(ref.disabled, "hidden when a save has it switched on")
print("ok")
"""


@pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")
def test_hiding_a_listed_object_again_replaces_its_entry():
    script = SCRIPT.replace("[[MOD]]", "[[" + os.path.join(SUITE, "mwfloatfix", "main.lua") + "]]")
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stderr + out.stdout


def test_no_plugin_patch_names_the_arrille_trapdoor():
    found = []
    for base, _dirs, files in os.walk(os.path.join(SUITE, "mwpluginpatches")):
        for name in files:
            if name.endswith(".lua"):
                with open(os.path.join(base, name), encoding="utf-8") as f:
                    text = f.read().lower()
                if "dim_com_m_trapdoor_b" in text or "arrilleinndoors" in text:
                    found.append(name)
    assert not found, found
