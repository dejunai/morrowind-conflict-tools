"""Vortex's state.v2 is a LevelDB: once Vortex compacts its log into sorted tables (.ldb), keys are
prefix-compressed and blocks Snappy-compressed, so the settings must be read as a real table, not grepped.
The tables here are built in the test, the way LevelDB writes them."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mwdialog_paths as P                       # noqa: E402


def _varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _snappy(data):
    """A small Snappy compressor: literals plus 2-byte-offset copies, as LevelDB stores a block."""
    out = bytearray(_varint(len(data)))
    lit = bytearray()
    seen = {}
    i = 0

    def flush():
        n = len(lit)
        if not n:
            return
        if n <= 60:
            out.append((n - 1) << 2)
        else:
            nb = (n - 1).bit_length() + 7 >> 3
            out.append((59 + nb) << 2)
            out.extend((n - 1).to_bytes(nb, "little"))
        out.extend(lit)
        lit.clear()

    while i < len(data):
        key = data[i:i + 4]
        j = seen.get(key) if len(key) == 4 else None
        seen[key] = i
        if j is not None and i - j < 65536:
            size = 4
            while i + size < len(data) and size < 64 and data[j + size] == data[i + size]:
                size += 1
            flush()
            out.append(((size - 1) << 2) | 2)
            out.extend((i - j).to_bytes(2, "little"))
            i += size
            continue
        lit.append(data[i])
        i += 1
    flush()
    return bytes(out)


def _block(entries, restart_every=16):
    buf, restarts, last = bytearray(), [], b""
    for n, (k, v) in enumerate(entries):
        if n % restart_every == 0:
            restarts.append(len(buf))
            shared = 0
        else:
            shared = 0
            while shared < min(len(k), len(last)) and k[shared] == last[shared]:
                shared += 1
        buf += _varint(shared) + _varint(len(k) - shared) + _varint(len(v)) + k[shared:] + v
        last = k
    for r in restarts or [0]:
        buf += r.to_bytes(4, "little")
    buf += len(restarts or [0]).to_bytes(4, "little")
    return bytes(buf)


def _ikey(key, seq, live=True):
    return key + ((seq << 8) | (1 if live else 0)).to_bytes(8, "little")


def build_table(rows, compress=True):
    """rows: (user key bytes, seq, value bytes or None for a deletion). Returns .ldb bytes."""
    rows = sorted(rows, key=lambda r: (r[0], -r[1]))
    data_block = _block([(_ikey(k, s, v is not None), v or b"") for k, s, v in rows])
    out = bytearray()
    body = _snappy(data_block) if compress else data_block
    data_handle = _varint(0) + _varint(len(body))
    out += body + bytes([1 if compress else 0]) + b"\0\0\0\0"
    meta = _block([])
    meta_handle = _varint(len(out)) + _varint(len(meta))
    out += meta + b"\0" + b"\0\0\0\0"
    index = _block([(_ikey(rows[-1][0], rows[-1][1]), data_handle)], restart_every=1)
    index_handle = _varint(len(out)) + _varint(len(index))
    out += index + b"\0" + b"\0\0\0\0"
    footer = (meta_handle + index_handle).ljust(40, b"\0") + bytes.fromhex("57fb808b247547db")
    return bytes(out + footer)


def build_log(seq, puts):
    rec = seq.to_bytes(8, "little") + len(puts).to_bytes(4, "little")
    for k, v in puts:
        rec += b"\x01" + _varint(len(k)) + k + _varint(len(v)) + v
    return b"\0\0\0\0" + len(rec).to_bytes(2, "little") + b"\x01" + rec


def _settings_rows(staging, downloads, seq=100):
    rows = [(f"settings###mods###installPath###{g}".encode(), seq, json.dumps(f"{staging}\\{{game}}").encode())
            for g in ("avowed", "kotor", "morrowind", "starfield")]
    rows.append((b"settings###mods###installPathMode", seq, b'"userData"'))
    rows.append((b"settings###downloads###copyOnIFF", seq, b"true"))
    rows.append((b"settings###downloads###maxParallelDownloads", seq, b'"6"'))
    rows.append((b"settings###downloads###path", seq, json.dumps(f"{downloads}\\{{game}}").encode()))
    rows += [(f"persistent###mods###morrowind###mod{i:04d}###state".encode(), seq, b'"installed"')
             for i in range(200)]
    return rows


@pytest.fixture
def vortex(tmp_path, monkeypatch):
    app = tmp_path / "Roaming"
    db = app / "Vortex" / "state.v2"
    db.mkdir(parents=True)
    staging_root = tmp_path / "Vortex Mods"
    dl_root = tmp_path / "Downloads" / "Vortex"
    (staging_root / "morrowind").mkdir(parents=True)
    (dl_root / "morrowind").mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(app))
    monkeypatch.setattr(P, "GENERATED_DIR", str(tmp_path / "no-generated"))
    P.clear_vortex_settings_cache()
    yield db, staging_root, dl_root
    P.clear_vortex_settings_cache()


def test_snappy_round_trip():
    data = b"settings###mods###installPath###" * 40 + bytes(range(256)) * 3
    assert P._snappy_decompress(_snappy(data)) == data


def test_compacted_table_is_read(vortex):
    db, staging_root, dl_root = vortex
    (db / "004670.ldb").write_bytes(build_table(_settings_rows(staging_root, dl_root)))
    (db / "LOG").write_text("Compacting 1@0 + 4@1 files\n", encoding="ascii")
    # the old raw search can't see prefix-compressed keys in a Snappy block: today's failure
    assert P._scan_leveldb_raw(str(db), "morrowind") == (None, None)
    assert os.path.normcase(P.resolve_staging()) == os.path.normcase(str(staging_root / "morrowind"))
    assert os.path.normcase(P.resolve_downloads()) == os.path.normcase(str(dl_root / "morrowind"))


def test_uncompressed_table_and_newest_log_wins(vortex, tmp_path):
    db, staging_root, dl_root = vortex
    (db / "000005.ldb").write_bytes(build_table(_settings_rows(tmp_path / "old", tmp_path / "old"), compress=False))
    (db / "000009.log").write_bytes(build_log(500, [
        (b"settings###mods###installPath###morrowind", json.dumps(f"{staging_root}\\{{game}}").encode()),
        (b"settings###downloads###path", json.dumps(f"{dl_root}\\{{game}}").encode())]))
    dl, st = P._leveldb_settings(str(db), "morrowind")
    assert st == f"{staging_root}\\{{game}}"
    assert dl == f"{dl_root}\\{{game}}"


def test_deletion_hides_older_value(vortex, tmp_path):
    db, staging_root, dl_root = vortex
    rows = _settings_rows(staging_root, dl_root, seq=10)
    rows.append((b"settings###downloads###path", 20, None))
    (db / "000007.ldb").write_bytes(build_table(rows))
    dl, st = P._leveldb_settings(str(db), "morrowind")
    assert dl is None and st == f"{staging_root}\\{{game}}"


def test_locked_or_damaged_files_are_skipped(vortex):
    db, staging_root, dl_root = vortex
    (db / "000001.ldb").write_bytes(b"\x00garbage" * 20 + bytes.fromhex("57fb808b247547db"))
    (db / "000002.ldb").write_bytes(build_table(_settings_rows(staging_root, dl_root)))
    (db / "000003.log").write_bytes(b"\xff" * 5)
    assert os.path.normcase(P.resolve_staging()) == os.path.normcase(str(staging_root / "morrowind"))


def test_marker_fallback_uses_remembered_folders(vortex, tmp_path, monkeypatch):
    db, staging_root, dl_root = vortex
    gen = tmp_path / "generated"
    gen.mkdir()
    monkeypatch.setattr(P, "GENERATED_DIR", str(gen))
    st, dl = staging_root / "morrowind", dl_root / "morrowind"
    (st / P.STAGING_MARKER).write_text('{"instance":"x","game":"morrowind"}', encoding="utf-8")
    (dl_root / P.DOWNLOADS_MARKER).write_text('{"instance":"x"}', encoding="utf-8")
    # a run that resolves them (here from the flags) remembers them...
    assert P.resolve_staging(cli=str(st)) == str(st)
    assert P.resolve_downloads(cli=str(dl)) == str(dl)
    rec = json.loads((gen / P.VORTEX_PATHS_RECORD).read_text(encoding="utf-8"))
    assert rec == {"staging": str(st), "downloads": str(dl)}
    # ...so with no readable settings at all the markers vouch for them
    P.clear_vortex_settings_cache()
    assert os.path.normcase(P.resolve_staging()) == os.path.normcase(str(st))
    assert os.path.normcase(P.resolve_downloads()) == os.path.normcase(str(dl))
    # a remembered folder whose marker is gone is not trusted
    (st / P.STAGING_MARKER).unlink()
    with pytest.raises(P.VortexPathError):
        P.resolve_staging()


def test_marker_fallback_vortex_default_location(vortex):
    db, _s, _d = vortex
    default = db.parent / "morrowind" / "mods"
    default.mkdir(parents=True)
    (default / P.STAGING_MARKER).write_text('{"game":"morrowind"}', encoding="utf-8")
    assert os.path.normcase(P.resolve_staging()) == os.path.normcase(str(default))
    (default / P.STAGING_MARKER).write_text('{"game":"skyrimse"}', encoding="utf-8")
    with pytest.raises(P.VortexPathError):
        P.resolve_staging()


def test_folder_without_marker_is_not_remembered(vortex, tmp_path, monkeypatch):
    gen = tmp_path / "generated"
    gen.mkdir()
    monkeypatch.setattr(P, "GENERATED_DIR", str(gen))
    plain = tmp_path / "plain"
    plain.mkdir()
    assert P.resolve_staging(cli=str(plain)) == str(plain)
    assert not (gen / P.VORTEX_PATHS_RECORD).exists()


def test_staging_flag_is_accepted_by_mwdialog_check(monkeypatch, tmp_path):
    import conftest
    m = conftest.m
    st = tmp_path / "st"
    st.mkdir()
    seen = {}

    def fake(args):
        seen["vortex_dir"] = args.vortex_dir
        raise SystemExit(0)

    monkeypatch.setattr(m, "_ensure_vortex_paths", fake)
    for flag in ("--staging", "--vortex-dir"):
        seen.clear()
        try:
            m._main([str(tmp_path), flag, str(st)])
        except SystemExit:
            pass
        assert seen.get("vortex_dir") == str(st), flag