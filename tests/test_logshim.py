"""The F1 log shim: the static replacement for the old mwguard's log-spam guard. Python patch tests, then the
shim itself run in LuaJIT (lupa) with mwse, io, lfs, os.time, event and timer mocked."""
import json
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
    assert e["main.lua"]["patch"] is None                       # flagged: no spam signs, no shim
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
        assert t.count('package.loaded["mwluafix_logshim:testmod"]') == 2 and lf.SHIM_END in t
    assert e["data.lua"]["patch"] is None                       # no logging: untouched


def test_logger_creations_are_wrapped_only_with_the_shim(tmp_path):
    e, _ = plan(tmp_path / "a", {"main.lua": LOGGER})
    t = e["main.lua"]["patch"]["text"]
    assert "local log = mwluafix_log.wrap(mwse.Logger.new())" in t
    assert "local old = mwluafix_log.wrap(L2.new{ name = 'x' })" in t
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
    assert c["log"]["scope"] == "all" and c["log"]["budget"] == 10 and c["log"]["exemptMods"] == ["a"]
    assert lf.DEFAULTS["log"]["perSecond"] == 50                # defaults untouched
    shim = lf.log_shim("testmod", c)
    assert "init = 7," in shim and "perSecond = 9," in shim and "maxBytes = 1048576," in shim


@need_lua
def test_shim_compiles_in_luajit_and_keeps_one_line():
    s = lf.log_shim("abot/Some Mod", CFG)
    assert "\n" not in s and s.rstrip().endswith(lf.SHIM_END)
    rt = _lj.LuaRuntime()
    assert rt.eval("loadstring(...) ~= nil", s + "return 1") is True


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


class Rt:
    def __init__(self, **log):
        self.cfg = cfg(**dict(dict(perSecond=0), **log))
        self.rt = _lj.LuaRuntime(unpack_returned_tuples=True)
        self.rt.execute(ENV)
        self.g = self.rt.globals()

    def load(self, body, name="testmod", path="testmod\\main.lua", shim=True):
        code = (lf.log_shim(name, self.cfg) if shim else "") + body
        return self.rt.globals().loadMod(path, code)

    def run(self, lua):
        return self.rt.execute(lua)

    def out(self):
        return list(self.g.OUT.values())

    def file(self, path=LOG):
        return [l.split("] ", 1)[1] if l.startswith("[") and "] " in l else l
                for l in self.g.lines(path).values()]

    def has(self, path):
        return self.g.FILES[path] is not None


@need_lua
def test_first_lines_pass_then_the_rest_goes_to_the_mod_log():
    r = Rt(budgetInit=5)
    r.load("for i = 1, 20 do print('line ' .. i) end mwse.log('fmt %d', 21) print('a', 'b')")
    out = r.out()
    assert out[:5] == [f"line {i}" for i in range(1, 6)]
    assert len(out) == 6 and "testmod has written 5 line(s)" in out[5] and LOG in out[5]
    f = r.file()
    assert "lines past its MWSE.log allowance" in f[0]
    assert f[1:] == [f"line {i}" for i in range(6, 21)] + ["fmt 21", "a\tb"]


@need_lua
def test_budget_after_initialized_and_shared_by_the_mods_files():
    r = Rt(budgetInit=4, budget=2)
    r.load("print('m1') print('m2')")
    r.load("print('u1') print('u2')", path="testmod\\util.lua")      # same mod: same allowance
    r.run("fire('initialized')")
    r.load("print('late1') print('late2') print('late3')", path="testmod\\late.lua")
    out = r.out()
    assert out[:6] == ["m1", "m2", "u1", "u2", "late1", "late2"] and "has written 6 line(s)" in out[6]
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
    r.run("package.loaded['mwluafix_logshim:testmod'].flush()")
    assert r.file()[1:] == ["same", "[previous line repeated 9 more time(s)]", "other", "again",
                            "[previous line repeated 2 more time(s)]"]


