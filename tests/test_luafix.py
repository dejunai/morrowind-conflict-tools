"""mwdialog_luafix / mwdialog_lua: tokenizer, parser, rules, patching in place, undo, tidy wiring."""
import json
import os
import sys

import pytest

from conftest import _load, vt

L = _load("mwdialog_lua")
lf = _load("mwdialog_luafix")

try:
    from lupa import luajit21 as _lj
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
        if self.reject_new and "mwdialog_luafix" in text:
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
    assert "local function onSimulate(e) if mwluafix_gate(1, 0.35) then return end\n" in new
    assert new.count("\n") == PUDDLE.count("\n")            # every line number stays
    assert new.startswith(f"--[[mwdialog_luafix {lf.VERSION}: G2]] local mwluafix_gate do")


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
    assert patch(src) is None or "mwluafix_gate(" not in patch(src)


def test_G2_unknown_calls_and_direct_calls_are_medium_only():
    src = "local m = require('x')\nlocal function poll() if m.check() then m.go() end end\n" \
          "event.register('enterFrame', poll)\n"
    a = analyse(src)
    assert [f["conf"] for f in a.findings if f["rule"] == "G2"] == ["medium"]
    assert patch(src) is None and "mwluafix_gate(1" in patch(src, "medium")
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
    with pytest.raises(Exception):
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


def test_H2_simulate_timer_restarted_on_load_is_fine_real_one_is_not():
    base = "event.register('loaded', function() timer.start{{ type = {t}, duration = 1, iterations = -1, " \
           "callback = function() end }} end)"
    assert not [f for f in analyse(base.format(t="timer.simulate")).findings if f["rule"] == "H2"]
    assert [f for f in analyse(base.format(t="timer.real")).findings if f["rule"] == "H2"]


def test_H5_require_cycle(tmp_path):
    data, root = mod_tree(tmp_path, {"main.lua": "local a = require('testmod.a')",
                                     "a.lua": "local b = require('testmod.b') return {}",
                                     "b.lua": "local a = require('testmod.a') return {}"})
    rep = lf.check_paths([str(data)], CFG, checker=OkChecker(), use_cache=False)
    h5 = [f for e in rep.files.values() for f in e["findings"] if f["rule"] == "H5"]
    assert len(h5) == 1 and "testmod/a.lua" in h5[0]["what"]


# ------------------------------------------------------------------------------------------------ F1 / F2
SPAM = "local function onSim(e)\n mwse.log('tick %d', 1)\nend\nevent.register('simulate', onSim)\nprint('Init')\n"


def test_F1_log_spam_gets_the_shim_when_mwguard_does_not_cover(tmp_path):
    data, root = mod_tree(tmp_path, {"main.lua": SPAM})
    rep = lf.check_paths([str(data)], CFG, checker=OkChecker(), use_cache=False, data_dir=str(tmp_path / "none"))
    e = next(iter(rep.files.values()))
    assert e["patch"]["ok"] and "F1" in e["patch"]["rules"]
    assert 'package.loaded["mwluafix_logshim:testmod"]' in e["patch"]["text"]
    assert e["patch"]["text"].count("\n") == SPAM.count("\n")


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
    assert any("further output goes to" in s for s in shown)
    assert "Error: something broke" in shown and "a" not in shown
    log = logdir / "testmod.log" if os.name == "nt" else tmp_path / "Data Files\\MWSE\\logs\\testmod.log"
    text = log.read_text()
    assert "line 6" in text and "line 100" in text and "a\tb" in text


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


def test_shebang_and_bom_keep_their_place():
    src = "\xef\xbb\xbf" + PUDDLE
    assert patch(src).startswith("\xef\xbb\xbf--[[mwdialog_luafix")
    src = "#!/usr/bin/lua\n" + PUDDLE
    assert patch(src).startswith("#!/usr/bin/lua\n--[[mwdialog_luafix")


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
    monkeypatch.setattr(vt, "__file__", str(tmp_path / "vortex_tidy.py"))
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
    assert "mwluafix_gate(1" in (mod / "MWSE" / "mods" / "puddle" / "main.lua").read_text()
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


# ------------------------------------------------------------------------------------------------ nil guards (A1-A4)
def nil_findings(a, rule):
    return [f for f in a.findings if f["rule"] == rule]


def run_lua(src, *args):
    rt = _lj.LuaRuntime()
    fn = rt.execute(src)
    return rt, fn


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
    with pytest.raises(Exception):
        f_old(unbound, rt.eval("{ keyCode = 18 }"))
    assert f_new(unbound, rt.eval("{ keyCode = 18 }")) == (None, True)
    assert f_new(unbound, rt.eval("{ keyCode = 16 }")) == (None, None)


def test_A2_statement_call_is_wrapped_and_local_value_is_guarded():
    src = ("local cfg = mwse.loadConfig('x')\n"
           "event.register('keyDown', onKey, { filter = cfg.toggleKey.keyCode })\n"
           "local function f()\n local down = ic:isKeyDown(cfg.modKey.keyCode)\n return down\nend\n")
    new = patch(src)
    assert "if cfg.toggleKey then event.register('keyDown', onKey, { filter = cfg.toggleKey.keyCode }) end\n" in new
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
    assert " do local mwluafix_v = tes3.getObject('x') if mwluafix_v then mwluafix_v.value = 5 end end\n" in new
    assert " do local mwluafix_v = tes3ui.findMenu('M') if mwluafix_v then mwluafix_v:updateLayout() end end\n" in new
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
    with pytest.raises(Exception):
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
