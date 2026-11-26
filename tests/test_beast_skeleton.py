"""Multipatch beast skeleton rule (approved by dej / dejunai, 2026-11-26): an NPC of a beast race (the winning
RACE record's RADT beast flag) with no model or a humanoid skeleton gets the beast skeleton in the Multipatch."""
import argparse
import struct

from conftest import m, sub, z, rec, plugin

import mwdialog_multipatch as MP


def game(tmp_path):
    df = tmp_path / "Data Files"
    df.mkdir(exist_ok=True)
    return df


def race(id_, beast):
    radt = bytearray(140)
    struct.pack_into("<I", radt, 136, 1 | (2 if beast else 0))
    return rec("RACE", sub("NAME", z(id_)) + sub("FNAM", z(id_.title())) + sub("RADT", bytes(radt)))


def npc(id_, race_id, model=None, female=False, flags=0):
    b = sub("NAME", z(id_))
    if model is not None:
        b += sub("MODL", z(model))
    b += sub("FNAM", z(id_)) + sub("RNAM", z(race_id)) + sub("CNAM", z("Commoner")) \
        + sub("FLAG", struct.pack("<I", 0x18 | (1 if female else 0)))
    return rec("NPC_", b, flags)


def modl(raw):
    d = dict(m.iter_subs(raw[16:]))
    return m.cstr(d["MODL"]) if "MODL" in d else None


def load(tmp_path, files):
    """files: [(name, [records])] in load order -> [(name, path)]."""
    out = []
    for name, recs in files:
        p = str(tmp_path / name)
        plugin(p, [] if name.endswith(".esm") else [("Morrowind.esm", 0)], recs)
        out.append((name, p))
    return out


BASE = ("Morrowind.esm", [race("Khajiit", True), race("Argonian", True), race("Dark Elf", False),
                          npc("vanilla_kha", "Khajiit", "base_animKnA.nif"),
                          npc("vanilla_dunmer", "Dark Elf")])


def fixes(tmp_path, *files, merged=None):
    return {f["id"].lower(): f for f in MP.beast_skeleton_fixes(load(tmp_path, [BASE, *files]), merged)}


def test_beast_race_without_model_gets_the_skeleton(tmp_path):
    got = fixes(tmp_path, ("MCA Addon.esp", [npc("_mca_thief_m", "Khajiit"), npc("_mca_thief_f", "Khajiit", female=True)]))
    assert set(got) == {"_mca_thief_m", "_mca_thief_f"}
    for f in got.values():                           # vanilla: the same file for women and men
        assert f["before"] is None and f["after"] == "base_animkna.nif" and f["plugin"] == "MCA Addon.esp"
        assert modl(f["record"]) == "base_animkna.nif"
    subs = [n for n, _d in m.iter_subs(got["_mca_thief_f"]["record"][16:])]
    assert subs[:2] == ["NAME", "MODL"] and subs.count("MODL") == 1
    assert "FLAG" in subs and "RNAM" in subs


def test_empty_model_counts_as_none(tmp_path):
    got = fixes(tmp_path, ("A.esp", [npc("e", "Argonian", "")]))
    assert got["e"]["after"] == "base_animkna.nif"


def test_beast_race_with_humanoid_skeleton_gets_it(tmp_path):
    got = fixes(tmp_path, ("A.esp", [npc("m", "Khajiit", "base_anim.nif"),
                                     npc("f", "Argonian", "Meshes\\Base_Anim_Female.NIF", female=True)]))
    assert got["m"]["before"] == "base_anim.nif" and got["f"]["before"] == "Meshes\\Base_Anim_Female.NIF"
    assert modl(got["m"]["record"]) == modl(got["f"]["record"]) == "base_animkna.nif"
    assert [n for n, _d in m.iter_subs(got["m"]["record"][16:])].count("MODL") == 1


def test_existing_beast_skeleton_untouched(tmp_path):
    got = fixes(tmp_path, ("A.esp", [npc("a", "Khajiit", "base_animkna.nif"),
                                     npc("b", "Argonian", "meshes/BASE_ANIMKNA.nif")]))
    assert got == {}                                  # vanilla_kha (base_animKnA.nif) too


def test_non_beast_race_untouched(tmp_path):
    got = fixes(tmp_path, ("A.esp", [npc("d1", "Dark Elf"), npc("d2", "Dark Elf", "base_anim.nif")]))
    assert got == {}


def test_mods_own_pose_model_untouched(tmp_path):
    got = fixes(tmp_path, ("AM.esp", [npc("slave", "Khajiit", "AM\\II\\SlaveSitting.nif"),
                                      npc("dead", "Argonian", "td\\anim_death2_m.nif")]))
    assert got == {}


def test_race_turned_beast_by_a_later_override_follows_the_winner(tmp_path):
    got = fixes(tmp_path, ("Races.esp", [race("Dark Elf", True)]), ("A.esp", [npc("d", "Dark Elf")]))
    assert set(got) == {"d", "vanilla_dunmer"}
    assert got["vanilla_dunmer"]["plugin"] == "Morrowind.esm"


def test_race_turned_non_beast_by_a_later_override_follows_the_winner(tmp_path):
    got = fixes(tmp_path, ("A.esp", [npc("k", "Khajiit")]), ("Races.esp", [race("Khajiit", False)]))
    assert got == {}


