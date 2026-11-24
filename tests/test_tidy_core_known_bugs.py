"""vortex_tidy checks MWSE's own core files that a Known Bugs rule names (KB3, KB4) where MWSE's updater puts
them, Data Files, and offers the patch in place; a staged mod that ships MWSE is checked there instead."""
import os
import shutil
import types

import vortex_tidy as T

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "mwse")
REL = os.path.join("MWSE", "core", "mcm", "components", "pages", "ExclusionsPage.lua")


def run(tmp_path, monkeypatch, ship_in_staging=False):
    game = tmp_path / "Morrowind"
    data = game / "Data Files"
    (data / REL).parent.mkdir(parents=True)
    shutil.copy(os.path.join(FIX, "ExclusionsPage.lua"), data / REL)
    staging = tmp_path / "staging"
    (staging / "Some Mod" / "MWSE" / "mods" / "some").mkdir(parents=True)
    (staging / "Some Mod" / "MWSE" / "mods" / "some" / "main.lua").write_text("local x = 1\n")
    if ship_in_staging:
        (staging / "MWSE" / REL).parent.mkdir(parents=True)
        shutil.copy(os.path.join(FIX, "ExclusionsPage.lua"), staging / "MWSE" / REL)
    monkeypatch.setattr(T, "HERE", str(game))
    monkeypatch.setattr(T, "blacklist", lambda create=False: [])
    args = types.SimpleNamespace(staging=str(staging), only=None, skip=None, apply=False, luajit=None,
                                 lua_level="high", lua_log=None)
    return T.lua_check(args), data


def test_data_files_core_file_is_checked_and_patched_in_place(tmp_path, monkeypatch):
    res, data = run(tmp_path, monkeypatch)
    core = dict(res["reps"])[T.CORE_KEY]
    (path, entry), = core.files.items()
    assert os.path.normcase(path) == os.path.normcase(str(data / REL))
    assert entry["patch"] and entry["patch"]["rules"] == ["KB3", "KB4"]
    assert T.CORE_KEY in res["body"]


def test_staged_mwse_is_not_checked_twice(tmp_path, monkeypatch):
    res, _data = run(tmp_path, monkeypatch, ship_in_staging=True)
    reps = dict(res["reps"])
    assert T.CORE_KEY not in reps
    assert any(e["patch"] and e["patch"]["rules"] == ["KB3", "KB4"] for e in reps["MWSE"].files.values())
