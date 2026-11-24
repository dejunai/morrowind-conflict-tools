"""The tools' own files (records, caches, journals, reports, rules) live in conflict-tools\\generated\\ when the
tools are installed in the game; a copy left in the game folder is moved there the first time it is used."""
import os

import pytest

from conftest import m

MP = m.MP


@pytest.fixture
def installed(tmp_path, monkeypatch):
    game = tmp_path / "Morrowind"
    tools = game / "conflict-tools"
    tools.mkdir(parents=True)
    monkeypatch.setattr(MP, "TOOL_DIR", str(tools))
    monkeypatch.setattr(MP, "GENERATED_DIR", str(tools / "generated"))
    return game, tools / "generated"


def test_game_folder_files_go_to_generated_and_old_copies_move(installed):
    game, gen = installed
    (game / m.CONFLICT_ANSWERS_FILE).write_text('{"answers": {"a.esp|b.esp": {"do": "keep"}}}', encoding="utf-8")
    path = MP.state_path(str(game), m.CONFLICT_ANSWERS_FILE)
    assert path == os.path.join(str(gen), m.CONFLICT_ANSWERS_FILE)
    assert not (game / m.CONFLICT_ANSWERS_FILE).exists()
    assert m.read_conflict_answers(str(game)) == {"a.esp|b.esp": {"do": "keep"}}   # the readers follow it
    m.write_cell_winners(str(game), {"hall": ("Hall", "B.esp", "A.esp")})
    assert (gen / m.CELL_WINNERS_FILE).is_file() and not (game / m.CELL_WINNERS_FILE).exists()


def test_a_copy_already_in_generated_wins(installed):
    game, gen = installed
    gen.mkdir()
    (gen / m.RULES_FILE).write_text("new", encoding="utf-8")
    (game / m.RULES_FILE).write_text("old", encoding="utf-8")
    assert open(MP.state_path(str(game), m.RULES_FILE), encoding="utf-8").read() == "new"
    assert (game / m.RULES_FILE).read_text(encoding="utf-8") == "old"         # left for the user, never overwritten


def test_other_folders_and_absolute_names_are_used_as_given(installed, tmp_path):
    game, gen = installed
    other = tmp_path / "elsewhere"
    assert MP.state_path(str(other), m.RULES_FILE) == os.path.join(str(other), m.RULES_FILE)
    log = str(tmp_path / "my.log")
    assert MP.state_path(str(game), log) == log
    assert not gen.exists() or not any(gen.iterdir())
