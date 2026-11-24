"""mwpluginpatches' "illegible handwriting" filter: An-Drazh's line gives the note only after its text is read, so
requiring the note hid the topic at the one moment it is learned. It goes away when the quest is finished (70), not
at 50 (Nallaia answers it at 60), and a save that never learned it gets it back."""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.path.join(ROOT, "tools", "luajit", "luajit.exe")
MODS = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

SCRIPT = r"""
local handlers, stage, notes, added = {}, 0, 0, {}
event = { register = function(name, fn) handlers[name] = fn end }
mwse = { log = function() end }
tes3 = { player = {}, event = setmetatable({}, { __index = function(_, k) return k end }),
         getJournalIndex = function() return stage end, getItemCount = function() return notes end,
         addTopic = function(p) added[#added + 1] = p.topic end }
package.loaded["mwpluginpatches.config"] = { talesHandwritingFixEnabled = true,
                                             isTalesOfSeydaNeenActive = function() return true end }
package.path = [[MODS\?.lua;]] .. package.path
require("mwpluginpatches.patches.talesHandwritingFix").init()
local function offered(topic)
  local e = { dialogue = { id = topic or "Illegible Handwriting" }, passes = true }
  handlers.infoFilter(e)
  return e.passes
end
local function check(ok, what) if not ok then error(what, 2) end end

check(offered(), "stage 0, no note yet: offered while An-Drazh's line is read, or it is never learned")
handlers.journal({ topic = { id = "den_bottle" }, index = 10 })
check(added[1] == "illegible handwriting", "learned as the quest starts")
stage, notes = 10, 1
check(offered(), "stage 10 with the note")
stage, notes = 60, 0
check(offered(), "Nallaia answers it at 60")
stage = 70
check(not offered(), "gone once the quest is finished")
check(offered("little secret"), "other topics untouched")

added = {}
stage = 10; handlers.loaded()
check(added[1] == "illegible handwriting", "a save that never learned it gets it back")
added = {}
stage = 70; handlers.loaded()
stage = 0; handlers.loaded()
handlers.journal({ topic = { id = "den_bottle" }, index = 70 })
handlers.journal({ topic = { id = "other_quest" }, index = 10 })
check(#added == 0, "not before the quest, after it, or for another quest")
print("ok")
"""


def test_the_topic_is_learned_and_goes_away_when_the_quest_is_finished():
    out = subprocess.run([LUAJIT, "-"], input=SCRIPT.replace("MODS", MODS), capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stderr + out.stdout
