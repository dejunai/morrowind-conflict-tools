"""Putting things back never loses the original: --restore-all uses the oldest backup, backs up what it
replaces and removes nothing; a texture --fix could not shrink stays in place. All in temp folders."""
import os

from conftest import m  # noqa: F401  (loads the modules from SRC)

import mwdialog_generated as G
import mwdialog_restore as R


def _game(tmp_path):
    game = tmp_path / "game"
    (game / "Data Files").mkdir(parents=True)
    (game / "Morrowind.ini").write_text("[Game Files]\n", encoding="utf-8")
    return game, game / "Data Files"


def test_restore_all_puts_back_the_oldest_backup_and_keeps_what_it_replaced(tmp_path):
    game, data = _game(tmp_path)
    (data / "X.esp").write_bytes(b"edited twice")
    home = game / "mwdialog_backup" / "Data Files"
    home.mkdir(parents=True)
    (home / "X.esp.bak").write_bytes(b"original")
    (home / "X.esp.bak2").write_bytes(b"edited once")
    assert R.restore_all(str(data), True, str(tmp_path / "fix.log")) == 0
    assert (data / "X.esp").read_bytes() == b"original"
    legacy = game / "mwdialog_backup" / "legacy" / "Data Files"
    assert os.listdir(home) == ["X.esp.bak3"]       # one backup at the top: the newest; older ones in legacy
    assert sorted(os.listdir(legacy)) == ["X.esp.bak", "X.esp.bak2"]
    assert (home / "X.esp.bak3").read_bytes() == b"edited twice"
    assert R.restore_all(str(data), True, str(tmp_path / "fix.log")) == 0
    assert len(os.listdir(home)) + len(os.listdir(legacy)) == 3      # nothing to do the second time


def test_a_texture_that_could_not_be_shrunk_stays_in_place(tmp_path, monkeypatch):
    game, data = _game(tmp_path)
    tex = data / "Textures" / "big.dds"
    tex.parent.mkdir()
    tex.write_bytes(b"full size")
    monkeypatch.setattr(G, "dds_reduce", lambda data_: (b"small", (4096, 4096, 2048, 2048)))
    real_replace = os.replace

    def failing_replace(src, dst):
        if str(src).endswith(".mwdtmp"):
            raise OSError("disk full")
        return real_replace(src, dst)

    monkeypatch.setattr(G.os, "replace", failing_replace)
    log = []
    assert G.reduce_textures(str(data), str(game), [(str(tex), "Textures\\big.dds", 4096, 4096, 9)], log) == (0, 0)
    assert tex.read_bytes() == b"full size"
    assert not os.path.exists(str(tex) + ".mwdtmp")
    assert not (game / G.REDUCED_RECORD).exists()
    assert "NOT reduced" in log[-1][2]


def test_installed_tools_back_up_into_their_folder_one_per_file(tmp_path, monkeypatch):
    import shutil
    import mwdialog_backup as B
    import mwdialog_loadorder as LO
    game = tmp_path / "Morrowind"
    (game / "Data Files").mkdir(parents=True)
    ini = game / "Morrowind.ini"
    ini.write_bytes(b"[Game Files]\r\nGameFile0=Morrowind.esm\r\n")
    monkeypatch.setattr(B, "TOOL_DIR", str(game / "conflict-tools"))
    root = game / "conflict-tools" / "backups"
    p = game / "Data Files" / "X.esp"
    p.write_bytes(b"v")
    for _ in range(3):
        shutil.copy2(p, B.backup_path(str(p)))
    assert os.listdir(root / "Data Files") == ["X.esp.bak3"]
    assert sorted(os.listdir(root / "legacy" / "Data Files")) == ["X.esp.bak", "X.esp.bak2"]
    assert [os.path.basename(c) for c in B.backup_candidates(str(p))] == ["X.esp.bak", "X.esp.bak2", "X.esp.bak3"]
    rules = game / "mwdialog_check.rules.txt"
    rules.write_text("x")
    dated = B.stamped_backup(str(rules))
    shutil.copy2(rules, dated)
    shutil.copy2(rules, B.backup_path(str(rules)))       # a numbered backup retires the dated one
    assert [f for f in os.listdir(root) if f.startswith("mwdialog_check")] == ["mwdialog_check.rules.txt.bak"]
    assert os.path.basename(dated) in os.listdir(root / "legacy")
    LO.write_ini_game_files(str(ini), ["Morrowind.esm", "A.esp"])
    assert [f for f in os.listdir(root) if f.startswith("Morrowind.ini")] == ["Morrowind.ini.mwdialog-play.bak"]
    kept = [f for f in os.listdir(root / "legacy") if f.startswith("Morrowind.ini")]
    assert "Morrowind.ini.mwdialog-original.bak" in kept and len(kept) == 2
    assert not (game / "mwdialog_backup").exists()


def test_restore_all_dry_run_lists_and_changes_nothing(tmp_path):
    game, data = _game(tmp_path)
    (data / "X.esp").write_bytes(b"edited")
    home = game / "mwdialog_backup" / "Data Files"
    home.mkdir(parents=True)
    (home / "X.esp.bak").write_bytes(b"original")
    assert R.restore_all(str(data), True, str(tmp_path / "fix.log"), dry_run=True) == 0
    assert (data / "X.esp").read_bytes() == b"edited" and os.listdir(home) == ["X.esp.bak"]
