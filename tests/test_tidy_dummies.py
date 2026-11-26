"""vortex_tidy's dummy rule: a broken asset it can't repair goes to the mod's Off\\broken\\ folder and a small valid
file of the same format takes its place (marked, so a later run leaves it alone); --undo puts the original back.
Everything here runs in pytest's tmp folder only."""
import json
import os
import struct
import types
import zlib

import pytest

from conftest import ah, m, plugin, vt

COIN = b"NetImmerse File Format, Version 4.0.0.2\n" + b"\0" * 60       # what the old stand-in source gave
GARBAGE_NIF = b"Gamebryo File Format, Version 20.0.0.5\n" + b"\1" * 80
FAKE_DDS = b"\x89PNG\r\n\x1a\n" + b"\2" * 200
BAD_MP3 = b"\0" * 700


def tree(root):
    out = {}
    for base, _ds, fns in os.walk(root):
        for fn in fns:
            p = os.path.join(base, fn)
            with open(p, "rb") as f:
                out[os.path.relpath(p, root)] = f.read()
    return out


def rel(*parts):
    return os.path.join(*parts)


@pytest.fixture
def env(tmp_path, monkeypatch):
    game = tmp_path / "game"
    (game / "Data Files").mkdir(parents=True)
    (tmp_path / "state").mkdir()
    monkeypatch.setattr(vt, "JOURNAL", str(tmp_path / "state" / "vortex_tidy_journal.jsonl"))
    monkeypatch.setattr(vt, "HERE", str(game))
    monkeypatch.setattr(vt, "CORE_MISSING", {})
    monkeypatch.setattr(vt, "blacklist", lambda create=False: [])
    monkeypatch.setattr(m, "stand_in_bytes", lambda r: COIN)             # never used for a dummy any more
    staging = tmp_path / "staging"
    root = staging / "Broken Bits-99-1-0"
    for d in ("textures", "sound", "video", "meshes"):
        (root / d).mkdir(parents=True)
    plugin(str(root / "Bits.esp"), [], [])
    (root / "textures" / "empty.tga").write_bytes(b"")
    (root / "textures" / "fake.dds").write_bytes(FAKE_DDS)
    (root / "sound" / "bad.mp3").write_bytes(BAD_MP3)
    (root / "video" / "empty.bik").write_bytes(b"")
    (root / "meshes" / "bad.nif").write_bytes(GARBAGE_NIF)
    audit = tmp_path / "backups" / "tidy" / "run"
    args = types.SimpleNamespace(staging=str(staging), only=None, skip=None, apply=True, _audit=str(audit),
                                 _journal_extra={"plan_copy": str(audit / "plan_enacted.txt"), "apply": "a1"})
    return types.SimpleNamespace(tmp=tmp_path, game=game, staging=staging, root=root, args=args)


def check(env):
    return vt.assets_check_mod(str(env.root), m, ah, str(env.game / "Data Files"), set(), str(env.game), {})


def apply(env):
    ares = vt.assets_check(env.args)
    vt.assets_apply(env.args, ares)
    return ares


def test_the_plan_says_a_dummy_goes_in_each_broken_files_place(env):
    ent = check(env)
    kinds = {f[2]: f[0] for f in ent["fixes"]}
    for r in (rel("textures", "empty.tga"), rel("textures", "fake.dds"), rel("sound", "bad.mp3"),
              rel("meshes", "bad.nif")):
        assert kinds.get(r) == "dummy", (r, kinds)
    assert rel("video", "empty.bik") not in kinds                       # no safe dummy: left as it is
    msgs = {r: msg for _s, r, msg in ent["issues"]}
    assert "a 4x4 placeholder TGA put in its place" in msgs[rel("textures", "empty.tga")]
    assert "a silent MP3 put in its place" in msgs[rel("sound", "bad.mp3")]
    assert "left as it is: no dummy for .bik files" in msgs[rel("video", "empty.bik")]   # no game data here
    assert "would need a dummy shipped with the tools" in msgs[rel("video", "empty.bik")]
    lines = vt.asset_action_lines(ent)
    assert any(x.startswith("repair dummy " + rel("textures", "empty.tga")) for x in lines)


