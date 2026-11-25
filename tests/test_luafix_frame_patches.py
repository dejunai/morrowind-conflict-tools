"""luafix 2026-11-25: noise filters (MWSE\\backups / *-off folders, files nothing loads, G6 on "player", H2 for custom
events fired only on loaded) and the targeted frame-drain (KP) and safe-handle (KR) patches."""
import os

import pytest

from conftest import _load

L = _load("mwdialog_lua")
lf = _load("mwdialog_luafix")

try:
    from lupa import luajit21 as _lj
    from lupa.luajit21 import LuaError
    HAVE_LUA = True
except Exception:                                    # the behaviour tests need a real LuaJIT
    HAVE_LUA = False
need_lua = pytest.mark.skipif(not HAVE_LUA, reason="lupa (LuaJIT) not installed")

CFG = dict(lf.DEFAULTS)


class OkChecker:
    name = "fake"

    def check(self, text):
        return True, ""


def analyse(src, rel="testmod/main.lua", cfg=CFG):
    a = lf.FileAnalysis(src, "testmod", rel, cfg)
    a.run()
    return a


def mod_tree(tmp_path, files, name="testmod"):
    root = tmp_path / "Mod" / "MWSE" / "mods" / name
    root.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="latin-1")
    return tmp_path / "Mod", root


def check(paths, data_dir="", cfg=CFG):
    """data_dir "": an empty Data Files\\MWSE beside the tree (other mods load nothing); None: no Data Files."""
    if data_dir == "":
        first = os.path.dirname(str(paths[0]).rstrip("/\\"))
        data_dir = os.path.join(first, "Data Files")
        os.makedirs(os.path.join(data_dir, "MWSE"), exist_ok=True)
    return lf.check_paths([str(p) for p in paths], cfg, False, OkChecker(), "high", data_dir, use_cache=False)


def by_rel(rep):
    return {e["rel"]: e for e in rep.files.values()}


# ------------------------------------------------------------------------------------------------ noise filters
def test_backups_and_switched_off_folders_are_never_walked_or_touched(tmp_path):
    mwse = tmp_path / "Data Files" / "MWSE"
    for rel in ("mods/live/main.lua", "backups/suite-relocation-20261121/mwfloatfix/main.lua",
                "MWSE-off/mods/old/main.lua", "mods/old_off/main.lua", "mods/x/backups/main.lua"):
        p = mwse / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("local x = 1\n")
    found = {os.path.relpath(p, mwse).replace("\\", "/") for p in lf.lua_files(str(mwse))}
    assert found == {"mods/live/main.lua", "mods/x/backups/main.lua"}     # only MWSE\backups is a backup folder
    assert "backup copy" in lf.excluded(str(mwse / "backups" / "a" / "main.lua"))
    assert "switched-off" in lf.excluded(str(tmp_path / "Extras" / "MWSE-off" / "mods" / "MWCA" / "main.lua"))
    assert lf.excluded(str(mwse / "mods" / "live" / "main.lua")) is None


def test_G6_ignores_getReference_player_but_not_a_real_search():
    src = ('event.register("activate", function(e)\n'
           '    local p = tes3.getReference("player")\n'
           '    local q = tes3.getReference("PlayerSaveGame")\n'
           '    local c = tes3.getReference("chargen captain")\n'
           'end)\n')
    g6 = [f["line"] for f in analyse(src).findings if f["rule"] == "G6"]
    assert g6 == [4]


H2_COMMON = '''local function onLoad()
    event.trigger("Mine:DataLoaded")
end
event.register("loaded", onLoad)
'''
H2_TIMER = '''local function onData()
    timer.start{ duration = 1, type = timer.simulate, iterations = -1, callback = function() end }
end
event.register("Mine:DataLoaded", onData)
'''


def test_H2_custom_event_fired_only_from_loaded_counts_as_loaded(tmp_path):
    root, _m = mod_tree(tmp_path, {"main.lua": 'require("testmod.common")\nrequire("testmod.xp")\n',
                                   "common.lua": H2_COMMON, "xp.lua": H2_TIMER})
    assert not [f for e in check([root]).files.values() for f in e["findings"] if f["rule"] == "H2"]


