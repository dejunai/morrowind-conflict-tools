"""Moved-land incompatibilities require a choice, not automatic relocation."""
import os
import struct
import types

import pytest

from conftest import fold, m, plugin, rec, sub, z
import mwdialog_anthology_override as A

CELL = 8192


def land_at(gx, gy, height):
    return rec("LAND", sub("INTV", struct.pack("<ii", gx, gy))
               + sub("VHGT", struct.pack("<f", height / 8.0) + bytes(4225 + 3)))


def cell_at(gx, gy, *refs):
    return rec("CELL", sub("NAME", z("")) + sub("DATA", struct.pack("<Iii", 0, gx, gy)) + b"".join(refs))


def ref(index, oid, x, y, height):
    return sub("FRMR", struct.pack("<I", index)) + sub("NAME", z(oid)) + \
        sub("DATA", struct.pack("<6f", x, y, height, 0.0, 0.0, 0.0))


def game(tmp_path, cells=8, people_land=None, people_height=None, pathgrid=False, position_script=False):
    data = tmp_path / "Data Files"
    data.mkdir(parents=True)
    heights = [40 + 8 * i for i in range(cells)]
    base = plugin(data / "Master.esm", [], [
        rec("STAT", sub("NAME", z("rock")) + sub("MODL", z("rock.nif"))),
        *[land_at(i, 0, height) for i, height in enumerate(heights)]])
    mover = plugin(data / "Mover.esp", [("Master.esm", len(base))],
                   [land_at(i, 0, -100) for i in range(cells)]
                   + [land_at(i + 2, 1, height) for i, height in enumerate(heights)])
    x, y = 3 * CELL + 2000.0, 2000.0
    records = [cell_at(3, 0, ref(1, "rock", x, y, heights[3] if people_height is None else people_height))]
    if people_land is not None:
        records.append(land_at(3, 0, people_land))
    if pathgrid:
        records.append(rec("PGRD", sub("NAME", z("")) + sub("DATA", struct.pack("<iiHH", 3, 0, 1, 1))
                           + sub("PGRP", struct.pack("<iiiBBH", 2000, 2000, int(heights[3]), 0, 0, 0))))
    if position_script:
        records.append(rec("SCPT", sub("SCHD", z("rockScript").ljust(52, b"\0"))
                           + sub("SCTX", z(f"begin rockScript\nrock->SetPos X {int(x)}\nend"))))
    plugin(data / "People.esp", [("Master.esm", len(base))], records)
    plugin(data / "Aware.esp", [("Master.esm", len(base)), ("Mover.esp", len(mover))],
           [cell_at(3, 0, ref(1, "rock", x + 500, y, heights[3]))])
    order = ["Master.esm", "Mover.esp", "People.esp", "Aware.esp"]
    (tmp_path / "Morrowind.ini").write_text("[Game Files]\n", encoding="cp1252")
    m.write_load_order(str(tmp_path), order, "test")
    args = types.SimpleNamespace(data_dir=str(data), ini=str(tmp_path / "Morrowind.ini"), dry_run=False,
                                 no_interactive=True, use_answers=False, only_new=False, conflict_min=5,
                                 conflict_top=40, conflict_all=False, only=None, fix_log=str(tmp_path / "fix.log"),
                                 fix=False, multipatch=False)
    return args, [(name, str(data / name)) for name in order]


def track_conflict_outputs(monkeypatch):
    calls = []
    for name in ("write_collide_data", "write_float_data", "write_ghost_statics", "write_stranded_data"):
        def capture(*args, _name=name, **_kwargs):
            order = args[2] if _name == "write_ghost_statics" else args[1]
            calls.append((_name, [n for n, _p in order]))
        monkeypatch.setattr(m, name, capture)
    return calls


