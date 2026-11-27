"""The 2026-11-26 audit's tidy-side items for the OpenMW converter handoff:
1. a recovery intent is on disk before omw2mwse writes anything, and an interrupted conversion is put back
   exactly by the next --apply or --undo (or refused, changing nothing);
2. --apply is bound to a digest of the converter's preview, the files it reads and the converter itself, and the
   plan shows its hard-coded rewrites and plugin placements;
3. partial API matches are shown next to the readiness verdict;
4. what ships converts in normal mode, also once the marked developer setting is removed.
The converter is the stub of test_tidy_undo_convert. Temporary folders only; tidy never runs on live data.
Python 3.9+."""
import json
import os
import sys

from conftest import fold, vt
from omw_interface_stub import new_interface_stub
from test_tidy_undo_convert import STUB, env, full_mod, put, root_mod, snap  # noqa: F401  (env is a fixture)

ARGV = ["vortex_tidy.py", "--no-lua", "--no-assets"]


def run(env, *extra):
    env.mp.setattr(vt.sys, "argv", ARGV + ["--staging", str(env.staging), *extra])
    vt.NOTES.clear()
    return vt.main()


def plan_text():
    with open(vt.PLAN, encoding="utf-8") as f:
        return f.read()


def inject(env, **fields):
    """Wrap run_converter so each ok mod of its JSON also carries `fields` (what a newer converter reports)."""
    real = vt.run_converter

    def wrapped(mod_dir, mode, dry_run=False):
        code, data, err = real(mod_dir, mode, dry_run)
        for m in (data or {}).get("mods") or []:
            m.update(json.loads(json.dumps(fields)))
        return code, data, err
    env.mp.setattr(vt, "run_converter", wrapped)


# ---------------------------------------------------------------- 1. recovery intent

def test_the_intent_is_on_disk_before_the_converter_writes_and_gone_after(env):
    mod = root_mod(env.staging, "Foo")
    before, _ = snap(mod)
    real, seen = vt.run_converter, []

    def spy(mod_dir, mode, dry_run=False):
        if not dry_run:
            it = vt.read_intent()
            seen.append(it)
            assert it and it["mod"] == mod_dir
            assert {k.replace("/", os.sep): v for k, v in it["files"].items()} == before   # every file, its hash
        return real(mod_dir, mode, dry_run)
    env.mp.setattr(vt, "run_converter", spy)
    env.apply()
    assert len(seen) == 1 and vt.read_intent() is None
    (conv,) = [o for o in env.journal() if "omw_convert" in o]
    assert conv["intent"] == seen[0]["intent"]                              # the journal names the intent it closed


def test_a_run_stopped_after_the_converter_wrote_is_put_back_by_the_next_apply(env, capsys):
    mod = root_mod(env.staging, "Foo")
    before = snap(mod)

    def boom(*a, **k):
        raise KeyboardInterrupt                                            # stopped before the undo record
    env.mp.setattr(vt, "journal_conversions", boom)
    assert run(env) == 0
    env.mp.setattr(vt.sys, "argv", ARGV + ["--staging", str(env.staging), "--apply", "--yes"])
    try:
        vt.main()
        raise AssertionError("the interruption did not happen")
    except KeyboardInterrupt:
        pass
    assert snap(mod) != before and vt.read_intent()                        # half done, the intent is pending
    env.mp.undo()                                                          # a new process: tidy as shipped
    env.mp.setattr(vt, "JOURNAL", str(env.tmp / "journal.jsonl"))
    env.mp.setattr(vt, "PLAN", str(env.tmp / "vortex_tidy_plan.txt"))
    env.mp.setattr(vt, "AUDIT_ROOT", str(env.tmp / "audit"))
    env.mp.setattr(vt, "HERE", str(env.game))
    env.mp.setattr(vt, "BLACKLIST_FILE", str(env.tmp / "bl.txt"))
    env.mp.setattr(vt, "CONVERTER_HOME", str(env.tmp / "tools-home"))
    env.mp.setattr(vt, "CONVERTER", dict(vt.CONVERTER))
    env.mp.setattr(vt, "interpreter_version", lambda cmd: (3, 11))
    env.mp.setattr(vt, "vortex_info", lambda d: {})
    env.mp.setattr(vt, "CORE_MISSING", {})
    env.mp.setenv("PATH", str(env.tmp / "empty-path"))
    env.mp.setenv("STUB_LOG", str(env.tmp / "calls.jsonl"))
    capsys.readouterr()
    assert run(env) == 0                                                   # the plan says so, changes nothing
    out = capsys.readouterr().out
    assert "an omw2mwse conversion of Foo-1-0 was interrupted" in out and vt.read_intent()
    assert run(env, "--apply", "--yes") == 1                               # puts it back, then stops
    out = capsys.readouterr().out
    assert "Foo-1-0: put back as it was before omw2mwse ran" in out and "run vortex_tidy again" in out
    assert snap(mod) == before and vt.read_intent() is None


