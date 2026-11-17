"""Data-safety fixes: atomic text writes, a damaged load order falls back to its backup, a BOM before the first ini
section, --undo stops at the staging folder, an unused asset is never deleted without a copy, first_sub bounds."""
import json
import os
import struct
import types

import pytest

from conftest import _load, ah, m, vt

T = _load("mwdialog_tes3")
LO = _load("mwdialog_loadorder")


def test_atomic_open_leaves_the_old_file_when_the_write_fails(tmp_path):
    p = tmp_path / "rules.txt"
    p.write_text("old rules\n")
    with pytest.raises(RuntimeError):
        with T.atomic_open(str(p)) as f:
            f.write("half of the new")
            raise RuntimeError("crash mid-write")
    assert p.read_text() == "old rules\n" and sorted(os.listdir(tmp_path)) == ["rules.txt"]
    with T.atomic_open(str(p)) as f:
        f.write("new rules\n")
    assert p.read_text() == "new rules\n"


def test_an_empty_load_order_falls_back_to_its_backup(tmp_path):
    data = tmp_path / "Data Files"
    data.mkdir()
    path = tmp_path / LO.LOAD_ORDER_FILE
    path.write_text("")                                          # cut short by a crash
    open(LO.bak_home(str(path)) + ".bak", "w").write("; header\nMorrowind.esm\nTribunal.esm\n")
    assert LO.read_load_order(types.SimpleNamespace(data_dir=str(data), ini=None)) == ["Morrowind.esm", "Tribunal.esm"]
    assert "Tribunal.esm" in path.read_text()                    # restored


def test_a_bom_before_the_first_section_is_ignored(tmp_path):
    ini = tmp_path / "Morrowind.ini"
    ini.write_bytes(b"\xef\xbb\xbf[Game Files]\r\nGameFile0=Morrowind.esm\r\n")
    assert LO.read_ini_sections(str(ini))["game files"] == [("GameFile0", "Morrowind.esm")]


def test_undo_never_removes_the_staging_folder(tmp_path, monkeypatch):
    staging = tmp_path / "staging"
    (staging / "Other").mkdir(parents=True)
    moved = staging / "Mod" / "Docs" / "a.txt"
    moved.parent.mkdir(parents=True)
    moved.write_text("x")
    journal = tmp_path / "journal.jsonl"
    journal.write_text(json.dumps({"run": "now", "staging": str(staging)}) + "\n"
                       + json.dumps({"src": str(staging / "Other" / "a.txt"), "dst": str(moved)}) + "\n")
    monkeypatch.setattr(vt, "JOURNAL", str(journal))
    os.rmdir(staging / "Other")                                   # the undo makes it again; then Mod is empty
    assert vt.undo() == 0
    assert (staging / "Other" / "a.txt").exists() and not (staging / "Mod").exists() and staging.is_dir()


def test_an_unused_asset_is_kept_in_off_when_the_staging_copy_is_missing(tmp_path, monkeypatch):
    data, mod = tmp_path / "Data Files", tmp_path / "staging" / "Mod"
    (data / "Meshes").mkdir(parents=True)
    mod.mkdir(parents=True)
    full = data / "Meshes" / "x.nif"
    full.write_bytes(b"only copy")
    monkeypatch.setattr(m, "asset_owner_folder", lambda d, rel: (str(mod), "Mod.esp"))
    ah.apply([("unused", str(full), "Meshes\\x.nif", "unused")], str(data), str(tmp_path), m, [])
    assert not full.exists()
    assert [p.read_bytes() for p in mod.rglob("x.nif")] == [b"only copy"]


def test_first_sub_refuses_a_subrecord_running_past_its_record():
    body = b"NAME" + struct.pack("<I", 50) + b"short"
    with pytest.raises(T.FormatError):
        T.first_sub(body, b"NAME")
