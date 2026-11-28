"""mwdialog_luafix / mwdialog_lua: tokenizer, parser, rules, patching in place, undo, tidy wiring."""
import json
import os
import subprocess
import sys

import pytest

from conftest import _load, vt

L = _load("mwdialog_lua")
lf = _load("mwdialog_luafix")

try:
    from lupa import luajit21 as _lj
    from lupa.luajit21 import LuaError
    HAVE_LUA = True
except Exception:                                    # the execution tests need a real LuaJIT
    HAVE_LUA = False
need_lua = pytest.mark.skipif(not HAVE_LUA, reason="lupa (LuaJIT) not installed")

CFG = dict(lf.DEFAULTS)


class OkChecker:
    name = "fake"

    def __init__(self, ok=True, reject_new=False):
        self.calls, self.ok, self.reject_new = [], ok, reject_new

    def check(self, text):
        self.calls.append(text)
        if self.reject_new and "localpatch" in text:
            return False, "line 1: rejected"
        return self.ok, "" if self.ok else "line 1: bad"


def analyse(src, rel="testmod/main.lua"):
    a = lf.FileAnalysis(src, "testmod", rel, CFG)
    a.run()
    return a


def rules(a, conf=None):
    return sorted(f["rule"] for f in a.findings if conf is None or f["conf"] == conf)


def patch(src, level="high", shim=False):
    a = analyse(src)
    new, _r = lf.build_patch(src, a.findings, "testmod", CFG, level, shim)
    return new


def mod_tree(tmp_path, files, name="testmod"):
    root = tmp_path / "Mod" / "MWSE" / "mods" / name
    root.mkdir(parents=True)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode("latin-1") if isinstance(text, str) else text)
    return tmp_path / "Mod", root


# ------------------------------------------------------------------------------------------------ tokenizer
def test_tokenizer_long_brackets_comments_and_escapes():
    src = ('local a = [==[ x ]] ]=] still ]==] --[[ comment\n ]] local b = "q\\"\\\\" '
           "--[=[ nested [[ ]] ]=] local c = 'it\\'s' -- end\nlocal d = 0x1p4 + 1e-3 + 10ULL + .5")
    toks = [t for t in L.tokenize(src) if t.t != "eof"]
    strs = [t.v for t in toks if t.t == "str"]
    assert strs == ['[==[ x ]] ]=] still ]==]', '"q\\"\\\\"', "'it\\'s'"]
    assert [t.v for t in toks if t.t == "num"] == ["0x1p4", "1e-3", "10ULL", ".5"]
    assert [t.v for t in toks if t.t == "name"] == ["a", "b", "c", "d"]
    assert L.string_value('"q\\"\\\\"') == 'q"\\'
    assert L.string_value("[[\nab]]") == "ab"
    assert L.string_value('"\\65\\x42\\z   C"') == "ABC"


def test_tokenizer_lines_and_spans_survive_long_strings():
    src = "local s = [[a\nb\nc]]\nlocal t = 1"
    toks = L.tokenize(src)
    t = next(x for x in toks if x.v == "t")
    assert t.line == 4 and src[t.s:t.e] == "t"


@pytest.mark.parametrize("bad", ["local a = [[ open", "x = 'unterminated\n'", "--[[ never closed", "local 1a = 2"])
def test_tokenizer_errors(bad):
    with pytest.raises(L.LuaSyntaxError):
        L.parse(bad)


@pytest.mark.parametrize("src", [
    "local a = b.c:d{e = 1}.f['g'](...)", "goto x ::x::", "a, b.c = 1, 2", "return", "for i = 1, 2, 3 do end",
    "for k, v in pairs(t) do break end", "repeat local x = 1 until x", "f 'str' f [[long]] f {}",
    "local x = - - 1 .. 2 ^ - 3", "if a then elseif b then else end", "local function f(a, ...) return ... end",
    "local t = { [1] = 2; x = 3, 4, }", "do end; local y = 1;", "#!/usr/bin/lua\nlocal a = 1",
])
def test_parser_accepts_what_luajit_accepts(src):
    L.parse(src)
    if HAVE_LUA:
        rt = _lj.LuaRuntime()
        e = rt.eval("function(s) local f, e = loadstring(s) return e end")(src.split("\n", 1)[-1]
                                                                           if src.startswith("#") else src)
        assert e is None


@pytest.mark.parametrize("src", ["x", "a.b", "f() = 1", "local function a.b() end", "return 1 return 2", "(f)"])
def test_parser_rejects_what_luajit_rejects(src):
    with pytest.raises(L.LuaSyntaxError):
        L.parse(src)


# ------------------------------------------------------------------------------------------------ G1
def test_G1_priority_literal_and_constant_compressed_keeping_order():
    src = ("local P = 999999999\n"
           "event.register(tes3.event.activate, f, { priority = 1000000 })\n"
           "event.register(tes3.event.activate, g, { priority = -100000 })\n"
           "event.register(tes3.event.activate, h, { priority = P })\n"
           "event.register(tes3.event.activate, k, { priority = math.huge })\n"
           "event.register(tes3.event.activate, j, { priority = 500 })\n")
    new = patch(src)
    assert "priority = 9200 }" in new and "priority = -9100 }" in new and "local P = 9499" in new
    assert "priority = 9999 }" in new and "priority = 500 }" in new
    assert lf.compress_priority(10000, CFG) == 9000 and lf.compress_priority(10 ** 7, CFG) == 9300
    ps = [10000, 99999, 100000, 10 ** 6, 2 ** 31 - 1, float("inf")]
    assert [lf.compress_priority(p, CFG) for p in ps] == sorted(lf.compress_priority(p, CFG) for p in ps)
    assert all(9000 <= lf.compress_priority(p, CFG) < 10000 for p in ps)    # above every ordinary priority
    clamp = dict(CFG, priorityMode="clamp")
    assert lf.compress_priority(10 ** 6, clamp) == 1200 and lf.compress_priority(-10000, clamp) == -1000


def test_G1_computed_priority_is_report_only():
    a = analyse("event.register('activate', f, { priority = base + 100000 })")
    assert [f["conf"] for f in a.findings if f["rule"] == "G1"] == ["report"]


def test_G1_constant_used_elsewhere_is_not_edited():
    a = analyse("local P = 100000\nevent.register('activate', f, { priority = P })\nprint(P)")
    assert [f["conf"] for f in a.findings if f["rule"] == "G1"] == ["report"]


# ------------------------------------------------------------------------------------------------ G2 / G3
PUDDLE = """local last = 0
local function onSimulate(e)
    local puddle = tes3.getReference("puddle")
    if puddle and puddle.scale > last then
        last = puddle.scale
        tes3.messageBox("The puddle got bigger")
    end
end
event.register(tes3.event.simulate, onSimulate)
"""


def test_G2_puddle_poll_is_throttled_without_moving_lines():
    new = patch(PUDDLE)
    assert "local function onSimulate(e) if localpatch_gate(1, 0.35) then return end\n" in new
    assert new.count("\n") == PUDDLE.count("\n")            # every line number stays
    assert new.startswith(f"--[[localpatch {lf.VERSION}: G2]] local localpatch_gate do")


@pytest.mark.parametrize("body", [
    "local cam = tes3.getCamera() cam.position = cam.position + e.delta",          # dt-integrated motion
    "tes3.mobilePlayer.reference.orientation = target",                             # orientation writes
    "local menu = tes3ui.findMenu('MenuMulti') if menu then menu:updateLayout() end",  # UI
    "frames = frames + 1 if frames > 60 then frames = 0 doIt() end",                # frame counter
    "if os.clock() - t > 1 then t = os.clock() end",                                # already self-timed
])
def test_G2_frame_critical_per_frame_left_alone(body):
    src = f"local t, frames = 0, 0\nlocal function doIt() end\nevent.register('simulate', function(e) {body} end)\n"
    a = analyse(src)
    assert all(f["conf"] == "info" for f in a.findings if f["rule"] == "G2")
    assert patch(src) is None or "localpatch_gate(" not in patch(src)


def test_G2_unknown_calls_and_direct_calls_are_medium_only():
    src = "local m = require('x')\nlocal function poll() if m.check() then m.go() end end\n" \
          "event.register('enterFrame', poll)\n"
    a = analyse(src)
    assert [f["conf"] for f in a.findings if f["rule"] == "G2"] == ["medium"]
    assert patch(src) is None and "localpatch_gate(1" in patch(src, "medium")
    src2 = PUDDLE + "event.register('loaded', function() onSimulate() end)\n"
    assert [f["conf"] for f in analyse(src2).findings if f["rule"] == "G2"] == ["medium"]


def test_G3_tight_forever_timer_slowed_only_when_it_polls():
    src = ("local seen\nlocal function check() if tes3.getGlobal('x') ~= seen then seen = tes3.getGlobal('x') end end\n"
           "timer.start({ duration = 0.01, iterations = -1, callback = check })\n"
           "timer.start({ duration = 0.01, iterations = -1, callback = function(e) local c = tes3.getCamera() end })\n"
           "timer.start({ duration = 0.01, iterations = 5, callback = check })\n")
    new = patch(src)
    assert new.count("duration = 0.35") == 1 and new.count("duration = 0.01") == 2


# ------------------------------------------------------------------------------------------------ G4
ONESHOT = """local done = false
local function waitForQuest(e)
    if done then return end
    if tes3.getJournalIndex{ id = "MS_Lookout" } >= 50 then
        tes3.addItem{ reference = tes3.player, item = "gold_001", count = 5 }
        done = true
    end
end
event.register(tes3.event.cellChanged, waitForQuest)
"""


def test_G4_flag_guarded_one_shot_gets_unregister():
    new = patch(ONESHOT)
    assert "done = true event.unregister(tes3.event.cellChanged, waitForQuest)\n" in new
    assert new.count("\n") == ONESHOT.count("\n")
    assert patch(new) is None                                # idempotent


def test_G4_one_shot_with_filter_unregisters_with_it():
    src = ONESHOT.replace("event.register(tes3.event.cellChanged, waitForQuest)",
                          "event.register(tes3.event.activate, waitForQuest, { filter = 'door_01', priority = 5 })")
    assert "event.unregister(tes3.event.activate, waitForQuest, { filter = 'door_01' })" in patch(src)


def test_G4_rearmed_one_shot_left_alone():
    src = ONESHOT + "event.register('loaded', function() done = false end)\n"
    a = analyse(src)
    assert [f["conf"] for f in a.findings if f["rule"] == "G4"] == ["info"]
    assert patch(src) is None or "unregister(tes3.event.cellChanged" not in patch(src)


def test_G4_inline_one_shot_is_report_only():
    src = "local done\nevent.register('menuEnter', function(e)\n if done then return end\n init() done = true\nend)\n"
    a = analyse(src)
    assert [(f["rule"], f["conf"]) for f in a.findings if f["rule"] == "G4"] == [("G4", "report")]


def test_G4_handler_that_fires_every_time_is_left_alone():
    src = "local function onAct(e) if e.target then tes3.messageBox('hi') end end\nevent.register('activate', onAct)\n"
    assert not [f for f in analyse(src).findings if f["rule"] == "G4"]


# ------------------------------------------------------------------------------------------------ A1
def test_A1_ref_data_guard_guards_every_level_after_data():
    src = ("local function f(ref)\n local v = ref.data.myMod.count\n if ref.data.flag == 1 then end\n"
           " ref.data.x = 1\n local w = tes3.player.data.y\n local s = self.data.z\nend\n")
    new = patch(src)
    assert "local v = (ref.data and ref.data.myMod and ref.data.myMod.count)" in new
    assert "if (ref.data and ref.data.flag) == 1 then" in new
    assert " ref.data.x = 1" in new and "tes3.player.data.y" in new and "self.data.z" in new


def test_A1_already_guarded_is_left_alone():
    src = "local function f(ref)\n if ref.supportsLuaData then local v = ref.data.k end\nend\n"
    assert not [f for f in analyse(src).findings if f["rule"] == "A1"]
    src2 = "local function f(ref)\n if not ref.data then return end\n local v = ref.data.k\nend\n"
    assert not [f for f in analyse(src2).findings if f["rule"] == "A1"]


def test_A1_patched_text_no_longer_crashes_where_the_naive_guard_does():
    if not HAVE_LUA:
        pytest.skip("needs LuaJIT")
    src = "local function f(e) local v = e.reference.data.count return v end\nreturn f"
    new = patch(src)
    rt = _lj.LuaRuntime()
    fn = rt.execute(new)
    assert fn(rt.eval("{ reference = {} }")) is None        # data nil: nil, not an error
    with pytest.raises(LuaError):                          # nil 'data': raised by the LuaJIT FFI, not a broad catch
        rt.execute(src)(rt.eval("{ reference = {} }"))


# ------------------------------------------------------------------------------------------------ D1 / H1
def test_D1_info_filter_returns_early_unless_passes():
    src = "local function onInfo(e)\n if e.info.text:find('x') then e.passes = false end\nend\n" \
          "event.register(tes3.event.infoFilter, onInfo)\n"
    assert "local function onInfo(e) if not e.passes then return end\n" in patch(src)


def test_D1_handler_that_can_make_a_response_pass_is_left_alone():
    src = "local function onInfo(e)\n if e.info.text:find('x') then e.passes = true end\nend\n" \
          "event.register('infoFilter', onInfo)\n"
    assert all(f["conf"] == "report" for f in analyse(src).findings if f["rule"] == "D1")


def test_H1_named_reregister_on_load_is_guarded_anonymous_reported():
    src = ("local function onAct(e) end\nlocal function onLoaded()\n"
           "  event.register(tes3.event.activate, onAct, { priority = 5 })\n"
           "  event.register(tes3.event.simulate, function() end)\nend\nevent.register('loaded', onLoaded)\n")
    a = analyse(src)
    assert sorted(f["conf"] for f in a.findings if f["rule"] == "H1") == ["high", "report-high"]
    new = patch(src)
    assert ("  if not event.isRegistered(tes3.event.activate, onAct, { priority = 5 }) then "
            "event.register(tes3.event.activate, onAct, { priority = 5 }) end\n") in new
    assert patch(new) is None


def test_H1_initialized_handler_is_fine():
    src = "local function onAct(e) end\nevent.register('initialized', function() event.register('activate', onAct) end)"
    assert not [f for f in analyse(src).findings if f["rule"] == "H1"]


