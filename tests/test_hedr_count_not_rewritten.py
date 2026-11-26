"""A released plugin whose header record count is wrong (No Fires in Bad Weather.esp: saved by OpenMW-CS with 1,
has 2) is not rewritten just for that: the game uses the count only for the loading bar, and rewriting the file in
place (through its hard link, into the Vortex staging copy too) made it differ from the mod's release after every
--fix. When --fix rewrites the plugin for a real repair, the count is still set to the true one."""
import hashlib
import os
import struct

from conftest import hedr_count, m, misc, plugin


def _game(tmp_path):
    g = tmp_path / "Morrowind"
    df = g / "Data Files"
    df.mkdir(parents=True)
    (g / "Morrowind.ini").write_text("[Game Files]\n")
    return g, df


def _fix(g, df, names):
    m.OWN_FIXES.clear()
    m.main([str(df), "--plugins", *names, "--no-vortex", "--no-archive-lookup", "--fix", "--yes",
            "--fix-log", str(g / "mwdialog_fixes.log")])


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _backups(tmp_path, name):
    return [p for p in tmp_path.rglob("*") if p.name.lower().startswith(name.lower() + ".bak")]


def test_a_wrong_record_count_alone_leaves_the_released_file_byte_identical(tmp_path):
    g, df = _game(tmp_path)
    plugin(df / "Base.esm", [], [misc("zz_base")])
    rel = df / "Release.esp"
    plugin(rel, [("Base.esm", (df / "Base.esm").stat().st_size)], [misc("zz_a"), misc("zz_b")], count=1)
    os.utime(rel, (1020211200, 1020211200))                       # a load-order date, as on the real file
    before, mtime = _sha(rel), rel.stat().st_mtime
    for _ in range(2):                                            # every run, not just the first
        _fix(g, df, ["Base.esm", "Release.esp"])
        assert _sha(rel) == before
        assert rel.stat().st_mtime == mtime
        assert hedr_count(rel) == 1
    assert not _backups(tmp_path, "Release.esp")
    path = g / "mwdialog_fixes.log"
    log = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    assert "Release.esp: header says 1 record(s)" not in log


def test_the_mismatch_is_still_reported_as_cosmetic():
    report = m.Report()
    world = m.World(report)
    world.hedr_count = {"Release.esp": 1, "Base.esm": 9}
    world.real_count = {"Release.esp": 2, "Base.esm": 1}
    world.size_mismatch = []
    world._check_headers()
    text = repr(report.issues)
    assert "header says 1 record(s), the file has 2" in text
    assert "loading bar" in text
    assert "a master; not changed" in text
    assert not [f for f in report.fixes if "fix_count" in repr(f)]


def test_a_real_repair_still_writes_the_true_count(tmp_path):
    g, df = _game(tmp_path)
    plugin(df / "Base.esm", [], [misc("zz_base")])
    rel = df / "Release.esp"
    stale = (df / "Base.esm").stat().st_size + 40                 # the master changed size since it was saved
    plugin(rel, [("Base.esm", stale)], [misc("zz_a"), misc("zz_b")], count=1)
    _fix(g, df, ["Base.esm", "Release.esp"])
    data = rel.read_bytes()
    assert hedr_count(rel) == 2
    i = data.index(b"DATA", data.index(b"MAST"))
    assert struct.unpack_from("<Q", data, i + 8)[0] == (df / "Base.esm").stat().st_size
    after = _sha(rel)
    _fix(g, df, ["Base.esm", "Release.esp"])                      # idempotent: nothing left to change
    assert _sha(rel) == after
