"""--cell-conflicts: an .esm vs an .esp pair can't be reordered, but its current winner can still be confirmed
([1] keep ... winning) and that answer is remembered."""
import builtins
import types

import pytest

from conftest import fold, m, plugin, rec, sub, z


def _families(tmp_path):
    data = tmp_path / "Data Files"
    data.mkdir()
    a = len(plugin(data / "A.esp", [], [rec("STAT", sub("NAME", z("a_object")))]))
    b = len(plugin(data / "B.esp", [], [rec("STAT", sub("NAME", z("b_object")))]))
    patch = len(plugin(data / "A addon.esp", [("A.esp", a)], []))
    plugin(data / "A addon patch.esp", [("A addon.esp", patch)], [])
    plugin(data / "A B patch.esp", [("A.esp", a), ("B.esp", b)], [])
    cell = sub("NAME", z("House")) + sub("DATA", bytes(12))
    cell += sub("FRMR", bytes(4)) + sub("NAME", z("a_object"))
    plugin(data / "Object user.esp", [], [rec("CELL", cell)])
    plugin(data / "Unrelated.esp", [], [])
    order = ["A.esp", "B.esp", "A addon.esp", "A addon patch.esp", "A B patch.esp",
             "Object user.esp", "Unrelated.esp"]
    masters = {"a.esp": [], "b.esp": [], "a addon.esp": ["a.esp"],
               "a addon patch.esp": ["a addon.esp"], "a b patch.esp": ["a.esp", "b.esp"],
               "object user.esp": [], "unrelated.esp": []}
    m.write_load_order(str(tmp_path), order, "test")
    (tmp_path / "Morrowind.ini").write_text("[Game Files]\n", encoding="cp1252")
    args = types.SimpleNamespace(data_dir=str(data), ini=str(tmp_path / "Morrowind.ini"),
                                 dry_run=False, use_answers=False, only_new=False)
    return args, [(name, str(data / name)) for name in order], masters


def test_disabling_a_conflict_side_sets_aside_its_dependents(tmp_path, monkeypatch, capsys):
    args, plugins, masters = _families(tmp_path)
    names = {name.lower(): name for name, _path in plugins}
    conflict = {"place": [], "refs": [(("i", "house"), 1, False)], "settings": [], "doubled": False}
    pairs = [("a.esp", "b.esp"), ("b.esp", "a addon.esp"), ("b.esp", "object user.esp")]
    prompts = []
    monkeypatch.setattr(m, "IN_FULL", True)
    monkeypatch.setattr(builtins, "input", lambda prompt="": prompts.append(prompt) or "3")
    m._conflict_session(args, [(pair, conflict) for pair in pairs], names, masters, 1, plugins)
    out = capsys.readouterr().out
    assert prompts == ["  > "]
    assert "also set aside: A addon.esp, A B patch.esp, Object user.esp, A addon patch.esp" in out
    assert m.read_load_order(args) == ["B.esp", "Unrelated.esp"]
    disabled = m.read_disabled(str(tmp_path))
    assert set(disabled) == {"A.esp", "A addon.esp", "A addon patch.esp", "A B patch.esp", "Object user.esp"}
    assert all("conflicts with B.esp" in why for why in disabled.values())
    answer = m.read_conflict_answers(str(tmp_path))["a.esp|b.esp"]
    assert set(answer["affected"]) == set(disabled)


def test_dry_run_conflict_choice_does_not_write_rules_or_launch_follow_up(tmp_path, monkeypatch):
    args, plugins, masters = _families(tmp_path)
    args.dry_run = True
    names = {name.lower(): name for name, _path in plugins}
    conflict = {"place": [], "refs": [(("i", "house"), 1, False)], "settings": [], "doubled": False}
    monkeypatch.setattr(builtins, "input", lambda _prompt="": "1")
    monkeypatch.setattr(m, "main", lambda _argv: pytest.fail("dry run launched a follow-up"))
    assert m._conflict_session(args, [(("a.esp", "b.esp"), conflict)], names, masters, 1, plugins) == 0
    assert not (tmp_path / m.RULES_FILE).exists()
    assert not (tmp_path / m.CONFLICT_ANSWERS_FILE).exists()
    assert m.read_load_order(args) == [name for name, _path in plugins]


