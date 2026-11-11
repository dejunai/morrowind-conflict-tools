"""Sounds in a big voice pack: the asset pass takes their size and date from the directory listing (no
os.stat each) and only confirms with os.stat what the cache can't vouch for; the sound index of every scan
lists the Sound folder without per-file path arithmetic."""
import os
import struct

from conftest import ah, m
from test_cache import install, reopen, run


def wav(ch=1, rate=44100):
    fmt = struct.pack("<HHIIHH", 1, ch, rate, rate * 2 * ch, 2 * ch, 16)
    data = bytes(64)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", len(body)) + body


def voices(df, n=30):
    for i in range(n):
        d = df / "Sound" / "Vo" / "AIV" / ("Race%d" % (i % 3)) / "F"
        d.mkdir(parents=True, exist_ok=True)
        (d / ("Line%02d.wav" % i)).write_bytes(wav())


def old_walk(d):
    root = os.path.join(d, "Sound")
    out = set()
    for dirpath, _dirs, fns in os.walk(root):
        for fn in fns:
            out.add(os.path.relpath(os.path.join(dirpath, fn), d).replace("\\", "/").lower())
    return out


def test_sound_names_match_the_old_walk(tmp_path):
    g, df = install(tmp_path)
    voices(df)
    (df / "Sound/fx/Odd Name (1).WAV").write_bytes(wav())
    (df / "Sound/Vo/AIV/empty").mkdir()
    got = m.sound_names_under(str(df / "Sound"))
    assert len(got) == len(set(got))
    assert set(got) == old_walk(str(df)) and len(got) == 31
    assert m.collect_sound_files([str(df)], []) == old_walk(str(df))
    assert m.sound_names_under(str(df / "nope")) == []


def test_listing_stamp_only_for_sounds_and_equal_to_stat(tmp_path):
    g, df = install(tmp_path)
    voices(df, 5)
    tree = m.DataTree(str(df))
    seen = 0
    for i, top, rel, full in tree.asset_entries(ah.ASSET_DIRS):
        ls = tree.listed_stamp(i)
        if top in ("sound", "music"):
            assert ls == ah.stamp_of(os.stat(full))
            seen += 1
        else:
            assert ls is None
    assert seen == 5
    assert list(tree.asset_files(ah.ASSET_DIRS)) == [e[1:] for e in tree.asset_entries(ah.ASSET_DIRS)]


def _count_sound_stats(monkeypatch):
    calls = []
    real = m.DataTree.stat

    def stat(self, full):
        if os.sep + "sound" + os.sep in full.lower():
            calls.append(full)
        return real(self, full)
    monkeypatch.setattr(m.DataTree, "stat", stat)
    return calls


def test_run_2_needs_no_stat_for_cached_healthy_sounds(tmp_path, capsys, monkeypatch):
    g, df = install(tmp_path)
    voices(df)
    (df / "Sound/fx/stereo.wav").write_bytes(wav(ch=2))
    calls = _count_sound_stats(monkeypatch)
    out1 = run(df, capsys)
    assert len(calls) == 31                             # run 1: nothing cached, every sound stat-ed and read
    assert "stereo.wav: stereo" in out1
    calls.clear()
    reopen(g)
    out2 = run(df, capsys)
    # the 30 healthy voices come from the cache by their listing stamp; the stereo one (a problem) is
    # confirmed with os.stat and still reported
    assert [os.path.basename(c) for c in calls] == ["stereo.wav"]
    assert "stereo.wav: stereo" in out2
    rows = ah.shared_cache(str(g)).d
    assert sum(1 for k in rows if k.startswith("snd:sound\\vo\\")) == 30


def test_stale_listing_never_hides_a_cached_problem(tmp_path, capsys, monkeypatch):
    """A listing stamp that points at an old cached problem is checked against the real file; an empty file
    (listed as 0 bytes) always goes through os.stat and is reported."""
    g, df = install(tmp_path)
    (df / "Sound/fx/fine.wav").write_bytes(wav())
    (df / "Sound/fx/now_empty.wav").write_bytes(wav())
    run(df, capsys)
    cache = reopen(g)
    st = os.stat(df / "Sound/fx/fine.wav")
    fake = "%d:%d" % (st.st_size + 1, int(st.st_mtime))
    cache.put("snd:sound\\fx\\fine.wav", fake, [2, 44100])       # an old, stereo version of the file
    cache.flush()
    (df / "Sound/fx/now_empty.wav").write_bytes(b"")
    real = m.DataTree.listed_stamp

    def listed(self, i):
        return fake if self.files[i][1].lower().endswith("fine.wav") else real(self, i)
    monkeypatch.setattr(m.DataTree, "listed_stamp", listed)
    out = run(df, capsys)
    assert "fine.wav: stereo" not in out
    assert "now_empty.wav: empty file" in out


def test_generated_sound_always_read_in_full(tmp_path, capsys, monkeypatch):
    g, df = install(tmp_path)
    (df / "Sound/fx/standin.wav").write_bytes(wav())
    monkeypatch.setattr(m, "generated_rels", lambda gd: {"sound\\fx\\standin.wav"})
    run(df, capsys)
    calls = _count_sound_stats(monkeypatch)
    reopen(g)
    run(df, capsys)
    assert [os.path.basename(c) for c in calls] == ["standin.wav"]
