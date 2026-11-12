"""A plan file can't be enacted twice: --apply blanks it (or cuts it down to what was not applied), atomically,
keeps audit copies, and --undo never needs it. vortex_tidy.py and mwdialog_luafix.py."""
import json
import os
import sys

import pytest

from conftest import _load, vt

lf = _load("mwdialog_luafix")
PF = _load("mwdialog_planfile")

PUDDLE = """local last = 0
local function onSimulate(e)
    local puddle = tes3.getReference("puddle")
    if puddle and puddle.scale > last then
        last = puddle.scale
        tes3.messageBox("The puddle got bigger")
    end
end
event.register(tes3.event.simulate, onSimulate)
"""


class OkChecker:
    name = "fake"

    def check(self, text):
        return True, ""


# ------------------------------------------------------------------------------------------- mwdialog_planfile
def test_planfile_states_and_atomic_write(tmp_path):
    p = str(tmp_path / "plan.txt")
    assert PF.state(p) == "missing"
    PF.write_atomic(p, "tool plan, today\n    a -> b\n")
    assert PF.state(p) == "pending"
    PF.write_atomic(p, PF.blank_text("tool.py"))
    t = open(p).read()
    assert t.startswith("# applied ") and "by tool.py --apply; nothing pending. Rerun in plan mode" in t
    assert PF.state(p) == "applied"
    assert "already applied" in PF.refuse_message(p, "tool.py")
    assert not [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]     # no temp file left behind
    PF.write_atomic(p, PF.partial_text("tool.py", ["    x -> y"]))
    assert PF.state(p) == "pending" and "partially applied" in open(p).read()


# ------------------------------------------------------------------------------------------- vortex_tidy
@pytest.fixture
def tidy(tmp_path, monkeypatch):
    staging = tmp_path / "staging"
    mod = staging / "Foo-1-1-0"
    (mod / "Meshes").mkdir(parents=True)
    (mod / "Meshes" / "a.nif").write_text("n")
    (mod / "readme.txt").write_text("r")
    (mod / "notes.txt").write_text("n")
    monkeypatch.setattr(vt, "JOURNAL", str(tmp_path / "journal.jsonl"))
    monkeypatch.setattr(vt, "PLAN", str(tmp_path / "vortex_tidy_plan.txt"))
    monkeypatch.setattr(vt, "BLACKLIST_FILE", str(tmp_path / "bl.txt"))
    monkeypatch.setattr(vt, "__file__", str(tmp_path / "vortex_tidy.py"))

    def run(*extra):
        monkeypatch.setattr(sys, "argv", ["vortex_tidy.py", "--staging", str(staging), "--no-lua", "--no-assets",
                                          *extra])
        return vt.main()
    run.mod, run.tmp = mod, tmp_path
    return run


def _runs(journal):
    return [json.loads(x) for x in open(journal) if '"run"' in x] if os.path.exists(journal) else []


def test_tidy_apply_blanks_the_plan_and_keeps_audit_copies(tidy):
    assert tidy() == 0
    plan = open(vt.PLAN).read()
    assert "readme.txt  ->" in plan and PF.state(vt.PLAN) == "pending"
    assert tidy("--apply", "--yes") == 0
    assert (tidy.mod / "Docs" / "Foo-1-1-0 - readme.txt").exists()
    assert PF.state(vt.PLAN) == "applied"
    assert open(vt.PLAN).read().startswith("# applied ") and "vortex_tidy.py --apply; nothing pending" in \
        open(vt.PLAN).read()
    (run,) = _runs(vt.JOURNAL)
    copy = run["plan_copy"]
    assert os.path.dirname(copy).startswith(vt.AUDIT_ROOT)
    assert "readme.txt  ->" in open(copy).read()                              # the enacted plan
    assert "readme.txt  ->" in open(os.path.join(os.path.dirname(copy), "plan_reviewed.txt")).read()


