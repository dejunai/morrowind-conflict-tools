"""CR-8: bug reports append by section, attribute mesh textures to the providing mod, omit
normal-map stand-ins, and drop PlaceholderCell-covered script warnings."""
import os
from types import SimpleNamespace

import pytest

from conftest import ah, m, plugin


def reports(tmp_path, name):
    return "".join(r.read_text(encoding="utf-8") for r in tmp_path.rglob(f"{name}*.bugreport.txt"))


def test_update_bug_report_preserves_header_and_appends_sections(tmp_path):
    out = tmp_path / "bugreports" / "Subject.bugreport.txt"
    tidy_header = ["Bug report for Subject.esp", "Generated 2026-11-01 08:00 by vortex_tidy.",
                   "Paths are relative to the mod's folder (Data Files)."]
    check_header = ["Bug report for Subject.esp", "Generated 2026-11-24 10:00 by mwdialog_check.",
                    "Paths are relative to Data Files."]
    ah.update_bug_report(str(out), "vortex_tidy (files)", tidy_header, ["  - own broken texture"])
    ah.update_bug_report(str(out), "mwdialog_check", check_header, ["  - header says 7 record(s), the file has 1"])
    text = out.read_text(encoding="utf-8")
    assert "Generated 2026-11-01 08:00 by vortex_tidy." in text
    assert "Generated 2026-11-24 10:00 by mwdialog_check." not in text
    assert "own broken texture" in text
    assert "header says 7 record(s), the file has 1" in text
    assert "======== vortex_tidy (files) ========" in text
    assert "======== mwdialog_check ========" in text
    # a later rewrite of only the check section leaves tidy's section in place
    ah.update_bug_report(str(out), "mwdialog_check", check_header, ["  - a different check finding"])
    text = out.read_text(encoding="utf-8")
    assert "own broken texture" in text
    assert "a different check finding" in text
    assert "header says 7 record(s), the file has 1" not in text
    assert "Generated 2026-11-01 08:00 by vortex_tidy." in text


def test_update_bug_report_keeps_legacy_unsectioned_content(tmp_path):
    out = tmp_path / "bugreports" / "Legacy.bugreport.txt"
    out.parent.mkdir(parents=True)
    out.write_text("Bug report for Legacy.esp\n\nSome old finding from an earlier tool.\n", encoding="utf-8")
    ah.update_bug_report(str(out), "mwdialog_check", ["Bug report for Legacy.esp", "Generated now."],
                         ["  - a new finding"])
    text = out.read_text(encoding="utf-8")
    assert "Some old finding from an earlier tool." in text
    assert "======== previous report ========" in text
    assert "a new finding" in text
    assert "Generated now." in text


def test_step8_without_asset_check_does_not_wipe_the_asset_section(tmp_path):
    data = tmp_path / "Data Files"
    data.mkdir()
    path = data / "Subject.esp"
    plugin(path, [], [])
    plugins = [("Subject.esp", str(path))]
    world = m.World(m.Report())
    world.generated = [(r"Textures\sign.dds", "model 'banners.nif' (Subject.esp)", None, "Subject.esp")]
    args5 = SimpleNamespace(data_dir=str(data), asset_check=True, fix=True)
    m.write_bug_reports(args5, plugins, world.r, world)
    text = reports(tmp_path, "Subject")
    assert "======== mwdialog_check (assets) ========" in text
    assert r"Textures\sign.dds" in text
    # --all / step 8: --fix without --asset-check, and no generated stand-ins this pass
    world.generated = []
    args8 = SimpleNamespace(data_dir=str(data), asset_check=False, fix=True)
    m.write_bug_reports(args8, plugins, m.Report(), world)
    text = reports(tmp_path, "Subject")
    assert "======== mwdialog_check (assets) ========" in text
    assert r"Textures\sign.dds" in text


def test_automerge_does_not_get_its_own_bug_report(tmp_path):
    data = tmp_path / "Data Files"
    data.mkdir()
    path = data / m.AUTO_MERGE_NAME
    plugin(path, [], [])
    plugins = [(m.AUTO_MERGE_NAME, str(path))]
    world = m.World(m.Report())
    world.r.add("WARN", m.AUTO_MERGE_NAME, "", "", "header says 7 record(s), the file has 1")
    m.write_bug_reports(SimpleNamespace(data_dir=str(data)), plugins, world.r, world)
    assert list(tmp_path.rglob("*.bugreport.txt")) == []


def test_pluginless_mesh_replacer_texture_is_attributed_to_the_mod(tmp_path):
    # The winning record still belongs to Morrowind.esm; the .nif is a loose replacer with no plugin.
    game = tmp_path / "Morrowind"
    df = game / "Data Files"
    (df / "Meshes" / "f").mkdir(parents=True)
    mod = tmp_path / "Water In Wells 60418 1 2026-09-30T17-39Z KH7cHaR6"
    (mod / "Meshes" / "f").mkdir(parents=True)
    src = mod / "Meshes" / "f" / "furn_well00.nif"
    src.write_bytes(b"NIF")
    dst = df / "Meshes" / "f" / "furn_well00.nif"
    os.link(src, dst)

    world = m.World(m.Report())
    world.assets = SimpleNamespace(
        mesh_exists=lambda v: True,
        missing_textures=lambda v: [r"oaab\water\tr_water11.dds"],
        find_orphaned=lambda *a, **k: None,
        norm=m.ModelAssets.norm,
        mesh_loose={r"f\furn_well00.nif": str(dst)},
        mesh_bsa={},
    )
    world.vortex = None
    win = (0, "Morrowind.esm", {("MODL", "mesh"): r"f\furn_well00.nif"}, False, "furn_well00")
    world._texture_stand_ins(win)
    assert world.generated, "expected a stand-in for the missing diffuse"
    rel, why, source, blamed, blamed_dir = world.generated[0]
    assert blamed == "Water In Wells 60418 1 2026-09-30T17-39Z KH7cHaR6"
    assert blamed != "Morrowind.esm"
    assert blamed_dir == str(mod)
    assert "Morrowind.esm" not in why
    assert "Water In Wells" in why

    import mwdialog_bugreports as BR
    mm = SimpleNamespace(OUR_PATCHES=(), is_our_patch=lambda n: False, OWN_FIXES={})
    report = SimpleNamespace(issues=[], fixes=[], bug_context={})
    per = BR.collect(mm, [("Morrowind.esm", "Morrowind.esm")], report, world)
    assert "morrowind.esm" not in per or not per["morrowind.esm"]["missing"]
    pkg = ("__package__", str(mod), blamed)
    assert pkg in per
    assert any("tr_water11.dds" in line and "Water In Wells" in line for line in per[pkg]["missing"])


