"""Regression tests for mwdialog_check.py (C1, I1-I3, I8, I9, M1-M10, M14)."""
import argparse
import os
import struct
import subprocess
import sys

import pytest

from conftest import (SRC, hedr_count, lev, m, misc, plugin, rec, records_of, sub, tes3, z)


def ref(i, name, x=0.0):
    return sub("FRMR", struct.pack("<I", i)) + sub("NAME", z(name)) + sub("DATA", struct.pack("<6f", x, 0, 0, 0, 0, 0))


def interior(name, refs=b"", extra=b""):
    return rec("CELL", sub("NAME", z(name)) + sub("DATA", struct.pack("<Iif", 1, 0, 0.0)) + extra + refs)


def game(tmp_path):
    df = tmp_path / "Data Files"
    df.mkdir()
    return df


# ---------------------------------------------------------------- basics
def test_parse_and_truncation():
    d = tes3(count=1) + misc("a")
    assert [t for _o, t, _f, _b in m.iter_records(d)] == ["TES3", "MISC"]
    with pytest.raises(m.FormatError):
        list(m.iter_records(d[:-3]))


# ---------------------------------------------------------------- C1: clean compares with the winning master
def _clean_setup(tmp_path, mod_value):
    df = game(tmp_path)
    mw, tr, pe = df / "Morrowind.esm", df / "Tribunal.esm", df / "Mod.esp"
    plugin(mw, [], [misc("x", 5)])
    plugin(tr, [("Morrowind.esm", mw.stat().st_size)], [misc("x", 50)])
    plugin(pe, [("Morrowind.esm", mw.stat().st_size), ("Tribunal.esm", tr.stat().st_size)], [misc("x", mod_value)])
    plugins = [("Morrowind.esm", str(mw)), ("Tribunal.esm", str(tr)), ("Mod.esp", str(pe))]
    args = argparse.Namespace(dry_run=False, yes=True, fix_log=str(tmp_path / "log.txt"))
    return plugins, args, pe


def test_C1_clean_keeps_deliberate_revert_to_earlier_master(tmp_path):
    plugins, args, pe = _clean_setup(tmp_path, 5)          # Mod puts Morrowind's value back over Tribunal's
    m.run_clean(args, plugins, None)
    assert "MISC" in [t for _o, t, _f, _b in records_of(pe)], "the mod's intended revert was cleaned away"


def test_C1_clean_still_removes_copy_of_winning_master(tmp_path):
    plugins, args, pe = _clean_setup(tmp_path, 50)         # identical to Tribunal (the winner): redundant
    m.run_clean(args, plugins, None)
    left = [t for _o, t, _f, _b in records_of(pe)]
    assert "MISC" not in left
    assert hedr_count(pe) == len(left) - 1                 # M6: the HEDR count follows


def test_C1_clean_cell_ref_compared_with_last_master(tmp_path):
    df = game(tmp_path)
    mw, tr, pe = df / "Morrowind.esm", df / "Tribunal.esm", df / "Mod.esp"
    plugin(mw, [], [misc("a"), interior("Room", ref(1, "a", 1.0))])
    plugin(tr, [("Morrowind.esm", mw.stat().st_size)], [interior("Room", ref((1 << 24) | 1, "a", 2.0))])
    plugin(pe, [("Morrowind.esm", mw.stat().st_size), ("Tribunal.esm", tr.stat().st_size)],
           [interior("Room", ref((1 << 24) | 1, "a", 1.0))])   # moves it back where Morrowind had it
    plugins = [("Morrowind.esm", str(mw)), ("Tribunal.esm", str(tr)), ("Mod.esp", str(pe))]
    args = argparse.Namespace(dry_run=False, yes=True, fix_log=str(tmp_path / "log.txt"))
    m.run_clean(args, plugins, None)
    cells = [b for _o, t, _f, b in records_of(pe) if t == "CELL"]
    assert cells and m.first_sub(cells[0], b"FRMR") is not None, "the deliberate move-back was cleaned away"


