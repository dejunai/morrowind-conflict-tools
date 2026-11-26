r"""Where the stand-in ("dummy") files are kept: <tools>\generated\dummy by default, made only when the first one is
written; a caller can choose the folder (module attribute or environment variable) or route it (MWManager:
outputs\dummy). Never next to the script, never in the game folder, never shipped. Temp folders only."""
import os

import pytest

from conftest import _load, m
from test_check import bsa

MED = _load("mwdialog_media")
MP = _load("mwdialog_paths")


@pytest.fixture
def world(tmp_path, monkeypatch):
    game = tmp_path / "game"
    (game / "Data Files").mkdir(parents=True)
    (game / "Data Files" / "Morrowind.bsa").write_bytes(bsa([(r"meshes\m\misc_dwrv_coin00.nif", b"COIN")]))
    gen = tmp_path / "tools" / "generated"
    monkeypatch.delenv(MED.DUMMY_DIR_ENV, raising=False)
    monkeypatch.setattr(MED, "DUMMY_DIR", None)
    monkeypatch.setattr(MP, "GENERATED_DIR", str(gen))
    return game, gen


def listing(root):
    return sorted(os.path.relpath(os.path.join(b, n), str(root)) for b, ds, fs in os.walk(str(root)) for n in ds + fs)


def test_the_default_is_generated_dummy_beside_the_tools_not_the_script_nor_the_game(world):
    game, gen = world
    assert MED.dummy_dir(str(game)) == str(gen / "dummy")
    assert os.path.dirname(MED.dummy_dir(str(game))) != os.path.dirname(os.path.abspath(MED.__file__))
    assert "dummy assets" not in MED.dummy_dir(str(game))


def test_the_folder_is_made_only_when_the_first_stand_in_is_written(world):
    game, gen = world
    before = listing(game)
    assert not gen.exists()
    MED.dummy_path("not_a_known_stand_in.nif", str(game))                 # a name that is no stand-in: nothing made
    MED.dummy_dir(str(game))
    assert not (gen / "dummy").exists() and not gen.exists()
    path = MED.dummy_path(MED.DUMMY_NIF, str(game))                       # copied out of Morrowind.bsa: made now
    assert path == str(gen / "dummy" / MED.DUMMY_NIF) and open(path, "rb").read() == b"COIN"
    assert listing(game) == before                                        # nothing in the game folder


def test_no_bsa_and_no_kept_copy_is_an_error_and_makes_no_folder(world):
    game, gen = world
    (game / "Data Files" / "Morrowind.bsa").unlink()
    with pytest.raises(OSError):
        MED.dummy_path(MED.DUMMY_NIF, str(game))
    assert not (gen / "dummy").exists()


def test_a_kept_copy_is_used_without_the_bsa(world):
    game, gen = world
    MED.dummy_path(MED.DUMMY_NIF, str(game))
    (game / "Data Files" / "Morrowind.bsa").unlink()
    assert open(MED.dummy_path(MED.DUMMY_NIF, str(game)), "rb").read() == b"COIN"


def test_the_attribute_beats_the_environment_beats_a_routed_state_folder_beats_the_default(world, tmp_path, monkeypatch):
    game, gen = world
    monkeypatch.setattr(MP, "state_path", lambda base, name: os.path.join(str(tmp_path / "outputs"), name))
    assert MED.dummy_dir(str(game)) == str(tmp_path / "outputs" / "dummy")          # MWManager: outputs\dummy
    monkeypatch.setenv(MED.DUMMY_DIR_ENV, str(tmp_path / "from-env"))
    assert MED.dummy_dir(str(game)) == str(tmp_path / "from-env")
    monkeypatch.setattr(MED, "DUMMY_DIR", str(tmp_path / "from-attr"))
    assert MED.dummy_dir(str(game)) == str(tmp_path / "from-attr")
    assert MED.dummy_path(MED.DUMMY_NIF, str(game)) == str(tmp_path / "from-attr" / MED.DUMMY_NIF)
    assert open(tmp_path / "from-attr" / MED.DUMMY_NIF, "rb").read() == b"COIN"
    assert not (tmp_path / "outputs").exists() and not (tmp_path / "from-env").exists()


def test_a_routed_folder_inside_the_game_is_not_used(world, monkeypatch):
    game, gen = world
    monkeypatch.setattr(MP, "state_path", lambda base, name: os.path.join(base, name))     # "as given": in the game
    assert MED.dummy_dir(str(game)) == str(gen / "dummy")


def test_an_old_dummy_assets_folder_is_left_alone_and_not_used(world):
    game, gen = world
    old = game / "dummy assets"
    old.mkdir()
    (old / MED.DUMMY_NIF).write_bytes(b"OLD")
    assert open(MED.dummy_path(MED.DUMMY_NIF, str(game)), "rb").read() == b"COIN"
    assert (old / MED.DUMMY_NIF).read_bytes() == b"OLD"


def test_mwdialog_check_resolves_the_same_folder(world, monkeypatch, tmp_path):
    game, gen = world
    assert m.dummy_dir(str(game)) == MED.dummy_dir(str(game))
    monkeypatch.setenv(MED.DUMMY_DIR_ENV, str(tmp_path / "e"))
    assert m.dummy_dir() == str(tmp_path / "e")