# ------------------------------------------------------------------------------------------------ report-only rules
def test_report_only_rules():
    src = ("local cfg = mwse.loadConfig('x')\nleak = 1\nlocal p = tes3.player\n"
           "local function a(e) local k = cfg.hotkey.keyCode end\n"
           "local function b(menu) menu:destroy() menu.parent:updateLayout() end\n"
           "local function c() tes3.runLegacyScript{ command = 'TogglePOV' } end\n"
           "local function d() for i = 1, 3 do tes3.messageBox('x') end end\n"
           "local function onSim(e) local o = tes3.getObject('x') mwse.saveConfig('x', cfg) end\n"
           "event.register('simulate', onSim)\n"
           "local function onCell() timer.start{ type = timer.simulate, duration = 1, iterations = -1, "
           "callback = function() end } end\nevent.register('cellChanged', onCell)\n")
    a = analyse(src)
    got = set(rules(a))
    assert {"A2", "B1", "C1", "H6", "G5", "H3", "H4", "H2"} <= got
    assert all(not f["edits"] for f in a.findings if f["rule"] in ("B1", "C1", "H6", "G5", "H3", "H4", "H2"))
    assert all(f["edits"] and f["conf"] == "high" for f in a.findings if f["rule"] == "A2")   # now a nil guard
    assert "H4" not in rules(analyse(src, "testmod/util.lua"))     # required later: top level is fine there
    g5 = next(f for f in a.findings if f["rule"] == "G5")
    assert g5["conf"] == "report-high" and "mwse.saveConfig" in g5["what"]


def test_S1_sound_query_on_a_non_actor_is_reported_never_patched():
    aura = ("local this = {}\nfunction this.getTrackPlaying(track, ref)\n"
            "    if track and ref and tes3.getSoundPlaying { sound = track, reference = ref } then\n"
            "        return track\n    end\nend\nreturn this\n")
    a = analyse(aura)
    s1 = [f for f in a.findings if f["rule"] == "S1"]
    assert len(s1) == 1 and s1[0]["line"] == 3 and not s1[0]["edits"] and s1[0]["conf"] == "report"
    assert "mwsoundguard" in s1[0]["what"] and "starts looping" not in s1[0]["what"]
    assert patch(aura) is None                                       # report only: nothing to write
    flies = ("local function tick(ref)\n  if not tes3.getSoundPlaying({ sound = 'Flies', reference = ref.data.f }) "
             "then\n    tes3.playSound{ sound = 'Flies', reference = ref.data.f, loop = true }\n  end\nend\n"
             "timer.start{ duration = 1, iterations = -1, callback = tick }\n")
    assert "this file starts looping sounds" in next(f for f in analyse(flies).findings if f["rule"] == "S1")["what"]
    for fine in ("local p = tes3.player if tes3.getSoundPlaying{ sound = 's', reference = player } then end",
                 "if tes3.getSoundPlaying{ sound = 's', reference = mp.reference } then end",
                 "if tes3.getSoundPlaying{ sound = 's' } then end",
                 "local function f(ref) local ot = ref.object.objectType\n"
                 "if ot == tes3.objectType.npc or ot == tes3.objectType.creature then\n"
                 "return tes3.getSoundPlaying{ sound = 's', reference = ref } end end"):
        assert "S1" not in rules(analyse(fine)), fine


def test_H2_any_timer_restarted_on_load_is_fine():
    # MWSE clears real, simulate and game timers just before `loaded` (LuaManager::clearTimers)
    base = "event.register('{ev}', function() timer.start{{ type = {t}, duration = 1, iterations = -1, " \
           "callback = function() end }} end)"
    for t in ("timer.simulate", "timer.real", "timer.game"):
        assert not [f for f in analyse(base.format(ev="loaded", t=t)).findings if f["rule"] == "H2"], t
    assert [f for f in analyse(base.format(ev="cellChanged", t="timer.real")).findings if f["rule"] == "H2"]


def test_H5_require_cycle(tmp_path):
    data, root = mod_tree(tmp_path, {"main.lua": "local a = require('testmod.a')",
                                     "a.lua": "local b = require('testmod.b') return {}",
                                     "b.lua": "local a = require('testmod.a') return {}"})
    rep = lf.check_paths([str(data)], CFG, checker=OkChecker(), use_cache=False)
    h5 = [f for e in rep.files.values() for f in e["findings"] if f["rule"] == "H5"]
    assert len(h5) == 1 and "testmod/a.lua" in h5[0]["what"]


# the AURA regression of 2026-11-18: Misc/miscMain.lua still calls common.log, common.lua was restored without it
AURA_COMMON = ("local this = {}\nfunction this.debugLog(m) mwse.log(m) end\nlocal function log(m) end\n"
               "this.thunArray = {}\nreturn this\n")
AURA_MISC = ("local common = require('testmod.common')\nlocal function init()\n"
             "    common.log('loading')\n    common.debugLog('x')\nend\ninit()\n")


def _h7(tmp_path, files):
    data, _root = mod_tree(tmp_path, dict({"main.lua": "dofile('x')"}, **files))
    rep = lf.check_paths([str(data)], CFG, checker=OkChecker(), use_cache=False)
    return [f for e in rep.files.values() for f in e["findings"] if f["rule"] == "H7"]


def test_H7_call_to_a_field_the_required_module_never_defines(tmp_path):
    h7 = _h7(tmp_path, {"common.lua": AURA_COMMON, "Misc/miscMain.lua": AURA_MISC})
    assert len(h7) == 1 and h7[0]["line"] == 3 and "log()" in h7[0]["what"]


@pytest.mark.parametrize("common", [
    AURA_COMMON.replace("local function log(m) end", "this.log = print"),
    AURA_COMMON.replace("local function log(m) end", "function this.log(m) end"),
    "return { log = print, debugLog = print }",
    AURA_COMMON.replace("return this", "setmetatable(this, { __index = mwse }) return this"),
    AURA_COMMON.replace("return this", "mixin(this) return this"),
    AURA_COMMON.replace("return this", "this[key] = 1 return this"),
])
def test_H7_left_alone_when_the_field_is_there_or_cant_be_told(tmp_path, common):
    assert not _h7(tmp_path, {"common.lua": common, "Misc/miscMain.lua": AURA_MISC})


@pytest.mark.parametrize("other", [
    "local c = require('testmod.common')\nfunction c.log(m) end\n",             # added by another file
    "local c = require('testmod.common')\nc.log = print\n",
])
def test_H7_field_added_by_another_file_or_in_a_nested_block(tmp_path, other):
    assert not _h7(tmp_path, {"common.lua": AURA_COMMON, "Misc/miscMain.lua": AURA_MISC, "other.lua": other})
    nested = AURA_COMMON.replace("local function log(m) end", "do\n function this.log(m) end\nend")
    assert not _h7(tmp_path / "n", {"common.lua": nested, "Misc/miscMain.lua": AURA_MISC})


# the AttendMe regression of 2026-11-18: refresh() indexes a deleted reference from its last pass every tick
FOLLOWERS = ("local followers = {}\nlocal this = {}\nfunction this.refresh()\n local newList = {}\n"
             " for _, ref in ipairs(followers) do\n"
             "        if ref and ref.mobile and not ref.mobile.isDead then\n"
             "            table.insert(newList, ref)\n        end\n end\n followers = newList\n return #newList\nend\n"
             "function this.set(l) followers = l end\nreturn this\n")


def test_KB1_attendme_stale_reference_is_skipped():
    a = analyse(FOLLOWERS, rel="AttendMeMWSE/followers.lua")
    k1 = [f for f in a.findings if f["rule"] == "KB1"]
    assert len(k1) == 1 and k1[0]["line"] == 6 and k1[0]["conf"] == "high"
    new, rules = lf.build_patch(FOLLOWERS, a.findings, "AttendMeMWSE", CFG)
    assert "KB1" in rules and new.count("\n") == FOLLOWERS.count("\n")
    assert not [f for f in analyse(new, rel="AttendMeMWSE/followers.lua").findings if f["rule"] == "KB1"]
    assert not [f for f in analyse(FOLLOWERS, rel="other/followers.lua").findings if f["rule"] == "KB1"]
    if not HAVE_LUA:
        return
    rt = _lj.LuaRuntime()
    stale = "setmetatable({}, { __index = function() error('sol: received nil for self') end })"
    good = "{ mobile = { isDead = false } }"
    m = rt.execute(new)
    m.set(rt.eval(f"{{ {stale}, {good} }}"))
    assert m.refresh() == 1                               # the deleted one is dropped, the live one kept
    old = rt.execute(FOLLOWERS)
    old.set(rt.eval(f"{{ {stale}, {good} }}"))
    with pytest.raises(LuaError):
        old.refresh()


# ------------------------------------------------------------------------------------------------ F1 / F2
SPAM = "local function onSim(e)\n mwse.log('tick %d', 1)\nend\nevent.register('simulate', onSim)\nprint('Init')\n"


def test_F1_log_spam_gets_the_shim_when_mwguard_does_not_cover(tmp_path):
    data, root = mod_tree(tmp_path, {"main.lua": SPAM})
    rep = lf.check_paths([str(data)], CFG, checker=OkChecker(), use_cache=False, data_dir=str(tmp_path / "none"))
    e = next(iter(rep.files.values()))
    assert e["patch"]["ok"] and "F1" in e["patch"]["rules"]
    assert 'package.loaded["localpatch_logshim:testmod"]' in e["patch"]["text"]
    assert e["patch"]["text"].count("\n") == SPAM.count("\n")


def test_F1_all_logging_mods_get_a_private_log_by_default(tmp_path):
    data, _root = mod_tree(tmp_path, {"main.lua": "mwse.log('ordinary detail')\n"})
    rep = lf.check_paths([str(data)], CFG, checker=OkChecker(), use_cache=False, data_dir=str(tmp_path / "none"))
    e = next(iter(rep.files.values()))
    assert CFG["log"]["scope"] == "all"
    assert e["patch"]["ok"] and "F1" in e["patch"]["rules"]


def test_F1_old_embedded_policy_is_replaced_and_current_policy_is_idempotent():
    old_cfg = dict(CFG, log=dict(CFG["log"], budgetInit=40, budget=10))
    src = lf.log_shim("testmod", old_cfg) + "mwse.log('detail')\n"
    a = analyse(src)
    assert a.old_shim
    new, rules = lf.build_patch(src, a.findings, "testmod", CFG, want_shim=True)
    assert rules == ["F1"] and "init = 0, after = 0" in new and f"S.v == {lf.SHIM_V}" in new
    a = analyse(new)
    assert not a.old_shim
    assert lf.build_patch(new, a.findings, "testmod", CFG, want_shim=True)[0] is None


def test_F1_mod_with_its_own_logger_has_generic_shim_removed(tmp_path):
    src = lf.log_shim("mwsaveguard", CFG) + "mwse.log('Save completed')\n"
    data, _root = mod_tree(tmp_path, {"main.lua": src}, name="mwsaveguard")
    rep = lf.check_paths([str(data)], CFG, include_own=True, checker=OkChecker(), use_cache=False,
                         data_dir=str(tmp_path / "none"))
    patch_ = next(iter(rep.files.values()))["patch"]
    assert patch_["ok"] and "localpatch_logshim" not in patch_["text"]


def test_own_mods_remove_shims_even_when_logging_is_flagged(tmp_path):
    data, _root = mod_tree(tmp_path, {"main.lua": lf.log_shim("mwcompanions", CFG) + SPAM},
                            name="mwcompanions")
    rep = lf.check_paths([str(data)], CFG, include_own=True, checker=OkChecker(), use_cache=False,
                         data_dir=str(tmp_path / "none"))
    patch_ = next(iter(rep.files.values()))["patch"]
    assert patch_["ok"] and "localpatch_logshim" not in patch_["text"]

def test_nested_suite_mods_are_excluded_and_never_receive_log_shims(tmp_path):
    data, root = mod_tree(tmp_path, {"main.lua": SPAM}, name="mwsuite")
    nested = root / "mwcompanions"
    nested.mkdir()
    path = nested / "main.lua"
    path.write_text(SPAM, encoding="utf-8")
    assert lf.excluded(str(path), cfg=CFG)
    assert lf.mod_key_of(str(root.parent), "mwsuite/mwcompanions/main.lua") == "mwsuite/mwcompanions"
    assert lf.log_exempt(CFG, "mwsuite/mwcompanions")
    rep = lf.check_paths([str(data)], CFG, include_own=True, checker=OkChecker(), use_cache=False,
                         data_dir=str(tmp_path / "none"))
    assert all(not e["patch"] or "localpatch_logshim" not in e["patch"].get("text", "")
               for e in rep.files.values())


def test_include_own_applies_only_nil_and_log_rules_to_exempt_mods(tmp_path):
    src = "local x = ref.data.foo\nevent.register('save', function() end, { priority = 10000 })\n"
    data, _root = mod_tree(tmp_path, {"main.lua": src}, name="custommod")
    cfg = dict(CFG, exemptMods=["custommod"])
    rep = lf.check_paths([str(data)], cfg, include_own=True, checker=OkChecker(), use_cache=False,
                         data_dir=str(tmp_path / "none"), level="high")
    patch_ = next(iter(rep.files.values()))["patch"]
    assert patch_ and patch_["ok"]
    assert "A1" in patch_["rules"] and "G1" not in patch_["rules"]
    # the same file, not exempt, still gets G1
    data2, _r2 = mod_tree(tmp_path / "other", {"main.lua": src}, name="thirdparty")
    rep2 = lf.check_paths([str(data2)], CFG, include_own=True, checker=OkChecker(), use_cache=False,
                          data_dir=str(tmp_path / "none"), level="high")
    rules2 = next(iter(rep2.files.values()))["patch"]["rules"]
    assert "A1" in rules2 and "G1" in rules2


def test_own_mod_sources_do_not_embed_generic_log_shims():
    mods = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lua tools", "MWSE", "mods", "mwsuite")
    for mod in lf.OWN_MODS:
        root = os.path.join(mods, mod)
        if not os.path.isdir(root):
            continue
        for base, _dirs, files in os.walk(root):
            for name in files:
                if name.lower().endswith(".lua"):
                    path = os.path.join(base, name)
                    with open(path, encoding="latin-1") as source:
                        assert "localpatch_logshim" not in source.read(), path


def test_F1_skipped_when_mwguard_runtime_guard_clearly_covers(tmp_path):
    data, root = mod_tree(tmp_path, {"main.lua": SPAM})
    dd = tmp_path / "Data Files"
    (dd / "MWSE" / "mods" / "mwguard").mkdir(parents=True)
    (dd / "MWSE" / "mods" / "mwguard" / "main.lua").write_text("local d = { logSpamGuard = true }")
    rep = lf.check_paths([str(data)], CFG, checker=OkChecker(), use_cache=False, data_dir=str(dd))
    e = next(iter(rep.files.values()))
    assert e["patch"] is None and {f["conf"] for f in e["findings"] if f["rule"] == "F1"} == {"covered"}
    cfg = dict(CFG, logShimWhenMwguard=True)            # asked for anyway -> shim
    rep = lf.check_paths([str(data)], cfg, checker=OkChecker(), use_cache=False, data_dir=str(dd))
    assert next(iter(rep.files.values()))["patch"]["ok"]
    for cfg in (dict(CFG, logExemptMods=["testmod"]), dict(CFG, log=dict(CFG["log"], exemptMods=["TestMod"]))):
        rep = lf.check_paths([str(data)], dict(cfg, logShimWhenMwguard=True), checker=OkChecker(), use_cache=False,
                             data_dir=str(dd))
        assert next(iter(rep.files.values()))["patch"] is None      # exempt: stays in MWSE.log