# ---------------------------------------------------------------- I1: safe in-place writes
def test_I1_safe_write_keeps_hard_link_and_date(tmp_path):
    f, g = tmp_path / "a.esp", tmp_path / "staging.esp"
    f.write_bytes(tes3())
    os.link(f, g)
    os.utime(f, (1_000_000_000, 1_000_000_000))
    st = os.stat(f)
    new = tes3(count=1) + misc("x")
    m.write_plugin_bytes(str(f), new, keep_times=st)
    assert g.read_bytes() == new and os.path.samefile(f, g)
    assert int(os.stat(f).st_mtime) == 1_000_000_000
    assert not (tmp_path / "a.esp.mwdtmp").exists()


def test_I1_invalid_output_never_reaches_the_file(tmp_path):
    f = tmp_path / "a.esp"
    f.write_bytes(tes3())
    with pytest.raises(m.FormatError):
        m.write_plugin_bytes(str(f), tes3(count=1) + misc("x")[:-2])     # cut short
    assert f.read_bytes() == tes3()
    assert not (tmp_path / "a.esp.mwdtmp").exists()


# ---------------------------------------------------------------- I2: lossless text, per-plugin errors
def test_I2_undefined_cp1252_bytes_round_trip():
    raw = b"Topic\x81X\x8d\x8f\x90\x9d"
    assert m.pack_str(m.cstr(raw)) == raw + b"\0"


def test_I2_set_text_with_undefined_byte_topic(tmp_path):
    dial = rec("DIAL", sub("NAME", b"Q_Quest\x81\0") + sub("DATA", b"\x04"))
    info = rec("INFO", sub("INAM", z("1")) + sub("PNAM", z("")) + sub("NNAM", z(""))
               + sub("DATA", struct.pack("<B3xibbbb", 4, 0, -1, -1, -1, 0)) + sub("QSTN", b"\x01"))
    p = tmp_path / "Data Files"
    p.mkdir()
    p = p / "x.esp"
    data = plugin(p, [], [dial, info])
    off = [o for o, t, _f, _b in m.iter_records(data) if t == "INFO"][0]
    w = m.World(m.Report())
    w.file_sizes = {}
    w.load_plugin(str(p), "x.esp")
    tname = next(iter(w.topics.values())).name
    m.apply_plan(str(p), "x.esp", {off: [(("set_text", tname), "gave name", "msg")]}, w, [], backup=False)
    body = [b for _o, t, _f, b in records_of(p) if t == "INFO"][0]
    assert bytes(m.first_sub(body, b"NAME")) == b"Q_Quest\x81"


def test_I2_merge_levlist_with_undefined_byte_name():
    defs = [("a", lev(["x"], b"l_\x81"), False), ("b", lev(["x", "y"], b"l_\x81"), False),
            ("c", lev(["x", "z"], b"l_\x81"), False)]
    out, _n = m.merge_levlist("LEVI", defs)
    assert bytes(m.first_sub(out[16:], b"NAME")) == b"l_\x81\0"


# ---------------------------------------------------------------- I3: leveled lists vs. the plugin's masters
def _masters_of(table):
    return lambda p: table.get(p.lower(), set())


def test_I3_patch_can_remove_what_its_master_added():
    defs = [("Morrowind.esm", lev(["a", "b"]), False), ("ModA.esp", lev(["a", "b", "c"]), False),
            ("ModA_patch.esp", lev(["a", "b"]), False)]
    mo = _masters_of({"moda.esp": {"morrowind.esm"}, "moda_patch.esp": {"morrowind.esm", "moda.esp"}})
    out, _n = m.merge_levlist("LEVI", defs, None, mo)
    assert sorted(e for e, _l in m.parse_levlist("LEVI", out[16:])[2]) == ["a", "b"]


def test_I3_independent_additions_both_kept():
    defs = [("Morrowind.esm", lev(["a"]), False), ("A.esp", lev(["a", "c"]), False), ("B.esp", lev(["a", "d"]), False)]
    mo = _masters_of({"a.esp": {"morrowind.esm"}, "b.esp": {"morrowind.esm"}})
    out, _n = m.merge_levlist("LEVI", defs, None, mo)
    assert sorted(e for e, _l in m.parse_levlist("LEVI", out[16:])[2]) == ["a", "c", "d"]


