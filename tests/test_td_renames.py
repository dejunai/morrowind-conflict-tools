"""Tamriel Data renames IDs between versions and ships the map (Docs\\Translation.txt, old:new). --fix rewrites
a mod's inventory and leveled-list entries to the current ID instead of dropping them, and a script's object gets
a copy of the current object under the old ID instead of a placeholder coin (compiled scripts keep the old name)."""
import struct

from conftest import lev, m, misc, plugin, rec, sub, z

OLD, NEW = "tr_a_chitin_helm_open", "T_De_Chitin_HelmOpen"


def install(tmp_path):
    df = tmp_path / "Morrowind" / "Data Files"
    docs = df / "Docs" / "tamriel_data"
    docs.mkdir(parents=True)
    lines = [f"tr_filler_{i}:T_Filler_{i}" for i in range(1200)] + [f"{OLD}:{NEW}"]
    (docs / "Translation.txt").write_text("\n".join(lines) + "\n", encoding="cp1252")
    td = df / "Tamriel_Data.esm"
    plugin(td, [], [misc(NEW, value=40, name="Chitin Helm"), misc("gold_001", name="Gold")])
    npco = lambda item: sub("NPCO", struct.pack("<i", 1) + item.encode().ljust(32, b"\0"))   # noqa: E731
    mod = df / "Mod.esp"
    plugin(mod, [("Tamriel_Data.esm", td.stat().st_size)], [rec("NPC_", sub("NAME", z("npc_trader")) + npco(OLD) + npco("nothing_here")),
                                       rec("LEVI", lev([OLD, "nothing_here"]))])
    w = m.World(m.Report())
    w.file_sizes = {}
    w.args_data_dir = str(df)
    for path in (td, mod):
        w.load_plugin(str(path), path.name)
    w.plugin_paths = [str(td), str(mod)]
    return w


def test_a_renamed_inventory_item_and_list_entry_are_renamed_not_dropped(tmp_path):
    w = install(tmp_path)
    assert w.td_rename(OLD) == NEW
    assert w.td_rename("nothing_here") is None
    w._check_item_refs()
    w._check_leveled()
    npc = next(f for f in w.item_fixes if f["tag"] == "NPC_")
    assert npc["rename"] == {OLD: NEW} and npc["npco"] == {"nothing_here"}
    levi = next(f for f in w.item_fixes if f["tag"] == "LEVI")
    assert levi["rename"] == {OLD: NEW} and levi["lev_drop"] == {"nothing_here"}

    body = sub("NAME", z("npc_trader")) + sub("NPCO", struct.pack("<i", 1) + OLD.encode().ljust(32, b"\0")) \
        + sub("NPCO", struct.pack("<i", 1) + b"nothing_here".ljust(32, b"\0"))
    items = [m.cstr(d[4:36]) for n, d in m.iter_subs(m.fix_item_body(body, npc)) if n == "NPCO"]
    assert items == [NEW]
    entries = dict(m.iter_subs(m.fix_item_body(lev([OLD, "nothing_here"]), levi)))
    names = [m.cstr(d) for n, d in m.iter_subs(m.fix_item_body(lev([OLD, "nothing_here"]), levi)) if n == "INAM"]
    assert names == [NEW] and struct.unpack("<I", entries["INDX"])[0] == 1


def test_a_script_object_gets_a_copy_of_its_renamed_object_not_a_coin(tmp_path):
    w = install(tmp_path)
    copy = m.renamed_copy(w, OLD)
    assert copy[:4] == b"MISC"
    subs = dict(m.iter_subs(copy[16:]))
    assert m.cstr(subs["NAME"]) == OLD                       # the name the compiled script uses
    assert m.cstr(subs["FNAM"]) == "Chitin Helm"            # the current object's data, not a placeholder coin
    assert m.renamed_copy(w, "nothing_here") is None


def test_no_map_is_no_renames(tmp_path):
    w = install(tmp_path)
    (tmp_path / "Morrowind" / "Data Files" / "Docs" / "tamriel_data" / "Translation.txt").write_text("hello\n")
    w._td_renames = None
    assert w.td_rename(OLD) is None