def pathgrid_winner_game(tmp_path):
    args, plugins = game(tmp_path, cells=10, pathgrid=True)
    data = tmp_path / "Data Files"
    aware_grid = rec("PGRD", sub("NAME", z("")) + sub("DATA", struct.pack("<iiHH", 3, 0, 1, 1))
                     + sub("PGRP", struct.pack("<iiiBBH", 2000, 2000, 64, 0, 0, 0)))
    plugin(data / "Aware.esp",
           [("Master.esm", (data / "Master.esm").stat().st_size),
            ("Mover.esp", (data / "Mover.esp").stat().st_size)],
           [aware_grid])
    initial = ["Master.esm", "Mover.esp", "People.esp", "Aware.esp"]
    reordered = ["Master.esm", "Mover.esp", "Aware.esp", "People.esp"]

    def set_dates(order):
        for i, name in enumerate(order):
            os.utime(data / name, (946684800 + i * 86400, 946684800 + i * 86400))

    set_dates(initial)
    return args, plugins, data, reordered, set_dates


def test_automatic_land_relocation_is_disabled(tmp_path, capsys):
    args, plugins = game(tmp_path)
    m.fix_cell_winners(args, plugins)
    assert "automatic relocation is disabled" in capsys.readouterr().out
    patch = tmp_path / "Data Files" / m.CELL_WINNER_PATCH
    if patch.exists():
        records = list(m.iter_records(patch.read_bytes()))
        assert not any(tag == "NPC_" for _off, tag, _flags, _body in records)
        assert not any(part[0][0] == "MVRF" for _off, tag, _flags, body in records if tag == "CELL"
                       for group in m.split_cell(body)[1::2] for part in group)


def test_moved_land_requires_a_choice_but_aware_plugins_are_not_flagged(tmp_path, monkeypatch, capsys):
    args, plugins = game(tmp_path, cells=10, people_land=80, pathgrid=True)
    writes = track_conflict_outputs(monkeypatch)
    assert m.run_cell_conflicts(args, plugins) == 2
    out = fold(capsys.readouterr().out)
    assert "INCOMPATIBLE: Mover.esp vs People.esp" in out
    assert "pathgrid, placed objects, terrain" in out
    assert "INCOMPATIBLE: Mover.esp vs Aware.esp" not in out
    assert "need a choice before building patches" in out
    assert m.read_load_order(args) == [n for n, _p in plugins]
    assert writes == []


@pytest.mark.parametrize("action", ["--fix", "--multipatch", "--auto-merge"])
@pytest.mark.parametrize("in_full", [False, True])
def test_direct_builds_and_merges_stop_before_mutating_incompatible_plugins(tmp_path, capsys, monkeypatch,
                                                                            action, in_full):
    args, _plugins = game(tmp_path, cells=10, people_land=80)
    monkeypatch.setattr(m, "IN_FULL", in_full)
    data = tmp_path / "Data Files"
    before = {p.name: p.read_bytes() for p in data.iterdir() if p.is_file()}
    before_order = (tmp_path / m.LOAD_ORDER_FILE).read_bytes()
    rc = m.main([str(data), action, "--no-vortex", "--no-sounds", "--no-follow-up"])
    assert rc == 2
    assert "must be resolved before building or merging" in fold(capsys.readouterr().err)
    assert {p.name: p.read_bytes() for p in data.iterdir() if p.is_file()} == before
    assert (tmp_path / m.LOAD_ORDER_FILE).read_bytes() == before_order


@pytest.mark.parametrize("action", [["--multipatch"], ["--fix"], ["--fix", "--multipatch"], ["--all"]])
@pytest.mark.parametrize("no_follow", [False, True])
def test_sort_rechecks_incompatibilities_before_building(tmp_path, monkeypatch, capsys, action, no_follow):
    args, plugins, data, reordered, set_dates = pathgrid_winner_game(tmp_path)
    assert m.run_cell_conflicts(args, plugins, incompatible_only=True) == 0

    def sort(sort_args, _plugins):
        set_dates(reordered)
        m.write_load_order(str(tmp_path), reordered, "test sort")
        sort_args.sort_changed = True

    monkeypatch.setattr(m, "run_sort", sort)
    for name in ("fix_ref_groups", "fix_cell_layouts", "fix_cell_winners", "retire_performers_patch"):
        monkeypatch.setattr(m, name, lambda *_args: pytest.fail("repair ran before the sorted-order guard"))
    monkeypatch.setattr(m, "fix_omwaddon_masters", lambda *_args: False)
    monkeypatch.setattr(m, "fix_long_names", lambda *_args: False)
    monkeypatch.setattr(m, "scan", lambda *_args: pytest.fail("built after a newly exposed conflict"))
    flags = ["--sort", *action, "--yes", "--no-vortex", "--no-sounds", "--no-doubled"]
    if no_follow:
        flags.append("--no-follow-up")
    assert m.main([str(data), *flags]) == 2
    assert "must be resolved before building or merging" in fold(capsys.readouterr().err)