@pytest.mark.parametrize("name", ["tr_water11_n.dds", "tx_a_nm.dds", "tx_a_nrm.dds", "tx_a_normal.dds"])
def test_normal_map_stand_ins_are_omitted_from_bug_reports(name):
    import mwdialog_bugreports as BR
    import mwdialog_state as MS
    assert MS.NORMAL_MAP_RE.search(rf"Textures\{name}")
    mm = SimpleNamespace(OUR_PATCHES=(), is_our_patch=lambda n: False, OWN_FIXES={})
    report = SimpleNamespace(issues=[], fixes=[], bug_context={})
    world = SimpleNamespace(masters={}, generated=[
        (rf"Textures\{name}", "model 'f\\furn_well00.nif' (Morrowind.esm)", None, "Morrowind.esm"),
        (r"Textures\oaab\water\tr_water11.dds", "model 'f\\furn_well00.nif' (Morrowind.esm)", None, "Morrowind.esm"),
    ], missing_files=[])
    per = BR.collect(mm, [("Morrowind.esm", "Morrowind.esm")], report, world)
    missing = per["morrowind.esm"]["missing"]
    assert any("tr_water11.dds" in line for line in missing), missing
    assert not any(name in line for line in missing), missing


def test_normal_map_regex_groups_nrm_and_normal_with_other_normals():
    import mwdialog_state as MS
    for rel in (r"Textures\a_n.dds", r"Textures\a_nm.tga", r"Textures\a_normal.bmp", r"Textures\a_nrm.dds"):
        assert MS.NORMAL_MAP_RE.search(rel), rel
    assert not MS.NORMAL_MAP_RE.search(r"Textures\tr_water11.dds")
    assert not MS.NORMAL_MAP_RE.search(r"Textures\tx_wall.dds")


def test_deleted_object_goes_into_missing_objects_for_placeholdercell():
    world = m.World(m.Report())
    world.defined_by_obj["bm_thing"] = "Bloodmoon.esm"
    world.deleted_by_obj["bm_thing"] = "Later.esp"
    world.script_src["bmscript"] = ("Bloodmoon.esm", "BmScript", "Begin BmScript\nBm_Thing->Disable\nEnd\n")
    world._check_scripts()
    assert "bm_thing" in world.missing_objects
    assert world.missing_objects["bm_thing"]["arrow"] is True
    assert ("Bloodmoon.esm", "BmScript") in world.missing_objects["bm_thing"]["used_by"]
    assert any("deletes it" in issue[4] for issue in world.r.issues)


def test_placeholder_covered_script_warnings_are_suppressed(tmp_path):
    data = tmp_path / "Data Files"
    data.mkdir()
    subject = data / "Subject.esp"
    later = data / "Later.esp"
    plugin(subject, [("Later.esp", 0)], [])
    plugin(later, [], [])
    plugins = [("Subject.esp", str(subject)), ("Later.esp", str(later))]

    # A missing object the script names, and a last placed copy Later.esp deletes (Later is a
    # declared master, so without --fix the warning currently appears on Subject).
    world = m.World(m.Report())
    world.gold_template = b"gold"
    world.masters = {"subject.esp": ["Later.esp"]}
    world.script_src["needsmissing"] = ("Subject.esp", "NeedsMissing",
                                        "Begin NeedsMissing\nMissingObj->Disable\nEnd\n")
    world.all_ids["rent_door"] = "DOOR"
    world.defined_by_obj["rent_door"] = "Subject.esp"
    world.unplaced_by["rent_door"] = "Later.esp"
    world.arrow_targets["rent_door"] = {"id": "Rent_Door", "used_by": [("Subject.esp", "Pub")]}
    world._check_scripts()
    world._check_placed()
    assert "missingobj" in world.missing_objects
    assert "rent_door" in world.unplaced

    m.write_bug_reports(SimpleNamespace(data_dir=str(data)), plugins, world.r, world)
    text = reports(tmp_path, "Subject")
    assert "MissingObj" in text or "NeedsMissing" in text
    assert "Rent_Door" in text or "deleted the last placed copy" in text

    m.write_bug_reports(SimpleNamespace(data_dir=str(data), fix=True), plugins, world.r, world)
    text = reports(tmp_path, "Subject")
    later_text = reports(tmp_path, "Later")
    assert "which doesn't exist" not in text
    assert "no copy of it is placed" not in text
    assert "======== mwdialog_check (conflicts) ========" in later_text
    assert "this plugin deletes" in later_text
    assert "Rent_Door" in later_text or "Pub" in later_text
