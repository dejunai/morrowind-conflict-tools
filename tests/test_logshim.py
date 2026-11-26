"""The F1 log shim: the static replacement for the old mwguard's log-spam guard. Python patch tests, then the
shim itself run in tools\\luajit with mwse, io, lfs, os.time, event and timer mocked."""
import json
import os
import subprocess

import pytest

from conftest import _load

lf = _load("mwdialog_luafix")

LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                          "tools", "luajit", "luajit.exe"))
need_lua = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

CFG = dict(lf.DEFAULTS)
LOG = "Data Files\\MWSE\\logs\\testmod.log"
OLD = "Data Files\\MWSE\\logs\\testmod.old.log"


class OkChecker:
    name = "fake"

    def check(self, text):
        return True, ""


def cfg(**log):
    return dict(CFG, log=dict(CFG["log"], **log))


def mod_tree(tmp_path, files, name="testmod"):
    root = tmp_path / "Mod" / "MWSE" / "mods" / name
    root.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    return tmp_path / "Mod", root


def plan(tmp_path, files, c=None, scope=None, name="testmod"):
    data, _root = mod_tree(tmp_path, files, name)
    rep = lf.check_paths([str(data)], c or CFG, checker=OkChecker(), use_cache=False,
                         data_dir=str(tmp_path / "none"), log_scope=scope)
    return {os.path.basename(p): e for p, e in rep.files.items()}, rep


SPAM = "local function onSim(e)\n  print('tick')\nend\nevent.register('simulate', onSim)\n"
QUIET = "print('[quiet] initialized')\n"
LOGGER = ("local log = mwse.Logger.new()\nlocal L2 = require('logging.logger')\nlocal old = L2.new{ name = 'x' }\n"
          "local function onSim(e)\n  log:debug('frame %d', 1)\nend\nevent.register('simulate', onSim)\n")


# ------------------------------------------------------------------------------------------------ patching
def test_scope_flagged_all_off(tmp_path):
    files = {"main.lua": QUIET}
    e, _ = plan(tmp_path / "a", files)
    assert e["main.lua"]["patch"] is not None                   # default all: every logging mod gets a shim
    e, rep = plan(tmp_path / "b", files, scope="all")
    assert e["main.lua"]["patch"]["ok"] and "F1" in e["main.lua"]["patch"]["rules"]
    assert rep.mods["testmod"]["shim"] and "--lua-log all" in rep.mods["testmod"]["why"]
    e, _ = plan(tmp_path / "c", {"main.lua": SPAM}, scope="off")
    assert e["main.lua"]["patch"] is None
    assert {f["conf"] for f in e["main.lua"]["findings"] if f["rule"] == "F1"} == {"covered"}
    e, _ = plan(tmp_path / "d", files, c=cfg(scope="all"))     # the same from mwguard.json luafix.log.scope
    assert e["main.lua"]["patch"]["ok"]


def test_one_shim_state_per_mod_every_logging_file_patched(tmp_path):
    e, _ = plan(tmp_path, {"main.lua": SPAM, "util.lua": "local M = {}\nfunction M.say(s) mwse.log(s) end\nreturn M\n",
                           "data.lua": "return { a = 1 }\n"})
    for fn in ("main.lua", "util.lua"):
        t = e[fn]["patch"]["text"]
        assert t.count('package.loaded["localpatch_logshim:testmod"]') == 2 and lf.SHIM_END in t
    assert e["data.lua"]["patch"] is None                       # no logging: untouched


def test_logger_creations_are_wrapped_only_with_the_shim(tmp_path):
    e, _ = plan(tmp_path / "a", {"main.lua": LOGGER})
    t = e["main.lua"]["patch"]["text"]
    assert "local log = localpatch_log.wrap(mwse.Logger.new())" in t
    assert "local old = localpatch_log.wrap(L2.new{ name = 'x' })" in t
    assert t.count("\n") == LOGGER.count("\n")
    e, _ = plan(tmp_path / "b", {"main.lua": LOGGER}, scope="off")
    assert e["main.lua"]["patch"] is None
    assert not [f for f in e["main.lua"]["findings"] if f["what"] == "logger created here"]


def test_patched_file_is_stable_and_the_shim_is_not_analysed(tmp_path):
    e, _ = plan(tmp_path, {"main.lua": LOGGER})
    new = e["main.lua"]["patch"]["text"]
    a = lf.FileAnalysis(new, "testmod", "testmod/main.lua", CFG)
    a.run()
    assert not a.logger_creations() and a.log_calls() == 0
    assert all(f["line"] > 1 or f["rule"] in ("G1",) for f in a.findings)   # nothing reported from the shim line
    again, _r = lf.build_patch(new, a.findings, "testmod", CFG, "high", True)
    assert again is None                                        # idempotent


def test_exempt_mods_never_shimmed(tmp_path):
    e, rep = plan(tmp_path, {"main.lua": SPAM}, c=cfg(exemptMods=["TESTMOD"]))
    assert e["main.lua"]["patch"] is None and "exemptMods" in rep.mods["testmod"]["why"]


