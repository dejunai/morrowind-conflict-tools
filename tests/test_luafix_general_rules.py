"""luafix general rules added 2026-11-26 (rules run before the Known Bugs table): Y1 (syntax LuaJIT always rejects),
F3 (true/false concatenated into log text), A3's new lookups, R1/H2/H4 as fixes, A1 at medium for references named
otherwise, and the order rules-then-KB."""
import os

import pytest

from conftest import _load

lf = _load("mwdialog_luafix")

try:
    from lupa import luajit21 as _lj
    HAVE_LUA = True
except Exception:
    HAVE_LUA = False
need_lua = pytest.mark.skipif(not HAVE_LUA, reason="lupa (LuaJIT) not installed")

CFG = dict(lf.DEFAULTS)
MED = dict(CFG)


def analyse(src, rel="testmod/main.lua", cfg=CFG):
    a = lf.FileAnalysis(src, "testmod", rel, cfg)
    a.run()
    return a


def of(a, rule):
    return [f for f in a.findings if f["rule"] == rule]


def patch(src, findings, level="high"):
    return lf.build_patch(src, findings, "testmod", CFG, level, False)


def compiles(text):
    rt = _lj.LuaRuntime()
    rt.globals().SRC = text
    return rt.eval("(loadstring(SRC)) ~= nil")


def lua():
    return _lj.LuaRuntime(unpack_returned_tuples=True)


# ------------------------------------------------------------------------------------------------ Y1
@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_Y1_moves_a_split_calls_paren_up_and_keeps_every_line(eol):
    src = ("local M = { f = function(...) end }\nlocal o = { m = function(self, x) end }\n"
           "M.f\n    (1)\no:m\n\t\t(2)\nM.f(3)\n").replace("\n", eol)
    y1 = of(analyse(src), "Y1")
    assert len(y1) == 2 and all(f["conf"] == "high" for f in y1)
    new, rules = patch(src, y1)
    assert rules == ["Y1"] and new.count(eol) == src.count(eol)
    assert "M.f(" + eol + "    1)" in new and "o:m(" + eol + "\t\t2)" in new and "M.f(3)" in new
    assert not of(analyse(new), "Y1")
    if HAVE_LUA:
        assert not compiles(src) and compiles(new)


def test_Y1_leaves_calls_on_one_line_and_a_comment_between_alone():
    assert not of(analyse("local f = print\nf (1)\nf(2)\n"), "Y1")
    assert not of(analyse("local f = print\nf -- x\n(1)\n"), "Y1")


def test_Y1_adds_the_missing_comma_between_literals_on_separate_lines():
    src = 'local t = {\n  "a"\n  "b"\n  2\n  3,\n}\nreturn t\n'
    fixed, found = lf.syntax_text_repair(src)
    assert [f["rule"] for f in found] == ["Y1", "Y1", "Y1"]
    assert fixed == 'local t = {\n  "a",\n  "b",\n  2,\n  3,\n}\nreturn t\n'
    if HAVE_LUA:
        assert not compiles(src) and compiles(fixed)
    # another syntax error is not guessed at
    assert lf.syntax_text_repair("local t = { a = }\n") == ("local t = { a = }\n", [])
    assert lf.syntax_text_repair('local t = { "a" "b" }\n')[1] == []        # same line: not this shape


def test_Y1_may_repair_a_file_that_does_not_compile():
    class Refuses:
        name = "luajit-like"

        def check(self, text):
            return ("f\n(" not in text), "ambiguous syntax"
    src = "local f = print\nf\n(1)\n"
    a = analyse(src)
    new, rules = patch(src, a.findings)
    assert lf.verify_patch(src, new, rules, Refuses(), "testmod", "testmod/main.lua", CFG, "high")["ok"]


# ------------------------------------------------------------------------------------------------ F3
def test_F3_wraps_true_false_values_in_log_text():
    src = ("local data = { read = {} }\n"
           "local function onBook(e)\n  data.read[e.id] = true\n"
           "  mwse.log('read ' .. data.read[e.id])\n"
           "  mwse.log('flag ' .. (e.a == 1) .. ' and ' .. e.name)\nend\n"
           "event.register('bookGetText', onBook)\n")
    f3 = of(analyse(src), "F3")
    assert len(f3) == 2 and all(f["conf"] == "high" for f in f3)
    new, _r = patch(src, f3)
    assert "'read ' .. tostring(data.read[e.id])" in new and "tostring((e.a == 1))" in new
    assert "' and ' .. e.name" in new                       # a string field is left as it is
    assert not of(analyse(new), "F3")


def test_F3_leaves_slots_that_also_hold_other_values_and_non_log_calls():
    src = ("local t = {}\nt.x = true\nt.x = 'y'\nmwse.log('v ' .. t.x)\n"
           "local f = {}\nf.on = true\nlocal s = 'x' .. f.on\n")
    assert not of(analyse(src), "F3")


# ------------------------------------------------------------------------------------------------ A3 lookups
def test_A3_current_weather_is_high_and_player_cell_is_medium():
    src = ("local function a()\n  local w = tes3.getCurrentWeather()\n  return w.index\nend\n"
           "local function b()\n  local c = tes3.getPlayerCell()\n  return c.id\nend\n")
    a3 = of(analyse(src), "A3")
    conf = {f["what"].split(" - ")[0]: f["conf"] for f in a3}
    assert conf == {"w.index": "high", "c.id": "medium"}