@pytest.mark.parametrize("common", [
    H2_COMMON.replace('"loaded"', '"simulate"'),                              # fired every frame
    H2_COMMON + "onLoad()\n",                                                 # also fired directly
    'event.trigger("Mine:DataLoaded")\n',                                     # fired at file load
    H2_COMMON + 'event.register("cellChanged", function() event.trigger("Mine:DataLoaded") end)\n',
])
def test_H2_custom_event_fired_elsewhere_still_reports(tmp_path, common):
    root, _m = mod_tree(tmp_path, {"main.lua": 'require("testmod.common")\nrequire("testmod.xp")\n',
                                   "common.lua": common, "xp.lua": H2_TIMER})
    h2 = [f for e in check([root]).files.values() for f in e["findings"] if f["rule"] == "H2"]
    assert len(h2) == 1 and h2[0]["events"] == ["Mine:DataLoaded"]


def test_H2_custom_event_chain_through_another_load_like_event(tmp_path):
    common = H2_COMMON + 'event.register("Mine:DataLoaded", function() event.trigger("Mine:Ready") end)\n'
    xp = H2_TIMER.replace("Mine:DataLoaded", "Mine:Ready")
    root, _m = mod_tree(tmp_path, {"main.lua": 'require("testmod.common")\nrequire("testmod.xp")\n',
                                   "common.lua": common, "xp.lua": xp})
    assert not [f for e in check([root]).files.values() for f in e["findings"] if f["rule"] == "H2"]


DEAD_SRC = 'event.register("activate", function(e) local c = tes3.getReference("chargen captain") end)\n'


def test_files_nothing_names_are_listed_apart_but_still_checked_and_patched(tmp_path):
    root, m = mod_tree(tmp_path, {
        "main.lua": 'local a = require("testmod.a")\nlocal ok, c = pcall(require, "testmod.c")\n'
                    'local function later() return include("testmod\\\\sub\\\\d") end\n'
                    'local registry = { "testmod.e" }\nlocal parts = { "hud", "config" }\n'
                    'local setsDir = "Data Files\\\\MWSE\\\\mods\\\\testmod\\\\sets"\n',
        "a.lua": DEAD_SRC, "backup.lua": DEAD_SRC, "notmain.lua": DEAD_SRC + "local x = e.reference.data.y\n",
        "c.lua": DEAD_SRC, "sub/d.lua": DEAD_SRC, "e.lua": DEAD_SRC, "i18n/eng.lua": "return {}\n",
        "sub/init.lua": DEAD_SRC, "interop.lua": DEAD_SRC, "hud.lua": DEAD_SRC, "sets/iron.lua": DEAD_SRC})
    rep = check([root])
    files = by_rel(rep)
    dead = sorted(r for r, e in files.items() if e.get("dead"))
    assert dead == ["testmod/backup.lua", "testmod/notmain.lua"]
    b = files["testmod/backup.lua"]
    assert b["findings"] == [] and [f["rule"] for f in b["dead_findings"]] == ["G6"] and b["patch"] is None
    nm = files["testmod/notmain.lua"]                   # its fixable finding is still patched
    assert [f["rule"] for f in nm["dead_findings"]] == ["G6"] and nm["patch"] and nm["patch"]["ok"]
    assert [f["rule"] for f in files["testmod/a.lua"]["findings"]] == ["G6"]
    lines, counts = lf.format_report(rep)
    assert sum("unreferenced testmod/" in ln for ln in lines) == 2
    assert counts[("G6", "report")] == 8                # the 8 referenced files; the 2 set aside are not counted
@pytest.mark.parametrize("main", [
    'local name = "x" require("testmod." .. name)\n',          # built at run time: anything under testmod
    'local r = require\n',                                       # require handed around
    'for _, n in ipairs(list) do dofile(n) end\n',
])
def test_a_mod_that_builds_its_require_names_has_no_dead_files(tmp_path, main):
    root, _m = mod_tree(tmp_path, {"main.lua": main, "backup.lua": DEAD_SRC})
    assert not any(e.get("dead") for e in check([root]).files.values())


def test_libraries_and_other_mods_names_keep_a_file_alive(tmp_path):
    root, _m = mod_tree(tmp_path, {"lib/util.lua": DEAD_SRC})                     # no main.lua: a library
    assert not any(e.get("dead") for e in check([root]).files.values())
    root2, _m2 = mod_tree(tmp_path / "two", {"main.lua": "", "shared.lua": DEAD_SRC}, "provider")
    data = tmp_path / "Game" / "Data Files"
    (data / "MWSE" / "mods" / "consumer").mkdir(parents=True)
    (data / "MWSE" / "mods" / "consumer" / "main.lua").write_text('local s = require("provider.shared")\n')
    assert not any(e.get("dead") for e in check([root2], str(data)).files.values())
    (tmp_path / "empty-data" / "MWSE").mkdir(parents=True)
    assert any(e.get("dead") for e in check([root2], str(tmp_path / "empty-data")).files.values())


