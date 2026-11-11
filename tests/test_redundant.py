"""--redundant: plugins doing the same job as another. Exact duplicates (nothing of theirs would be missed),
two versions of one mod (a choice), and the reversible turning off (record, undo, release, --add-all-esp)."""
import builtins
import os
import struct
import sys

from conftest import m, sub, z, rec, misc

MW = [("Morrowind.esm", 0)]


def write(df, name, records, masters=MW, desc=""):
    path = os.path.join(df, name)
    hedr = struct.pack("<fI", 1.3, 0) + b"me".ljust(32, b"\0") + desc.encode().ljust(256, b"\0") \
        + struct.pack("<I", len(records))
    head = sub("HEDR", hedr) + b"".join(sub("MAST", z(n)) + sub("DATA", struct.pack("<Q", s)) for n, s in masters)
    with open(path, "wb") as f:
        f.write(rec("TES3", head) + b"".join(records))
    return path


def game(tmp_path, spec):
    """spec: [(name, records, masters, desc)] in load order. Returns (data dir, {lower name: path})."""
    df = tmp_path / "Data Files"
    df.mkdir()
    paths = {}
    for i, (name, records, masters, desc) in enumerate(spec):
        p = write(str(df), name, records, masters, desc)
        os.utime(p, (1_000_000 + i * 100, 1_000_000 + i * 100))
        paths[name.lower()] = p
    m.write_load_order(str(tmp_path), [n for n, *_r in spec])
    (tmp_path / "Morrowind.ini").write_text("[Game Files]\n", encoding="cp1252")
    return str(df), paths


def order(tmp_path):
    return [l.strip() for l in open(tmp_path / m.LOAD_ORDER_FILE, encoding="utf-8")
            if l.strip() and not l.startswith(";")]


def find(df, names, **kw):
    plugins = [(n, os.path.join(df, n)) for n in names]
    return m.find_redundant(plugins, **kw)


BASE = ("Morrowind.esm", [misc("a", 1), misc("b", 1), misc("c", 1)], [], "")


def test_itm_only_plugin_is_redundant(tmp_path):
    df, _p = game(tmp_path, [BASE, ("Mod.esp", [misc("x", 5)], MW, ""),
                             ("Itm.esp", [misc("a", 1), misc("x", 5)], MW, "")])
    r = find(df, ["Morrowind.esm", "Mod.esp", "Itm.esp"])
    assert [(e["plugin"], e["confidence"], e["itm"]) for e in r["exact"]] == [("itm.esp", "high", 2)]


def test_copy_contained_in_a_later_plugin(tmp_path):
    """Everything Small.esp changes, Big.esp (later) changes the same way: Small does nothing Big doesn't."""
    df, _p = game(tmp_path, [BASE, ("Small.esp", [misc("a", 7), misc("n1", 2)], MW, ""),
                             ("Big.esp", [misc("a", 7), misc("n1", 2), misc("b", 9)], MW, "")])
    r = find(df, ["Morrowind.esm", "Small.esp", "Big.esp"])
    assert [(e["plugin"], e["keep"], e["confidence"]) for e in r["exact"]] == [("small.esp", "big.esp", "high")]


def test_unique_record_or_unique_conflict_is_not_redundant(tmp_path):
    """A plugin with its own version of a record - even one a later plugin overrides - adds a conflict of its
    own (and a Multipatch input): never flagged."""
    df, _p = game(tmp_path, [BASE, ("Own.esp", [misc("a", 7), misc("b", 3)], MW, ""),
                             ("Later.esp", [misc("a", 7), misc("b", 4)], MW, "")])
    r = find(df, ["Morrowind.esm", "Own.esp", "Later.esp"])
    assert r["exact"] == []


def test_removing_must_not_change_a_winner(tmp_path):
    """A(7) B(8) P(7): P's copy is identical to A's, but without P B's 8 would win."""
    df, _p = game(tmp_path, [BASE, ("A.esp", [misc("a", 7)], MW, ""), ("B.esp", [misc("a", 8)], MW, ""),
                             ("P.esp", [misc("a", 7)], MW, "")])
    r = find(df, ["Morrowind.esm", "A.esp", "B.esp", "P.esp"])
    assert "p.esp" not in [e["plugin"] for e in r["exact"]]


