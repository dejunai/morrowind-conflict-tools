"""mwpluginpatches' "illegible handwriting" filter: An-Drazh's line gives the note only after its text is read, so
requiring the note hid the topic at the one moment it is learned. It goes away when the quest is finished (70), not
at 50 (Nallaia answers it at 60), and a save that never learned it gets it back."""
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(ROOT, "tools", "luajit", "luajit.exe"))
MODS = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite")
pytestmark = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

SCRIPT = r"""
local lists, stage, notes, added = {}, 0, 0, {}
local function list(n) lists[n] = lists[n] or {} return lists[n] end
event = {
  register = function(n, fn) local l = list(n) for _, f in ipairs(l) do if f == fn then return end end l[#l + 1] = fn end,
  unregister = function(n, fn) local l = list(n) for i = #l, 1, -1 do if l[i] == fn then table.remove(l, i) end end end,
}
local function fire(n, e) e = e or {} for _, f in ipairs({ unpack(list(n)) }) do f(e) end return e end
mwse = { log = function() end }
tes3 = { event = setmetatable({}, { __index = function(_, k) return k end }),
         getJournalIndex = function() return stage end, getItemCount = function() return notes end,
         addTopic = function(p) added[#added + 1] = p.topic end }
package.loaded["mwpluginpatches.config"] = { talesHandwritingFixEnabled = true,
                                             isTalesOfSeydaNeenActive = function() return true end }
package.path = [[MODS\?.lua;]] .. package.path
local patch = require("mwpluginpatches.patches.talesHandwritingFix")
patch.init()
local function offered(topic)
  local e = { dialogue = { id = topic or "Illegible Handwriting" }, passes = true }
  fire("infoFilter", e)
  return e.passes
end
local function check(ok, what) if not ok then error(what, 2) end end

check(#list("loaded") == 1 and #list("journal") == 0 and #list("infoFilter") == 0, "only loaded before a game")
fire("loaded")
check(#list("journal") == 1 and #list("infoFilter") == 0, "quest not finished: journal hook only, no filter")
check(offered(), "stage 0, no note yet: offered while An-Drazh's line is read, or it is never learned")
fire("journal", { topic = { id = "den_bottle" }, index = 10 })
check(added[1] == "illegible handwriting", "learned as the quest starts")
stage, notes = 10, 1
check(offered(), "stage 10 with the note")
stage, notes = 60, 0
check(offered(), "Nallaia answers it at 60")
stage = 70
fire("journal", { topic = { id = "den_bottle" }, index = 70 })
check(not offered(), "gone once the quest is finished")
check(offered("little secret"), "other topics untouched")
check(#list("journal") == 0 and #list("infoFilter") == 1, "after the quest: the journal hook is gone, the filter stays")

added = {}
stage = 10; fire("loaded")
check(added[1] == "illegible handwriting", "a save that never learned it gets it back")
check(#list("journal") == 1 and #list("infoFilter") == 0, "an earlier save: back to the journal hook, no filter")
added = {}
stage = 70; fire("loaded")
check(#list("journal") == 0 and #list("infoFilter") == 1, "a finished save: filter only")
stage = 0; fire("loaded")
fire("journal", { topic = { id = "den_bottle" }, index = 70 })
fire("journal", { topic = { id = "other_quest" }, index = 10 })
check(#added == 0, "not before the quest, after it, or for another quest")
print("ok")
"""

def test_the_topic_is_learned_and_goes_away_when_the_quest_is_finished():
    out = subprocess.run([LUAJIT, "-"], input=SCRIPT.replace("MODS", MODS), capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip().endswith("ok"), out.stderr + out.stdout