def test_I3_flags_from_last_plugin_that_changed_them():
    defs = [("Morrowind.esm", lev(["a"], flags=1), False), ("A.esp", lev(["a", "c"], flags=3), False),
            ("B.esp", lev(["a", "d"], flags=1), False)]
    mo = _masters_of({"a.esp": {"morrowind.esm"}, "b.esp": {"morrowind.esm"}})
    out, _n = m.merge_levlist("LEVI", defs, None, mo)
    assert m.parse_levlist("LEVI", out[16:])[0] == 3


# ---------------------------------------------------------------- I8: damaged BSA headers
def bsa(files):
    c = len(files)
    names = b"".join(n.encode() + b"\0" for n, _d in files)
    noffs, o = [], 0
    for n, _d in files:
        noffs.append(o)
        o += len(n) + 1
    so, doff = b"", 0
    for _n, d in files:
        so += struct.pack("<II", len(d), doff)
        doff += len(d)
    dir_ = so + struct.pack(f"<{c}I", *noffs) + names
    return struct.pack("<III", 0x100, len(dir_), c) + dir_ + b"\0" * 8 * c + b"".join(d for _n, d in files)


def test_I8_valid_bsa_reads(tmp_path):
    p = tmp_path / "ok.bsa"
    p.write_bytes(bsa([("meshes\\a.nif", b"NIF1"), ("textures\\b.dds", b"DDS!")]))
    assert m.bsa_file_names(str(p)) == {"meshes/a.nif", "textures/b.dds"}
    idx = m.bsa_index(str(p))
    off, size = idx["textures\\b.dds"]
    assert p.read_bytes()[off:off + size] == b"DDS!"


@pytest.mark.parametrize("fn", ["bsa_file_names", "bsa_index"])
def test_I8_damaged_bsa_raises_formaterror(tmp_path, fn):
    p = tmp_path / "bad.bsa"
    p.write_bytes(struct.pack("<III", 0x100, 16, 100000) + b"\0" * 16)
    with pytest.raises(m.FormatError):
        getattr(m, fn)(str(p))


# ---------------------------------------------------------------- I9: Morrowind.ini backups
def test_I9_ini_backups_kept(tmp_path):
    game(tmp_path)
    ini = tmp_path / "Morrowind.ini"
    ini.write_bytes(b"[General]\r\nx=1\r\n[Game Files]\r\nGameFile0=Morrowind.esm\r\n")
    first = ini.read_bytes()
    m.write_ini_game_files(str(ini), ["Morrowind.esm", "A.esp"])
    m.write_ini_game_files(str(ini), ["Morrowind.esm", "B.esp"])
    assert b"GameFile1=B.esp" in ini.read_bytes()
    found = {f: open(os.path.join(dp, f), "rb").read() for dp, _d, fs in os.walk(tmp_path) for f in fs}
    assert found["Morrowind.ini.mwdialog-original.bak"] == first
    assert b"A.esp" in found["Morrowind.ini.mwdialog-play.bak"]
    assert any(k.startswith("Morrowind.ini.mwdialog-2") for k in found)


# ---------------------------------------------------------------- M1: backups past .bak99
def test_M1_backup_numbering_past_99(tmp_path):
    df = game(tmp_path)
    p = df / "X.esp"
    p.write_bytes(b"v0")
    for i in range(101):
        b = m.backup_path(str(p))
        with open(b, "w") as f:
            f.write(f"backup {i}")
    newest = m.backup_candidates(str(p))[-1]
    assert open(newest).read() == "backup 100"
    assert newest.endswith(".bak101")


