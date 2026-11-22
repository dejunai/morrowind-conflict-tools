"""Regressions of the 2026-11-22 audit: no repair loses an updated file or writes over one it didn't read, and the
suite's Lua fixes. Everything runs on invented files in a temp folder."""
import argparse
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import SRC, ah, m, misc, plugin, rec, sub, z

import mwdialog_backup as B
import mwdialog_generated as G
import mwdialog_luafix as L
import mwdialog_masters as MA
import mwdialog_paths as MP
import mwdialog_restore as R


def refs(*names):
    return rec("CELL", sub("NAME", z("Town")) + sub("DATA", struct.pack("<Iif", 1, 0, 0.0)) + b"".join(
        sub("FRMR", struct.pack("<I", i)) + sub("NAME", z(n)) + sub("DATA", struct.pack("<6f", *[0] * 6))
        for i, n in enumerate(names, 1)))


def test_luafix_direct_run_refuses_a_held_game_lock(monkeypatch, capsys):
    monkeypatch.setattr(MP, "acquire_game_lock", lambda _game: False)
    assert L.main(["--undo"]) == 1
    assert MP.RUN_LOCKED_MESSAGE in capsys.readouterr().err


@pytest.fixture
def df(tmp_path):
    d = tmp_path / "Morrowind" / "Data Files"
    d.mkdir(parents=True)
    (d.parent / "Morrowind.ini").write_text("[Game Files]\n")
    return d


def kept(folder, data):
    return [p for p in Path(folder).rglob("*") if p.is_file() and p.read_bytes() == data]


def fix(df, names, *extra):
    return m.main([str(df), "--plugins", *names, "--no-vortex", "--no-archive-lookup", "--no-interactive",
                   "--fix", "--yes", "--fix-log", str(df.parent / "fixes.log"), *extra])


def test_restore_all_keeps_the_mod_update_it_replaces(df):
    p = df / "Mod.esp"
    plugin(p, [], [misc("v1")])
    shutil.copy2(p, B.backup_path(str(p)))
    update = plugin(p, [], [misc("version_two")])
    R.restore_all(str(df), True, str(df.parent / "log"))
    assert b"v1" in p.read_bytes() and kept(df.parent, update)


def test_clean_up_during_a_purge_keeps_every_backup(df):
    p = df / "Mod.esp"
    original = plugin(p, [], [misc("original")])
    shutil.copy2(p, B.backup_path(str(p)))
    p.unlink()
    R.run_clean_up(argparse.Namespace(data_dir=str(df), dry_run=False, yes=True, fix_log=str(df.parent / "log")))
    assert kept(df.parent, original)


def test_clean_up_keeps_the_original_and_the_newest(df):
    p = df / "Mod.esp"
    made = []
    for i in range(4):
        made.append(plugin(p, [], [misc(f"v{i}")]))
        shutil.copy2(p, B.backup_path(str(p)))
    R.run_clean_up(argparse.Namespace(data_dir=str(df), dry_run=False, yes=True, fix_log=str(df.parent / "log")))
    assert [Path(b).read_bytes() for b in B.backup_candidates(str(p))] == [made[0], made[3]]


def test_an_updated_asset_is_kept_and_our_own_repair_is_not(tmp_path):
    mod = tmp_path / "staging" / "Some Mod"
    (mod / "Sound").mkdir(parents=True)
    f = mod / "Sound" / "a.mp3"
    job = [("snd", str(f), os.path.join("Sound", "a.mp3"), {"strip": 4})]
    f.write_bytes(b"AAAABBBBold sound")
    ah.apply_folder(str(mod), job, m, str(tmp_path), "Some Mod")
    ah.apply_folder(str(mod), job, m, str(tmp_path), "Some Mod")
    assert len(list((mod / "Off").rglob("*.mp3"))) == 1
    f.write_bytes(b"TAG2the updated sound")
    ah.apply_folder(str(mod), job, m, str(tmp_path), "Some Mod")
    assert kept(mod, b"TAG2the updated sound")


def test_a_backup_that_cannot_be_made_stops_the_write(tmp_path, monkeypatch):
    first, now = tmp_path / "kept.wav", tmp_path / "a.wav"
    first.write_bytes(b"first")
    now.write_bytes(b"updated")

    def full_disk(*_a, **_k):
        raise OSError("no space")

    monkeypatch.setattr(G.shutil, "copy2", full_disk)
    with pytest.raises(OSError):
        G.keep_new_original(str(first), str(now))


