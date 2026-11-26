"""mwpluginpatches and mwinfoloop: one-shot intercepts come off once their job is done (nothing stays resident).

Party Alchemy's module message, Watch the Skies' metadata guard, Mabrigash Distribution's popup, AutoStartup's
setup hooks, Trainer Log's topic hook, Personal Effects' office timer and mwinfoloop's startup-check hooks.
The target mods are faked with small stand-ins; nothing of theirs is copied.
"""
import os
import subprocess

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
SUITE = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite").replace("\\", "/")
MOD = SUITE + "/mwpluginpatches"
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

BOOT = r"""
local lists, logs, boxes = {}, {}, {}
local function key(n, o) return tostring(n) .. "|" .. tostring(type(o) == "table" and o.filter or "") end
local function list(n, o) local k = key(n, o) lists[k] = lists[k] or {} return lists[k] end
event = {
  register = function(n, fn, o) local l = list(n, o) for _, h in ipairs(l) do if h.fn == fn then return end end
    l[#l + 1] = { fn = fn, priority = type(o) == "table" and o.priority or 0 }
    table.sort(l, function(a, b) return a.priority > b.priority end) end,
  unregister = function(n, fn, o) local l = list(n, o) for i = #l, 1, -1 do if l[i].fn == fn then table.remove(l, i) end end end,
  isRegistered = function(n, fn, o) for _, h in ipairs(list(n, o)) do if h.fn == fn then return true end end return false end,
}
function fire(n, e, o) e = e or {} for _, h in ipairs({ unpack(list(n, o)) }) do h.fn(e) end return e end
function count(n, o) return #list(n, o) end
mwse = { log = function(fmt, ...) logs[#logs + 1] = string.format(fmt, ...) end }
globals = {}
tes3 = {
  event = setmetatable({}, { __index = function(_, k) return k end }),
  findGlobal = function(id) return globals[id] end,
}
tes3.messageBox = function(first, ...)
  local text = type(first) == "table" and first.message or string.format(first, ...)
  boxes[#boxes + 1] = text
  return "box"
end
nativeBox = tes3.messageBox
timers = {}
timer = { real = "real", simulate = "simulate",
  start = function(p) local t = { p = p, cancelled = false } t.cancel = function() t.cancelled = true end timers[#timers + 1] = t return t end }
cfg = setmetatable({ enabled = true }, { __index = function(_, k) if type(k) == "string" and k:match("^is") then return function() return true end end end })
table.insert(package.loaders, 2, function(name)
  if name == "mwpluginpatches.config" then return function() return cfg end end
  if name == "mwpluginpatches.intercept" then return assert(loadfile("MOD/intercept.lua")) end
  local p = name:match("^mwpluginpatches%.patches%.(.+)$")
  if p then return assert(loadfile("MOD/patches/" .. p .. ".lua")) end
end)
package.path = "MODS/?.lua;" .. package.path
function joined(t) return table.concat(t, "|") end
"""


def run(script, mods=""):
    script = (BOOT + script).replace("MODS", mods).replace("MOD/", MOD + "/").replace("SUITE", SUITE)
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stdout + out.stderr


@pytest.fixture()
def mods(tmp_path):
    root = tmp_path / "mods"
    for rel, text in (
        ("partyAlchemy/main.lua", 'function paInit() tes3.messageBox("Switched to module: [%s]", "Vanilla") end\n'
                                  'event.register(tes3.event.initialized, paInit)\n'),
        ("tew/Watch the Skies/util.lua", 'local util = {}\nfunction util.metadataMissing() error("stand-in") end\nreturn util\n'),
    ):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return str(root).replace("\\", "/")


def test_party_alchemy_message_rule_comes_off_after_initialized(mods):
    run(r"""
cfg.partyAlchemyModuleBoxEnabled = true
local patch = require("mwpluginpatches.patches.partyAlchemyModuleBox")
assert(patch.init() == true)
assert(tes3.messageBox ~= nativeBox)
assert(loadfile("MODS/partyAlchemy/main.lua"))()
fire("initialized")
assert(#boxes == 0, "held back during initialized: " .. joined(boxes))
assert(tes3.messageBox == nativeBox, "messageBox is put back once initialized is over")
paInit()
assert(boxes[1] == "Switched to module: [Vanilla]", "after initialized nothing is held back")
print("ok")
""", mods)


