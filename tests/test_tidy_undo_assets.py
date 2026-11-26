"""vortex_tidy --undo and asset repairs: --undo does not reverse a repair, it puts every original file back at its
own path (kept, with its hash, in <backups folder>\\tidy\\<run>\\assets before the repair) and removes the files
the repairs made. Everything here runs in pytest's tmp folder only."""
import json
import os
import types

import pytest

from conftest import ah, vt

TEX = b"DDS original texture bytes"
WAV = b"RIFF original wave bytes"
ESP = b"TES3 original plugin bytes"
OLD_TIME = 1_000_000_000


def tree(root):
    """{relative path: bytes} of every file under root."""
    out = {}
    for base, _ds, fns in os.walk(root):
        for fn in fns:
            p = os.path.join(base, fn)
            with open(p, "rb") as f:
                out[os.path.relpath(p, root)] = f.read()
    return out


def fake_apply_folder(root, fixes, m, game_dir, plug):
    """Stands in for mwdialog_assets.apply_folder: the kinds of change real repairs make."""
    done = 0
    for kind, full, rel, job in fixes:
        off = os.path.join(root, "Off", "converted", plug, rel)
        os.makedirs(os.path.dirname(off), exist_ok=True)
        with open(off, "wb") as f, open(full, "rb") as g:      # the mod's own Off copy
            f.write(g.read())
        if kind == "tex":                                       # repaired in place
            with open(full, "r+b") as f:
                f.write(b"DDS repaired")
                f.truncate()
        elif kind == "snd":                                     # x.wav becomes x.mp3
            with open(os.path.splitext(full)[0] + ".mp3", "wb") as f:
                f.write(b"ID3 new mp3")
            os.remove(full)
        done += 1
    esp = os.path.join(root, plug + ".esp")                     # a name written into the plugin, new date
    with open(esp, "r+b") as f:
        f.write(b"TES3 renamed path")
    os.utime(esp, (OLD_TIME + 999, OLD_TIME + 999))
    return done, []


def make_mod(tmp_path):
    staging = tmp_path / "staging"
    root = staging / "Signs-1234-1-0"
    (root / "textures").mkdir(parents=True)
    (root / "sound").mkdir()
    (root / "textures" / "sign.dds").write_bytes(TEX)
    (root / "sound" / "ding.wav").write_bytes(WAV)
    (root / "Signs.esp").write_bytes(ESP)
    os.utime(root / "Signs.esp", (OLD_TIME, OLD_TIME))
    return staging, root


@pytest.fixture
def env(tmp_path, monkeypatch):
    (tmp_path / "state").mkdir()
    monkeypatch.setattr(vt, "JOURNAL", str(tmp_path / "state" / "vortex_tidy_journal.jsonl"))
    monkeypatch.setattr(vt, "HERE", str(tmp_path / "game"))
    staging, root = make_mod(tmp_path)
    audit = tmp_path / "backups" / "tidy" / "20261125-120000"
    args = types.SimpleNamespace(staging=str(staging), _audit=str(audit),
                                 _journal_extra={"plan_copy": str(audit / "plan_enacted.txt"), "apply": "a2"})
    return types.SimpleNamespace(tmp=tmp_path, staging=staging, root=root, audit=audit, args=args)


def run_repairs(env, apply_folder=fake_apply_folder):
    class Ah:
        update_bug_report = staticmethod(ah.update_bug_report)
        package_bug_report_subject = staticmethod(lambda root, m, name: (name, [f"Bug report for {name}"]))
        package_bug_report_path = staticmethod(ah.package_bug_report_path)
        package_asset_bug_lines = staticmethod(ah.package_asset_bug_lines)
    Ah.apply_folder = staticmethod(apply_folder)
    root = str(env.root)
    fixes = [("tex", os.path.join(root, "textures", "sign.dds"), "textures\\sign.dds", {"dxt": True}),
             ("snd", os.path.join(root, "sound", "ding.wav"), "sound\\ding.wav", {"mp3": True})]
    ent = {"issues": [("WARN", "textures\\sign.dds", "not compressed")], "fixes": fixes, "lp_plan": [], "root": root}
    ares = {"m": None, "ah": Ah, "game_dir": str(env.tmp / "game"), "data_dir": "", "bsa": None, "done": set(),
            "mods": {env.root.name: ent}}
    vt.assets_apply(env.args, ares)
    return ares