def test_without_data_files_nothing_is_called_unreferenced(tmp_path):
    root, _m = mod_tree(tmp_path, {"main.lua": "", "backup.lua": DEAD_SRC})
    assert any(e.get("dead") for e in check([root]).files.values())
    assert not any(e.get("dead") for e in check([root], None).files.values())


def test_skipKnown_reports_a_targeted_patch_without_applying_it():
    cfg = dict(CFG, skipKnown=["KP3"])
    src = KEGDRIP
    fs = [f for f in analyse(src, "kegdrip/main.lua", cfg).findings if f["rule"] == "KP3"]
    assert len(fs) == 1 and fs[0]["conf"] == "report" and not fs[0]["edits"] and "skipKnown" in fs[0]["what"]


def test_known_labels():
    assert lf.known_label("KB19") == "(Known Bugs)" and lf.known_label("KP1") == "(Known Perf)"
    assert lf.known_label("KR2") == "(Ref Safety)" and lf.known_label("G6") is None


# ------------------------------------------------------------------------------------------------ KP / KR patches
NEW_RULES = {"KP1", "KP2", "KP3", "KP4", "KR1", "KR2", "KR3"}


def test_targeted_patches_apply_once_and_are_whole_where_parts_depend():
    entries = [e for e in lf.KNOWN_BUGS if e[0] in NEW_RULES]
    assert {e[0] for e in entries} == NEW_RULES
    for _rule, _owner, rel, old, new, _what in entries:
        assert old not in new and rel == rel.lower()
        assert "local fix" in new or "localpatch_" in new
    assert {"KP1", "KR1", "KR2"} <= lf.KNOWN_BUGS_WHOLE
    own = {r.split("/")[0] for _r, _o, r, *_x in entries}
    assert not own & set(lf.OWN_MODS)                      # never the user's own mwsuite Lua


def kp_patch(source, rel, rule, parts, eol):
    """The rule's findings on source (with eol): patched, parses, idempotent, line 1 keeps its text."""
    source = source.replace("\n", eol)
    findings = [f for f in analyse(source, rel).findings if f["rule"] == rule]
    assert len(findings) == parts and all(f["conf"] == "high" for f in findings), findings
    repaired, applied = lf.build_patch(source, findings, "testmod", CFG, "high", False)
    assert rule in applied and repaired.count("\n") == repaired.count(eol)
    assert source.split(eol, 1)[0] in repaired.split(eol, 1)[0]
    assert not [f for f in analyse(repaired, rel).findings if f["rule"] == rule]
    assert lf.verify_patch(source, repaired, applied, None, "testmod", rel, CFG, "high")["ok"]
    return repaired


def lua():
    return _lj.LuaRuntime(unpack_returned_tuples=True)


def entry(rule, i=0):
    return [e for e in lf.KNOWN_BUGS if e[0] == rule][i]


ATTEND_ACTIONS = """local currentTarget = COMPANION
local labels = {}

""" + entry("KP1")[3] + """

local function resolveLootContext(companionRef)
    local hit = rayWorld(companionRef)
    if not hit or not hit.reference then return nil, "Loot", nil end
    return "loot", "Loot", hit.reference
end

local function resolveMoveContext(companionRef)
    if not companionRef then return "move", "Move" end
""" + entry("KP1", 1)[3] + """
        return "wait", "Wait"
    end
    return "move", "Move"
end

local function resolveActionContext(companionRef)
    local hit = rayWorld(companionRef)
    if hit and hit.reference and hit.reference.locked then return "lock", "Pick Lock", hit.reference end
    return "wander", "Wander", nil
end

local function onSimulate()
    local _, a = resolveMoveContext(currentTarget)
    local _, b = resolveLootContext(currentTarget)
    local _, c = resolveActionContext(currentTarget)
    local _, _, t = resolveActionContext(currentTarget)
    labels[#labels + 1] = a .. "/" .. tostring(b) .. "/" .. c .. "/" .. tostring(t and t.name)
    if FAIL then error("boom") end
end

local function init()
""" + entry("KP1", 2)[3] + """end
init()
return { rayWorld = rayWorld, labels = labels, move = resolveMoveContext }
"""

