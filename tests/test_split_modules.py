"""The split of mwdialog_check.py into smaller modules: code that moved out still sees this run's settings.

- record_bases (mwdialog_state) reads TOP_ARGS from mwdialog_check, so the Vortex staging and downloads
  folders are bases: tagged staging:/downloads: paths resolve, and new ones are stored tagged.
- --restore-textures (mwdialog_generated) finds originals recorded as staging: and downloads: paths.
- ModelAssets (mwdialog_datatree) hands mwdialog_assets the mwdialog_check module, which holds every name.
- No moved module looks up mwdialog_check's run state in its own globals.
All in temp folders."""
import argparse
import ast
import os
import sys

from conftest import SRC, m

import mwdialog_paths as MP

MOVED = ("tes3", "bsa", "media", "backup", "loadorder", "records", "state", "cellmods", "datatree",
         "console", "masters", "patchfile", "redundant", "generated", "restore")


def _layout(tmp_path):
    game = tmp_path / "game"
    data = game / "Data Files"
    staging = tmp_path / "staging"
    downloads = tmp_path / "downloads"
    for d in (data / "Textures", staging / "ModA" / "Textures", downloads):
        d.mkdir(parents=True)
    return game, data, staging, downloads


def _top_args(monkeypatch, staging, downloads):
    ns = argparse.Namespace(vortex_dir=str(staging), vortex_downloads=str(downloads))
    monkeypatch.setattr(m, "TOP_ARGS", ns)
    return ns


def test_record_bases_has_staging_and_downloads_from_this_run(tmp_path, monkeypatch):
    game, _data, staging, downloads = _layout(tmp_path)
    _top_args(monkeypatch, staging, downloads)
    state = sys.modules["mwdialog_state"]
    for bases in (state.record_bases(str(game)), m.record_bases(str(game))):
        assert bases == {"game": os.path.abspath(game), "staging": os.path.abspath(staging),
                         "downloads": os.path.abspath(downloads)}
        assert MP.resolve_stored("staging:ModA/Textures/a.dds", bases) == \
            os.path.join(os.path.abspath(staging), "ModA", "Textures", "a.dds")
        assert MP.resolve_stored("downloads:a.7z", bases) == os.path.join(os.path.abspath(downloads), "a.7z")
        full = os.path.join(str(staging), "ModA", "Textures", "b.dds")
        stored = MP.store_path(full, bases)
        assert stored.startswith("staging:") and MP.resolve_stored(stored, bases) == os.path.abspath(full)


def test_explicit_args_still_win(tmp_path, monkeypatch):
    game, _data, staging, downloads = _layout(tmp_path)
    _top_args(monkeypatch, tmp_path / "elsewhere", downloads)
    state = sys.modules["mwdialog_state"]
    bases = state.record_bases(str(game), argparse.Namespace(vortex_dir=str(staging), vortex_downloads=None))
    assert bases["staging"] == os.path.abspath(staging) and "downloads" not in bases


def test_restore_textures_resolves_staging_and_downloads_tags(tmp_path, monkeypatch, capsys):
    game, data, staging, downloads = _layout(tmp_path)
    _top_args(monkeypatch, staging, downloads)
    (staging / "ModA" / "Textures" / "a.dds").write_bytes(b"full size a")
    (downloads / "b.dds").write_bytes(b"full size b")
    (data / "Textures" / "a.dds").write_bytes(b"reduced a")
    (data / "Textures" / "b.dds").write_bytes(b"reduced b")
    rec = game / m.REDUCED_RECORD
    sep = os.sep                                   # the record holds paths as this OS writes them
    rec.write_text(f"; header\nTextures{sep}a.dds\tlink\tstaging:ModA/Textures/a.dds\n"
                   f"Textures{sep}b.dds\tbackup\tdownloads:b.dds\n", encoding="utf-8")
    m.run_restore_textures(argparse.Namespace(data_dir=str(data), dry_run=True))
    out = capsys.readouterr().out
    assert out.count("would restore") == 2
    assert os.path.abspath(staging) in out and os.path.abspath(downloads) in out
    m.run_restore_textures(argparse.Namespace(data_dir=str(data), dry_run=False))
    out = capsys.readouterr().out
    assert "Restored 2 full-size texture(s)." in out and "no longer exist" not in out
    assert (data / "Textures" / "a.dds").read_bytes() == b"full size a"
    assert (data / "Textures" / "b.dds").read_bytes() == b"full size b"


def test_reduced_texture_record_is_written_tagged(tmp_path, monkeypatch):
    game, _data, staging, downloads = _layout(tmp_path)
    _top_args(monkeypatch, staging, downloads)
    gen = sys.modules["mwdialog_generated"]
    full = os.path.join(str(staging), "ModA", "Textures", "a.dds")
    assert MP.store_path(full, gen.record_bases(str(game))).startswith("staging:")


def test_model_assets_hands_assets_the_check_module():
    dt = sys.modules["mwdialog_datatree"]
    assert dt._check_module() is m
    assert hasattr(dt._check_module(), "TEXT_KEY_TAG") and hasattr(dt._check_module(), "nif_text_keys_lf")


def test_sibling_prefers_the_file_next_to_it():
    dt = sys.modules["mwdialog_datatree"]
    mod = dt._sibling("mwdialog_mastercheck")
    assert os.path.dirname(os.path.abspath(mod.__file__)) == os.path.abspath(SRC)


def test_no_moved_module_reads_run_state_from_its_own_globals():
    """globals().get(...) or sys.modules[__name__] in a moved module would look in the wrong module."""
    bad = []
    for n in MOVED:
        path = os.path.join(SRC, f"mwdialog_{n}.py")
        for node in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "globals":
                bad.append(f"mwdialog_{n}.py:{node.lineno}: globals()")
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Name) \
                    and node.slice.id == "__name__":
                bad.append(f"mwdialog_{n}.py:{node.lineno}: sys.modules[__name__]")
    assert not bad, bad


def test_vortex_settings_memo_keeps_no_failure(tmp_path, monkeypatch):
    calls = []

    def fake(game_id=MP.GAME_ID):
        calls.append(1)
        return {"downloads_tmpl": None, "staging_tmpl": None, "tried": [], "reason": "nothing"}
    monkeypatch.setattr(MP, "_read_vortex_settings", fake)
    MP.clear_vortex_settings_cache()
    MP.read_vortex_settings()
    MP.read_vortex_settings()
    assert len(calls) == 2                                  # a failure is not kept

    def good(game_id=MP.GAME_ID):
        calls.append(1)
        return {"downloads_tmpl": "D", "staging_tmpl": "S", "tried": ["x"], "reason": None}
    monkeypatch.setattr(MP, "_read_vortex_settings", good)
    first = MP.read_vortex_settings()
    first["tried"].append("changed by a caller")
    assert MP.read_vortex_settings()["tried"] == ["x"] and len(calls) == 3   # kept, and not shared
    MP.read_vortex_settings(refresh=True)
    assert len(calls) == 4
    MP.clear_vortex_settings_cache()