def test_two_copies_of_each_other_only_one_goes(tmp_path):
    """The later copy is ITM (identical to the earlier one's version): it goes, the original stays."""
    df, _p = game(tmp_path, [BASE, ("Copy1.esp", [misc("w", 3)], MW, ""), ("Copy2.esp", [misc("w", 3)], MW, "")])
    r = find(df, ["Morrowind.esm", "Copy1.esp", "Copy2.esp"])
    assert [(e["plugin"], e["keep"]) for e in r["exact"]] == [("copy2.esp", "copy1.esp")]   # the ITM copy


def test_chain_of_add_ons_found_one_at_a_time(tmp_path):
    """The Khajiit case: BEAST, CIV (alternative versions), BEAST X / CIV X (subsets of each). Both X files go;
    without either, every record's winner is the same as now."""
    npcs = [misc(f"npc{i}", 5) for i in range(6)]
    beast = [misc("r1", 1), misc("r2", 1), misc("tail", 1)]
    civ = [misc("r1", 2), misc("r2", 2)]
    df, _p = game(tmp_path, [BASE, ("Khajiit Div(BEAST).esp", beast + npcs, MW, "four races. beast feet"),
                             ("Khajiit Div(CIV).esp", civ + npcs, MW, "four races. civilized feet"),
                             ("Khajiit Div(BEAST)X.esp", beast, MW, "four races"), ("Khajiit Div(CIV)X.esp", civ, MW, "four races")])
    names = ["Morrowind.esm", "Khajiit Div(BEAST).esp", "Khajiit Div(CIV).esp", "Khajiit Div(BEAST)X.esp", "Khajiit Div(CIV)X.esp"]
    r = find(df, names)
    assert sorted(e["plugin"] for e in r["exact"]) == ["khajiit div(beast)x.esp", "khajiit div(civ)x.esp"]
    # the real pair's descriptions differ in the variant's own sentence; CIV adds nothing BEAST doesn't define
    # first - still two versions, not a patch (no patch word in its name)
    assert [(v["a"], v["b"]) for v in r["variant"]] == [("khajiit div(beast).esp", "khajiit div(civ).esp")]


def test_masters_and_lua_named_are_never_candidates(tmp_path):
    df, _p = game(tmp_path, [BASE, ("Itm.esp", [misc("a", 1)], MW, ""),
                             ("Patch.esp", [misc("q", 1)], MW + [("Itm.esp", 0)], ""),
                             ("Itm2.esp", [misc("b", 1)], MW, "")])
    r = find(df, ["Morrowind.esm", "Itm.esp", "Patch.esp", "Itm2.esp"], lua={"itm2.esp"})
    assert r["exact"] == []


def test_patch_is_not_a_variant_of_its_master(tmp_path):
    recs = [misc(f"i{i}", 1) for i in range(8)]
    df, _p = game(tmp_path, [BASE, ("Mod.esp", recs, MW, "same"),
                             ("Mod Patch.esp", recs[:6] + [misc("i7", 2)], MW + [("Mod.esp", 0)], "same")])
    r = find(df, ["Morrowind.esm", "Mod.esp", "Mod Patch.esp"])
    assert r["variant"] == []


def test_keep_both_is_remembered(tmp_path):
    df, _p = game(tmp_path, [BASE, ("Copy1.esp", [misc("w", 3)], MW, ""), ("Copy2.esp", [misc("w", 3)], MW, "")])
    r = find(df, ["Morrowind.esm", "Copy1.esp", "Copy2.esp"], keep_both={frozenset(("copy1.esp", "copy2.esp"))})
    assert r["exact"] == []


def run(tmp_path, *extra):
    return m.main([str(tmp_path / "Data Files"), "--no-vortex", "--fix-log", str(tmp_path / "fix.log")] + list(extra))


SPEC = [BASE, ("Small.esp", [misc("a", 7)], MW, ""), ("Big.esp", [misc("a", 7), misc("b", 9)], MW, "")]