def test_a_rename_keeps_an_updated_file(tmp_path):
    root = tmp_path / "Mod"
    old, new = os.path.join("Textures", "café.dds"), os.path.join("Textures", "cafe.dds")
    first = Path(m.off_dest(str(root), "names", None, old))
    for p, data in ((root / old, b"update"), (root / new, b"fixed"), (first, b"first original")):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    ah.rename_ascii(str(root), str(root / old), old, new, lambda _t: None)
    assert kept(root, b"update") and first.read_bytes() == b"first original"


def test_a_rename_keeps_an_updated_plugin_and_one_copy_for_several_renames(tmp_path):
    root = tmp_path / "Mod"
    (root / "Meshes").mkdir(parents=True)
    names = [f"café{i}.nif" for i in range(3)]
    for n in names:
        (root / "Meshes" / n).write_bytes(b"nif")
    stats = [rec("STAT", sub("NAME", z(f"s{i}")) + sub("MODL", z(n))) for i, n in enumerate(names)]
    first = Path(m.off_dest(str(root), "names", "Mod.esp", "Mod.esp"))
    first.parent.mkdir(parents=True)
    plugin(first, [], stats)
    update = plugin(root / "Mod.esp", [], stats + [misc("only_in_update")])
    for n in names:
        old = os.path.join("Meshes", n)
        ah.rename_ascii(str(root), str(root / old), old, old.replace("é", "e"), lambda _t: None)
    assert kept(root, update) and len(list((root / "Off").rglob("*.esp"))) == 2


def test_restore_unused_never_replaces_a_newer_file(df, tmp_path):
    mod = tmp_path / "staging" / "Mod"
    rel = os.path.join("Textures", "x.dds")
    moved = mod / "Off" / "unused" / "Mod" / rel
    for p, data in ((moved, b"old"), (mod / rel, b"newer")):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    (df.parent / ah.UNUSED_RECORD).write_text(f"2026-01-01 00:00:00\t{rel}\t{moved}\tnothing names it\n")
    ah.restore_unused(str(df.parent), str(df))
    assert (mod / rel).read_bytes() == b"newer" and moved.read_bytes() == b"old"


def test_an_item_fix_backs_up_when_the_first_write_failed(df, monkeypatch):
    plugin(df / "Base.esm", [], [misc("gold_001")])
    npc = rec("NPC_", sub("NAME", z("guy")) + sub("NPCO", struct.pack("<i", 1) + b"gone_item".ljust(32, b"\0")))
    original = plugin(df / "Mod.esp", [("Base.esm", (df / "Base.esm").stat().st_size)], [npc, refs("gone_thing")])
    real = m.apply_plan

    def fails(path, *a, **kw):
        if kw.get("collect") is None:
            raise PermissionError("in use for a moment")
        return real(path, *a, **kw)

    monkeypatch.setattr(m, "apply_plan", fails)
    fix(df, ["Base.esm", "Mod.esp"])
    assert (df / "Mod.esp").read_bytes() != original and kept(df.parent, original)


def test_a_plan_is_not_applied_to_a_plugin_replaced_since_the_scan(df):
    p = df / "Mod.esp"
    data = plugin(p, [], [refs("wrong_id"), misc("tail")])
    off = next(o for o, t, _f, _b in m.iter_records(data) if t == "CELL")
    w = m.World(m.Report())
    w.file_sizes = {}
    w.load_plugin(str(p), "Mod.esp")
    newer = plugin(p, [], [refs("right_id"), misc("tail")])
    with pytest.raises(OSError):
        m.apply_plan(str(p), "Mod.esp", {off: [(("drop_ref", 1), "removed", "no such object")]}, w, [])
    assert p.read_bytes() == newer


def test_clean_does_not_write_an_old_plugin_over_a_new_one(df, monkeypatch):
    plugin(df / "Base.esm", [], [misc("dup")])
    p = df / "Mod.esp"
    masters = [("Base.esm", (df / "Base.esm").stat().st_size)]
    plugin(p, masters, [misc("dup"), misc("old_version")])
    real = m.write_inplace

    def deploy_first(path, out, **kw):
        plugin(p, masters, [misc("new_version")])
        return real(path, out, **kw)

    monkeypatch.setattr(m, "write_inplace", deploy_first)
    m.run_clean(argparse.Namespace(dry_run=False, yes=True, fix_log=str(df.parent / "log")),
                [("Base.esm", str(df / "Base.esm")), ("Mod.esp", str(p))], None)
    assert b"new_version" in p.read_bytes() and b"old_version" not in p.read_bytes()


