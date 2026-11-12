"""A plan file can't be enacted twice: --apply blanks it (or cuts it down to what was not applied), atomically,
keeps audit copies, and --undo never needs it. vortex_tidy.py and mwdialog_luafix.py."""
import json
import os
import sys

import pytest

from conftest import _load, fold, vt

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


def test_planfile_write_falls_back_to_in_place_when_the_rename_is_refused(tmp_path, monkeypatch):
    p = str(tmp_path / "plan.txt")
    PF.write_atomic(p, "x plan\n    a -> b\n")
    monkeypatch.setattr(os, "replace", lambda a, b: (_ for _ in ()).throw(PermissionError("held open")))
    monkeypatch.setattr(PF.time, "sleep", lambda s: None)
    PF.write_atomic(p, PF.blank_text("t.py"))
    assert PF.state(p) == "applied" and not [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]


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
    assert tidy("--apply", "--yes") == 2
    out = capsys.readouterr().out
    out = fold(out)
    assert "REFUSED" in out and "plan is empty / already applied" in out and "plan mode first" in out
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
    assert luafix("--apply", "--yes") == 2
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


def test_luafix_plan_with_no_actions_refuses(luafix, capsys):
    for f in luafix.files:
        f.write_text("local x = 1\n")
    luafix()
    capsys.readouterr()
    assert luafix("--apply", "--yes") == 2
    assert "lists no actions" in capsys.readouterr().out and PF.state(lf.PLAN_FILE) == "pending"


# ------------------------------------------------------------------------------------------- strict --apply
def test_planfile_compare_ignores_headers_comments_and_order():
    a = "x plan, 2026-11-11 10:00: 2\n  left alone: Z\n\nM   [M]\n    a  ->  b   (doc)\n    c  ->  d   (doc)\n"
    b = "# a comment\nx plan, 2026-11-12 09:00: 2\n\nM   [M]\n    c  ->  d   (doc)\n    a  ->  b   (doc)\n"
    assert PF.compare(a, b) == ([], [])
    added, removed = PF.compare(a, b.replace("c  ->  d", "c  ->  e"))
    assert len(added) == 1 and len(removed) == 1 and "c  ->  e" in added[0][1]
    assert PF.actions("\nM\n    lua m/main.lua\n        G2 high        line 9: x\n        G5 report      line 2: y\n"
                      "        => patch ready (G2) [abcd1234]\n") == {
        ("M | lua m/main.lua", "G2 high        line 9: x"): 1, ("M | lua m/main.lua", "=> patch ready (G2) [abcd1234]"): 1}


def test_tidy_missing_plan_refuses(tidy, capsys):
    assert tidy("--apply", "--yes") == 2
    out = capsys.readouterr().out
    out = fold(out)
    assert "there is no plan file" in out and "plan mode first" in out
    assert (tidy.mod / "readme.txt").exists() and not _runs(vt.JOURNAL)


def test_tidy_plan_with_no_actions_refuses(tidy, capsys):
    open(vt.PLAN, "w").write("vortex_tidy plan, 2026-11-11 10:00: 1 mod(s), 0 to change\n")
    assert tidy("--apply", "--yes") == 2 and "lists no actions" in capsys.readouterr().out


def test_tidy_mismatch_refuses_changes_nothing_and_rewrites_the_plan_with_prev(tidy, capsys):
    tidy()
    reviewed = open(vt.PLAN).read()
    (tidy.mod / "changelog.txt").write_text("new since the review")         # one more move now
    os.remove(tidy.mod / "notes.txt")                                        # one less
    capsys.readouterr()
    assert tidy("--apply", "--yes") == 2
    out = capsys.readouterr().out
    flat = fold(out)
    assert "REFUSED" in flat and "1 action(s) added, 1 removed" in flat
    assert "changelog.txt" in flat and "notes.txt" in flat
    prev = os.path.splitext(vt.PLAN)[0] + ".prev.txt"
    assert f"saved as {prev}" in flat
    assert open(prev).read() == reviewed                                     # the reviewed one, kept
    assert "changelog.txt  ->" in open(vt.PLAN).read()                       # the new one, to review
    assert (tidy.mod / "readme.txt").exists() and (tidy.mod / "changelog.txt").exists() and not _runs(vt.JOURNAL)
    assert tidy("--apply", "--yes") == 0                                     # reviewed now: it applies
    assert (tidy.mod / "Docs" / "Foo-1-1-0 - changelog.txt").exists() and PF.state(vt.PLAN) == "applied"


def test_tidy_edited_plan_file_refuses_too(tidy):
    tidy()
    t = open(vt.PLAN).read()
    open(vt.PLAN, "w").write("\n".join(ln for ln in t.splitlines() if "notes.txt" not in ln) + "\n")
    assert tidy("--apply", "--yes") == 2 and (tidy.mod / "notes.txt").exists()