def test_failed_load_order_write_restores_moved_conflict_plugins(tmp_path, monkeypatch):
    args, plugins, masters = _families(tmp_path)
    names = {name.lower(): name for name, _path in plugins}
    conflict = {"place": [], "refs": [(("i", "house"), 1, False)], "settings": [], "doubled": False}
    aside = tmp_path / "disabled"
    aside.mkdir()

    def move(_args, selected):
        moved = []
        for name in selected:
            source, target = tmp_path / "Data Files" / name, aside / name
            source.rename(target)
            moved.append((str(source), str(target)))
        return moved

    def fail(*_args):
        raise OSError("load-order write failed")

    monkeypatch.setattr(m, "move_conflict_plugins", move)
    monkeypatch.setattr(m, "set_game_files", fail)
    monkeypatch.setattr(builtins, "input", lambda _prompt="": "3")
    with pytest.raises(OSError, match="load-order write failed"):
        m._conflict_session(args, [(("a.esp", "b.esp"), conflict)], names, masters, 1, plugins)
    assert all((tmp_path / "Data Files" / name).is_file() for name, _path in plugins)
    assert list(aside.iterdir()) == []
    assert m.read_load_order(args) == [name for name, _path in plugins]
    assert m.read_disabled(str(tmp_path)) == {}


def test_incompatible_only_review_preserves_existing_conflict_rules(tmp_path, monkeypatch):
    args, plugins, masters = _families(tmp_path)
    args.only_incompatible = True
    names = {name.lower(): name for name, _path in plugins}
    conflict = {"place": [], "refs": [], "settings": [], "doubled": False,
                "incompatible": {"cells": {(1, 2)}, "evidence": {"terrain"}}}
    rules = (f"{m.CONFLICT_RULES_HEADER}\n[Order]\nUnrelated.esp\nB.esp\n"
             "; keep B.esp winning where they conflict\n")
    rules_path = tmp_path / m.RULES_FILE
    rules_path.write_text(rules, encoding="cp1252")
    monkeypatch.setattr(m, "IN_FULL", True)
    monkeypatch.setattr(builtins, "input", lambda _prompt="": "3")
    assert m._conflict_session(args, [(("a.esp", "b.esp"), conflict)], names, masters, 1, plugins) == 0
    assert rules_path.read_text(encoding="cp1252") == rules


def test_changed_dependency_family_is_not_replayed_without_confirmation(tmp_path, monkeypatch, capsys):
    args, plugins, masters = _families(tmp_path)
    args.only_new = True
    names = {name.lower(): name for name, _path in plugins}
    m.write_conflict_answers(str(tmp_path), {"a.esp|b.esp": {
        "do": "off", "plugin": "A.esp", "affected": ["A.esp"], "pair": ["A.esp", "B.esp"]}})
    conflict = {"place": [], "refs": [(("i", "house"), 1, False)], "settings": [], "doubled": False}
    prompts = []
    monkeypatch.setattr(m, "IN_FULL", True)
    monkeypatch.setattr(builtins, "input", lambda prompt="": prompts.append(prompt) or "s")
    m._conflict_session(args, [(("a.esp", "b.esp"), conflict)], names, masters, 1, plugins)
    assert prompts == ["  > "]
    assert "last time's answer no longer fits" in fold(capsys.readouterr().out)
    assert m.read_load_order(args) == [name for name, _path in plugins]


def test_cannot_disable_a_side_that_the_chosen_winner_needs(tmp_path, monkeypatch, capsys):
    args, plugins, masters = _families(tmp_path)
    names = {name.lower(): name for name, _path in plugins}
    conflict = {"place": [], "refs": [(("i", "house"), 1, False)], "settings": [], "doubled": False}
    monkeypatch.setattr(builtins, "input", lambda prompt="": "s")
    m._conflict_session(args, [(("a.esp", "a addon.esp"), conflict)], names, masters, 1, plugins)
    out = capsys.readouterr().out
    assert "can't turn off A.esp: A addon.esp also depends on it" in out
    assert m.read_load_order(args) == [name for name, _path in plugins]


