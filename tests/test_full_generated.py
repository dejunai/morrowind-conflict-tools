"""CT-48: --full builds generated patches once, on the last --fix after --clean and sort."""
import sys

from conftest import m, misc, plugin
from test_full_redundant import full_args

def _game(tmp_path):
    g = tmp_path / "Morrowind"
    df = g / "Data Files"
    df.mkdir(parents=True)
    (g / "Morrowind.ini").write_text("[Game Files]\n")
    return g, df


def test_deferred_fix_does_not_write_or_drop_cell_fixes(tmp_path):
    g, df = _game(tmp_path)
    plugin(df / "Base.esm", [], [misc("zz_base")])
    existing = df / m.CELL_WINNER_PATCH
    existing.write_bytes(b"keep-cell-fixes")
    args = type("A", (), {"data_dir": str(df), "dry_run": False, "ini": str(g / "Morrowind.ini"),
                           "fix": True})()
    m.IN_FULL = True
    m.FULL_FINAL_PASS = False
    try:
        m.fix_cell_winners(args, [("Base.esm", str(df / "Base.esm"))])
    finally:
        m.IN_FULL = False
        m.FULL_FINAL_PASS = False
    assert existing.read_bytes() == b"keep-cell-fixes"


def test_deferred_run_fix_skips_esm_and_place_patches(tmp_path, monkeypatch):
    g, df = _game(tmp_path)
    plugin(df / "Base.esm", [], [misc("zz_base")])
    plugin(df / "Mod.esp", [("Base.esm", (df / "Base.esm").stat().st_size)], [misc("zz_mod")])
    built = []
    monkeypatch.setattr(m, "write_patch", lambda *a, **k: built.append("write_patch") or (0, 0))
    m.IN_FULL = True
    m.FULL_FINAL_PASS = False
    try:
        rc = m.main([str(df), "--plugins", "Base.esm", "Mod.esp", "--fix", "--yes",
                     "--no-vortex", "--no-archive-lookup", "--no-soundfix", "--no-doubled",
                     "--fix-log", str(g / "fix.log")])
    finally:
        m.IN_FULL = False
        m.FULL_FINAL_PASS = False
    assert rc in (0, 1)
    assert not (df / m.PATCH_NAME).exists()
    assert not (df / m.PLACE_PATCH_NAME).exists()
    assert "write_patch" not in built


def test_final_pass_and_standalone_still_build_generated_work(tmp_path, monkeypatch):
    g, df = _game(tmp_path)
    plugin(df / "Base.esm", [], [misc("zz_base")])
    plugin(df / "Mod.esp", [("Base.esm", (df / "Base.esm").stat().st_size)], [misc("zz_mod")])
    calls = []
    monkeypatch.setattr(m, "run_multipatch", lambda *a, **k: calls.append("multipatch"))
    real_cc = m.run_cell_conflicts
    def spy_cc(*a, **k):
        if k.get("aux_only"):
            calls.append("aux")
            return None
        return real_cc(*a, **k)
    monkeypatch.setattr(m, "run_cell_conflicts", spy_cc)
    import mwdialog_soundfix as sf
    monkeypatch.setattr(sf, "run_soundfix", lambda *a, **k: calls.append("soundfix") or 0)
    monkeypatch.setattr(m, "sync_master_sizes_now", lambda *a, **k: calls.append("sync") or 0)

    def run(flag_in_full, final):
        calls[:] = []
        m.IN_FULL = flag_in_full
        m.FULL_FINAL_PASS = final
        try:
            return m.main([str(df), "--plugins", "Base.esm", "Mod.esp", "--fix", "--multipatch", "--yes",
                           "--no-vortex", "--no-archive-lookup", "--no-doubled",
                           "--fix-log", str(g / "fix.log")])
        finally:
            m.IN_FULL = False
            m.FULL_FINAL_PASS = False

    run(True, False)
    assert "soundfix" not in calls and "multipatch" not in calls and "aux" not in calls
    assert "sync" in calls

    run(True, True)
    assert "soundfix" in calls and "multipatch" in calls
    assert calls[-1] == "sync"

    run(False, False)
    assert "soundfix" in calls and "multipatch" in calls
    assert calls[-1] == "sync"


def test_run_full_builds_generated_patches_only_on_the_last_fix(tmp_path, monkeypatch):
    steps = []

    def fake(argv):
        steps.append(list(argv[1:]))
        return 0
    monkeypatch.setattr(m, "main", fake)
    monkeypatch.setattr(m, "full_check", lambda *a, **k: 0)
    monkeypatch.setattr(m, "full_missing_masters", lambda *a, **k: [])
    monkeypatch.setattr(m, "full_reset", lambda *a, **k: 0)
    monkeypatch.setattr(m, "multipatch_aside", lambda *a, **k: 0)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    (tmp_path / "Data Files").mkdir()
    m.run_full(full_args(tmp_path, no_redundant=True, no_interactive=True, fresh_answers=True))
    fixes = [a for a in steps if "--fix" in a]
    assert len(fixes) >= 2
    assert all("--multipatch" not in a for a in fixes[:-1])
    assert "--multipatch" in fixes[-1]
    assert not any("--all" in a for a in steps)