ATTEND_STUBS = """
COMPANION = { name = "Ajira" }
CHEST = { name = "chest", locked = true }
RAYS = 0
RESULT = {}                                    -- MWSE reuses one result object for every rayTest
HANDLER = nil
event = { register = function(_e, fn) HANDLER = fn end }
tes3 = { event = { simulate = "simulate" }, player = { name = "player" },
         getPlayerEyePosition = function() return 0 end, getPlayerEyeVector = function() return 1 end }
tes3.rayTest = function(p)
    RAYS = RAYS + 1
    local skipCompanion = false
    for _, r in ipairs(p.ignore) do if r == COMPANION then skipCompanion = true end end
    RESULT.reference = skipCompanion and CHEST or COMPANION
    return RESULT
end
"""


@need_lua
@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_KP1_attend_me_shares_the_frames_eye_rays_and_keeps_every_label(eol):
    repaired = kp_patch(ATTEND_ACTIONS, "attendmemwse/actions.lua", "KP1", 3, eol)
    out = {}
    for name, text in (("orig", ATTEND_ACTIONS), ("patched", repaired)):
        rt = lua()
        rt.execute(ATTEND_STUBS)
        rt.globals().SRC = text.replace("\r", "")
        m = rt.eval("assert(loadstring(SRC))()")
        rt.execute("HANDLER() HANDLER()")
        rays_two_frames = rt.eval("RAYS")
        rt.globals().M = m
        assert rt.eval("M.rayWorld(COMPANION) == RESULT and M.rayWorld(COMPANION).reference == CHEST")
        assert rt.eval("select(2, M.move(COMPANION))") == "Wait"
        rt.execute("FAIL = true")
        ok = rt.eval("pcall(HANDLER)")
        assert ok[0] is False and "boom" in ok[1]
        rt.execute("FAIL = false RAYS = 0")
        assert rt.eval("M.rayWorld(COMPANION) == RESULT and RAYS == 1")     # an error never leaves the memo on
        out[name] = (list(m.labels.values()), rays_two_frames)
    assert out["orig"][0] == out["patched"][0] == ["Wait/Loot/Pick Lock/chest"] * 3
    assert out["orig"][1] == 8 and out["patched"][1] == 4                    # 4 rays a frame -> 2


RECRUIT = """local active = true
local rays, labels = 0, 0
local function rayTarget() rays = rays + 1 return { reference = NPC } end
local function showLabel() labels = labels + 1 end

""" + entry("KP2")[3] + """    if hit and hit.reference then showLabel() end
end

local function onClick()
    local hit = rayTarget()
    return hit.reference
end
return { sim = onSimulate, click = onClick, counts = function() return rays, labels end }
"""


@need_lua
@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_KP2_recruit_label_ray_every_third_frame_click_unchanged(eol):
    repaired = kp_patch(RECRUIT, "attendmemwse/recruit.lua", "KP2", 1, eol)
    got = {}
    for name, text in (("orig", RECRUIT), ("patched", repaired)):
        rt = lua()
        rt.execute('NPC = { name = "Fargoth" } MENU = false tes3 = { menuMode = function() return MENU end }')
        rt.globals().SRC = text.replace("\r", "")
        rt.globals().M = rt.eval("assert(loadstring(SRC))()")
        rt.execute("for i = 1, 6 do M.sim() end MENU = true M.sim() M.sim() MENU = false")
        rays, labels = rt.eval("M.counts()")
        assert rt.eval("M.click() == NPC")
        got[name] = (rays, labels)
    assert got["orig"] == (6, 6) and got["patched"] == (2, 2)                # frames 1 and 4; none in menu mode


KEGDRIP = """local kegs = {}
""" + entry("KP3")[3] + """
return normalizeMesh
"""