def test_group_includes_script_and_dialogue_users_but_not_shared_objects(tmp_path):
    args, plugins, masters = _families(tmp_path)
    data = tmp_path / "Data Files"
    plugin(data / "B.esp", [], [rec("STAT", sub("NAME", z("a_object")))])
    plugin(data / "Script user.esp", [], [
        rec("SCPT", sub("SCHD", z("script").ljust(52, b"\0"))
            + sub("SCTX", z('begin script\n"a_object"->Disable\nend')))])
    plugin(data / "Dialogue user.esp", [], [
        rec("INFO", sub("INAM", z("1")) + sub("BNAM", z('a_object->Enable')))])
    for name in ("Script user.esp", "Dialogue user.esp"):
        plugins.append((name, str(data / name)))
        masters[name.lower()] = []
    assert set(m.disable_dependents(plugins, masters, ["A.esp"])) == {
        "a.esp", "a addon.esp", "a addon patch.esp", "a b patch.esp"}
    plugin(data / "B.esp", [], [rec("STAT", sub("NAME", z("b_object")))])
    assert set(m.disable_dependents(plugins, masters, ["A.esp"])) == {
        "a.esp", "a addon.esp", "a addon patch.esp", "a b patch.esp",
        "object user.esp", "script user.esp", "dialogue user.esp"}


def test_generated_patches_are_set_aside_and_active_merges_block_choices(tmp_path, monkeypatch, capsys):
    args, plugins, masters = _families(tmp_path)
    data = tmp_path / "Data Files"
    plugin(data / m.CELL_WINNER_PATCH, [], [])
    plugins.append((m.CELL_WINNER_PATCH, str(data / m.CELL_WINNER_PATCH)))
    masters[m.CELL_WINNER_PATCH.lower()] = []
    m.write_load_order(str(tmp_path), [n for n, _p in plugins], "test")
    names = {name.lower(): name for name, _path in plugins}
    conflict = {"place": [], "refs": [(("i", "house"), 1, False)], "settings": [], "doubled": False}
    monkeypatch.setattr(m, "IN_FULL", True)
    monkeypatch.setattr(builtins, "input", lambda prompt="": "3")
    m._conflict_session(args, [(("a.esp", "b.esp"), conflict)], names, masters, 1, plugins)
    out = fold(capsys.readouterr().out)
    assert m.CELL_WINNER_PATCH not in m.read_load_order(args)
    assert m.CELL_WINNER_PATCH not in m.read_disabled(str(tmp_path))
    assert "generated patches will need rebuilding" in out
    plugin(data / m.AUTO_MERGE_NAME, [], [])
    plugins.append((m.AUTO_MERGE_NAME, str(data / m.AUTO_MERGE_NAME)))
    masters[m.AUTO_MERGE_NAME.lower()] = []
    m.write_load_order(str(tmp_path), [n for n, _p in plugins], "test")
    monkeypatch.setattr(builtins, "input", lambda prompt="": "s")
    m._conflict_session(args, [(("a.esp", "b.esp"), conflict)], names, masters, 1, plugins)
    assert "unmerge" in capsys.readouterr().out
    assert m.read_load_order(args) == [n for n, _p in plugins]


def test_group_reactivation_requires_its_root_and_every_master(tmp_path, monkeypatch, capsys):
    args, plugins, masters = _families(tmp_path)
    names = {name.lower(): name for name, _path in plugins}
    conflict = {"place": [], "refs": [(("i", "house"), 1, False)], "settings": [], "doubled": False}
    monkeypatch.setattr(m, "IN_FULL", True)
    monkeypatch.setattr(builtins, "input", lambda prompt="": "3")
    m._conflict_session(args, [(("a.esp", "b.esp"), conflict)], names, masters, 1, plugins)
    args.reenable = ["Object user.esp"]
    assert m.run_reenable(args) == 1
    assert "Object user.esp" not in m.read_load_order(args)
    assert "Object user.esp" in m.read_disabled(str(tmp_path))
    m.write_load_order(str(tmp_path), ["Unrelated.esp"], "winner removed")
    args.plugins = None
    args.openmw_cfg = None
    assert m.release_lost_winners(args) == 4
    order = m.read_load_order(args)
    assert set(order) == {"A.esp", "A addon.esp", "A addon patch.esp", "Object user.esp", "Unrelated.esp"}
    assert order.index("A.esp") < order.index("A addon.esp") < order.index("A addon patch.esp")
    assert order.index("A.esp") < order.index("Object user.esp")
    assert set(m.read_disabled(str(tmp_path))) == {"A B patch.esp"}
    assert "b.esp is not active or being restored" in fold(capsys.readouterr().out)