def test_F2_debug_logger_level_set_to_info():
    src = "local logger = require('logging.logger')\nlocal log = logger.new{ name = 'x', logLevel = 'DEBUG' }\n" \
          "log:setLogLevel(\"TRACE\")\n"
    new = patch(src)
    assert "logLevel = 'INFO'" in new and 'setLogLevel("INFO")' in new


@need_lua
def test_F1_shim_runs_errors_pass_and_spam_goes_to_the_mod_log(tmp_path):
    src = "for i = 1, 100 do mwse.log('line %d', i) end\nmwse.log('Error: something broke')\nprint('a', 'b')\n" \
          "return mwse.version"
    new = lf.log_shim("testmod", dict(CFG, log=dict(CFG["log"], budgetInit=5, perSecond=0))) + src
    logdir = tmp_path / "Data Files" / "MWSE" / "logs"
    logdir.mkdir(parents=True)
    rt = _lj.LuaRuntime()
    rt.execute("lines = {} mwse = { version = 42, log = function(f, ...) lines[#lines + 1] = string.format(f, ...) end }"
               " print = function(s) lines[#lines + 1] = s end lfs = { mkdir = function() end } tes3 = {}")
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert rt.execute(new) == 42                           # mwse.* other than log still reachable
    finally:
        os.chdir(cwd)
    shown = list(rt.globals().lines.values())
    assert shown[:5] == [f"line {i}" for i in range(1, 6)]
    assert not any("further output goes to" in s or "luafix" in s for s in shown)   # no notice of ours
    assert "Error: something broke" in shown and "a" not in shown
    log = logdir / "testmod.log" if os.name == "nt" else tmp_path / "Data Files\\MWSE\\logs\\testmod.log"
    text = log.read_text()
    assert "line 6" in text and "line 100" in text and "a\tb" in text


@need_lua
def test_F1_lifecycle_and_errors_stay_in_mwse_and_are_also_in_the_mod_log(tmp_path):
    src = "mwse.log('ordinary detail')\nmwse.log('Registered handlers')\nmwse.log('Error: broke')\n"
    new = lf.log_shim("testmod", CFG) + src
    logdir = tmp_path / "Data Files" / "MWSE" / "logs"
    logdir.mkdir(parents=True)
    rt = _lj.LuaRuntime()
    rt.execute("lines = {} mwse = { log = function(f, ...) lines[#lines + 1] = string.format(f, ...) end }"
               " print = function(s) lines[#lines + 1] = s end lfs = { mkdir = function() end } tes3 = {}")
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        rt.execute(new)
    finally:
        os.chdir(cwd)
    shown = list(rt.globals().lines.values())
    assert "ordinary detail" not in shown
    assert "Registered handlers" in shown and "Error: broke" in shown
    log = logdir / "testmod.log" if os.name == "nt" else tmp_path / "Data Files\\MWSE\\logs\\testmod.log"
    text = log.read_text()
    assert "ordinary detail" in text and "Registered handlers" in text and "Error: broke" in text


@need_lua
def test_G2_gate_runs_at_most_every_interval():
    new = patch(PUDDLE) + "\nreturn function() return last end"
    rt = _lj.LuaRuntime()
    rt.execute("clockv = 0 os.clock = function() return clockv end scale = 1 "
               "tes3 = { event = { simulate = 'simulate' }, getReference = function() return { scale = scale } end, "
               "messageBox = function() end } event = { register = function(ev, f) handler = f end }")
    last = rt.execute(new)
    g = rt.globals()
    sim = g.handler
    sim({})
    assert last() == 1
    g.scale, g.clockv = 2, 0.1
    sim({})
    assert last() == 1                                        # within 0.35 s: skipped
    g.clockv = 0.5
    sim({})
    assert last() == 2


