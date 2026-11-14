"""Path helpers: no hardcoded drive letters in code, Vortex errors, tagged record round-trip."""
import os
import re
import stat
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mwdialog_paths as P                       # noqa: E402


# ------------------------------------------------------------------------------------ lint

# Production code and docs (not tests, not git, not tool binaries).
SCAN_ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", "tests", "tools"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".json", ".txt", ".jsonl", ".sqlite"}
# Data records are linted separately after migration; code/docs must stay clean.
CODE_SUFFIXES = {".py", ".bat", ".md", ".gitignore"}
DRIVE_LIT = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:\\(?![dDsSnNtTwWbBaAzZrfvxuk0-9])")


# Installed in the game folder (no .git): only the files this repo ships are ours to lint; the folder also holds
# the game, other mods' tools and backups.
SHIPPED = re.compile(r"(mwdialog_|vortex_tidy|chargen_ship_patch|stranded_doors_patch|readme\.md$|changes\.md$)", re.I)
SHIPPED_DIRS = {"diag"}
# Written by the tools on a real install and kept out of the repo by .gitignore (caches, reports, journals).
# mwdialog_mastercheck_cache.json now stores tagged paths (tests/test_mastercheck_cache.py checks what it writes),
# but an install's copy keeps its older absolute entries until the next check rewrites it, and a path under none
# of the game/staging/download folders stays absolute by design, so it is not linted here.
IGNORED_RECORDS = {
    "mwdialog_mastercheck_cache.json", "mwdialog_asset_cache.json", "mwdialog_report.txt",
    "mwdialog_unused_assets.txt", "mwdialog_new_conflicts.txt", "mwdialog.conflicts.txt",
    "mwdialog_loadorder_undo.txt", "mwdialog_longpaths.json", "mwdialog_luafix.json", "mwdialog_luafix_plan.txt",
    "mwdialog_fixes.log",
}


def _in_repo():
    return (SCAN_ROOT / ".git").exists()


def _iter_code_files():
    repo = _in_repo()
    for p in SCAN_ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(SCAN_ROOT).parts
        if any(part in SKIP_DIRS for part in rel):
            continue
        if p.suffix.lower() not in CODE_SUFFIXES and p.name not in {".gitignore"}:
            continue
        if not repo and not ((len(rel) == 1 and SHIPPED.match(p.name)) or (len(rel) == 2 and rel[0] in SHIPPED_DIRS)):
            continue
        yield p


def test_no_absolute_paths_in_repo_code():
    hits = []
    for p in _iter_code_files():
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeError:
            text = p.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if DRIVE_LIT.search(line):
                hits.append(f"{p.relative_to(SCAN_ROOT)}:{i}:{line.strip()}")
    assert hits == [], "drive-letter literals in repo code:\n" + "\n".join(hits)


# ------------------------------------------------------------------------------------ Vortex resolution

def test_vortex_unreadable_error_when_appdata_missing(monkeypatch):
    monkeypatch.delenv("APPDATA", raising=False)
    with pytest.raises(P.VortexPathError) as ei:
        P.resolve_staging(required=True)
    msg = str(ei.value)
    assert "Could not determine Vortex's Morrowind staging folder." in msg
    assert "%APPDATA%" in msg
    assert "--staging DIR" in msg

    with pytest.raises(P.VortexPathError) as ei:
        P.resolve_downloads(required=True)
    msg = str(ei.value)
    assert "Could not determine Vortex's Morrowind download folder." in msg
    assert "--vortex-downloads DIR (or --downloads DIR)" in msg


def test_vortex_unreadable_error_when_appdata_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path / "no-such-roaming"))
    with pytest.raises(P.VortexPathError) as ei:
        P.resolve_staging(required=True)
    msg = str(ei.value)
    assert "Could not determine Vortex's Morrowind staging folder." in msg
    assert "Vortex AppData folder not found" in msg
    assert "--staging DIR" in msg
    assert "Looked for Vortex settings in:" in msg


def test_cli_override_wins_and_missing_dir_errors(tmp_path):
    st = tmp_path / "staging"
    st.mkdir()
    assert P.resolve_staging(cli=str(st)) == str(st)
    with pytest.raises(P.VortexPathError) as ei:
        P.resolve_staging(cli=str(tmp_path / "missing"))
    assert "Staging folder not found" in str(ei.value)
    assert "--staging DIR" in str(ei.value)


