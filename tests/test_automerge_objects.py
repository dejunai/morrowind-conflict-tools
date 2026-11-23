"""Object merge across a merged plugin (AutoMerge): each input is measured against its own masters, not
the merged plugin's union of masters. The prison-ship lantern case and the general rule."""
import struct

from conftest import m, sub, z, rec, plugin

LID = "light_com_lantern_02_200_Boat"
KEY = ("LIGH", LID.lower())


def ligh(radius, script=None, sound=None, id_=LID):
    b = sub("NAME", z(id_)) + sub("MODL", z("l\\Light_Com_Lantern_02.NIF")) \
        + sub("LHDT", struct.pack("<fiiIII", 0.0, 10, -1, radius, 0x288cf5, 0))
    if script:
        b += sub("SCRI", z(script))
    if sound:
        b += sub("SNAM", z(sound))
    return rec("LIGH", b)


def scpt(name):
    return rec("SCPT", sub("SCHD", name.encode().ljust(32, b"\0") + b"\0" * 20))


SCRIPTS = [scpt("Float"), scpt("SignRotate"), scpt("cupScript")]


def fields(raw):
    d = dict(m.iter_subs(raw[16:]))
    return {"SCRI": m.cstr(d["SCRI"]) if "SCRI" in d else None,
            "SNAM": m.cstr(d["SNAM"]) if "SNAM" in d else None,
            "radius": struct.unpack_from("<I", d["LHDT"], 12)[0]}


def setup(tmp_path, automerge_record=None):
    """Morrowind.esm (Float, r200), Expanded Sounds.esp (SignRotate + plx_swingrope), and the two inputs
    of the user's AutoMerge: the ES TLAD patch (masters include ES; r300) and Glowing Flames TLAD tweaks
    (vanilla masters only; r375, Float, no sound). The AutoMerge lists all their masters, ES included."""
    mw = [("Morrowind.esm", 0)]
    P = {}
    for name, masters, r in (
            ("Morrowind.esm", [], ligh(200, "Float")),
            ("Expanded Sounds.esp", mw, ligh(200, "SignRotate", "plx_swingrope")),
            ("ES TLAD Patch.esp", mw + [("Expanded Sounds.esp", 0)], ligh(300, "SignRotate", "plx_swingrope")),
            ("Glowing Flames TLAD.esp", mw, ligh(375, "Float")),
            ("mwdialog_check AutoMerge.esp", mw + [("Expanded Sounds.esp", 0)],
             automerge_record or ligh(375, "Float"))):
        P[name] = str(tmp_path / name)
        plugin(P[name], masters, ([r] + SCRIPTS) if name == "Morrowind.esm" else [r])
    active = [(n, P[n]) for n in ("Morrowind.esm", "Expanded Sounds.esp", "mwdialog_check AutoMerge.esp")]
    mi = {"mwdialog_check automerge.esp": [("ES TLAD Patch.esp", P["ES TLAD Patch.esp"]),
                                           ("Glowing Flames TLAD.esp", P["Glowing Flames TLAD.esp"])]}
    return P, active, mi


def test_bug_reproduced_without_merge_record(tmp_path):
    """The old behaviour: measured against its union of masters (ES among them), the AutoMerge looks like it
    deliberately put Float back and dropped the sound, so the Multipatch keeps the bug."""
    _P, active, _mi = setup(tmp_path)
    recs, _n = m.merged_objects(active)
    assert recs == []


def test_multipatch_measures_automerge_records_by_input(tmp_path):
    _P, active, mi = setup(tmp_path)
    recs, notes = m.merged_objects(active, merged_inputs=mi)
    assert len(recs) == 1
    assert fields(recs[0]) == {"SCRI": "SignRotate", "SNAM": "plx_swingrope", "radius": 375}
    assert "Glowing Flames TLAD.esp" in notes[0]


def test_multipatch_skips_what_the_automerge_already_has(tmp_path):
    good = ligh(375, "SignRotate", "plx_swingrope")
    _P, active, mi = setup(tmp_path, automerge_record=good)
    recs, _n = m.merged_objects(active, merged_inputs=mi)
    assert recs == []