def test_sort_revalidates_after_repairs_change_plugin_state(tmp_path, monkeypatch):
    _args, _plugins, data, reordered, set_dates = pathgrid_winner_game(tmp_path)
    events = []

    def guard(_args, _plugins):
        events.append("guard")
        return 2 if events.count("guard") == 3 else 0

    def sort(sort_args, plugins):
        events.append("sort")
        set_dates(reordered)
        m.write_load_order(str(tmp_path), reordered, "test post-repair guard")
        sort_args.sort_changed = True

    monkeypatch.setattr(m, "build_compatibility_guard", guard)
    monkeypatch.setattr(m, "run_sort", sort)
    monkeypatch.setattr(m, "fix_omwaddon_masters", lambda *_args: False)
    monkeypatch.setattr(m, "fix_long_names", lambda *_args: False)
    monkeypatch.setattr(m, "fix_ref_groups", lambda *_args: events.append("fix_ref_groups"))
    monkeypatch.setattr(m, "fix_cell_layouts", lambda *_args: events.append("fix_cell_layouts"))
    monkeypatch.setattr(m, "retire_performers_patch", lambda *_args: events.append("retire_performers_patch"))
    monkeypatch.setattr(m, "fix_cell_winners", lambda *_args: pytest.fail("patch built after post-repair conflict"))
    monkeypatch.setattr(m, "scan", lambda *_args: pytest.fail("report built after post-repair conflict"))

    flags = ["--sort", "--fix", "--yes", "--no-vortex", "--no-sounds", "--no-doubled", "--no-follow-up"]
    assert m.main([str(data), *flags]) == 2
    assert events == ["guard", "sort", "guard", "fix_ref_groups", "fix_cell_layouts",
                      "retire_performers_patch", "guard"]


def test_master_repair_sort_rechecks_before_fixing(tmp_path, monkeypatch, capsys):
    args, plugins, data, reordered, set_dates = pathgrid_winner_game(tmp_path)
    assert m.run_cell_conflicts(args, plugins, incompatible_only=True) == 0

    def sort(sort_args, _plugins):
        set_dates(reordered)
        m.write_load_order(str(tmp_path), reordered, "test master repair")
        sort_args.sort_changed = True

    monkeypatch.setattr(m, "fix_omwaddon_masters", lambda *_args: True)
    monkeypatch.setattr(m, "run_sort", sort)
    monkeypatch.setattr(m, "fix_ref_groups", lambda *_args: pytest.fail("fixed after a newly exposed conflict"))
    assert m.main([str(data), "--fix", "--yes", "--no-vortex", "--no-sounds"]) == 2
    assert "must be resolved before building or merging" in fold(capsys.readouterr().err)


def test_interactive_build_guard_refuses_unreadable_plugins(tmp_path, monkeypatch, capsys):
    args, plugins = game(tmp_path)
    bad = tmp_path / "Data Files" / "Broken.esp"
    bad.write_bytes(b"not a plugin")
    plugins.append((bad.name, str(bad)))
    monkeypatch.setattr(m, "IN_FULL", False)
    monkeypatch.setattr(m, "cell_conflicts_interactive", lambda _args: True)
    writes = track_conflict_outputs(monkeypatch)
    assert m.build_compatibility_guard(args, plugins) == 2
    assert "cannot check incompatible plugins" in fold(capsys.readouterr().err)
    assert not writes


def test_interactive_build_guard_does_not_regenerate_auxiliary_data_when_no_choice_is_needed(tmp_path, monkeypatch):
    args, plugins = game(tmp_path)
    monkeypatch.setattr(m, "IN_FULL", False)
    monkeypatch.setattr(m, "cell_conflicts_interactive", lambda _args: True)
    writes = track_conflict_outputs(monkeypatch)
    assert m.build_compatibility_guard(args, plugins) == 0
    assert not writes


