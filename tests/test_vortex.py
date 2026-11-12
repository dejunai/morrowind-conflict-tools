"""Regression tests for vortex_tidy.py (I7 normal maps, I8, M12)."""
import json

import pytest
import os
import struct
import sys

from conftest import ah, m, vt


def _mod(tmp_path, files):
    mod = tmp_path / "staging" / "Signs-1234-1-0"
    (mod / "textures").mkdir(parents=True)
    for f in files:
        (mod / "textures" / f).write_bytes(b"DDS ")
    (mod / "Signs.esp").write_bytes(b"TES3")
    return mod


def _moved(mod):
    return sorted(os.path.basename(s) for s, d, _w in vt.plan_mod(str(mod)) if d and "normal maps" in d)


# ---------------------------------------------------------------- I7: normal maps (all moved; warn without a diffuse)
def _plan(mod):
    vt.NOTES.clear()
    vt.ORPHAN_NORMALS.clear()
    vt.NORMAL_PACKS.clear()
    vt._TEX_INDEX.clear()
    return [(os.path.basename(s), d, w) for s, d, w in vt.plan_mod(str(mod)) if d and "normal maps" in d]


def test_I7_all_normal_maps_move_without_the_asset_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(vt, "HERE", str(tmp_path))                 # no mwdialog_asset_cache.json here
    mod = _mod(tmp_path, ["tx_sign_n.dds", "tx_sign.dds", "tx_wall_nm.tga", "tx_wall.dds", "tx_a_normal.bmp",
                          "tx_a.dds", "tx_b_nrm.dds", "tx_b.tga", "tx_plain.dds"])
    assert sorted(n for n, _d, _w in _plan(mod)) == ["tx_a_normal.bmp", "tx_b_nrm.dds", "tx_sign_n.dds",
                                                    "tx_wall_nm.tga"]
    assert vt.NOTES == []


def test_I7_model_named_normal_map_moves_too(tmp_path, monkeypatch):
    (tmp_path / "mwdialog_asset_cache.json").write_text(json.dumps({"m.nif": {"r": {"tex": ["tx_wall_nm"]}}}))
    monkeypatch.setattr(vt, "HERE", str(tmp_path))
    mod = _mod(tmp_path, ["tx_wall_nm.dds", "tx_wall.dds"])
    plan = _plan(mod)
    assert [n for n, _d, _w in plan] == ["tx_wall_nm.dds"]
    assert os.path.join("Off", "normal maps", "Signs", "textures", "tx_wall_nm.dds") in plan[0][1]


def test_I7_orphan_normal_map_is_left_in_place(tmp_path, monkeypatch):
    monkeypatch.setattr(vt, "HERE", str(tmp_path))                 # no Data Files: staging only
    mod = _mod(tmp_path, ["tx_sign_n.dds", "tx_sign_s.dds", "tx_wall_n.dds", "tx_wall.dds"])
    plan = _plan(mod)
    assert [n for n, _d, _w in plan] == ["tx_wall_n.dds"]           # the one with a diffuse still moves
    assert vt.ORPHAN_NORMALS == [("Signs-1234-1-0", os.path.join("textures", "tx_sign_n.dds"))]
    assert vt.NOTES == []


def test_I7_diffuse_in_another_mod_or_a_bsa_counts(tmp_path, monkeypatch):
    from test_cache import _bsa
    monkeypatch.setattr(vt, "HERE", str(tmp_path))
    mod = _mod(tmp_path, ["tx_rock_n.dds", "tx_bsa_nm.dds", "tx_none_n.dds"])
    other = tmp_path / "staging" / "Rocks-55-1-0" / "Textures"
    other.mkdir(parents=True)
    (other / "tx_rock.dds").write_bytes(b"DDS ")
    (tmp_path / "Data Files").mkdir()
    (tmp_path / "Data Files" / "Morrowind.bsa").write_bytes(_bsa([("textures\\tx_bsa.dds", b"DDS ")]))
    monkeypatch.setattr(vt, "_tool_modules", lambda: (m, ah))
    assert sorted(n for n, _d, _w in _plan(mod)) == ["tx_bsa_nm.dds", "tx_rock_n.dds"]
    assert [os.path.basename(r) for _d, r in vt.ORPHAN_NORMALS] == ["tx_none_n.dds"]