def test_missing_input_falls_back_to_the_merged_plugin(tmp_path):
    P, active, mi = setup(tmp_path)
    mi["mwdialog_check automerge.esp"][1] = ("Glowing Flames TLAD.esp", str(tmp_path / "gone.esp"))
    order, owner = m.expand_merged(active, mi)
    assert order == active and owner == {}


def test_merged_armour_keeps_the_art_mods_parts_whatever_its_id(tmp_path):
    """The worn parts come from the plugins, never from a list of IDs in the tools."""
    for k, rid in enumerate(("the_chiding_cuirass", "dwemer_boots of flying", "merisan helm", "any_armour")):
        def armo(part, rating):
            return rec("ARMO", sub("NAME", z(rid)) + sub("MODL", z("a\\ground.nif"))
                       + sub("AODT", struct.pack("<ifiiii", 1, 6.0, 100, 100, 100, rating))
                       + sub("INDX", b"\x03") + sub("BNAM", z(part)))
        folder = tmp_path / str(k)
        folder.mkdir()
        order = []
        for name, masters, body in (("Morrowind.esm", [], armo("plain_part", 10)),
                                    ("Art.esp", [("Morrowind.esm", 0)], armo("art_part", 10)),
                                    ("Stats.esp", [("Morrowind.esm", 0)], armo("plain_part", 40))):
            plugin(str(folder / name), masters, [body])
            order.append((name, str(folder / name)))
        got = m.object_merges(order, only={("ARMO", rid)})
        assert len(got) == 1, rid
        fields = dict(m.iter_subs(got[0][1][16:]))
        assert m.cstr(fields["BNAM"]) == "art_part", rid
        assert struct.unpack("<ifiiii", fields["AODT"])[5] == 40, rid


def test_automerge_merges_objects_shared_by_inputs(tmp_path):
    """--auto-merge: the inputs' shared object is merged field by field before build_merge writes it."""
    P, _active, _mi = setup(tmp_path)
    order = [(n, P[n]) for n in ("Morrowind.esm", "Expanded Sounds.esp", "ES TLAD Patch.esp",
                                 "Glowing Flames TLAD.esp")]
    got = m.object_merges(order, only={KEY})
    assert [k for k, _r, _n in got] == [KEY]
    raw = got[0][1]
    assert fields(raw) == {"SCRI": "SignRotate", "SNAM": "plx_swingrope", "radius": 375}
    ins = [(n, open(P[n], "rb").read()) for n in ("ES TLAD Patch.esp", "Glowing Flames TLAD.esp")]
    log = []
    out, summary = m.build_merge(ins, "M.esp", [n for n, _p in order], {}, log, object_merges={KEY: raw})
    lights = [r for _o, t, _f, r in m.iter_records(out) if t == "LIGH"]
    assert len(lights) == 1 and fields(b"LIGH" + b"\0" * 12 + lights[0]) == fields(raw)
    assert summary["stats"]["objects merged"] == 1
    out2, _s = m.build_merge(ins, "M.esp", [n for n, _p in order], {}, [])
    l2 = [r for _o, t, _f, r in m.iter_records(out2) if t == "LIGH"][0]
    assert fields(b"LIGH" + b"\0" * 12 + l2)["SCRI"] == "Float"          # without it: last input wins whole


def test_rule_explicit_change_beats_a_plugin_that_left_it_vanilla(tmp_path):
    """General rule: a field a plugin changed from its master's value survives a later plugin that left that
    field as the master had it; an optional subrecord the later plugin simply doesn't have (and its master
    didn't either) is 'unchanged', not 'removed'."""
    base = rec("MISC", sub("NAME", z("cup")) + sub("MODL", z("m\\cup.nif")) + sub("FNAM", z("Cup"))
               + sub("MCDT", struct.pack("<fii", 1.0, 5, 0)))
    a = rec("MISC", sub("NAME", z("cup")) + sub("MODL", z("m\\cup.nif")) + sub("FNAM", z("Cup"))
            + sub("MCDT", struct.pack("<fii", 1.0, 5, 0)) + sub("SCRI", z("cupScript")) + sub("ITEX", z("m\\cup.tga")))
    b = rec("MISC", sub("NAME", z("cup")) + sub("MODL", z("m\\cup.nif")) + sub("FNAM", z("Fine Cup"))
            + sub("MCDT", struct.pack("<fii", 1.0, 5, 0)))
    mw = [("Morrowind.esm", 0)]
    paths = {}
    for n, ms, r in (("Morrowind.esm", [], base), ("A.esp", mw, a), ("B.esp", mw, b)):
        paths[n] = str(tmp_path / n)
        plugin(paths[n], ms, ([r] + SCRIPTS) if n == "Morrowind.esm" else [r])
    recs, _n = m.merged_objects([(n, paths[n]) for n in ("Morrowind.esm", "A.esp", "B.esp")])
    d = dict(m.iter_subs(recs[0][16:]))
    assert m.cstr(d["SCRI"]) == "cupScript" and m.cstr(d["ITEX"]) == "m\\cup.tga" and m.cstr(d["FNAM"]) == "Fine Cup"