def test_apply_moves_the_original_to_off_and_puts_a_marked_dummy_in_place(env):
    apply(env)
    off = env.root / "Off" / "broken" / "Bits"
    assert (off / "textures" / "empty.tga").read_bytes() == b""
    assert (off / "textures" / "fake.dds").read_bytes() == FAKE_DDS
    assert (off / "sound" / "bad.mp3").read_bytes() == BAD_MP3
    assert (off / "meshes" / "bad.nif").read_bytes() == GARBAGE_NIF
    assert (env.root / "textures" / "empty.tga").read_bytes() == vt.dummy_tga("empty.tga")
    assert (env.root / "textures" / "fake.dds").read_bytes()[:4] == b"DDS "
    assert (env.root / "sound" / "bad.mp3").read_bytes()[:2] == b"\xff\xfb"
    assert (env.root / "meshes" / "bad.nif").read_bytes() == vt.dummy_nif()            # made in code
    assert (env.root / "video" / "empty.bik").read_bytes() == b""           # left as it is
    mark = json.loads((off / "textures" / ("empty.tga" + vt.DUMMY_MARK)).read_text())
    assert mark["rel"] == rel("textures", "empty.tga")
    assert mark["sha"] == vt.hashlib.sha256(vt.dummy_tga("empty.tga")).hexdigest()


def test_a_later_run_leaves_the_dummies_alone(env):
    apply(env)
    st = {}
    ent = vt.assets_check_mod(str(env.root), m, ah, str(env.game / "Data Files"), set(), str(env.game), st)
    flagged = {f[2] for f in ent["fixes"]} | {r for _s, r, _m in ent["issues"]}
    for r in (rel("textures", "empty.tga"), rel("textures", "fake.dds"), rel("sound", "bad.mp3"),
              rel("meshes", "bad.nif")):
        assert r not in flagged
    assert st["dummies"] == 4


def test_applying_again_changes_nothing(env):
    apply(env)
    once = tree(env.root)
    apply(env)
    assert tree(env.root) == once


def test_undo_puts_the_originals_back_and_removes_dummies_off_copies_and_marks(env):
    before = tree(env.root)
    apply(env)
    assert tree(env.root) != before
    assert vt.undo() == 0
    assert tree(env.root) == before
    assert not (env.root / "Off").exists()


def test_undo_refuses_without_the_kept_original(env, capsys):
    apply(env)
    ops = [json.loads(x) for x in open(vt.JOURNAL, encoding="utf-8") if x.strip()]
    bak = next(op["backup"] for op in ops if "asset" in op and op["asset"].endswith("empty.tga"))
    os.remove(bak)
    after = tree(env.root)
    assert vt.undo() == 1
    assert tree(env.root) == after
    assert "original is missing" in capsys.readouterr().err


def test_a_dummy_changed_since_needs_force(env, capsys):
    before = tree(env.root)
    apply(env)
    (env.root / "textures" / "empty.tga").write_bytes(b"my own texture")
    assert vt.undo() == 1
    assert "changed since" in capsys.readouterr().err
    assert vt.undo(force=True) == 0
    assert tree(env.root) == before


def test_a_changed_dummy_is_no_longer_treated_as_one(env):
    apply(env)
    (env.root / "textures" / "fake.dds").write_bytes(FAKE_DDS)          # broken again (a mod update)
    ent = check(env)
    assert any(f[0] == "dummy" and f[2] == rel("textures", "fake.dds") for f in ent["fixes"])