def journal(env):
    with open(vt.JOURNAL, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def test_undo_puts_every_original_back_at_its_own_path_and_removes_what_the_repairs_made(env):
    before = tree(env.root)
    run_repairs(env)
    after = tree(env.root)
    assert after != before
    assert "sound\\ding.mp3".replace("\\", os.sep) in after                 # made by the repairs
    assert any(k.startswith("bugreports") for k in after)                   # a new bug report
    assert vt.undo() == 0
    assert tree(env.root) == before                                          # nothing more, nothing less
    assert os.stat(env.root / "Signs.esp").st_mtime == OLD_TIME             # the load-order date is back
    assert journal(env) == []                                                # the run is off the journal


def test_originals_are_kept_with_their_hash_before_anything_changes(env):
    seen = {}

    def check_then_repair(root, fixes, m, game_dir, plug):
        seen["ops"] = [op for op in journal(env) if "asset" in op]
        return fake_apply_folder(root, fixes, m, game_dir, plug)
    run_repairs(env, check_then_repair)
    kept = {os.path.basename(op["asset"]): op for op in seen["ops"]}
    assert {"sign.dds", "ding.wav", "Signs.esp"} <= set(kept)
    for name, data in (("sign.dds", TEX), ("ding.wav", WAV), ("Signs.esp", ESP)):
        with open(kept[name]["backup"], "rb") as f:
            assert f.read() == data
        assert kept[name]["backup"].startswith(str(env.audit / "assets" / env.root.name))
        assert kept[name]["before"] == vt.hashlib.sha256(data).hexdigest()


def test_undo_twice_is_harmless(env):
    before = tree(env.root)
    run_repairs(env)
    assert vt.undo() == 0
    assert vt.undo() == 1                       # nothing left to undo: says so, changes nothing
    assert tree(env.root) == before


def test_a_file_put_back_by_hand_already_counts_as_put_back(env):
    before = tree(env.root)
    run_repairs(env)
    (env.root / "textures" / "sign.dds").write_bytes(TEX)
    assert vt.undo() == 0
    assert tree(env.root) == before


def test_a_missing_original_stops_the_undo_before_anything_changes(env, capsys):
    run_repairs(env)
    repaired = tree(env.root)
    lines = open(vt.JOURNAL, encoding="utf-8").read()
    bak = next(op["backup"] for op in journal(env) if "asset" in op and op["asset"].endswith("sign.dds"))
    os.remove(bak)
    assert vt.undo() == 1
    assert tree(env.root) == repaired                                         # nothing was changed
    assert open(vt.JOURNAL, encoding="utf-8").read() == lines                # the journal neither
    err = capsys.readouterr().err
    assert "changed nothing" in err and "original is missing" in err and "sign.dds" in err


def test_an_altered_original_stops_the_undo(env, capsys):
    run_repairs(env)
    bak = next(op["backup"] for op in journal(env) if "asset" in op and op["asset"].endswith("Signs.esp"))
    with open(bak, "wb") as f:
        f.write(b"something else")
    repaired = tree(env.root)
    assert vt.undo() == 1
    assert tree(env.root) == repaired
    assert "different hash" in capsys.readouterr().err


def test_a_file_changed_since_the_repair_needs_force(env, capsys):
    before = tree(env.root)
    run_repairs(env)
    (env.root / "textures" / "sign.dds").write_bytes(b"DDS edited by hand later")
    assert vt.undo() == 1
    assert "changed since" in capsys.readouterr().err
    assert (env.root / "textures" / "sign.dds").read_bytes() == b"DDS edited by hand later"
    assert vt.undo(force=True) == 0
    assert tree(env.root) == before


def test_undo_keeps_a_hard_link_a_hard_link(env, tmp_path):
    deployed = tmp_path / "game" / "Data Files" / "textures" / "sign.dds"
    deployed.parent.mkdir(parents=True)
    try:
        os.link(env.root / "textures" / "sign.dds", deployed)
    except (OSError, AttributeError):
        pytest.skip("no hard links here")
    run_repairs(env)
    assert deployed.read_bytes() == b"DDS repaired"                           # repaired in place: both changed
    assert vt.undo() == 0
    assert deployed.read_bytes() == TEX                                       # put back in place: both back


def test_a_mod_whose_originals_cannot_be_kept_is_not_repaired(env, monkeypatch, capsys):
    before = tree(env.root)

    def no_copy(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(vt.shutil, "copy2", no_copy)
    calls = []
    run_repairs(env, lambda *a: calls.append(a) or (0, []))
    assert calls == []
    assert tree(env.root) == before
    assert "NOT repaired" in capsys.readouterr().out


def test_without_a_run_folder_nothing_is_journaled(env):
    env.args._audit = None
    run_repairs(env)
    assert not os.path.exists(vt.JOURNAL)


def test_one_undo_undoes_the_whole_last_apply_moves_too(env):
    """The moves, Lua patches and asset repairs of one --apply are journaled under one head each (same "apply"
    id): one --undo puts back all of them, the repairs first."""
    src = env.root / "readme.txt"
    src.write_bytes(b"read me")
    before = tree(env.staging)
    dst = env.root / "Docs" / "Signs - readme.txt"
    vt.apply([(str(src), str(dst), "document")], str(env.staging), head_extra=env.args._journal_extra)
    run_repairs(env)
    assert vt.undo() == 0
    assert tree(env.staging) == before
    assert journal(env) == []


def test_an_earlier_apply_is_left_for_the_next_undo(env):
    other = env.staging / "Other"
    other.mkdir()
    (other / "a.txt").write_bytes(b"a")
    vt.apply([(str(other / "a.txt"), str(other / "Docs" / "a.txt"), "document")], str(env.staging),
             head_extra={"apply": "a1"})
    before = tree(env.root)
    run_repairs(env)
    assert vt.undo() == 0
    assert tree(env.root) == before
    assert (other / "Docs" / "a.txt").exists()                               # the earlier --apply is untouched
    assert vt.undo() == 0
    assert (other / "a.txt").exists()


def test_mwse_core_lua_patch_needs_its_original_too(env, tmp_path, capsys):
    """MWSE's core files are patched in place in Data Files; --undo checks their kept originals the same way."""
    lf = vt._luafix()
    core = tmp_path / "game" / "Data Files" / "MWSE" / "core" / "mcm" / "x.lua"
    core.parent.mkdir(parents=True)
    old, new = b"local a = 1\n", b"local a = 2\n"
    core.write_bytes(new)
    bak = tmp_path / "backups" / "luafix" / "run" / "x.lua"
    bak.parent.mkdir(parents=True)
    with open(vt.JOURNAL, "w", encoding="utf-8") as j:
        j.write(json.dumps({"run": "2026-11-25 12:00:00", "what": "luafix", "lua": True,
                            "staging": str(env.staging), "apply": "a1"}) + "\n")
        j.write(json.dumps({"luafix": str(core), "backup": str(bak), "before": lf.sha(old),
                            "after": lf.sha(new)}) + "\n")
    assert vt.undo() == 1                                                     # its original is missing
    assert core.read_bytes() == new
    assert "original is missing" in capsys.readouterr().err
    bak.write_bytes(old)
    assert vt.undo() == 0
    assert core.read_bytes() == old


def test_short_path_records_tidy_made_are_dropped(env, monkeypatch):
    saved = {}

    class Record:
        def __init__(self, game_dir):
            self.moves = [{"orig": "meshes\\a\\long.nif", "short": "meshes\\s\\1.nif", "by": "tidy",
                           "mod": env.root.name},
                          {"orig": "meshes\\b.nif", "short": "meshes\\s\\2.nif", "by": "check"}]

        def save(self):
            saved["moves"] = self.moves
    monkeypatch.setattr(vt, "_lp_module", lambda: types.SimpleNamespace(
        Record=Record, norm=lambda r: r.replace("/", "\\").lower()))
    vt._asset_undo({}, [{"asset_lp_record": "meshes\\a\\long.nif", "mod": env.root.name}], False)
    assert [x["orig"] for x in saved["moves"]] == ["meshes\\b.nif"]


def test_candidates_cover_same_named_files_renames_plugins_and_bug_reports(env):
    (env.root / "textures" / "sign.tga").write_bytes(b"x")
    (env.root / "bugreports").mkdir()
    (env.root / "bugreports" / "Signs.bugreport.txt").write_bytes(b"r")
    (env.root / "Off" / "converted" / "Signs" / "textures").mkdir(parents=True)
    (env.root / "Off" / "converted" / "Signs" / "textures" / "a.dds.repaired.sha256").write_bytes(b"h")
    (env.root / "textures" / "other.dds").write_bytes(b"o")
    root = str(env.root)
    got = {os.path.relpath(p, root) for p in vt._repair_candidates(
        root, [("tex", os.path.join(root, "textures", "sign.dds"), "textures\\sign.dds", {})], [])}
    want = {os.path.join("textures", "sign.dds"), os.path.join("textures", "sign.tga"), "Signs.esp",
            os.path.join("bugreports", "Signs.bugreport.txt"),
            os.path.join("Off", "converted", "Signs", "textures", "a.dds.repaired.sha256")}
    assert got == want
