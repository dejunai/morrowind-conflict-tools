"""CR-6: the MWSE suite's data is built with this tool's own patches as the last word (Cell Fixes above all), an
item is judged by what its real author knew, --fix can rewrite the data on the final load order alone
(run_cell_conflicts(aux_only=True)), and mwfloatfix stops trusting a list older than the patches it was built on."""
import json
import os
import struct
import subprocess
import types

import pytest

from conftest import m, plugin, rec, sub, z
from mwdialog_cellmods import float_items, fnv1a_file

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.path.join(ROOT, "tools", "luajit", "luajit.exe")
MOD = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwfloatfix", "main.lua")
FIXES = next(x for x in m.OUR_PATCHES if "cell fixes" in x.lower())

TAGS = {"dock": "STAT", "bucket": "MISC"}
DEPS = {"morrowind.esm": set(), "ports.esp": {"morrowind.esm"}, "squat.esp": {"morrowind.esm"},
        FIXES.lower(): {"morrowind.esm", "ports.esp", "squat.esp"},
        m.AUTO_MERGE_NAME.lower(): {"morrowind.esm"}}


def _dock_deleted_by_ports():
    return [(0, "morrowind.esm", "dock", (100.0, 100.0, 0.0), 1.0, False), (1, "ports.esp", "dock", None, 1.0, True)]


def test_an_item_our_cell_fixes_moved_is_judged_by_its_real_author():
    """Squat put the bucket on the vanilla dock, Ports deleted the dock, Cell Fixes nudged the bucket: before, the
    bucket's last version was Cell Fixes', which 'knows' Ports, so it was never listed."""
    hist = {("e", 0, 0): {
        ("morrowind.esm", 1): _dock_deleted_by_ports(),
        ("squat.esp", 1): [(2, "squat.esp", "bucket", (110.0, 100.0, 34.0), 1.0, False),
                           (2.5, FIXES.lower(), "bucket", (112.0, 100.0, 34.0), 1.0, False)]}}
    deps = lambda p: DEPS[p]
    assert float_items(hist, {}, deps, TAGS) == {}                              # the old judgement
    found = float_items(hist, {}, deps, TAGS, ours=frozenset({FIXES.lower()}))
    assert found == {"#0,0": {("bucket", 112, 100, 34): ("squat.esp", "dock deleted by ports.esp")}}


def test_an_auto_merged_item_is_judged_against_the_masters_alone():
    hist = {("e", 0, 0): {
        ("morrowind.esm", 1): _dock_deleted_by_ports(),
        (m.AUTO_MERGE_NAME.lower(), 1): [(2.5, m.AUTO_MERGE_NAME.lower(), "bucket", (110.0, 100.0, 34.0), 1.0, False)]}}
    found = float_items(hist, {}, lambda p: DEPS[p], TAGS, ours=frozenset({m.AUTO_MERGE_NAME.lower()}),
                        esm_only=frozenset({"morrowind.esm"}))
    assert found == {"#0,0": {("bucket", 110, 100, 34): (m.AUTO_MERGE_NAME.lower(), "dock deleted by ports.esp")}}


def _cell(*refs):
    return rec("CELL", sub("NAME", z("")) + sub("DATA", struct.pack("<Iii", 0, 0, 0)) + b"".join(refs))


def _ref(index, oid, x, zpos, deleted=False):
    tail = sub("DELE", struct.pack("<I", 0)) if deleted else sub("DATA", struct.pack("<6f", x, 100.0, zpos, 0, 0, 0))
    return sub("FRMR", struct.pack("<I", index)) + sub("NAME", z(oid)) + tail


def _chargen_dock(tmp_path):
    """The Seyda Neen chargen dock, as on the stress-test install: Ports deletes the vanilla dock, Expanded Sounds
    puts the same reference back on the same spot (only its object changes), Cell Fixes deletes it again, and the
    bucket Damp Little Squat set on the vanilla dock is left in the air."""
    data = tmp_path / "Data Files"
    data.mkdir()
    size = len(plugin(data / "Master.esm", [], [
        rec("STAT", sub("NAME", z("dock")) + sub("MODL", z("dock.nif"))),
        rec("ACTI", sub("NAME", z("creaky_dock")) + sub("MODL", z("dock.nif"))),
        rec("MISC", sub("NAME", z("bucket")) + sub("MODL", z("bucket.nif"))),
        _cell(_ref(1, "dock", 100.0, 73.8))]))
    plugin(data / "Ports.esp", [("Master.esm", size)], [_cell(_ref((1 << 24) | 1, "dock", 0, 0, deleted=True))])
    plugin(data / "Squat.esp", [("Master.esm", size)], [_cell(_ref(1, "bucket", 110.0, 107.9))])
    plugin(data / "Sounds.esp", [("Master.esm", size)], [_cell(_ref((1 << 24) | 1, "creaky_dock", 100.0, 73.8))])
    order = ["Master.esm", "Ports.esp", "Squat.esp", "Sounds.esp"]
    return data, size, order


def test_without_cell_fixes_the_bucket_looks_supported(tmp_path):
    """Why the list --full wrote before Cell Fixes existed missed the bucket: the dock looks untouched."""
    data, _size, order = _chargen_dock(tmp_path)
    args = types.SimpleNamespace(data_dir=str(data), dry_run=False)
    m.run_cell_conflicts(args, [(n, str(data / n)) for n in order], aux_only=True)
    listed = json.loads((data / "MWSE" / "config" / "mwfloatfix_data.json").read_text())["cells"]
    assert "#0,0" not in listed


