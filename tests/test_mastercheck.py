"""Master mismatch guard: a patch made for a different master (or another version of it) than the installed one."""
import json
import os
import struct
import zipfile

import pytest

from conftest import m, plugin, rec, sub, z, misc

mc = m.mastercheck_module()


def cont(id_, items, script=None):
    b = sub("NAME", z(id_)) + sub("MODL", z("m\\box.nif")) + sub("CNDT", struct.pack("<f", 10.0))
    b += sub("FLAG", struct.pack("<I", 8))
    if script:
        b += sub("SCRI", z(script))
    for it in items:
        b += sub("NPCO", struct.pack("<i", 1) + it.encode().ljust(32, b"\0"))
    return rec("CONT", b)


@pytest.fixture
def game(tmp_path):
    g = tmp_path / "Morrowind"
    df = g / "Data Files"
    df.mkdir(parents=True)
    (g / "Morrowind.ini").write_text("[Game Files]\n")
    plugin(df / "Morrowind.esm", [], [misc("gold_001")])
    plugin(df / "Fooland.esp", [("Morrowind.esm", os.path.getsize(df / "Morrowind.esm"))],
           [misc(f"zz_{c}") for c in "abcdef"])
    return g, df


def run(df, *extra, plugins=("Morrowind.esm", "Fooland.esp", "Fooland Patch.esp")):
    return m.main([str(df), "--plugins", *plugins, "--no-vortex", "--no-archive-lookup",
                   "--fix-log", str(df.parent / "mwdialog_fixes.log")] + list(extra))


def header(path):
    return mc.header_masters(open(path, "rb").read())


def verdicts(g):
    return json.load(open(g / mc.CACHE_FILE))["verdicts"]


def test_different_mod_is_not_synced_or_stripped_and_can_be_disabled(game, capsys):
    g, df = game
    mor = os.path.getsize(df / "Morrowind.esm")
    plugin(df / "Fooland Patch.esp", [("Morrowind.esm", mor), ("Fooland.esp", 123456)],
           [cont("pt_box", ["zz_x", "zz_y", "zz_q", "zz_w"], script="zz_boxscript")])
    run(df, "--fix", "--yes")
    out = capsys.readouterr().out
    v = verdicts(g)["fooland patch.esp|fooland.esp"]
    assert v["kind"] == "different mod" and v["confidence"] >= 0.75
    assert "made for a different 'Fooland.esp'" in out and "not synced" in out
    assert dict(header(df / "Fooland Patch.esp"))["Fooland.esp"] == 123456            # header left as evidence
    data = open(df / "Fooland Patch.esp", "rb").read()
    assert b"zz_q" in data                                                      # dead references kept
    # the original size was noted before anything could rewrite it
    rec_ = json.load(open(g / mc.SIZES_RECORD))
    assert rec_["fooland patch.esp"]["masters"]["fooland.esp"]["original"] == 123456
    run(df, "--disable-mismatched")
    order = [x.strip() for x in (g / m.LOAD_ORDER_FILE).read_text().splitlines() if x.strip() and x[0] != ";"]
    assert "Fooland.esp" in order and "Fooland Patch.esp" not in order
    assert "taken out of the load order" in (g / "mwdialog_fixes.log").read_text()


def test_other_version_is_reported_and_synced_as_before(game, capsys):
    g, df = game
    mor = os.path.getsize(df / "Morrowind.esm")
    plugin(df / "Fooland Patch.esp", [("Morrowind.esm", mor), ("Fooland.esp", 123456)],
           [cont("pt_box", ["zz_a", "zz_b", "zz_c", "zz_gone"])])
    run(df, "--fix", "--yes")
    out = capsys.readouterr().out
    v = verdicts(g)["fooland patch.esp|fooland.esp"]
    assert v["kind"] == "other version" and v["confidence"] < 0.75 and v["misses"] == ["zz_gone"]
    assert "made for another version of 'Fooland.esp'" in out
    assert dict(header(df / "Fooland Patch.esp"))["Fooland.esp"] == os.path.getsize(df / "Fooland.esp")   # synced


def test_master_named_in_the_file_name_and_removed_refs_from_the_log(game):
    g, df = game
    # no masters at all (tes3cmd-made patch); a --fix already removed the references Fooland.esp doesn't have
    plugin(df / "Fooland Patch.esp", [], [cont("pt_box", ["zz_a"])])
    (g / "mwdialog_backup").mkdir()
    (g / "mwdialog_backup" / "fixes.archive.txt").write_text(
        "".join(f"Fooland Patch.esp: CONT 'pt_box': inventory item 'zz_{x}' doesn't exist -> remove it from the inventory\n"
                for x in ("p", "q", "r", "s", "t")))
    run(df)
    v = verdicts(g)["fooland patch.esp|fooland.esp"]
    assert v["why"] == "named in the file name"
    assert v["kind"] == "different mod" and sorted(v["misses"]) == [f"zz_{x}" for x in "pqrst"]


