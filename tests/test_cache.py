"""The asset cache and the speed-ups of the asset pass: sqlite cache (migration, crash safety, pruning),
cached model texture lists, the unused-files fix, BSA list memo, vortex_tidy's per-mod records and the
stand-ins that are always checked in full."""
import json
import os
import random
import sqlite3
import struct
import subprocess
import sys

import pytest

from conftest import SRC, ah, m, rec, sub, tes3, z

NIF = b"NetImmerse File Format, Version 4.0.0.2\n" + struct.pack("<I", 0x04000002)


def dds(w=32, h=32, fourcc=b"DXT1"):
    head = (b"DDS " + struct.pack("<7I", 124, 0x1007, h, w, w * h // 2, 0, 1) + b"\0" * 44
            + struct.pack("<2I", 32, 4) + fourcc + b"\0" * 40)
    return head + bytes(max(1, w // 4) * max(1, h // 4) * 8)


def dx10(total):
    head = (b"DDS " + struct.pack("<7I", 124, 0x1007, 32, 32, 512, 0, 1) + b"\0" * 44
            + struct.pack("<2I", 32, 4) + b"DX10" + b"\0" * 40 + struct.pack("<5I", 71, 3, 0, 1, 0))
    return head + bytes(total - len(head))


def nif(*texs):
    body = NIF + b"\x01\x02NiNode\0NiTriShape\0"
    for t in texs:
        s = ("textures\\" + t).encode("cp1252")
        body += struct.pack("<I", len(s)) + s
    return body + bytes(600)


def install(tmp_path):
    """A small Morrowind folder: one plugin naming two models, textures (one unused), a Lua file."""
    g = tmp_path / "Morrowind"
    df = g / "Data Files"
    for d in ("Meshes/m", "Textures", "Sound/fx", "MWSE/mods/x"):
        (df / d).mkdir(parents=True)
    (df / "Meshes/m/a.nif").write_bytes(nif("tx_a.dds", "tx_missing.dds"))
    (df / "Meshes/m/b.nif").write_bytes(nif("tx_b.dds"))
    for t in ("tx_a.dds", "tx_b.dds", "tx_lonely.dds", "tx_lua.dds", "tx_ini.dds"):
        (df / "Textures" / t).write_bytes(dds())
    (df / "MWSE/mods/x/main.lua").write_text('local t = "tx_lua.dds"\n')
    # body parts: their models are always checked (no placed object needed)
    recs = [rec("BODY", sub("NAME", z(f"bp_{x}")) + sub("MODL", z(f"m\\{x}.nif")) + sub("FNAM", z("Dark Elf"))
                + sub("BYDT", bytes(4))) for x in ("a", "b")]
    (df / "Base.esm").write_bytes(tes3(count=len(recs)) + b"".join(recs))
    (g / "Morrowind.ini").write_text("[Game Files]\nGameFile0=Base.esm\n; tx_ini.dds\n")
    return g, df


def run(df, capsys, *extra):
    m.main([str(df), "--plugins", "Base.esm", "--asset-check", "--no-vortex", "--min-severity", "INFO"] + list(extra))
    return capsys.readouterr().out


def unused_count(out):
    for line in out.splitlines():
        if "texture/sound file(s)" in line and "no plugin, model" in line:
            return int(line.split("INFO", 1)[1].split()[0])
    return 0


def db_rows(g):
    db = sqlite3.connect(os.path.join(str(g), ah.CACHE_DB))
    try:
        return dict((k, (s, r)) for k, s, r in db.execute("SELECT k, s, r FROM c"))
    finally:
        db.close()


def reopen(g):
    ah.close_caches()
    return ah.shared_cache(str(g))


# ---------------------------------------------------------------- (1) unused: the tool's own files don't count
def test_unused_same_on_run_1_and_2_and_own_files_ignored(tmp_path, capsys):
    g, df = install(tmp_path)
    # this tool's own files in the Morrowind folder name the unused texture: they must not count
    (g / "mwdialog_report.txt").write_text("tx_lonely.dds\n")
    (g / ah.UNUSED_RECORD).write_text("t\ttextures\\tx_lonely.dds\tx\tunused\n")
    first = run(df, capsys)
    assert unused_count(first) == 1                     # tx_lonely; tx_lua (Lua) and tx_ini (the ini) are used
    reopen(g)
    second = run(df, capsys)
    assert unused_count(second) == 1
    assert not any(k.startswith("refs:") and os.path.dirname(k[5:]) == str(g).lower() and
                   not k.endswith("morrowind.ini") for k in db_rows(g))


# ---------------------------------------------------------------- (2) model texture lists: fast scan, cached
CASES = [b"textures\\tx a b.dds", b"x\\tx_(odd)&[1]{2}~!@#$%'+,;=.TGA", b"\0\0caf\xe9.dds\0", b"..dds",
         b"\0.dds.dds", b"a.dds b.bmp c", b"\x05\0\0\0a.ddsx\0", b"textures/Sub Dir/tx.Dds", b".dds", b"x.dd",
         b"\xff\xfe" + b"y" * 300 + b".bmp", b"a.dds\x80b.tga", b"tx_\xe4rger.dds ok.dds"]


@pytest.mark.parametrize("raw", CASES)
def test_nif_texture_names_match_the_old_regex(raw):
    for data in (raw, b"\0\1" + raw + b"\0", NIF + raw + bytes(7) + raw):
        assert m.nif_texture_names(data) == m.NIF_TEXTURE_RE.findall(data)


def test_nif_texture_names_match_the_old_regex_on_random_bytes():
    rnd = random.Random(7)
    alphabet = b"ab ._\\/-\xe9\x00dstgbmpDDS()"
    for _ in range(3000):
        data = bytes(rnd.choice(alphabet) for _ in range(rnd.randrange(0, 60)))
        assert m.nif_texture_names(data) == m.NIF_TEXTURE_RE.findall(data), data
    blob = bytes(rnd.randrange(256) for _ in range(200000)) + b"textures\\x y.dds"
    assert m.nif_texture_names(blob) == m.NIF_TEXTURE_RE.findall(blob)


def test_model_textures_come_from_the_cache_on_run_2(tmp_path, capsys, monkeypatch):
    g, df = install(tmp_path)
    first = run(df, capsys)
    assert "tx_missing" in first
    reopen(g)

    def boom(_b):
        raise AssertionError("a model was read again")
    monkeypatch.setattr(m, "nif_texture_refs", boom)
    second = run(df, capsys)
    assert "tx_missing" in second
    rows = db_rows(g)
    assert json.loads(rows["nif:meshes\\m\\a.nif"][1])["tn"] == ["tx_a.dds", "tx_missing.dds"]


# ---------------------------------------------------------------- generated stand-ins: always checked in full
def test_stand_in_is_always_rechecked_and_a_replacement_noticed(tmp_path, capsys):
    g, df = install(tmp_path)
    gen = df / "Textures" / "tx_gen.dds"
    gen.write_bytes(dds())
    (g / m.GENERATED_RECORD).write_text("[Base.esm]\nTextures\\tx_gen.dds\t640\n")
    run(df, capsys)
    st = os.stat(gen)
    # a proper (here: DX10) file of the same size put in its place, with the same date: the stamp can't tell
    gen.write_bytes(dx10(len(dds())))
    os.utime(gen, ns=(st.st_atime_ns, st.st_mtime_ns))
    reopen(g)
    out = run(df, capsys)
    assert "tx_gen.dds: DX10" in out
    # an ordinary file whose cache entry still matches is NOT read again (the cache is used)
    other = df / "Textures" / "tx_b.dds"
    st = os.stat(other)
    other.write_bytes(dx10(len(dds())))
    os.utime(other, ns=(st.st_atime_ns, st.st_mtime_ns))
    reopen(g)
    assert "tx_b.dds: DX10" not in run(df, capsys)


def test_generated_model_ignores_cache_and_tidy(tmp_path):
    g, df = install(tmp_path)
    full = str(df / "Meshes/m/a.nif")
    st = os.stat(full)
    c = ah.shared_cache(str(g))
    key = ah.norm_rel(os.path.join("Meshes", "m", "a.nif"))
    c.put("nif:" + key, ah.stamp_of(st), {"tn": ["cached.dds"]})
    c.put(ah.TIDY_KEY + "mod|" + key, ah.stamp_of(st), {"c": True, "f": {"tn": ["tidy.dds"]}})
    assert ah.model_facts_cached(c, key, full, st, m)["tn"] == ["tidy.dds"]
    assert ah.model_facts_cached(c, key, full, st, m, {key})["tn"] == ["tx_a.dds", "tx_missing.dds"]


# ---------------------------------------------------------------- (3)/(4) migration from the JSON cache
def test_migration_from_json_once(tmp_path, capsys):
    g, df = install(tmp_path)
    head = dds()[:148]
    old = {"meshes\\m\\a.nif": {"s": "1:2", "r": {"tex": ["tx_a"]}},
           "texh:textures\\tx_a.dds": {"s": "3:4", "r": head.hex()},
           "clean2:textures\\tx_a.dds": {"s": "3:4", "r": True},
           "bsa:base.bsa": {"s": "5:6", "r": ["x"]},
           "snd:sound/fx/a.wav": {"s": "7:8", "r": [1, 22050]},
           "refs:" + os.path.join(str(g), "mwdialog_report.txt").lower(): {"s": "9:9", "r": [[], ["tx_lonely"]]},
           "refs:" + os.path.join(str(df), "mwse", "a.lua").lower(): {"s": "9:9", "r": [[], ["w"]]}}
    (g / ah.CACHE_FILE).write_text(json.dumps(old))
    with open(g / (ah.CACHE_FILE + ".add"), "w") as f:
        f.write(json.dumps(["snd:sound\\fx\\b.wav", {"s": "1:1", "r": False}]) + "\n" + '["cut sho')
    c = ah.shared_cache(str(g))
    err = capsys.readouterr().err
    assert "converting mwdialog_asset_cache.json" in err and ".json.migrated" in err
    assert c.get("nif:meshes\\m\\a.nif", "1:2") == {"tex": ["tx_a"]}
    assert c.get("texh:textures\\tx_a.dds", "3:4") == head.hex()
    assert c.get("snd:sound\\fx\\a.wav", "7:8") == [1, 22050]
    assert c.get("snd:sound\\fx\\b.wav", "1:1") is False                      # from the .add file
    assert not any(k.startswith(("clean2:", "bsa:")) for k in c.d)
    assert not any("mwdialog_report" in k for k in c.d) and any(k.endswith("a.lua") for k in c.d)
    assert not (g / ah.CACHE_FILE).exists() and (g / (ah.CACHE_FILE + ".migrated")).exists()
    assert (g / (ah.CACHE_FILE + ".add.migrated")).exists()
    # once only: a JSON file that turns up again later is not read in again
    (g / ah.CACHE_FILE).write_text(json.dumps({"nif:x": {"s": "1", "r": 1}}))
    c = reopen(g)
    assert "nif:x" not in c.d and "converting" not in capsys.readouterr().err


def test_old_texture_header_converted_on_use(tmp_path, capsys):
    g, df = install(tmp_path)
    t = df / "Textures" / "tx_a.dds"
    st = os.stat(t)
    key = ah.norm_rel(os.path.join("Textures", "tx_a.dds"))
    fake = dx10(len(dds()))[:148]                     # the old cache says DX10: proves its header is used
    (g / ah.CACHE_FILE).write_text(json.dumps({"texh:" + key: {"s": ah.stamp_of(st), "r": fake.hex()}}))
    out = run(df, capsys)
    assert "tx_a.dds: DX10" in out
    rows = db_rows(g)
    assert "texh:" + key not in rows and json.loads(rows["tex2:" + key][1])[0] == "dx10"


# ---------------------------------------------------------------- (3) a crash mid-run leaves a usable cache
def test_crash_mid_run_keeps_written_batches(tmp_path):
    g = tmp_path
    code = (f"import sys, os; sys.path.insert(0, {SRC!r}); import mwdialog_assets as ah\n"
            f"c = ah.shared_cache({str(g)!r})\n"
            "for i in range(1234): c.put('nif:m%d' % i, '1:1', {'tn': []})\n"
            "os._exit(3)\n")                           # killed: no atexit, no close
    assert subprocess.run([sys.executable, "-c", code]).returncode == 3
    c = ah.shared_cache(str(g))
    n = sum(1 for k in c.d if k.startswith("nif:m"))
    assert n >= 1000 and n % ah.AssetCache.BATCH == 0         # every full batch, nothing half-written
    c.put("nif:after", "1:1", 1)
    c = reopen(g)
    assert c.get("nif:after", "1:1") == 1


def test_failed_write_never_raises_and_damaged_file_is_set_aside(tmp_path, capsys):
    c = ah.shared_cache(str(tmp_path))
    c.put("nif:a", "1:1", 1)
    c.flush()

    class Broken:
        def execute(self, *a):
            raise sqlite3.OperationalError("disk I/O error")
        executemany = execute

        def close(self):
            pass
    real, c.db = c.db, Broken()
    c.put("nif:b", "1:1", 2)
    assert c.flush() is False and "could not write" in capsys.readouterr().err
    c.db = real
    c = reopen(tmp_path)
    assert c.get("nif:a", "1:1") == 1
    ah.close_caches()
    (tmp_path / ah.CACHE_DB).write_bytes(b"this is not a database" * 100)
    for x in ("-wal", "-shm"):
        if (tmp_path / (ah.CACHE_DB + x)).exists():
            (tmp_path / (ah.CACHE_DB + x)).unlink()
    c = ah.shared_cache(str(tmp_path))
    assert c.d == {} and (tmp_path / (ah.CACHE_DB + ".bad")).exists()
    c.put("nif:c", "1:1", 3)
    assert reopen(tmp_path).get("nif:c", "1:1") == 3


def test_cache_is_written_right_after_the_asset_pass(tmp_path, capsys):
    g, df = install(tmp_path)
    run(df, capsys)                                   # no close: what a later crash would leave
    assert any(k.startswith("tex2:") for k in db_rows(g)) and any(k.startswith("nif:") for k in db_rows(g))


# ---------------------------------------------------------------- (4) pruning
def test_entries_of_deleted_files_are_pruned(tmp_path, capsys):
    g, df = install(tmp_path)
    run(df, capsys)
    key = "tex2:" + ah.norm_rel(os.path.join("Textures", "tx_lonely.dds"))
    assert key in db_rows(g)
    (df / "Textures" / "tx_lonely.dds").unlink()
    reopen(g)
    run(df, capsys)
    assert key not in db_rows(g)


# ---------------------------------------------------------------- (5) one walk; BSA lists remembered
def test_tree_gives_the_same_sound_list_as_the_walk(tmp_path):
    g, df = install(tmp_path)
    (df / "Sound/fx/A.wav").write_bytes(b"RIFF")
    (df / "Sound/fx/sub").mkdir()
    (df / "Sound/fx/sub/b.mp3").write_bytes(b"ID3")
    tree = m.DataTree(str(df))
    assert m.collect_sound_files([str(df)], [], tree) == m.collect_sound_files([str(df)], [])
    walked = sorted((t, r) for t, r, _f in ah._walk(str(df), ah.ASSET_DIRS))
    assert sorted((t, r) for t, r, _f in tree.asset_files(ah.ASSET_DIRS)) == walked


def _bsa(files):
    names = b"".join(n.encode() + b"\0" for n, _d in files)
    noffs, o = [], 0
    for n, _d in files:
        noffs.append(o)
        o += len(n) + 1
    so, doff = b"", 0
    for _n, d in files:
        so += struct.pack("<II", len(d), doff)
        doff += len(d)
    dir_ = so + struct.pack(f"<{len(files)}I", *noffs) + names
    return struct.pack("<III", 0x100, len(dir_), len(files)) + dir_ + b"\0" * 8 * len(files) + b"".join(
        d for _n, d in files)


def test_bsa_lists_remembered_until_the_bsa_changes(tmp_path):
    p = tmp_path / "a.bsa"
    p.write_bytes(_bsa([("meshes\\a.nif", nif("tx_one.dds"))]))
    first = m.bsa_file_names(str(p))
    assert m.bsa_file_names(str(p)) is first                         # read once
    assert first == {"meshes/a.nif"}
    st = os.stat(p)
    p.write_bytes(_bsa([("meshes\\b.nif", nif("tx_two.dds")), ("meshes\\c.nif", nif())]))
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    assert m.bsa_file_names(str(p)) == {"meshes/b.nif", "meshes/c.nif"}
    assert set(m.bsa_index(str(p))) == {"meshes\\b.nif", "meshes\\c.nif"}


def test_bsa_model_textures_cached_by_bsa_size_and_date(tmp_path):
    g = tmp_path
    df = g / "Data Files"
    df.mkdir()
    p = df / "a.bsa"
    p.write_bytes(_bsa([("meshes\\a.nif", nif("tx_one.dds"))]))
    c = ah.shared_cache(str(g))
    assert m.ModelAssets([str(df)], [str(p)], cache=c).texture_names("a.nif") == ["tx_one.dds"]
    assert c.get("bsa2:a.bsa", ah.stamp_of(os.stat(p)))["tn"] == {"a.nif": ["tx_one.dds"]}
    st = os.stat(p)
    p.write_bytes(_bsa([("meshes\\a.nif", nif("tx_two.dds"))]))
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    m._BSA_MEMO.clear()
    assert m.ModelAssets([str(df)], [str(p)], cache=c).texture_names("a.nif") == ["tx_two.dds"]


# ---------------------------------------------------------------- (6) vortex_tidy's per-mod records
def test_tidy_records_per_mod_and_trust_needs_the_same_file(tmp_path, monkeypatch):
    g, df = install(tmp_path)
    mod = g / "staging" / "Rocks-12-1"
    (mod / "Meshes/m").mkdir(parents=True)
    (mod / "Meshes/m/r.nif").write_bytes(nif("tx_rock.dds"))
    ah.check_folder(str(mod), m, str(df), set())
    c = ah.shared_cache(str(g))
    key = ah.norm_rel(os.path.join("Meshes", "m", "r.nif"))
    rec_ = c.get(ah.TIDY_KEY + "rocks-12-1|" + key, ah.stamp_of(os.stat(mod / "Meshes/m/r.nif")))
    assert rec_["c"] is True and rec_["f"]["tn"] == ["tx_rock.dds"]
    os.link(mod / "Meshes/m/r.nif", df / "Meshes/m/r.nif")            # what Vortex deploys
    full = str(df / "Meshes/m/r.nif")

    def no_read(*a, **k):
        raise AssertionError("a tidy-checked file was read")
    monkeypatch.setattr(ah, "open", no_read, raising=False)
    assert ah.model_facts_cached(c, key, full, os.stat(full), m)["tn"] == ["tx_rock.dds"]
    monkeypatch.undo()
    # not the same file (another date): checked in full
    st = os.stat(full)
    os.unlink(full)
    (df / "Meshes/m/r.nif").write_bytes(nif("tx_other.dds"))
    os.utime(full, ns=(st.st_atime_ns, st.st_mtime_ns + 3_000_000_000))
    assert ah.model_facts_cached(c, key, full, os.stat(full), m)["tn"] == ["tx_other.dds"]


def test_tidy_trust_in_the_data_files_check(tmp_path, capsys):
    g, df = install(tmp_path)
    mod = g / "staging" / "Signs"
    (mod / "Textures").mkdir(parents=True)
    (mod / "Textures/tx_sign.dds").write_bytes(dx10(len(dds())))         # tidy reports it (can't fix it here)
    ah.check_folder(str(mod), m, str(df), set())
    os.link(mod / "Textures/tx_sign.dds", df / "Textures/tx_sign.dds")
    assert "tx_sign.dds: DX10" not in run(df, capsys)               # trusted: tidy's report has it
    reopen(g)
    st = os.stat(df / "Textures/tx_sign.dds")
    os.unlink(df / "Textures/tx_sign.dds")
    (df / "Textures/tx_sign.dds").write_bytes(dx10(len(dds())))       # a different file at the same path
    os.utime(df / "Textures/tx_sign.dds", ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))
    assert "tx_sign.dds: DX10" in run(df, capsys)


def test_tidy_prunes_files_and_mods_that_are_gone(tmp_path):
    g = tmp_path
    c = ah.shared_cache(str(g))
    for k in ("a|x.dds", "a|gone.dds", "b|y.dds", "c|z.dds"):
        c.put(ah.TIDY_KEY + k, "1:1", {"c": True})
    c.touched = {ah.TIDY_KEY + "a|x.dds"}               # checked now: mod a still has x.dds only
    ah.prune_tidy(c, {"a"}, {"a", "b"})
    assert sorted(k[len(ah.TIDY_KEY):] for k in c.d) == ["a|x.dds", "b|y.dds"]
