"""Paths too long for Windows: moved to <top>\\lp\\<name>_<hash>.<ext>; .esp records edited, .esm records
corrected through the ESM patch, loose models' texture names rewritten; undo; no second shortening."""
import json
import os
import struct

import pytest

from conftest import m, rec, sub, tes3, z
from test_cache import _bsa, nif

lp = m.longpaths_module()
LONGDIR = "averyveryverylongfoldername_of_a_mod_that_likes_long_names"


def dds():
    head = (b"DDS " + struct.pack("<7I", 124, 0x1007, 32, 32, 512, 0, 1) + b"\0" * 44
            + struct.pack("<2I", 32, 4) + b"DXT1" + b"\0" * 40)
    return head + bytes(512)


def misc(id_, model, icon=None):
    b = sub("NAME", z(id_)) + sub("MODL", z(model)) + sub("FNAM", z("Thing"))
    b += sub("MCDT", struct.pack("<fii", 1.0, 1, 0))
    if icon:
        b += sub("ITEX", z(icon))
    return rec("MISC", b)


def put(base, rel, data):
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


@pytest.fixture
def game(tmp_path, monkeypatch):
    g = tmp_path / "Morrowind"
    df = g / "Data Files"
    df.mkdir(parents=True)
    (g / "Morrowind.ini").write_text("[Game Files]\n")
    # a small limit, so test paths count as "too long": Data Files + 70 characters
    monkeypatch.setattr(lp, "MAX_PATH_CHARS", len(str(df)) + 1 + 70)
    monkeypatch.setattr(lp, "NEAR_CHARS", len(str(df)) + 1 + 60)
    return g, df


def fix(df, plugins, *extra):
    return m.main([str(df), "--plugins", *plugins, "--asset-check", "--fix", "--yes", "--no-vortex",
                   "--fix-log", str(df.parent / "fix.log")] + list(extra))


def field(path, tag, id_, sname):
    data = open(path, "rb").read()
    for _o, t, _f, body in m.iter_records(data):
        if t == tag and m.cstr(m.first_sub(body, b"NAME")).lower() == id_.lower():
            v = m.first_sub(body, sname.encode())
            return m.cstr(v) if v is not None else None
    return None


def long_model():
    return f"{LONGDIR}\\sub\\thing.nif"


def test_short_names_are_deterministic_unique_and_keep_top_and_extension():
    rel = f"Meshes\\{LONGDIR}\\a fancy  model (v2).nif"
    a = lp.short_rel(rel, set())
    assert a == lp.short_rel(rel, set())                                # same file, same name
    assert a.startswith("Meshes\\lp\\a_fancy__model") and a.endswith(".nif") and len(a) <= 40
    b = lp.short_rel(f"Meshes\\other\\{LONGDIR}\\a fancy  model (v2).nif", set())
    assert a != b                                                       # same name, other folder: other hash
    c = lp.short_rel(rel, {a.lower()})                                  # taken by another file: longer hash
    assert c != a and c.startswith(a[:-4]) and len(c) == len(a) + 4
    assert lp.short_rel(rel, {a.lower()}, {a.lower()}) == a             # ...unless it is this file's own
    snd = lp.short_rel(f"Sound\\{LONGDIR}\\a_long_sound_file_name.wav", set())
    assert len(lp.under_top(snd)) <= 31                                 # fits a sound record's 32-byte field


def test_esp_field_edited_esm_overridden_in_the_patch(game):
    g, df = game
    put(df, f"Meshes/{LONGDIR}/sub/thing.nif", nif("tx_ok.dds"))
    put(df, "Textures/tx_ok.dds", dds())
    put(df, "Meshes/ok.nif", nif("tx_ok.dds"))
    esm = df / "Base.esm"
    esm.write_bytes(tes3(count=2) + misc("base_thing", long_model()) + misc("base_ok", "ok.nif"))
    esm_before = esm.read_bytes()
    esp = df / "Mod.esp"
    esp.write_bytes(tes3([("Base.esm", len(esm_before))], count=1) + misc("mod_thing", long_model()))
    fix(df, ["Base.esm", "Mod.esp"])
    moves = json.load(open(g / lp.RECORD))["moves"]
    assert len(moves) == 1
    short = moves[0]["short"]
    assert not (df / f"Meshes/{LONGDIR}/sub/thing.nif").exists() and (df / lp.fs(short)).exists()
    assert field(esp, "MISC", "mod_thing", "MODL") == lp.under_top(short)          # .esp edited in place
    assert esm.read_bytes() == esm_before                                          # .esm never touched
    patch = df / m.PATCH_NAME
    assert field(patch, "MISC", "base_thing", "MODL") == lp.under_top(short)      # corrected copy in the patch
    assert field(patch, "MISC", "base_ok", "MODL") is None                        # nothing else copied
    assert moves[0]["esm"] == ["Base.esm"] and moves[0]["esp"][0].endswith("Mod.esp")