# ------------------------------------------------------------------------------------------------ safety
def test_core_and_own_mods_are_never_touched(tmp_path):
    for rel in ("MWSE/core/initialize.lua", "MWSE/core/mcm/main.lua", "MWSE/lib/x/init.lua",
                "MWSE/mods/mwguard/main.lua", "MWSE/mods/mwinfoloop/main.lua", "MWSE/config/x.lua"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(PUDDLE)
    rep = lf.check_paths([str(tmp_path)], CFG, checker=OkChecker(), use_cache=False)
    assert rep.files == {} and len(rep.skipped) == 6
    rep = lf.check_paths([str(tmp_path)], CFG, include_own=True, checker=OkChecker(), use_cache=False)
    assert sorted(e["rel"] for e in rep.files.values()) == ["mwguard/main.lua", "mwinfoloop/main.lua"]


def test_known_bugs_patch_exact_third_party_and_core_fingerprints(tmp_path):
    ui = tmp_path / "Data Files/MWSE/mods/UI Expansion/MenuDialog.lua"
    ui.parent.mkdir(parents=True)
    ui.write_text('local info = element:getPropertyObject("") or dialogue:getInfo({ actor = mobileActor })\n')
    core = tmp_path / "Data Files/MWSE/core/mcm/components/pages/ExclusionsPage.lua"
    core.parent.mkdir(parents=True)
    core.write_text("self.elements.outerContainer.parent:destroyChildren()\n\tself:create(self.elements.outerContainer.parent)\n")
    rep = lf.check_paths([str(tmp_path)], CFG, checker=OkChecker(), use_cache=False,
                         data_dir=str(tmp_path / "Data Files"))
    by_rel = {e["rel"]: e for e in rep.files.values()}
    assert by_rel["UI Expansion/MenuDialog.lua"]["patch"]["rules"] == ["KB2"]
    assert by_rel["core/mcm/components/pages/exclusionspage.lua"]["patch"]["rules"] == ["KB3"]
    lines, _ = lf.format_report(rep)
    report = "\n".join(lines)
    assert "(Known Bugs) KB2: line 1: UI Expansion:" in report
    assert "(Known Bugs) KB3: line 1: MWSE Core:" in report
    assert "localpatch_logshim" not in by_rel["core/mcm/components/pages/exclusionspage.lua"]["patch"]["text"]
    bug_lines = lf.known_bug_report_lines(rep)
    assert any("DETECTED: (Known Bugs) KB2: UI Expansion:" in line for line in bug_lines)
    assert any("DETECTED: (Known Bugs) KB3: MWSE Core:" in line for line in bug_lines)


def test_Y1_repairs_muse_mcm_calls_even_when_original_does_not_compile(tmp_path):
    source = '''local category = {}
category:createInfo
{
    text = "Music control"
}
category:createOnOffButton
    ({
        label = "Region music queuing",
    })
category:createOnOffButton
    ({
        label = "Other setting",
    })
'''
    path = tmp_path / "Data Files" / "MWSE" / "mods" / "music" / "MUSE.lua"
    path.parent.mkdir(parents=True)
    path.write_bytes(source.encode("latin-1"))

    class MUSEChecker:
        name = "MUSE syntax regression"

        def check(self, text):
            if "category:createOnOffButton\n    (" in text:
                return False, "ambiguous syntax (function call x new statement)"
            return True, ""

    rep = lf.check_paths([str(tmp_path)], CFG, checker=MUSEChecker(), use_cache=False,
                         data_dir=str(tmp_path / "Data Files"))
    entry = next(iter(rep.files.values()))
    # KB5 was retired on 2026-11-26: Y1 (any call whose '(' is on a later line) repairs it, line numbers kept
    assert [f["rule"] for f in entry["findings"] if f["rule"] == "Y1"] == ["Y1", "Y1"]
    assert entry["patch"]["ok"] and entry["patch"]["rules"] == ["Y1"]
    assert "category:createOnOffButton\n    (" not in entry["patch"]["text"]
    assert entry["patch"]["text"].count("category:createOnOffButton(") == 2
    assert entry["patch"]["text"].count("\n") == source.count("\n")


def test_KB6_repairs_enchanted_weapon_condition_only_at_matching_path():
    source = ("local weapon, weacon = ...\n"
              "        weacon.widget.current = weapon.itemData.condition\n"
              "        weacon.widget.max = weapon.object.maxCondition\n"
              "        if weapon.itemData then\n        end\n")
    analysis = analyse(source, "spammer/openui - mwse/mod.lua")
    findings = [f for f in analysis.findings if f["rule"] == "KB6"]
    assert len(findings) == 1
    repaired, applied = lf.build_patch(source, findings, "openui", CFG, "high", False)
    assert applied == ["KB6"]
    assert not [f for f in analyse(source, "another/mod.lua").findings if f["rule"] == "KB6"]
    assert not [f for f in analyse(repaired, "spammer/openui - mwse/mod.lua").findings if f["rule"] == "KB6"]
    luajit = os.environ.get("MWMANAGER_LUAJIT",
                            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "luajit", "luajit.exe"))
    if not os.path.isfile(luajit):
        pytest.skip("LuaJIT executable not available for behavioral verification")
    script = ("local chunk = assert(loadstring([==[" + repaired + "]==]))\n"
              "local function check(data, expected)\n"
              "  local gauge = {widget = {}}\n"
              "  chunk({object = {maxCondition = 100}, itemData = data}, gauge)\n"
              "  assert(gauge.widget.current == expected and gauge.widget.max == 100)\n"
              "end\ncheck(nil, 100)\ncheck({condition = 37}, 37)\ncheck({condition = 0}, 0)\n")
    result = subprocess.run([luajit, "-"], input=script, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


FRENS_LUA = """local icon = include("SSQN.interop")

---@param e loadedEventData
local function loaded(e)
\tif icon then
\t\ticon.registerQIcon("aa_ff", "ffrens.dds")
\tend
    if e.newGame then
        randomiseCompanions()
    end
end

event.register("loaded", loaded)"""


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_KB7_names_a_friends_and_frens_companions_own_birthsign(eol):
    source = FRENS_LUA.replace("\n", eol)
    findings = [f for f in analyse(source, "danae/frens/main.lua").findings if f["rule"] == "KB7"]
    assert len(findings) == 1
    assert not [f for f in analyse(source, "another/main.lua").findings if f["rule"] == "KB7"]
    repaired, applied = lf.build_patch(source, findings, "danae", CFG, "high", False)
    assert applied == ["KB7"] and repaired.count("\n") == repaired.count(eol)
    assert not [f for f in analyse(repaired, "danae/frens/main.lua").findings if f["rule"] == "KB7"]
    assert lf.verify_patch(source, repaired, applied, None, "danae", "danae/frens/main.lua", CFG, "high")["ok"]
    luajit = os.environ.get("MWMANAGER_LUAJIT", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "luajit", "luajit.exe"))
    if not os.path.isfile(luajit):
        pytest.skip("LuaJIT executable not available for behavioral verification")
    script = r"""
local handlers, speaker, reads = {}, nil, 0
include = function() end
event = { register = function(name, fn) handlers[name] = fn end }
tes3ui = { getServiceActor = function() return speaker end }
local LINE = "I am %Name, born under the sign of the %Sign, walking the path of the %Class"
assert(loadstring([==[SOURCE]==]))()
assert(handlers.loaded, "the mod's own handler is kept")
local function shown(context, original, already)
  speaker = context and { reference = { context = context ~= "none" and context or nil } } or nil
  reads = 0
  local e = { text = already, loadOriginalText = function() reads = reads + 1; return original or LINE end }
  handlers.infoGetText(e)
  return e.text
end
local names = { "Tower", "Ritual", "Steed", "Apprentice", "Mage", "Thief", "Lady", "Lover", "Shadow", "Serpent",
                "Lord", "Warrior", "Atronach" }
for n, name in ipairs(names) do
  assert(shown({ birthsign = n }) == "I am %Name, born under the sign of the " .. name .. ", walking the path of the %Class", name)
end
assert(shown({ birthsign = 0 }) == "I am %Name, born under a sign I never learned, walking the path of the %Class", "no sign")
assert(shown({ birthsign = 13 }, "Very well.") == nil, "other lines are left alone")
assert(shown({ birthsign = 13 }, LINE, "A %Sign") == "A Atronach" and reads == 0, "another mod's text is kept")
assert(shown(nil) == nil and reads == 0, "no speaker: nothing read")
assert(shown("none") == nil and reads == 0, "no script: nothing read")
assert(shown({}) == nil and reads == 0, "not a companion: nothing read")
"""
    result = subprocess.run([luajit, "-"], input=script.replace("SOURCE", repaired.replace("\r", "")),
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


TD_INVISIBILITY_LUA = """local this = {}
local invisibleReferences = {}

local function detectInvisibilityValid(ref)
\tif ref == tes3.player or not ref.mobile then return false end

\tfor _, spell in pairs(tes3.getSpells({ target = ref })) do
\t\tif spell == "ghost ability" then return false end
\tend

\treturn true
end

---@param e magicEffectActivatedEventData
function this.onInvisibilityEffectActivated(e)
\tif e.target and e.target ~= tes3.player and not invisibleReferences[e.target] then
\t\tif detectInvisibilityValid(e.target) then
\t\t\tinvisibleReferences[e.target] = true
\t\tend
\tend
end

this.valid, this.invisible = detectInvisibilityValid, invisibleReferences
return this
"""


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_KB8_tamriel_data_waits_for_the_save_to_load_before_reading_spells(eol):
    source = TD_INVISIBILITY_LUA.replace("\n", eol)
    path = "tamrieldata/magic.lua"
    findings = [f for f in analyse(source, path).findings if f["rule"] == "KB8"]
    assert len(findings) == 2
    assert not [f for f in analyse(source, "another/magic.lua").findings if f["rule"] == "KB8"]
    repaired, applied = lf.build_patch(source, findings, "tamrieldata", CFG, "high", False)
    assert set(applied) == {"KB8"} and repaired.count("\n") == repaired.count(eol)
    assert not [f for f in analyse(repaired, path).findings if f["rule"] == "KB8"]
    assert lf.verify_patch(source, repaired, applied, None, "tamrieldata", path, CFG, "high")["ok"]
    luajit = os.environ.get("MWMANAGER_LUAJIT", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "luajit", "luajit.exe"))
    if not os.path.isfile(luajit):
        pytest.skip("LuaJIT executable not available for behavioral verification")
    script = r"""
local handlers, resolved = {}, true
event = { register = function(name, fn) handlers[name] = handlers[name] or {}; table.insert(handlers[name], fn) end }
local function fire(name, e) for _, fn in ipairs(handlers[name] or {}) do fn(e or {}) end end
tes3 = { event = { load = "load", loaded = "loaded", simulate = "simulate" }, player = {},
         makeSafeObjectHandle = function(r)
           return { valid = function() return not r.gone end, getObject = function() return r end }
         end,
         getSpells = function(p)
           assert(resolved, "spell list read while the save is loading")
           return p.target.spells
         end }
local mod = assert(loadstring([==[SOURCE]==]))()
local function actor(spell) return { mobile = {}, spells = { spell } } end
local ghost, sneak, gone = actor("ghost ability"), actor("chameleon"), actor("chameleon")

fire("load"); resolved = false
for _, r in ipairs({ ghost, sneak, gone }) do mod.onInvisibilityEffectActivated({ target = r }) end
assert(mod.valid(sneak) == false, "the detection tick waits too")
resolved, gone.gone = true, true
fire("loaded")
assert(mod.invisible[sneak] and not mod.invisible[ghost] and not mod.invisible[gone], "judged once loaded")

local later = actor("chameleon")
mod.onInvisibilityEffectActivated({ target = later })
assert(mod.invisible[later], "at once outside a load")

fire("load"); resolved = false                      -- a load the player cancels at the missing-files prompt
local waiting = actor("chameleon")
mod.onInvisibilityEffectActivated({ target = waiting })
resolved = true
fire("simulate")
assert(mod.invisible[waiting] and mod.valid(waiting), "never left waiting")
"""
    result = subprocess.run([luajit, "-"], input=script.replace("SOURCE", repaired.replace("\r", "")),
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


SUNRAYS_LUA = """local ffi = require("ffi")
local TES3_WeatherController_updateSun = ffi.cast("void(__thiscall*)(void*, float)", 0x43FF80)

local function updateSun()
    local this = ffi.cast("void*", mwse.memory.addressOf(tes3.worldController.weatherController))
    TES3_WeatherController_updateSun(this, tes3.worldController.hour.value)\t\t-- Updates sceneSunVis
end

local function disableSunrays(e)
\tif TES3_WeatherController_updateSun then
\t\tdo
\t\t\tupdateSun()
\t\t\tlocal sunPosition = tes3.worldController.weatherController.sceneSunVis.translation
\t\t\tseen = sunPosition
\t\tend
\tend
end
return disableSunrays
"""


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_KB9_sunrays_skip_the_engine_sun_update_until_there_is_weather(eol):
    source = SUNRAYS_LUA.replace("\n", eol)
    path = "directionalsunrays/main.lua"
    findings = [f for f in analyse(source, path).findings if f["rule"] == "KB9"]
    assert len(findings) == 2
    assert not [f for f in analyse(source, "another/main.lua").findings if f["rule"] == "KB9"]
    repaired, applied = lf.build_patch(source, findings, "directionalsunrays", CFG, "high", False)
    assert set(applied) == {"KB9"} and repaired.count("\n") == repaired.count(eol)
    assert not [f for f in analyse(repaired, path).findings if f["rule"] == "KB9"]
    assert lf.verify_patch(source, repaired, applied, None, "directionalsunrays", path, CFG, "high")["ok"]
    luajit = os.environ.get("MWMANAGER_LUAJIT", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "luajit", "luajit.exe"))
    if not os.path.isfile(luajit):
        pytest.skip("LuaJIT executable not available for behavioral verification")
    script = r"""
local calls = 0
package.loaded.ffi = { cast = function(_t, v)
  if v == 0x43FF80 then return function(this) assert(this.currentWeather, "engine crash"); calls = calls + 1 end end
  return v end }
mwse = { memory = { addressOf = function(o) return o end } }
local wc = { sceneSunVis = { translation = "sun" } }
tes3 = { worldController = { weatherController = wc, hour = { value = 12 } } }
local tick = assert(loadstring([==[SOURCE]==]))()
tick({})
assert(calls == 0 and seen == nil, "no weather yet: skipped")
wc.currentWeather = {}
tick({})
assert(calls == 1 and seen == "sun", "updated once there is weather")
"""
    result = subprocess.run([luajit, "-"], input=script.replace("SOURCE", repaired.replace("\r", "")),
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


ROBENHOOD_LUA = """local staticConfig = { itemWeatherMap = { [4] = { item = "hood_lv" } } }
local logger = { trace = function() end, debug = function() end }
local function alreadyHasHelm() return false end
local function getHoodForRobedNPC() return nil end
local function getHatWeather() return nil end

local function isBadWeather(weather)
    weather = weather or tes3.getCurrentWeather()
    local weatherIsBad = staticConfig.itemWeatherMap[weather.index] ~= nil
    logger:trace("%s is %sbad weather", weather, weatherIsBad and "" or "not ")
    return weatherIsBad
end

local function getHatFromWeather(npc, weather)
    logger:trace("Getting hat from weather")
    local item
    item = getHatWeather(npc, weather)
    if item then return item end
    return staticConfig.itemWeatherMap[weather.index] and "hood_picked" or nil
end

local function findHat(npc, weather)
    logger:debug("findHat: finding hat for %s in weather %s", npc, weather.name)
    local item = getHoodForRobedNPC(npc)
    if item == nil and not alreadyHasHelm(npc) then
        item = getHatFromWeather(npc, weather)
    end
    return item
end

return { isBadWeather = isBadWeather, getHatFromWeather = getHatFromWeather, findHat = findHat }
"""


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_KB10_robenhood_guards_nil_weather_after_new_game(eol):
    source = ROBENHOOD_LUA.replace("\n", eol)
    path = "robenhood/main.lua"
    findings = [f for f in analyse(source, path).findings if f["rule"] == "KB10"]
    assert len(findings) == 3
    assert not [f for f in analyse(source, "another/main.lua").findings if f["rule"] == "KB10"]
    repaired, applied = lf.build_patch(source, findings, "Robe'n'Hood", CFG, "high", False)
    assert set(applied) == {"KB10"} and repaired.count("\n") == repaired.count(eol)
    assert not [f for f in analyse(repaired, path).findings if f["rule"] == "KB10"]
    assert lf.verify_patch(source, repaired, applied, None, "Robe'n'Hood", path, CFG, "high")["ok"]
    luajit = os.environ.get("MWMANAGER_LUAJIT", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "luajit", "luajit.exe"))
    if not os.path.isfile(luajit):
        pytest.skip("LuaJIT executable not available for behavioral verification")
    script = r"""
local cur = nil
tes3 = { getCurrentWeather = function() return cur end }
local mod = assert(loadstring([==[SOURCE]==]))()
assert(mod.isBadWeather(nil) == false)
assert(mod.getHatFromWeather("npc", nil) == nil)
assert(mod.findHat("npc", nil) == nil)
cur = { index = 4, name = "Rain" }
assert(mod.isBadWeather(nil) == true)
assert(mod.findHat("npc", cur) == "hood_picked")
"""
    result = subprocess.run([luajit, "-"], input=script.replace("SOURCE", repaired.replace("\r", "")),
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


NM_UTIL_LUA = """local niceWeather = { [0] = true }
local util = {}
function util.isNiceWeather()
	return niceWeather[tes3.worldController.weatherController.currentWeather.index] or false
end
return util
"""

NM_MANAGER_LUA = """local Class = { new = function() return {} end }
local EffectManager = Class:new()
function EffectManager:new()
	local t = Class:new()
	setmetatable(t, self)

	t.activeEffects = {}
	t.nextUpdateTimestamp = -1
	t.lastUpdateState = {}

	self.__index = self
	return t
end


-- Sets appCulled state of moths node on given reference.
return EffectManager
"""

NM_MAIN_LUA = """local effectManager = require("nm_manager"):new()
local function onCellChanged()
	effectManager:onCellChanged()
end
event.register(tes3.event.cellChanged, onCellChanged)

event.register(tes3.event.keyDown, function() end)
return effectManager
"""


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_KB11_nocturnal_moths_guards_nil_weather_and_resets_on_load(eol, tmp_path):
    files = {
        "util/init.lua": NM_UTIL_LUA.replace("\n", eol),
        "effectManager.lua": NM_MANAGER_LUA.replace("\n", eol),
        "main.lua": NM_MAIN_LUA.replace("\n", eol),
    }
    mod_root, _ = mod_tree(tmp_path, files, name="Nocturnal Moths")
    res = lf.check_paths([str(mod_root)], CFG, use_cache=False, data_dir=str(tmp_path / "none"))
    repaired = {}
    for rel, src in files.items():
        p = str(mod_root / "MWSE" / "mods" / "Nocturnal Moths" / rel)
        ent = res.files[p]
        kb = [f for f in ent["findings"] if f["rule"] == "KB11"]
        assert len(kb) == 1, (rel, kb)
        out, applied = lf.build_patch(src, kb, "Nocturnal Moths", CFG, "high", False)
        assert set(applied) == {"KB11"} and out.count("\n") == out.count(eol)
        assert lf.verify_patch(src, out, applied, None, "Nocturnal Moths", f"nocturnal moths/{rel}", CFG, "high")["ok"]
        assert not [f for f in analyse(out, f"nocturnal moths/{rel}").findings if f["rule"] == "KB11"]
        repaired[rel] = out.replace("\r", "")
    assert "KB11" in lf.KNOWN_BUGS_WHOLE
    luajit = os.environ.get("MWMANAGER_LUAJIT", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "luajit", "luajit.exe"))
    if not os.path.isfile(luajit):
        pytest.skip("LuaJIT executable not available for behavioral verification")
    script = r"""
local handlers = {}
util = { stopSound = function() end }      -- a local of EffectManager.lua in the mod
event = { register = function(name, fn) handlers[name] = fn end }
local wc = { currentWeather = nil }
tes3 = {
  event = { cellChanged = "cellChanged", keyDown = "keyDown", load = "load" },
  worldController = { weatherController = wc },
}
package.preload["nm_manager"] = function() return assert(loadstring([==[MANAGER]==]))() end
local util = assert(loadstring([==[UTIL]==]))()
assert(util.isNiceWeather() == false)
wc.currentWeather = { index = 0 }
assert(util.isNiceWeather() == true)
local em = assert(loadstring([==[MAIN]==]))()
em.activeEffects["oldRef"] = "node"
em.nextUpdateTimestamp = 99999
em.lastUpdateState = { isNight = true }
handlers.load()
assert(next(em.activeEffects) == nil and em.nextUpdateTimestamp == -1 and next(em.lastUpdateState) == nil)
"""
    script = (script.replace("MANAGER", repaired["effectManager.lua"])
                    .replace("UTIL", repaired["util/init.lua"])
                    .replace("MAIN", repaired["main.lua"]))
    result = subprocess.run([luajit, "-"], input=script, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


TD_WEATHER_LUA = """local this = {}
local defaultStormOrigin = "default"
local region_storm_origins = {}
function this.changeStormOrigin(e)
	local weather
	if not e.to then
		weather = tes3.getCurrentWeather()
	else
		weather = e.to
	end

	if weather and weather.index == tes3.weather.ash or weather.index == tes3.weather.blight then
		weather.stormOrigin = defaultStormOrigin
	end
end

function this.silenceCreatures(e)
	if e.sound.id == "T_SndCrea_SeagullScream1" or e.sound.id == "T_SndCrea_SeagullScream2" or e.sound.id == "T_SndCrea_SeagullFlap" then	-- Could also account for T_SndCrea_MastreeveMoan, T_SndCrea_MastreeveRoar, T_SndCrea_MastreeveScream?
		if tes3.getCurrentWeather().index == tes3.weather.ash then
			return false
		end
	end
end
return this
"""


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_KB12_tamriel_data_weather_guards_nil_weather(eol):
    source = TD_WEATHER_LUA.replace("\n", eol)
    path = "tamrieldata/weather.lua"
    findings = [f for f in analyse(source, path).findings if f["rule"] == "KB12"]
    assert len(findings) == 2
    assert not [f for f in analyse(source, "another/weather.lua").findings if f["rule"] == "KB12"]
    repaired, applied = lf.build_patch(source, findings, "Tamriel Data", CFG, "high", False)
    assert set(applied) == {"KB12"} and repaired.count("\n") == repaired.count(eol)
    assert not [f for f in analyse(repaired, path).findings if f["rule"] == "KB12"]
    assert lf.verify_patch(source, repaired, applied, None, "Tamriel Data", path, CFG, "high")["ok"]
    luajit = os.environ.get("MWMANAGER_LUAJIT", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "luajit", "luajit.exe"))
    if not os.path.isfile(luajit):
        pytest.skip("LuaJIT executable not available for behavioral verification")
    script = r"""
local cur = nil
tes3 = { weather = { ash = 4, blight = 5 }, getCurrentWeather = function() return cur end }
local w = assert(loadstring([==[SOURCE]==]))()
w.changeStormOrigin({})
assert(w.silenceCreatures({ sound = { id = "T_SndCrea_SeagullScream1" } }) == nil)
cur = { index = 5 }
w.changeStormOrigin({})
assert(cur.stormOrigin == "default")
cur = { index = 4 }
assert(w.silenceCreatures({ sound = { id = "T_SndCrea_SeagullScream1" } }) == false)
"""
    result = subprocess.run([luajit, "-"], input=script.replace("SOURCE", repaired.replace("\r", "")),
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


UIEX_COMMON_LUA = """local common = {}
function common.createSearchBar(p)
	local border = p.parent:createThinBorder()
	return { border = border, input = { text = "", color = nil } }
end
local uiExFilterFunction = {}
uiExFilterFunction.__index = uiExFilterFunction

function uiExFilterFunction:setFiltersExact(params)
	params = params or {}
	self.searchText = params.text
	if (self.createSearchBar and self.searchText == nil and self.searchBlock ~= nil) then
		self.searchBlock.input.text = self.searchTextPlaceholder
	end
	for _, filter in pairs(self.filtersOrdered) do
		if (filter.iconElement) then
			filter.iconElement.alpha = 1.0
		end
		if (filter.buttonElement) then
			filter.buttonElement.visible = true
		end
	end
end

function uiExFilterFunction:createElements(parent)
	local searchBarParams = { parent = parent }
	self.searchBlock = common.createSearchBar(searchBarParams)

	-- Create icons for filtering.
	if (self.createIcons) then
		local block = parent:createThinBorder({})
		self.iconFiltersBlock = block
		block:registerBefore("destroy", function()
			self.iconFiltersBlock = nil
		end)
		self.filtersOrdered[1].iconElement = { alpha = 0 }
	end
	if (self.createButtons) then
		local block = parent:createBlock({})
		self.buttonFiltersBlock = block
		block:registerBefore("destroy", function()
			self.buttonFiltersBlock = nil
		end)
		self.filtersOrdered[1].buttonElement = { visible = false }
	end
end
return { common = common, mt = uiExFilterFunction }
"""


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_KB13_ui_expansion_clears_searchBlock_and_filter_elements_on_destroy(eol):
    source = UIEX_COMMON_LUA.replace("\n", eol)
    path = "ui expansion/common.lua"
    findings = [f for f in analyse(source, path).findings if f["rule"] == "KB13"]
    assert len(findings) == 3
    assert not [f for f in analyse(source, "another/common.lua").findings if f["rule"] == "KB13"]
    partial = source.replace("\t\tself.buttonFiltersBlock = block", "\t\tself.other = block")
    assert [f for f in analyse(partial, path).findings if f["rule"] == "KB13" and f["conf"] == "report"]
    assert not [f for f in analyse(partial, path).findings if f["rule"] == "KB13" and f["edits"]]
    repaired, applied = lf.build_patch(source, findings, "UI Expansion", CFG, "high", False)
    assert set(applied) == {"KB13"} and repaired.count("\n") == repaired.count(eol)
    assert not [f for f in analyse(repaired, path).findings if f["rule"] == "KB13"]
    assert lf.verify_patch(source, repaired, applied, None, "UI Expansion", path, CFG, "high")["ok"]
    luajit = os.environ.get("MWMANAGER_LUAJIT", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "luajit", "luajit.exe"))
    if not os.path.isfile(luajit):
        pytest.skip("LuaJIT executable not available for behavioral verification")
    script = r"""
local destroyCbs = {}
local function makeEl()
  local el = {}
  function el:registerBefore(ev, fn) if ev == "destroy" then table.insert(destroyCbs, fn) end end
  function el:createThinBorder() return makeEl() end
  function el:createBlock() return makeEl() end
  return el
end
local m = assert(loadstring([==[SOURCE]==]))()
local f = setmetatable({
  createSearchBar = true, createIcons = true, createButtons = true,
  searchTextPlaceholder = "Search", filtersOrdered = { {} },
}, m.mt)
f:createElements(makeEl())
assert(f.searchBlock ~= nil and f.filtersOrdered[1].iconElement ~= nil and f.filtersOrdered[1].buttonElement ~= nil)
for _, fn in ipairs(destroyCbs) do fn() end
assert(f.searchBlock == nil and f.iconFiltersBlock == nil and f.buttonFiltersBlock == nil)
assert(f.filtersOrdered[1].iconElement == nil and f.filtersOrdered[1].buttonElement == nil)
f:setFiltersExact()
"""
    result = subprocess.run([luajit, "-"], input=script.replace("SOURCE", repaired.replace("\r", "")),
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


MWSE_FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "mwse")