@need_lua
def test_per_second_cap_on_the_mod_log():
    r = Rt(budgetInit=0, perSecond=5)
    r.load("for i = 1, 20 do print('l' .. i) end TIME = TIME + 1 print('next second')")
    f = r.file()[1:]
    assert f[:5] == [f"l{i}" for i in range(1, 6)]
    assert f[5] == "[15 line(s) dropped: more than 5 in one second]" and f[6] == "next second"
    assert len(r.out()) == 1                                    # only the redirect notice


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
    assert r.file("Data Files\\MWSE\\logs\\testmod.luafix.log")[-1] == "new"


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
    assert sum("log shim error" in o for o in out) == 1 and "w15" in out
    r.run("FAILW = false")
    r.load("print('after')", path="testmod\\c.lua")
    assert r.out()[-1] == "after"                               # ten failures: passes through from then on


@need_lua
def test_other_mods_and_the_global_print_are_untouched():
    r = Rt(budgetInit=0)
    r.load("print('spam')")
    assert r.rt.eval("print == ORIG_PRINT and mwse.log ~= nil and getmetatable(mwse) == nil")
    r.load("for i = 1, 60 do print('other ' .. i) end", name="other", path="other\\main.lua", shim=False)
    assert r.out()[-60:] == [f"other {i}" for i in range(1, 61)]


@need_lua
def test_flushing_buffered_after_initialized():
    r = Rt(budgetInit=0, flushSeconds=3)
    r.load("print('a')")
    before = r.g.FLUSHES
    assert before >= 1                                          # startup lines are flushed at once
    r.run("fire('initialized')")
    assert r.g.TIMERS[1].duration == 3 and r.g.TIMERS[1].iterations == -1
    n = r.g.FLUSHES
    r.load("print('b') print('c')", path="testmod\\x.lua")
    assert r.g.FLUSHES == n                                     # buffered now
    r.run("fire('save')")
    assert r.g.FLUSHES == n + 1
    r.run("TIMERS[1].callback()")                               # nothing new: no flush
    assert r.g.FLUSHES == n + 1


@need_lua
def test_generic_logger_methods_wrapped():
    r = Rt(budgetInit=2)
    r.run("LOGGERS = {} mwse.Logger = { new = function() local lg = { lv = 3 } "
          "function lg:info(m) if self.lv >= 3 then print('[INFO] ' .. m) end end "
          "function lg:debug(m) if self.lv >= 4 then print('[DEBUG] ' .. m) end end "
          "function lg:warn(m) print('[WARN] ' .. m) end LOGGERS[#LOGGERS + 1] = lg return lg end }")
    r.load("local log = mwluafix_log.wrap(mwse.Logger.new()) "
           "for i = 1, 5 do log:info('i' .. i) end log:debug('hidden') log:warn('careful') "
           "LOG_IS = log return log")
    out = r.out()
    assert out[:2] == ["[INFO] i1", "[INFO] i2"] and "[WARN] careful" in out
    assert "[INFO] i3" not in out and r.file()[-3:] == ["[INFO] i3", "[INFO] i4", "[INFO] i5"]
    assert "hidden" not in " ".join(out + r.file())             # the logger's own level still decides
    assert r.rt.eval("print == ORIG_PRINT and LOG_IS == LOGGERS[1]")


MWSE_CORE = "/workspace/mwse_src/misc/package/Data Files/MWSE/core"


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
    ok = r.rt.eval("pcall(function() mwse.Logger = require('logger') end)")
    if not (ok if isinstance(ok, bool) else ok[0]):
        pytest.skip("MWSE's logger doesn't load with these stubs")
    try:
        r.load("local log = mwluafix_log.wrap(mwse.Logger.new{ modName = 'testmod', level = 'DEBUG' })\n"
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
    assert r.rt.eval("print == ORIG_PRINT")


V1_SHIM = None


def _v1_shim():
    """The version-1 shim exactly as the first release wrote it (from git), for the upgrade test."""
    import subprocess
    src = subprocess.run(["git", "show", "7b13bc1:mwdialog_luafix.py"], capture_output=True, text=True,
                         cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).stdout
    if not src:
        pytest.skip("no git history here")
    ns = {}
    start = src.index("def lua_str(")
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
    assert t.startswith(f"--[[mwdialog_luafix {lf.VERSION}: F1]] local print, mwse, mwluafix_log")
    e2, _ = plan(tmp_path / "again", {"main.lua": t})
    assert e2["main.lua"]["patch"] is None                       # stable after the upgrade