def test_deleted_race_is_not_beast(tmp_path):
    got = fixes(tmp_path, ("A.esp", [npc("k", "Khajiit")]), ("Del.esp", [race("Khajiit", True)[:12]
                                                                         + struct.pack("<I", 0x20)
                                                                         + race("Khajiit", True)[16:]]))
    assert got == {}


def test_mod_supplied_beast_skeleton_kept_and_used(tmp_path):
    own = "kd\\base_animkna_tail.nif"
    got = fixes(tmp_path, ("KD.esp", [race("Ohmes", True), npc("o1", "Ohmes", own), npc("o2", "Ohmes", own),
                                      npc("o3", "Ohmes"), npc("o4", "Ohmes", "base_anim.nif")]),
                ("Later.esp", [npc("o5", "Ohmes")]))
    assert set(got) == {"o3", "o4", "o5"}            # o1/o2 keep the mod's own beast skeleton
    assert got["o3"]["after"] == got["o4"]["after"] == own      # the NPC's own plugin's skeleton
    assert got["o5"]["after"] == own                 # Later.esp has none: the race's plugin's


def test_later_override_without_model_is_the_winner(tmp_path):
    got = fixes(tmp_path, ("Face.esp", [npc("vanilla_kha", "Khajiit")]))
    assert set(got) == {"vanilla_kha"} and got["vanilla_kha"]["plugin"] == "Face.esp"
    deleted = npc("vanilla_kha", "Khajiit", flags=0x20)
    assert fixes(tmp_path, ("Face.esp", [npc("vanilla_kha", "Khajiit")]), ("Del.esp", [deleted])) == {}


def test_the_multipatch_itself_is_not_read(tmp_path):
    got = fixes(tmp_path, ("A.esp", [npc("k", "Khajiit")]), (MP.MULTI_PATCH_NAME, [npc("k", "Khajiit", "base_animkna.nif")]))
    assert set(got) == {"k"}


def test_merged_record_is_the_one_patched(tmp_path):
    merged = npc("vanilla_kha", "Khajiit", "base_anim.nif", flags=0x400)
    got = fixes(tmp_path, ("A.esp", [npc("other", "Dark Elf")]), merged={"vanilla_kha": merged})
    f = got["vanilla_kha"]
    assert f["before"] == "base_anim.nif" and modl(f["record"]) == "base_animkna.nif"
    assert struct.unpack_from("<I", f["record"], 12)[0] == 0x400


def _run(tmp_path, monkeypatch, files, **extra):
    df = game(tmp_path)
    plugins = []
    for name, recs in [BASE] + files:
        p = df / name
        plugin(str(p), [] if name.endswith(".esm") else [("Morrowind.esm", 0)], recs)
        plugins.append((name, str(p)))
    w = m.World(m.Report())
    w.file_sizes = {}
    got = {}
    monkeypatch.setattr(m, "write_patch", lambda path, *a, extra=(), **k: got.setdefault("recs", list(extra)))
    monkeypatch.setattr(m, "next_free_date", lambda *a, **k: None)
    monkeypatch.setattr(m, "read_load_order", lambda *a, **k: [])
    monkeypatch.setattr(m, "merged_objects", lambda *a, **k: ([], []))
    args = argparse.Namespace(dry_run=False, data_dir=str(df), fix_log=str(tmp_path / "log.txt"),
                              no_merge_objects=True, ini=None, **extra)
    m.run_multipatch(args, plugins, w)
    return got.get("recs", []), (tmp_path / "log.txt")


def test_multipatch_writes_the_beast_skeleton(tmp_path, monkeypatch):
    recs, log = _run(tmp_path, monkeypatch, [("MCA Addon.esp", [npc("_mca_rogue_f", "Khajiit", female=True)])])
    npcs = [r for r in recs if r[:4] == b"NPC_"]
    assert len(npcs) == 1 and modl(npcs[0]) == "base_animkna.nif"
    assert "beast skeleton" in log.read_text(encoding="utf-8")


def test_no_beast_skeleton_switch(tmp_path, monkeypatch):
    recs, _log = _run(tmp_path, monkeypatch, [("MCA Addon.esp", [npc("_mca_rogue_f", "Khajiit")])],
                      no_beast_skeleton=True)
    assert not [r for r in recs if r[:4] == b"NPC_"]


def test_dry_run_lists_and_writes_nothing(tmp_path, monkeypatch, capsys):
    df = game(tmp_path)
    p = df / "MCA Addon.esp"
    plugin(str(df / "Morrowind.esm"), [], BASE[1])
    plugin(str(p), [("Morrowind.esm", 0)], [npc("_mca_rogue_f", "Khajiit")])
    monkeypatch.setattr(m, "write_patch", lambda *a, **k: (_ for _ in ()).throw(AssertionError("wrote")))
    monkeypatch.setattr(m, "merged_objects", lambda *a, **k: ([], []))
    args = argparse.Namespace(dry_run=True, data_dir=str(df), fix_log=str(tmp_path / "log.txt"),
                              no_merge_objects=True, ini=None)
    m.run_multipatch(args, [("Morrowind.esm", str(df / "Morrowind.esm")), ("MCA Addon.esp", str(p))],
                     m.World(m.Report()))
    out = capsys.readouterr().out
    assert "1 beast-race NPC(s)" in out and "_mca_rogue_f (khajiit) no model -> 'base_animkna.nif'" in out
    assert not (df / MP.MULTI_PATCH_NAME).exists()