def test_KB3_KB4_page_stock_mwse_exclusions_page_exactly_once():
    stock = open(os.path.join(MWSE_FIX, "ExclusionsPage.lua"), encoding="latin-1").read()
    paged = open(os.path.join(MWSE_FIX, "ExclusionsPage.paged.lua"), encoding="latin-1").read()
    rel = "core/mcm/components/pages/exclusionspage.lua"
    for eol in ("\n", "\r\n"):
        src = stock.replace("\n", eol)
        findings = [f for f in lf.FileAnalysis(src, "MWSE Core", rel, CFG).run() if f["rule"].startswith("KB")]
        repaired, rules = lf.build_patch(src, findings, "MWSE Core", CFG)
        assert rules == ["KB3", "KB4"] and repaired.startswith("--[[localpatch ")
        assert repaired.split("]] ", 1)[1] == paged.replace("\n", eol)
        again = [f for f in lf.FileAnalysis(repaired, "MWSE Core", rel, CFG).run() if f["rule"].startswith("KB")]
        assert again == []                                              # patched once, never twice
    assert [f for f in lf.FileAnalysis(paged, "MWSE Core", rel, CFG).run() if f["rule"].startswith("KB")] == []


def test_KB4_applies_whole_or_not_at_all():
    stock = open(os.path.join(MWSE_FIX, "ExclusionsPage.lua"), encoding="latin-1").read()
    changed = stock.replace("\n\n--- Constructor", "\n-- changed upstream\n--- Constructor")
    findings = lf.FileAnalysis(changed, "MWSE Core", "core/mcm/components/pages/exclusionspage.lua", CFG).run()
    kb4 = [f for f in findings if f["rule"] == "KB4"]
    assert len(kb4) == 1 and kb4[0]["conf"] == "report" and not kb4[0]["edits"]
    assert "2 of its 3 parts" in kb4[0]["what"]
    _repaired, rules = lf.build_patch(changed, findings, "MWSE Core", CFG)
    assert rules == ["KB3"]


def test_own_mods_do_not_get_shims_when_included(tmp_path):
    src = "mwse.log('ordinary detail')\nevent.register('x', f, { priority = 10000 })\n"
    data, _root = mod_tree(tmp_path, {"main.lua": src}, name="mwmouseguard")
    rep = lf.check_paths([str(data)], CFG, include_own=True, checker=OkChecker(), use_cache=False,
                         data_dir=str(tmp_path / "none"))
    e = next(iter(rep.files.values()))
    assert e["patch"] is None


def test_mwhangwatch_log_is_under_mwse_logs():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "lua tools", "MWSE", "mods", "mwsuite", "mwhangwatch",
                        "main.lua")
    text = open(path, encoding="utf-8").read()
    assert 'local LOG_DIR      = "Data Files\\\\MWSE\\\\logs"' in text
    assert 'local LOG_NAME     = LOG_DIR .. "\\\\mwhangwatch.log"' in text


def test_syntax_checker_rejects_patch_and_bad_original(tmp_path):
    data, root = mod_tree(tmp_path, {"main.lua": PUDDLE})
    rep = lf.check_paths([str(data)], CFG, checker=OkChecker(reject_new=True), use_cache=False)
    pt = next(iter(rep.files.values()))["patch"]
    assert not pt["ok"] and "rejects the patched text" in pt["why"]
    rep = lf.check_paths([str(data)], CFG, checker=OkChecker(ok=False), use_cache=False)
    pt = next(iter(rep.files.values()))["patch"]
    assert not pt["ok"] and "original doesn't compile" in pt["why"]
    w, refused = lf.apply_report(rep, journal=str(tmp_path / "j.jsonl"), backup_root=str(tmp_path / "bk"), log=lambda s: 0)
    assert w == 0 and refused and (root / "main.lua").read_text() == PUDDLE


def test_unparseable_file_is_left_alone(tmp_path):
    data, root = mod_tree(tmp_path, {"main.lua": "local x = = 1\n" + PUDDLE})
    rep = lf.check_paths([str(data)], CFG, checker=OkChecker(), use_cache=False)
    e = next(iter(rep.files.values()))
    assert e["error"] and e["patch"] is None


def test_apply_in_place_keeps_hard_link_and_undo_restores(tmp_path):
    crlf = PUDDLE.replace("\n", "\r\n").replace("bigger", "bigger \xe9").encode("latin-1")
    data, root = mod_tree(tmp_path, {"main.lua": crlf})
    linked = tmp_path / "DataFiles_main.lua"
    os.link(root / "main.lua", linked)                       # Vortex's hard link into Data Files
    j, bk = tmp_path / "j.jsonl", tmp_path / "bk"
    rep = lf.check_paths([str(data)], CFG, checker=OkChecker(), use_cache=False)
    w, refused = lf.apply_report(rep, journal=str(j), backup_root=str(bk), log=lambda s: 0)
    assert w == 1 and not refused
    new = (root / "main.lua").read_bytes()
    assert linked.read_bytes() == new and os.path.samefile(root / "main.lua", linked)
    assert new.count(b"\r\n") == crlf.count(b"\r\n") and b"bigger \xe9" in new      # line endings, bytes kept
    # idempotent: a second run patches nothing
    rep2 = lf.check_paths([str(data)], CFG, checker=OkChecker(), use_cache=False)
    assert not any(e.get("patch") for e in rep2.files.values())
    assert lf.undo(str(j), log=lambda s: 0) == 0
    assert (root / "main.lua").read_bytes() == crlf and os.path.samefile(root / "main.lua", linked)


def test_backup_and_journal_reach_the_disk_before_the_original_changes(tmp_path, monkeypatch):
    data, root = mod_tree(tmp_path, {"main.lua": PUDDLE})
    j, bk = tmp_path / "j.jsonl", tmp_path / "bk"
    rep = lf.check_paths([str(data)], CFG, checker=OkChecker(), use_cache=False)
    synced, real_fsync, real_write = [], os.fsync, lf.write_in_place

    def fsync(fd):
        synced.append(fd)
        real_fsync(fd)

    def write(path, data):
        assert len(synced) >= 2, f"backup and journal not synced before the write ({len(synced)} sync(s))"
        real_write(path, data)

    monkeypatch.setattr(lf.os, "fsync", fsync)
    monkeypatch.setattr(lf, "write_in_place", write)
    w, refused = lf.apply_report(rep, journal=str(j), backup_root=str(bk), log=lambda s: 0)
    assert w == 1 and not refused


def test_undo_refuses_a_file_changed_since(tmp_path):
    data, root = mod_tree(tmp_path, {"main.lua": PUDDLE})
    j = tmp_path / "j.jsonl"
    rep = lf.check_paths([str(data)], CFG, checker=OkChecker(), use_cache=False)
    lf.apply_report(rep, journal=str(j), backup_root=str(tmp_path / "bk"), log=lambda s: 0)
    (root / "main.lua").write_text("-- edited by hand\n")
    assert lf.undo(str(j), log=lambda s: 0) == 1
    assert (root / "main.lua").read_text() == "-- edited by hand\n"
    assert lf.undo(str(j), force=True, log=lambda s: 0) == 0 and (root / "main.lua").read_text() == PUDDLE


def test_cache_skips_unchanged_files(tmp_path, monkeypatch):
    ah = _load("mwdialog_assets")
    data, root = mod_tree(tmp_path, {"main.lua": PUDDLE, "util.lua": "return {}"})
    game = tmp_path / "game"
    game.mkdir()
    lf.check_paths([str(data)], CFG, checker=OkChecker(), game_dir=str(game))
    ah.shared_cache(str(game)).flush()
    calls = []
    orig = lf.FileAnalysis.__init__
    monkeypatch.setattr(lf.FileAnalysis, "__init__", lambda self, *a, **k: (calls.append(a[2]), orig(self, *a, **k))[1])
    rep2 = lf.check_paths([str(data)], CFG, checker=OkChecker(), game_dir=str(game))
    assert "testmod/util.lua" not in calls                     # unchanged and nothing to fix: from the cache
    assert [e["rel"] for e in rep2.files.values() if e.get("patch")] == ["testmod/main.lua"]
    ah.close_caches()


def test_cache_invalidates_when_known_bug_rules_change(tmp_path, monkeypatch):
    ah = _load("mwdialog_assets")
    data, _root = mod_tree(tmp_path, {"main.lua": 'return "before"\n'})
    game = tmp_path / "game"
    game.mkdir()
    lf.check_paths([str(data)], CFG, checker=OkChecker(), game_dir=str(game))
    ah.shared_cache(str(game)).flush()

    monkeypatch.setattr(lf, "KNOWN_BUGS", lf.KNOWN_BUGS + [
        ("KB_TEST", "testmod", "testmod/main.lua", 'return "before"', 'return "after"', "cache test")
    ])
    rep = lf.check_paths([str(data)], CFG, checker=OkChecker(), game_dir=str(game))
    entry = next(iter(rep.files.values()))
    assert entry["patch"]["rules"] == ["KB_TEST"]
    assert 'return "after"' in entry["patch"]["text"]
    ah.close_caches()


def test_shebang_and_bom_keep_their_place():
    src = "\xef\xbb\xbf" + PUDDLE
    assert patch(src).startswith("\xef\xbb\xbf--[[localpatch")
    src = "#!/usr/bin/lua\n" + PUDDLE
    assert patch(src).startswith("#!/usr/bin/lua\n--[[localpatch")


def test_config_from_mwguard_json(tmp_path):
    dd = tmp_path / "Data Files"
    (dd / "MWSE" / "config").mkdir(parents=True)
    (dd / "MWSE" / "config" / "mwguard.json").write_text(json.dumps(
        {"priorityLimit": 5000, "costMs": 1, "luafix": {"minInterval": 0.5}}))
    cfg = lf.load_config(str(tmp_path), str(dd))
    assert cfg["priorityLimit"] == 5000 and cfg["minInterval"] == 0.5 and "costMs" not in cfg


# ------------------------------------------------------------------------------------------------ tidy wiring
def test_tidy_plan_lists_lua_and_apply_undo_round_trip(tmp_path, monkeypatch, capsys):
    staging = tmp_path / "staging"
    mod = staging / "Puddle Mod-123-1-0"
    (mod / "MWSE" / "mods" / "puddle").mkdir(parents=True)
    (mod / "MWSE" / "mods" / "puddle" / "main.lua").write_text(PUDDLE)
    monkeypatch.setattr(vt, "JOURNAL", str(tmp_path / "tidy_journal.jsonl"))
    monkeypatch.setattr(vt, "PLAN", str(tmp_path / "plan.txt"))
    monkeypatch.setattr(vt, "BLACKLIST_FILE", str(tmp_path / "bl.txt"))
    monkeypatch.setattr(vt, "HERE", str(tmp_path))
    monkeypatch.setattr(lf, "find_checker", lambda *a, **k: OkChecker())
    monkeypatch.setattr(lf, "BACKUP_ROOT", str(tmp_path / "bk"))
    monkeypatch.setattr(lf.apply_report, "__defaults__", (lf.JOURNAL, str(tmp_path / "bk"), None, print, None, None))
    monkeypatch.setattr(sys, "argv", ["vortex_tidy.py", "--staging", str(staging), "--lua-only"])
    assert vt.main() == 0
    out = capsys.readouterr().out
    assert "LUA CHECK" in out and "G2" in out and "1 Lua file(s) to patch" in out
    assert (mod / "MWSE" / "mods" / "puddle" / "main.lua").read_text() == PUDDLE
    monkeypatch.setattr(sys, "argv", ["vortex_tidy.py", "--staging", str(staging), "--lua-only", "--apply", "--yes"])
    assert vt.main() == 0
    assert "localpatch_gate(1" in (mod / "MWSE" / "mods" / "puddle" / "main.lua").read_text()
    assert vt.undo() == 0
    assert (mod / "MWSE" / "mods" / "puddle" / "main.lua").read_text() == PUDDLE


def test_tidy_no_lua_skips_it(tmp_path, monkeypatch, capsys):
    staging = tmp_path / "staging"
    (staging / "M" / "MWSE" / "mods" / "m").mkdir(parents=True)
    (staging / "M" / "MWSE" / "mods" / "m" / "main.lua").write_text(PUDDLE)
    monkeypatch.setattr(vt, "PLAN", str(tmp_path / "plan.txt"))
    monkeypatch.setattr(vt, "BLACKLIST_FILE", str(tmp_path / "bl.txt"))
    monkeypatch.setattr(sys, "argv", ["vortex_tidy.py", "--staging", str(staging), "--no-lua", "--no-assets"])
    assert vt.main() == 0
    assert "LUA CHECK" not in capsys.readouterr().out


