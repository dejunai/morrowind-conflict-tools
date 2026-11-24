"""The tools' own files (conflict-tools\\generated, \\plans) keep one backup next to the file (<file>.bak); every
older one moves to <backups>\\legacy\\<file>.<YYYYmmdd-HHMMSS>.bak. Plugin backups are unchanged."""
import os
import re
import shutil

import pytest

from conftest import m

import mwdialog_backup as MB    # noqa: E402  (conftest put the tools on sys.path)
import mwdialog_planfile as PF  # noqa: E402

DATED = re.compile(r"\.\d{8}-\d{6}(-\d+)?\.bak$")


@pytest.fixture
def game(tmp_path, monkeypatch):
    game = tmp_path / "Morrowind"
    tools = game / "conflict-tools"
    for d in ("generated", "plans", "Data Files"):
        (tools if d != "Data Files" else game).joinpath(d).mkdir(parents=True)
    (game / "Morrowind.ini").write_text("[Game Files]\n", encoding="utf-8")
    monkeypatch.setattr(MB, "TOOL_DIR", str(tools))
    monkeypatch.setattr(m.MP, "TOOL_DIR", str(tools))
    monkeypatch.setattr(m.MP, "GENERATED_DIR", str(tools / "generated"))
    return game


def save(path, text, when):
    path.write_text(text, encoding="utf-8")
    os.utime(path, (when, when))


def test_one_backup_beside_and_older_ones_dated_in_legacy(game):
    rec = game / "conflict-tools" / "generated" / "mwdialog_cell_winners.txt"
    for n, when in enumerate((1_700_000_000, 1_700_000_100, 1_700_000_200)):
        save(rec, f"v{n}", when)
        shutil.copy2(rec, MB.backup_path(str(rec)))
    beside = sorted(p.name for p in rec.parent.iterdir())
    assert beside == ["mwdialog_cell_winners.txt", "mwdialog_cell_winners.txt.bak"]
    assert (rec.parent / "mwdialog_cell_winners.txt.bak").read_text(encoding="utf-8") == "v2"
    legacy = game / "conflict-tools" / "backups" / "legacy"
    old = sorted(p.name for p in legacy.iterdir())
    assert len(old) == 2 and all(n.startswith("mwdialog_cell_winners.txt.") and DATED.search(n) for n in old)
    assert sorted(p.read_text(encoding="utf-8") for p in legacy.iterdir()) == ["v0", "v1"]


def test_stamped_backup_of_the_rules_file_is_the_same_single_bak(game):
    rules = game / "conflict-tools" / "generated" / m.RULES_FILE
    save(rules, "a", 1_700_000_000)
    assert MB.stamped_backup(str(rules)) == str(rules) + ".bak"


def test_load_order_saves_keep_one_backup_beside(game):
    for n in range(3):
        m.write_load_order(str(game), ["Morrowind.esm", f"Mod{n}.esp"], "test")
    gen = game / "conflict-tools" / "generated"
    assert sorted(p.name for p in gen.iterdir()) == [m.LOAD_ORDER_FILE, m.LOAD_ORDER_FILE + ".bak"]
    legacy = game / "conflict-tools" / "backups" / "legacy"
    assert [DATED.search(p.name) is not None for p in legacy.iterdir()] == [True]
    assert "Mod1.esp" in (gen / (m.LOAD_ORDER_FILE + ".bak")).read_text(encoding="utf-8")


def test_a_refused_plan_keeps_one_previous_plan_beside(game):
    plan = game / "conflict-tools" / "plans" / "vortex_tidy_plan.txt"
    prev = PF.prev_path(str(plan))
    save(plan, "reviewed 1", 1_700_000_000)
    PF.refuse_mismatch(str(plan), "fresh 1", [], [], "vortex_tidy", log=lambda *_a: None)
    PF.refuse_mismatch(str(plan), "fresh 2", [], [], "vortex_tidy", log=lambda *_a: None)
    assert open(prev, encoding="utf-8").read() == "fresh 1"
    legacy = list((game / "conflict-tools" / "backups" / "legacy").iterdir())
    assert len(legacy) == 1 and DATED.search(legacy[0].name) and legacy[0].read_text(encoding="utf-8") == "reviewed 1"


def test_plugin_backups_are_unchanged(game):
    esp = game / "Data Files" / "Mod.esp"
    esp.write_bytes(b"TES3")
    bak = MB.backup_path(str(esp))
    assert bak == str(game / "conflict-tools" / "backups" / "Data Files" / "Mod.esp.bak")
