"""--cell-conflicts: an .esm vs an .esp pair can't be reordered, but its current winner can still be confirmed
([1] keep ... winning) and that answer is remembered."""
import builtins
import types

from conftest import m


def test_esm_vs_esp_pair_offers_and_remembers_keep_winning(tmp_path, monkeypatch, capsys):
    data = tmp_path / "Morrowind" / "Data Files"
    data.mkdir(parents=True)
    conflict = {"place": [(("i", "town, hall"), 0, 0, 0, 0, 0, True)], "refs": [], "settings": [], "doubled": False}
    names = {"a.esm": "A.esm", "b.esp": "B.esp"}
    args = types.SimpleNamespace(data_dir=str(data), dry_run=False, use_answers=False, only_new=False)
    monkeypatch.setattr(builtins, "input", lambda prompt="": "1")
    m._conflict_session(args, [(("a.esm", "b.esp"), conflict)], names, {}, 1, labels={("i", "town, hall"): "Town, Hall"})
    out = capsys.readouterr().out
    assert "[1] keep  B.esp winning" in out and "-> B.esp keeps winning" in out
    answers = m.read_conflict_answers(str(tmp_path / "Morrowind"))
    assert answers["a.esm|b.esp"]["do"] == "keep" and answers["a.esm|b.esp"]["plugin"] == "B.esp"