# ---------------------------------------------------------------- M2: one module copy
def test_M2_script_and_import_share_one_module():
    code = (
        "import importlib.util, sys\n"
        f"sys.path.insert(0, {SRC!r})\n"
        f"spec = importlib.util.spec_from_file_location('__main_like__', {os.path.join(SRC, 'mwdialog_check.py')!r})\n"
        "main = importlib.util.module_from_spec(spec); sys.modules['__main_like__'] = main\n"
        "spec.loader.exec_module(main)\n"
        "main.asset_health_module()\n"
        "print(sys.modules['mwdialog_check'] is main)\n")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.strip().endswith("True")


# ---------------------------------------------------------------- M3: long ids
def _long_args(tmp_path, df, **kw):
    a = dict(data_dir=str(df), dry_run=False, fix_log=str(tmp_path / "log.txt"), openmw_cfg=None)
    a.update(kw)
    return argparse.Namespace(**a)


def test_M3_long_id_renamed_in_cell_references(tmp_path):
    df = game(tmp_path)
    long_id = "a_very_long_object_identifier_xyz_123"
    p = df / "A.esp"
    plugin(p, [], [misc(long_id), interior("Room", ref(1, long_id))])
    m.fix_long_names(_long_args(tmp_path, df), [("A.esp", str(p))], [])
    recs = records_of(p)
    mb = [b for _o, t, _f, b in recs if t == "MISC"][0]
    cb = [b for _o, t, _f, b in recs if t == "CELL"][0]
    assert m.cstr(m.first_sub(mb, b"NAME")) == long_id[:31]
    names = [m.cstr(d) for n, d in m.iter_subs(cb) if n == "NAME"]
    assert names == ["Room", long_id[:31]]


def test_M3_colliding_prefixes_not_renamed(tmp_path):
    df = game(tmp_path)
    a, b = "a_very_long_object_identifier_xy_one", "a_very_long_object_identifier_xy_two"
    p = df / "A.esp"
    plugin(p, [], [misc(a), misc(b), misc(a[:31])])
    before = p.read_bytes()
    m.fix_long_names(_long_args(tmp_path, df), [("A.esp", str(p))], [])
    assert p.read_bytes() == before


def test_M3_openmw_is_report_only(tmp_path):
    df = game(tmp_path)
    p = df / "A.esp"
    plugin(p, [], [misc("a_very_long_object_identifier_xyz_123")])
    before = p.read_bytes()
    m.fix_long_names(_long_args(tmp_path, df, openmw_cfg="openmw.cfg"), [("A.esp", str(p))], [])
    assert p.read_bytes() == before


# ---------------------------------------------------------------- M4: merges
def test_M4_merge_cell_flags_and_master_size(tmp_path):
    mw = tmp_path / "Morrowind.esm"
    mw.write_bytes(b"x" * 1234)
    da = tes3([("Morrowind.esm", 0)], 2) + rec("DIAL", sub("NAME", z("Topic")) + sub("DATA", b"\x00")) \
        + interior("Room", ref(1, "a"))
    db = tes3([("Morrowind.esm", 0)], 2) + rec("DIAL", sub("NAME", z("topic")) + sub("DATA", b"\x00")) \
        + rec("CELL", sub("NAME", z("Room")) + sub("DATA", struct.pack("<Iif", 1, 0, 0.0)), flags=0x400)
    log = []
    out, _s = m.build_merge([("A.esp", da), ("B.esp", db)], "M.esp", ["Morrowind.esm"], {}, log,
                            {"morrowind.esm": str(mw)})
    recs = list(m.iter_records(out))
    cell = [(f, b) for _o, t, f, b in recs if t == "CELL"][0]
    assert cell[0] & 0x400
    dial = [b for _o, t, _f, b in recs if t == "DIAL"][0]
    assert m.cstr(m.first_sub(dial, b"NAME")) == "topic"
    mast = [d for n, d in m.iter_subs(recs[0][3]) if n == "DATA"]
    assert struct.unpack("<Q", mast[0])[0] == 1234