def test_I7_orphan_in_a_normal_maps_pack_still_moves_and_the_pack_is_flagged(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(vt, "HERE", str(tmp_path))
    mod = tmp_path / "staging" / "Better Rocks-77-1-0"
    nm = mod / "Textures" / "Normal Maps"
    nm.mkdir(parents=True)
    (nm / "tx_rock_n.dds").write_bytes(b"DDS ")                    # no diffuse anywhere, but a pack: moves
    (mod / "Textures" / "tx_lone_n.dds").write_bytes(b"DDS ")       # no diffuse, not in the pack path: stays
    monkeypatch.setattr(vt, "PLAN", str(tmp_path / "plan.txt"))
    monkeypatch.setattr(vt, "BLACKLIST_FILE", str(tmp_path / "bl.txt"))
    vt.NOTES.clear()

    class A:
        pass
    a = A()
    a.staging, a.only, a.skip, a.apply = str(mod.parent), None, None, False
    moves = vt.run_plan(a)
    out = capsys.readouterr().out
    moved = [os.path.basename(s) for s, d, _w in moves if d and "normal maps" in d.lower()]
    assert moved == ["tx_rock_n.dds"]
    assert vt.NO_DIFFUSE_WARNING in next(w for s, _d, w in moves if s.endswith("tx_rock_n.dds"))
    assert "Better Rocks-77-1-0: a normal-map add-on pack" in out and "not applicable to classic Morrowind" in out
    assert "left in place (no diffuse texture anywhere)" in open(tmp_path / "plan.txt").read()
    assert vt.ORPHAN_NORMALS == [("Better Rocks-77-1-0", os.path.join("Textures", "tx_lone_n.dds"))]


# ---------------------------------------------------------------- I8: damaged BSA in Data Files
def test_I8_damaged_bsa_does_not_stop_the_asset_check(tmp_path, monkeypatch, capsys):
    game = tmp_path / "game"
    (game / "Data Files").mkdir(parents=True)
    (game / "Data Files" / "bad.bsa").write_bytes(struct.pack("<III", 0x100, 16, 100000) + b"\0" * 16)
    staging = tmp_path / "staging"
    staging.mkdir()
    monkeypatch.setattr(vt, "__file__", str(game / "vortex_tidy.py"))
    monkeypatch.setattr(vt, "_tool_modules", lambda: (m, ah))
    monkeypatch.setattr(vt, "BLACKLIST_FILE", str(tmp_path / "bl.txt"))

    class A:
        pass
    a = A()
    a.staging, a.only, a.skip, a.apply = str(staging), None, None, False
    vt.assets_check(a)
    assert "ASSET CHECK" in capsys.readouterr().out


# ---------------------------------------------------------------- M12
def test_M12_deleted_folder_follows_staging(tmp_path):
    st = tmp_path / "Vortex Mods" / "morrowind"
    assert vt.deleted_dir(str(st)) == str(tmp_path / "Vortex Mods" / "morrowind - deleted by vortex_tidy")


def test_M12_plan_run_creates_no_blacklist_file(tmp_path, monkeypatch):
    bl = tmp_path / "vortex_tidy_blacklist.txt"
    monkeypatch.setattr(vt, "BLACKLIST_FILE", str(bl))
    vt.blacklist(create=False)
    assert not bl.exists()
    vt.blacklist()
    assert bl.exists()


def test_M12_undo_keeps_what_it_could_not_put_back(tmp_path, monkeypatch):
    j = tmp_path / "journal.jsonl"
    monkeypatch.setattr(vt, "JOURNAL", str(j))
    a_src, a_dst = tmp_path / "a.txt", tmp_path / "Docs" / "a.txt"
    a_dst.parent.mkdir()
    a_dst.write_text("a")
    gone_src, gone_dst = tmp_path / "b.txt", tmp_path / "Docs" / "b.txt"     # gone_dst doesn't exist
    with open(j, "w") as f:
        f.write(json.dumps({"run": "2026-11-11 06:00:00", "staging": str(tmp_path)}) + "\n")
        f.write(json.dumps({"src": str(a_src), "dst": str(a_dst)}) + "\n")
        f.write(json.dumps({"src": str(gone_src), "dst": str(gone_dst)}) + "\n")
    vt.undo()
    assert a_src.read_text() == "a"
    left = [json.loads(x) for x in j.read_text().splitlines()]
    assert any(op.get("dst") == str(gone_dst) for op in left)


def test_M12_tool_modules_reuses_loaded_modules(monkeypatch):
    monkeypatch.setitem(sys.modules, "mwdialog_check", m)
    monkeypatch.setitem(sys.modules, "mwdialog_assets", ah)
    a, b = vt._tool_modules()
    assert a is m and b is ah


@pytest.mark.parametrize("folder,pack", [
    ("Normal Maps", True), ("normal_map", True), ("Normal-Map", True), ("NormalMap", True), ("normal.maps", True),
    ("NORMALMAPS", True), ("normal  maps", True), ("abnormalmap", False), ("normal mapping", False),
    ("Normals", False), ("map normal", False)])
def test_I7_normal_map_pack_path_variants(tmp_path, monkeypatch, folder, pack):
    monkeypatch.setattr(vt, "HERE", str(tmp_path))
    mod = tmp_path / "staging" / "Rocks-77-1-0"
    d = mod / "Textures" / folder
    d.mkdir(parents=True)
    (d / "tx_rock_n.dds").write_bytes(b"DDS ")                      # an orphan: moves only from a pack path
    moved = [n for n, _d, _w in _plan(mod)]
    assert moved == (["tx_rock_n.dds"] if pack else [])
    assert bool(vt.NORMAL_PACKS) == pack


def test_I7_normal_map_pack_named_by_the_mod_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(vt, "HERE", str(tmp_path))
    mod = tmp_path / "staging" / "Vanilla NormalMap Pack-88-1-0"
    (mod / "Textures").mkdir(parents=True)
    (mod / "Textures" / "tx_rock_n.dds").write_bytes(b"DDS ")
    assert [n for n, _d, _w in _plan(mod)] == ["tx_rock_n.dds"]