def test_config_luafix_log_section_and_legacy_keys(tmp_path):
    dd = tmp_path / "Data Files"
    (dd / "MWSE" / "config").mkdir(parents=True)
    (dd / "MWSE" / "config" / "mwguard.json").write_text(json.dumps(
        {"enabled": True, "logBudgetInit": 7, "logExemptMods": ["a"],
         "luafix": {"log": {"perSecond": 9, "maxMB": 1, "scope": "all"}}}))
    c = lf.load_config(str(tmp_path), str(dd))
    assert c["log"]["budgetInit"] == 7 and c["log"]["perSecond"] == 9 and c["log"]["maxMB"] == 1
    assert c["log"]["scope"] == "all" and c["log"]["budget"] == 0 and c["log"]["exemptMods"] == ["a"]
    assert lf.DEFAULTS["log"]["perSecond"] == 25                # defaults untouched
    shim = lf.log_shim("testmod", c)
    assert "init = 7," in shim and "perSecond = 9," in shim and "maxBytes = 1048576," in shim
    assert 'name = "tew.aura"' in lf.log_shim("tew/AURA", c)


@need_lua
def test_shim_compiles_in_luajit_and_keeps_one_line():
    s = lf.log_shim("abot/Some Mod", CFG)
    assert "\n" not in s and s.rstrip().endswith(lf.SHIM_END)
    assert Rt().eval(f"loadstring({quote(s + 'return 1')}) ~= nil")


# ------------------------------------------------------------------------------------------------ runtime
ENV = r"""
FILES, OUT, TIME, INIT, FLUSHES, ATTR = {}, {}, 1000, false, 0, {}
NOOPEN, FAILW = false, false
local rawprint = function(...) local t = {} for i = 1, select('#', ...) do t[i] = tostring((select(i, ...))) end
  OUT[#OUT + 1] = table.concat(t, "\t") end
print = rawprint
ORIG_PRINT = rawprint
mwse = { log = function(f, ...) print(tostring(f):format(...)) end, version = 42 }
os.time = function() return TIME end
os.clock = function() return 0 end
lfs = { mkdir = function() end, attributes = function(p, k) return ATTR[p] end }
local function mkfile(p)
  local f = { p = p }
  function f:write(...) if FAILW then error("disk full") end
    for _, s in ipairs({ ... }) do FILES[self.p] = (FILES[self.p] or "") .. s end return self end
  function f:flush() FLUSHES = FLUSHES + 1 end
  function f:close() end
  function f:setvbuf() end
  return f
end
io = { open = function(p, m) if NOOPEN then return nil, "denied" end if m == "w" then FILES[p] = "" end return mkfile(p) end }
os.remove = function(p) FILES[p] = nil return true end
os.rename = function(a, b) if FILES[a] == nil then return nil, "no file" end FILES[b] = FILES[a] FILES[a] = nil return true end
tes3 = { isInitialized = function() return INIT end }
EVENTS, TIMERS = {}, {}
event = { register = function(e, f) EVENTS[e] = EVENTS[e] or {} table.insert(EVENTS[e], f) end }
timer = { real = 1, start = function(p) TIMERS[#TIMERS + 1] = p end }
function fire(e) if e == "initialized" then INIT = true end for _, f in ipairs(EVENTS[e] or {}) do f({}) end end
function loadMod(path, code) return assert(loadstring(code, "@Data Files\\MWSE\\mods\\" .. path))() end
function lines(path) local t = {} for l in (FILES[path] or ""):gmatch("[^\n]+") do t[#t + 1] = l end return t end
"""


def quote(text):
    return '"' + "".join(chr(b) if 32 <= b < 127 and chr(b) not in '"\\' else f"\\{b:03d}"
                          for b in text.encode("utf-8")) + '"'


class Rt:
    """One Lua session: what was run so far is replayed in LuaJIT for each look at it (the mocks have no clock)."""

    def __init__(self, **log):
        self.cfg = cfg(**dict(dict(perSecond=0), **log))
        self.steps = []

    def look(self, step="", value="nil"):
        program = ["local write = io.write", "do " + ENV + "\nend"]
        program += [f"assert(loadstring({quote(x)}))()" for x in self.steps + [step]]
        program.append(f"write('\\1', tostring({value}))")
        done = subprocess.run([LUAJIT, "-"], input="\n".join(program).encode("utf-8"), capture_output=True)
        if done.returncode:
            raise RuntimeError(done.stderr.decode("utf-8", "replace"))
        return done.stdout.decode("utf-8").replace("\r\n", "\n").rsplit("\1", 1)[1]

    def load(self, body, name="testmod", path="testmod\\main.lua", shim=True):
        code = (lf.log_shim(name, self.cfg) if shim else "") + body
        self.run(f"loadMod({quote(path)}, {quote(code)})")

    def run(self, lua):
        self.look(lua)                                          # raises at the step that is wrong
        self.steps.append(lua)

    def eval(self, expr):
        return self.look(value=f"(select(1, {expr}))") == "true"

    def num(self, expr):
        return float(self.look(value=expr))

    def listed(self, expr):
        got = self.look(value=f"table.concat({expr}, '\\31')")
        return got.split("\x1f") if got else []

    def out(self):
        return self.listed("OUT")

    def file(self, path=LOG):
        return [l.split("] ", 1)[1] if l.startswith("[") and "] " in l else l
                for l in self.listed(f"lines({quote(path)})")]

    def has(self, path):
        return self.eval(f"FILES[{quote(path)}] ~= nil")


@need_lua
def test_first_lines_pass_then_the_rest_goes_to_the_mod_log():
    r = Rt(budgetInit=5)
    r.load("for i = 1, 20 do print('line ' .. i) end mwse.log('fmt %d', 21) print('a', 'b')")
    out = r.out()
    assert out[:5] == [f"line {i}" for i in range(1, 6)]
    assert len(out) == 5                                        # no notice of ours in MWSE.log
    f = r.file()
    assert f[0].endswith("testmod log")
    assert f[1:] == [f"line {i}" for i in range(6, 21)] + ["fmt 21", "a\tb"]