def test_tidy_second_apply_is_a_no_op(tidy, capsys):
    tidy()
    tidy("--apply", "--yes")
    (tidy.mod / "late.txt").write_text("would be moved by a fresh plan")
    capsys.readouterr()
    assert tidy("--apply", "--yes") == 0
    out = capsys.readouterr().out
    assert "plan is empty / already applied" in out and "plan mode first" in out
    assert (tidy.mod / "late.txt").exists() and len(_runs(vt.JOURNAL)) == 1
    tidy()                                                                    # plan mode regenerates it
    assert PF.state(vt.PLAN) == "pending" and "late.txt  ->" in open(vt.PLAN).read()


def test_tidy_partial_failure_leaves_only_what_was_not_applied(tidy, monkeypatch):
    tidy()
    real = os.rename

    def flaky(a, b):
        if a.endswith("notes.txt"):
            raise PermissionError("in use")
        return real(a, b)
    monkeypatch.setattr(os, "rename", flaky)
    assert tidy("--apply", "--yes") == 1
    plan = open(vt.PLAN).read()
    assert plan.startswith("# partially applied") and PF.state(vt.PLAN) == "pending"
    assert "notes.txt  ->" in plan and "readme.txt" not in plan               # applied: gone from the plan
    assert (tidy.mod / "Docs" / "Foo-1-1-0 - readme.txt").exists()


def test_tidy_interrupted_apply_keeps_only_the_moves_not_made(tidy, monkeypatch):
    tidy()
    real, calls = os.rename, []

    def stop(a, b):
        calls.append(a)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return real(a, b)
    monkeypatch.setattr(os, "rename", stop)
    with pytest.raises(KeyboardInterrupt):
        tidy("--apply", "--yes")
    plan = open(vt.PLAN).read()
    first, second = os.path.basename(calls[0]), os.path.basename(calls[1])
    assert "interrupted" in plan and f"{second}  ->" in plan and first not in plan


def test_tidy_undo_works_without_the_plan_file(tidy):
    tidy()
    tidy("--apply", "--yes")
    os.remove(vt.PLAN)
    assert vt.undo() == 0
    assert (tidy.mod / "readme.txt").exists() and (tidy.mod / "notes.txt").exists()


def test_tidy_declined_apply_leaves_the_plan_pending(tidy, monkeypatch):
    tidy()
    monkeypatch.setattr("builtins.input", lambda *_a: "n")
    assert tidy("--apply") == 0
    assert PF.state(vt.PLAN) == "pending" and not _runs(vt.JOURNAL)


@pytest.fixture
def tidy_lua(tidy, monkeypatch):
    lua = tidy.mod.parent / "Puddle-2-1-0" / "MWSE" / "mods" / "puddle"
    lua.mkdir(parents=True)
    (lua / "main.lua").write_text(PUDDLE)
    monkeypatch.setattr(lf, "find_checker", lambda *a, **k: OkChecker())
    monkeypatch.setattr(lf, "BACKUP_ROOT", str(tidy.tmp / "bk"))
    monkeypatch.setattr(lf.apply_report, "__defaults__", (lf.JOURNAL, str(tidy.tmp / "bk"), None, print, None, None))
    staging = str(tidy.mod.parent)

    def run(*extra):
        monkeypatch.setattr(sys, "argv", ["vortex_tidy.py", "--staging", staging, "--no-assets", *extra])
        return vt.main()
    run.lua, run.mod = lua / "main.lua", tidy.mod
    return run


def test_tidy_lua_only_apply_blanks_lua_but_keeps_pending_moves(tidy_lua):
    assert tidy_lua() == 0                                                    # full plan: moves + LUA CHECK
    assert tidy_lua("--lua-only") == 0                                        # Lua part replaced, not doubled
    plan = open(vt.PLAN).read()
    assert plan.count("\nLUA CHECK\n") == 1 and "readme.txt  ->" in plan
    assert tidy_lua("--lua-only", "--apply", "--yes") == 1                    # moves still pending: exit 1
    assert "mwluafix_gate(" in tidy_lua.lua.read_text()
    plan = open(vt.PLAN).read()
    assert "readme.txt  ->" in plan and "puddle/main.lua" not in plan and "LUA CHECK" not in plan
    assert tidy_lua("--apply", "--yes") == 0                                  # moves applied: now blank
    assert PF.state(vt.PLAN) == "applied"
    assert vt.undo() == 0 and vt.undo() == 0                                  # both runs undone from the journal
    assert tidy_lua.lua.read_text() == PUDDLE and (tidy_lua.mod / "readme.txt").exists()