def test_dummy_formats_are_valid():
    t = vt.dummy_tga("textures\\a.tga")
    assert len(t) == 18 + 4 * 4 * 3 and t[2] == 2 and struct.unpack_from("<HHB", t, 12) == (4, 4, 24)
    b = vt.dummy_bmp("textures\\a.bmp")
    assert b[:2] == b"BM" and struct.unpack_from("<I", b, 2)[0] == len(b) == 54 + 48
    assert struct.unpack_from("<iiHH", b, 18) == (4, 4, 1, 24)
    p = vt.dummy_png("textures\\a.png")
    assert p[:8] == b"\x89PNG\r\n\x1a\n"
    pos, chunks = 8, {}
    while pos < len(p):
        n, tag = struct.unpack_from(">I4s", p, pos)
        data = p[pos + 8:pos + 8 + n]
        assert struct.unpack_from(">I", p, pos + 8 + n)[0] == zlib.crc32(tag + data) & 0xFFFFFFFF
        chunks[tag] = data
        pos += 12 + n
    assert struct.unpack(">IIBBBBB", chunks[b"IHDR"]) == (4, 4, 8, 2, 0, 0, 0)
    assert len(zlib.decompress(chunks[b"IDAT"])) == 4 * (1 + 4 * 3)
    assert vt.dummy_tga("textures\\wall_nm.tga")[18:21] == bytes((255, 128, 128))   # flat normal, as the DDS ones
    assert vt.dummy_bytes("textures\\a.dds", m)[0][:4] == b"DDS "
    assert vt.dummy_bytes("sound\\a.wav", m)[0][:4] == b"RIFF"
    assert vt.dummy_bytes("video\\a.bik", m)[0] is None
    assert vt.dummy_bytes("fonts\\a.fnt", m)[0] is None


def _model_case(tmp_path, other_copy):
    staging = tmp_path / "staging"
    root = staging / "Mod"
    (root / "meshes").mkdir(parents=True)
    (root / "meshes" / "x.nif").write_bytes(b"x")
    if other_copy:
        (staging / "Other" / "meshes").mkdir(parents=True)
        (staging / "Other" / "meshes" / "x.nif").write_bytes(b"good")
    return str(root), os.path.join(str(root), "meshes", "x.nif")


@pytest.mark.parametrize("other_copy", [False, True])
def test_a_crashing_model_gets_a_dummy_unless_another_copy_can_win(tmp_path, monkeypatch, other_copy):
    monkeypatch.setattr(m, "stand_in_bytes", lambda r: COIN)
    root, full = _model_case(tmp_path, other_copy)
    r = rel("meshes", "x.nif")
    issues = [("ERROR", r, "broken model: ... -> moved to Off\\...\\broken\\; Deploy in Vortex so another mod's copy wins")]
    out_i, out_f = vt.apply_dummy_rule(root, m, ah, None, set(), issues, [("brokenout", full, r, "broken model")])
    assert out_f[0][0] == ("brokenout" if other_copy else "dummy")
    assert ("Deploy in Vortex" in out_i[0][2]) == other_copy


@pytest.mark.parametrize("other_copy", [False, True])
def test_a_stand_in_already_in_place_of_a_broken_model_stays(tmp_path, monkeypatch, other_copy):
    root, full = _model_case(tmp_path, other_copy)
    r = rel("meshes", "x.nif")
    out_i, out_f = vt.apply_dummy_rule(root, m, ah, None, set(), [("ERROR", r, "stand-in -> removed")],
                                       [("brokenout", full, r, "stand-in")])
    assert bool(out_f) == other_copy and bool(out_i) == other_copy


def test_no_dummy_for_a_type_without_generator_or_core_file(tmp_path, monkeypatch):
    monkeypatch.setattr(vt, "HERE", str(tmp_path / "game"))                # no game data at all
    staging = tmp_path / "staging"
    root = staging / "Mod"
    (root / "meshes").mkdir(parents=True)
    full = str(root / "meshes" / "xa.kf")
    r = rel("meshes", "xa.kf")
    st = {}
    out_i, out_f = vt.apply_dummy_rule(str(root), m, ah, None, set(), [("ERROR", r, "empty file -> kept")],
                                       [("broken", full, r, "empty")], st)
    assert out_f == [] and "left as it is" in out_i[0][2] and st["no_dummy"] == {".kf"}
    out_i, out_f = vt.apply_dummy_rule(str(root), m, ah, None, set(), [("ERROR", r, "broken -> moved")],
                                       [("brokenout", full, r, "broken model")])
    assert out_f[0][0] == "brokenout" and "with no dummy" in out_i[0][2]


# ---------------------------------------------------------------- dummies made in code
def test_generated_nif_is_a_model_the_asset_tools_accept(tmp_path):
    b = vt.dummy_nif()
    assert b.startswith(ah.NIF_HEAD) and ah.nif_links_past_end(b) is None and not ah.nif_without_shapes(b)
    mod = tmp_path / "Mod"
    (mod / "meshes").mkdir(parents=True)
    (mod / "meshes" / "a.nif").write_bytes(b)
    issues, fixes = ah.check_folder(str(mod), m, str(tmp_path / "Data Files"), set())
    assert issues == [] and fixes == []