@need_lua
def test_budget_after_initialized_and_shared_by_the_mods_files():
    r = Rt(budgetInit=4, budget=2)
    r.load("print('m1') print('m2')")
    r.load("print('u1') print('u2')", path="testmod\\util.lua")      # same mod: same allowance
    r.run("fire('initialized')")
    r.load("print('late1') print('late2') print('late3')", path="testmod\\late.lua")
    out = r.out()
    assert out == ["m1", "m2", "u1", "u2", "late1", "late2"]
    assert r.file()[-1] == "late3"


@need_lua
def test_errors_and_warnings_always_reach_mwse_log_and_are_flushed():
    r = Rt(budgetInit=1)
    r.load("print('x') print('y') print('ERROR: it broke') mwse.log('[Mod] Warning: %s', 'w') "
           "print(debug.traceback('stack'))  print('pcall failed: attempt to index a nil value')")
    out = r.out()
    assert "ERROR: it broke" in out and "[Mod] Warning: w" in out
    assert any(o.startswith("stack") for o in out) and "pcall failed: attempt to index a nil value" in out
    assert "y" not in out and "ERROR: it broke" in r.file()      # its own log is complete too


@need_lua
def test_identical_lines_collapse_in_the_mod_log():
    r = Rt(budgetInit=0)
    r.load("for i = 1, 10 do print('same') end print('other') for i = 1, 3 do print('again') end")
    r.run("package.loaded['localpatch_logshim:testmod'].flush()")
    assert r.file()[1:] == ["same", "[previous line repeated 9 more time(s)]", "other", "again",
                            "[previous line repeated 2 more time(s)]"]


@need_lua
def test_per_second_cap_on_the_mod_log():
    r = Rt(budgetInit=0, perSecond=5)
    r.load("for i = 1, 20 do print('l' .. i) end TIME = TIME + 1 print('next second')")
    f = r.file()[1:]
    assert f[:5] == [f"l{i}" for i in range(1, 6)]
    assert f[5] == "[15 line(s) dropped: more than 5 in one second]" and f[6] == "next second"
    assert r.out() == []                                        # no redirect notice


@need_lua
def test_size_cap_rotates_and_keeps_one_old():
    r = Rt(budgetInit=0, maxMB=200 / 1048576)                   # 200 bytes
    r.load("for i = 1, 40 do print(string.format('line %03d xxxxxxxxxx', i)) end")
    cur, old = r.file(), r.file(OLD)
    assert old and cur and len("".join(cur)) < 400
    seen = old + cur
    assert "line 040 xxxxxxxxxx" in cur and "line 001 xxxxxxxxxx" not in seen  # only one generation kept
    r2 = Rt(budgetInit=0, maxMB=200 / 1048576, keepOld=0)
    r2.load("for i = 1, 40 do print(string.format('line %03d xxxxxxxxxx', i)) end")
    assert not r2.has(OLD) and r2.has(LOG)


@need_lua
def test_previous_session_log_kept_and_a_file_written_this_session_not_clobbered():
    r = Rt(budgetInit=0)
    r.run("FILES[ [[" + LOG + "]] ] = 'last session\\n' ATTR[ [[" + LOG + "]] ] = 1")
    r.load("print('new')")
    assert r.file(OLD) == ["last session"] and r.file()[-1] == "new"
    r = Rt(budgetInit=0)
    r.run("FILES[ [[" + LOG + "]] ] = 'the mod logger file\\n' ATTR[ [[" + LOG + "]] ] = 2000")
    r.load("print('new')")
    assert r.file() == ["the mod logger file"]
    assert r.file("Data Files\\MWSE\\logs\\testmod.routine.log")[-1] == "new"


@need_lua
def test_io_failures_never_reach_the_mod():
    r = Rt(budgetInit=1)
    r.run("NOOPEN = true")
    r.load("for i = 1, 5 do print('l' .. i) end")
    out = r.out()
    assert out[0] == "l1" and "can't be opened" in out[1] and out[2:] == ["l2", "l3", "l4", "l5"]
    r = Rt(budgetInit=1)
    r.load("print('ok') print('redirected')")
    r.run("FAILW = true")
    r.load("for i = 1, 15 do print('w' .. i) end", path="testmod\\b.lua")   # writes now throw: no error
    out = r.out()
    assert sum("log write failed" in o for o in out) == 1 and "w15" in out
    r.run("FAILW = false")
    r.load("print('after')", path="testmod\\c.lua")
    assert r.out()[-1] == "after"                               # ten failures: passes through from then on


@need_lua
def test_other_mods_and_the_global_print_are_untouched():
    r = Rt(budgetInit=0)
    r.load("print('spam')")
    assert r.eval("print == ORIG_PRINT and mwse.log ~= nil and getmetatable(mwse) == nil")
    r.load("for i = 1, 60 do print('other ' .. i) end", name="other", path="other\\main.lua", shim=False)
    assert r.out()[-60:] == [f"other {i}" for i in range(1, 61)]


@need_lua
def test_flushing_buffered_after_initialized():
    r = Rt(budgetInit=0, flushSeconds=3)
    r.load("print('a')")
    before = r.num("FLUSHES")
    assert before >= 1                                          # startup lines are flushed at once
    r.run("fire('initialized')")
    assert r.num("TIMERS[1].duration") == 3 and r.num("TIMERS[1].iterations") == -1
    n = r.num("FLUSHES")
    r.load("print('b') print('c')", path="testmod\\x.lua")
    assert r.num("FLUSHES") == n                                     # buffered now
    r.run("fire('save')")
    assert r.num("FLUSHES") == n + 1
    r.run("TIMERS[1].callback()")                               # nothing new: no flush
    assert r.num("FLUSHES") == n + 1