def test_party_alchemy_rule_leaves_a_later_messagebox_wrapper_alone(mods):
    run(r"""
cfg.partyAlchemyModuleBoxEnabled = true
local patch = require("mwpluginpatches.patches.partyAlchemyModuleBox")
assert(patch.init())
local ours = tes3.messageBox
local later = function(...) return ours(...) end
tes3.messageBox = later
fire("initialized")
assert(tes3.messageBox == later, "a wrapper put on after ours is kept")
assert(loadfile("MODS/partyAlchemy/main.lua"))()
paInit()
assert(boxes[1] == "Switched to module: [Vanilla]", "ours is now a pass-through")
print("ok")
""", mods)


def test_party_alchemy_keeps_other_drop_rules(mods):
    run(r"""
cfg.partyAlchemyModuleBoxEnabled = true
local intercept = require("mwpluginpatches.intercept")
local other = { label = "x", source = "/stdin", prefix = "keep me hidden" }
assert(intercept.messageBoxDrop(other))
local patch = require("mwpluginpatches.patches.partyAlchemyModuleBox")
assert(patch.init())
fire("initialized")
assert(tes3.messageBox ~= nativeBox, "another rule still needs the wrapper")
print("ok")
""", mods)


def test_wts_guard_comes_off_after_initialized(mods):
    run(r"""
cfg.wtsMetadataLogEnabled = true
local patch = require("mwpluginpatches.patches.wtsMetadataLog")
assert(patch.init() == true)
local util = require("tew.Watch the Skies.util")
assert(pcall(util.metadataMissing), "guarded while the game starts")
local loaders = package.loaders or package.searchers
local n = #loaders
fire("initialized")
assert(not pcall(util.metadataMissing), "the mod's own function is back after initialized")
assert(#loaders == n - 1, "the searcher is gone too")
print("ok")
""", mods)


def test_wts_guard_left_in_place_when_replaced_by_someone_else(mods):
    run(r"""
cfg.wtsMetadataLogEnabled = true
local patch = require("mwpluginpatches.patches.wtsMetadataLog")
assert(patch.init())
local util = require("tew.Watch the Skies.util")
local theirs = function() return "theirs" end
util.metadataMissing = theirs
fire("initialized")
assert(util.metadataMissing == theirs, "a function put there after us is not replaced")
print("ok")
""", mods)


def test_mabrigash_popup_hooks_arm_only_until_the_popup_is_held_back():
    run(r"""
cfg.mabrDistSuppressionEnabled = true
tes3ui = { registerID = function(id) return id end }
local patch = require("mwpluginpatches.patches.mabrDist")
assert(patch.init() == true)
assert(count("uiActivated", { filter = "MenuMessage" }) == 0 and count("loaded") == 1, "nothing before a load")
globals.gv_mabrDist = { value = 1 }
tes3.player = {}
fire("loaded")
assert(count("uiActivated", { filter = "MenuMessage" }) == 0, "already distributed: not armed")
globals.gv_mabrDist = { value = 0 }
fire("loaded")
for i = 1, 3 do assert(count("uiActivated", { filter = "MenuNotify" .. i }) == 1) end
assert(count("uiActivated", { filter = "MenuMessage" }) == 1)
-- an unrelated popup leaves it armed
local other = { text = "hello", findChild = function() return nil end, children = {}, destroy = function() end }
fire("uiActivated", { element = other }, { filter = "MenuMessage" })
assert(count("uiActivated", { filter = "MenuMessage" }) == 1)
-- the distribution popup: held back, then the handlers come off
local destroyed = false
local menu = { text = "Distributing Mabrigash helmets", findChild = function() return nil end, children = {},
  destroy = function() destroyed = true end }
local e = fire("uiActivated", { element = menu }, { filter = "MenuMessage" })
assert(destroyed and e.claim == true, "the popup is held back")
for i = 1, 3 do assert(count("uiActivated", { filter = "MenuNotify" .. i }) == 0) end
assert(count("uiActivated", { filter = "MenuMessage" }) == 0)
assert(count("loaded") == 1, "the loaded hook stays")
print("ok")
""")