def _jpeg_segments(b):
    assert b[:2] == b"\xff\xd8" and b[-2:] == b"\xff\xd9"
    pos, segs = 2, {}
    while b[pos + 1] != 0xDA:
        marker, n = b[pos + 1], struct.unpack_from(">H", b, pos + 2)[0]
        segs.setdefault(marker, []).append(b[pos + 4:pos + 2 + n])
        pos += 2 + n
    return segs


def test_generated_jpeg_is_a_baseline_greyscale_jpeg():
    for name in ("a.jpg", "a_glow.jpg", "a_nm.jpeg"):
        segs = _jpeg_segments(vt.dummy_jpg(name))
        assert struct.unpack(">BHHB", segs[0xC0][0][:6]) == (8, 8, 8, 1)          # 8-bit, 8x8, one component
        assert len(segs[0xC4]) == 2 and len(segs[0xDB][0]) == 65
    assert vt.generate_dummy("textures\\a.jpg")[1] == "an 8x8 placeholder JPEG"


def test_generated_sounds():
    w = vt.dummy_wav()
    assert w[:4] == b"RIFF" and w[8:12] == b"WAVE" and struct.unpack_from("<HHI", w, 20) == (1, 1, 22050)
    mp3 = vt.dummy_mp3()
    assert len(mp3) == 8 * 417 and all(mp3[i:i + 4] == b"\xff\xfb\x90\x64" for i in range(0, len(mp3), 417))


def test_every_generated_type_needs_no_files(tmp_path, monkeypatch):
    monkeypatch.setattr(vt, "HERE", str(tmp_path / "nowhere"))
    for ext in (".dds", ".tga", ".bmp", ".png", ".jpg", ".jpeg", ".wav", ".mp3"):
        b, what = vt.dummy_bytes("textures\\a" + ext)
        assert b and what == vt.GENERATED[ext]
    assert vt.dummy_bytes("meshes\\a.nif")[0] == vt.dummy_nif()               # no coin anywhere: the empty one
    assert vt.dummy_bytes("icons\\a.dds")[1] == "a 32x32 placeholder icon"
    assert vt.dummy_dds("a.dds") == m.placeholder_dds("a.dds")               # the old colours, made here
    assert vt.dummy_icon() == m.placeholder_icon()


# ---------------------------------------------------------------- copies of core game files
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


@pytest.fixture
def game(tmp_path, monkeypatch):
    g = tmp_path / "game"
    data = g / "Data Files"
    data.mkdir(parents=True)
    monkeypatch.setattr(vt, "HERE", str(g))
    monkeypatch.setattr(vt, "CORE_MISSING", {})
    vt._REF_TEXT.clear()
    (data / "Morrowind.bsa").write_bytes(_bsa([
        ("meshes\\a\\xused_door.kf", b"KF used"),
        ("meshes\\b\\xspare_thing.kf", b"KF spare, longer"),
        ("meshes\\i\\xin_dagoth_bridge00.kf", b"KF bridge"),
        ("meshes\\c\\shared.kf", b"KF the same path")]))
    plugin(str(data / "Morrowind.esm"), [], [vt_misc("door", "a\\used_door.nif"), vt_misc("u", "c\\shared.nif"),
                                             vt_misc("v", "in_dagoth_bridge00.nif")])
    (g / "Morrowind.ini").write_text("[Game Files]\nGameFile0=Morrowind.esm\n[Fonts]\nFont 0=magic_cards_regular\n")
    return types.SimpleNamespace(game=g, data=data, tmp=tmp_path)


def vt_misc(id_, model):
    from conftest import rec, sub, z
    return rec("MISC", sub("NAME", z(id_)) + sub("MODL", z(model)))


def test_a_kf_dummy_is_an_unused_core_animation(game):
    b, what = vt.dummy_bytes("meshes\\mine\\xbroken.kf", staging=str(game.tmp / "staging"))
    assert b == b"KF spare, longer" and "xspare_thing.kf" in what and "nothing in your plugins uses it" in what
    cache = json.loads((game.game / vt.DUMMY_SOURCES).read_text())
    assert cache[".kf"]["pick"][2] == "meshes\\b\\xspare_thing.kf"