@need_lua
def test_generic_logger_methods_wrapped():
    r = Rt(budgetInit=2)
    r.run("LOGGERS = {} mwse.Logger = { new = function() local lg = { lv = 3 } "
          "function lg:info(m) if self.lv >= 3 then print('[INFO] ' .. m) end end "
          "function lg:debug(m) if self.lv >= 4 then print('[DEBUG] ' .. m) end end "
          "function lg:warn(m) print('[WARN] ' .. m) end LOGGERS[#LOGGERS + 1] = lg return lg end }")
    r.load("local log = localpatch_log.wrap(mwse.Logger.new()) "
           "for i = 1, 5 do log:info('i' .. i) end log:debug('hidden') log:warn('careful') "
           "LOG_IS = log return log")
    out = r.out()
    assert out[:2] == ["[INFO] i1", "[INFO] i2"] and "[WARN] careful" in out
    assert "[INFO] i3" not in out and r.file()[-3:] == ["[INFO] i3", "[INFO] i4", "[INFO] i5"]
    assert "hidden" not in " ".join(out + r.file())             # the logger's own level still decides
    assert r.eval("print == ORIG_PRINT and LOG_IS == LOGGERS[1]")


MWSE_CORE = next((p for p in ("/workspace/mwse_src/misc/package/Data Files/MWSE/core",
                              os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                           "Data Files", "MWSE", "core").replace(os.sep, "/"))
                  if os.path.isdir(os.path.join(p, "lib"))), "")


@need_lua
@pytest.mark.skipif(not os.path.isdir(MWSE_CORE), reason="MWSE source not on this machine")
def test_real_mwse_logger_lines_redirected_with_correct_line_numbers():
    r = Rt(budgetInit=1)
    r.run("package.path = [[" + MWSE_CORE + "/lib/?.lua;" + MWSE_CORE + "/lib/?/init.lua;]] .. package.path "
          "socket = { gettime = function() return 0 end } package.loaded.socket = socket "
          "mwse.getConfig = function(k) return k == 'EnableLogLineNumbers' end "
          "function string.split(s, sep) local t = {} for p in s:gmatch('[^' .. sep .. ']+') do t[#t + 1] = p end "
          "return t end table.copy = function(t) local c = {} for k, v in pairs(t) do c[k] = v end return c end "
          "lfs.directoryexists = function() return true end lfs.fileexists = function() return true end "
          "tes3ui = { log = function() end } mwse.activeLuaMods = { testmod = { key = 'testmod' } } "
          "table.getset = function(t, k, d) if t[k] == nil then t[k] = d end return t[k] end "
          "table.new = table.new or function() return {} end table.unpack = table.unpack or unpack "
          "table.find = function(t, v) for k, x in pairs(t) do if x == v then return k end end end "
          "tes3.getLuaModMetadata = function() return nil end")
    try:
        r.run("mwse.Logger = require('logger')")
    except RuntimeError:
        pytest.skip("MWSE's logger doesn't load with these stubs")
    # the logger takes the mod from the last frame below MWSE's loader, so that loader has to be on the stack
    r.run("loadMod = assert(loadstring([[return function(path, code) "
          "return (assert(loadstring(code, '@Data Files\\\\MWSE\\\\mods\\\\' .. path))()) end]], "
          "'@Data Files\\\\MWSE\\\\core\\\\startLuaMods.lua'))()")
    try:
        r.load("local log = localpatch_log.wrap(mwse.Logger.new{ modName = 'testmod', level = 'DEBUG' })\n"
               "log:info('first')\n"
               "log:info('second')\n"
               "log:trace('not shown')\n"
               "log:error('bad')\n")
    except Exception as e:                                      # stubs too thin for this MWSE build
        pytest.skip(f"MWSE's logger needs more stubs: {e}")
    out, f = r.out(), r.file()
    assert any("first" in o for o in out) and any("bad" in o for o in out)
    assert not any("second" in o for o in out) and any("second" in l for l in f)
    second = next(l for l in f if "second" in l)
    assert ":3" in second, second                               # the mod's line, not the shim's
    assert not any("not shown" in l for l in out + f)
    assert r.eval("print == ORIG_PRINT")


def _v1_shim():
    """The version-1 shim exactly as the first release wrote it (from git), for the upgrade test."""
    import subprocess
    src = subprocess.run(["git", "show", "7b13bc1:mwdialog_luafix.py"], capture_output=True, text=True,
                         cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).stdout
    if not src:
        pytest.skip("no git history here")
    ns = {}
    end = src.index("MARK_RE = re.compile")
    exec("import re\nMARK = 'mwdialog_luafix'\n" + src[src.index("def log_name("):end], ns)
    old_defaults = {"logBudgetInit": 40, "logBudget": 10, "logKeepPatterns": ["error", "warn"]}
    return ns["log_shim"]("testmod", old_defaults)