def test_tidy_lua_only_compares_only_the_lua_section(tidy_lua, capsys):
    tidy_lua()                                                               # full plan: moves + Lua
    (tidy_lua.mod / "changelog.txt").write_text("a move the plan doesn't have")
    assert tidy_lua("--lua-only", "--apply", "--yes") == 1                   # moves differ: not compared
    assert "mwluafix_gate(" in tidy_lua.lua.read_text()
    assert (tidy_lua.mod / "changelog.txt").exists()                         # --lua-only moves nothing


def test_tidy_lua_only_mismatch_refuses(tidy_lua, capsys):
    tidy_lua("--lua-only")
    tidy_lua.lua.write_text(PUDDLE.replace("0.35", "x").replace("bigger", "much bigger"))   # patch text changes
    capsys.readouterr()
    assert tidy_lua("--lua-only", "--apply", "--yes") == 2
    assert "REFUSED" in capsys.readouterr().out and "mwluafix_gate(" not in tidy_lua.lua.read_text()
    assert os.path.exists(os.path.splitext(vt.PLAN)[0] + ".prev.txt")


@pytest.fixture
def tidy_assets(tidy, monkeypatch):
    from conftest import ah, m
    bar = tidy.mod.parent / "Bar-2-1-0" / "Meshes"
    bar.mkdir(parents=True)
    (bar / "empty.nif").write_bytes(b"")
    monkeypatch.setattr(vt, "_tool_modules", lambda: (m, ah))
    monkeypatch.setattr(m, "stand_in_bytes", lambda rel: b"NIF stand-in")
    staging = str(tidy.mod.parent)

    def run(*extra):
        monkeypatch.setattr(sys, "argv", ["vortex_tidy.py", "--staging", staging, "--no-lua", *extra])
        return vt.main()
    run.nif, run.mod = bar / "empty.nif", tidy.mod
    return run


def test_tidy_asset_repairs_are_in_the_plan_and_applied_only_as_reviewed(tidy_assets):
    assert tidy_assets() == 0
    plan = open(vt.PLAN).read()
    assert "\nASSET CHECK\n" in plan and "    repair broken Meshes" in plan and "empty.nif empty" in plan
    assert tidy_assets.nif.stat().st_size == 0                              # plan mode changes nothing
    assert tidy_assets("--apply", "--yes") == 0
    assert tidy_assets.nif.stat().st_size > 0 and PF.state(vt.PLAN) == "applied"   # stand-in put there


def test_tidy_new_asset_repair_since_review_refuses(tidy_assets, capsys):
    tidy_assets()
    (tidy_assets.nif.parent / "empty2.nif").write_bytes(b"")
    capsys.readouterr()
    assert tidy_assets("--apply", "--yes") == 2
    out = capsys.readouterr().out
    assert "1 action(s) added, 0 removed" in out and "empty2.nif" in out
    assert tidy_assets.nif.stat().st_size == 0 and (tidy_assets.mod / "readme.txt").exists()


def test_luafix_mismatch_refuses_and_keeps_prev(luafix, capsys):
    luafix()
    luafix.files[1].write_text("local x = 1\n")                             # b no longer needs a patch
    capsys.readouterr()
    assert luafix("--apply", "--yes") == 2
    out = capsys.readouterr().out
    assert "REFUSED" in out and "0 action(s) added" in out
    assert "mwluafix_gate(" not in luafix.files[0].read_text()
    prev = os.path.splitext(lf.PLAN_FILE)[0] + ".prev.txt"
    assert "b/main.lua" in open(prev).read() and "b/main.lua" not in open(lf.PLAN_FILE).read()
    assert luafix("--apply", "--yes") == 0 and "mwluafix_gate(" in luafix.files[0].read_text()


def test_luafix_missing_plan_refuses(luafix, capsys):
    assert luafix("--apply", "--yes") == 2
    assert "there is no plan file" in capsys.readouterr().out
    assert all(f.read_text() == PUDDLE for f in luafix.files)


def test_tidy_asset_repair_that_fails_stays_in_the_plan(tidy_assets, monkeypatch):
    from conftest import m
    tidy_assets()

    def boom(rel):
        if rel.endswith("empty.nif"):
            raise OSError("no stand-in")
        return b"NIF stand-in"
    monkeypatch.setattr(m, "stand_in_bytes", boom)
    assert tidy_assets("--apply", "--yes") == 1
    plan = open(vt.PLAN).read()
    assert plan.startswith("# partially applied") and "ASSET CHECK" in plan
    assert "repair broken Meshes/empty.nif" in plan and "a.nif" not in plan and "readme.txt" not in plan