# ------------------------------------------------------------------------------------------------ R1
@need_lua
def test_R1_fix_ends_the_callback_once_the_reference_is_gone():
    src = ("local function onAct(e)\n  local ref = e.target\n  timer.start{ duration = 5, callback = function()\n"
           "    ref:disable()\n  end }\nend\nreturn onAct\n")
    r1 = of(analyse(src), "R1")
    new, rules = patch(src, r1)
    assert rules == ["R1"] and new.count("\n") == src.count("\n")
    stubs = ("CALLS = 0 CB = nil\ntimer = { start = function(t) CB = t.callback end }\n"
             "tes3 = { makeSafeObjectHandle = function(r) return { valid = function() return not r.gone end } end }\n")
    for text, want in ((src, "error"), (new, "skipped")):
        rt = lua()
        rt.execute(stubs)
        rt.globals().SRC = text
        rt.execute("local f = assert(loadstring(SRC))() REF = { disable = function(self) "
                   "if self.gone then error('sol: received nil for self') end CALLS = CALLS + 1 end } "
                   "f({ target = REF }) CB() REF.gone = true")
        ok = rt.eval("(pcall(CB))")
        assert (ok and rt.eval("CALLS") == 1) if want == "skipped" else not ok


# ------------------------------------------------------------------------------------------------ H2
def test_H2_cancels_a_kept_timer_before_starting_another_at_medium():
    src = ("local t\nlocal function onCell(e)\n"
           "  t = timer.start{ duration = 1, iterations = -1, callback = function() end }\nend\n"
           "event.register('cellChanged', onCell)\n")
    h2 = of(analyse(src), "H2")
    assert len(h2) == 1 and h2[0]["conf"] == "medium"
    assert patch(src, h2, "high")[0] is None                # medium: only with --level medium
    new, _r = patch(src, h2, "medium")
    assert "if t then t:cancel() end t = timer.start{" in new and new.count("\n") == src.count("\n")
    local = src.replace("local t\n", "").replace("  t = timer", "  local t = timer")
    assert [f["conf"] for f in of(analyse(local), "H2")] == ["report-high"]   # a handler's local: no handle kept


# ------------------------------------------------------------------------------------------------ H4
@need_lua
def test_H4_reads_a_load_time_capture_again_where_it_is_used():
    src = ("local WtC = tes3.worldController.weatherController\n"
           "local function now()\n  return WtC.currentWeather.index\nend\nreturn now\n")
    h4 = of(analyse(src, "testmod/main.lua"), "H4")
    assert len(h4) == 1 and h4[0]["conf"] == "medium" and h4[0]["edits"]
    new, _r = patch(src, h4, "medium")
    assert new.startswith("--[[localpatch") and "local WtC = tes3.worldController and " \
        "tes3.worldController.weatherController" in new
    assert "(WtC or (tes3.worldController and tes3.worldController.weatherController)).currentWeather" in new
    assert not [f for f in of(analyse(new, "testmod/main.lua"), "H4")]
    rt = lua()
    rt.execute("tes3 = {}")                                 # the file loads before the game data exists
    rt.globals().SRC = new
    rt.execute("NOW = assert(loadstring(SRC))()")
    rt.execute("tes3.worldController = { weatherController = { currentWeather = { index = 4 } } }")
    assert rt.eval("NOW()") == 4
    assert not of(analyse(src, "testmod/other.lua"), "H4")     # only main.lua runs at load


# ------------------------------------------------------------------------------------------------ A1 medium
def test_A1_guards_a_reference_known_by_its_fields_at_medium():
    src = ("local function stable(stables, resident)\n"
           "  if stables.baseObject and resident.baseObject then\n"
           "    stables.data.resident = resident.baseObject.id\n  end\nend\nreturn stable\n")
    a1 = of(analyse(src), "A1")
    assert [f["conf"] for f in a1] == ["medium"]
    new, _r = patch(src, a1, "medium")
    assert "if stables.supportsLuaData then stables.data.resident = resident.baseObject.id end" in new
    plain = "local function f(config)\n  config.data.x = 1\nend\nreturn f\n"
    assert not of(analyse(plain), "A1")                     # nothing says it is a reference


# ------------------------------------------------------------------------------------------------ rules before KB
def test_rules_run_first_and_a_kb_part_applies_only_where_no_rule_matched(monkeypatch):
    src = "local f = print\nf\n(1)\nf\n(2)\n"
    kb = [("KB900", "Test", "testmod/main.lua", "f\n(1)", "f(1)", "test"),
          ("KB901", "Test", "testmod/main.lua", "f\n(2)", "f(2)", "test")]
    monkeypatch.setattr(lf, "KNOWN_BUGS", lf.KNOWN_BUGS + kb)
    a = analyse(src)
    assert not of(a, "KB900") and of(a, "KB901") == [] and len([f for f in of(a, "Y1") if f["edits"]]) == 2
    monkeypatch.setattr(lf, "KNOWN_BUGS_WHOLE", lf.KNOWN_BUGS_WHOLE | {"KB900", "KB901"})
    a = analyse(src)                                        # a whole rule keeps its parts; the rule gives way
    assert len(of(a, "KB900")) == 1 and len(of(a, "KB901")) == 1
    assert all(f["conf"] == "report" and not f["edits"] and "Known Bugs" in f["fix"] for f in of(a, "Y1"))
    new, rules = patch(src, a.findings)
    assert rules == ["KB900", "KB901"] and "f(1)" in new and "f(2)" in new