def test_v1_shim_is_upgraded_in_place(tmp_path):
    v1 = _v1_shim()
    assert lf.SHIM_V1_RE.fullmatch(v1)
    body = "local log = mwse.Logger.new()\nprint('x')\n"
    old = "--[[mwdialog_luafix 1: F1]] " + v1 + body
    e, _ = plan(tmp_path, {"main.lua": old}, scope="off")      # upgraded even with the shim off
    t = e["main.lua"]["patch"]["text"]
    assert e["main.lua"]["patch"]["ok"] and "F1" in e["main.lua"]["patch"]["rules"]
    assert not lf.SHIM_V1_RE.search(t) and t.count(lf.SHIM_END) == 1 and t.count("\n") == old.count("\n")
    assert t.startswith(f"--[[localpatch {lf.VERSION}: F1]] local print, mwse, localpatch_log")
    e2, _ = plan(tmp_path / "again", {"main.lua": t})
    assert e2["main.lua"]["patch"] is None                       # stable after the upgrade


@need_lua
def test_flush_timer_is_started_again_after_a_load():
    r = Rt(budgetInit=0)
    r.load("print('x')")
    r.run("fire('initialized')")
    assert r.num("#TIMERS") == 1
    r.run("TIMERS = {} fire('loaded')")              # MWSE cancels every timer right before loaded
    assert r.num("#TIMERS") == 1 and r.num("TIMERS[1].iterations") == -1


@need_lua
def test_lifecycle_words_are_capped_word_by_word():
    r = Rt(budgetInit=0)
    r.load("for i = 1, 500 do print('Registered recipe ' .. i) end print('Error: broke') print('[Mod] Initialized')")
    out = r.out()
    assert len([o for o in out if o.startswith("Registered recipe")]) == 5
    assert "Error: broke" in out and "[Mod] Initialized" in out     # a flood of one word doesn't crowd out another
    assert len([o for o in r.file() if o.startswith("Registered recipe")]) == 500


@need_lua
def test_lines_printed_by_initialized_handlers_reach_mwse_log():
    r = Rt(budgetInit=0)
    r.load("print('setting up') event.register('initialized', function() "
           "print('[Mod] Initialized') print('[Aura] 6.0 initialised') mwse.log('[Mod] MCM registered') "
           "print('[Mod] started') print('routine') end)")
    r.run("fire('initialized')")
    assert r.out() == ["[Mod] Initialized", "[Aura] 6.0 initialised", "[Mod] MCM registered", "[Mod] started"]
    assert "routine" in r.file()


@need_lua
def test_configured_keep_patterns_still_match_british_spelling():
    r = Rt(budgetInit=0, keepPatterns=["error", "initializ"])
    r.load("print('[Mod] initialised')")
    assert r.out() == ["[Mod] initialised"]


@need_lua
def test_nothing_of_ours_is_written_into_the_mods_output():
    for broken in ("", "NOOPEN = true", "FAILW = true"):
        r = Rt(budgetInit=0)
        r.run(broken)
        r.load("print('routine') print('more') print('Error: broke')")
        text = " ".join(r.out() + r.file()).lower()
        assert "luafix" not in text and "mwdialog" not in text and "localpatch" not in text
        assert "error: broke" in text
    shim = lf.log_shim("testmod", CFG).lower()
    assert "luafix" not in shim and "mwdialog" not in shim


@need_lua
def test_dialogue_started_is_not_a_lifecycle_line():
    r = Rt(budgetInit=0)
    r.load(
        "print('[Mod] started') "
        "print(\"[Animated Dialogue | services/events/eventlogger.lua:44  | INFO] "
        "Dialogue started with 'arrille'\") "
        "print('restarting a loop') "
        "print('[AURA i18n]: Starting translation verification.') "
        "print('routine')"
    )
    out = r.out()
    assert "[Mod] started" in out
    assert "[AURA i18n]: Starting translation verification." in out
    assert not any("Dialogue started" in o for o in out)
    assert not any("restarting" in o for o in out)
    assert "routine" not in out
    f = r.file()
    assert any("Dialogue started" in l for l in f)
    assert any("restarting" in l for l in f)
    assert "routine" in f


@need_lua
def test_lifecycle_cap_writes_one_hand_off_line_naming_the_mod_log():
    r = Rt(budgetInit=0)
    r.load("for i = 1, 9 do print('Registered recipe ' .. i) end")
    out = r.out()
    assert len([o for o in out if o.startswith("Registered recipe")]) == 5
    notes = [o for o in out if o.startswith("[log redirect]")]
    assert len(notes) == 1 and "testmod" in notes[0] and "register" in notes[0] and "testmod.log" in notes[0]
    assert len([o for o in r.file() if o.startswith("Registered recipe")]) == 9


def test_bare_start_is_no_longer_a_lifecycle_pattern():
    assert "start" not in lf.LIFECYCLE_PATTERNS and "start" not in CFG["log"]["keepPatterns"]
    assert lf.SHIM_V == 7 and "S.v == 7" in lf.log_shim("testmod", CFG)

# ------------------------------------------------------------------------------------------ fresh logs each session
OWN = "Data Files\\MWSE\\logs\\Own Mod.log"
OWN_OLD = "Data Files\\MWSE\\logs\\Own Mod.old.log"
OPEN_OWN = "local P = [[" + OWN + "]] "


def seed(r, path, text, mtime=None):
    r.run("FILES[ [[" + path + "]] ] = '" + text + "\\n'" + (f" ATTR[ [[{path}]] ] = {mtime}" if mtime else ""))


