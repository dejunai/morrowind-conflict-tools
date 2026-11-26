"""vortex_tidy: a file both too long for Windows once deployed and broken (MWManager's "Zz Deep Path"). The long-path
move takes it to <top>\\lp\\..., and its dummy repair is made there in the same --apply (it used to be dropped as
"moved: next run", leaving a plan line pending and --apply exiting 1). The original goes to
Off\\<plugin>\\broken\\<short path>; --undo puts everything back. pytest's tmp folder only."""
import json
import os
import types

import pytest

from conftest import ah, m, plugin, vt

GARBAGE_NIF = b"Gamebryo File Format, Version 20.0.0.5\n" + b"\1" * 80
DEEP = "averyveryverylongfoldername_of_a_mod_that_likes_long_names"
lp = m.longpaths_module()


def tree(root):
    out = {}
    for base, _ds, fns in os.walk(root):
        for fn in fns:
            p = os.path.join(base, fn)
            with open(p, "rb") as f:
                out[os.path.relpath(p, root)] = f.read()
    return out


@pytest.fixture
def env(tmp_path, monkeypatch):
    game = tmp_path / "game"
    df = game / "Data Files"
    df.mkdir(parents=True)
    (game / "Morrowind.ini").write_text("[Game Files]\n")
    (tmp_path / "state").mkdir()
    monkeypatch.setattr(vt, "JOURNAL", str(tmp_path / "state" / "vortex_tidy_journal.jsonl"))
    monkeypatch.setattr(vt, "HERE", str(game))
    monkeypatch.setattr(vt, "CORE_MISSING", {})
    monkeypatch.setattr(vt, "blacklist", lambda create=False: [])
    # a small limit, so the test path counts as too long once deployed: Data Files + 70 characters
    monkeypatch.setattr(lp, "MAX_PATH_CHARS", len(str(df)) + 1 + 70)
    monkeypatch.setattr(lp, "NEAR_CHARS", len(str(df)) + 1 + 60)
    staging = tmp_path / "staging"
    root = staging / "Zz Deep Path-1-0"
    long_rel = os.path.join("meshes", DEEP, DEEP, "bad.nif")
    (root / os.path.dirname(long_rel)).mkdir(parents=True)
    (root / long_rel).write_bytes(GARBAGE_NIF)
    plugin(str(root / "Deep.esp"), [], [])
    audit = tmp_path / "backups" / "tidy" / "run"
    args = types.SimpleNamespace(staging=str(staging), only=None, skip=None, apply=True, _audit=str(audit),
                                 _journal_extra={"plan_copy": str(audit / "plan_enacted.txt"), "apply": "a1"})
    return types.SimpleNamespace(game=game, df=df, root=root, long_rel=long_rel, args=args)


def test_the_plan_both_shortens_and_repairs_the_file(env):
    ent = vt.assets_check_mod(str(env.root), m, ah, str(env.df), set(), str(env.game), {})
    assert [p["orig"] for p in ent["lp_plan"]] == [env.long_rel]
    assert [(f[0], f[2]) for f in ent["fixes"]] == [("dummy", env.long_rel)]


def test_a_too_long_broken_file_is_moved_and_repaired_at_its_short_path_in_one_apply(env):
    ares = vt.assets_check(env.args)
    ent = ares["mods"]["Zz Deep Path-1-0"]
    short = lp.fs(ent["lp_plan"][0]["short"])
    planned = vt.assets_pending(ares)
    assert any(ln.strip().startswith("repair dummy " + env.long_rel) for ln in planned)
    assert any(ln.strip().startswith("shorten ") for ln in planned)
    vt.assets_apply(env.args, ares)
    assert vt.assets_pending(ares) == []                         # nothing left: --apply exits 0
    assert not (env.root / env.long_rel).exists()
    assert (env.root / short).read_bytes() not in (GARBAGE_NIF, b"")     # the dummy, at the short path
    off = env.root / "Off" / "Deep" / "broken" / short           # the Off layout, under the path the mod deploys
    assert off.read_bytes() == GARBAGE_NIF
    mark = json.loads((env.root / "Off" / "Deep" / "broken" / (short + vt.DUMMY_MARK)).read_text())
    assert mark["rel"] == short
    assert len(str(off)) < len(str(env.root / "Off" / "Deep" / "broken" / env.long_rel))


def test_a_later_run_finds_nothing_left_to_do(env):
    vt.assets_apply(env.args, vt.assets_check(env.args))
    ent = vt.assets_check_mod(str(env.root), m, ah, str(env.df), set(), str(env.game), {})
    assert ent["fixes"] == [] and ent["lp_plan"] == []


def test_undo_puts_the_long_original_back_and_removes_the_dummy_and_off_copy(env):
    before = tree(env.root)
    vt.assets_apply(env.args, vt.assets_check(env.args))
    assert tree(env.root) != before
    assert vt.undo() == 0
    assert tree(env.root) == before


def test_a_failed_move_keeps_the_repair_pending_for_the_next_run(env, monkeypatch):
    ares = vt.assets_check(env.args)
    monkeypatch.setattr(lp, "_move", lambda src, dst: (_ for _ in ()).throw(OSError("in use")))
    vt.assets_apply(env.args, ares)
    left = vt.assets_pending(ares)
    assert any(ln.strip().startswith("repair dummy " + env.long_rel) for ln in left)
    assert (env.root / env.long_rel).read_bytes() == GARBAGE_NIF  # nothing done to it