def test_G4_one_shot_registered_again_on_load_still_fixed_and_equivalent():
    src = ONESHOT + "event.register('loaded', function() event.register(tes3.event.cellChanged, waitForQuest) end)\n"
    new = patch(src)
    assert "done = true event.unregister(tes3.event.cellChanged, waitForQuest)" in new   # flag never reset:
    # after the unregister a load registers it again and it returns at once, exactly as before


def test_H1_toggle_pattern_guard_is_behaviour_preserving():
    src = ("local function onSim(e) end\nlocal function onAct(e) event.register('simulate', onSim) end\n"
           "local function onDeact(e) event.unregister('simulate', onSim) end\n"
           "event.register('activate', onAct)\nevent.register('mobileDeactivated', onDeact)\n")
    new = patch(src)
    assert "if not event.isRegistered('simulate', onSim) then event.register('simulate', onSim) end" in new


def test_F1_passive_mwguard_does_not_count_as_covering(tmp_path):
    data, root = mod_tree(tmp_path, {"main.lua": SPAM})
    dd = tmp_path / "Data Files"
    (dd / "MWSE" / "mods" / "mwguard").mkdir(parents=True)
    (dd / "MWSE" / "mods" / "mwguard" / "main.lua").write_text("-- passive profiler\nlocal d = { enabled = true }")
    rep = lf.check_paths([str(data)], CFG, checker=OkChecker(), use_cache=False, data_dir=str(dd))
    e = next(iter(rep.files.values()))
    assert e["patch"]["ok"] and "F1" in e["patch"]["rules"]
    assert any("passive profiler with no log-spam redirect" in f["fix"] for f in e["findings"] if f["rule"] == "F1")


def test_patched_priorities_are_below_mwguards_report_limit():
    assert all(abs(lf.compress_priority(p, CFG)) < CFG["priorityLimit"] for p in (10000, -10 ** 9, float("inf")))


# ------------------------------------------------------------------------------------------------ nil guards (A1-A5)
def nil_findings(a, rule):
    return [f for f in a.findings if f["rule"] == rule]


PEEK = ("local config = { peekEnabled = true }\nlocal peek = {}\n"
        "local function pressedKey(e)\n"
        "    if e.keyCode == config.peekLeftKey.keyCode then\n        peek.left = true\n"
        "    elseif e.keyCode == config.peekRightKey.keyCode then\n        peek.right = true\n    end\nend\n"
        "event.register(tes3.event.keyDown, pressedKey)\n"
        "return function(c, e) config = c peek = {} pressedKey(e) return peek.left, peek.right end\n")


def test_A2_keybind_in_a_condition_gets_an_and_guard_and_is_idempotent():
    a = analyse(PEEK)
    a2 = nil_findings(a, "A2")
    assert [f["conf"] for f in a2] == ["high", "high"] and all(f["edits"] for f in a2)
    new = patch(PEEK)
    assert "    if e.keyCode == (config.peekLeftKey and config.peekLeftKey.keyCode) then\n" in new
    assert "    elseif e.keyCode == (config.peekRightKey and config.peekRightKey.keyCode) then\n" in new
    assert new.count("\n") == PEEK.count("\n")
    assert patch(new) is None                                  # applied again: nothing more
    assert not nil_findings(analyse(new), "A2")


@need_lua
def test_A2_patched_peek_keys_behave_the_same_when_bound_and_do_not_crash_unbound():
    new = "event = { register = function() end } tes3 = { event = {} }\n" + patch(PEEK)
    old = "event = { register = function() end } tes3 = { event = {} }\n" + PEEK
    rt = _lj.LuaRuntime()
    f_new, f_old = rt.execute(new), rt.execute(old)
    bound = rt.eval("{ peekLeftKey = { keyCode = 16 }, peekRightKey = { keyCode = 18 } }")
    for kc in (16, 18, 20):
        e = rt.eval("{ keyCode = %d }" % kc)
        assert f_new(bound, e) == f_old(bound, e)
    unbound = rt.eval("{ peekRightKey = { keyCode = 18 } }")
    with pytest.raises(LuaError):                          # nil 'peekLeftKey': not a broad catch
        f_old(unbound, rt.eval("{ keyCode = 18 }"))
    assert f_new(unbound, rt.eval("{ keyCode = 18 }")) == (None, True)
    assert f_new(unbound, rt.eval("{ keyCode = 16 }")) == (None, None)


def test_A2_statement_call_is_wrapped_and_local_value_is_guarded():
    src = ("local cfg = mwse.loadConfig('x')\n"
           "event.register('keyDown', onKey, { filter = cfg.toggleKey.keyCode })\n"
           "local function f()\n local down = ic:isKeyDown(cfg.modKey.keyCode)\n return down\nend\n")
    new = patch(src)
    assert "event.register('keyDown', onKey, { filter = (cfg.toggleKey and cfg.toggleKey.keyCode) })\n" in new
    assert " local down = (cfg.modKey and ic:isKeyDown(cfg.modKey.keyCode))\n" in new
    assert patch(new) is None


def test_A2_table_key_in_a_local_stays_a_report_with_the_reason():
    src = "local function f(kb)\n local map = { [kb.cfg.next.keyCode] = 1 }\n return map\nend\n"
    a2 = nil_findings(analyse(src), "A2")
    assert a2 and a2[0]["conf"] == "report" and not a2[0]["edits"] and "table constructor" in a2[0]["fix"]


def test_A2_checked_key_and_loop_variable_are_left_alone():
    src = ("local function f(e)\n if not config.k then return end\n if e.keyCode == config.k.keyCode then end\nend\n"
           "local function g(e)\n for _, key in pairs(keys) do if e.keyCode == key.keyCode then end end\nend\n"
           "local function h(e)\n if type(config.j) ~= 'table' or not config.j.keyCode then return end\nend\n")
    assert not nil_findings(analyse(src), "A2")


def test_A1_write_and_call_with_ref_data_get_an_if_guard():
    src = "local function f(ref)\n ref.data.x = 1\n show(ref.data.count)\nend\n"
    new = patch(src)
    assert " if ref.data then ref.data.x = 1 end\n" in new
    assert " if ref.data then show(ref.data.count) end\n" in new
    assert patch(new) is None


def test_A1_init_then_write_both_guarded_once():
    src = "local function f(ref)\n ref.data.m = ref.data.m or {}\n ref.data.m.n = 1\nend\n"
    new = patch(src)
    assert " if ref.data then ref.data.m = ref.data.m or {} end\n if ref.data and ref.data.m then ref.data.m.n = 1 end\n" in new
    assert patch(new) is None
    assert not nil_findings(analyse("local function f(ref)\n if not ref.data then return end\n ref.data.x = 1\nend\n"), "A1")


def test_nil_values_in_and_or_table_values_and_generic_for_are_repaired():
    src = ("local function f(ref)\n"
           " local crafted = ref.data.crafted or false\n"
           " local row = { name = ref.data.name }\n"
           " for item in ref.data.items:iterator() do use(item) end\n"
           " return crafted, row\nend\n")
    new = patch(src)
    assert "local crafted = (ref.data and (ref.data.crafted or false))" in new
    assert "local row = { name = (ref.data and ref.data.name) }" in new
    assert "if ref.data then for item in ref.data.items:iterator() do use(item) end end" in new
    assert patch(new) is None


def test_event_reference_guard_also_satisfies_ref_data_guard():
    src = ("local function tip(e)\n local ref = e.reference\n"
           " if ref.data and ref.data.GH or ref.sceneNode.appCulled then return end\nend\n"
           "event.register('uiObjectTooltip', tip)\n")
    new = patch(src)
    assert "(ref and ref.data.GH)" in new and "(ref and ref.sceneNode.appCulled)" in new
    assert patch(new) is None


def test_A3_lookup_local_uses_are_guarded():
    src = ("local function f()\n local ref = tes3.getReference('x')\n ref:disable()\n"
           " if ref.cell.isInterior then go() end\n local p = ref.position:copy()\n ref.scale = 2\n return p\nend\n")
    new = patch(src)
    assert " if ref then ref:disable() end\n" in new
    assert " if (ref and ref.cell.isInterior) then go() end\n" in new
    assert " local p = (ref and ref.position:copy())\n" in new
    assert " if ref then ref.scale = 2 end\n" in new
    assert patch(new) is None


def test_A3_checked_or_reassigned_lookup_is_left_alone():
    src = ("local function f()\n local ref = tes3.getReference('x')\n if not ref then return end\n ref:disable()\nend\n"
           "local function g()\n local o = tes3.getObject('x')\n o = o or fallback\n o:doIt()\nend\n")
    assert not nil_findings(analyse(src), "A3")


def test_A3_direct_lookup_statement_is_held_in_a_local():
    src = "local function f()\n tes3.getObject('x').value = 5\n tes3ui.findMenu('M'):updateLayout()\nend\n"
    new = patch(src)
    assert " do local localpatch_v = tes3.getObject('x') if localpatch_v then localpatch_v.value = 5 end end\n" in new
    assert " do local localpatch_v = tes3ui.findMenu('M') if localpatch_v then localpatch_v:updateLayout() end end\n" in new
    assert patch(new) is None


def test_A3_direct_lookup_inside_an_expression_stays_a_report():
    src = "local function f()\n return tes3.getObject('x').name .. '!'\nend\n"
    a3 = nil_findings(analyse(src), "A3")
    assert a3 and a3[0]["conf"] == "report" and "bigger expression" in a3[0]["fix"]


@need_lua
def test_A3_patched_lookup_runs_the_same_when_found_and_skips_when_not():
    src = ("local found\ntes3 = { getObject = function(id) return found end }\n"
           "local function f()\n tes3.getObject('x').value = 5\n local o = tes3.getObject('y')\n o.count = 3\n"
           " return 'done'\nend\nreturn function(v) found = v return f() end\n")
    new = patch(src)
    rt = _lj.LuaRuntime()
    t = rt.eval("{}")
    assert rt.execute(new)(t) == "done" and t["value"] == 5 and t["count"] == 3
    assert rt.execute(new)(None) == "done"
    with pytest.raises(LuaError):                          # nil 'getObject': not a broad catch
        rt.execute(src)(None)


def test_A4_nullable_event_field_is_guarded_and_alias_too():
    src = ("local function onDamage(e)\n if e.attacker.actorType == 1 then x() end\n"
           " local a = e.attackerReference\n a:say('hi')\nend\nevent.register(tes3.event.damage, onDamage)\n"
           "local function onAct(e)\n e.target:disable()\nend\nevent.register('activate', onAct)\n")
    new = patch(src)
    assert " if (e.attacker and e.attacker.actorType) == 1 then x() end\n" in new
    assert " if a then a:say('hi') end\n" in new
    assert " e.target:disable()\n" in new                       # activate always has a target
    assert patch(new) is None


def test_A5_an_npcs_head_or_hair_is_guarded():
    """Tamriel Data's fixVampireHeadAssignment read baseObject.head.id for every NPC: "attempt to index field 'head'
    (a nil value)" in MWSE.log for an NPC whose record names no head (or hair)."""
    src = ("local function fix(e)\n"
           " if e.reference.mobile.object.baseObject.head.id == 'T_Head' then e.bodyPart = nil\n"
           " elseif e.reference.mobile.object.baseObject.head.id == 'T_Head2' then e.bodyPart = nil end\n"
           " if e.reference.mobile.object.baseObject.hair.id == 'T_Hair' then e.bodyPart = nil end\n"
           "end\nevent.register(tes3.event.bodyPartAssigned, fix)\n")
    new = patch(src)
    assert " if (e.reference.mobile.object.baseObject.head and e.reference.mobile.object.baseObject.head.id) == " \
           "'T_Head' then" in new
    assert " elseif (e.reference.mobile.object.baseObject.head and " in new
    assert " if (e.reference.mobile.object.baseObject.hair and e.reference.mobile.object.baseObject.hair.id) == " \
           "'T_Hair' then" in new
    assert patch(new) is None


def test_A5_a_checked_head_and_other_fields_are_left_alone():
    src = ("local function f(e)\n local o = e.reference.baseObject\n"
           " if e.reference.baseObject.head and e.reference.baseObject.head.id == 'x' then end\n"
           " local r = e.reference.baseObject.race.id\nend\nevent.register('bodyPartAssigned', f)\n")
    assert not nil_findings(analyse(src), "A5")


def test_A4_checked_field_is_left_alone():
    src = ("local function onTip(e)\n if e.object.isSoulGem and e.itemData and e.itemData.soul then end\nend\n"
           "event.register('uiObjectTooltip', onTip)\n")
    assert not nil_findings(analyse(src), "A4")


def test_nil_guard_never_truncates_extra_return_values_or_guards_repeat():
    src = ("local function f()\n local o = tes3.getObject('x')\n local a, b = o:pair()\n"
           " repeat step() until o.done\n return a, b\nend\n")
    a3 = nil_findings(analyse(src), "A3")
    assert sorted(f["conf"] for f in a3) == ["report", "report"]
    assert any("extra return values" in f["fix"] for f in a3) and any("repeat" in f["fix"] for f in a3)


@need_lua
def test_nested_guards_in_one_condition_compile_and_hold_under_each_missing_key():
    src = ("local cfg = {}\nlocal function f(e, ic)\n if ic:isKeyDown(cfg.a.keyCode) == cfg.b.keyCode then return 1 end\n"
           " return 0\nend\nreturn function(c, e, ic) cfg = c return f(e, ic) end\n")
    new = patch(src)
    assert patch(new) is None
    rt = _lj.LuaRuntime()
    fn = rt.execute(new)
    ic = rt.eval("{ isKeyDown = function(self, k) return k end }")
    assert fn(rt.eval("{ a = { keyCode = 3 }, b = { keyCode = 3 } }"), None, ic) == 1
    assert fn(rt.eval("{ a = { keyCode = 3 }, b = { keyCode = 4 } }"), None, ic) == 0
    assert fn(rt.eval("{ b = { keyCode = 3 } }"), None, ic) == 0
    assert fn(rt.eval("{ a = { keyCode = 3 } }"), None, ic) == 0


@need_lua
def test_every_nil_guard_patch_compiles():
    srcs = [PEEK, "local function f(ref)\n ref.data.x = 1\n show(ref.data.count)\nend\n",
            "local function f()\n tes3.getObject('x').value = 5\n tes3ui.findMenu('M'):updateLayout()\nend\n",
            "local function f()\n local ref = tes3.getReference('x')\n ref:disable()\n local p = ref.position:copy()\n"
            " return p\nend\n",
            "local function onDamage(e)\n local a = e.attackerReference\n a:say('hi')\nend\n"
            "event.register('damage', onDamage)\n"]
    ch = lf.LupaChecker()
    for s in srcs:
        new = patch(s)
        assert new and ch.check(new)[0], new