def test_the_core_file_at_the_same_path_comes_first(game):
    b, what = vt.dummy_bytes("meshes\\c\\shared.kf")
    assert b == b"KF the same path" and "the original this file replaces" in what


def test_the_cached_pick_is_used_without_reading_the_plugins_again(game, monkeypatch):
    vt.dummy_bytes("meshes\\x\\xa.kf")
    monkeypatch.setattr(vt, "_reference_text", lambda files: (_ for _ in ()).throw(AssertionError("rescanned")))
    assert vt.dummy_bytes("meshes\\x\\xb.kf")[0] == b"KF spare, longer"


def test_with_every_core_animation_used_the_old_stand_in_animation_is_next(game):
    plugin(str(game.data / "Morrowind.esm"), [], [vt_misc("door", "a\\used_door.nif"),
                                                  vt_misc("t", "b\\spare_thing.nif"),
                                                  vt_misc("u", "c\\shared.nif"), vt_misc("v", "in_dagoth_bridge00.nif")])
    b, what = vt.dummy_bytes("meshes\\x\\xa.kf")
    assert b == b"KF bridge" and "stand-in" in what


def test_a_video_dummy_is_a_core_loose_video_not_a_deployed_one(game, tmp_path):
    video = game.data / "Video"
    video.mkdir()
    (video / "mw_intro.bik").write_bytes(b"BIKi intro, the bigger one")
    (video / "bethesda logo.bik").write_bytes(b"BIKi logo")
    staged = tmp_path / "staging" / "Mod" / "Video"
    staged.mkdir(parents=True)
    (staged / "tiny.bik").write_bytes(b"BIK")
    try:
        os.link(staged / "tiny.bik", video / "tiny.bik")                    # a Vortex-deployed file
    except (OSError, AttributeError):
        pytest.skip("no hard links here")
    b, what = vt.dummy_bytes("video\\mine.bik")
    assert b == b"BIKi logo" and "bethesda logo.bik" in what


def test_a_font_dummy_prefers_the_core_font_it_replaces(game):
    fonts = game.data / "Fonts"
    fonts.mkdir()
    (fonts / "magic_cards_regular.fnt").write_bytes(b"FNT core")
    (fonts / "daedric_font.fnt").write_bytes(b"FNT d")
    assert vt.dummy_bytes("fonts\\magic_cards_regular.fnt")[0] == b"FNT core"
    b, what = vt.dummy_bytes("fonts\\my_font.fnt")
    assert b == b"FNT d" and "nothing in your plugins uses it" in what   # magic_cards is named by Morrowind.ini


# ---------------------------------------------------------------- models: the Dwemer coin by default, --no-coins
def _coin_bsa(env, with_coin=True):
    files = [("meshes\\m\\misc_dwrv_coin00.nif", COIN)] if with_coin else [("meshes\\m\\other.nif", COIN)]
    (env.game / "Data Files" / "Morrowind.bsa").write_bytes(_bsa(files))


def _nif_fix(ent):
    return next(f for f in ent["fixes"] if f[2] == rel("meshes", "bad.nif"))


def test_by_default_a_broken_model_gets_the_dwemer_coin(env, monkeypatch):
    monkeypatch.setattr(vt, "NO_COINS", False)
    _coin_bsa(env)
    ent = check(env)
    fix = _nif_fix(ent)
    assert fix[0] == "dummy" and fix[3]["dummy"] == "coin"
    assert "Dwemer coin" in {r: msg for _s, r, msg in ent["issues"]}[rel("meshes", "bad.nif")]
    apply(env)
    assert (env.root / "meshes" / "bad.nif").read_bytes() == COIN                    # read out of Morrowind.bsa
    assert not (env.tmp / "game" / "dummy assets").exists()


def test_no_coins_gives_the_empty_invisible_model(env, monkeypatch):
    monkeypatch.setattr(vt, "NO_COINS", True)
    _coin_bsa(env)
    fix = _nif_fix(check(env))
    assert fix[3]["dummy"] == "empty"
    apply(env)
    assert (env.root / "meshes" / "bad.nif").read_bytes() == vt.dummy_nif()