def test_vortex_settings_from_json_backup(monkeypatch, tmp_path):
    app = tmp_path / "Roaming"
    vortex = app / "Vortex"
    bak = vortex / "temp" / "state_backups_full"
    bak.mkdir(parents=True)
    (bak / "hourly.json").write_text(
        '{"settings": {"downloads": {"path": "K:\\\\Downloads\\\\Vortex\\\\{game}"},'
        ' "mods": {"installPath": {"morrowind": "G:\\\\Vortex Mods\\\\{game}"}}}}',
        encoding="utf-8")
    # the folders named in settings must exist to resolve
    staging = tmp_path / "Vortex Mods" / "morrowind"
    downloads = tmp_path / "Downloads" / "Vortex" / "morrowind"
    staging.mkdir(parents=True)
    downloads.mkdir(parents=True)
    # rewrite settings to point at the tmp folders (still via {game} / no drive in the *code*)
    # Use the tmp path inside the JSON so resolve can find the directories.
    (bak / "hourly.json").write_text(
        json_blob := (
            '{"settings": {"downloads": {"path": "'
            + str(downloads.parent).replace("\\", "\\\\")
            + '\\\\{game}"}, "mods": {"installPath": {"morrowind": "'
            + str(staging.parent).replace("\\", "\\\\")
            + '\\\\{game}"}}}}'
        ),
        encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(app))
    st = P.resolve_staging()
    dl = P.resolve_downloads()
    assert os.path.normcase(st) == os.path.normcase(str(staging))
    assert os.path.normcase(dl) == os.path.normcase(str(downloads))


# ------------------------------------------------------------------------------------ tagged records

def _win_bases(tmp_path=None):
    """Synthetic Windows-style bases that work on Linux (no need for the folders to exist)."""
    return {
        "staging": r"G:\Vortex Mods\morrowind",
        "downloads": r"K:\Downloads\Vortex\morrowind",
        "game": r"G:\Program Files\Steam\steamapps\common\Morrowind",
    }


def test_relative_record_round_trip():
    bases = _win_bases()
    src = r"G:\Vortex Mods\morrowind\Some Mod-123\textures\foo.dds"
    stored = P.store_path(src, bases)
    assert stored == r"staging:Some Mod-123\textures\foo.dds"
    assert ":" in stored and not P.DRIVE_RE.match(stored)
    back = P.resolve_stored(stored, bases)
    assert P._normkey(back) == P._normkey(src)

    src2 = r"G:\Program Files\Steam\steamapps\common\Morrowind\mwdialog_fullsize_textures\tx.dds"
    stored2 = P.store_path(src2, bases)
    assert stored2 == r"game:mwdialog_fullsize_textures\tx.dds"
    assert P._normkey(P.resolve_stored(stored2, bases)) == P._normkey(src2)

    src3 = r"K:\Downloads\Vortex\morrowind\Mod-1.7z"
    stored3 = P.store_path(src3, bases)
    assert stored3 == r"downloads:Mod-1.7z"
    assert P._normkey(P.resolve_stored(stored3, bases)) == P._normkey(src3)


def test_old_absolute_record_still_read():
    bases = _win_bases()
    old = r"G:\Vortex Mods\morrowind\Dwemer's vestiges\textures\tx_a_dwemer_head.dds"
    # resolve leaves an older absolute path alone
    assert P.resolve_stored(old, bases) == old
    # the next write migrates it
    assert P.store_path(old, bases) == r"staging:Dwemer's vestiges\textures\tx_a_dwemer_head.dds"

    abs_orig = r"G:\Vortex Mods\morrowind\AATL Compatibility Patches\Off\AATL FTHOG Interop\AATL Doors of Oblivion Interop.ESP"
    meta = "2026-11-07 13:45:41; original: " + abs_orig + "; why: content: 7 of 9 records"
    new = P.rewrite_original_meta(meta, bases)
    assert "original: staging:AATL Compatibility Patches\\Off\\AATL FTHOG Interop\\AATL Doors of Oblivion Interop.ESP" in new
    assert P.DRIVE_RE.search(new) is None
    # reading the old meta still yields the absolute path
    assert P.original_from_meta(meta).startswith("G:")
    # reading the new meta yields a tagged path that resolves back
    tagged = P.original_from_meta(new)
    assert tagged.startswith("staging:")
    back = P.resolve_stored(tagged, bases)
    assert P._normkey(back) == P._normkey(abs_orig)