def test_write_inplace_refuses_bytes_it_was_not_made_from(df):
    p = df / "Mod.esp"
    read = plugin(p, [], [misc("read")])
    newer = plugin(p, [], [misc("deployed_since")])
    out = [read[o:o + 16 + len(b)] for o, _t, _f, b in m.iter_records(read)]
    with pytest.raises(OSError):
        MA.write_inplace(str(p), out, read_as=m.content_id(read))
    assert p.read_bytes() == newer


def test_restore_textures_keeps_the_lines_it_could_not_restore(df):
    record = df.parent / G.REDUCED_RECORD
    record.write_text(f"Textures\\x.dds\tlink\t{df.parent / 'offline' / 'x.dds'}\n")
    G.run_restore_textures(argparse.Namespace(data_dir=str(df), dry_run=False))
    assert "x.dds" in record.read_text()


def test_both_typos_of_one_response_are_fixed(df):
    info = rec("INFO", sub("INAM", z("1")) + sub("PNAM", z("")) + sub("NNAM", z(""))
               + sub("DATA", struct.pack("<B3xibbbb", 0, 10, -1, -1, -1, 0))
               + sub("NAME", b"He asked me to find his fried, Sky-Crest. He is true friend of mine."))
    plugin(df / "AFFresh.esm", [], [rec("DIAL", sub("NAME", z("T")) + sub("DATA", b"\0")), info])
    fix(df, ["AFFresh.esm"], "--no-follow-fix")
    data = (df / m.PATCH_NAME).read_bytes()
    assert b"his friend," in data and b"is a true friend" in data


def test_a_merge_that_fails_its_check_leaves_no_temp_file(df, monkeypatch):
    plugin(df / "Base.esm", [], [misc("gold_001")])
    masters = [("Base.esm", (df / "Base.esm").stat().st_size)]
    plugin(df / "A.esp", masters, [misc("a")])
    plugin(df / "B.esp", masters, [misc("b")])
    real = m.scan
    out = df / "Merged.esp"

    def scan(args, order, *a, **kw):
        if os.path.exists(str(out) + ".tmp"):
            raise RuntimeError("check failed")
        return real(args, order, *a, **kw)

    monkeypatch.setattr(m, "scan", scan)
    with pytest.raises(RuntimeError):
        m.main([str(df), "--plugins", "Base.esm", "A.esp", "B.esp", "--no-vortex", "--no-archive-lookup",
                "--merge", str(out), str(df / "A.esp"), str(df / "B.esp"), "--merge-all", "--yes",
                "--fix-log", str(df.parent / "log")])
    assert not os.path.exists(str(out) + ".tmp")


def test_a_core_known_bug_is_offered_from_the_cache_too(tmp_path):
    core = tmp_path / "Data Files" / "MWSE" / "core" / "mcm" / "components" / "pages"
    core.mkdir(parents=True)
    f = core / "exclusionspage.lua"
    f.write_text("function X:refresh()\n\t" + L.KNOWN_BUGS[2][3] + "\nend\n")
    for _ in range(2):
        found = L.check_paths([str(f)], dict(L.DEFAULTS), use_cache=True, game_dir=str(tmp_path),
                              data_dir=str(tmp_path / "none"))
        assert next(iter(found.files.values())).get("patch")


# ---------------------------------------------------------------------------------------------------- the lock

def locked_elsewhere(lock_dir, game):
    code = ("import sys, mwdialog_paths as P; P.GAME_LOCK_DIR = sys.argv[1]; "
            "print(P.acquire_game_lock(sys.argv[2]))")
    return subprocess.run([sys.executable, "-B", "-c", code, str(lock_dir), str(game)], cwd=SRC,
                          capture_output=True, text=True).stdout.strip() == "False"


def test_one_game_takes_one_run_and_lets_go(df):
    game = df.parent
    assert MP.acquire_game_lock(str(game)) and MP.acquire_game_lock(str(game))
    assert locked_elsewhere(MP.GAME_LOCK_DIR, game)
    assert not list(game.rglob("*.lock"))               # MWManager's rollback check counts extra files
    MP.release_game_locks()
    assert not locked_elsewhere(MP.GAME_LOCK_DIR, game)


def test_the_game_lock_is_the_one_mwmanager_jobs_take(df):
    import hashlib
    MP.acquire_game_lock(str(df.parent))
    key = os.path.normcase(str(df.parent.resolve()))            # workflow_safety.mutation_lock's naming
    assert (Path(MP.GAME_LOCK_DIR) / (hashlib.sha256(key.encode()).hexdigest() + ".lock")).is_file()