def test_without_the_coin_the_empty_model_is_used_and_the_plan_says_so(env, monkeypatch, capsys):
    monkeypatch.setattr(vt, "NO_COINS", False)
    _coin_bsa(env, with_coin=False)
    st = {}
    ent = vt.assets_check_mod(str(env.root), m, ah, str(env.game / "Data Files"), set(), str(env.game), st)
    assert _nif_fix(ent)[3]["dummy"] == "empty" and st["no_coin"]
    msg = {r: x for _s, r, x in ent["issues"]}[rel("meshes", "bad.nif")]
    assert "empty, invisible model" in msg and vt.NO_COIN_NOTE in msg
    ares = vt.assets_check(env.args)
    assert vt.NO_COIN_NOTE in ares["body"]                                            # in the plan file's summary
    vt.assets_apply(env.args, ares)
    assert (env.root / "meshes" / "bad.nif").read_bytes() == vt.dummy_nif()


@pytest.mark.parametrize("first,then", [(False, True), (True, False)])
def test_switching_modes_leaves_existing_dummies_alone(env, monkeypatch, first, then):
    _coin_bsa(env)
    monkeypatch.setattr(vt, "NO_COINS", first)
    apply(env)
    once = tree(env.root)
    monkeypatch.setattr(vt, "NO_COINS", then)
    ent = check(env)
    assert rel("meshes", "bad.nif") not in {f[2] for f in ent["fixes"]} | {r for _s, r, _m in ent["issues"]}
    apply(env)
    assert tree(env.root) == once


def test_the_plan_line_names_the_kind_so_a_plan_from_the_other_mode_differs(env, monkeypatch):
    _coin_bsa(env)
    monkeypatch.setattr(vt, "NO_COINS", False)
    coin = vt.asset_action_lines(check(env))
    monkeypatch.setattr(vt, "NO_COINS", True)
    empty = vt.asset_action_lines(check(env))
    assert set(coin) != set(empty)
    assert any('"dummy": "coin"' in x for x in coin) and any('"dummy": "empty"' in x for x in empty)


def test_a_coin_the_plan_named_but_gone_at_apply_is_not_swapped_for_another_kind(env, monkeypatch):
    full = str(env.root / "meshes" / "bad.nif")
    done, skipped = vt.make_dummies(str(env.root), [("dummy", full, rel("meshes", "bad.nif"),
                                                     {"why": "x", "dummy": "coin"})], m, "Bits")
    assert done == 0 and skipped and (env.root / "meshes" / "bad.nif").read_bytes() == GARBAGE_NIF


def test_help_lists_no_coins(monkeypatch, capsys):
    monkeypatch.setattr(vt.sys, "argv", ["vortex_tidy.py", "--help"])
    with pytest.raises(SystemExit):
        vt.main()
    assert "--no-coins" in capsys.readouterr().out


# ---------------------------------------------------------------- core game files altered: one warning per run
@pytest.fixture
def whole(tmp_path, monkeypatch):
    """vortex_tidy run whole (plan, then --apply) on one mod with a broken model, in tmp only."""
    game = tmp_path / "game"
    (game / "Data Files").mkdir(parents=True)
    staging = tmp_path / "staging"
    mod = staging / "Bits-1-1-0"
    (mod / "meshes").mkdir(parents=True)
    plugin(str(mod / "Bits.esp"), [], [])
    (mod / "meshes" / "bad.nif").write_bytes(GARBAGE_NIF)
    monkeypatch.setattr(vt, "HERE", str(game))
    monkeypatch.setattr(vt, "CORE_MISSING", {})
    monkeypatch.setattr(vt, "JOURNAL", str(tmp_path / "journal.jsonl"))
    monkeypatch.setattr(vt, "PLAN", str(tmp_path / "vortex_tidy_plan.txt"))
    monkeypatch.setattr(vt, "BLACKLIST_FILE", str(tmp_path / "bl.txt"))
    monkeypatch.setattr(vt, "_tool_modules", lambda: (m, ah))
    monkeypatch.setattr(m, "stand_in_bytes", lambda r: COIN)

    def run(*extra):
        monkeypatch.setattr(vt.sys, "argv", ["vortex_tidy.py", "--staging", str(staging), "--no-lua", *extra])
        return vt.main()

    def bsa(files):
        (game / "Data Files" / "Morrowind.bsa").write_bytes(_bsa(files))
    run.bsa, run.nif, run.data = bsa, mod / "meshes" / "bad.nif", game / "Data Files"
    return run


