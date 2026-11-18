"""Regression tests for mwdialog_assets.py (I4, I5, I6, M13)."""
import os
import struct

from conftest import ah, m, plugin, rec, records_of, sub, tes3, z


# ---------------------------------------------------------------- I4: --restore-unused
def test_I4_orphaned_and_unused_go_back_into_the_mod(tmp_path):
    g = tmp_path
    data = g / "Data Files"
    data.mkdir()
    mod = g / "staging" / "SomeMod"
    for kind in ("unused", "orphaned"):
        rel = os.path.join("meshes", "x", f"x{kind}.kf")
        dest = m.off_dest(str(mod), kind, "SomeMod.esp", rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w") as f:
            f.write(kind)
        with open(g / ah.UNUSED_RECORD, "a") as f:
            f.write(f"2026-11-11 06:00:00\t{rel}\t{dest}\t{kind}\n")
    ah.restore_unused(str(g), str(data))
    for kind in ("unused", "orphaned"):
        rel = os.path.join("meshes", "x", f"x{kind}.kf")
        staged, deployed = mod / rel, data / rel
        assert staged.read_text() == kind, f"{kind}: not back in the mod folder"
        assert deployed.exists() and os.path.samefile(staged, deployed), f"{kind}: not linked into Data Files"
    assert (g / (ah.UNUSED_RECORD + ".restored")).exists()


def test_I4_failed_line_keeps_the_record(tmp_path, monkeypatch):
    g = tmp_path
    data = g / "Data Files"
    data.mkdir()
    src = g / "elsewhere.kf"
    src.write_text("x")
    with open(g / ah.UNUSED_RECORD, "w") as f:
        f.write(f"t\tmeshes/a.kf\t{src}\tunused\n")
    real = os.replace

    def boom(a, b):
        if str(a) == str(src):
            raise OSError("locked")
        return real(a, b)
    monkeypatch.setattr(os, "replace", boom)
    ah.restore_unused(str(g), str(data))
    assert (g / ah.UNUSED_RECORD).exists()


# ---------------------------------------------------------------- I5: a new original after a mod update
def test_I5_new_original_kept_after_mod_update(tmp_path):
    data = tmp_path / "Data Files"
    (data / "Textures").mkdir(parents=True)
    rel = os.path.join("Textures", "a.dds")
    full = data / rel
    full.write_bytes(b"original v1")
    first = m.backup_asset_original(str(data), rel)
    assert open(first, "rb").read() == b"original v1"
    m.replace_asset_in_place(str(full), b"repaired v1")
    # a second repair run: the file is our repair, so no new copy
    assert m.backup_asset_original(str(data), rel) == first
    # the mod is updated: a new file arrives at the same path
    full.write_bytes(b"original v2")
    second = m.backup_asset_original(str(data), rel)
    assert second != first and open(second, "rb").read() == b"original v2"
    assert open(first, "rb").read() == b"original v1"


def test_I5_replace_in_place_keeps_hard_link(tmp_path):
    a, b = tmp_path / "a.dds", tmp_path / "staged.dds"
    a.write_bytes(b"old")
    os.link(a, b)
    m.replace_asset_in_place(str(a), b"new contents")
    assert b.read_bytes() == b"new contents" and os.path.samefile(a, b)


# ---------------------------------------------------------------- I6: renaming non-ASCII files
def test_I6_only_whole_path_values_change(tmp_path):
    root = tmp_path / "Mod"
    (root / "Meshes" / "x").mkdir(parents=True)
    (root / "Meshes" / "x" / "café.nif").write_bytes(b"NIF")
    book = rec("BOOK", sub("NAME", z("bk")) + sub("MODL", z("x\\café.nif"))
               + sub("TEXT", z("I drank at the café.nif bar; see x\\café.nif")))
    other = rec("MISC", sub("NAME", z("m")) + sub("MODL", z("y\\café.nif")))
    p = root / "Mod.esp"
    plugin(p, [], [book, other])
    msgs = []
    ah.rename_ascii(str(root), str(root / "Meshes" / "x" / "café.nif"), "Meshes/x/café.nif",
                    "Meshes/x/cafe.nif", msgs.append)
    recs = {t: b for _o, t, _f, b in records_of(p)}
    assert m.first_sub(recs["BOOK"], b"MODL") == b"x\\cafe.nif\0"
    assert b"caf\xe9.nif bar; see x\\caf\xe9.nif" in bytes(m.first_sub(recs["BOOK"], b"TEXT"))
    assert m.first_sub(recs["MISC"], b"MODL") == "y\\café.nif".encode("cp1252") + b"\0"
    assert (root / "Meshes" / "x" / "cafe.nif").exists()


def test_I6_script_text_full_path_changes():
    scpt = rec("SCPT", sub("SCHD", b"s".ljust(52, b"\0")) + sub("SCTX", b'PlaySound3D "x\\caf\xe9.wav"'))
    data = tes3(count=1) + scpt
    new, hits = ah.plugin_path_rename(data, [(b"x\\caf\xe9.wav", b"x\\cafe.wav"), (b"sound\\x\\caf\xe9.wav",
                                                                                 b"sound\\x\\cafe.wav")])
    assert hits == 1 and b'"x\\cafe.wav"' in new


def test_I6_model_naming_the_file_blocks_rename(tmp_path):
    root = tmp_path / "Mod"
    (root / "Meshes").mkdir(parents=True)
    (root / "Meshes" / "a.nif").write_bytes(b"NetImmerse\x00\x00\x00textures\\caf\xe9.dds\x00")
    assert ah._models_naming(b"caf\xe9.dds", str(root))
    assert not ah._models_naming(b"th\xe9.dds", str(root))


# ---------------------------------------------------------------- M13: DX10 alpha
def dx10_head(dxgi, alpha_mode=0):
    head = bytearray(148)
    head[:4] = b"DDS "
    head[84:88] = b"DX10"
    struct.pack_into("<I", head, 128, dxgi)
    struct.pack_into("<I", head, 144, alpha_mode)
    return bytes(head)


def test_M13_dx10_alpha_detection():
    assert ah.dx10_has_alpha(dx10_head(71)) is False      # BC1
    assert ah.dx10_has_alpha(dx10_head(98)) is True       # BC7
    assert ah.dx10_has_alpha(dx10_head(98, 3)) is False   # BC7, opaque
    assert ah.dx10_has_alpha(b"DDS ") is True             # unknown: keep alpha


def test_check_folder_leaves_a_plain_wav_alone(tmp_path):
    # the game does not fall back from a missing .wav to an .mp3: no conversion until plugins are repathed
    import struct
    fmt = struct.pack("<HHIIHH", 1, 1, 44100, 88200, 2, 16)              # mono, 44.1 kHz, 16-bit PCM
    wav = b"RIFF" + struct.pack("<I", 36) + b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"data" + b"\0" * 4
    (tmp_path / "Sound" / "fx").mkdir(parents=True)
    (tmp_path / "Sound" / "fx" / "a.wav").write_bytes(wav)
    issues, fixes = ah.check_folder(str(tmp_path), m)
    assert [f for f in fixes if f[0] == "snd"] == []


def test_a_large_splash_tga_gets_a_dds_without_mipmaps_and_stays(tmp_path, monkeypatch):
    import struct
    import subprocess
    splash = tmp_path / "mod" / "Splash"
    splash.mkdir(parents=True)
    (splash / "big.tga").write_bytes(b"\0" * 12 + struct.pack("<HH", 2048, 1024) + b"\x20\0" + b"px")
    (splash / "small.tga").write_bytes(b"\0" * 12 + struct.pack("<HH", 1024, 512) + b"\x20\0" + b"px")
    issues, fixes = ah.check_folder(str(tmp_path / "mod"), m)
    jobs = [(os.path.basename(f), j) for k, f, _r, j in fixes if k == "tex"]
    assert jobs == [("big.tga", {"convert": ".dds", "nomips": True, "keep": True})]
    (tmp_path / "texconv.exe").write_bytes(b"")
    seen = []

    def fake(cmd, **_kw):
        seen.append(cmd)
        out = cmd[cmd.index("-o") + 1]
        open(os.path.join(out, "big.dds"), "wb").write(b"DDS converted")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(ah.subprocess, "run", fake)
    done, skipped = ah.apply_folder(str(tmp_path / "mod"), fixes, m, str(tmp_path), "mod")
    assert (done, skipped) == (1, [])
    assert seen[0][seen[0].index("-m") + 1] == "1" and "BC3_UNORM" in seen[0]
    assert (splash / "big.dds").read_bytes() == b"DDS converted" and (splash / "big.tga").exists()


def test_apply_folder_turns_a_wav_into_a_same_stem_mp3_and_keeps_the_wav_in_off(tmp_path, monkeypatch):
    import struct
    import subprocess
    fmt = struct.pack("<HHIIHH", 1, 1, 44100, 88200, 2, 16)
    wav = b"RIFF" + struct.pack("<I", 36) + b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"data" + b"\0" * 4
    sound = tmp_path / "mod" / "Sound" / "fx"
    sound.mkdir(parents=True)
    (sound / "a.wav").write_bytes(wav)
    fixes = [("snd", str(sound / "a.wav"), "Sound\\fx\\a.wav", {"mp3": True})]

    def fake(cmd, **_kw):
        open(cmd[-1], "wb").write(b"ID3mp3 audio")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(ah, "find_ffmpeg", lambda: "ffmpeg.exe")
    monkeypatch.setattr(ah.subprocess, "run", fake)
    done, skipped = ah.apply_folder(str(tmp_path / "mod"), fixes, m, str(tmp_path), "mod")
    assert (done, skipped) == (1, [])
    assert (sound / "a.mp3").read_bytes() == b"ID3mp3 audio" and not (sound / "a.wav").exists()
    assert list((tmp_path / "mod" / "Off").rglob("a.wav"))                    # the original is kept


def test_check_folder_survives_a_non_ascii_name_that_is_not_utf8_in_cp1252(tmp_path):
    # Tamriel Rebuilt: os.path.basename on the cp1252 bytes raised UnicodeDecodeError and stopped the mod's check
    (tmp_path / "Textures" / "x").mkdir(parents=True)
    (tmp_path / "Textures" / "x" / "café.tga").write_bytes(b"\0" * 12 + struct.pack("<HH", 64, 64) + b"\x20\0px")
    issues, _fixes = ah.check_folder(str(tmp_path), m)
    assert any("non-ASCII" in i[2] for i in issues)