# ---------------------------------------------------------------- M5: remove_master and moved references
def test_M5_remove_master_refuses_when_moved_ref_uses_it(tmp_path):
    df = game(tmp_path)
    p = df / "P.esp"
    cell = interior("Room", sub("MVRF", struct.pack("<I", (2 << 24) | 7)) + sub("CNDT", struct.pack("<ii", 0, 0)))
    plugin(p, [("Morrowind.esm", 1), ("Extra.esm", 1)], [cell])
    with pytest.raises(m.FormatError):
        m.remove_master(str(p), "Extra.esm")


# ---------------------------------------------------------------- M6: HEDR count only where HEDR is
def test_M6_set_hedr_count_needs_a_real_hedr():
    head = rec("TES3", sub("XXXX", b"\0" * 300))
    assert m.set_hedr_count(head, 7) == head
    good = tes3()
    assert struct.unpack_from("<I", m.set_hedr_count(good, 7), 16 + 8 + 296)[0] == 7


# ---------------------------------------------------------------- M7: our patches in any case
def test_M7_is_our_patch_ignores_case():
    assert m.is_our_patch(m.PATCH_NAME.upper())
    assert not m.is_our_patch("Other.esp")


# ---------------------------------------------------------------- M8: multipatch keeps the cell header
def test_M8_multipatch_fog_cell_keeps_other_subrecords(tmp_path, monkeypatch):
    df = game(tmp_path)
    p = df / "Fog.esp"
    extra = sub("WHGT", struct.pack("<f", -5.0)) + sub("AMBI", b"\0" * 12 + struct.pack("<f", 0.0)) \
        + sub("NAM5", b"\x01\x02\x03\x00")
    cell = rec("CELL", sub("NAME", z("FogRoom")) + sub("DATA", struct.pack("<Iif", 1, 0, 0.0)) + extra)
    plugin(p, [], [cell])
    w = m.World(m.Report())
    w.file_sizes = {}
    w.load_plugin(str(p), "Fog.esp")
    assert w.fogcells
    got = {}
    monkeypatch.setattr(m, "write_patch", lambda path, *a, extra=(), **k: got.setdefault("recs", extra))
    monkeypatch.setattr(m, "next_free_date", lambda *a, **k: None)
    monkeypatch.setattr(m, "read_load_order", lambda *a, **k: [])
    monkeypatch.setattr(m, "merged_objects", lambda *a, **k: ([], []))
    args = argparse.Namespace(dry_run=False, data_dir=str(df), fix_log=str(tmp_path / "log.txt"),
                              no_merge_objects=True, ini=None)
    m.run_multipatch(args, [("Fog.esp", str(p))], w)
    cb = [r for r in got["recs"] if r[:4] == b"CELL"][0][16:]
    subs = dict(m.iter_subs(cb))
    assert "WHGT" in subs and "NAM5" in subs
    assert struct.unpack_from("<f", subs["AMBI"], 12)[0] == pytest.approx(0.01)


# ---------------------------------------------------------------- M9: object merge
def test_M9_duplicate_inventory_entries_stay_separate():
    body = sub("NAME", z("npc")) + sub("NPCO", struct.pack("<i", 1) + b"gold_001".ljust(32, b"\0")) \
        + sub("NPCO", struct.pack("<i", 5) + b"gold_001".ljust(32, b"\0"))
    fields = dict(m.merge_fields("NPC_", body))
    assert len(fields["NPCO"]) == 2


def test_M9_damaged_plugin_left_out_of_object_merge(tmp_path):
    good, bad = tmp_path / "Good.esp", tmp_path / "Bad.esp"
    plugin(good, [], [misc("x")])
    bad.write_bytes(tes3(count=1) + misc("x")[:-3])
    recs, _notes = m.merged_objects([("Good.esp", str(good)), ("Bad.esp", str(bad))])
    assert recs == []


# ---------------------------------------------------------------- M10: read cache sees changes
def test_M10_read_cache_notices_a_changed_file(tmp_path):
    p = tmp_path / "a.esp"
    p.write_bytes(tes3())
    assert m.read_plugin_bytes(str(p)) == tes3()
    p.write_bytes(tes3(count=1) + misc("x"))
    assert m.read_plugin_bytes(str(p)) == tes3(count=1) + misc("x")


