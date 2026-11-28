"""mwsaveguard's routine notices (every save requested, deferred, completed) go to Data Files\\MWSE\\logs\\
mwsaveguard.log, not MWSE.log, where they buried everything else; the MCM switch copies them back. Its main.lua
runs in LuaJIT with stub MWSE calls, in a temporary game folder."""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MODS = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

STUBS = r"""
local function stub()
  return setmetatable({}, { __index = function() return stub() end, __call = function() return nil end })
end
logged, handlers, copy = {}, {}, COPY
mwse = setmetatable({
  log = function(fmt, ...) logged[#logged + 1] = string.format(fmt, ...) end,
  loadConfig = function(_, d) local c = {} for k, v in pairs(d) do c[k] = v end
                               if copy ~= nil then c.copyNoticesToMWSELog = copy end return c end,
}, { __index = function() return stub() end })
event = setmetatable({ register = function(name, fn) handlers[name] = fn end }, { __index = function() return stub() end })
tes3, tes3ui, timer = stub(), stub(), stub()
lfs = { mkdir = function(p) os.execute('mkdir "' .. p .. '" 2>nul') end }
"""


def run(tmp_path, copy):
    script = (STUBS.replace("COPY", "true" if copy else "nil")
              + "\npackage.path = [[" + MODS + "\\?.lua;" + MODS + "\\?\\init.lua;]] .. package.path\n"
              + 'dofile([[' + os.path.join(MODS, "mwsaveguard", "main.lua") + ']])\n'
              + "handlers.saved({ filename = 'quiksave', name = 'Quicksave' })\n"
              + "for _, l in ipairs(logged) do print('MWSE.log: ' .. l) end\nprint('ok')\n")
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, timeout=60, cwd=tmp_path)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stderr + out.stdout
    own = tmp_path / "Data Files" / "MWSE" / "logs" / "mwsaveguard.log"
    return out.stdout, own.read_text(encoding="utf-8") if own.exists() else ""


def test_save_notices_go_to_their_own_log(tmp_path):
    mwse_log, own = run(tmp_path, copy=False)
    assert "Save completed: file='quiksave'" in own
    assert "Save completed" not in mwse_log
    assert "Initialized successfully" in mwse_log          # the startup line still reaches MWSE.log


def test_the_mcm_switch_copies_them_to_mwse_log(tmp_path):
    mwse_log, own = run(tmp_path, copy=True)
    assert "Save completed" in mwse_log and "Save completed" in own
