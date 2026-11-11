"""Mipmaps only where a world model draws the texture: vortex_tidy judges a mod's textures by its own
models (menu / MCM / icon / effect pictures exempt), mwdialog_check's asset check judges every winning
model against the winning texture (loose or BSA, by the game's override rules), cached by size + date."""
import os
import struct

from conftest import ah, m, rec, sub, tes3, z
from test_cache import _bsa, nif


def dds(w=128, h=128, mips=1):
    head = (b"DDS " + struct.pack("<7I", 124, 0x21007 if mips > 1 else 0x1007, h, w, w * h // 2, 0, mips)
            + b"\0" * 44 + struct.pack("<2I", 32, 4) + b"DXT1" + b"\0" * 40)
    body, lw, lh = 0, w, h
    for _ in range(mips):
        body += max(1, lw // 4) * max(1, lh // 4) * 8
        lw, lh = max(1, lw // 2), max(1, lh // 2)
    return head + bytes(body)


def put(base, rel, data):
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def game(tmp_path):
    g = tmp_path / "Morrowind"
    df = g / "Data Files"
    df.mkdir(parents=True)
    (g / "Morrowind.ini").write_text("[Game Files]\nGameFile0=Base.esm\n")
    return g, df


def flagged(issues):
    return sorted(r.replace("\\", "/") for _s, r, t in issues if "no mipmaps" in t)


# ---------------------------------------------------------------- vortex_tidy: the mod's own models only
def test_tidy_flags_only_textures_its_own_world_models_draw(tmp_path):
    g, df = game(tmp_path)
    mod = g / "staging" / "Things"
    put(mod, "Meshes/m/thing.nif", nif("tx_thing.dds", "mymod/mymod_logo.dds"))
    put(mod, "Meshes/e/spark.nif", nif("tx_spark.dds"))               # an effect model
    put(mod, "Meshes/m/vfx_burst.nif", nif("tx_burst.dds"))
    put(mod, "Textures/tx_thing.dds", dds())                          # drawn by thing.nif: flagged
    put(mod, "Textures/mymod/mymod_logo.dds", dds(256, 128))          # MCM logo: exempt even when named
    put(mod, "Textures/tx_spark.dds", dds())                          # only an effect model draws it
    put(mod, "Textures/tx_burst.dds", dds())
    put(mod, "Textures/vfx_glow01.dds", dds())                        # effect name, no model
    put(mod, "Textures/menu_mymod.dds", dds())
    put(mod, "Textures/tx_pack_rock.dds", dds())                      # a replacer: no own model draws it
    put(mod, "Textures/tx_small.dds", dds(32, 32))                    # under 64 px: never
    put(mod, "Icons/m/tx_thing.dds", dds())                           # inventory icon
    put(mod, "BookArt/mymod_page.dds", dds())
    put(mod, "MWSE/mods/mymod/logo.dds", dds())                       # not an asset folder at all
    st = {}
    issues, fixes = ah.check_folder(str(mod), m, str(df), set(), stats=st)
    assert flagged(issues) == ["Textures/tx_thing.dds"]
    assert [f[2].replace("\\", "/") for f in fixes if f[0] == "tex" and f[3].get("mips")] == ["Textures/tx_thing.dds"]
    assert st["mips_skipped"] == 8                                    # all the others 64 px+ without mipmaps
    # the record says the mipmaps are missing but didn't count, and keeps the facts for mwdialog_check
    c = ah.shared_cache(str(g))
    r = c.get(ah.TIDY_KEY + "things|textures\\tx_pack_rock.dds", ah.stamp_of(os.stat(mod / "Textures/tx_pack_rock.dds")))
    assert r["c"] is True and r["m"] is True and r["t"][0] == "dds"


def test_tidy_cached_skip_is_judged_again_when_a_model_starts_using_it(tmp_path, monkeypatch):
    g, df = game(tmp_path)
    mod = g / "staging" / "Pack"
    put(mod, "Textures/tx_rock.dds", dds())
    assert flagged(ah.check_folder(str(mod), m, str(df), set())[0]) == []
    ah.close_caches()
    reads = []
    real_open = open

    def spy(p, *a, **k):
        reads.append(str(p))
        return real_open(p, *a, **k)
    monkeypatch.setattr(ah, "open", spy, raising=False)
    assert flagged(ah.check_folder(str(mod), m, str(df), set())[0]) == []
    assert not any(p.endswith("tx_rock.dds") for p in reads)          # clean record: not read again
    put(mod, "Meshes/m/rock.nif", nif("tx_rock.dds"))                 # the mod now has a model drawing it
    assert flagged(ah.check_folder(str(mod), m, str(df), set())[0]) == ["Textures/tx_rock.dds"]


def test_exempt_file_adds_and_drops_patterns(tmp_path):
    g, df = game(tmp_path)
    (g / ah.MIP_EXEMPT_RECORD).write_text("texture-name: tx_hud*\n!texture-name: *logo*\nmesh: meshes\\spells\\*\n")
    mod = g / "staging" / "Cfg"
    put(mod, "Meshes/m/a.nif", nif("tx_hud_bar.dds", "tx_logo_sign.dds"))
    put(mod, "Meshes/spells/s.nif", nif("tx_rune.dds"))
    for t in ("tx_hud_bar", "tx_logo_sign", "tx_rune"):
        put(mod, f"Textures/{t}.dds", dds())
    assert flagged(ah.check_folder(str(mod), m, str(df), set())[0]) == ["Textures/tx_logo_sign.dds"]


def test_exemption_lists():
    r = ah.mip_rules()
    for t in ("textures\\menu_book.dds", "textures\\mymod\\mymod_logo.dds", "icons\\a\\b.dds", "bookart\\x.dds",
              "splash\\s.dds", "textures\\levelup\\x.dds", "textures\\vfx_fire.dds", "textures\\a\\b_vfx.dds",
              "textures\\tx_bloodfx.dds", "textures\\tx_blood_01.dds", "textures\\tx_glow_spark.dds",
              "textures\\mwse\\mymod\\x.dds", "textures\\tx_cursor.dds", "textures\\birthsigns\\lady.dds"):
        assert ah.mip_exempt_texture(t, r), t
    for t in ("textures\\tx_rock_01.dds", "textures\\tr\\tr_wall.dds", "textures\\tx_scroll_open.dds"):
        assert ah.mip_exempt_texture(t, r) is None, t
    assert ah.mip_exempt_mesh("e\\magic_cast_fire.nif", r) and ah.mip_exempt_mesh("meshes\\x\\vfx_a.nif", r)
    assert ah.mip_exempt_mesh("meshes\\x\\ex_hlaalu_b_01.nif", r) is None


# ---------------------------------------------------------------- mwdialog_check: winning model vs winning texture
def install(tmp_path):
    g, df = game(tmp_path)
    put(df, "Meshes/m/rock.nif", nif("tx_rock.tga"))                  # .tga name: the .dds is used
    put(df, "Meshes/e/fire.nif", nif("tx_flame.dds"))
    put(df, "Meshes/m/brazier.nif", nif("tx_coal.dds"))
    put(df, "Meshes/e/coalfx.nif", nif("tx_coal.dds"))
    recs = [rec("BODY", sub("NAME", z(f"bp_{x}")) + sub("MODL", z(f"m\\{x}.nif")) + sub("FNAM", z("Dark Elf"))
                + sub("BYDT", bytes(4))) for x in ("rock", "brazier")]
    (df / "Base.esm").write_bytes(tes3(count=len(recs)) + b"".join(recs))
    return g, df


def run(df, capsys):
    m.main([str(df), "--plugins", "Base.esm", "--asset-check", "--no-vortex", "--min-severity", "INFO"])
    return capsys.readouterr().out


def test_texture_pack_for_existing_model_is_flagged_only_by_the_top_level_check(tmp_path, capsys):
    g, df = install(tmp_path)
    pack = g / "staging" / "Rock Pack"
    for t in ("tx_rock", "tx_flame", "tx_coal", "tx_unrelated"):
        put(pack, f"Textures/{t}.dds", dds())
    put(pack, "Textures/mymod_logo.dds", dds())
    issues, _f = ah.check_folder(str(pack), m, str(df), set())
    assert flagged(issues) == []                                      # tidy: not its own models
    for t in ("tx_rock", "tx_flame", "tx_coal", "tx_unrelated", "mymod_logo"):
        os.link(pack / f"Textures/{t}.dds", df / f"Textures/{t}.dds") if (df / "Textures").is_dir() else (
            (df / "Textures").mkdir(), os.link(pack / f"Textures/{t}.dds", df / f"Textures/{t}.dds"))
    out = run(df, capsys)
    hits = sorted(l.split(": no mipmaps")[0].split()[-1] for l in out.splitlines() if ": no mipmaps" in l)
    # tidy-trusted hard links are still judged; flame only on an effect model; coal also on a world one
    assert hits == ["Textures/tx_coal.dds".replace("/", os.sep), "Textures/tx_rock.dds".replace("/", os.sep)]


def test_bsa_override_order(tmp_path):
    g, df = game(tmp_path)
    a, b = df / "a.bsa", df / "b.bsa"
    a.write_bytes(_bsa([("textures\\tx_x.dds", dds(mips=8)), ("textures\\tx_y.dds", dds(mips=8))]))
    b.write_bytes(_bsa([("textures\\tx_x.dds", dds()), ("textures\\tx_y.dds", dds())]))
    loose = put(df, "Textures/tx_y.dds", dds())
    os.utime(a, (2_000_000_000, 2_000_000_000))                       # a is newest: it beats b (listed later)
    os.utime(b, (1_000_000_000, 1_000_000_000))
    os.utime(loose, (1_500_000_000, 1_500_000_000))
    w = ah.WinningFiles("textures", {"tx_y.dds": str(loose)}, [str(a), str(b)])
    assert w.winner("tx_x.dds")[0] == "bsa" and w.winner("tx_x.dds")[1][0] == str(a)
    assert w.winner("tx_y.dds")[0] == "bsa"                           # the BSA is newer than the loose file
    os.utime(a, (1_000_000_000, 1_000_000_000))                       # same date: the one listed later
    w = ah.WinningFiles("textures", {"tx_y.dds": str(loose)}, [str(a), str(b)])
    assert w.winner("tx_x.dds")[1][0] == str(b)
    assert w.winner("tx_y.dds") == ("loose", str(loose))              # loose newer than both
    assert ah.WinningFiles("textures", {"tx_y.dds": str(loose)}, [str(a), str(b)], 1).winner("tx_y.dds")[0] == "bsa"
    w = ah.WinningFiles("textures", {"tx_y.dds": str(loose)}, [str(a), str(b)], -1)
    assert w.winner("tx_x.dds") is None and w.winner("tx_y.dds")[0] == "loose"


def _pairs(g, df, bsas):
    tree = m.DataTree(str(df))
    c = ah.shared_cache(str(g))
    A = m.ModelAssets([str(df)], [str(p) for p in bsas], tree=tree, cache=c)
    lo, bs, _st = ah.mip_pairs(A, tree, str(df), m, c, ini_path=str(g / "Morrowind.ini"), game_dir=str(g))
    return (sorted(x[0].replace("\\", "/").rsplit("/", 1)[-1] for x in lo),
            sorted(x[0].replace("\\", "/").rsplit("/", 1)[-1] for x in bs))


def test_vanilla_model_in_bsa_against_loose_texture_pack(tmp_path):
    g, df = game(tmp_path)
    v = df / "Morrowind.bsa"
    v.write_bytes(_bsa([("meshes\\x\\wall.nif", nif("tx_wall.dds")), ("meshes\\e\\spell.nif", nif("tx_spell.dds")),
                        ("textures\\tx_wall.dds", dds(mips=8)), ("textures\\tx_spell.dds", dds(mips=8)),
                        ("meshes\\x\\old.nif", nif("tx_old.dds")), ("textures\\tx_old.dds", dds())]))
    os.utime(v, (1_000_000_000, 1_000_000_000))
    pack = [put(df, "Textures/tx_wall.dds", dds()), put(df, "Textures/tx_spell.dds", dds())]
    for p in pack:
        os.utime(p, (1_500_000_000, 1_500_000_000))
    assert _pairs(g, df, [v]) == (["tx_wall.dds"], ["tx_old.dds"])    # the pack's copy wins; spell is an effect
    ah.close_caches()
    os.utime(v, (1_600_000_000, 1_600_000_000))                       # now the BSA is newer: its copy is used
    m._BSA_MEMO.clear()
    assert _pairs(g, df, [v]) == ([], ["tx_old.dds"])


def test_per_pair_results_come_from_the_cache_on_run_2(tmp_path, monkeypatch):
    g, df = game(tmp_path)
    v = df / "Morrowind.bsa"
    v.write_bytes(_bsa([("meshes\\x\\old.nif", nif("tx_old.dds")), ("textures\\tx_old.dds", dds())]))
    put(df, "Meshes/m/a.nif", nif("tx_a.dds"))
    put(df, "Textures/tx_a.dds", dds())
    first = _pairs(g, df, [v])
    assert first == (["tx_a.dds"], ["tx_old.dds"])
    keys = set(ah.shared_cache(str(g)).d)
    assert "tex2:textures\\tx_a.dds" in keys and "tex2b:morrowind.bsa|tx_old.dds" in keys
    ah.close_caches()

    real_open = open

    def no_read(p, *a, **k):
        if str(p).lower().endswith((".dds", ".nif", ".bsa")):
            raise AssertionError(f"read again: {p}")
        return real_open(p, *a, **k)
    monkeypatch.setattr(ah, "open", no_read, raising=False)
    assert _pairs(g, df, [v]) == first