@need_lua
def test_a_mods_own_appended_log_starts_new_in_a_session_and_is_kept_as_old():
    r = Rt(budgetInit=0)
    seed(r, OWN, "last session", 1)
    r.load(OPEN_OWN + "local f = io.open(P, 'a') f:write('first\\n') f:close() "
           "local g = io.open(P, 'a') g:write('second\\n') io.open(P, 'a'):write('third\\n')")
    assert r.file(OWN) == ["first", "second", "third"]           # new once, then appended for the rest of the session
    assert r.file(OWN_OLD) == ["last session"]                  # the previous session is kept, like the shim's own log
    r.load(OPEN_OWN + "io.open(P, 'a'):write('another file of the mod\\n')", path="testmod\\util.lua")
    assert r.file(OWN)[-1] == "another file of the mod" and len(r.file(OWN)) == 4     # one session: not new again


@need_lua
def test_an_own_log_already_written_this_session_or_not_there_is_appended_to():
    r = Rt(budgetInit=0)
    seed(r, OWN, "written by another mod just now", 2000)
    r.load(OPEN_OWN + "io.open(P, 'a'):write('mine\\n')")
    assert r.file(OWN) == ["written by another mod just now", "mine"] and not r.has(OWN_OLD)
    r = Rt(budgetInit=0)
    r.load(OPEN_OWN + "io.open(P, 'a'):write('first ever\\n')")
    assert r.file(OWN) == ["first ever"] and not r.has(OWN_OLD)


@need_lua
def test_keep_old_zero_deletes_the_previous_own_log():
    r = Rt(budgetInit=0, keepOld=0)
    seed(r, OWN, "last session", 1)
    r.load(OPEN_OWN + "io.open(P, 'a'):write('fresh\\n')")
    assert r.file(OWN) == ["fresh"] and not r.has(OWN_OLD)


@need_lua
def test_only_append_opens_of_logs_under_mwse_logs_are_touched():
    cfgfile = "Data Files\\MWSE\\config\\Own Mod.json"
    outside = "Data Files\\Own Mod.log"
    olderlog = "Data Files\\MWSE\\logs\\Other Mod.old.log"
    r = Rt(budgetInit=0)
    for path in (OWN, cfgfile, outside, olderlog):
        seed(r, path, "keep", 1)
    r.run("io.lines = function() return 'passed through' end")
    r.load("io.open([[" + OWN + "]], 'r') io.open([[" + cfgfile + "]], 'a'):write('x\\n') "
           "io.open([[" + outside + "]], 'a'):write('x\\n') io.open([[" + olderlog + "]], 'a'):write('x\\n') "
           "SEEN = io.lines()")
    assert r.file(cfgfile) == ["keep", "x"] and r.file(outside) == ["keep", "x"] and r.file(olderlog) == ["keep", "x"]
    assert r.file(OWN) == ["keep"] and not r.has(OWN_OLD)       # a read-mode open does not start a session either
    assert r.eval("SEEN == 'passed through'")                  # everything else of io is still there


@need_lua
def test_forward_slash_paths_count_as_the_same_log():
    slash, slash_old = "Data Files/MWSE/logs/Own Mod.log", "Data Files/MWSE/logs/Own Mod.old.log"
    r = Rt(budgetInit=0)
    seed(r, slash, "last", 1)
    r.load("local P = [[" + slash + "]] io.open(P, 'a'):write('a\\n') io.open(P, 'a'):write('b\\n')")
    assert r.file(slash) == ["a", "b"] and r.file(slash_old) == ["last"]


@need_lua
def test_a_log_from_an_earlier_session_is_set_aside_at_initialized_when_nothing_wrote_it():
    r = Rt(budgetInit=5)
    seed(r, LOG, "ancient", 1)
    seed(r, OLD, "older")
    r.load("print('[Mod] hello')")                               # inside the allowance: the log is never opened
    assert r.file() == ["ancient"]
    r.run("fire('initialized')")
    assert not r.has(LOG) and r.file(OLD) == ["ancient"]        # one generation back, like MWSE.log's restart
    r = Rt(budgetInit=5)
    seed(r, LOG, "written this session", 2000)
    r.load("print('x')")
    r.run("fire('initialized')")
    assert r.file() == ["written this session"] and not r.has(OLD)


@need_lua
def test_the_shims_own_log_is_not_set_aside_twice_in_a_session():
    r = Rt(budgetInit=0)
    seed(r, LOG, "last session", 1)
    r.load("print('first')")
    r.run("fire('initialized')")
    r.load("print('second')", path="testmod\\late.lua")
    r.run("package.loaded['localpatch_logshim:testmod'].flush()")
    assert r.file(OLD) == ["last session"] and r.file()[-2:] == ["first", "second"]


def test_a_file_that_appends_to_its_own_log_gets_the_shim_with_its_io(tmp_path):
    src = "local P = 'Data Files\\\\MWSE\\\\logs\\\\x.log'\nlocal f = io.open(P, 'a')\nf:write('x')\n"
    e, _ = plan(tmp_path / "a", {"main.lua": src})
    t = e["main.lua"]["patch"]["text"]
    assert e["main.lua"]["patch"]["ok"]
    assert t.startswith(f"--[[localpatch {lf.VERSION}: F1]] local print, mwse, localpatch_log, io =")
    assert "io.open(P, 'a')" in t                               # the mod's own line is not touched
    e, _ = plan(tmp_path / "b", {"main.lua": "local f = io.open('Data Files\\\\x.txt', 'r')\n"})
    assert e["main.lua"]["patch"] is None                       # reading, or no logging at all: no shim