def test_rule_removal_against_own_master_is_kept(tmp_path):
    """A plugin made against ES that drops ES's sound really removes it (absent vs. its own master)."""
    mw = [("Morrowind.esm", 0)]
    paths = {}
    for n, ms, r in (("Morrowind.esm", [], ligh(200, "Float")),
                     ("Expanded Sounds.esp", mw, ligh(200, "SignRotate", "plx_swingrope")),
                     ("Quiet.esp", mw + [("Expanded Sounds.esp", 0)], ligh(200, "SignRotate")),
                     ("Bright.esp", mw, ligh(500, "Float"))):
        paths[n] = str(tmp_path / n)
        plugin(paths[n], ms, ([r] + SCRIPTS) if n == "Morrowind.esm" else [r])
    recs, _n = m.merged_objects([(n, paths[n]) for n in paths])
    assert fields(recs[0]) == {"SCRI": "SignRotate", "SNAM": None, "radius": 500}


def test_merged_inputs_of_reads_the_merge_record(tmp_path):
    df = tmp_path / "Data Files"
    df.mkdir()
    (df / "A.esp").write_bytes(b"x")
    (tmp_path / m.MERGE_RECORD).write_text("[mwdialog_check AutoMerge.esp]\nA.esp\nGone.esp\n", encoding="utf-8")
    got = m.merged_inputs_of(str(tmp_path), str(df))
    assert got == {"mwdialog_check automerge.esp": [("A.esp", str(df / "A.esp")), ("Gone.esp", None)]}


def test_automerge_keeps_scripts_and_start_scripts(tmp_path):
    """Scripted plugins can be merged: SCPT and SSCR records survive, later input wins a shared script."""
    def sscr(name):
        return rec("SSCR", sub("DATA", b"1234") + sub("NAME", z(name)))
    def scpt_text(name, text):
        return rec("SCPT", sub("SCHD", name.encode().ljust(32, b"\0") + b"\0" * 20) + sub("SCTX", text.encode()))
    a = tmp_path / "A.esp"
    b = tmp_path / "B.esp"
    plugin(str(a), [("Morrowind.esm", 0)], [scpt_text("qScript", "begin qScript\nend"), sscr("qScript")])
    plugin(str(b), [("Morrowind.esm", 0)], [scpt_text("qScript", "begin qScript\n;v2\nend"), scpt("other")])
    ins = [(n, open(p, "rb").read()) for n, p in (("A.esp", a), ("B.esp", b))]
    out, _s = m.build_merge(ins, "M.esp", ["Morrowind.esm", "A.esp", "B.esp"], {"morrowind.esm": 1}, [])
    recs = {m.record_id(t, r): r for _o, t, _f, r in m.iter_records(out) if t != "TES3"}
    assert set(recs) == {("SCPT", "qscript"), ("SCPT", "other"), ("SSCR", "qscript")}
    assert b";v2" in m.first_sub(recs[("SCPT", "qscript")], b"SCTX")


def test_auto_merge_blacklist_reads_one_plugin_per_line(tmp_path):
    assert m.read_auto_merge_blacklist(str(tmp_path)) == set()
    (tmp_path / m.AUTO_MERGE_BLACKLIST).write_text("\ufeff; comment\n# also\n\n  Janel Addon.ESP  \nB.esp\n",
                                                   encoding="utf-8")
    assert m.read_auto_merge_blacklist(str(tmp_path)) == {"janel addon.esp", "b.esp"}