def test_unreadable_headers_block_group_choices_and_reactivation(tmp_path, monkeypatch, capsys):
    args, plugins, masters = _families(tmp_path)
    bad = tmp_path / "Data Files" / "Broken.esp"
    bad.write_bytes(b"not a plugin")
    plugins.append(("Broken.esp", str(bad)))
    masters["broken.esp"] = []
    m.write_load_order(str(tmp_path), [n for n, _p in plugins], "test")
    args._cell_master_errors = {"Broken.esp": "missing or truncated TES3 header"}
    names = {name.lower(): name for name, _path in plugins}
    conflict = {"place": [], "refs": [(("i", "house"), 1, False)], "settings": [], "doubled": False}
    monkeypatch.setattr(builtins, "input", lambda prompt="": "s")
    m._conflict_session(args, [(("a.esp", "b.esp"), conflict)], names, masters, 1, plugins)
    assert "can't safely turn off" in capsys.readouterr().out
    m.write_load_order(str(tmp_path), ["B.esp"], "test")
    m.write_disabled(str(tmp_path), {"Broken.esp": "test"})
    args.reenable = ["Broken.esp"]
    assert m.run_reenable(args) == 1
    assert "could not read its masters" in capsys.readouterr().out
    assert m.read_load_order(args) == ["B.esp"]
    assert set(m.read_disabled(str(tmp_path))) == {"Broken.esp"}


def test_incompatible_esm_esp_conflict_cannot_be_resolved_by_order_or_skipping(tmp_path, monkeypatch, capsys):
    data = tmp_path / "Data Files"
    data.mkdir()
    args = types.SimpleNamespace(data_dir=str(data), dry_run=False, use_answers=False, only_new=False)
    names = {"a.esm": "A.esm", "b.esp": "B.esp"}
    conflict = {"place": [], "refs": [], "settings": [], "doubled": False,
                "incompatible": {"cells": {(1, 2)}, "evidence": {"terrain"}}}
    monkeypatch.setattr(builtins, "input", lambda _prompt="": "s")
    assert m._conflict_session(args, [(("a.esm", "b.esp"), conflict)], names, {}, 1) == 2
    out = fold(capsys.readouterr().out)
    assert "one side must be turned off" in out
    assert "Load order and automatic relocation cannot safely resolve" in out
    assert "[1] keep" not in out
    assert "incompatible plugins remain active" in out


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


def test_only_new_asks_when_remembered_answer_no_longer_fits(tmp_path, monkeypatch, capsys):
    data = tmp_path / "Morrowind" / "Data Files"
    data.mkdir(parents=True)
    game = str(tmp_path / "Morrowind")
    m.write_conflict_answers(game, {"a.esp|b.esp": {
        "do": "off", "plugin": "A.esp", "pair": ["A.esp", "B.esp"], "when": "earlier"}})
    conflict = {"place": [], "refs": [(('i', 'hall'), 1, False)], "settings": [], "doubled": False}
    names = {"a.esp": "A.esp", "b.esp": "B.esp"}
    args = types.SimpleNamespace(data_dir=str(data), dry_run=False, use_answers=False, only_new=True)
    prompts = []
    replies = iter(("1", "n"))

    def answer(prompt=""):
        prompts.append(prompt)
        return next(replies)

    monkeypatch.setattr(builtins, "input", answer)
    m._conflict_session(args, [(("a.esp", "b.esp"), conflict)], names,
                        {"dependent.esp": ["a.esp"]}, 1)
    capsys.readouterr()
    assert prompts[0] == "  > "
    assert m.read_conflict_answers(game)["a.esp|b.esp"]["do"] == "order"