def test_report_only_changes_nothing(tmp_path, capsys):
    game(tmp_path, SPEC)
    before = order(tmp_path)
    run(tmp_path, "--redundant", "--no-interactive")
    out = capsys.readouterr().out
    assert "Small.esp  ->  turn off, keep Big.esp" in out and "shared records: 1" in out
    assert order(tmp_path) == before and not (tmp_path / m.REDUNDANT_RECORD).exists()


def test_auto_turns_off_and_undo_restores(tmp_path, capsys):
    game(tmp_path, SPEC)
    run(tmp_path, "--redundant-auto", "--no-interactive")
    assert order(tmp_path) == ["Morrowind.esm", "Big.esp"]
    off, _both = m.read_redundant(str(tmp_path))
    assert list(off) == ["Small.esp"] and off["Small.esp"][0] == "Big.esp"
    run(tmp_path, "--add-all-esp")                            # stays out
    assert "Small.esp" not in order(tmp_path)
    run(tmp_path, "--redundant-undo")
    assert order(tmp_path) == ["Morrowind.esm", "Small.esp", "Big.esp"]
    assert not (tmp_path / m.REDUNDANT_RECORD).exists()


def test_dry_run_turns_nothing_off(tmp_path):
    game(tmp_path, SPEC)
    run(tmp_path, "--redundant-auto", "--no-interactive", "--dry-run")
    assert order(tmp_path) == ["Morrowind.esm", "Small.esp", "Big.esp"]


def test_comes_back_when_the_kept_plugin_is_gone(tmp_path):
    df, paths = game(tmp_path, SPEC)
    run(tmp_path, "--redundant-auto", "--no-interactive")
    os.remove(paths["big.esp"])
    run(tmp_path, "--redundant", "--no-interactive")
    assert "Small.esp" in order(tmp_path)
    assert m.read_redundant(str(tmp_path))[0] == {}


def test_interactive_choice_between_versions(tmp_path, monkeypatch, capsys):
    recs = [misc(f"i{i}", 1) for i in range(8)]
    game(tmp_path, [BASE, ("Mod - A.esp", recs, MW, "adds things"),
                    ("Mod - B.esp", recs[:7] + [misc("i7", 2)], MW, "adds things")])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    answers = iter(["b"])
    monkeypatch.setattr(builtins, "input", lambda _p="": next(answers))
    run(tmp_path, "--redundant")
    out = capsys.readouterr().out
    assert "[choice] Mod - A.esp  vs  Mod - B.esp" in out and "identical: 7; different: 1" in out
    assert order(tmp_path) == ["Morrowind.esm", "Mod - B.esp"]
    assert m.read_redundant(str(tmp_path))[0]["Mod - A.esp"][0] == "Mod - B.esp"


def test_interactive_keep_both_not_asked_again(tmp_path, monkeypatch, capsys):
    game(tmp_path, SPEC)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    asked = []
    monkeypatch.setattr(builtins, "input", lambda p="": asked.append(p) or "k")
    run(tmp_path, "--redundant")
    assert len(asked) == 1 and order(tmp_path) == ["Morrowind.esm", "Small.esp", "Big.esp"]
    run(tmp_path, "--redundant")
    assert len(asked) == 1
    assert "None found" in capsys.readouterr().out


def test_auto_never_turns_off_a_version_choice(tmp_path):
    recs = [misc(f"i{i}", 1) for i in range(8)]
    game(tmp_path, [BASE, ("Mod - A.esp", recs, MW, "adds things"),
                    ("Mod - B.esp", recs[:7] + [misc("i7", 2)], MW, "adds things")])
    run(tmp_path, "--redundant-auto", "--no-interactive")
    assert order(tmp_path) == ["Morrowind.esm", "Mod - A.esp", "Mod - B.esp"]


def test_patch_without_master_is_not_a_version(tmp_path):
    """Djangos Dialogue - Patch for Purists: no MAST, but only changes the main mod's records (nothing new) and
    has its own description: a patch on top, not another version to choose between."""
    recs = [misc(f"i{i}", 1) for i in range(8)]
    df, _p = game(tmp_path, [BASE, ("Djangos.esp", recs, MW, "1.44"),
                             ("Djangos - Patch.esp", recs[:6] + [misc("i7", 2)], MW, "(generated)")])
    r = find(df, ["Morrowind.esm", "Djangos.esp", "Djangos - Patch.esp"])
    assert r["variant"] == []


