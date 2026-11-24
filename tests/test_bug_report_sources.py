"""A plugin's bug report (to send its author) lists its own faults wherever they were found: records --clean
removes (a dirty plugin), and a master's header faults, which are only reported because a master is never edited."""
import os
import struct
from types import SimpleNamespace

import pytest

from conftest import m, misc, plugin, rec, sub, z


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


def report_world(tmp_path, masters=()):
    data = tmp_path / "Data Files"
    data.mkdir()
    paths = []
    for name in ("Base.esm", "Subject.esp", "Other.esp"):
        path = data / name
        plugin(path, [(master, 0) for master in masters] if name == "Subject.esp" else [], [])
        paths.append((name, str(path)))
    world = m.World(m.Report())
    world.masters = {"subject.esp": list(masters)}
    world.loaded = [name.lower() for name, _path in paths]
    return SimpleNamespace(data_dir=str(data)), paths, world


@pytest.mark.parametrize("declared_master", [False, True, "transitive"])
def test_unplaced_script_targets_are_only_reported_within_the_declared_dependency_chain(tmp_path, declared_master):
    masters = ("Other.esp",) if declared_master == "transitive" else ("Base.esm",) if declared_master else ()
    args, plugins, world = report_world(tmp_path, masters)
    if declared_master == "transitive":
        world.masters["other.esp"] = ["Base.esm"]
    world.all_ids["target"] = "STAT"
    world.defined_by_obj["target"] = "Subject.esp"
    world.unplaced_by["target"] = "Base.esm"
    world.arrow_targets["target"] = {"id": "target", "used_by": [("Subject.esp", "script")]}
    world._check_placed()
    assert world.r.issues
    m.write_bug_reports(args, plugins, world.r, world)
    assert ("deleted the last placed copy" in reports(tmp_path, "Subject")) == bool(declared_master)


def test_interaction_repairs_do_not_leak_back_into_bug_reports(tmp_path):
    args, plugins, world = report_world(tmp_path, ("Base.esm",))
    world.r.add("ERROR", "Subject.esp", "Greeting", "123", "previous link deleted by a later plugin",
                fix=(16, ("set_prev", ""), "relinked after the other plugin's deletion"))
    world.r.add("ERROR", "Subject.esp", "", "", "header says 7 record(s), the file has 1",
                fix=(0, ("fix_count",), "set the header's record count to 1"))
    m.write_bug_reports(args, plugins, world.r, world)
    text = reports(tmp_path, "Subject")
    assert "header says 7" in text
    assert "record count to 1" in text
    assert "previous link" not in text
    assert "relinked" not in text
    assert len(world.r.fixes) == 2


@pytest.mark.parametrize("declared_master", [False, True])
def test_cell_kind_clashes_record_the_plugin_that_supplied_the_conflicting_cell(tmp_path, declared_master):
    args, plugins, world = report_world(tmp_path, ("Base.esm",) if declared_master else ())
    world.cell_name_at = {("e", 1, 2): [(0, "Base.esm", "Shared place")]}
    world.cell_loads = [(1, "Subject.esp", ("i", "shared place"), "Shared place", 0)]
    world._check_cell_kind_clash()
    assert world.r.issues
    m.write_bug_reports(args, plugins, world.r, world)
    assert ("trying to become Exterior Cell" in reports(tmp_path, "Subject")) == declared_master


def test_master_mismatch_details_become_one_summary_without_hiding_an_independent_defect(tmp_path):
    args, plugins, world = report_world(tmp_path, ("Base.esm", "Other.esp"))
    verdict = dict(plugin="Subject.esp", master="Base.esm", kind="different mod", confidence=0.9,
                   original_size=100, installed_size=200, size_source="original header",
                   total=40, hits=1, misses=["old_target"])
    world.master_verdicts = {("subject.esp", "base.esm"): verdict}
    world.master_verdicts[("subject.esp", "other.esp")] = dict(verdict, master="Other.esp", obsolete=True)
    m.mastercheck_module()._report(world.r, verdict)
    path = dict(plugins)["Subject.esp"]
    body = sub("NAME", z("Old interior")) + sub("DATA", struct.pack("<Iii", 1, 0, 0))
    plugin(path, [("Base.esm", 100)], [rec("CELL", body)])
    world.paths = {name.lower(): path for name, path in plugins}
    world.ref_mods = [("Subject.esp", 16, ("i", "old interior"), "Old interior",
                       (1 << 24) | index, f"old_{index}", False, None, False) for index in range(1, 21)]
    world._check_refs()
    world.r.add("ERROR", "Subject.esp", "", "", "header says 7 record(s), the file has 1")
    m.write_bug_reports(args, plugins, world.r, world)
    text = reports(tmp_path, "Subject")
    assert "header says 7" in text
    summaries = [line for line in text.splitlines() if "Master compatibility:" in line]
    assert len(summaries) == 1
    assert "Base.esm" in summaries[0] and "obsolete" in summaries[0]
    assert "Other.esp" in summaries[0]
    assert "changes reference #" not in text
    assert "old_target" not in text
    assert "original header" not in text
    assert len(world.r.issues) > 20