def test_texture_named_by_a_loose_model_and_icon_by_record(game):
    g, df = game
    tex = f"{LONGDIR}\\textures_of_it\\tx_long.dds"
    put(df, "Textures/" + tex.replace("\\", "/"), dds())
    put(df, "Meshes/m/a.nif", nif(tex))
    put(df, f"Icons/{LONGDIR}/icon_folder/thing.dds", dds())
    esp = df / "Mod.esp"
    esp.write_bytes(tes3(count=1) + misc("t", "m\\a.nif", icon=f"{LONGDIR}\\icon_folder\\thing.tga"))
    fix(df, ["Mod.esp"])
    moves = {mv["orig"].replace("/", "\\").replace(os.sep, "\\").lower(): mv["short"]
             for mv in json.load(open(g / lp.RECORD))["moves"]}
    tshort = moves["textures\\" + tex.lower()]
    assert m.nif_texture_refs((df / "Meshes/m/a.nif").read_bytes()) == [lp.under_top(tshort).lower()]
    ishort = moves[f"icons\\{LONGDIR}\\icon_folder\\thing.dds".lower()]
    assert field(esp, "MISC", "t", "ITEX") == lp.under_top(ishort)                 # .tga name, .dds file: matched


def test_texture_a_bsa_model_names_is_left_alone(game, capsys):
    g, df = game
    tex = f"{LONGDIR}\\textures_of_it\\tx_long.dds"
    p = put(df, "Textures/" + tex.replace("\\", "/"), dds())
    (df / "Base.bsa").write_bytes(_bsa([("meshes\\b\\b.nif", nif(tex))]))
    (df / "Base.esm").write_bytes(tes3(count=1) + misc("t", "b\\b.nif"))
    (g / "Morrowind.ini").write_text("[Game Files]\nGameFile0=Base.esm\n[Archives]\nArchive 0=Base.bsa\n")
    m.main([str(df), "--asset-check", "--fix", "--yes", "--no-vortex", "--min-severity", "INFO",
            "--fix-log", str(g / "fix.log")])          # load order and BSAs from Morrowind.ini
    out = capsys.readouterr().out
    assert "a model inside a BSA names it (Base.bsa: b\\b.nif)" in out and "left as it is" in out
    assert p.exists() and not (g / lp.RECORD).exists()


def test_undo_and_no_second_shortening(game, capsys):
    g, df = game
    put(df, f"Meshes/{LONGDIR}/sub/thing.nif", nif("tx_ok.dds"))
    put(df, f"Meshes/{LONGDIR}/sub/xthing.nif", nif("tx_ok.dds"))
    put(df, f"Meshes/{LONGDIR}/sub/xthing.kf", b"NetImmerse File Format, Version 4.0.0.2\n" + bytes(64))
    tex = f"{LONGDIR}\\textures_of_it\\tx_long.dds"
    put(df, "Textures/" + tex.replace("\\", "/"), dds())
    put(df, "Meshes/m/a.nif", nif(tex))
    esp = df / "Mod.esp"
    esp.write_bytes(tes3(count=2) + misc("mod_thing", long_model()) + misc("a", "m\\a.nif"))
    fix(df, ["Mod.esp"])
    first = json.load(open(g / lp.RECORD))["moves"]
    assert len(first) == 2
    kf = [mv for mv in first if mv["orig"].lower().endswith("thing.nif")][0]
    assert any(dst.endswith("xthing_" + kf["short"].rsplit("_", 1)[1][:-4] + ".kf") for _s, dst in kf["files"])
    after_esp = esp.read_bytes()
    nif_after = (df / "Meshes/m/a.nif").read_bytes()
    capsys.readouterr()
    fix(df, ["Mod.esp"])                                          # again: nothing more to move or edit
    assert json.load(open(g / lp.RECORD))["moves"] == first
    assert esp.read_bytes() == after_esp and (df / "Meshes/m/a.nif").read_bytes() == nif_after
    assert not list((df / "Meshes/lp").glob("*/lp"))
    assert m.main([str(df), "--longpaths-undo", "--no-vortex"]) == 0
    for f in ("thing.nif", "xthing.nif", "xthing.kf"):
        assert (df / f"Meshes/{LONGDIR}/sub/{f}").exists()
    assert field(esp, "MISC", "mod_thing", "MODL") == long_model()
    assert m.nif_texture_refs((df / "Meshes/m/a.nif").read_bytes()) == [tex.lower()]
    assert not (g / lp.RECORD).exists() and (g / (lp.RECORD + ".undone")).exists()


