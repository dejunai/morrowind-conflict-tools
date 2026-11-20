"""A plugin's bug report (to send its author) lists its own faults wherever they were found: records --clean
removes (a dirty plugin), and a master's header faults, which are only reported because a master is never edited."""
from conftest import m, misc, plugin


def reports(tmp_path, name):
    return "".join(r.read_text(encoding="utf-8") for r in tmp_path.rglob(f"{name}*.bugreport.txt"))


def test_a_dirty_plugin_and_a_masters_bad_header_reach_their_bug_reports(tmp_path):
    g = tmp_path / "Morrowind"
    df = g / "Data Files"
    df.mkdir(parents=True)
    (g / "Morrowind.ini").write_text("[Game Files]\n")
    thing = misc("zz_thing", value=5)
    plugin(df / "Base.esm", [], [thing], count=7)                 # the header says 7 records; it has 1
    plugin(df / "Dirty.esp", [("Base.esm", (df / "Base.esm").stat().st_size)], [thing, misc("zz_new")])
    m.OWN_FIXES.clear()
    m.main([str(df), "--plugins", "Base.esm", "Dirty.esp", "--no-vortex", "--no-archive-lookup", "--clean",
            "--fix", "--yes", "--fix-log", str(g / "mwdialog_fixes.log")])
    dirty = reports(tmp_path, "Dirty")
    assert "dirty: 1 duplicate record" in dirty, dirty
    base = reports(tmp_path, "Base")
    assert "header says 7 record(s), the file has 1" in base, base