def test_tidy_lua_refused_write_stays_in_the_plan(tidy_lua, monkeypatch):
    tidy_lua("--lua-only")
    monkeypatch.setattr(lf, "write_in_place", lambda p, b: (_ for _ in ()).throw(PermissionError("locked")))
    assert tidy_lua("--lua-only", "--apply", "--yes") == 1
    plan = open(vt.PLAN).read()
    assert plan.startswith("# partially applied") and "puddle/main.lua" in plan and "LUA CHECK" in plan


# ------------------------------------------------------------------------------------------- mwdialog_luafix
@pytest.fixture
def luafix(tmp_path, monkeypatch):
    root = tmp_path / "Mod" / "MWSE" / "mods"
    for name in ("a", "b"):
        (root / name).mkdir(parents=True)
        (root / name / "main.lua").write_text(PUDDLE)
    monkeypatch.setattr(lf, "JOURNAL", str(tmp_path / "lj.jsonl"))
    monkeypatch.setattr(lf, "BACKUP_ROOT", str(tmp_path / "bk"))
    monkeypatch.setattr(lf, "find_checker", lambda *a, **k: OkChecker())
    monkeypatch.setattr(lf, "load_config", lambda *a, **k: dict(lf.DEFAULTS, _sources=[]))

    def run(*extra):
        return lf.main([str(tmp_path / "Mod"), "--no-cache", *extra])
    run.files = [root / "a" / "main.lua", root / "b" / "main.lua"]
    return run


def test_luafix_apply_blanks_the_plan_with_an_audit_copy_and_second_apply_is_a_no_op(luafix, capsys):
    assert luafix() == 0 and PF.state(lf.PLAN_FILE) == "pending"
    assert luafix("--apply", "--yes") == 0
    assert all("mwluafix_gate(" in f.read_text() for f in luafix.files)
    assert PF.state(lf.PLAN_FILE) == "applied"
    assert "mwdialog_luafix.py --apply; nothing pending" in open(lf.PLAN_FILE).read()
    (run,) = [json.loads(x) for x in open(lf.JOURNAL) if '"run"' in x]
    assert os.path.exists(run["plan_copy"]) and "a/main.lua" in open(run["plan_copy"]).read()
    assert os.path.dirname(run["plan_copy"]).startswith(lf.BACKUP_ROOT)
    capsys.readouterr()
    assert luafix("--apply", "--yes") == 0
    assert "already applied" in capsys.readouterr().out
    assert len([x for x in open(lf.JOURNAL) if '"run"' in x]) == 1


def test_luafix_partial_failure_keeps_only_the_unwritten_file(luafix, monkeypatch):
    luafix()
    real = lf.write_in_place

    def flaky(p, b):
        if os.path.normpath(str(p)).endswith(os.path.join("b", "main.lua")):
            raise PermissionError("locked")
        return real(p, b)
    monkeypatch.setattr(lf, "write_in_place", flaky)
    assert luafix("--apply", "--yes") == 1
    plan = open(lf.PLAN_FILE).read()
    assert plan.startswith("# partially applied") and "b/main.lua" in plan and "a/main.lua" not in plan


def test_luafix_undo_works_without_the_plan_file(luafix):
    luafix()
    luafix("--apply", "--yes")
    os.remove(lf.PLAN_FILE)
    lf.undo(journal=lf.JOURNAL)
    assert all(f.read_text() == PUDDLE for f in luafix.files)


def test_luafix_nothing_to_patch_also_blanks(luafix, tmp_path):
    for f in luafix.files:
        f.write_text("local x = 1\n")
    luafix()
    assert luafix("--apply", "--yes") == 0 and PF.state(lf.PLAN_FILE) == "applied"