def test_deleted_dialogue_dependencies_and_their_fixes_are_not_the_authors_own_bugs(tmp_path):
    args, plugins, world = report_world(tmp_path, ("Base.esm",))
    world.deleted_by_obj["speaker"] = "Other.esp"
    deleted_topic = world._load_dial(sub("NAME", z("Lost topic")) + sub("DATA", b"\0"), 0, "Base.esm", 0)
    world._load_dial(sub("NAME", z("Lost topic")) + sub("DELE", b"\0" * 4), 0, "Other.esp", 0)
    assert deleted_topic.deleted_by == "Other.esp"
    topic = m.Topic("Greeting", 1, "Subject.esp")
    info = m.Info()
    info.id, info.source, info.off = "123", "Subject.esp", 16
    info.actor = "speaker"
    info.result = 'AddTopic "Lost topic"'
    world._check_info(info, topic, {}, None)
    assert len(world.r.fixes) == 2
    m.write_bug_reports(args, plugins, world.r, world)
    assert not reports(tmp_path, "Subject")


def test_cleaning_report_removes_stale_interaction_findings_but_preserves_other_sections(tmp_path):
    args, plugins, world = report_world(tmp_path)
    ah = m.asset_health_module()
    out = ah.bug_report_path(args.data_dir, str(tmp_path), "Subject.esp", m)
    header = ["Bug report for Subject.esp"]
    ah.update_bug_report(out, "mwdialog_check", header, ["old load-order conflict"])
    ah.update_bug_report(out, "vortex_tidy (files)", header, ["own broken texture"])
    world.r.add("WARN", "Subject.esp", "", "", "Other.esp deleted the last placed copy")
    m.write_bug_reports(args, plugins, world.r, world)
    text = reports(tmp_path, "Subject")
    assert "old load-order conflict" not in text
    assert "own broken texture" in text


def test_package_file_reports_do_not_pick_an_arbitrary_plugin(tmp_path):
    ah = m.asset_health_module()
    plugin(tmp_path / "One.esp", [], [])
    plugin(tmp_path / "Two.esp", [], [])
    subject, header = ah.package_bug_report_subject(str(tmp_path), m, "Package")
    assert subject == "Package"
    assert not any(line.startswith("Plugin:") for line in header)
    assert "not an individual plugin" in " ".join(header)


def test_asset_bug_reports_keep_the_file_defect_not_the_cross_plugin_rename_decision():
    ah = m.asset_health_module()
    message = "non-ASCII file name, named so by Other.esp; left as it is (renaming it would break that plugin)"
    issues = [("WARN", "Textures\\non-ascii.dds", message)]
    text = "\n".join(ah.package_asset_bug_lines(issues))
    assert "non-ASCII file name" in text
    assert "Other.esp" not in text
    assert issues[0][2] == message


def splash_tga(path, width, bpp, noisy=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    pixel = (lambda i: bytes([i % 251, i % 241, i % 239]) + b"\x80" * (bpp == 4)) if noisy else \
        (lambda i: bytes([40, 80, 120, 255][:bpp]))
    head = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, width, 8, bpp * 8, 8 if bpp == 4 else 0)
    path.write_bytes(head + b"".join(pixel(i) for i in range(width * 8)))


def test_size_reductions_are_repairs_but_not_bugs_while_alpha_and_mipmaps_are(tmp_path):
    ah = m.asset_health_module()
    mod = tmp_path / "Splash Pack"
    splash_tga(mod / "Splash" / "wide.tga", 4096, 3)
    splash_tga(mod / "Splash" / "wide_alpha.tga", 4096, 4)
    splash_tga(mod / "Splash" / "alpha.tga", 1024, 4, noisy=True)
    splash_tga(mod / "Splash" / "no_rle.tga", 1024, 3)
    issues, fixes = ah.check_folder(str(mod), m, None)
    assert len([f for f in fixes if f[0] == "splash"]) == 4
    issues += [("WARN", "Textures\\big.dds", "4096x4096 (over 2048) -> converted"),
               ("WARN", "Textures\\rock.dds", "4096x4096 (over 2048), no mipmaps -> converted")]
    text = "\n".join(ah.package_asset_bug_lines(issues))
    assert "Problems in the mod's files: 3" in text, text
    assert "wide_alpha.tga" in text and "alpha.tga: splash screen with an alpha channel" in text
    assert "wide.tga" not in text and "no_rle.tga" not in text and "big.dds" not in text
    assert "rock.dds: no mipmaps -> converted" in text
    reductions = [i for i in issues if os.path.basename(i[1]) in ("wide.tga", "no_rle.tga", "big.dds")]
    assert len(reductions) == 3 and ah.package_asset_bug_lines(reductions) == []