def test_sync_line_in_the_log_gives_the_original_size_and_parsing_is_incremental(game, tmp_path):
    g, df = game
    log = g / "mwdialog_fixes.log"
    log.write_text("\n==== 2026-11-01 10:00:00 ====\n"
                   "Fooland Patch.esp: master 'Fooland.esp' has changed size since this plugin was saved; the game warns at "
                   "startup -> synced the size recorded for 'Fooland.esp' (111 -> 222); its references all line up\n")
    cache = {}
    f1 = mc.log_facts(str(g), cache)
    assert f1["syncs"]["fooland patch.esp"]["fooland.esp"] == [111, 222]
    off = cache["logs"][os.path.normcase(os.path.abspath(log))]["offset"]
    with open(log, "a") as f:
        f.write("Fooland Patch.esp: master 'Fooland.esp' has changed size since this plugin was saved; the game warns "
                "at startup -> synced the size recorded for 'Fooland.esp' (222 -> 333); ok\n"
                "Bar.esp: [cell X] door: changes reference #5 in master 'Fooland.esp', which no longer exists there "
                "-> removed the reference\n")
    seen = []
    real = mc._merge_line
    mc._merge_line = lambda facts, line: (seen.append(line), real(facts, line))
    try:
        f2 = mc.log_facts(str(g), cache)
    finally:
        mc._merge_line = real
    assert len(seen) == 2                                    # only the new lines were read
    assert f2["syncs"]["fooland patch.esp"]["fooland.esp"] == [111, 333]     # the oldest value is the original
    assert f2["refgone"]["bar.esp"]["fooland.esp"] == 1
    assert cache["logs"][os.path.normcase(os.path.abspath(log))]["offset"] > off
    # a rotated log (head cut) is parsed again from the start
    log.write_text("Fooland Patch.esp: x -> synced the size recorded for 'Fooland.esp' (444 -> 555); ok\n")
    assert mc.log_facts(str(g), cache)["syncs"]["fooland patch.esp"]["fooland.esp"] == [444, 555]


def test_rewritten_header_original_from_the_download_archive(game, tmp_path):
    g, df = game
    mor = os.path.getsize(df / "Morrowind.esm")
    foo = os.path.getsize(df / "Fooland.esp")
    recs = [cont("pt_box", ["zz_a", "zz_b", "zz_c", "zz_d"])]
    # as downloaded: saved against a Fooland.esp of another size; installed: header rewritten to the current size
    orig = plugin(tmp_path / "orig.esp", [("Morrowind.esm", mor), ("Fooland.esp", 999)], recs)
    plugin(df / "Fooland Patch.esp", [("Morrowind.esm", mor), ("Fooland.esp", foo)], recs)
    (g / "mwdialog_fixes.log").write_text("Fooland Patch.esp: x -> synced the size recorded for 'Morrowind.esm' (1 -> 2)\n")
    staging, dl = tmp_path / "staging", tmp_path / "dl"
    (staging / "Fooland Patch-123-1-0-1700000000").mkdir(parents=True)
    (staging / "Fooland Patch-123-1-0-1700000000" / "Fooland Patch.esp").write_bytes(open(df / "Fooland Patch.esp", "rb").read())
    dl.mkdir()
    with zipfile.ZipFile(dl / "Fooland Patch-123-1-0-1700000000.zip", "w") as zf:
        zf.writestr("00 Core/Fooland Patch.esp", orig)
    m.main([str(df), "--plugins", "Morrowind.esm", "Fooland.esp", "Fooland Patch.esp", "--no-vortex",
            "--vortex-dir", str(staging), "--vortex-downloads", str(dl), "--fix-log", str(g / "mwdialog_fixes.log")])
    cache = json.load(open(g / mc.CACHE_FILE))
    assert any(c["masters"][1] == ["Fooland.esp", 999] for v in cache["archives"].values() for c in v)
    v = cache["verdicts"].get("fooland patch.esp|fooland.esp")
    # all its references line up: a matching master (just another size) is not reported as a mismatch
    assert v is None


def test_assess_scores():
    prof = {"ids": {"zz_a", "zz_b", "zz_c", "zz_d"}, "dials": set(), "prefixes": {"zz"}}
    facts = lambda refs: {"defs": set(), "refs": set(refs), "dials": set(), "links": []}
    assert mc.assess(facts(["zz_a", "zz_b"]), prof, set())[1] == "matches"
    c, k, _ = mc.assess(facts(["zz_a", "zz_b", "zz_c", "zz_x"]), prof, set())
    assert k == "other version" and c == 0.25
    c, k, _ = mc.assess(facts(["zz_x", "zz_y", "zz_w", "zz_v"]), prof, set())
    assert k == "different mod" and c == 1.0
    # same original size as the installed master: at most "other version"
    assert mc.assess(facts(["zz_x", "zz_y", "zz_w", "zz_v"]), prof, set(), original_size=5, installed_size=5)[1] \
        == "other version"
    # ids defined by some other loaded plugin are not counted against the master
    assert mc.assess(facts(["zz_x"]), prof, {"zz_x"})[2]["total"] == 0


def test_wrapped_fix_log_lines_are_rejoined(tmp_path):
    """Human fix-log lines may wrap at 115 chars; parse_log must rejoin continuations."""
    import mwdialog_text as MT
    log = tmp_path / "mwdialog_fixes.log"
    msg = ("Fooland Patch.esp: master 'Fooland.esp' has changed size since this plugin was saved; "
           "the game warns at startup -> synced the size recorded for 'Fooland.esp' (111 -> 222); "
           "its references all line up")
    with MT.open_log(log, "w") as f:
        f.write("==== 2026-11-01 10:00:00 ====\n")
        f.write("2026-11-01 10:00:00  " + msg + "\n")
    text = log.read_text(encoding="utf-8")
    assert "\n" in text.rstrip() and "synced the size" in text
    facts = mc.parse_log(str(log))["facts"]
    assert facts["syncs"]["fooland patch.esp"]["fooland.esp"] == [111, 222]