def test_applied_report_prefixes_every_finding_with_its_status():
    rep = lf.Report()
    find = lambda rule, conf, fix: {"rule": rule, "conf": conf, "line": 1, "what": rule + " wrong", "fix": fix}
    patch = {"ok": True, "rules": ["A1"], "text": "x", "why": ""}
    rep.files["a.lua"] = {"rel": "a.lua", "mod": "m", "error": None, "patch": patch,
                          "findings": [find("A1", "high", "guard"), find("A2", "high", ""), find("L1", "report", "")]}
    rep.files["b.lua"] = {"rel": "b.lua", "mod": "m", "error": None, "patch": dict(patch),
                          "findings": [find("A1", "high", "guard")]}
    lines, _c = lf.format_report(rep, done=["a.lua"], refused={"b.lua": "syntax check failed"})
    text = "\n".join(lines)
    assert "PATCHED: A1 line 1: A1 wrong  -> guard" in lines[1]
    assert "UNCONFIGURED: A2 line 1: A2 wrong" in text and "REPORTED: L1 line 1: L1 wrong" in text
    assert "=> PATCHED (A1)" in text
    assert "NOT PATCHED: A1 line 1" in text and "=> NOT PATCHED: syntax check failed" in text


SAVE_SRC = """local config = {}
event.register(tes3.event.save, function(e)
    mwse.saveConfig("x", config)
end)
event.register(tes3.event.uiActivated, function(e)
    local t = timer.start({ type = timer.real, duration = 10, iterations = -1, callback = function()
        local m = tes3ui.findMenu("MenuLoading")
        if m then m:updateLayout() end
    end })
end, { filter = "MenuLoading" })
"""


def test_a_ui_slideshow_timer_skips_while_saving_and_config_waits_for_the_save():
    a = lf.FileAnalysis(SAVE_SRC, "x", "x/main.lua")
    rules = sorted(f["rule"] for f in a.run() if f["rule"] in ("I2", "I3"))
    assert rules == ["I2", "I3"]
    new, applied = lf.build_patch(SAVE_SRC, a.findings, "x", lf.load_config())
    assert {"I2", "I3"} <= set(applied)
    assert "if localpatch_save.saving then return end" in new and "localpatch_savestate" in new
    assert 'event.register("menuExit", function() localpatch_save.saving = false end)' in new
    assert 'timer.delayOneFrame(function() mwse.saveConfig("x", config) end, timer.real)' in new
    b = lf.FileAnalysis(new, "x", "x/main.lua")                     # a second pass changes nothing more
    assert not [f for f in b.run() if f["rule"] in ("I2", "I3")]


# --- L1 / M1 / V1 (rules added after the 2026-11 hand-edit audit)
def test_l1_caps_linked_walk_and_countdown():
    src = ("local function f(c)\n  while c do\n    c = c.parent\n  end\nend\n"
           "local function g(w, d)\n  while w.elapsed >= w.duration do\n    w.elapsed = w.elapsed - d\n  end\nend\n"
           "local function h(i)\n  while i > 0 do\n    i = i - 1\n  end\nend\n"
           "local function u(s, d)\n  while s.left <= 0 do\n    s.left = s.left + d\n  end\nend\n")
    a = analyse(src)
    assert [f["rule"] for f in a.findings if f["rule"] == "L1"] == ["L1", "L1", "L1"]   # i - 1 always ends
    new = patch(src)
    assert new.count("localpatch_n1") == 4 and new.count("localpatch_n2") == 4
    assert new.count("\n") == src.count("\n")                                    # line numbers kept
    assert not [f for f in analyse(new).findings if f["rule"] == "L1"]           # idempotent


def test_m1_menu_exit_only_without_ui():
    src = ("event.register('enterFrame', function(e) local p = tes3.player.position end)\n"
           "event.register('enterFrame', function(e) local m = tes3ui.findMenu('MenuMulti') end)\n"
           "event.register('simulate', function(e) local p = tes3.player.position end)\n")
    a = analyse(src)
    assert [f["line"] for f in a.findings if f["rule"] == "M1"] == [1]
    new = patch(src)
    assert new.splitlines()[0].count("if tes3.menuMode() then return end") == 1


def test_v1_number_times_vector_swapped():
    src = "local up = tes3vector3.new(0, 0, 1)\nlocal d = -1 * up\nlocal n = 2 * count\nlocal k = 2 * 3\n"
    a = analyse(src)
    assert sorted((f["line"], f["conf"]) for f in a.findings if f["rule"] == "V1") == [(2, "high")]
    assert "local d = up * -1" in patch(src)


def test_v1_only_flags_with_vector_evidence():
    # the 2026-11-24 tidy plan's 355 false alarms: plain number math, including names that look like vectors
    plain = ("local a = 2 * math.pi\nlocal b = 0.9 * vol\nlocal c = 1.5 * acrobatics\nlocal d = .75 * chameleonMagnitude\n"
             "local e = 2 * dir\nlocal f = 3 + offset\nlocal g = 1 - pos\nlocal h = 2 * mobile.health.current\n"
             "local i = 2 * #list\nlocal j = 1 - e.delta\nlocal k = 2 * tes3.player.object.level\n"
             "local s = 1 + ref.position.z\nlocal t = 2 * cfg.scale\n")
    assert "V1" not in rules(analyse(plain))
    real = ("local function f(ref, e)\n"
            "  local v = 2 * ref.position\n"                       # 2 high: a reference's position
            "  local w = -1 * tes3.getCameraVector()\n"            # 3 high: documented vector function
            "  local x = 0.5 * mob.velocity\n"                     # 4 high: documented vector field
            "  local n = node.worldTransform.translation\n"
            "  local y = 10 + n\n"                                 # 6 high: a local set from one
            "  local z = 1 - tes3vector3.new(1, 2, 3)\n"           # 7 high
            "  local q = 3 * thing.position\n"                     # 8 medium: position of something unknown
            "  local r = 2 * ref.forwardDirection:normalized()\n"  # 9 high
            "end\n")
    a = analyse(real)
    assert sorted((f["line"], f["conf"]) for f in a.findings if f["rule"] == "V1") == \
        [(2, "high"), (3, "high"), (4, "high"), (6, "high"), (7, "high"), (8, "medium"), (9, "high")]
    new = patch(real)
    for line in ("local v = ref.position * 2", "local w = tes3.getCameraVector() * -1", "local y = n + 10",
                 "local z = -tes3vector3.new(1, 2, 3) + 1", "local r = ref.forwardDirection:normalized() * 2",
                 "local q = 3 * thing.position"):
        assert line in new, line
    assert patch(new) is None or "V1" not in rules(analyse(new), "high")


@need_lua
def test_v1_swaps_keep_the_value():
    rt = _lj.LuaRuntime()
    rt.execute("""V = {} V.__index = V
      function V.new(x) return setmetatable({x = x}, V) end
      V.__mul = function(a, b) assert(getmetatable(a) == V and type(b) == 'number') return V.new(a.x * b) end
      V.__add = function(a, b) assert(getmetatable(a) == V and type(b) == 'number') return V.new(a.x + b) end
      V.__unm = function(a) return V.new(-a.x) end
      tes3vector3 = { new = V.new }""")
    src = "local v = tes3vector3.new(4)\nreturn (2 * v).x, (3 + v).x, (10 - v).x\n"
    with pytest.raises(LuaError):
        rt.execute(src)
    assert tuple(rt.execute(patch(src))) == (8, 7, 6)


@need_lua
def test_l1_patched_cycle_terminates():
    src = ("local a = {} a.parent = a\nlocal function f(c)\n  local n = 0\n  while c do\n    c = c.parent n = n + 1\n"
           "  end\n  return n\nend\nreturn f(a)\n")
    rt = _lj.LuaRuntime()
    assert rt.execute(patch(src)) == 10000


def test_branding_from_older_patches_is_taken_off(tmp_path):
    mods = tmp_path / "MWSE" / "mods"
    old = {
        "gated": "--[[mwdialog_luafix 3: G2]] local mwluafix_gate = function() return false end "
                 "local function f() if mwluafix_gate(1, 0.35) then return end end\nreturn f\n",
        "marked": "--[[mwdialog_luafix 4: A1]] local a = 1\nreturn a\n",
    }
    for name, text in old.items():
        (mods / name).mkdir(parents=True)
        (mods / name / "main.lua").write_text(text)

    def check():
        return lf.check_paths([str(mods)], CFG, use_cache=False, data_dir=str(tmp_path / "none")).files

    files = check()
    assert len(files) == 2
    for path, ent in files.items():
        text = ent["patch"]["text"]
        assert ent["patch"]["ok"] and "luafix" not in text and "mwdialog" not in text
        assert text.startswith("--[[localpatch ") and text.count("\n") == 2
        with open(path, "w") as f:
            f.write(text)
    assert all(not ent["patch"] for ent in check().values())    # and only once


def test_nothing_luafix_injects_carries_its_name():
    injected = [lf.GATE_HELPER, lf.SAVE_HELPER, lf.NIL_TMP, lf.MARK, lf.log_shim("testmod", CFG)]
    injected += [new for _rule, _plugin, _rel, _old, new, _what in lf.KNOWN_BUGS]
    for text in injected:
        assert "luafix" not in text.lower() and "mwdialog" not in text.lower(), text[:80]


# ------------------------------------------------------------------------------------------------ KB14-KB17, KB19
LUAJIT_KB = os.environ.get("MWMANAGER_LUAJIT", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                            "tools", "luajit", "luajit.exe"))


def kb_patch(source, rel, rule, owner, parts, eol):
    """The rule's findings on source (with eol), patched, checked, idempotent, line 1 untouched: the new text."""
    source = source.replace("\n", eol)
    findings = [f for f in analyse(source, rel).findings if f["rule"] == rule]
    assert len(findings) == parts and all(f["conf"] == "high" for f in findings), findings
    repaired, applied = lf.build_patch(source, findings, owner, CFG, "high", False)
    assert set(applied) == {rule} and repaired.count("\n") == repaired.count(eol)
    assert source.split(eol, 1)[0] in repaired.split(eol, 1)[0]          # line 1 keeps its text (marker only)
    assert not [f for f in analyse(repaired, rel).findings if f["rule"] == rule]
    assert lf.verify_patch(source, repaired, applied, None, owner, rel, CFG, "high")["ok"]
    return repaired