def test_lua_names_in_settings_or_turned_off_mods_dont_count(tmp_path):
    df = tmp_path / "Data Files"
    for rel, text in (("MWSE/config/cache.json", '{"A.esp": true}'), ("MWSE/off/mods/x/main.lua", 'q("B.esp")'),
                      ("MWSE/mods/y/main.lua", 'tes3.isModActive("C.esp")')):
        f = df / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    assert m.lua_required_plugins(str(df)) == {"c.esp"}


def cell(name, ref_id):
    return rec("CELL", sub("NAME", z(name)) + sub("DATA", struct.pack("<iii", 1, 0, 0))
               + sub("FRMR", struct.pack("<I", 1)) + sub("NAME", z(ref_id)))


def test_two_halves_with_their_own_cells_are_not_versions(tmp_path):
    """Danae's Edits: TR and Vv define the same NPCs, each placing them in its own cells (mainland vs
    Vvardenfell). Not alternatives."""
    objs = [misc(f"am_npc{i}", 1) for i in range(10)]
    df, _p = game(tmp_path, [BASE, ("Animated - Edits - TR.esp", objs + [cell(f"Mainland {i}", "am_npc1") for i in range(6)],
                                    MW, "same mod"),
                             ("Animated - Edits - Vv.esp", objs + [cell(f"Vvardenfell {i}", "am_npc1") for i in range(6)],
                              MW, "same mod")])
    r = find(df, ["Morrowind.esm", "Animated - Edits - TR.esp", "Animated - Edits - Vv.esp"])
    assert r["variant"] == []


def test_added_master_is_a_soft_dependency(tmp_path):
    """FMI_HulStop lists Danae's Vv only because --sort added it (a content rule); no reference uses it. With
    the link soft, Vv is judged on its content alone (here: a pure ITM copy, so redundant)."""
    df, _p = game(tmp_path, [BASE, ("Danae Vv.esp", [misc("a", 1)], MW, ""),
                             ("HulStop.esp", [misc("hul", 1)], MW + [("Danae Vv.esp", 0)], "")])
    names = ["Morrowind.esm", "Danae Vv.esp", "HulStop.esp"]
    assert find(df, names)["exact"] == []
    r = find(df, names, soft_masters={("hulstop.esp", "danae vv.esp")})
    assert [e["plugin"] for e in r["exact"]] == ["danae vv.esp"]
    assert not m.added_master_in_use(os.path.join(df, "HulStop.esp"), "Danae Vv.esp")


def test_added_master_used_by_a_reference_stays_hard(tmp_path):
    df, _p = game(tmp_path, [BASE, ("Mod.esp", [misc("a", 1)], MW, ""),
                             ("Patch.esp", [rec("CELL", sub("NAME", z("X")) + sub("DATA", struct.pack("<iii", 1, 0, 0))
                                                + sub("FRMR", struct.pack("<I", (2 << 24) | 5)) + sub("NAME", z("a")))],
                              MW + [("Mod.esp", 0)], "")])
    assert m.added_master_in_use(os.path.join(df, "Patch.esp"), "Mod.esp")


def test_auto_turning_off_a_soft_master_takes_it_out_of_the_patch(tmp_path):
    import json
    df, paths = game(tmp_path, [BASE, ("Danae Vv.esp", [misc("a", 1)], MW, ""),
                                ("HulStop.esp", [misc("hul", 1)], MW + [("Danae Vv.esp", 0)], "")])
    (tmp_path / m.ADDED_MASTERS_RECORD).write_text(json.dumps({"HulStop.esp": {"Danae Vv.esp": "2026-11-07; why: content"}}))
    run(tmp_path, "--redundant-auto", "--no-interactive")
    assert order(tmp_path) == ["Morrowind.esm", "HulStop.esp"]
    assert m.read_header_masters(paths["hulstop.esp"]) == ["Morrowind.esm"]
    assert m.read_added_masters(str(tmp_path)) == {}