def test_a_run_refuses_a_game_another_one_holds(df):
    code = ("import sys, mwdialog_paths as P; P.GAME_LOCK_DIR = sys.argv[1]; "
            "print(P.acquire_game_lock(sys.argv[2]), flush=True); sys.stdin.read()")
    holder = subprocess.Popen([sys.executable, "-B", "-c", code, MP.GAME_LOCK_DIR, str(df.parent)], cwd=SRC,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "True"
        plugin(df / "A.esp", [], [misc("a")])
        assert fix(df, ["A.esp"]) == 1
    finally:
        holder.communicate("")


def test_a_lock_file_without_a_token_delegates_to_nobody(df, monkeypatch):
    code = ("import sys, mwdialog_paths as P; P.GAME_LOCK_DIR = sys.argv[1]; P.acquire_game_lock(sys.argv[2]); "
            "h = next(iter(P._RUN_LOCKS.values())); h.write(b'{}'); h.flush(); print('held', flush=True); sys.stdin.read()")
    holder = subprocess.Popen([sys.executable, "-B", "-c", code, MP.GAME_LOCK_DIR, str(df.parent)], cwd=SRC,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        monkeypatch.delenv("MWMANAGER_DELEGATED_LOCKS", raising=False)
        assert not MP.acquire_game_lock(str(df.parent))
    finally:
        holder.communicate("")


# -------------------------------------------------------------------------------------------------------- Lua

LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(SRC, "tools", "luajit", "luajit.exe"))
MODS = (Path(SRC) / "Data Files" / "MWSE" / "mods" / "mwsuite").as_posix()
needs_lua = pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")

STUB = r"""
local handlers, saved, timers = {}, {}, {}
local auto = setmetatable({}, { __index = function(_, k) return k end })
event = { register = function(n, f, o) local k = n .. (o and o.filter or ""); handlers[k] = handlers[k] or {}; table.insert(handlers[k], f) end }
local function fire(n, e) e = e or {}; for _, f in ipairs(handlers[n] or {}) do f(e) end return e end
timer = { real = "real", simulate = "simulate", start = function(p) timers[#timers + 1] = p; return { cancel = function() end } end,
          delayOneFrame = function() end, frame = { delayOneFrame = function(f) f() end } }
lfs = { mkdir = function() end, fileexists = function(p) local f = io.open(p, "rb"); if f then f:close(); return true end return false end }
io.open = (function(open) return function(p, mode)
  if mode and mode:find("w") then return { write = function() end, flush = function() end, close = function() end } end
  return open(p, mode) end end)(io.open)
tes3ui = { menuMode = function() return false end, findMenu = function() return {} end, registerID = function(i) return i end }
tes3vector3 = { new = function(x, y, z) return { x = x, y = y, z = z } end }
tes3 = { event = auto, uiEvent = auto, objectType = { npc = "npc", container = "container", reference = "reference" },
         gmst = auto, specialization = { combat = 0, magic = 1, stealth = 2 }, findGMST = function() end,
         onMainMenu = function() return false end, getActiveCells = function() return {} end,
         saveGame = function(p) saved[#saved + 1] = p.file end, mobilePlayer = { health = { current = 10 } },
         dataHandler = {}, messageBox = function() end, runLegacyScript = function() end }
mwse = { log = function() end, loadConfig = function(_, d) d.enabled = true; return d end, overrideScript = function() end }
package.path = "MODS/?.lua;" .. package.path
"""


def lua(tmp_path, body):
    got = subprocess.run([LUAJIT, "-"], input=(STUB + body).replace("MODS", MODS), capture_output=True, text=True,
                         cwd=tmp_path)
    assert got.returncode == 0, got.stderr


@needs_lua
def test_saveguard_writes_every_deferred_save_once(tmp_path):
    lua(tmp_path, r"""
assert(loadfile("MODS/mwsaveguard/main.lua"))()
tes3.player = { object = {}, cell = {} }
fire("save", { filename = "my manual save" }); fire("save", { filename = "autosave" }); fire("save", { filename = "autosave" })
timers[#timers].callback()
assert(table.concat(saved, ",") == "my manual save,autosave", table.concat(saved, ","))
""")


@needs_lua
def test_saveguard_disables_a_clone_and_leaves_a_lookalike(tmp_path):
    lua(tmp_path, r"""
assert(loadfile("MODS/mwsaveguard/main.lua"))()
local same = {}
local function looks() return { name = "N", race = same, head = same, hair = same, class = same } end
tes3.player = { object = looks(), cell = {} }
local hidden, refs = {}, {}
for _, id in ipairs({ "player", "mirror" }) do
  refs[#refs + 1] = { id = id .. "00000001", object = looks(), baseObject = { id = id, objectType = "npc" },
                      position = { x = 0, y = 0, z = 0 }, disable = function() hidden[id] = true end }
end
tes3.getActiveCells = function() return { { editorName = "c", iterateReferences = function() local i = 0
  return function() i = i + 1 return refs[i] end end } } end
fire("cellChanged")
assert(hidden.player and not hidden.mirror)
""")


@needs_lua
@pytest.mark.parametrize("tail,good", [(b"", True), (b"\0\0\0\0", True), (b"CELL\x10", False)])
def test_save_validation_allows_padding_only(tmp_path, tail, good):
    hedr = struct.pack("<fI", 1.3, 32) + b"\0" * 288 + struct.pack("<I", 0)
    (tmp_path / "s.ess").write_bytes(rec("TES3", sub("HEDR", hedr) + sub("GMDT", b"\0" * 124)) + tail)
    lua(tmp_path, f"""
local v = assert(loadfile("MODS/mwsaveguard/validator.lua"))()
assert(v.validateSave("s.ess") == {str(good).lower()})
""")


@needs_lua
def test_teleportguard_reads_past_comments_and_quotes(tmp_path):
    lua(tmp_path, r"""
package.preload["mwteleportguard.config"] = function() return { enabled = true } end
assert(loadfile("MODS/mwteleportguard/main.lua"))()
local ran = ""
tes3.runLegacyScript = function(p) ran = ran .. p.command end
fire("initialized")
local function blocks(cmd) return fire("infoResponse", { command = cmd }).block == true end
assert(not blocks('Journal MyQuest 20\n; Player->PositionCell 1 2 3 0 "Old Test Cell"\n'), "a comment")
assert(not blocks('if ( Random100 > 5 )\nPlayer->PositionCell 1 2 3 0 "Balmora"\nendif'), "conditional")
assert(blocks('MessageBox "Wait if you dare; then go"\nPlayer->PositionCell 1 2 3 90 "Balmora, Guild" ; back'), "real")
assert(ran:find('then go"', 1, true), ran)
""")


@needs_lua
@pytest.mark.parametrize("receipt", [0, 1])
def test_personaleffects_fills_and_empties_once(tmp_path, receipt):
    lua(tmp_path, r"""
package.preload["mwpersonaleffects.config"] = function() return { enabled = true, isPersonalEffectsActive = function() return true end } end
assert(loadfile("MODS/mwpersonaleffects/main.lua"))()
fire("initialized")
local chest = { baseObject = { id = "R0_pe_basecont" }, object = { inventory = {} }, enable = function() end }
local itemData = { condition = 17 }
local ring = { baseObject = { id = "R0_pe_cont_mage" }, position = { x = 0, y = 0, z = 0 },
               object = { inventory = { { object = { id = "ring" }, count = 1, variables = { itemData } } } } }
ring.disable = function() ring.disabled = true end
local cell = { id = "Seyda Neen, Census and Excise Office", iterateReferences = function() local d = false
  return function() if not d then d = true return ring end end end }
tes3.player = { cell = cell, data = {}, object = { class = { id = "Warrior" } } }
tes3.getReference = function(id) if id == "R0_pe_basecont" then return chest end end
tes3.getObject = function(id) if id == "R0_pe_cont_warrior" then return { inventory = { { object = { id = "sword" }, count = 1 } } } end
  return { id = id } end
tes3.unlock, tes3.setOwner, tes3.playSound = function() end, function() end, function() end
tes3.getJournalIndex = function() return 10 end
local got = { R0_pe_inventory_warrior = RECEIPT }
tes3.getItemCount = function(p) return got[p.item] or 0 end
tes3.addItem = function(p)
  local id = type(p.item) == "table" and p.item.id or p.item
  got[id] = (got[id] or 0) + p.count
  if p.reference == chest then chest.object.inventory[#chest.object.inventory + 1] = { object = p.item, count = p.count } end
end
local movedData
tes3.transferInventory = function(p)
  assert(p.from == ring and p.to == chest and p.limitCapacity == false, "wrong inventory transfer")
  local stack = ring.object.inventory[1]
  got[stack.object.id] = (got[stack.object.id] or 0) + stack.count
  movedData = stack.variables[1]
end
for _ = 1, 3 do fire("activate", { target = chest }); chest.object.inventory = {} end
assert((got.sword or 0) == 1 - RECEIPT, "swords: " .. tostring(got.sword))
assert(got.ring == 1, "rings: " .. tostring(got.ring))
assert(movedData == itemData, "stray chest itemData was lost")
""".replace("RECEIPT", str(receipt)))