def run_lua(script, repaired):
    if not os.path.isfile(LUAJIT_KB):
        pytest.skip("LuaJIT executable not available for behavioral verification")
    for name, text in repaired.items():
        script = script.replace(name, text.replace("\r", ""))
    result = subprocess.run([LUAJIT_KB, "-"], input=script, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_kb14_to_kb19_never_touch_line_1_and_are_whole_where_parts_depend():
    rules = {"KB14", "KB15", "KB16", "KB17", "KB19"}
    entries = [e for e in lf.KNOWN_BUGS if e[0] in rules]
    assert {e[0] for e in entries} == rules
    for _rule, _owner, _rel, old, new, _what in entries:
        assert old not in new                                     # applied once, never matches again
    assert {"KB14", "KB16", "KB17", "KB19"} <= lf.KNOWN_BUGS_WHOLE and "KB15" not in lf.KNOWN_BUGS_WHOLE


NM14_UTIL = """local config = { enableSound = true, soundVolume = 0.7 }
local sound = "R0_moths_fluttering"
local util = {}
function util.playSound(reference)
\tif not config.enableSound then return end
\ttes3.playSound({
\t\treference = reference,
\t\tsound = sound,
\t\tloop = true,
\t\tvolume = config.soundVolume,
\t})
end
function util.stopSound(reference)
\tif not config.enableSound then return end
\ttes3.removeSound({ reference = reference, sound = sound })
end
return util
"""

NM14_MANAGER = """local util = NM_UTIL
local EffectManager = { activeEffects = {} }
function EffectManager:reset()
\tself.activeEffects = {}
\tself.nextUpdateTimestamp = -1
\tself.lastUpdateState = {}
end
return EffectManager
"""


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_KB14_nocturnal_moths_does_not_stack_loops_and_stops_them_on_reset(eol):
    util = kb_patch(NM14_UTIL, "nocturnal moths/util/init.lua", "KB14", "Nocturnal Moths", 1, eol)
    manager = kb_patch(NM14_MANAGER, "nocturnal moths/effectmanager.lua", "KB14", "Nocturnal Moths", 1, eol)
    run_lua(r"""
local playing, plays, removes = {}, 0, 0
tes3 = {
  getSoundPlaying = function(p) return playing[p.reference] == true end,
  playSound = function(p) plays = plays + 1 playing[p.reference] = true end,
  removeSound = function(p) removes = removes + 1 playing[p.reference] = nil end,
}
NM_UTIL = assert(loadstring([==[@UTIL@]==]))()
local mgr = assert(loadstring([==[@MANAGER@]==]))()
local lantern = {}
NM_UTIL.playSound(lantern) NM_UTIL.playSound(lantern) NM_UTIL.playSound(lantern)
assert(plays == 1, "moth loop stacked: " .. plays)
NM_UTIL.playSound({ disabled = true })
assert(plays == 1, "played on a disabled reference")
mgr.activeEffects[lantern] = true
mgr:reset()
assert(removes == 1 and next(mgr.activeEffects) == nil and mgr.nextUpdateTimestamp == -1)
""", {"@UTIL@": util, "@MANAGER@": manager})


AURA15 = """local this = {}
function this.getTrackPlaying(track, ref)
\tif track and ref and tes3.getSoundPlaying { sound = track, reference = ref } then
\t\treturn track
\tend
end
return this
"""


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_KB15_aura_trusts_its_own_track_over_getSoundPlaying(eol):
    common = kb_patch(AURA15, "tew/aura/common.lua", "KB15", "AURA", 1, eol)
    run_lua(r"""
tes3 = { getSoundPlaying = function() return false end }     -- the engine's answer for a 3D loop on a door
local common = assert(loadstring([==[@COMMON@]==]))()
assert(common.getTrackPlaying("IE_tav_imp_1", {}) == "IE_tav_imp_1")
assert(common.getTrackPlaying(nil, {}) == nil and common.getTrackPlaying("x", nil) == nil)
""", {"@COMMON@": common})


FLIES16 = """local mod = { name = "R-Zero's Flies" }

local function refDelete(cell)
    for ref in cell:iterateReferences({ tes3.objectType.activator }) do
        if ref and ref.data and ref.data.spa_TempFlies then ref:delete() end
    end
end

---@param e cellChangedEventData
event.register("cellChanged", function(e)
    for ref in e.cell:iterateReferences({ tes3.objectType.npc, tes3.objectType.creature }) do
        if ref
            and ref.data
            and ref.isDead
            and ref.data.spa_fliesCountDown
            and ref.data.spa_fliesCountDown < (tes3.getSimulationTimestamp() - 24) then
            tes3.playSound { sound = "Flies", reference = ref, loop = true, volume = 0.5, pitch = 1.0 }
        end
    end
    refDelete(e.cell)
end)


---@param e table|menuExitEventData
event.register("menuExit", function(e)
    refDelete(tes3.player.cell)
end)
"""


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_KB16_flies_do_not_stack_on_corpses_and_stop_when_unloaded(eol):
    main = kb_patch(FLIES16, "spammer/flies/main.lua", "KB16", "Flies", 2, eol)
    partial = FLIES16.replace("    refDelete(e.cell)\nend)\n\n\n", "    refDelete(e.cell)\nend)\n\n")
    got = [f for f in analyse(partial, "spammer/flies/main.lua").findings if f["rule"] == "KB16"]
    assert [f["conf"] for f in got] == ["report"]                 # one part of two: left alone, said why
    run_lua(r"""
local handlers, playing, plays, removes = {}, {}, 0, 0
event = { register = function(name, fn) handlers[name] = fn end }
local corpse = { isDead = true, data = { spa_fliesCountDown = 0 } }
local cell = { iterateReferences = function(_, types)
  local list = (types[1] == "npc") and { corpse } or {}
  local i = 0
  return function() i = i + 1 return list[i] end
end }
tes3 = {
  objectType = { npc = "npc", creature = "creature", activator = "activator" },
  getSimulationTimestamp = function() return 1000 end,
  getSoundPlaying = function(p) return playing[p.reference] == true end,
  playSound = function(p) plays = plays + 1 playing[p.reference] = true end,
  removeSound = function(p) removes = removes + 1 playing[p.reference] = nil end,
  player = { cell = cell },
}
assert(loadstring([==[@MAIN@]==]))()
handlers.cellChanged({ cell = cell }) handlers.cellChanged({ cell = cell })
assert(plays == 1, "fly loop stacked: " .. plays)
handlers.referenceDeactivated({ reference = corpse })
assert(removes == 1 and not playing[corpse])
handlers.cellChanged({ cell = cell }) handlers.loaded()
assert(plays == 2 and removes == 2)
""", {"@MAIN@": main})


LEV17 = """local levitating
local timeEnteredPad
local function addLevitation()
    levitating = true
    tes3.playSound{
        sound = "forcefield",
        loop = true,
        pitch = 1.2
    }
end
local function levitate(e)
    if not levitating then addLevitation() end
end
event.register("simulate", levitate)
"""


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_KB17_tel_raloran_pad_plays_one_forcefield_loop_and_clears_it_on_load(eol):
    main = kb_patch(LEV17, "telraloran/levpad.lua", "KB17", "Tel Raloran", 2, eol)
    run_lua(r"""
local handlers, playing, plays = {}, false, 0
event = { register = function(name, fn) handlers[name] = fn end }
tes3 = {
  getSoundPlaying = function() return playing end,
  playSound = function() plays = plays + 1 playing = true end,
  removeSound = function() playing = false end,
}
assert(loadstring([==[@MAIN@]==]))()
handlers.simulate({})
handlers.loaded()
assert(playing == false, "forcefield still playing after load")
handlers.simulate({})
assert(plays == 2)
""", {"@MAIN@": main})


KEG19 = """local function samePlacement(effect, keg)
    return effect.position:distance(keg.position) < 0.01
        and effect.orientation:distance(keg.orientation) < 0.001
        and math.abs(effect.scale - keg.scale) < 0.001
end

local function available(ref) return not ref.deleted end

local function refreshCell(cell, kegs, effects, definition)
    local used = {}
    for _, keg in ipairs(kegs) do
        do
            do
                local effect
                for _, candidate in ipairs(effects) do
                    if not used[candidate] and available(candidate) and samePlacement(candidate, keg) then
                        effect = candidate
                        break
                    end
                end
                if not effect then
                    effect = tes3.createReference {
                        object = definition.id,
                        cell = cell,
                        position = keg.position,
                        orientation = keg.orientation,
                        scale = keg.scale,
                        updateCollisionGroups = false,
                    }
                    effect.modified = false
                end
                used[effect] = true
            end
        end
    end
    for _, effect in ipairs(effects) do
        if not used[effect] then
            effect:delete()
            effect.modified = false
        end
    end
end
return refreshCell
"""


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_KB19_keg_drip_reuses_its_drip_instead_of_recreating_it(eol):
    main = kb_patch(KEG19, "kegdrip/main.lua", "KB19", "Keg Drip", 3, eol)
    run_lua(r"""
local created, removed = 0, 0
local function vec(x) return { x = x, distance = function(a, b) return math.abs(a.x - b.x) end } end
tes3 = {
  createReference = function(p) created = created + 1 return { object = { id = p.object }, position = p.position,
    orientation = p.orientation, scale = p.scale, delete = function(self) self.deleted = true end } end,
  removeSound = function() removed = removed + 1 end,
}
local refreshCell = assert(loadstring([==[@MAIN@]==]))()
local def = { id = "furn_com_kegstand_dr" }
local keg = { position = vec(100.5), orientation = vec(0), scale = 1 }
local old = { object = { id = "furn_com_kegstand_dr" }, position = vec(100), orientation = vec(0.01), scale = 1,
  delete = function(self) self.deleted = true end }
refreshCell("cell", { keg }, { old }, def)
assert(created == 0 and not old.deleted, "the drip was recreated instead of kept")
local far = { position = vec(5000), orientation = vec(0), scale = 1 }
refreshCell("cell", { far }, { old }, def)
assert(created == 0 and old.position == far.position, "a free drip of the same id should be moved, not remade")
local stray = { object = { id = "furn_de_kegstand_dr" }, position = vec(1), orientation = vec(0), scale = 1,
  delete = function(self) self.deleted = true end }
refreshCell("cell", {}, { stray }, def)
assert(stray.deleted and removed == 1, "a leftover drip is deleted after its sound is stopped")
""", {"@MAIN@": main})


# ------------------------------------------------------------------------------------------------ G1 pairs
def test_G1_unregister_and_isRegistered_literals_follow_the_compressed_register():
    src = ("event.register('save', saveBlock, { priority = 300000 })\n"
           "if event.isRegistered('save', saveBlock, { priority = 300000 }) then\n"
           "  event.unregister('save', saveBlock, { priority = 300000 })\nend\n"
           "event.unregister('save', other, { priority = 50 })\n")
    q = lf.compress_priority(300000, CFG)
    new = patch(src)
    assert new.count(f"priority = {q} }}") == 3 and "300000" not in new and "priority = 50 }" in new
    assert not [f for f in analyse(new).findings if f["rule"] == "G1"]


# --- CR-22: D1 widened, G6 / G7 / R1 / T1 / P1 (report only)
def test_D1_costly_work_before_passes_is_early_returned():
    src = ("local function onInfo(e)\n  if e.dialogue.id:lower() == 'x' and tes3.isModActive('a.esp') then\n"
           "    e.passes = false\n  end\nend\nevent.register(tes3.event.infoFilter, onInfo)\n")
    a = analyse(src)
    d1 = [f for f in a.findings if f["rule"] == "D1"]
    assert len(d1) == 1 and d1[0]["conf"] == "high" and "string work on e.dialogue.id" in d1[0]["what"]
    assert "local function onInfo(e) if not e.passes then return end\n" in patch(src)
    ok = ("local function onInfo(e)\n  if not e.passes then return end\n  if e.dialogue.id:lower() == 'x' then "
          "e.passes = false end\nend\nevent.register('infoFilter', onInfo)\n")
    assert "D1" not in rules(analyse(ok))


def test_D1_costly_work_with_side_effects_is_only_reported():
    src = ("local seen = {}\nlocal function onInfo(e)\n  local id = e.info.id:lower()\n  seen[id] = true\n"
           "  if id == 'x' then e.passes = false end\nend\nevent.register('infoFilter', onInfo)\n")
    d1 = [f for f in analyse(src).findings if f["rule"] == "D1"]
    assert len(d1) == 1 and d1[0]["conf"] == "report" and not d1[0]["edits"]
    cheap = ("local function onInfo(e)\n  if e.dialogue == someDialogue then e.passes = false end\nend\n"
             "event.register('infoFilter', onInfo)\n")
    assert "D1" not in rules(analyse(cheap))


def test_G6_getReference_in_frequent_handlers_and_fast_timers():
    src = ("local function onTarget(e) local box = tes3.getReference('keyring') end\n"
           "event.register('activationTargetChanged', onTarget)\n"
           "timer.start{ duration = 0.2, iterations = -1, callback = function() local r = tes3.getReference('x') end }\n"
           "event.register('loaded', function() local r = tes3.getReference('x') end)\n")
    g6 = [f for f in analyse(src).findings if f["rule"] == "G6"]
    assert sorted(f["line"] for f in g6) == [1, 3] and all(f["conf"] == "report" and not f["edits"] for f in g6)


def test_G7_unrooted_or_unbounded_raytest():
    src = ("event.register('simulate', function()\n  tes3.rayTest{ position = p, direction = d }\n"
           "  tes3.rayTest{ position = p, direction = d, maxDistance = 100, root = tes3.game.worldObjectRoot }\n"
           "  tes3.rayTest{ position = p, direction = d, maxDistance = 100, root = r, accurateSkinned = true }\n"
           "end)\nevent.register('activate', function() tes3.rayTest{ position = p, direction = d, maxDistance = 9 } end)\n"
           "event.register('loaded', function() tes3.rayTest{ position = p, direction = d } end)\n")
    g7 = sorted((f["line"], f["conf"]) for f in analyse(src).findings if f["rule"] == "G7")
    assert g7 == [(2, "report-high"), (4, "report"), (6, "report")]
    assert "no root" in next(f for f in analyse(src).findings if f["rule"] == "G7" and f["line"] == 6)["what"]


def test_R1_timer_holding_an_event_reference():
    bad = ("local function onAct(e)\n  local ref = e.target\n  timer.start{ duration = 5, callback = function()\n"
           "    ref:disable()\n  end }\nend\nevent.register('activate', onAct)\n"
           "local function onDmg(e)\n  timer.start{ duration = 1, callback = function() e.reference.mobile:kill() end }\n"
           "end\nevent.register('damaged', onDmg)\n")
    r1 = [f for f in analyse(bad).findings if f["rule"] == "R1"]
    assert sorted(f["line"] for f in r1) == [4, 9] and all(f["edits"] and f["conf"] == "high" for f in r1)
    fixed, applied = lf.build_patch(bad, r1, "testmod", CFG, "high", False)     # R1 is a fix since 2026-11-26
    assert applied == ["R1"] and fixed.count("\n") == bad.count("\n")
    assert "local localpatch_h1 = ref and tes3.makeSafeObjectHandle(ref) timer.start" in fixed
    assert "callback = function() if localpatch_h1 and not localpatch_h1:valid() then return end" in fixed
    assert "local localpatch_h2 = e.reference and tes3.makeSafeObjectHandle(e.reference) timer.start" in fixed
    assert "R1" not in [f["rule"] for f in analyse(fixed).findings if f["edits"]]
    good = ("local function onAct(e)\n  local h = tes3.makeSafeObjectHandle(e.target)\n"
            "  timer.start{ duration = 5, callback = function()\n    if h:valid() then h:getObject():disable() end\n"
            "  end }\nend\nevent.register('activate', onAct)\n"
            "local function onAct2(e)\n  local ref = e.target\n  timer.start{ duration = 5, callback = function()\n"
            "    if ref:isValid() then ref:disable() end\n  end }\nend\nevent.register('activate', onAct2)\n"
            "timer.start{ duration = 1, callback = function() local r = tes3.player end }\n")
    assert "R1" not in rules(analyse(good))


def test_T1_named_timer_never_registered(tmp_path):
    data, root = mod_tree(tmp_path, {"main.lua": "require('testmod.t')\n"
                                                 "timer.start{ duration = 1, callback = 'testmod:tick' }\n"
                                                 "timer.start{ duration = 1, callback = 'testmod:other' }\n",
                                     "t.lua": "timer.register('testmod:tick', function() end) return {}\n"})
    rep = lf.check_paths([str(data)], CFG, checker=OkChecker(), use_cache=False)
    t1 = [(os.path.basename(p), f["line"]) for p, ent in rep.files.items() for f in ent["findings"] if f["rule"] == "T1"]
    assert t1 == [("main.lua", 3)]


def test_P1_data_on_a_non_actor_without_modified():
    bad = ("local function onAct(e)\n  if e.target.object.objectType == tes3.objectType.container then\n"
           "    e.target.data.looted = true\n  end\nend\nevent.register('activate', onAct)\n"
           "event.register('itemDropped', function(e) e.reference.data.dropped = true end)\n")
    p1 = [f for f in analyse(bad).findings if f["rule"] == "P1"]
    assert sorted(f["line"] for f in p1) == [3, 7] and all(not f["edits"] for f in p1)
    good = ("local function onAct(e)\n  if e.target.object.objectType == tes3.objectType.container then\n"
            "    e.target.data.looted = true\n    e.target.modified = true\n  end\nend\n"
            "event.register('activate', onAct)\n"
            "local function onAct2(e)\n  if e.target.object.objectType == tes3.objectType.npc then\n"
            "    e.target.data.talked = true\n  end\nend\nevent.register('activate', onAct2)\n"
            "event.register('loaded', function() tes3.player.data.x = 1 end)\n")
    assert "P1" not in rules(analyse(good))


def test_backups_are_relative_to_the_shared_folder_not_a_full_path_mirror(tmp_path):
    data, root = mod_tree(tmp_path, {"main.lua": PUDDLE})
    twin = tmp_path / "Twin" / "MWSE" / "mods" / "testmod"           # a second mod with the same folders
    twin.mkdir(parents=True)
    (twin / "main.lua").write_text(PUDDLE.replace("bigger", "twin"))
    j, bk = tmp_path / "j.jsonl", tmp_path / "bk"
    rep = lf.check_paths([str(data), str(tmp_path / "Twin")], CFG, checker=OkChecker(), use_cache=False)
    w, _refused = lf.apply_report(rep, journal=str(j), backup_root=str(bk), log=lambda s: 0)
    ops = [json.loads(s) for s in j.read_text().splitlines() if '"backup"' in s]
    rels = sorted(os.path.relpath(op["backup"], str(bk)).split(os.sep, 1)[1] for op in ops)
    assert w == 2 and rels == [os.path.join("1 Mod", "testmod", "main.lua"), os.path.join("2 Twin", "testmod", "main.lua")]
    assert lf.undo(str(j), log=lambda s: 0) == 0 and (root / "main.lua").read_text() == PUDDLE
    assert (twin / "main.lua").read_text() == PUDDLE.replace("bigger", "twin")
