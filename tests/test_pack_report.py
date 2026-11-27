"""vortex_tidy.py --pack-report (mwdialog_report): one scrubbed archive of the logs for a bug report.

Temp folders only, no Steam. The user, the game, staging and downloads are all made up here (the environment is
pointed at a fake profile), so nothing real is read or written.
"""
import hashlib
import os
import re
import sys
import zipfile
from pathlib import Path

import pytest

from conftest import _load, vt
from test_staged_only import Guard, put

MR = _load("mwdialog_report")
MS = _load("mwdialog_staged")
MP = vt.MP
USER = "Zorbathrax"

pytestmark = pytest.mark.skipif(MP.find_7z() is None, reason="needs the bundled 7-Zip (tools\\7z)")


def tree_state(root):
    out = {}
    for base, dirs, fns in os.walk(root):
        for d in dirs:
            out[os.path.relpath(os.path.join(base, d), root) + os.sep] = None
        for fn in fns:
            p = os.path.join(base, fn)
            with open(p, "rb") as f:
                out[os.path.relpath(p, root)] = (hashlib.sha256(f.read()).hexdigest(), os.stat(p).st_mtime_ns)
    return out


def forms(p):
    p = str(p)
    return {"plain": p, "fwd": p.replace("\\", "/"), "json": p.replace("\\", "\\\\"), "upper": p.upper()}


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A fake user, game, staging and downloads; --pack-report is pointed at them."""
    profile = tmp_path / "Users" / USER
    game = tmp_path / "Games" / "Morrowind"
    staging = tmp_path / "vortex" / "morrowind"
    downloads = tmp_path / "dl" / "morrowind"
    for d in (profile, staging, downloads):
        d.mkdir(parents=True)
    for var in ("USERNAME", "LOGNAME", "USER", "LNAME"):
        monkeypatch.setenv(var, USER)
    monkeypatch.setenv("USERPROFILE", str(profile))
    monkeypatch.setenv("HOME", str(profile))
    put(game / "Morrowind.ini", "[Game Files]\nGameFile0=Morrowind.esm\n")
    put(game / "Data Files" / "Loose.esp", b"TES3 not a source")
    put(game / "Data Files" / "MWSE" / "config" / "mwguard.json", "{}")
    put(game / "conflict-tools" / "plans" / "vortex_tidy_plan.txt", f"plan for {game}\n")
    put(game / "conflict-tools" / "tools.py", "not a source\n")
    log = [f"loaded {forms(game)['plain']}\\Data Files\\a.esp",
           f"fwd {forms(game)['fwd']}/Data Files/b.esp",
           f"json {forms(game)['json']}",
           f"upper {forms(game)['upper']}",
           f"stage {staging}\\Mod One\\x.lua",
           f"dl {downloads}\\a.7z",
           f"tmp {profile}\\AppData\\Local\\Temp\\x",
           f"user {USER.upper()} and {USER.lower()} but not {USER}es or x{USER}",
           "an ordinary line"]
    put(game / "MWSE.log", "\r\n".join(log) + "\r\n")
    put(game / "Data Files" / "MWSE" / "logs" / "ticker.log", f"[ticker] {game}\\x\n{USER}\n")
    put(game / "Data Files" / "MWSE" / "logs" / "sub" / "x.log", "quiet\n")
    gen = game / "conflict-tools" / "generated"
    put(gen / "journal.txt", f"{forms(staging)['fwd']}/m\n{forms(downloads)['json']}\n")
    put(gen / "empty.txt", "nothing to scrub\n")
    put(gen / "latin.log", b"caf\xe9 " + str(game).encode() + b"\n")
    put(gen / "cache.sqlite", b"SQLite format 3\x00" + str(game).encode() + b"\x00" + USER.encode())
    put(gen / "utf16.txt", (str(game) + USER).encode("utf-16"))
    put(gen / "dummy" / "x.nif", b"NIF\x00\x01")
    monkeypatch.setattr(vt, "HERE", str(game))
    monkeypatch.setattr(vt, "JOURNAL", str(tmp_path / "no_journal.jsonl"))
    monkeypatch.setattr(MP, "resolve_staging", lambda *a, **k: str(staging))
    monkeypatch.setattr(MP, "resolve_downloads", lambda *a, **k: str(downloads))
    systemp = tmp_path / "systemp"
    systemp.mkdir()
    monkeypatch.setattr(MR.tempfile, "tempdir", str(systemp))
    return type("W", (), dict(tmp=tmp_path, game=game, staging=staging, downloads=downloads, profile=profile,
                              gen=gen, systemp=systemp, reports=game / "conflict-tools" / "reports"))


def run(monkeypatch, *extra):
    monkeypatch.setattr(vt.sys, "argv", ["vortex_tidy.py", "--pack-report", *extra])
    return vt.main()


def extract(archive, into):
    with zipfile.ZipFile(archive) as z:
        z.extractall(into)
        return sorted(n for n in z.namelist() if not n.endswith("/"))


def counts_of(summary):
    return {m.group(2): int(m.group(1)) for m in re.finditer(r"^ +(\d+)  (\S.*)$", summary, re.M)}


EXPECTED = {"MWSE.log", "MWSE-logs/ticker.log", "MWSE-logs/sub/x.log", "generated/journal.txt",
            "generated/empty.txt", "generated/latin.log", "scrub-summary.txt"}


def make(world, monkeypatch, capsys):
    assert not world.reports.exists()
    assert run(monkeypatch) == 0
    out = capsys.readouterr().out
    return out


def test_one_line_the_archive_path_in_the_reports_folder(world, monkeypatch, capsys):
    out = make(world, monkeypatch, capsys)
    lines = out.splitlines()
    assert len(lines) == 1                                   # exactly one plain line, never wrapped
    archive = Path(lines[0])
    assert archive.parent == world.reports and archive.is_file()
    assert re.fullmatch(r"conflict-tools-report-\d{8}-\d{6}\.zip", archive.name)
    assert [p.name for p in world.reports.iterdir()] == [archive.name]


def test_only_the_listed_sources_and_the_summary_are_in_the_archive(world, monkeypatch, capsys, tmp_path):
    archive = make(world, monkeypatch, capsys).strip()
    names = extract(archive, tmp_path / "x")
    assert set(names) == EXPECTED
    # nothing from outside the three sources: not the ini, a plugin, mwguard.json, plans\, tools or generated\dummy
    assert not any(re.search(r"Morrowind\.ini|Loose|mwguard|plans|tools\.py|dummy|sqlite|utf16", n) for n in names)


def test_originals_are_byte_identical_and_data_files_is_only_read(world, monkeypatch, capsys):
    before = tree_state(world.tmp)
    g = watch_for(world, monkeypatch)
    make(world, monkeypatch, capsys)
    assert g.writes == []                                    # nothing written to Data Files
    assert g.reads == []                                     # and only the documented MWSE\logs\ read
    after = tree_state(world.tmp)
    new = {k for k in after if k not in before}
    assert len(new) == 2
    assert {k for k in before if k not in after} == set()    # nothing deleted or moved
    assert all(after[k] == before[k] for k in before if before[k] is not None)   # bytes AND dates unchanged
    assert {os.path.relpath(world.reports, world.tmp) + os.sep} <= new       # only the reports folder and file are new
    assert os.listdir(world.systemp) == []                   # the temp work folder is gone


def watch_for(world, monkeypatch):
    import builtins
    g = Guard(world.game / "Data Files")
    real_open, real_scandir, real_listdir = builtins.open, os.scandir, os.listdir

    def fake_open(file, mode="r", *a, **k):
        if not isinstance(file, int):
            (g.write if set("wax+") & set(mode) else g.read)(file)
        return real_open(file, mode, *a, **k)

    def scan(path=".", _r=real_scandir):
        if not isinstance(path, int):
            g.read(path)
        return _r(path)

    def lst(path=".", _r=real_listdir):
        if not isinstance(path, int):
            g.read(path)
        return _r(path)
    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(os, "scandir", scan)
    monkeypatch.setattr(os, "listdir", lst)
    return g


def test_the_reports_folder_is_made_only_when_needed(world, monkeypatch, capsys):
    monkeypatch.setattr(MP, "find_7z", lambda *a, **k: None)
    assert run(monkeypatch) == 2
    cap = capsys.readouterr()
    assert cap.out == "" and "7-Zip" in cap.err
    assert not world.reports.exists() and os.listdir(world.systemp) == []
    monkeypatch.undo()


def test_a_second_report_in_the_same_second_does_not_overwrite(world, monkeypatch, capsys):
    import time
    fixed = time.localtime(1_800_000_000)
    a = MR.pack_report(str(world.game), [str(world.staging)], [str(world.downloads)], now=fixed)
    b = MR.pack_report(str(world.game), [str(world.staging)], [str(world.downloads)], now=fixed)
    assert os.path.isfile(a) and os.path.isfile(b) and a != b and b.endswith("-2.zip")


def test_summary_counts_are_right_and_list_exclusions_without_contents(world, monkeypatch, capsys, tmp_path):
    archive = make(world, monkeypatch, capsys).strip()
    extract(archive, tmp_path / "x")
    summary = (tmp_path / "x" / "scrub-summary.txt").read_text(encoding="utf-8")
    counts = counts_of(summary)
    assert counts["MWSE.log"] == 9
    assert counts["MWSE-logs/ticker.log"] == 2               # the game path and the user name
    assert counts["MWSE-logs/sub/x.log"] == 0
    assert counts["generated/journal.txt"] == 2              # staging (forward slashes) and downloads (doubled)
    assert counts["generated/empty.txt"] == 0
    assert counts["generated/latin.log"] == 1
    assert counts["total"] == 9 + 2 + 2 + 1
    assert "Skipped (not found):\n  none" in summary
    for excluded in ("generated/cache.sqlite", "generated/utf16.txt", "generated/dummy/x.nif"):
        assert excluded in summary
    assert "binary" in summary
    assert USER.lower() not in summary.lower()
    assert not re.search(r"[A-Za-z]:[\\/]", summary)         # counts and names only: no paths, no contents


def test_missing_sources_are_skipped_and_noted(world, monkeypatch, capsys, tmp_path):
    (world.game / "MWSE.log").unlink()
    import shutil
    shutil.rmtree(world.game / "Data Files" / "MWSE" / "logs")
    shutil.rmtree(world.gen)
    archive = make(world, monkeypatch, capsys).strip()
    assert extract(archive, tmp_path / "x") == ["scrub-summary.txt"]
    summary = (tmp_path / "x" / "scrub-summary.txt").read_text(encoding="utf-8")
    for label in ("MWSE.log", "Data Files\\MWSE\\logs\\", "conflict-tools\\generated\\"):
        assert f"  {label}\n" in summary


def test_no_user_path_or_name_survives_anywhere_in_the_archive(world, monkeypatch, capsys, tmp_path):
    archive = make(world, monkeypatch, capsys).strip()
    names = extract(archive, tmp_path / "x")
    texts = {n: (tmp_path / "x" / n).read_bytes() for n in names}
    for n, data in texts.items():
        low = data.decode("latin-1").lower()
        low_names = low.replace("x" + USER.lower(), "").replace(USER.lower() + "es", "")   # not-a-token look-alikes
        assert USER.lower() not in low_names, n
        assert not re.search(r"[A-Za-z]:[\\/]", low), (n, re.findall(r"[A-Za-z]:[\\/].{0,40}", low)[:2])
        assert str(world.tmp).lower().replace("\\", "/") not in low.replace("\\\\", "/").replace("\\", "/"), n
    log = texts["MWSE.log"].decode("utf-8")
    assert log.count("<MORROWIND>") == 4 and log.count("<STAGING>") == 1 and log.count("<DOWNLOADS>") == 1
    assert log.count("<USERPROFILE>") == 1 and log.count("<USERNAME>") == 2
    assert f"not {USER}es or x{USER}" in log                  # whole tokens only
    assert "<MORROWIND>\\Data Files\\a.esp" in log and "<MORROWIND>/Data Files/b.esp" in log
    assert "<USERPROFILE>\\AppData\\Local\\Temp\\x" in log
    assert "\r\n" in log                                     # line endings kept
    assert texts["generated/latin.log"] == b"caf\xe9 <MORROWIND>\n"      # non-UTF-8 bytes kept exactly
    assert "<STAGING>/m" in texts["generated/journal.txt"].decode()
    assert "<DOWNLOADS>" in texts["generated/journal.txt"].decode()


def test_longest_match_first_staging_inside_the_profile(world, monkeypatch, capsys, tmp_path):
    inside = world.profile / "Mods" / "morrowind"
    inside.mkdir(parents=True)
    monkeypatch.setattr(MP, "resolve_staging", lambda *a, **k: str(inside))
    put(world.game / "MWSE.log", f"mod {inside}\\A\\b.lua\nprofile {world.profile}\\Documents\n")
    archive = make(world, monkeypatch, capsys).strip()
    extract(archive, tmp_path / "x")
    log = (tmp_path / "x" / "MWSE.log").read_text(encoding="utf-8")
    assert log == "mod <STAGING>\\A\\b.lua\nprofile <USERPROFILE>\\Documents\n"


def test_scrubber_forms_and_boundaries():
    sc = MR.Scrubber(r"C:\Games\Morrowind", [r"D:\Vortex Mods\morrowind"], [r"E:\dl"], [r"C:\Users\Zed"], ["Zed"])
    cases = {
        r"C:\Games\Morrowind\Data Files": "<MORROWIND>\\Data Files",
        "c:/games/morrowind/x": "<MORROWIND>/x",
        r"C:\\Games\\Morrowind\\x": "<MORROWIND>\\\\x",
        r"\\?\C:\Games\Morrowind\x": "<MORROWIND>\\x",
        r"C:\Games\Morrowind2\x": r"C:\Games\Morrowind2\x",           # a sibling is not the game folder
        r"D:\Vortex Mods\morrowind\A": "<STAGING>\\A",
        r"E:\DL\a.7z": "<DOWNLOADS>\\a.7z",
        r"C:\Users\Zed\AppData": "<USERPROFILE>\\AppData",
        "Zed, zed and ZED: Zeds Zed_x": "<USERNAME>, <USERNAME> and <USERNAME>: Zeds Zed_x",
        "file:///C:/Games/Morrowind/x": "file:///<MORROWIND>/x",
    }
    for src, want in cases.items():
        got, n = sc.scrub(src)
        assert got == want, (src, got)
        assert n == (0 if got == src else n)


def test_cli_rejects_other_switches_and_has_no_output_option(world, monkeypatch, capsys):
    for extra in ("--apply", "--undo", "--lua-only"):
        monkeypatch.setattr(vt.sys, "argv", ["vortex_tidy.py", "--pack-report", extra])
        with pytest.raises(SystemExit) as e:
            vt.main()
        assert e.value.code == 2
    assert not world.reports.exists()
    monkeypatch.setattr(vt.sys, "argv", ["vortex_tidy.py", "--pack-report", "--report-dir", str(world.tmp)])
    with pytest.raises(SystemExit):
        vt.main()


def test_not_in_a_game_folder_is_an_error(world, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(vt, "HERE", str(tmp_path / "nowhere"))
    assert run(monkeypatch) == 2
    assert "No Morrowind folder" in capsys.readouterr().err


def test_reports_are_never_deployed_synced_or_committed():
    root = Path(__file__).resolve().parents[1]
    assert "reports/" in (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    sys.path.insert(0, str(root))
    deploy = pytest.importorskip("deploy", reason="deploy.py is not vendored here (MWManager)")
    assert deploy.never("reports/conflict-tools-report-20260101-000000.zip")
    assert deploy.never("conflict-tools/reports/x.zip")


def test_the_log_read_is_a_documented_exception():
    data = r"C:\Game\Data Files"
    assert MS.is_read_exception(data + r"\MWSE\logs\ticker.log", data)
    assert MS.is_read_exception(data + r"\MWSE\logs", data)
    assert not MS.is_read_exception(data + r"\MWSE\core\x.lua", data)
    assert not MS.is_read_exception(data + r"\MWSE\logsx\a.log", data)
    assert not MS.is_read_exception(data + r"\Loose.esp", data)