def test_autostartup_hooks_only_while_setup_is_pending():
    run(r"""
cfg.mcaEnabled, cfg.euEnabled, cfg.mcaPartySize = true, true, 0
cfg.isMcaActive = function() return true end
cfg.isEbonheartUnderworksActive = function() return true end
tes3.addTopic = function() end
tes3ui = { registerID = function(id) return id end }
mwscript = { stopScript = function() end }
tes3.runLegacyScript = function() end
local startup = require("mwpluginpatches.patches.autoStartup")
startup.init()
assert(count("uiActivated", { filter = "MenuMessage" }) == 0 and count("cellChanged") == 0, "nothing before a load")
-- a save with both set up already
globals.MCA_Loaded = { value = 1 }
globals.MCA_MoreEnemies = { value = 0 }
globals.dd19rebirthConfig = { value = 1 }
fire("loaded")
assert(not startup.isArmed() and count("cellChanged") == 0, "set-up save: not armed")
-- a new game: Ebonheart Underworks still asks, MCA is answered on load
globals.MCA_Loaded = { value = 0 }
globals.dd19rebirthConfig = { value = 0 }
fire("loaded")
assert(globals.MCA_Loaded.value == 1 and globals.dd19rebirthConfig.value == 1, "applied on load")
assert(not startup.isArmed(), "both done on load: not armed")
-- a save whose EU global can't be set yet (no global): still armed until it appears and is applied
globals.dd19rebirthConfig = nil
globals.MCA_Loaded = { value = 1 }
globals.MCA_MoreEnemies = { value = 3 }
cfg.mcaPartySize = 2
local applied = 0
local real = startup.applyStartupConfig
startup.applyStartupConfig = function() applied = applied + 1 end
fire("loaded")
assert(startup.isArmed() and count("cellChanged") == 1 and count("uiActivated", { filter = "MenuMessage" }) == 1,
  "party size 3 still to repair: armed")
startup.applyStartupConfig = real
fire("cellChanged")
assert(globals.MCA_MoreEnemies.value == 2, "repaired")
assert(not startup.isArmed() and count("cellChanged") == 0 and count("uiActivated", { filter = "MenuMessage" }) == 0,
  "handlers off once done")
assert(count("loaded") == 1)
print("ok")
""")


def test_trainer_log_dialog_hook_comes_off_once_the_topics_are_added():
    run(r"""
cfg.trainerLogUnlockEnabled = true
cfg.trainerLogAutoUnlockOnLoad = false
local added = 0
tes3.addTopic = function() added = added + 1 end
local actor
tes3ui = { registerID = function(id) return id end, getServiceActor = function() return actor end }
local patch = require("mwpluginpatches.patches.trainerLogUnlock")
patch.init()
assert(not patch.dialogHooked(), "nothing before a load")
assert(count("uiActivated", { filter = "MenuServiceTraining" }) == 1, "icon scaling stays")
fire("loaded")
assert(patch.dialogHooked() and count("uiActivated", { filter = "MenuDialog" }) == 1)
actor = { reference = { baseObject = { aiConfig = { offersTraining = false } } } }
fire("uiActivated", {}, { filter = "MenuDialog" })
assert(added == 0 and patch.dialogHooked(), "not a trainer: still waiting")
actor = { reference = { baseObject = { aiConfig = { offersTraining = true } } } }
fire("uiActivated", {}, { filter = "MenuDialog" })
assert(added == 27 and not patch.dialogHooked() and count("uiActivated", { filter = "MenuDialog" }) == 0)
cfg.trainerLogAutoUnlockOnLoad = true
fire("loaded")
assert(added == 54 and not patch.dialogHooked(), "added on load: the dialog hook is not registered")
assert(count("uiActivated", { filter = "MenuServiceTraining" }) == 1)
print("ok")
""")


def test_personal_effects_timer_runs_only_in_the_census_office():
    run(r"""
cfg.personalEffectsEnabled = true
cfg.isPersonalEffectsActive = function() return true end
mwse.overrideScript = function() end
mwscript = { stopScript = function() end }
tes3.uiEvent = { destroy = "destroy" }
tes3.getReference = function() return nil end
timer.frame = { delayOneFrame = function() end }
local patch = require("mwpluginpatches.patches.personalEffects")
patch.init()
assert(#timers == 0, "no timer at initialized")
tes3.player = { cell = { id = "Balmora" } }
fire("loaded")
assert(not patch.backgroundRunning(), "not in the office: no background timer")
tes3.player.cell = { id = "Seyda Neen, Census and Excise Office" }
fire("cellChanged")
assert(patch.backgroundRunning())
local bg
for _, t in ipairs(timers) do if t.p.iterations == -1 then bg = t end end
assert(bg, "a repeating timer")
fire("cellChanged")
local n = 0
for _, t in ipairs(timers) do if t.p.iterations == -1 then n = n + 1 end end
assert(n == 1, "one timer, not one per cell change")
tes3.player.cell = { id = "Seyda Neen" }
fire("cellChanged")
assert(not patch.backgroundRunning() and bg.cancelled, "cancelled once the player has left")
print("ok")
""")