def test_undo_puts_back_an_interrupted_conversion_first(env):
    mod = root_mod(env.staging, "Foo")
    before = snap(mod)
    env.mp.setattr(vt, "journal_conversions", lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert run(env) == 0
    try:
        run(env, "--apply", "--yes")
    except KeyboardInterrupt:
        pass
    assert vt.read_intent()
    assert vt.undo() == 0
    assert snap(mod) == before and vt.read_intent() is None


CRASH = "import os, sys\nif '--dry-run' in sys.argv:\n    exec(compile(%r, 'stub', 'exec'))\nelse:\n" \
        "    import contextlib, io\n    with contextlib.redirect_stdout(io.StringIO()):\n" \
        "        exec(compile(%r, 'stub', 'exec'))\n    os._exit(9)\n"


def test_a_converter_that_dies_part_way_leaves_nothing_and_the_package_goes_to_off(env, capsys):
    (env.tmp / "tools-home" / "tools" / "omw2mwse.py").write_text(new_interface_stub(CRASH % (STUB, STUB)))
    mod = full_mod(env.staging)
    before = snap(mod)
    env.apply()
    out = " ".join(capsys.readouterr().out.split())
    assert "omw2mwse could not convert Foo-1-0" in out and "put back as it was before omw2mwse ran" in out
    after, _ = snap(mod)
    assert not any(k.lower().startswith("mwse") for k in after)            # nothing it wrote is left
    assert os.path.join("Off", "Foo", "OpenMW", "Foo.omwscripts") in after  # the usual set-aside instead
    assert vt.read_intent() is None and [o for o in env.journal() if "omw_convert" in o] == []
    assert vt.undo() == 0 and snap(mod) == before


def test_reconcile_restores_kept_files_moves_originals_back_and_removes_new_ones(env, tmp_path):
    mod = tmp_path / "staging" / "Bar-1-0"
    put(mod / "Bar.omwscripts", "x\n")
    put(mod / "scripts" / "Bar" / "g.lua", "return 1\n")
    put(mod / "MWSE" / "mods" / "mwsuite" / "openmw" / "Bar" / "main.lua", "old loader\n")
    before = snap(mod)
    preview = {"mods": [{"name": "Bar", "status": "ok", "off": "Off/Bar/OpenMW",
                         "files": {"MWSE/mods/mwsuite/openmw/Bar/main.lua": "updated"}}]}
    it = vt.begin_intent(str(mod), str(tmp_path / "staging"), "normal", preview, str(tmp_path / "audit"))
    assert set(it["kept"]) == {"MWSE/mods/mwsuite/openmw/Bar/main.lua"}
    (mod / "MWSE" / "mods" / "mwsuite" / "openmw" / "Bar" / "main.lua").write_text("new loader\n")
    put(mod / "Off" / "Bar" / "OpenMW" / "Bar.omwscripts", "x\n")
    os.remove(mod / "Bar.omwscripts")                                      # relocated
    put(mod / "MWSE" / "lib" / "omwcompat.lua", "rt\n")                    # written
    assert vt.reconcile_intent(vt.read_intent()) is True
    assert snap(mod) == before and vt.read_intent() is None


def test_reconcile_changes_nothing_when_it_cannot_be_exact(env, tmp_path, capsys):
    mod = tmp_path / "staging" / "Bar-1-0"
    put(mod / "Bar.omwscripts", "x\n")
    put(mod / "readme.txt", "hi\n")
    vt.begin_intent(str(mod), str(tmp_path / "staging"), "normal", None, str(tmp_path / "audit"))
    (mod / "readme.txt").write_text("edited\n")                            # changed, no original kept
    put(mod / "MWSE" / "lib" / "omwcompat.lua", "rt\n")
    now = snap(mod)
    assert vt.reconcile_intent(vt.read_intent()) is False
    assert snap(mod) == now and vt.read_intent()                           # nothing changed, it stays pending
    assert "readme.txt: changed, and no original was kept" in capsys.readouterr().out


# ---------------------------------------------------------------- 2. bound to the preview

def test_the_plan_carries_the_check_digest_and_the_same_inputs_give_the_same_digest(env):
    root_mod(env.staging, "Foo")
    assert run(env) == 0
    first = [ln for ln in plan_text().splitlines() if vt.CHECK_LABEL in ln]
    assert run(env) == 0
    assert first and [ln for ln in plan_text().splitlines() if vt.CHECK_LABEL in ln] == first


def test_a_sidecar_edit_between_plan_and_apply_is_refused(env, capsys):
    mod = root_mod(env.staging, "Foo")
    assert run(env) == 0
    put(mod / "Foo.omw2mwse.toml", "[mod]\nname = 'Foo'\n")               # a sidecar appears
    capsys.readouterr()
    assert run(env, "--apply", "--yes") == 2
    out = fold(capsys.readouterr().out)
    assert "REFUSED" in out and vt.CHECK_REFUSED in out
    assert [c for c in env.calls() if "--dry-run" not in c] == []          # the converter never really ran
    assert (mod / "Foo.omwscripts").exists() and vt.read_intent() is None


def test_a_converter_update_between_plan_and_apply_is_refused(env, capsys):
    root_mod(env.staging, "Foo")
    assert run(env) == 0
    stub = env.tmp / "tools-home" / "tools" / "omw2mwse.py"
    stub.write_text(stub.read_text() + "\n# 0.2.4\n")
    capsys.readouterr()
    assert run(env, "--apply", "--yes") == 2
    assert vt.CHECK_REFUSED in fold(capsys.readouterr().out)
    assert [c for c in env.calls() if "--dry-run" not in c] == []


def test_a_converter_changed_during_the_apply_is_not_run(env, capsys):
    mod = root_mod(env.staging, "Foo")
    assert run(env) == 0
    real = vt.convert_apply

    def swap(*a, **k):
        stub = env.tmp / "tools-home" / "tools" / "omw2mwse.py"
        stub.write_text(stub.read_text() + "\n# swapped mid-run\n")
        return real(*a, **k)
    env.mp.setattr(vt, "convert_apply", swap)
    capsys.readouterr()
    assert run(env, "--apply", "--yes") == 1
    assert vt.CHECK_REFUSED in fold(capsys.readouterr().out)
    assert [c for c in env.calls() if "--dry-run" not in c] == [] and (mod / "Foo.omwscripts").exists()


def test_the_absolute_folder_in_the_json_is_not_part_of_the_digest(env, tmp_path):
    a, b = str(tmp_path / "one" / "M"), str(tmp_path / "two" / "M")
    da = {"dir": a, "dryRun": True, "mods": [{"name": "M", "message": a + os.sep + "x.lua: bad"}]}
    db = {"dir": b, "dryRun": False, "mods": [{"name": "M", "message": b + os.sep + "x.lua: bad"}]}
    assert vt._preview_substance(da, a) == vt._preview_substance(db, b)
    assert vt._preview_substance(da, a)["mods"][0]["message"] == "<mod>/x.lua: bad"


def test_the_plan_shows_rewrites_and_plugin_placements(env):
    root_mod(env.staging, "Foo")
    inject(env, rewrites=[{"key": "Foo.START_HOUR", "file": "scripts/Foo/g.lua", "line": 12, "name": "START_HOUR",
                           "literal": "7"}])
    assert run(env) == 0
    plan = plan_text()
    assert "    omw2mwse makes a setting of Foo's hard-coded value: scripts/Foo/g.lua:12 START_HOUR = 7" in plan
    assert "    omw2mwse places Foo's plugin Foo.esp: root (required) at Foo.esp" in plan


def test_a_rewrite_that_appears_after_the_plan_is_refused(env, capsys):
    root_mod(env.staging, "Foo")
    assert run(env) == 0
    inject(env, rewrites=[{"file": "scripts/Foo/g.lua", "line": 3, "name": "X", "literal": "1"}])
    capsys.readouterr()
    assert run(env, "--apply", "--yes") == 2
    assert vt.CHECK_REFUSED in fold(capsys.readouterr().out)


# ---------------------------------------------------------------- 3. partial API next to readiness

PARTIAL = [{"api": "openmw.core.weather.getTransition", "kind": "symbol", "count": 1,
            "uses": [{"file": "scripts/Foo/g.lua", "line": 378}], "missing": "read from MWSE's weather controller"},
           {"api": "GameObject:remove", "kind": "method", "count": 3,
            "uses": [{"file": "scripts/Foo/g.lua", "line": 289}, {"file": "scripts/Foo/g.lua", "line": 437}],
            "missing": "content refs disabled"},
           {"api": "scriptFlag:CREATURE", "kind": "scriptFlag", "count": 1, "uses": [], "missing": "per object"}]


def test_partial_apis_are_shown_beside_the_verdict_with_their_first_use(env):
    root_mod(env.staging, "Foo")
    inject(env, partialApis=PARTIAL)
    assert run(env) == 0
    plan = " ".join(plan_text().split())
    assert ("Foo ok, verdict ready (partial API: openmw.core.weather.getTransition, GameObject:remove x3, "
            "scriptFlag:CREATURE)") in plan
    assert ("test these in game first: openmw.core.weather.getTransition (scripts/Foo/g.lua:378), "
            "GameObject:remove x3 (scripts/Foo/g.lua:289), scriptFlag:CREATURE") in plan


def test_an_opted_out_mod_never_shows_partial_apis_or_their_files():
    e = {"verdict": "blocked", "reason": {"code": "author-opt-out", "message": "m"}, "partialApis": PARTIAL}
    assert vt.partial_api(e) == [] and vt.partial_api(e, uses=True) == []
    assert vt.readiness_text(e) == "verdict blocked"


def test_the_older_partial_api_shape_still_reads():
    assert vt.partial_api({"partialApi": [{"symbol": "openmw.ui.showMessage", "count": 2}]}) == \
        ["openmw.ui.showMessage x2"]


def test_readiness_reads_a_symbols_map_and_says_nothing_extra_without_one():
    e = {"verdict": "ready", "symbols": {"openmw.ui.showMessage": {"status": "partial", "count": 3},
                                         "openmw.core.getGMST": {"status": "full", "count": 1}}}
    assert vt.readiness_text(e) == "verdict ready (partial API: openmw.ui.showMessage x3)"
    assert vt.readiness_text({"verdict": "ready"}) == "verdict ready"
    assert vt.partial_api({"partialApi": "nonsense"}) == []


# ---------------------------------------------------------------- 4. what ships

def test_with_the_marked_dev_line_removed_the_default_is_normal():
    """ready_to_ship.py flags the marked line; once it is deleted (not just set False) tidy still works and
    converts in normal mode, and an explicit hardcode still works."""
    with open(vt.__file__, encoding="utf-8") as f:
        src = f.read()
    marker = "remove before " + "shipping"
    kept = [ln for ln in src.splitlines(True) if not (ln.startswith("CONVERT_DEV_HARDCODE") and marker in ln.casefold())]
    assert len(kept) == len(src.splitlines(True)) - 1
    ns = {"__name__": "vortex_tidy_shipped", "__file__": vt.__file__}
    exec(compile("".join(kept), vt.__file__, "exec"), ns)
    assert "CONVERT_DEV_HARDCODE" not in ns
    assert ns["convert_mode"]() == "normal"
    assert ns["convert_mode"]("hardcode") == "hardcode" and ns["convert_mode"](None) is None
    assert sys.modules.get("vortex_tidy_shipped") is None


# ---------------------------------------------------------------- the converter's path contract and recovery journal

def test_relative_dot_and_old_absolute_paths_journal_the_same(tmp_path):
    mod = tmp_path / "staging" / "Foo-1-0"
    (mod / "Off" / "Foo" / "OpenMW").mkdir(parents=True)
    new = {"name": "Foo", "source": "Off/Foo/OpenMW", "off": "Off/Foo/OpenMW", "relocatedFrom": ".",
           "relocated": ["Foo.omwscripts"]}
    old = dict(new, source="Off\\Foo\\OpenMW", off="Off\\Foo\\OpenMW", relocatedFrom=str(mod))
    a, b = vt.conversion_op(str(mod), new, "normal"), vt.conversion_op(str(mod), old, "normal")
    assert a == b and a["from"] == "" and a["off"] == "Off/Foo/OpenMW"
    nested = vt.conversion_op(str(mod), dict(new, relocatedFrom="Off/OpenMW/Foo"), "normal")
    assert nested["from"] == "Off/OpenMW/Foo"


def test_the_recovery_folder_is_never_hashed_or_removed(tmp_path):
    mod = tmp_path / "staging" / "Bar-1-0"
    put(mod / "Bar.omwscripts", "x\n")
    j = mod / "MWSE" / "mods" / "mwsuite" / "openmw" / "Bar" / ".omw2mwse-recovery" / "journal.json"
    put(j, "{}")
    assert list(vt.mod_inputs(str(mod))) == ["Bar.omwscripts"]
    assert vt.recovery_journals(str(mod)) == ["MWSE/mods/mwsuite/openmw/Bar/.omw2mwse-recovery/journal.json"]


PENDING = r'''
import json, os, shutil, sys
args = sys.argv[1:]
if args and args[0] == "recover":
    d = args[1]
    with open(os.environ["STUB_LOG"], "a") as f:
        f.write(json.dumps(args) + "\n")
    shutil.rmtree(os.path.join(d, "MWSE", "mods", "mwsuite", "openmw", "Foo", ".omw2mwse-recovery"))
    print(json.dumps({"command": "recover", "rolledBack": [{"mod": "Foo", "stage": "outputs-written",
                      "restored": [], "removed": [], "kept": []}], "pendingRecovery": [], "exitCode": 0}))
    sys.exit(0)
import contextlib, io
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    exec(compile(%r, "stub", "exec"))
data = json.loads(buf.getvalue())
if "--dry-run" not in args:
    d = os.path.realpath(next(a for a in args if not a.startswith("--")))
    j = os.path.join(d, "MWSE", "mods", "mwsuite", "openmw", "Foo", ".omw2mwse-recovery")
    os.makedirs(j, exist_ok=True)
    open(os.path.join(j, "journal.json"), "w").write("{}")
    open(os.path.join(d, ".omw2mwse-x.tmp"), "w").write("half")
    data["pendingRecovery"] = [{"mod": "Foo", "stage": "outputs-written", "mode": "normal",
                                "journal": "MWSE/mods/mwsuite/openmw/Foo/.omw2mwse-recovery/journal.json",
                                "writes": 3, "removes": 0, "relocations": 1}]
print(json.dumps(data))
'''


def test_a_pending_recovery_is_rolled_back_by_omw2mwse_then_tidy_puts_the_folder_back(env, capsys):
    (env.tmp / "tools-home" / "tools" / "omw2mwse.py").write_text(new_interface_stub(PENDING % STUB))
    mod = full_mod(env.staging)
    before = snap(mod)
    env.apply()
    out = " ".join(capsys.readouterr().out.split())
    assert "omw2mwse could not convert Foo-1-0: an unfinished run is pending (Foo, stage outputs-written)" in out
    assert "omw2mwse rolled back its unfinished run" in out
    assert [c[0] for c in env.calls() if c and c[0] == "recover"] == ["recover"]
    after, _ = snap(mod)
    assert not any(k.lower().startswith("mwse") or k.endswith(".tmp") for k in after)
    assert os.path.join("Off", "Foo", "OpenMW", "Foo.omwscripts") in after       # the usual set-aside instead
    assert vt.read_intent() is None
    assert vt.undo() == 0 and snap(mod) == before