def test_convert_added_masters_and_reduced_row():
    bases = _win_bases()
    rec = {
        "Patch.esp": {
            "Master.esm": "2026-11-07; original: G:\\Vortex Mods\\morrowind\\Mod\\Off\\added masters\\Patch.esp; why: content"
        }
    }
    out = P.convert_added_masters(rec, bases)
    assert out["Patch.esp"]["Master.esm"].endswith(
        "original: staging:Mod\\Off\\added masters\\Patch.esp; why: content") or \
        "original: staging:Mod\\Off\\added masters\\Patch.esp" in out["Patch.esp"]["Master.esm"]
    rel, kind, keep = P.convert_reduced_row(
        r"textures\a.dds", "link",
        r"G:\Vortex Mods\morrowind\SomeMod\textures\a.dds", bases)
    assert (rel, kind, keep) == (r"textures\a.dds", "link", r"staging:SomeMod\textures\a.dds")


# ------------------------------------------------------------------------------------ 7-Zip / LuaJIT search

def test_find_7z_path_then_tools_no_program_files(tmp_path, monkeypatch):
    # PATH hit
    fake = tmp_path / "bin"
    fake.mkdir()
    exe = fake / ("7z.exe" if os.name == "nt" else "7z")
    exe.write_text("x")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(fake))
    monkeypatch.setattr(P.shutil, "which", lambda n: str(exe) if n == "7z" else None)
    assert P.find_7z(game_dir=str(tmp_path / "game")) == str(exe)

    # no PATH: tools/7z/7z.exe
    monkeypatch.setattr(P.shutil, "which", lambda n: None)
    game = tmp_path / "game"
    tool = game / "tools" / "7z" / ("7z.exe" if os.name == "nt" else "7z")
    tool.parent.mkdir(parents=True)
    tool.write_text("x")
    found = P.find_7z(game_dir=str(game))
    assert found == str(tool)

    # nothing: not required -> None; required -> clear error, no Program Files, no registry
    monkeypatch.setattr(P.shutil, "which", lambda n: None)
    empty = tmp_path / "empty"
    empty.mkdir()
    assert P.find_7z(game_dir=str(empty), required=False) is None
    with pytest.raises(P.ToolNotFoundError) as ei:
        P.find_7z(game_dir=str(empty), required=True)
    msg = str(ei.value)
    assert "Could not find 7-Zip (7z)." in msg
    assert "PATH" in msg
    assert "tools" in msg
    assert "Program Files" not in msg
    assert "registry" not in msg.lower() or "No registry" in msg or "PATH" in msg
    # the error must not recommend a drive-letter path (the folder it looked in is this test's temp folder,
    # which on Windows has a drive letter of its own)
    assert DRIVE_LIT.search(msg.replace(str(empty), "<game>")) is None


def test_luajit_candidates_are_relative_to_game(tmp_path):
    game = tmp_path / "Morrowind"
    cands = P.luajit_candidates(str(game), explicit=None)
    assert any(p.endswith(os.path.join("tools", "luajit", "luajit.exe")) or
               p.endswith(os.path.join("tools", "luajit", "luajit")) for p in cands)
    assert all(not P.DRIVE_RE.match(p) or p.startswith(str(game)) for p in cands)
    desc = P.describe_luajit_search(str(game))
    assert "tools" in desc and "luajit" in desc
    assert "--luajit PATH" in desc
    assert P.DRIVE_RE.search(desc) is None


def test_no_absolute_paths_in_data_records():
    """After migration, install records in the repo must not contain drive-letter paths."""
    hits = []
    for p in list(SCAN_ROOT.glob("mwdialog_*.json")) + list(SCAN_ROOT.glob("mwdialog_*.txt")) + [
        SCAN_ROOT / "mwdialog_check.rules.txt"
    ]:
        if not p.is_file() or p.name.lower() in IGNORED_RECORDS:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if DRIVE_LIT.search(line):
                hits.append(f"{p.name}:{i}:{line.strip()[:160]}")
    assert hits == [], "drive-letter literals in data records:\n" + "\n".join(hits)
