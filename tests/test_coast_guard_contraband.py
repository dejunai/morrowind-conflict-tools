"""mwpluginpatches' Seyda Neen Coast Guard contraband patch, run in LuaJIT with stub MWSE calls: all of one kind is
turned in at once (the guard's own script takes the first), a kind turned off is kept, and a response's text read by
anything else (UI Expansion reads info.text too) never turns contraband in on another response."""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MODS = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

STUBS = r"""
counts, removed, added, handlers = {}, {}, {}, {}
tes3 = {
  player = {},
  getItemCount = function(p) return counts[p.item] or 0 end,
  removeItem = function(p) removed[#removed + 1] = p.item .. "x" .. p.count; counts[p.item] = counts[p.item] - p.count end,
  addItem = function(p) added[#added + 1] = p.item .. "x" .. p.count end,
  messageBox = function() end,
}
tes3ui = { findMenu = function() end, registerID = function() end }
timer = { delayOneFrame = function() end }
event = { register = function(name, fn) handlers[name] = fn end }
config = { coastGuardContrabandEnabled = true, coastGuardBulkTurnIn = true, coastGuardHideExhausted = true,
           coastGuardTurnInSkooma = true, coastGuardTurnInRawEbony = false }
package.loaded["mwpluginpatches.config"] = config
SKOOMA, EBONY, OTHER = "394419472248279556", "2346497772141610621", "999"
function said(id) local e = { dialogue = { id = "Contraband" }, info = { id = id }, text = "" }
  handlers.infoGetText(e) return e end
function filter(id) local e = { dialogue = { id = "Contraband" }, info = { id = id }, passes = true }
  handlers.infoFilter(e) return e.passes end
function check(ok, what) if not ok then error(what, 2) end end
"""


def run(body):
    script = (STUBS + "\npackage.path = [[" + MODS + "\\?.lua;]] .. package.path\n"
              + 'require("mwpluginpatches.patches.coastGuardContraband").init()\n' + body + "\nprint('ok')\n")
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stderr + out.stdout


def test_all_bottles_are_turned_in_at_once():
    run(r"""
counts.potion_skooma_01 = 3
local e = said(SKOOMA)
check(e.text:find("150 drakes for all 3 bottles", 1, true), "the guard names the whole lot")
handlers.infoResponse({ info = { id = SKOOMA } })
check(removed[1] == "potion_skooma_01x2" and added[1] == "gold_001x100", "two more than the guard's script takes")
""")


def test_text_read_elsewhere_never_turns_contraband_in_on_another_response():
    run(r"""
counts.potion_skooma_01 = 3
said(SKOOMA)                                      -- read by another mod, never said
handlers.infoResponse({ info = { id = OTHER } })  -- some other response plays
check(#removed == 0 and #added == 0, "nothing turned in")
handlers.infoResponse({ info = { id = SKOOMA } })
check(#removed == 0, "the stale turn-in is gone, not kept for later")
""")


def test_a_kind_turned_off_is_kept():
    run(r"""
counts.ingred_raw_ebony_01 = 4
check(filter(EBONY) == false, "the guard doesn't ask for ebony")
counts.potion_skooma_01 = 1
check(filter(SKOOMA) == true, "skooma is still asked for")
""")
