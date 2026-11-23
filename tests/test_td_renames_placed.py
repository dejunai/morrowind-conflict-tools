"""--fix renames what plugins place under old Tamriel Data IDs, before the 64-unit match and before anything is removed.
Whole --fix runs: the map in tools (stood in for by tmp_path), the plugins, and what is on disk afterwards."""
import os
import struct

import pytest

from conftest import SRC, m, misc, plugin, rec, records_of, sub, z

TD = "Tamriel_Data.esm"
MAP = {
    "tr_crate": "T_Crate",
    "tr_sword_brk": "T_Sword_Broke",            # two steps: the middle name is gone as well
    "T_Sword_Broke": "T_Broken_01",
    "tr_still_made": "T_Crate",                 # old, but another mod still defines it
    "tr_unshipped": "T_Not_Here",               # the new name is not in this load order
    "tr_loop_a": "tr_loop_b",
    "tr_loop_b": "tr_loop_a",
    "tr_gate": "T_Gate",
}
NEW = ("T_Crate", "T_Broken_01", "T_Gate")


def ref(v, name, x=0.0, deleted=False):
    out = sub("FRMR", struct.pack("<I", v)) + sub("NAME", z(name))
    if deleted:
        out += sub("DELE", b"\0\0\0\0")
    return out + sub("DATA", struct.pack("<6f", x, 0, 0, 0, 0, 0))


def cell(name, persistent=b"", temporary=(), refs_in_temp=0):
    body = sub("NAME", z(name)) + sub("DATA", struct.pack("<Iif", 1, 0, 0.0)) + persistent
    if temporary:
        body += sub("NAM0", struct.pack("<I", refs_in_temp)) + temporary
    return rec("CELL", body)


def edit(v):
    return (1 << 24) | v                        # a reference of the plugin's first master


def placed(path, name="Town"):
    """{FRMR: (object, temporary?)} and NAM0 of a plugin's cell."""
    out, nam0, v = {}, 0, None
    for _o, tag, _f, body in records_of(path):
        if tag != "CELL" or m.cstr(m.first_sub(body, b"NAME")) != name:
            continue
        temp = False
        for n, d in m.iter_subs(body):
            if n == "NAM0":
                temp, nam0, v = True, struct.unpack("<I", d)[0], None
            elif n == "FRMR":
                v = struct.unpack("<I", d)[0]
            elif n == "NAME" and v is not None:
                out[v], v = (m.cstr(d), temp), None
    return out, nam0


def placed_fields(path, name="Town"):
    for _o, tag, _f, body in records_of(path):
        if tag == "CELL" and m.cstr(m.first_sub(body, b"NAME")) == name:
            return {n: m.cstr(d) for n, d in m.iter_subs(body)
                    if n in {"ANAM", "CNAM", "KNAM", "TNAM", "XSOL"}}
    return {}


@pytest.fixture
def game(tmp_path):
    df = tmp_path / "Morrowind" / "Data Files"
    df.mkdir(parents=True)
    (tmp_path / "Morrowind" / "Morrowind.ini").write_text("[Game Files]\n")
    lines = [f"tr_filler_{i}:T_Filler_{i}" for i in range(1200)] + [f"{a}:{b}" for a, b in MAP.items()]
    (tmp_path / "Translation.txt").write_text("\n".join(lines) + "\n", encoding="cp1252")

    def build(mod, master_refs=b"", others=(), town="Town"):
        td = df / TD
        plugin(td, [], [misc("gold_001", name="Gold")] + [misc(n, name=n) for n in NEW] + [cell(town, master_refs)])
        names = [TD]
        for name, records in others:
            plugin(df / name, [(TD, os.path.getsize(td))], records)
            names.append(name)
        plugin(df / "Mod.esp", [(TD, os.path.getsize(td))], mod)
        return df, names + ["Mod.esp"]

    return build


def fix(df, names):
    return m.main([str(df), "--plugins", *names, "--no-vortex", "--no-archive-lookup", "--no-interactive",
                   "--fix", "--yes", "--fix-log", str(df.parent / "fixes.log")])