def test_aux_only_writes_the_suite_data_with_cell_fixes_as_the_last_word(tmp_path, capsys):
    data, size, order = _chargen_dock(tmp_path)
    plugin(data / FIXES, [("Master.esm", size)], [_cell(_ref((1 << 24) | 1, "creaky_dock", 0, 0, deleted=True))])
    args = types.SimpleNamespace(data_dir=str(data), dry_run=False)
    assert m.run_cell_conflicts(args, [(n, str(data / n)) for n in order + [FIXES]], aux_only=True) == 0
    assert "CELL CONFLICTS" not in capsys.readouterr().out                    # nothing judged, nothing asked
    cfg = data / "MWSE" / "config"
    payload = json.loads((cfg / "mwfloatfix_data.json").read_text())
    assert payload["cells"]["#0,0"] == [{"id": "bucket", "pos": [110, 100, 108], "from": "Squat.esp",
                                         "why": f"dock deleted by {FIXES.lower()}"}]
    assert payload["sources"] == {FIXES: {"size": os.path.getsize(data / FIXES),
                                          "fnv1a": fnv1a_file(str(data / FIXES))}}
    assert (cfg / m.COLLIDE_DATA).exists() and (cfg / m.STRANDED_DATA).exists()


def _main_steps():
    """[(line, text)] of every call and assignment in mwdialog_check._main, read from the module's own file and
    parsed - not inspect.getsource, which goes through linecache and the code object's line number and returns
    other text when the file or the module set changed since the import (MWManager swaps module copies per test
    folder, and a sync can rewrite the file)."""
    import ast
    with open(m.__file__, "rb") as f:
        tree = ast.parse(f.read().decode("utf-8-sig"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_main")
    steps = []
    for node in ast.walk(fn):
        if isinstance(node, (ast.Call, ast.Assign)):
            steps.append((node.lineno, ast.unparse(node)))
    return [text for _line, text in sorted(steps, key=lambda s: s[0])]


def test_fix_refreshes_the_suite_data_from_the_load_order_file_last():
    """--fix ends with run_cell_conflicts(aux_only=True) on resolve()'s order (generated\\mwdialog_load_order.txt,
    the order --play gives the game), after the sound patch and the Multipatch."""
    steps = _main_steps()

    def first(text):
        return next(i for i, t in enumerate(steps) if t.startswith(text))

    at = first("run_cell_conflicts(args, final_plugins, aux_only=True)")
    assert first("run_multipatch(args, plugins, world)") < at
    assert first("mwdialog_soundfix.run_soundfix(args, sf_plugins") < at
    assert any(i < at and t in ("final_plugins, _b, _d = resolve(args, Report())",
                                "(final_plugins, _b, _d) = resolve(args, Report())")
               for i, t in enumerate(steps))


SCRIPT = r"""
local handlers, clock, logged = {}, 0, {}
os.clock = function() return clock end
local types = { miscItem = 1, book = 2, ingredient = 3, alchemy = 4, weapon = 5, ammunition = 6, armor = 7,
                clothing = 8, apparatus = 9, lockpick = 10, probe = 11, repairItem = 12, light = 13, npc = 14, creature = 15 }
tes3 = { objectType = types, scanCode = { delete = 211 }, event = setmetatable({}, { __index = function(_, k) return k end }),
         getActiveCells = function() return {} end }
tes3vector3 = { new = function(x, y, z) return { x = x, y = y, z = z } end }
event = { register = function(name, fn) handlers[name] = fn end }
lfs = { attributes = function(p) if p == "Data Files\\Cell Fixes.esp" then return { size = SIZE_NOW, modification = 7 } end end,
        mkdir = function() end }
mwse = { log = function(fmt, ...) logged[#logged + 1] = string.format(fmt, ...) end,
         loadConfig = function(name, defaults)
    if name == "mwfloatfix" then defaults.enabled = true; defaults.log = false; return defaults end
    if name == "mwfloatfix_data" then return { sources = { ["Cell Fixes.esp"] = { size = 100, mtime = 7 } },
        cells = { ["balmora, inn"] = { { id = "Misc_Bottle", pos = { 110, 95, 40 } } } } } end
    return defaults
end }
dofile([[MOD]])
local cell = { isInterior = true, id = "Balmora, Inn" }
local function item(x, y, z)
  local p = { x = x, y = y, z = z }
  return { object = { id = "Misc_Bottle", objectType = 1 }, cell = cell, position = p, startingPosition = p,
           sceneNode = {}, tempData = {}, sourceMod = "Morrowind.esm" }
end
local other = item(500, 500, 40)
handlers.referenceActivated({ reference = other })
for i = 1, 6 do                          -- no bounding box in this stub: tried again a few times, then given up on
  clock = clock + 10
  handlers.simulate()
end
print((other.tempData.mwfloatfixChecked and "checked" or "skipped") .. " " .. #logged)
"""


@pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")
@pytest.mark.parametrize("size_now, expect", [(100, "skipped 0"), (101, "checked 1")])
def test_mwfloatfix_checks_every_item_once_a_patch_changed_after_the_list(size_now, expect):
    script = SCRIPT.replace("[[MOD]]", "[[" + MOD + "]]").replace("SIZE_NOW", str(size_now))
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip().endswith(expect), out.stderr + out.stdout
