"""MAST DATA sizes are synced as the last step after plugin writes, and file dates are kept."""
import os
import struct

from conftest import m, misc, plugin


def _game(tmp_path):
    g = tmp_path / "Morrowind"
    df = g / "Data Files"
    df.mkdir(parents=True)
    (g / "Morrowind.ini").write_text("[Game Files]\n")
    return g, df


def _mast_size(path):
    data = path.read_bytes()
    i = data.index(b"DATA", data.index(b"MAST"))
    return struct.unpack_from("<Q", data, i + 8)[0]


def test_sync_master_sizes_updates_stale_size_and_keeps_the_date(tmp_path):
    g, df = _game(tmp_path)
    plugin(df / "Base.esm", [], [misc("zz_base")])
    stale = (df / "Base.esm").stat().st_size + 40
    rel = df / "Mod.esp"
    plugin(rel, [("Base.esm", stale)], [misc("zz_mod")])
    os.utime(rel, (1020211200, 1020211200))
    before = rel.stat().st_mtime
    args = type("A", (), {"data_dir": str(df), "dry_run": False})()
    n = m.sync_master_sizes_now(args, [("Base.esm", str(df / "Base.esm")), ("Mod.esp", str(rel))])
    assert n == 1
    assert _mast_size(rel) == (df / "Base.esm").stat().st_size
    assert rel.stat().st_mtime == before


def test_sync_master_sizes_is_idempotent(tmp_path):
    g, df = _game(tmp_path)
    plugin(df / "Base.esm", [], [misc("zz_base")])
    rel = df / "Mod.esp"
    plugin(rel, [("Base.esm", (df / "Base.esm").stat().st_size)], [misc("zz_mod")])
    args = type("A", (), {"data_dir": str(df), "dry_run": False})()
    plugins = [("Base.esm", str(df / "Base.esm")), ("Mod.esp", str(rel))]
    assert m.sync_master_sizes_now(args, plugins) == 0
    sha = rel.read_bytes()
    assert m.sync_master_sizes_now(args, plugins) == 0
    assert rel.read_bytes() == sha


def test_sync_runs_after_clean_and_generated_patches(tmp_path, monkeypatch):
    g, df = _game(tmp_path)
    plugin(df / "Base.esm", [], [misc("zz_base")])
    plugin(df / "Mod.esp", [("Base.esm", (df / "Base.esm").stat().st_size)], [misc("zz_mod")])
    order = []
    real_sync = m.sync_master_sizes_now

    def spy_sync(*a, **k):
        order.append("sync")
        return real_sync(*a, **k)

    monkeypatch.setattr(m, "sync_master_sizes_now", spy_sync)
    monkeypatch.setattr(m, "run_multipatch", lambda *a, **k: order.append("multipatch"))
    import mwdialog_soundfix as sf
    monkeypatch.setattr(sf, "run_soundfix", lambda *a, **k: order.append("soundfix") or 0)
    real_cc = m.run_cell_conflicts
    def spy_cc(*a, **k):
        if k.get("aux_only"):
            order.append("aux")
            return None
        return real_cc(*a, **k)
    monkeypatch.setattr(m, "run_cell_conflicts", spy_cc)
    rc = m.main([str(df), "--plugins", "Base.esm", "Mod.esp", "--fix", "--multipatch", "--yes",
                 "--no-vortex", "--no-archive-lookup", "--no-doubled",
                 "--fix-log", str(g / "fix.log")])
    assert rc in (0, 1)
    assert "sync" in order
    assert order[-1] == "sync"
    assert order.index("soundfix") < order.index("sync")
    assert order.index("multipatch") < order.index("sync")
    assert order.index("aux") < order.index("sync")