def test_cell_fixes_deletion_gets_a_hidden_script_target(tmp_path, monkeypatch, capsys):
    df = tmp_path / "Data Files"
    df.mkdir()
    (tmp_path / "Morrowind.ini").write_text("[Game Files]\n")
    script = rec("SCPT", sub("SCHD", b"plank_script".ljust(32, b"\0") + b"\0" * 20)
                 + sub("SCTX", b'begin plank_script\n"quest_plank"->Disable\nend\n'))
    base = plugin(df / "Morrowind.esm", [],
                  [misc("gold_001"), misc("quest_plank"), script, cell("Town", ref(1, "quest_plank"))])
    plugin(df / "Mod.esp", [("Morrowind.esm", len(base))], [misc("own")])

    def build_cell_fixes(args, plugins, report=None):
        plugin(df / m.CELL_WINNER_PATCH, [("Morrowind.esm", len(base))],
               [cell("Town", ref(edit(1), "quest_plank", deleted=True))])

    monkeypatch.setattr(m, "fix_cell_winners", build_cell_fixes)
    names = ["Morrowind.esm", "Mod.esp"]
    for _ in range(2):
        fix(df, names)
        refs, _nam0 = placed(df / m.PLACE_PATCH_NAME, m.PLACEHOLDER_CELL)
        assert list(refs.values()) == [("quest_plank", False)]
        assert (df / "Morrowind.esm").read_bytes() == base
        assert any(m.has_sub(body, b"DELE") for _o, t, _f, body in records_of(df / m.CELL_WINNER_PATCH)
                   if t == "CELL")
    out = capsys.readouterr().out
    assert "deleted the last placed copy" in out
    world = m.World(m.Report())
    world.file_sizes = {n.lower(): os.path.getsize(df / n) for n in names}
    for n in names + [m.CELL_WINNER_PATCH, m.PLACE_PATCH_NAME]:
        world.load_plugin(str(df / n), n)
    world._check_placed()
    assert world.placed["quest_plank"] == 1
    assert not world.unplaced


def test_the_map_is_read_from_tools(game):
    game([misc("own")])
    assert m.read_td_renames()["tr_crate"] == "T_Crate"


def test_its_place_is_tools_translation_txt():
    with open(os.path.join(SRC, "mwdialog_patchfile.py"), encoding="utf-8") as f:
        assert 'os.path.dirname(os.path.abspath(__file__)), "tools", "Translation.txt")' in f.read()


def test_placed_objects_are_renamed_and_only_those_that_may_be(game):
    persistent = ref(1, "tr_crate") + ref(2, "tr_still_made")
    temporary = ref(3, "tr_sword_brk") + ref(4, "tr_unshipped") + ref(5, "tr_loop_a")
    df, names = game([cell("Town", persistent, temporary, 3)],
                     others=[("Older.esp", [misc("tr_still_made")])])
    master = (df / TD).read_bytes()
    fix(df, names)
    refs, nam0 = placed(df / "Mod.esp")
    assert refs == {1: ("T_Crate", False),                    # renamed
                    2: ("tr_still_made", False),              # still defined: left alone
                    3: ("T_Broken_01", True)}                 # both steps followed
    assert nam0 == 1                                          # only the two with nothing to become were removed
    assert (df / TD).read_bytes() == master


def test_reference_owner_key_trap_and_soul_are_renamed(game):
    fields = b"".join(sub(name, z("tr_crate")) for name in ("ANAM", "CNAM", "KNAM", "TNAM", "XSOL"))
    df, names = game([cell("Town", ref(1, "gold_001") + fields)])
    master = (df / TD).read_bytes()
    fix(df, names)
    assert placed_fields(df / "Mod.esp") == {
        name: "T_Crate" for name in ("ANAM", "CNAM", "KNAM", "TNAM", "XSOL")}
    assert (df / TD).read_bytes() == master


def test_the_64_unit_match_accepts_the_new_name(game):
    master = ref(2, "T_Crate", 1000) + ref(3, "T_Gate", 5000) + ref(4, "T_Broken_01", 9000)
    mine = (ref(edit(9), "tr_crate", 1030)                    # renumbered and renamed
            + ref(edit(3), "tr_gate", 5000)                   # the same reference, renamed
            + ref(edit(8), "tr_sword_brk", 9900))             # renamed, but nothing within 64 units
    df, names = game([cell("Town", mine)], master)
    fix(df, names)
    assert placed(df / "Mod.esp")[0] == {edit(2): ("T_Crate", False), edit(3): ("T_Gate", False)}


def test_two_candidates_in_range_are_not_guessed_between(game):
    master = ref(2, "T_Crate", 1000) + ref(3, "T_Crate", 1020)
    df, names = game([cell("Town", ref(edit(9), "tr_crate", 1010))], master)
    fix(df, names)
    assert placed(df / "Mod.esp")[0] == {}


def test_a_renamed_interior_is_found_through_renamed_objects(game):
    df, names = game([cell("Old Town", ref(edit(2), "tr_crate", 1000) + ref(edit(3), "tr_gate", 5000))],
                     ref(2, "T_Crate", 1000) + ref(3, "T_Gate", 5000))
    fix(df, names)
    assert placed(df / "Mod.esp")[0] == {edit(2): ("T_Crate", False), edit(3): ("T_Gate", False)}