@need_lua
@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_KP3_keg_drip_normalises_each_mesh_once_with_the_same_answer(eol):
    repaired = kp_patch(KEGDRIP, "kegdrip/main.lua", "KP3", 1, eol)
    inputs = ["Meshes/F/Furn_Com_Kegstand.NIF", "f\\furn_de_kegstand.nif", "MESHES\\x/y.nif", "meshes/meshes/a.nif",
              "hr\\f\\hr_furn_kegstand_01.nif"]
    res = {}
    for name, text in (("orig", KEGDRIP), ("patched", repaired)):
        rt = lua()
        rt.execute("GSUBS = 0 local g = string.gsub string.gsub = function(...) GSUBS = GSUBS + 1 return g(...) end")
        rt.globals().SRC = text.replace("\r", "")
        rt.globals().F = rt.eval("assert(loadstring(SRC))()")
        vals = [rt.eval("F(...)", x) for x in inputs * 3]
        assert rt.eval("F(nil) == nil and F(false) == false")
        assert rt.eval("select('#', F('a/b.nif'))") == 1
        res[name] = (vals, rt.eval("GSUBS"))
    assert res["orig"][0] == res["patched"][0] and res["orig"][0][0] == "f\\furn_com_kegstand.nif"
    assert res["orig"][1] == 2 * (3 * len(inputs) + 1) and res["patched"][1] == 2 * (len(inputs) + 1)


G7 = """local mod = {}
---@param itemData tes3itemData|nil
""" + entry("KP4")[3] + """
return checkData
"""

G7_STUBS = """
LOOKUPS = 0
REFS = {}
tes3 = {}
tes3.getReference = function(id) LOOKUPS = LOOKUPS + 1 if id == nil then return "PLAYER" end return REFS[id] end
tes3.makeSafeObjectHandle = function(ref)
    return { valid = function() return not ref.gone end, getObject = function() return ref end }
end
function item(id) return { data = { g7containers = { linkedRef = id, baseObject = "g7_bag" } } } end
"""


@need_lua
@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_KP4_g7_containers_finds_the_linked_container_once(eol):
    repaired = kp_patch(G7, "spammer/g7 containers/main.lua", "KP4", 1, eol)
    steps = """
local out = {}
local function rec(r, b) out[#out + 1] = tostring(r and r.name) .. ":" .. tostring(b) end
local A, B, C = { name = "A" }, { name = "B" }, { name = "C" }
REFS.box = A
for i = 1, 3 do rec(F(item("box"))) end
A.gone = true REFS.box = B           -- handle invalid: looked up again
rec(F(item("box")))
B.deleted = true REFS.box = C        -- deleted: looked up again
rec(F(item("box"))) rec(F(item("box")))
REFS.box = nil C.gone = true         -- gone for good: nil like getReference
rec(F(item("box")))
rec(F(nil)) rec(F({ data = {} }))
out[#out + 1] = tostring(F(item(nil)))
return table.concat(out, ",")
"""
    got = {}
    for name, text in (("orig", G7), ("patched", repaired)):
        rt = lua()
        rt.execute(G7_STUBS)
        rt.globals().SRC = text.replace("\r", "")
        rt.globals().F = rt.eval("assert(loadstring(SRC))()")
        got[name] = (rt.execute(steps), rt.eval("LOOKUPS"))
    assert got["orig"][0] == got["patched"][0] == "A:g7_bag,A:g7_bag,A:g7_bag,B:g7_bag,C:g7_bag,C:g7_bag,nil:g7_bag,nil:nil,nil:nil,PLAYER"
    assert got["orig"][1] == 8 and got["patched"][1] == 5


FADER = """local this = {}
function this.fade(ref, track, fadeType, removeTrack, onFail, isTrackUnattached)
    local fadeInProgress = {}
    local iterCount = 0

    local function fader()
        iterCount = iterCount + 1
        if (not track) or (isTrackUnattached and not track:isPlaying()) or """ + entry("KR1", 1)[3] + """
            if onFail then onFail(fadeInProgress) end
            return "fail"
        end
        return "ok"
    end
    fadeInProgress.fader = fader
    fadeInProgress.done = function()
""" + entry("KR1", 2)[3] + """
                tes3.removeSound { sound = track, reference = ref }
                return "removed"
            end
        return "kept"
    end
    return fadeInProgress
end
return this
"""

REF_STUBS = """
tes3 = { makeSafeObjectHandle = function(ref) return { valid = function() return not ref._gone end } end }
function newRef(name)                      -- reading a field of a deleted reference raises, as MWSE does now
    return setmetatable({ _gone = false, _f = { name = name, mobile = { isDead = false } } }, { __index = function(t, k)
        if rawget(t, "_gone") then error("tried to use a deleted reference") end
        return rawget(t, "_f")[k] end })
end
tes3.getSoundPlaying = function(p) local _ = p.reference.name return true end
REMOVED = 0
tes3.removeSound = function(p) local _ = p.reference.name REMOVED = REMOVED + 1 end
"""


