"""Regression tests for vortex_tidy.py (I7 normal maps, I8, M12)."""
import json
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


def test_I7_no_diffuse_sibling_moves_with_warning(tmp_path):
    mod = _mod(tmp_path, ["tx_sign_n.dds", "tx_sign_s.dds"])        # no tx_sign.* beside it
    plan = _plan(mod)
    assert [n for n, _d, _w in plan] == ["tx_sign_n.dds"]
    assert vt.NO_DIFFUSE_WARNING in plan[0][2]
    assert len(vt.NOTES) == 1 and "tx_sign_n.dds" in vt.NOTES[0] and vt.NO_DIFFUSE_WARNING in vt.NOTES[0]


def test_I7_diffuse_sibling_means_no_warning(tmp_path):
    mod = _mod(tmp_path, ["tx_wall_n.dds", "tx_wall.tga"])
    plan = _plan(mod)
    assert [n for n, _d, _w in plan] == ["tx_wall_n.dds"]
    assert vt.NO_DIFFUSE_WARNING not in plan[0][2] and vt.NOTES == []


def test_I7_warning_shown_in_plan_and_apply_output(tmp_path, monkeypatch, capsys):
    mod = _mod(tmp_path, ["tx_sign_n.dds"])
    monkeypatch.setattr(vt, "PLAN", str(tmp_path / "plan.txt"))
    monkeypatch.setattr(vt, "JOURNAL", str(tmp_path / "journal.jsonl"))
    monkeypatch.setattr(vt, "BLACKLIST_FILE", str(tmp_path / "bl.txt"))
    vt.NOTES.clear()

    class A:
        pass
    a = A()
    a.staging, a.only, a.skip, a.apply = str(mod.parent), None, None, True
    moves = vt.run_plan(a)
    plan_out = capsys.readouterr().out
    assert vt.NO_DIFFUSE_WARNING in plan_out and "tx_sign_n.dds" in plan_out
    vt.apply(moves, str(mod.parent))
    apply_out = capsys.readouterr().out
    assert "WARNING" in apply_out and vt.NO_DIFFUSE_WARNING in apply_out
    assert (mod / "Off" / "normal maps" / "Signs" / "textures" / "tx_sign_n.dds").exists()


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
    vt.run_assets(a, False)
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