# ---------------------------------------------------------------- M14: missing PNAM is added
def test_M14_set_prev_adds_missing_pnam(tmp_path):
    df = game(tmp_path)
    p = df / "x.esp"
    dial = rec("DIAL", sub("NAME", z("greeting")) + sub("DATA", b"\x00"))
    info = rec("INFO", sub("INAM", z("2")) + sub("NNAM", z(""))
               + sub("DATA", struct.pack("<B3xibbbb", 0, 0, -1, -1, -1, 0)) + sub("NAME", z("hi")))
    data = plugin(p, [], [dial, info])
    off = [o for o, t, _f, _b in m.iter_records(data) if t == "INFO"][0]
    w = m.World(m.Report())
    w.file_sizes = {}
    w.load_plugin(str(p), "x.esp")
    m.apply_plan(str(p), "x.esp", {off: [(("set_prev", "1"), "linked", "msg")]}, w, [], backup=False)
    body = [b for _o, t, _f, b in records_of(p) if t == "INFO"][0]
    names = [n for n, _d in m.iter_subs(body)]
    assert names[:2] == ["INAM", "PNAM"] and m.cstr(m.first_sub(body, b"PNAM")) == "1"


# ---------------------------------------------------------------- normal maps tidy moved to Off\: flat stand-in
def test_normal_map_in_off_counts_as_missing(tmp_path):
    df = game(tmp_path)
    (df / "Meshes").mkdir()
    (df / "Meshes" / "m.nif").write_bytes(b"NetImmerse File Format\0\x10\0\0\0textures\\tx_wall_nm.dds\0")
    (df / "Textures").mkdir()
    (df / "Textures" / "tx_wall.dds").write_bytes(b"DDS ")
    off = df / "Off" / "normal maps" / "Signs" / "textures"          # even if an Off folder got deployed
    off.mkdir(parents=True)
    (off / "tx_wall_nm.dds").write_bytes(b"DDS ")
    a = m.ModelAssets([str(df)], [])
    assert "tx_wall_nm.dds" in a.missing_textures("m.nif")
    assert ("m.nif", "tx_wall_nm.dds") in a.ignored_normals


def test_vortex_lookup_never_brings_back_a_normal_map_from_off(tmp_path):
    st = tmp_path / "staging"
    for d in ("Signs/Off/normal maps/Signs/textures", "Signs/textures", "Rocks/Off/unused/Rocks/textures"):
        (st / d).mkdir(parents=True)
    (st / "Signs/Off/normal maps/Signs/textures/tx_wall_nm.dds").write_bytes(b"DDS ")
    (st / "Signs/textures/tx_wall.dds").write_bytes(b"DDS ")
    (st / "Rocks/Off/unused/Rocks/textures/tx_rock.dds").write_bytes(b"DDS ")
    repo = m.VortexRepo(str(st))
    assert repo.find("textures", "tx_wall_nm.dds", any_ext=True) is None
    assert repo.find("textures", "tx_wall.dds", any_ext=True) is not None
    assert repo.find("textures", "tx_rock.dds", any_ext=True) is not None    # other Off files: as before


@pytest.mark.parametrize("name", ["tx_a_n.dds", "tx_a_nm.dds", "tx_a_normal.dds", "tx_a_nrm.dds"])
def test_normal_map_stand_in_is_flat(tmp_path, name):
    df = game(tmp_path)
    rel = os.path.join("Textures", name)
    made = m.write_generated(str(df), str(tmp_path), [(rel, "model 'm.nif'", None, "Signs.esp")], [])
    assert made == [rel]
    data = (df / rel).read_bytes()
    assert data[:4] == b"DDS " and struct.unpack_from("<4I", data, 92) == (0x00FF0000, 0x0000FF00, 0x000000FF,
                                                                           0xFF000000)
    assert data[128:] == bytes((255, 128, 128, 255)) * 16           # BGRA: RGB (128, 128, 255) = flat normal
