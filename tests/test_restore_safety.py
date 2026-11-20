"""Putting things back never loses the original: --restore-all uses the oldest backup and removes backups only
after the plugin matches it; a texture --fix could not shrink stays in place. All in temp folders."""
import os

from conftest import m  # noqa: F401  (loads the modules from SRC)

import mwdialog_generated as G
import mwdialog_restore as R


def _game(tmp_path):
    game = tmp_path / "game"
    (game / "Data Files").mkdir(parents=True)
    (game / "Morrowind.ini").write_text("[Game Files]\n", encoding="utf-8")
    return game, game / "Data Files"


def test_restore_all_puts_back_the_oldest_backup_then_removes_them(tmp_path):
    game, data = _game(tmp_path)
    (data / "X.esp").write_bytes(b"edited twice")
    home = game / "mwdialog_backup" / "Data Files"
    home.mkdir(parents=True)
    (home / "X.esp.bak").write_bytes(b"original")
    (home / "X.esp.bak2").write_bytes(b"edited once")
    assert R.restore_all(str(data), True, str(tmp_path / "fix.log")) == 0
    assert (data / "X.esp").read_bytes() == b"original"
    assert sorted(os.listdir(home)) == []


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