def test_a_deleted_reference_is_left_deleted(game):
    df, names = game([cell("Town", ref(edit(2), "tr_crate", 1000, deleted=True))], ref(2, "T_Crate", 1000))
    before = placed(df / "Mod.esp")
    fix(df, names)
    assert placed(df / "Mod.esp") == before


def test_a_script_that_acts_on_the_old_name_keeps_its_object(game):
    text = b'Begin gate_script\r\n"tr_gate"->Disable\r\nEnd\r\n'
    script = rec("SCPT", sub("SCHD", b"gate_script".ljust(32, b"\0") + struct.pack("<5I", 0, 0, 0, 0, 0))
                 + sub("SCTX", text))
    df, names = game([script, cell("Town", ref(1, "tr_gate"))])
    fix(df, names)
    assert placed(df / "Mod.esp")[0] == {1: ("tr_gate", False)}       # compiled scripts find it by this name
    patch = records_of(df / m.PATCH_NAME)
    copy = [b for _o, t, _f, b in patch if t == "MISC" and m.cstr(m.first_sub(b, b"NAME")) == "tr_gate"]
    assert len(copy) == 1 and m.cstr(m.first_sub(copy[0], b"FNAM")) == "T_Gate"
    assert not (df / m.PLACE_PATCH_NAME).exists()                     # so no hidden stand-in is needed
    fix(df, names)                                                    # and the next run doesn't undo that
    assert placed(df / "Mod.esp")[0] == {1: ("tr_gate", False)}
    assert any(t == "MISC" and m.cstr(m.first_sub(b, b"NAME")) == "tr_gate" for _o, t, _f, b in records_of(df / m.PATCH_NAME))


def test_a_second_run_changes_nothing(game):
    df, names = game([cell("Town", ref(1, "tr_crate") + ref(edit(9), "tr_gate", 5010))], ref(3, "T_Gate", 5000))
    fix(df, names)
    once = (df / "Mod.esp").read_bytes()
    fix(df, names)
    assert (df / "Mod.esp").read_bytes() == once


def test_old_names_are_not_taken_for_another_mods_master(game):
    npc = rec("NPC_", sub("NAME", z("trader")) + b"".join(
        sub("NPCO", struct.pack("<i", 1) + old.encode().ljust(32, b"\0")) for old in ("tr_crate", "tr_gate", "tr_sword_brk")))
    df, names = game([npc, cell("Town", ref(edit(9), "tr_crate", 1030))], ref(2, "T_Crate", 1000))
    fix(df, names)
    items = [m.cstr(d[4:36]) for _o, t, _f, b in records_of(df / "Mod.esp") if t == "NPC_"
             for n, d in m.iter_subs(b) if n == "NPCO"]
    assert items == ["T_Crate", "T_Gate", "T_Broken_01"]
    assert placed(df / "Mod.esp")[0] == {edit(2): ("T_Crate", False)}


def test_the_mods_own_docs_are_not_searched(game, tmp_path):
    df, names = game([cell("Town", ref(1, "tr_crate"))])
    (df / "Docs").mkdir()
    os.replace(tmp_path / "Translation.txt", df / "Docs" / "Tamriel Data (HD) - Translation.txt")
    assert m.read_td_renames() == {}
    fix(df, names)
    assert placed(df / "Mod.esp")[0] == {}


@pytest.mark.parametrize("state", ["none", "empty", "junk", "unreadable"])
def test_without_a_usable_map_fix_carries_on_without_error(game, capsys, tmp_path, state):
    df, names = game([misc("own"), cell("Town", ref(1, "T_Crate"))])
    path = tmp_path / "Translation.txt"
    path.unlink()
    if state == "empty":
        path.write_bytes(b"")
    elif state == "junk":
        path.write_bytes(bytes(range(256)) * 50)
    elif state == "unreadable":
        path.mkdir()                                # opening it fails, as a locked file does
    assert m.read_td_renames() == {}
    before = (df / "Mod.esp").read_bytes()
    assert fix(df, names) == 0
    out = capsys.readouterr()
    assert "translation" not in (out.out + out.err).lower() and "Traceback" not in out.out + out.err
    assert (df / "Mod.esp").read_bytes() == before


def test_without_a_map_a_plugin_with_old_names_is_handled_as_before(game, tmp_path):
    df, names = game([cell("Town", ref(1, "tr_crate") + ref(2, "T_Gate"))])
    (tmp_path / "Translation.txt").unlink()
    fix(df, names)
    assert placed(df / "Mod.esp")[0] == {2: ("T_Gate", False)}
