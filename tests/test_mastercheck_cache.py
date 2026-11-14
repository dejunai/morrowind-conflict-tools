"""mwdialog_mastercheck_cache.json stores its paths like the other records: game:/staging:/downloads: plus a path
relative to that folder. Older absolute entries still load and are stored tagged on the next save; a path under
none of the folders is kept (and named); a tag whose folder isn't known this run is left alone. Temp folders only."""
import json
import os
import re
import zipfile

from conftest import m, plugin
from test_mastercheck import cont, game  # noqa: F401  (fixture)

mc = m.mastercheck_module()
DRIVE_OR_ABS = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]")


def _setup(g, df, tmp_path):
    mor = os.path.getsize(df / "Morrowind.esm")
    foo = os.path.getsize(df / "Fooland.esp")
    recs = [cont("pt_box", ["zz_a", "zz_b", "zz_c", "zz_d"])]
    orig = plugin(tmp_path / "orig.esp", [("Morrowind.esm", mor), ("Fooland.esp", 999)], recs)
    plugin(df / "Fooland Patch.esp", [("Morrowind.esm", mor), ("Fooland.esp", foo)], recs)
    (g / "mwdialog_fixes.log").write_text("Fooland Patch.esp: x -> synced the size recorded for 'Morrowind.esm' (1 -> 2)\n")
    staging, dl = tmp_path / "staging", tmp_path / "dl"
    mod = staging / "Fooland Patch-123-1-0-1700000000"
    mod.mkdir(parents=True)
    (mod / "Fooland Patch.esp").write_bytes(open(df / "Fooland Patch.esp", "rb").read())
    dl.mkdir()
    arc = dl / "Fooland Patch-123-1-0-1700000000.zip"
    with zipfile.ZipFile(arc, "w") as zf:
        zf.writestr("00 Core/Fooland Patch.esp", orig)
    return staging, dl, arc


def _run(g, df, staging, dl, *extra):
    m.main([str(df), "--plugins", "Morrowind.esm", "Fooland.esp", "Fooland Patch.esp", "--no-vortex",
            "--vortex-dir", str(staging), "--vortex-downloads", str(dl), "--fix-log", str(g / "mwdialog_fixes.log"),
            *extra])
    return (g / mc.CACHE_FILE).read_text(encoding="utf-8")


def test_cache_is_written_with_tagged_paths_and_read_back(game, tmp_path, monkeypatch):
    g, df = game
    staging, dl, arc = _setup(g, df, tmp_path)
    raw = _run(g, df, staging, dl)
    cache = json.loads(raw)
    assert str(tmp_path) not in raw and not DRIVE_OR_ABS.search(raw)
    assert cache["archives"] and all(k.startswith("downloads:") for k in cache["archives"])
    assert all(c["archive"] == "downloads:" + arc.name for v in cache["archives"].values() for c in v)
    assert cache["logs"] and all(k.startswith("game:") for k in cache["logs"])
    # second run: the archive is not read again (the tagged key resolves to the same archive)
    monkeypatch.setattr(mc, "plugins_in_archive", lambda *a, **k: (_ for _ in ()).throw(AssertionError("re-read")))
    assert json.loads(_run(g, df, staging, dl))["archives"] == cache["archives"]


def test_old_absolute_entries_still_load_and_are_stored_tagged(game, tmp_path, monkeypatch):
    g, df = game
    staging, dl, arc = _setup(g, df, tmp_path)
    tagged = json.loads(_run(g, df, staging, dl))
    bases = {"game": str(g), "staging": str(staging), "downloads": str(dl)}
    old = mc.load_cache(str(g / mc.CACHE_FILE), bases)          # the paths as an older version wrote them
    assert all(os.path.isabs(k.rsplit("|", 3)[0]) for k in old["archives"])
    (g / mc.CACHE_FILE).write_text(json.dumps(old), encoding="utf-8")
    monkeypatch.setattr(mc, "plugins_in_archive", lambda *a, **k: (_ for _ in ()).throw(AssertionError("re-read")))
    again = json.loads(_run(g, df, staging, dl))
    assert again["archives"] == tagged["archives"] and again["logs"].keys() == tagged["logs"].keys()


def test_paths_outside_every_folder_are_kept_and_named(game, tmp_path, capsys):
    g, df = game
    staging, dl, _arc = _setup(g, df, tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    log = other / "fixes.log"
    log.write_text("Fooland Patch.esp: x -> synced the size recorded for 'Morrowind.esm' (1 -> 2)\n")
    capsys.readouterr()
    m.main([str(df), "--plugins", "Morrowind.esm", "Fooland.esp", "Fooland Patch.esp", "--no-vortex",
            "--vortex-dir", str(staging), "--vortex-downloads", str(dl), "--fix-log", str(log)])
    cache = json.loads((g / mc.CACHE_FILE).read_text(encoding="utf-8"))
    assert os.path.normcase(str(log)) in cache["logs"]
    assert "path(s) under none of the game, staging and download folders" in " ".join(capsys.readouterr().err.split())


def test_a_tag_with_no_folder_this_run_is_left_alone(game, tmp_path):
    g, df = game
    staging, dl, _arc = _setup(g, df, tmp_path)
    before = json.loads(_run(g, df, staging, dl))
    m.main([str(df), "--plugins", "Morrowind.esm", "Fooland.esp", "Fooland Patch.esp", "--no-vortex",
            "--no-archive-lookup", "--fix-log", str(g / "mwdialog_fixes.log")])
    after = json.loads((g / mc.CACHE_FILE).read_text(encoding="utf-8"))
    assert after["archives"] == before["archives"]               # still downloads:..., not lost or broken


def test_load_and_save_round_trip(tmp_path):
    g, s, d = tmp_path / "g", tmp_path / "s", tmp_path / "d"
    bases = {"game": str(g), "staging": str(s), "downloads": str(d)}
    arc = os.path.join(str(d), "Mod-1-1.7z")
    mem = {"logs": {os.path.normcase(os.path.join(str(g), "mwdialog_fixes.log")): {"offset": 3}},
           "archives": {f"{os.path.normcase(arc)}|10|20|patch.esp": [{"archive": arc, "masters": []}]},
           "verdicts": {"patch.esp|m.esp": {"from_archive": arc, "kind": "different mod"}},
           "evidence": {"patch.esp|m.esp": ["x"]}}
    path = str(tmp_path / "c.json")
    assert mc.save_cache(path, mem, bases) == []
    raw = json.load(open(path))
    assert list(raw["logs"]) == ["game:mwdialog_fixes.log"]
    assert list(raw["archives"])[0].startswith("downloads:") and list(raw["archives"])[0].endswith("|10|20|patch.esp")
    assert raw["verdicts"]["patch.esp|m.esp"]["from_archive"] == "downloads:Mod-1-1.7z"
    assert mc.load_cache(path, bases) == mem