def test_a_version_6_shim_is_upgraded_to_the_one_with_io(tmp_path):
    v7 = lf.log_shim("testmod", CFG)
    assert "localpatch_log, io = (function" in v7
    v6 = v7.replace("localpatch_log, io = (function", "localpatch_log = (function").replace("S.v == 7", "S.v == 6")
    v6 = v6.replace("return S.print, S.mwse, S, S.io", "return S.print, S.mwse, S")
    assert lf.SHIM_RE.search(v6)
    e, _ = plan(tmp_path, {"main.lua": "--[[localpatch 5: F1]] " + v6 + "print('x')\n"})
    t = e["main.lua"]["patch"]["text"]
    assert e["main.lua"]["patch"]["ok"] and "S.v == 7" in t and "S.v == 6" not in t and t.count(lf.SHIM_END) == 1


# ------------------------------------------------------------------------- plan, then --apply (cached second read)
class MemCache:
    """The asset cache's get/put, JSON round-tripped like the real one, in memory."""

    def __init__(self):
        self.d = {}

    def get(self, key, stamp):
        hit = self.d.get(key)
        return json.loads(hit[1]) if hit and hit[0] == stamp else None

    def put(self, key, stamp, result):
        self.d[key] = (stamp, json.dumps(result))


@pytest.fixture
def mem_cache(monkeypatch):
    from conftest import ah
    cache = MemCache()
    monkeypatch.setattr(lf, "_cache", lambda game_dir: (ah, cache))
    return cache


@pytest.mark.parametrize("src,scope", [(SPAM, None), (SPAM, "off"), (LOGGER, None), (LOGGER, "off")])
def test_a_cached_second_read_plans_the_same_f1_lines_as_the_first(tmp_path, mem_cache, src, scope):
    data, _root = mod_tree(tmp_path, {"main.lua": src})

    def lines():
        rep = lf.check_paths([str(data)], CFG, checker=OkChecker(), use_cache=True, data_dir=str(tmp_path / "none"),
                             log_scope=scope)
        return lf.format_report(rep, indent="  ")[0]

    first = lines()
    assert mem_cache.d                                               # the second read comes from the cache
    assert lines() == first
    f1 = [ln for ln in first if " F1 " in ln]
    assert f1 and all("-> log shim" not in ln or "-> log shim:" in ln for ln in f1)


def test_plan_then_apply_round_trip_with_the_shim_is_not_refused(tmp_path, mem_cache, monkeypatch, capsys):
    game = tmp_path / "game"
    (game / "Data Files").mkdir(parents=True)
    data, root = mod_tree(tmp_path, {"main.lua": SPAM})
    monkeypatch.setattr(lf, "HERE", str(game))
    monkeypatch.setattr(lf, "JOURNAL", str(tmp_path / "luafix_journal.jsonl"))
    monkeypatch.setattr(lf, "BACKUP_ROOT", str(tmp_path / "backups"))
    monkeypatch.setattr(lf, "find_checker", lambda explicit=None, game_dir=None: OkChecker())
    monkeypatch.setattr(lf, "load_config", lambda game_dir=None, data_dir=None: dict(CFG, _sources=[]))
    assert lf.main([str(data)]) == 0                                 # plan: the file is read and cached
    plan = open(lf.PLAN_FILE, encoding="utf-8").read()
    assert "-> log shim: past its first" in plan
    capsys.readouterr()
    assert lf.main([str(data), "--apply", "--yes"]) == 0             # --apply: the same plan from the cache
    out = capsys.readouterr().out
    assert "REFUSED" not in out and "The plan matches the one you reviewed." in out
    assert lf.SHIM_END in (root / "main.lua").read_text(encoding="latin-1")

# ------------------------------------------------------------------------------------ F1: shimmed / high / report
ELSEWHERE = ("local log = require('othermod.mylog')\nlocal function onSim(e)\n  log:debug('frame')\nend\n"
             "event.register('simulate', onSim)\n")


def f1_of(entry):
    return [f for f in entry["findings"] if f["rule"] == "F1"]


def counts_of(rep):
    return lf.format_report(rep, indent="  ")[1]


def test_a_mod_with_the_current_shim_shows_f1_as_shimmed_not_high(tmp_path):
    e, _ = plan(tmp_path / "a", {"main.lua": SPAM})
    assert e["main.lua"]["patch"]["ok"]
    shimmed_text = e["main.lua"]["patch"]["text"]
    e, rep = plan(tmp_path / "b", {"main.lua": shimmed_text})
    ent = e["main.lua"]
    assert ent["patch"] is None                                       # nothing left to write
    f1 = f1_of(ent)
    assert f1 and {f["conf"] for f in f1} == {"shimmed"}
    assert all(f["fix"] == f"already handled by the log shim (v{lf.SHIM_V})" for f in f1)
    counts = counts_of(rep)
    assert ("F1", "shimmed") in counts and ("F1", "high") not in counts
    assert f"  F1: {len(f1)} shimmed" in lf.summary_lines(counts)
    assert not lf.pending_lines(rep)                                  # no plan line for it
    for level in ("high", "medium"):                                  # --lua-level gating is unchanged
        rep2 = lf.check_paths([str(tmp_path / "b" / "Mod")], CFG, checker=OkChecker(), use_cache=False,
                              data_dir=str(tmp_path / "none"), level=level)
        for x in rep2.files.values():                                  # (medium may gate the frame handler: not F1)
            assert {f["conf"] for f in f1_of(x)} == {"shimmed"}
            assert not x["patch"] or "F1" not in x["patch"]["rules"]