def test_dry_run_changes_nothing(game, capsys):
    g, df = game
    p = put(df, f"Meshes/{LONGDIR}/sub/thing.nif", nif())
    esp = df / "Mod.esp"
    esp.write_bytes(tes3(count=1) + misc("mod_thing", long_model()))
    before = esp.read_bytes()
    fix(df, ["Mod.esp"], "--dry-run")
    out = capsys.readouterr().out
    assert "Paths too long for Windows" in out and "Meshes" in out
    assert p.exists() and esp.read_bytes() == before and not (g / lp.RECORD).exists()


def test_tidy_moves_in_the_mod_edits_esp_lists_esm_and_check_writes_the_patch(game):
    g, df = game
    mod = g / "staging" / "Long Mod"
    put(mod, f"Meshes/{LONGDIR}/sub/thing.nif", nif(f"{LONGDIR}\\textures_of_it\\tx_long.dds"))
    put(mod, f"Textures/{LONGDIR}/textures_of_it/tx_long.dds", dds())
    (mod / "LongBase.esm").write_bytes(tes3(count=1) + misc("lb", long_model()))
    (mod / "LongMod.esp").write_bytes(tes3(count=1) + misc("lm", long_model()))
    esm_before = (mod / "LongBase.esm").read_bytes()
    issues, plan = lp.check_mod(str(mod), str(df), m, str(g))
    assert len(plan) == 2 and sum(1 for s, r, t in issues if s == "WARN") == 2
    assert lp.apply_mod(str(mod), plan, m, str(g), "LongMod") == 2
    short = {mv["orig"].lower().replace(os.sep, "\\"): mv["short"] for mv in json.load(open(g / lp.RECORD))["moves"]}
    mshort = short[f"meshes\\{LONGDIR}\\sub\\thing.nif".lower()]
    assert field(mod / "LongMod.esp", "MISC", "lm", "MODL") == lp.under_top(mshort)
    assert (mod / "LongBase.esm").read_bytes() == esm_before
    assert (mod / "Off/longpaths/LongMod/LongMod.esp").exists()                 # the .esp's original
    tshort = short[f"textures\\{LONGDIR}\\textures_of_it\\tx_long.dds".lower()]
    assert m.nif_texture_refs((mod / lp.fs(mshort)).read_bytes()) == [lp.under_top(tshort).lower()]
    assert lp.check_mod(str(mod), str(df), m, str(g))[1] == []                  # nothing left to shorten
    # "Vortex deploys" the mod; mwdialog_check's ESM patch corrects the master's record
    for f in ("LongBase.esm", "LongMod.esp", lp.fs(mshort), lp.fs(tshort)):
        put(df, f, (mod / f).read_bytes())
    fix(df, ["LongBase.esm", "LongMod.esp"])
    assert field(df / m.PATCH_NAME, "MISC", "lb", "MODL") == lp.under_top(mshort)
    assert (df / "LongBase.esm").read_bytes() == esm_before


def test_sound_name_too_long_for_the_32_byte_field_gets_a_short_name(game):
    g, df = game
    name = "fx\\a_sound_name_of_thirty_five_chars.wav"           # 39 characters: the game keeps 31
    put(df, "Sound/" + name.replace("\\", "/"), b"RIFF\x24\0\0\0WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 44100,
                                                                                       88200, 2, 16) + b"data\0\0\0\0")
    esp = df / "Mod.esp"
    esp.write_bytes(tes3(count=1) + rec("SOUN", sub("NAME", z("snd_x")) + sub("FNAM", z(name))
                                        + sub("DATA", bytes([255, 0, 255]))))
    fix(df, ["Mod.esp"])
    new = field(esp, "SOUN", "snd_x", "FNAM")
    assert new.startswith("lp\\a_sound_name_of") and len(new) <= 31 and (df / "Sound" / lp.fs(new)).exists()