INFOLOOP = r"""
local lists = {}
local function key(n, o) return tostring(n) .. "|" .. tostring(type(o) == "table" and o.filter or "") end
local function list(n, o) local k = key(n, o) lists[k] = lists[k] or {} return lists[k] end
event = {
  register = function(n, fn, o) local l = list(n, o) l[#l + 1] = fn end,
  unregister = function(n, fn, o) local l = list(n, o) for i = #l, 1, -1 do if l[i] == fn then table.remove(l, i) end end end,
}
function fire(n, e, o) for _, f in ipairs({ unpack(list(n, o)) }) do f(e or {}) end end
function hooks() return #list("uiActivated", { filter = "MenuOptions" }), #list("load") end
mwse = { log = function() end, saveConfig = function() end,
  loadConfig = function(_, d) d.enabled = true; d.startupCheck = STARTUP; d.scanBudgetMs = 0; return d end }
function el() local e = {} return setmetatable(e, { __index = function(_, k) if k == "children" then return {} end return function() return el() end end }) end
cache = nil
json = { loadfile = function() return cache end }
lfs = { mkdir = function() end, attributes = function() return nil end, fileexists = function() return false end }
tes3ui = { registerID = function(id) return id end, findMenu = function() end, showNotifyMenu = function() end,
  createMenu = function() return el() end, enterMenuMode = function() end, leaveMenuMode = function() end }
tes3 = { event = setmetatable({}, { __index = function(_, k) return k end }),
  dataHandler = { nonDynamicData = { dialogues = { {} }, activeMods = {} } } }
timer = { real = "real", start = function() return { cancel = function() end } end, delayOneFrame = function(f) f() return true end,
  frame = { delayOneFrame = function(f) step = f return true end } }
M = assert(loadfile([[SUITE/mwinfoloop/main.lua]]))()
local a, b = hooks()
assert(a == 1 and b == 1, "both startup hooks before the check")
"""


def infoloop(tmp_path, startup, body):
    script = (INFOLOOP + body).replace("SUITE", SUITE).replace("STARTUP", startup)
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, cwd=str(tmp_path))
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stdout + out.stderr


def test_infoloop_hooks_come_off_on_a_cache_hit(tmp_path):
    infoloop(tmp_path, "true", r"""
cache = { version = 2, fingerprint = M.fingerprint(), anomalies = {}, topics = 1, circular = 0 }
fire("initialized")
local a, b = hooks()
assert(a == 0 and b == 0, "cached: nothing to check, both hooks off")
print("ok")
""")


def test_infoloop_hooks_come_off_after_the_main_menu_when_no_check_runs(tmp_path):
    infoloop(tmp_path, "false", r"""
fire("initialized")
fire("uiActivated", { element = {} }, { filter = "MenuOptions" })
local a, b = hooks()
assert(a == 0 and b == 0, "check skipped this session: both hooks off")
print("ok")
""")


def test_infoloop_keeps_the_load_hook_while_a_check_runs(tmp_path):
    infoloop(tmp_path, "true", r"""
fire("initialized")
fire( "uiActivated", { element = {} }, { filter = "MenuOptions" })
local a, b = hooks()
assert(a == 0, "the main-menu hook is off once the check started")
local menu, load = M.startupHooksActive()
assert(load and b == 1, "a check still running keeps the load hook")
fire("load")
a, b = hooks()
assert(b == 0, "after a load the check can't start again: the load hook is off")
print("ok")
""")

def test_after_dispatch_defers_to_the_next_frame_when_there_are_timers():
    run(r"""
local intercept = require("mwpluginpatches.intercept")
local ran = false
intercept.afterDispatch(function() ran = true end)
assert(ran, "no delayOneFrame: runs at once")
local queued
timer.delayOneFrame = function(fn, kind) queued = { fn, kind } return true end
ran = false
intercept.afterDispatch(function() ran = true end)
assert(not ran and queued[2] == "real", "deferred on a real-time timer, so it runs in menus too")
queued[1]()
assert(ran)
print("ok")
""")


def test_files_are_utf8_without_bom():
    for rel in ("mwpluginpatches/intercept.lua", "mwpluginpatches/patches/partyAlchemyModuleBox.lua",
                "mwpluginpatches/patches/wtsMetadataLog.lua", "mwpluginpatches/patches/mabrDist.lua",
                "mwpluginpatches/patches/autoStartup.lua", "mwpluginpatches/patches/trainerLogUnlock.lua",
                "mwpluginpatches/patches/talesHandwritingFix.lua", "mwpluginpatches/patches/personalEffects.lua",
                "mwinfoloop/main.lua"):
        with open(os.path.join(SUITE, rel), "rb") as f:
            data = f.read()
        assert not data.startswith(b"\xef\xbb\xbf"), rel
        data.decode("utf-8")