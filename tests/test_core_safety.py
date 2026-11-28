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


def test_a_failed_record_write_keeps_the_previous_added_masters(tmp_path, monkeypatch):
    S = _load("mwdialog_state")
    (tmp_path / "Data Files").mkdir()
    S.write_added_masters(str(tmp_path), {"A.esp": {"Old.esm": {}}})
    before = (tmp_path / S.ADDED_MASTERS_RECORD).read_text(encoding="utf-8")

    def crash(obj, f, **kw):
        f.write('{"half')
        raise RuntimeError("crash mid-write")
    monkeypatch.setattr(S.json, "dump", crash)
    with pytest.raises(RuntimeError):
        S.write_added_masters(str(tmp_path), {"B.esp": {"New.esm": {}}})
    assert (tmp_path / S.ADDED_MASTERS_RECORD).read_text(encoding="utf-8") == before


def test_a_second_process_cannot_take_the_run_lock(tmp_path):
    import shutil
    import subprocess
    import sys
    # a copy, so the lock file is not the one this test process may already hold from other tests
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    shutil.copy(os.path.join(root, "mwdialog_paths.py"), tmp_path)
    shutil.copy(os.path.join(root, "mwdialog_version.py"), tmp_path)
    tools = str(tmp_path)
    hold = ("import sys, time, mwdialog_paths as MP; print(MP.acquire_run_lock(), flush=True); "
            "sys.stdin.read()")
    holder = subprocess.Popen([sys.executable, "-c", hold], cwd=tools, stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "True"
        second = subprocess.run([sys.executable, "-c", "import mwdialog_paths as MP; "
                                 "print(MP.acquire_run_lock(), MP.acquire_run_lock())"],
                                cwd=tools, capture_output=True, text=True)
        assert second.stdout.strip() == "False False"
    finally:
        holder.communicate("")
    again = subprocess.run([sys.executable, "-c", "import mwdialog_paths as MP; "
                            "print(MP.acquire_run_lock(), MP.acquire_run_lock())"],
                           cwd=tools, capture_output=True, text=True)
    assert again.stdout.strip() == "True True"                      # free after exit; reentrant in-process


def test_an_empty_load_order_falls_back_to_its_backup(tmp_path):
    data = tmp_path / "Data Files"
    data.mkdir()
    path = tmp_path / LO.LOAD_ORDER_FILE
    path.write_text("")                                          # cut short by a crash
    open(LO.bak_home(str(path)) + ".bak", "w").write("; header\nMorrowind.esm\nTribunal.esm\n")
    assert LO.read_load_order(types.SimpleNamespace(data_dir=str(data), ini=None)) == ["Morrowind.esm", "Tribunal.esm"]
    assert "Tribunal.esm" in path.read_text()                    # restored


def test_dry_run_uses_load_order_backup_without_restoring_it(tmp_path):
    data = tmp_path / "Data Files"
    data.mkdir()
    path = tmp_path / LO.LOAD_ORDER_FILE
    path.write_text("")
    backup = LO.bak_home(str(path)) + ".bak"
    with open(backup, "w") as f:
        f.write("; header\nMorrowind.esm\n")
    args = types.SimpleNamespace(data_dir=str(data), ini=None, dry_run=True)
    assert LO.read_load_order(args) == ["Morrowind.esm"]
    assert path.read_text() == ""


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


def test_a_move_is_journaled_before_it_is_made_and_undo_copes_when_it_never_happened(tmp_path, monkeypatch):
    staging = tmp_path / "staging"
    (staging / "Mod").mkdir(parents=True)
    src, dst = staging / "Mod" / "readme.txt", staging / "Mod" / "Docs" / "readme.txt"
    src.write_text("r")
    monkeypatch.setattr(vt, "JOURNAL", str(tmp_path / "journal.jsonl"))
    seen = []

    def crash(a, b):
        seen.append(open(vt.JOURNAL).read())                      # what is on disk when the move is made
        raise OSError("the move fails")
    monkeypatch.setattr(vt.os, "rename", crash)
    failed = vt.apply([(str(src), str(dst), "docs")], str(staging))
    assert failed and '"dst"' in seen[0]                          # journaled first
    monkeypatch.undo()
    monkeypatch.setattr(vt, "JOURNAL", str(tmp_path / "journal.jsonl"))
    assert vt.undo() == 0 and src.read_text() == "r"


def test_a_dry_run_reads_morrowind_ini_without_creating_the_load_order(tmp_path):
    data = tmp_path / "Data Files"
    data.mkdir()
    (tmp_path / "Morrowind.ini").write_text("[Game Files]\nGameFile0=Morrowind.esm\n")
    args = types.SimpleNamespace(data_dir=str(data), ini=None, dry_run=True)
    assert LO.read_load_order(args) == ["Morrowind.esm"]
    assert not (tmp_path / LO.LOAD_ORDER_FILE).exists()


def test_dry_run_does_not_rebuild_lost_doubled_objects(tmp_path, monkeypatch):
    data = tmp_path / "Data Files"
    data.mkdir()
    monkeypatch.setattr(m, "release_lost_doubles", lambda _args: pytest.fail("dry run rebuilt Cell Fixes"))
    monkeypatch.setattr(m, "run_header", lambda _args: 0)
    assert m.main([str(data), "--header", "A.esp", "--dry-run", "--no-vortex"]) == 0


def test_full_does_not_restore_losers_before_unmerging(tmp_path, monkeypatch):
    data = tmp_path / "Data Files"
    data.mkdir()
    monkeypatch.setattr(m, "release_lost_winners", lambda _args: pytest.fail("restored before unmerge"))
    monkeypatch.setattr(m, "run_full", lambda _args: 0)
    assert m.main([str(data), "--full", "--no-vortex"]) == 0


@pytest.mark.parametrize("rc,expected_calls", [(0, 1), (1, 1), (2, 0)])
def test_requested_play_does_not_launch_after_a_failed_build(monkeypatch, capsys, rc, expected_calls):
    calls = []
    monkeypatch.setattr(m, "PLAY_REQUEST", [object()])
    monkeypatch.setattr(m, "launch_game", lambda args: calls.append(args) or 0)
    assert m.finish_requested_play(rc) == rc
    assert len(calls) == expected_calls
    if rc == 2:
        assert "not starting" in capsys.readouterr().err


def test_malformed_conflict_answers_are_dropped_not_crashed_on(tmp_path):
    ST = _load("mwdialog_state")
    (tmp_path / ST.CONFLICT_ANSWERS_FILE).write_text(json.dumps(
        {"answers": {"a.esp|b.esp": "oops", "c.esp|d.esp": {"do": "skip"}, "e.esp|f.esp": None}}))
    assert ST.read_conflict_answers(str(tmp_path)) == {"c.esp|d.esp": {"do": "skip"}}
    (tmp_path / ST.CONFLICT_ANSWERS_FILE).write_text(json.dumps({"answers": ["not", "a", "mapping"]}))
    assert ST.read_conflict_answers(str(tmp_path)) == {}


def test_master_check_facts_are_kept_between_runs_and_dropped_when_a_plugin_changes(tmp_path, monkeypatch):
    MC = _load("mwdialog_mastercheck")
    plugin = tmp_path / "A.esp"
    plugin.write_bytes(b"x")
    real = {"defs": {"a"}, "refs": {"b"}, "dials": set(), "links": [("t", "1")]}
    calls = []
    monkeypatch.setattr(MC, "plugin_facts", lambda data: calls.append(data) or real)
    MC._load_facts(str(tmp_path))
    assert MC.cached_plugin_facts(str(plugin), b"x") == real
    MC._save_facts(str(tmp_path))
    MC._load_facts(str(tmp_path))
    assert MC.cached_plugin_facts(str(plugin), b"x") == real and len(calls) == 1    # from the file, not parsed
    MC._save_facts(str(tmp_path))
    os.utime(plugin, ns=(1, 1))                                                   # the plugin changed
    MC._load_facts(str(tmp_path))
    MC.cached_plugin_facts(str(plugin), b"x")
    MC._save_facts(str(tmp_path))
    assert len(calls) == 2
    saved = json.loads((tmp_path / MC.FACTS_FILE).read_text())
    assert len(saved["facts"]) == 1                                               # the old entry is gone