def _plan():
    with open(vt.PLAN, encoding="utf-8") as f:
        return f.read()


def test_no_coin_in_morrowind_bsa_warns_once_that_the_core_files_were_altered(whole, capsys):
    whole.bsa([("meshes\\m\\other.nif", COIN)])
    assert whole() == 0                                                      # plan mode: same exit code
    out = capsys.readouterr().out
    assert out.count(vt.CORE_WARN_HEAD) == 1
    assert "meshes\\m\\misc_dwrv_coin00.nif is not in Morrowind.bsa" in out and "Verify" in out
    assert out.rstrip().endswith("!" * 78)                                   # last thing the run prints
    plan = _plan()
    assert vt.NO_COIN_NOTE in plan                                           # the per-plan note stays
    assert ("# " + vt.CORE_WARN_HEAD) in plan and plan.rstrip().endswith("# " + "!" * 78)
    assert whole("--apply", "--yes") == 0                                    # never blocks
    out = capsys.readouterr().out
    assert out.count(vt.CORE_WARN_HEAD) == 1 and "The plan matches" in out
    assert whole.nif.read_bytes() == vt.dummy_nif()


def test_a_normal_morrowind_bsa_gives_no_warning(whole, capsys):
    whole.bsa([(vt.COIN_NIF, COIN)])
    assert whole() == 0
    out = capsys.readouterr().out
    assert vt.CORE_WARN_HEAD not in out and vt.CORE_WARN_HEAD not in _plan()
    assert whole("--apply", "--yes") == 0
    assert vt.CORE_WARN_HEAD not in capsys.readouterr().out and whole.nif.read_bytes() == COIN


def test_a_missing_morrowind_bsa_warns_too(whole, capsys):
    assert whole() == 0
    out = capsys.readouterr().out
    assert out.count(vt.CORE_WARN_HEAD) == 1 and "Morrowind.bsa is missing from Data Files" in out


def test_no_coins_never_looks_for_the_coin_so_no_warning(whole, capsys):
    assert whole("--no-coins") == 0
    assert vt.CORE_WARN_HEAD not in capsys.readouterr().out


def test_no_data_files_at_all_is_not_an_altered_game(whole, capsys):
    import shutil
    shutil.rmtree(whole.data)
    assert whole() == 0
    assert vt.CORE_WARN_HEAD not in capsys.readouterr().out


def test_the_kf_stand_in_missing_from_morrowind_bsa_warns_but_optional_archives_never_do(game):
    (game.data / "Morrowind.bsa").write_bytes(_bsa([("meshes\\a\\xused_door.kf", b"KF used")]))
    b, _what = vt.dummy_bytes("meshes\\mine\\xbroken.kf")
    assert b == b"KF used"                                                   # still a dummy: never blocks
    assert list(vt.CORE_MISSING) == [vt.KF_FALLBACK]                         # no Tribunal/Bloodmoon.bsa: fine
    assert any("xin_dagoth_bridge00.kf is not in Morrowind.bsa" in ln for ln in vt.core_warning())


def test_the_kf_stand_in_is_warned_about_even_when_another_unused_animation_is_used(game):
    (game.data / "Morrowind.bsa").write_bytes(_bsa([("meshes\\a\\xused_door.kf", b"KF used"),
                                                   ("meshes\\b\\xspare_thing.kf", b"KF spare, longer")]))
    b, what = vt.dummy_bytes("meshes\\mine\\xbroken.kf")
    assert b == b"KF spare, longer" and "nothing in your plugins uses it" in what
    assert list(vt.CORE_MISSING) == [vt.KF_FALLBACK]


def test_core_lookups_that_find_their_file_say_nothing(game):
    vt.dummy_bytes("meshes\\mine\\xbroken.kf")
    vt.dummy_bytes("meshes\\c\\shared.kf")
    assert vt.CORE_MISSING == {} and vt.core_warning() == []