@need_lua
@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_KR1_aura_fade_ends_when_its_reference_is_deleted(eol):
    repaired = kp_patch(FADER, "tew/aura/fader.lua", "KR1", 3, eol)
    got = {}
    for name, text in (("orig", FADER), ("patched", repaired)):
        rt = lua()
        rt.execute(REF_STUBS)
        rt.globals().SRC = text.replace("\r", "")
        rt.globals().M = rt.eval("assert(loadstring(SRC))()")
        live = rt.execute('local f = M.fade(newRef("door"), "tavern", "out", true) return f.fader() .. "," .. f.done()')
        gone = rt.execute('FAILED = 0 local r = newRef("door") local f = M.fade(r, "tavern", "out", true, '
                          'function() FAILED = FAILED + 1 end) r._gone = true '
                          'local ok1, a = pcall(f.fader) local ok2, b = pcall(f.done) '
                          'return tostring(ok1) .. "," .. tostring(a) .. "," .. tostring(ok2) .. "," .. tostring(b) .. "," .. FAILED')
        got[name] = (live, gone, rt.eval("REMOVED"))
    assert got["orig"][0] == got["patched"][0] == "ok,removed"
    assert got["orig"][1].startswith("false,") and got["patched"][1] == "true,fail,true,kept,1"
    assert got["patched"][2] == 1                                            # only the live fade removed its track


ATTEND_JOBS = """local log = {}
local function cancelJob(ref) log[#log + 1] = "cancel" end
local function forceFollow(ref)
    local ticks = 0
""" + entry("KR2")[3] + """            cancelJob(ref)
            return "stop"
        end
        return "go"
    end
    return tick
end

local function travelThen(ref, tickInterval)
""" + entry("KR2", 1)[3] + """                cancelJob(ref)
                return "stop"
            end
            return "go"
        end,
    })
    return job.timer
end
return { forceFollow = forceFollow, travelThen = travelThen, log = log }
"""


@need_lua
@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_KR2_attend_me_jobs_end_when_the_companion_is_deleted(eol):
    repaired = kp_patch(ATTEND_JOBS, "attendmemwse/actions.lua", "KR2", 2, eol)
    script = """
local out = {}
for _, make in ipairs({ M.forceFollow, function(r) return M.travelThen(r, 0.25) end }) do
    local r = newRef("Ajira")
    local tick = make(r)
    out[#out + 1] = tick()
    r._gone = true
    local ok, v = pcall(tick)
    out[#out + 1] = ok and v or "error"
    out[#out + 1] = make(nil)()
end
return table.concat(out, ",") .. "|" .. #M.log
"""
    got = {}
    for name, text in (("orig", ATTEND_JOBS), ("patched", repaired)):
        rt = lua()
        rt.execute(REF_STUBS + "timer = { simulate = 1, start = function(p) return p.callback end }")
        rt.globals().SRC = text.replace("\r", "")
        rt.globals().M = rt.eval("assert(loadstring(SRC))()")
        got[name] = rt.execute(script)
    assert got["orig"] == "go,error,stop,go,error,stop|2"
    assert got["patched"] == "go,stop,stop,go,stop,stop|4"


RECRUIT_DISMISS = """local HOME = 0
local function playRecallVisual(ref) end
local function dismissCompanion(ref)
    if not ref then return end
""" + entry("KR3")[3] + """            pcall(function()
                if ref.mobile and not ref.mobile.isDead then HOME = HOME + 1 end
            end)
        end,
    })
end
return { dismiss = dismissCompanion, home = function() return HOME end }
"""


@need_lua
@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_KR3_attend_me_dismiss_checks_a_safe_handle_first(eol):
    repaired = kp_patch(RECRUIT_DISMISS, "attendmemwse/recruit.lua", "KR3", 1, eol)
    got = {}
    for name, text in (("orig", RECRUIT_DISMISS), ("patched", repaired)):
        rt = lua()
        rt.execute(REF_STUBS + "CB = nil timer = { simulate = 1, start = function(p) CB = p.callback end }")
        rt.globals().SRC = text.replace("\r", "")
        rt.globals().M = rt.eval("assert(loadstring(SRC))()")
        got[name] = rt.execute('local r = newRef("Ajira") M.dismiss(r) CB() '
                               'local g = newRef("Ajira") M.dismiss(g) g._gone = true local ok = pcall(CB) '
                               'return M.home() .. "," .. tostring(ok)')
    assert got["orig"] == got["patched"] == "1,true"                         # same outcome; no swallowed error now