def test_direct_build_detects_incompatible_edits_inside_an_active_automerge(tmp_path, capsys):
    game(tmp_path, cells=10, people_land=80)
    data = tmp_path / "Data Files"
    (data / "People.esp").rename(data / m.AUTO_MERGE_NAME)
    m.write_load_order(str(tmp_path), ["Master.esm", "Mover.esp", m.AUTO_MERGE_NAME, "Aware.esp"])
    rc = m.main([str(data), "--fix", "--no-vortex", "--no-sounds", "--no-follow-up"])
    assert rc == 2
    assert "unmerge first" in fold(capsys.readouterr().err)


def test_interactive_build_guard_detects_incompatible_active_automerge(tmp_path, monkeypatch, capsys):
    args, plugins = game(tmp_path, cells=10, people_land=80)
    data = tmp_path / "Data Files"
    (data / "People.esp").rename(data / m.AUTO_MERGE_NAME)
    plugins = [(m.AUTO_MERGE_NAME, str(data / m.AUTO_MERGE_NAME)) if name == "People.esp" else (name, path)
               for name, path in plugins]
    m.write_load_order(str(tmp_path), [name for name, _path in plugins], "test")
    monkeypatch.setattr(m, "IN_FULL", False)
    monkeypatch.setattr(m, "cell_conflicts_interactive", lambda _args: True)
    monkeypatch.setattr(m, "conflict_choice", lambda *_args: "s")
    track_conflict_outputs(monkeypatch)
    assert m.build_compatibility_guard(args, plugins) == 2
    assert "unmerge" in fold(capsys.readouterr().out).lower()


def test_object_only_old_site_findings_warn_without_forcing_a_choice(tmp_path, monkeypatch, capsys):
    args, plugins = game(tmp_path)
    track_conflict_outputs(monkeypatch)
    assert m.run_cell_conflicts(args, plugins) == 0
    out = fold(capsys.readouterr().out)
    assert "old-site objects without evidence" in out
    assert "INCOMPATIBLE:" not in out


def test_underwater_terrain_patch_is_not_treated_as_old_island(tmp_path, monkeypatch, capsys):
    args, plugins = game(tmp_path, people_land=-100)
    track_conflict_outputs(monkeypatch)
    assert m.run_cell_conflicts(args, plugins) == 0
    assert "INCOMPATIBLE:" not in capsys.readouterr().out


def test_script_reusing_old_coordinates_requires_a_choice(tmp_path, monkeypatch, capsys):
    args, plugins = game(tmp_path, position_script=True)
    track_conflict_outputs(monkeypatch)
    assert m.run_cell_conflicts(args, plugins) == 2
    assert "script coordinates" in fold(capsys.readouterr().out)


def test_known_small_move_is_checked_even_without_enough_matched_cells(tmp_path, monkeypatch):
    args, plugins = game(tmp_path, cells=4, people_land=80)
    track_conflict_outputs(monkeypatch)
    assert m.run_cell_conflicts(args, plugins) == 0
    monkeypatch.setattr(A, "KNOWN_MOVES", {(2, 1): frozenset({"mover.esp"})})
    assert m.run_cell_conflicts(args, plugins) == 2


def test_moved_land_choice_disables_the_family_and_refreshes_output(tmp_path, monkeypatch, capsys):
    args, plugins = game(tmp_path, cells=10, people_land=80)
    writes = track_conflict_outputs(monkeypatch)
    args.no_interactive = False
    (tmp_path / m.RULES_FILE).write_text("[Order]\nMover.esp\nPeople.esp\n", encoding="cp1252")
    monkeypatch.setattr(m, "cell_conflicts_interactive", lambda _args: True)
    monkeypatch.setattr(m, "IN_FULL", True)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "3")
    assert m.run_cell_conflicts(args, plugins) == 0
    out = fold(capsys.readouterr().out)
    assert "one side must be turned off" in out
    assert "also set aside: Aware.esp" in out
    assert m.read_load_order(args) == ["Master.esm", "People.esp"]
    assert set(m.read_disabled(str(tmp_path))) == {"Mover.esp", "Aware.esp"}
    assert len(writes) == 4
    assert all([n.lower() for n in order] == ["master.esm", "people.esp"] for _name, order in writes)