def test_a_mod_that_needs_the_shim_still_shows_f1_high_and_plans_the_patch(tmp_path):
    e, rep = plan(tmp_path, {"main.lua": SPAM})
    ent = e["main.lua"]
    assert {f["conf"] for f in f1_of(ent)} == {"high"}
    assert ent["patch"]["ok"] and "F1" in ent["patch"]["rules"]
    assert lf.SHIM_END in ent["patch"]["text"]
    assert ("F1", "high") in counts_of(rep) and ("F1", "shimmed") not in counts_of(rep)
    assert any("patch ready (F1)" in ln for ln in lf.pending_lines(rep))


def test_an_old_shim_shows_f1_high_and_the_patch_upgrades_it(tmp_path, monkeypatch):
    monkeypatch.setattr(lf, "SHIM_V", lf.SHIM_V - 1)
    e, _ = plan(tmp_path / "a", {"main.lua": SPAM})
    old_text = e["main.lua"]["patch"]["text"]
    assert f"S.v == {lf.SHIM_V}" in old_text
    monkeypatch.undo()
    e, rep = plan(tmp_path / "b", {"main.lua": old_text})
    ent = e["main.lua"]
    assert ent["old_shim"] and ent["shim_state"] == "old"
    assert {f["conf"] for f in f1_of(ent)} == {"high"}
    assert ent["patch"]["ok"] and "F1" in ent["patch"]["rules"]
    assert f"S.v == {lf.SHIM_V}" in ent["patch"]["text"] and f"S.v == {lf.SHIM_V - 1}" not in ent["patch"]["text"]
    assert ("F1", "shimmed") not in counts_of(rep)


def test_a_cached_file_is_judged_again_when_the_shim_version_changes(tmp_path, mem_cache, monkeypatch):
    """Seen 2026-11-26: tidy cached "this file's shim is current" at v6; after v7 the cache still said so, so 138
    F1 findings showed high and no upgrade was planned."""
    monkeypatch.setattr(lf, "SHIM_V", lf.SHIM_V - 1)
    e, _ = plan(tmp_path / "a", {"main.lua": SPAM})
    v_old = e["main.lua"]["patch"]["text"]
    data, _root = mod_tree(tmp_path / "b", {"main.lua": v_old})

    def run():
        rep = lf.check_paths([str(data)], CFG, checker=OkChecker(), use_cache=True, data_dir=str(tmp_path / "none"))
        return next(iter(rep.files.values())), rep

    ent, rep = run()                                                   # cached while v(N-1) is current
    assert ent["shim_state"] == "current" and ent["patch"] is None
    assert {f["conf"] for f in f1_of(ent)} == {"shimmed"}
    ent, rep = run()
    assert ent.get("cached") and {f["conf"] for f in f1_of(ent)} == {"shimmed"}
    monkeypatch.undo()                                                 # the shim moves on to the next version
    ent, rep = run()
    assert not ent.get("cached")                                       # the stale entry is not trusted
    assert ent["shim_state"] == "old" and {f["conf"] for f in f1_of(ent)} == {"high"}
    assert ent["patch"]["ok"] and "F1" in ent["patch"]["rules"]
    first = lf.format_report(rep, indent="  ")[0]
    ent, rep = run()                                                   # and from the cache again: same plan lines
    assert ent.get("cached") and lf.format_report(rep, indent="  ")[0] == first


def test_shimmed_plan_lines_are_the_same_cached_or_not(tmp_path, mem_cache):
    e, _ = plan(tmp_path / "a", {"main.lua": SPAM})
    data, _root = mod_tree(tmp_path / "b", {"main.lua": e["main.lua"]["patch"]["text"]})

    def lines():
        rep = lf.check_paths([str(data)], CFG, checker=OkChecker(), use_cache=True, data_dir=str(tmp_path / "none"))
        return lf.format_report(rep, indent="  ")[0]
    first = lines()
    assert any(" F1 shimmed " in ln for ln in first) and lines() == first


def test_an_f1_trigger_the_shim_cannot_reach_is_a_report_not_a_high(tmp_path):
    """Crafting Framework: the handler logs through a logger made in another mod; no patch is possible."""
    e, rep = plan(tmp_path, {"main.lua": ELSEWHERE})
    ent = e["main.lua"]
    f1 = f1_of(ent)
    assert f1 and {f["conf"] for f in f1} == {"report"}
    assert "no repair planned" in f1[0]["fix"]
    assert ent["patch"] is None
    assert ("F1", "high") not in counts_of(rep)


def test_finding_status_after_apply_says_shimmed(tmp_path):
    e, _ = plan(tmp_path / "a", {"main.lua": SPAM})
    e, rep = plan(tmp_path / "b", {"main.lua": e["main.lua"]["patch"]["text"]})
    out = lf.format_report(rep, done=[], indent="  ")[0]
    assert any("SHIMMED: F1" in ln for ln in out)

def test_f1_in_a_second_file_follows_whether_the_patch_reaches_it(tmp_path):
    e, rep = plan(tmp_path / "a", {"main.lua": SPAM, "other.lua": ELSEWHERE})
    assert {f["conf"] for f in f1_of(e["main.lua"])} == {"high"} and "F1" in e["main.lua"]["patch"]["rules"]
    assert {f["conf"] for f in f1_of(e["other.lua"])} == {"report"}          # its logger is made somewhere unseen
    logger_file = "local log = mwse.Logger.new()\nreturn log\n"
    e, rep = plan(tmp_path / "b", {"log.lua": logger_file, "other.lua": ELSEWHERE})
    assert {f["conf"] for f in f1_of(e["other.lua"])} == {"high"}            # the wrapped logger may be the one it uses
    assert "F1" in e["log.lua"]["patch"]["rules"]