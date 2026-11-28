"""The pre-deploy rule (dej's, CT-41): tidy, luafix and the OpenMW converter handoff work on STAGED files only. Nothing
is written to Data Files before the final deploy step, and nothing there is read except the documented read-only
exceptions (mwdialog_staged.READ_EXCEPTIONS: the base game's BSAs and masters, its own loose Video/Fonts files and
MWSE\\config\\mwguard.json). Each test builds a fake game with a Data Files folder whose files are Vortex-style hard
links to the staged ones, watches every open / listdir / scandir / replace / rename / remove / mkdir / utime into
Data Files (and every write-mode open of a file hard-linked into it), and compares Data Files' hashes, sizes and
dates before and after. Temporary folders only; never a game install. Python 3.9+."""
import builtins
import hashlib
import io
import json
import os
import shutil
import types
from pathlib import Path

import pytest

from conftest import _load, fold, plugin, vt
from omw_interface_stub import mode_of, new_interface_stub
from test_cr18_suite_logging import LUAJIT, need_lua

MS = _load("mwdialog_staged")
lf = _load("mwdialog_luafix")
T3 = _load("mwdialog_tes3")

QUIET = "print('[ticker] initialized')\n"


def _norm(p):
    p = os.fsdecode(p)
    if p.startswith("\\\\?\\"):
        p = p[4:]
    return os.path.normcase(os.path.abspath(p))


class Guard:
    """Records every touch of Data Files (and every write through a hard link into it) while installed."""

    def __init__(self, data_dir):
        self.data = _norm(data_dir)
        self.reads, self.writes = [], []
        self.inodes = set()
        for base, _ds, fns in os.walk(data_dir):
            for fn in fns:
                st = os.stat(os.path.join(base, fn))
                self.inodes.add((st.st_dev, st.st_ino))

    def inside(self, p):
        try:
            n = _norm(p)
        except (TypeError, ValueError):
            return False
        return n == self.data or n.startswith(self.data + os.sep)

    def linked(self, p):
        try:
            st = os.stat(p)
        except (OSError, TypeError, ValueError):
            return False
        return (st.st_dev, st.st_ino) in self.inodes

    def read(self, p):
        if self.inside(p) and not MS.is_read_exception(os.fsdecode(p), self.data):
            self.reads.append(os.fsdecode(p))

    def write(self, p):
        if self.inside(p):
            self.writes.append(os.fsdecode(p))


def snapshot(data_dir):
    out = {}
    for base, _ds, fns in os.walk(data_dir):
        for fn in fns:
            p = os.path.join(base, fn)
            st = os.stat(p)
            with open(p, "rb") as f:
                out[os.path.relpath(p, data_dir)] = (hashlib.sha256(f.read()).hexdigest(), st.st_size, st.st_mtime_ns)
    return out


@pytest.fixture
def watch(monkeypatch):
    """watch(data_dir) -> Guard, with open/os/shutil patched to report into it."""
    def install(data_dir):
        g = Guard(data_dir)
        real_open = builtins.open

        def fake_open(file, mode="r", *a, **k):
            if isinstance(file, (str, bytes, os.PathLike)):
                if any(c in mode for c in "wax+"):
                    g.write(file)
                    if g.linked(file):
                        g.writes.append(os.fsdecode(file) + " (written through a hard link into Data Files)")
                else:
                    g.read(file)
            return real_open(file, mode, *a, **k)
        monkeypatch.setattr(builtins, "open", fake_open)
        monkeypatch.setattr(io, "open", fake_open)
        for name in ("listdir", "scandir"):
            real = getattr(os, name)

            def lister(path=".", _real=real):
                if not isinstance(path, int):
                    g.read(path)
                return _real(path)
            monkeypatch.setattr(os, name, lister)
        for name in ("remove", "unlink", "mkdir", "makedirs", "rmdir", "utime"):
            real = getattr(os, name)

            def one(path, *a, _real=real, **k):
                g.write(path)
                return _real(path, *a, **k)
            monkeypatch.setattr(os, name, one)
        for name in ("replace", "rename"):
            real = getattr(os, name)

            def two(src, dst, *a, _real=real, **k):
                g.write(src)
                g.write(dst)
                return _real(src, dst, *a, **k)
            monkeypatch.setattr(os, name, two)
        real_move = shutil.move

        def move(src, dst, *a, **k):
            g.write(src)
            g.write(dst)
            return real_move(src, dst, *a, **k)
        monkeypatch.setattr(shutil, "move", move)
        return g
    return install


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())


def deploy_links(staging, data):
    """Hard-link every staged file into Data Files, as Vortex's hardlink deployment does (not Off\\)."""
    for mod in os.listdir(staging):
        root = os.path.join(staging, mod)
        for base, dirs, fns in os.walk(root):
            dirs[:] = [d for d in dirs if d.lower() != "off"]
            for fn in fns:
                src = os.path.join(base, fn)
                dst = os.path.join(data, os.path.relpath(src, root))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if not os.path.exists(dst):
                    os.link(src, dst)


@pytest.fixture
def game(tmp_path, monkeypatch):
    g = tmp_path / "Morrowind"
    data = g / "Data Files"
    put(g / "Morrowind.ini", "[Game Files]\nGameFile0=Morrowind.esm\nGameFile1=Loose.esp\n")
    put(data / "Loose.esp", b"TES3 a plugin installed by hand, never staged")
    put(data / "textures" / "loose_only.dds", b"DDS loose, not staged")
    put(data / "MWSE" / "config" / "mwguard.json", json.dumps({"luafix": {}}))
    put(data / "MWSE" / "core" / "mcm" / "components" / "pages" / "ExclusionsPage.lua", "-- MWSE core\n")
    staging = tmp_path / "staging"
    staging.mkdir()
    for k, v in (("HERE", str(g)), ("CORE_MISSING", {}), ("JOURNAL", str(tmp_path / "tidy_journal.jsonl")),
                 ("PLAN", str(tmp_path / "vortex_tidy_plan.txt")), ("AUDIT_ROOT", str(tmp_path / "audit")),
                 ("BLACKLIST_FILE", str(tmp_path / "bl.txt"))):
        monkeypatch.setattr(vt, k, v)
    monkeypatch.setattr(vt, "vortex_info", lambda d: {})
    for d in (vt.NOTES, vt.REVIEW, vt.CONVERTED, vt.CONVERT):
        d.clear()
    monkeypatch.setattr(lf, "HERE", str(g))
    monkeypatch.setattr(lf, "JOURNAL", str(tmp_path / "luafix_journal.jsonl"))
    monkeypatch.setattr(lf, "BACKUP_ROOT", str(tmp_path / "backups"))
    return types.SimpleNamespace(dir=g, data=data, staging=staging, tmp=tmp_path)


def assets_mod(staging):
    mod = staging / "Signs-1234-1-0"
    mod.mkdir(parents=True)
    plugin(str(mod / "Signs.esp"), [], [])
    put(mod / "readme.txt", "Signs readme\n")
    put(mod / "preview.jpg", b"\xff\xd8\xff not really a jpeg")
    put(mod / "textures" / "tx_sign.dds", b"DDS diffuse")
    put(mod / "textures" / "tx_sign_n.dds", b"DDS normal map")
    put(mod / "meshes" / "signs" / "broken.nif", b"")
    return mod


def lua_mod(staging):
    mod = staging / "Ticker-1-0"
    put(mod / "MWSE" / "mods" / "ticker" / "main.lua", QUIET)
    return mod


def run_tidy(monkeypatch, staging, *extra):
    monkeypatch.setattr(vt.sys, "argv", ["vortex_tidy.py", "--staging", str(staging), "--no-convert-omwscripts",
                                         "--no-coins", *extra])
    return vt.main()


# ------------------------------------------------------------------------------------------------ tidy
@need_lua
def test_tidy_plan_apply_and_undo_never_touch_data_files(game, watch, monkeypatch):
    mod = assets_mod(game.staging)
    lua_mod(game.staging)
    deploy_links(game.staging, game.data)
    before = snapshot(game.data)
    g = watch(game.data)
    jit = ["--luajit", LUAJIT]
    assert run_tidy(monkeypatch, game.staging, *jit) == 0                  # the plan
    assert run_tidy(monkeypatch, game.staging, "--apply", "--yes", *jit) == 0
    assert not (mod / "readme.txt").exists()                               # staging really changed
    assert run_tidy(monkeypatch, game.staging, "--undo", *jit) == 0
    assert g.writes == []
    assert g.reads == []
    assert snapshot(game.data) == before


def test_tidy_apply_writes_staged_files_as_new_files_and_breaks_the_link(game, monkeypatch):
    mod = assets_mod(game.staging)
    deploy_links(game.staging, game.data)
    before = snapshot(game.data)
    assert run_tidy(monkeypatch, game.staging, "--no-lua") == 0
    assert run_tidy(monkeypatch, game.staging, "--no-lua", "--apply", "--yes") == 0
    assert snapshot(game.data) == before
    for base, _ds, fns in os.walk(mod):                                    # what tidy changed is no longer shared
        for fn in fns:
            p = os.path.join(base, fn)
            d = os.path.join(game.data, os.path.relpath(p, mod))
            if os.path.exists(d) and os.path.samefile(p, d):
                with open(p, "rb") as a, open(d, "rb") as b:
                    assert a.read() == b.read()


def test_tidy_lua_check_reads_staging_and_lua_tools_only(game, watch, monkeypatch):
    lua_mod(game.staging)
    deploy_links(game.staging, game.data)
    g = watch(game.data)
    args = types.SimpleNamespace(staging=str(game.staging), only=None, skip=None, apply=False, luajit=None,
                                 lua_level="high", lua_log="all")
    monkeypatch.setattr(vt, "blacklist", lambda create=False: [])
    res = vt.lua_check(args)
    assert res is not None and vt.CORE_KEY not in dict(res["reps"])        # MWSE core in Data Files: left to deploy
    assert g.reads == [] and g.writes == []


# ------------------------------------------------------------------------------------------------ luafix
def run_luafix(*argv):
    return lf.main(list(argv))


def test_luafix_plan_and_apply_patch_the_staged_file_never_data_files(game, watch, monkeypatch):
    mod = lua_mod(game.staging)
    deploy_links(game.staging, game.data)
    staged = mod / "MWSE" / "mods" / "ticker" / "main.lua"
    deployed = game.data / "MWSE" / "mods" / "ticker" / "main.lua"
    assert os.path.samefile(staged, deployed)
    before = snapshot(game.data)
    g = watch(game.data)
    base = ["--staging", str(game.staging), "--no-syntax-check", "--lua-log", "all"]
    assert run_luafix(*base) == 0                                          # plan: default = every staged MWSE mod
    assert run_luafix(*base, "--apply", "--yes") == 0
    patched = staged.read_text()
    with MS.staged_run(str(game.staging), str(game.dir)):                 # what --undo runs in (its journal)
        assert lf.undo(journal=lf.JOURNAL) == 0
    assert g.writes == [] and g.reads == []                                # (before the checks below read Data Files)
    assert patched != QUIET and lf.SHIM_END in patched                     # the staged copy was patched
    assert staged.read_text() == QUIET                                     # and put back by --undo
    assert deployed.read_text() == QUIET                                   # Data Files kept the old one throughout
    assert snapshot(game.data) == before


def test_luafix_refuses_a_data_files_path_before_deploy(game, capsys):
    assert run_luafix(str(game.data / "MWSE" / "mods"), "--staging", str(game.staging)) == 2
    assert "it is in Data Files" in fold(capsys.readouterr().err)


# ------------------------------------------------------------------------------------------------ write primitives
def linked_pair(game):
    mod = game.staging / "M-1"
    put(mod / "textures" / "a.dds", b"old")
    deploy_links(game.staging, game.data)
    return mod / "textures" / "a.dds", game.data / "textures" / "a.dds"


def test_safe_write_bytes_in_a_staged_run_replaces_instead_of_writing_through(game):
    staged, deployed = linked_pair(game)
    with MS.staged_run(str(game.staging), str(game.dir)):
        T3.safe_write_bytes(str(staged), b"new")
        with pytest.raises(MS.DataFilesWriteError):
            T3.safe_write_bytes(str(deployed), b"never")
        with pytest.raises(MS.DataFilesWriteError):
            with T3.atomic_open(str(game.data / "x.txt")) as f:
                f.write("never")
    assert staged.read_bytes() == b"new" and deployed.read_bytes() == b"old"
    assert not (game.data / "x.txt").exists()


def test_outside_a_staged_run_the_deploy_time_behaviour_is_unchanged(game):
    staged, deployed = linked_pair(game)
    T3.safe_write_bytes(str(staged), b"new")                               # mwdialog_check --fix, --play: in place
    assert deployed.read_bytes() == b"new"


def test_luafix_write_in_place_breaks_the_link_in_a_staged_run(game):
    staged, deployed = linked_pair(game)
    with MS.staged_run(str(game.staging), str(game.dir)):
        lf.write_in_place(str(staged), b"patched")
        with pytest.raises(MS.DataFilesWriteError):
            lf.write_in_place(str(deployed), b"never")
    assert staged.read_bytes() == b"patched" and deployed.read_bytes() == b"old"


def test_detach_tree_gives_every_linked_staged_file_its_own_copy(game):
    staged, deployed = linked_pair(game)
    with MS.staged_run(str(game.staging), str(game.dir)):
        assert MS.detach_tree(str(game.staging)) == 1
    assert not os.path.samefile(staged, deployed) and staged.read_bytes() == deployed.read_bytes() == b"old"


def test_read_exceptions_are_the_base_game_files_only(game):
    d = str(game.data)
    put(game.data / "Video" / "intro.bik", b"bik")
    assert MS.is_read_exception(os.path.join(d, "Morrowind.bsa"), d)
    assert MS.is_read_exception(os.path.join(d, "Bloodmoon.esm"), d)
    assert MS.is_read_exception(os.path.join(d, "MWSE", "config", "mwguard.json"), d)
    assert MS.is_read_exception(os.path.join(d, "Video", "intro.bik"), d)
    assert not MS.is_read_exception(os.path.join(d, "Loose.esp"), d)
    assert not MS.is_read_exception(os.path.join(d, "MWSE", "mods", "x", "main.lua"), d)
    assert not MS.is_read_exception(os.path.join(d, "textures", "loose_only.dds"), d)


# ------------------------------------------------------------------------------------------------ converter handoff
STUB = r'''
import json, os, shutil, sys
args = sys.argv[1:]
mode = next(a.split("=", 1)[1] for a in args if a.startswith("--convert-omwscripts="))
d = next(a for a in args if not a.startswith("--"))
dry = "--dry-run" in args
name = os.path.basename(d).split("-")[0]
mod = {"name": name, "source": ".", "status": "ok", "verdict": "ready", "alerts": []}
if not dry:
    out = os.path.join(d, "MWSE", "mods", "mwsuite", "openmw", name)
    os.makedirs(out)
    with open(os.path.join(out, "main.lua"), "w") as f:
        f.write("-- %s: MWSE loader generated by omw2mwse 0.3.1.\n" % name)
    lib = os.path.join(d, "MWSE", "lib")
    os.makedirs(lib, exist_ok=True)
    with open(os.path.join(lib, "omwcompat.lua"), "w") as f:
        f.write("-- generated by omw2mwse: omwcompat runtime\n")
    off = os.path.join(d, "Off", name, "OpenMW")
    os.makedirs(off)
    for e in os.listdir(d):
        if e.lower().endswith(".omwscripts") or e.lower() == "scripts":
            shutil.move(os.path.join(d, e), os.path.join(off, e))
    with open(os.path.join(d, "%s.omwscripts.note" % name), "w") as f:
        f.write("x")
    os.remove(os.path.join(d, "%s.omwscripts.note" % name))
    # a converter that writes over an existing staged file in place (what interface 1 forbids, tidy guards anyway)
    with open(os.path.join(d, "shared.txt"), "r+") as f:
        f.write("CHANGED")
mod["off"] = "Off/%s/OpenMW" % name
print(json.dumps({"tool": "omw2mwse", "version": "0.3.1", "dryRun": dry, "changed": not dry, "mods": [mod]}))
sys.exit(0)
'''


@pytest.fixture
def converter(game, monkeypatch):
    home = game.tmp / "tools-home"
    (home / "tools").mkdir(parents=True)
    (home / "tools" / "omw2mwse.py").write_text(new_interface_stub(STUB))
    monkeypatch.setenv("PATH", str(game.tmp / "empty-path"))
    monkeypatch.setenv("STUB_LOG", str(game.tmp / "calls.jsonl"))
    monkeypatch.setattr(vt, "CONVERTER_HOME", str(home))
    monkeypatch.setattr(vt, "CONVERTER", dict(vt.CONVERTER))
    monkeypatch.setattr(vt, "interpreter_version", lambda cmd: (3, 11))
    return lambda: [json.loads(x) for x in (game.tmp / "calls.jsonl").read_text().splitlines()]


def openmw_mod(staging):
    mod = staging / "Glow-1-0"
    put(mod / "Glow.omwscripts", "GLOBAL: scripts/Glow/g.lua\n")
    put(mod / "scripts" / "Glow" / "g.lua", "return {}\n")
    put(mod / "shared.txt", "original")
    return mod


def test_converter_gets_the_staged_mod_and_its_output_stays_in_staging(game, converter, monkeypatch):
    mod = openmw_mod(game.staging)
    deploy_links(game.staging, game.data)
    before = snapshot(game.data)
    monkeypatch.setattr(vt.sys, "argv", ["vortex_tidy.py", "--staging", str(game.staging), "--no-lua", "--no-assets",
                                         "--convert-omwscripts=normal"])
    assert vt.main() == 0
    monkeypatch.setattr(vt.sys, "argv", vt.sys.argv + ["--apply", "--yes"])
    assert vt.main() == 0
    calls = converter()
    assert "--dry-run" in calls[0] and [c for c in calls if "--dry-run" not in c] == calls[-1:]
    for c in calls:
        assert c[:2] == ["--staged-root", str(mod)] and mode_of(c) == "normal"
        res = c[c.index("--result-json") + 1]
        assert not MS.in_data_files(res, str(game.data)) and not res.startswith(str(game.staging))
        assert not res.startswith(str(game.dir)) and not os.path.exists(res)   # a temp file, removed afterwards
        assert "--no-runtime" not in c and not any("Data Files" in a for a in c)
    assert (mod / "MWSE" / "lib" / "omwcompat.lua").exists()                # the runtime is staged too
    assert (mod / "Off" / "Glow" / "OpenMW" / "Glow.omwscripts").exists()
    assert (mod / "shared.txt").read_text().startswith("CHANGED")
    assert snapshot(game.data) == before                                    # incl. shared.txt: the link was broken first
    op = next(json.loads(x) for x in open(vt.JOURNAL, encoding="utf-8") if '"omw_convert"' in x)
    assert "MWSE/lib/omwcompat.lua" in op["written"] and "Glow.omwscripts" in op["moved"]
    monkeypatch.setattr(vt.sys, "argv", ["vortex_tidy.py", "--undo"])
    assert vt.main() == 0
    assert (mod / "Glow.omwscripts").exists() and not (mod / "MWSE").exists()
    assert snapshot(game.data) == before


def test_converter_is_never_pointed_at_data_files_or_the_game(game, monkeypatch):
    called = []
    monkeypatch.setattr(vt.subprocess, "run", lambda *a, **k: called.append(a))
    monkeypatch.setattr(vt, "CONVERTER", dict(vt.CONVERTER, cmd=["omw2mwse"]))
    for target in (game.data / "Glow", game.dir, game.data):
        code, data, err = vt.run_converter(str(target), "normal", dry_run=True)
        assert code is None and data is None and "not handed to omw2mwse" in err
    assert called == []


@pytest.mark.parametrize("exit_code,errors,want", [
    (0, [], 0), (1, [], 0), (2, [{"code": "conflict", "message": "x: not ours"}], 4),
    (2, [{"code": "hardcode-not-accepted", "message": "needs --accept-hardcode-conversions"}], 3),
    (2, [{"code": "error", "message": "boom"}], 2), (3, [{"code": "target-refused", "message": "Data Files"}], 2),
    (70, [{"code": "internal-error", "message": "bug"}], 70)])
def test_converter_result_maps_interface_1_onto_tidys_outcomes(tmp_path, exit_code, errors, want):
    mod = tmp_path / "Foo-1"
    mod.mkdir()
    verdict = {0: "ready", 1: "blocked", 2: "failed", 3: "refused", 70: "error"}[exit_code]
    doc = {"interface": 1, "tool": "omw2mwse", "version": "0.3.1", "requiresPython": ">=3.9", "dry_run": False,
           "exit_code": exit_code, "verdict": verdict, "blockers": ["needs openmw.ui"] if exit_code == 1 else [],
           "guards": ["activeDedupe"], "runtime_version": "0.4.0",
           "written_files": ["MWSE/lib/omwcompat.lua"] if exit_code == 0 else [], "planned_files": [],
           "removed_files": [], "moved_files": ["Foo.omwscripts"] if exit_code == 0 else [],
           "excluded_by_author": False, "errors": errors,
           "mods": [{"name": "Foo", "source": ".", "verdict": verdict, "blockers": [], "guards": {},
                     "off": "Off/Foo/OpenMW"}]}
    code, data = vt.converter_result(exit_code, doc, str(mod))
    assert code == want
    m = data["mods"][0]
    if exit_code == 0:
        assert m["status"] == "ok" and m["written_files"] == ["MWSE/lib/omwcompat.lua"] and m["relocatedFrom"] == ""
    if exit_code == 1:
        assert m["verdict"] == "blocked" and "needs openmw.ui" in vt.blocked_reason(m)
    if exit_code in (2, 3, 70):
        assert vt.converter_summary(code, data, "")[0] is False


def test_an_author_exclusion_never_names_a_file_or_line(tmp_path):
    doc = {"interface": 1, "exit_code": 1, "verdict": "blocked", "excluded_by_author": True, "blockers": ["fixed"],
           "mods": [], "written_files": [], "moved_files": [], "removed_files": [], "errors": []}
    code, data = vt.converter_result(1, doc, str(tmp_path))
    (m,) = data["mods"]
    assert code == 0 and vt.is_opt_out(m) and vt.blocked_reason(m) == vt.OPT_OUT_TEXT


# ------------------------------------------------------------------------------------------------ write-root guard
def _junction(link, target):
    """A directory junction (no admin rights needed), or skip."""
    if os.name != "nt":
        try:
            os.symlink(str(target), str(link), target_is_directory=True)
            return link
        except OSError as e:
            pytest.skip(f"no symlinks here: {e}")
    import subprocess
    r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)
    if r.returncode or not os.path.isdir(link):
        pytest.skip("could not make a junction")
    return link


def _symlink(link, target):
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
    except (OSError, NotImplementedError) as e:
        pytest.skip(f"no directory symlinks without rights: {e}")
    return link


def _aliases(game):
    """Data Files, the game folder, a folder in each, other spellings and junction aliases of both."""
    data, g = game.data, game.dir
    (data / "Meshes").mkdir(exist_ok=True)
    out = [data, g, data / "Meshes", g / "conflict-tools", Path(str(data).upper()), Path(str(g).lower()),
           Path(str(data) + os.sep), _junction(game.tmp / "dataalias", data), _junction(game.tmp / "gamealias", g)]
    out.append(game.tmp / "gamealias" / "Data Files")
    return out


def test_guard_refuses_data_files_the_game_and_their_aliases(game):
    for target in _aliases(game):
        for mode in ("tidy", "converter", "luafix", "apply", "undo"):
            assert MS.write_root_problem(target, str(game.dir), str(game.data), mode=mode), (target, mode)
            assert MS.write_root_problem(target, mode=mode), (target, mode)       # found without being told
            with pytest.raises(MS.DataFilesWriteError, match="refuses to write"):
                MS.require_write_root(target, str(game.dir), str(game.data), mode=mode)
    assert MS.write_root_problem(game.staging, str(game.dir), str(game.data)) == ""
    assert MS.write_root_problem(game.staging / "Some Mod", str(game.dir), str(game.data)) == ""


def test_guard_refuses_a_symlink_alias(game):
    link = _symlink(game.tmp / "datasym", game.data)
    assert MS.write_root_problem(link, str(game.dir), str(game.data))
    assert MS.write_root_problem(link / "Meshes", str(game.dir), str(game.data))
    with MS.staged_run(str(game.staging), str(game.dir)):
        with pytest.raises(MS.DataFilesWriteError):
            MS.check_write(str(link / "new.esp"))


def test_check_write_follows_junctions_and_ignores_case(game):
    alias = _junction(game.tmp / "dataalias", game.data)
    with MS.staged_run(str(game.staging), str(game.dir)):
        for p in (alias / "x.esp", Path(str(game.data).upper()) / "X.ESP", game.dir / "data files" / "y.dds"):
            with pytest.raises(MS.DataFilesWriteError):
                MS.check_write(str(p))
        MS.check_write(str(game.staging / "mod" / "x.esp"))                   # staging is fine


def test_only_init_is_exempt(game):
    """tidy --init (MWManager: the core install, never staged) may act on Data Files; nothing else may."""
    for target in _aliases(game):
        assert MS.write_root_problem(target, str(game.dir), str(game.data), mode=MS.INIT_MODE) == ""
        assert MS.require_write_root(target, str(game.dir), str(game.data), mode="init")
        for mode in ("tidy", "converter", "luafix", "Init", "init ", "--init", "data-files", ""):
            assert MS.write_root_problem(target, str(game.dir), str(game.data), mode=mode), (target, mode)
    core = game.data / "MWSE" / "core" / "x.lua"
    assert MS.write_root_problem(core, str(game.dir), str(game.data), mode=MS.CORE_MODE) == ""
    assert MS.write_root_problem(game.data, str(game.dir), str(game.data), mode=MS.CORE_MODE)
    assert MS.write_root_problem(game.data / "MWSE" / "mods" / "x.lua", str(game.dir), str(game.data), mode=MS.CORE_MODE)


@pytest.mark.parametrize("which", ["data", "game", "data_alias", "game_alias", "data_upper"])
@pytest.mark.parametrize("extra", [(), ("--apply", "--yes")])
def test_tidy_refuses_data_files_or_the_game_as_staging(game, watch, monkeypatch, capsys, which, extra):
    put(game.data / "SomeMod" / "readme.txt", "a mod folder in Data Files\n")
    target = {"data": game.data, "game": game.dir, "data_upper": Path(str(game.data).upper()),
              "data_alias": lambda: _junction(game.tmp / "dataalias", game.data),
              "game_alias": lambda: _junction(game.tmp / "gamealias", game.dir)}[which]
    target = target() if callable(target) else target
    before = snapshot(game.dir)
    g = watch(game.data)
    assert run_tidy(monkeypatch, target, *extra) == 2
    err = fold(capsys.readouterr().err)
    assert "Not tidying" in err and "staging folder before deploy" in err
    assert g.writes == []
    assert snapshot(game.dir) == before
    assert not os.path.exists(vt.PLAN)


def test_tidy_undo_refuses_a_journal_that_points_into_data_files(game, watch, monkeypatch, capsys):
    with open(vt.JOURNAL, "w", encoding="utf-8") as f:
        f.write(json.dumps({"run": "x", "staging": str(game.data)}) + "\n")
    monkeypatch.setattr(vt, "_journal_stagings", lambda: [str(game.data)])
    before = snapshot(game.dir)
    g = watch(game.data)
    assert run_tidy(monkeypatch, game.staging, "--undo") == 2
    assert "Not tidying" in fold(capsys.readouterr().err)
    assert g.writes == [] and snapshot(game.dir) == before


@pytest.mark.parametrize("which", ["data_mod", "game", "alias_mod"])
def test_converter_handoff_refuses_data_files_the_game_and_aliases(game, monkeypatch, which):
    mod = game.data / "OmwMod"
    put(mod / "OmwMod.omwscripts", "PLAYER: scripts/x.lua\n")
    target = {"data_mod": mod, "game": game.dir,
              "alias_mod": lambda: _junction(game.tmp / "dataalias", game.data) / "OmwMod"}[which]
    target = target() if callable(target) else target
    calls = []
    monkeypatch.setattr(vt.subprocess, "run", lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError))
    monkeypatch.setitem(vt.CONVERTER, "cmd", ["omw2mwse"])
    code, data, err = vt.run_converter(str(target), "normal", dry_run=True)
    assert code is None and "not handed to omw2mwse" in err
    assert calls == []
    assert vt.converter_target_problem(str(game.staging / "OmwMod")) == ""


def test_luafix_refuses_data_files_as_staging(game, watch, capsys):
    alias = _junction(game.tmp / "dataalias", game.data)
    before = snapshot(game.data)
    g = watch(game.data)
    for target in (game.data, alias, game.dir):
        assert run_luafix("--staging", str(target)) == 2
        assert "it is in Data Files" in fold(capsys.readouterr().err)
    assert g.writes == [] and snapshot(game.data) == before


# ------------------------------------------------------------------------------------------------ --data-files
@pytest.mark.parametrize("opt", ["--data-files", "--init", "--game-data-files"])
def test_tidy_has_no_data_files_or_init_mode(game, monkeypatch, opt):
    """--data-files / --init are MWManager's wrapper modes (mwmanager_tidy_ext), not this CLI's: here they are
    rejected by argparse before anything runs, so this tidy can never sort documents into Data Files\\Docs."""
    monkeypatch.setattr(vt.sys, "argv", ["vortex_tidy.py", opt, str(game.data)])
    with pytest.raises(SystemExit) as e:
        vt.main()
    assert e.value.code == 2
    assert not (game.data / "Docs").exists()


def test_tidy_documents_go_to_the_staged_mods_docs_never_data_files_docs(game, watch, monkeypatch):
    mod = assets_mod(game.staging)
    deploy_links(game.staging, game.data)
    g = watch(game.data)
    assert run_tidy(monkeypatch, game.staging) == 0
    assert run_tidy(monkeypatch, game.staging, "--apply", "--yes") == 0
    assert (mod / "Docs" / "Signs - readme.txt").exists()
    assert not (game.data / "Docs").exists()
    assert g.writes == []


# ------------------------------------------------------------------------------------------------ after MWSE-Update
@pytest.mark.parametrize("rc,before,after,outcome", [
    (0, "aaa111", "bbb222", "updated"),
    (0, "", "bbb222", "updated"),                  # a fresh install
    (1, "aaa111", "bbb222", "failed"),
    (-1, "aaa111", "aaa111", "failed"),
    (None, "aaa111", "aaa111", "failed"),          # did not start
    (0, "aaa111", "", "failed"),                   # exit 0 but no marker: nothing proves the update
    (0, "aaa111", "aaa111", "no-update"),
    (0, "aaa111\n", " aaa111 ", "no-update"),
])
def test_mwse_update_outcome(rc, before, after, outcome):
    assert vt.mwse_update_outcome(rc, before, after)[0] == outcome


@pytest.mark.parametrize("rc,before,after,runs", [
    (0, "aaa111", "bbb222", True),                 # success: core is re-patched
    (3, "aaa111", "bbb222", False),                # failure: skipped
    (0, "aaa111", "aaa111", False),                # no update: skipped
])
def test_tidy_after_mwse_update_runs_only_after_a_successful_update(game, monkeypatch, rc, before, after, runs):
    _prep_core(game, monkeypatch)
    put(game.dir / "mwse-version.txt", after)
    calls = []
    monkeypatch.setattr(vt, "plan_main", lambda *a, **k: calls.append("plan") or 0)
    monkeypatch.setattr(vt, "apply_main", lambda *a, **k: calls.append("apply") or 0)
    monkeypatch.setattr(vt, "run_converter", lambda *a, **k: calls.append("converter") or (None, None, "no"))
    logs = []
    outcome, reason, result = vt.tidy_after_mwse_update(rc, before, str(game.dir), log=logs.append)
    assert calls == []                                         # no other tidy function
    if runs:
        assert outcome == "updated" and result == 0
        assert "luafix --core-only" in logs[0]
        assert b"localpatch" in (game.data / "MWSE" / "core" / "mcm" / "components" / "pages" /
                                 "ExclusionsPage.lua").read_bytes()
    else:
        assert result is None and "skipped" in logs[0]
        assert (game.data / "MWSE" / "core" / "mcm" / "components" / "pages" /
                "ExclusionsPage.lua").read_bytes() == _stock_core()


def test_cli_after_mwse_update_patches_core_only(game, watch, monkeypatch, capsys):
    _prep_core(game, monkeypatch)
    put(game.dir / "mwse-version.txt", "bbb222")
    calls = []
    monkeypatch.setattr(vt, "plan_main", lambda *a, **k: calls.append("plan") or 0)
    monkeypatch.setattr(vt, "apply_main", lambda *a, **k: calls.append("apply") or 0)
    monkeypatch.setattr(vt, "run_converter", lambda *a, **k: calls.append("converter") or (None, None, "no"))
    core = game.data / "MWSE" / "core" / "mcm" / "components" / "pages" / "ExclusionsPage.lua"
    before = snapshot(game.data)
    g = watch(game.data)
    assert run_tidy(monkeypatch, game.staging, "--after-mwse-update", "0", "--mwse-version-before", "aaa111") == 0
    assert calls == []
    assert b"localpatch" in core.read_bytes()
    # the only Data Files write is the core file itself (the documented exemption)
    rels = []
    for p in g.writes:
        p = p.split(" (written", 1)[0]
        rels.append(os.path.normcase(os.path.relpath(p, game.data)))
    assert rels and all(r.startswith(os.path.normcase(os.path.join("MWSE", "core")) + os.sep) for r in rels)
    # everything else in Data Files (plugin, loose texture, mwguard.json) is unchanged
    after = snapshot(game.data)
    for rel, val in before.items():
        if "exclusionspage.lua" in rel.lower():
            assert after[rel] != val
        else:
            assert after[rel] == val


@pytest.mark.parametrize("rc,after", [(1, "bbb222"), (0, "aaa111")])
def test_cli_after_mwse_update_skips_on_failure_or_no_update(game, watch, monkeypatch, rc, after):
    _prep_core(game, monkeypatch)
    put(game.dir / "mwse-version.txt", after)
    calls = []
    monkeypatch.setattr(vt, "plan_main", lambda *a, **k: calls.append("plan") or 0)
    core = game.data / "MWSE" / "core" / "mcm" / "components" / "pages" / "ExclusionsPage.lua"
    stock = core.read_bytes()
    g = watch(game.data)
    assert run_tidy(monkeypatch, game.staging, "--after-mwse-update", str(rc), "--mwse-version-before", "aaa111") == 0
    assert calls == [] and core.read_bytes() == stock and g.writes == []


def test_after_mwse_update_refuses_when_morrowind_is_running(game, watch, monkeypatch):
    _prep_core(game, monkeypatch)
    put(game.dir / "mwse-version.txt", "bbb222")
    monkeypatch.setattr(vt, "morrowind_process_running", lambda: True)
    calls = []
    monkeypatch.setattr(vt, "plan_main", lambda *a, **k: calls.append("plan") or 0)
    monkeypatch.setattr(lf, "apply_core_known_bugs", lambda *a, **k: calls.append("core") or [])
    core = game.data / "MWSE" / "core" / "mcm" / "components" / "pages" / "ExclusionsPage.lua"
    stock = core.read_bytes()
    g = watch(game.data)
    assert run_tidy(monkeypatch, game.staging, "--after-mwse-update", "0", "--mwse-version-before", "aaa111") == 2
    assert calls == [] and core.read_bytes() == stock and g.writes == []


def test_after_mwse_update_morrowind_running_message(game, monkeypatch, capsys):
    _prep_core(game, monkeypatch)
    put(game.dir / "mwse-version.txt", "bbb222")
    monkeypatch.setattr(vt, "morrowind_process_running", lambda: True)
    rc = run_tidy(monkeypatch, game.staging, "--after-mwse-update", "0", "--mwse-version-before", "aaa111")
    assert rc == 2
    text = fold(capsys.readouterr().out + capsys.readouterr().err)
    assert "Morrowind.exe is running" in text and "Nothing was killed" in text


def test_after_mwse_update_is_idempotent_on_a_second_run(game, monkeypatch):
    _prep_core(game, monkeypatch)
    put(game.dir / "mwse-version.txt", "bbb222")
    assert vt.tidy_after_mwse_update(0, "aaa111", str(game.dir), log=lambda *a: None)[2] == 0
    core = game.data / "MWSE" / "core" / "mcm" / "components" / "pages" / "ExclusionsPage.lua"
    patched = core.read_bytes()
    assert b"localpatch" in patched
    # a second successful-update call (same new marker) dry-runs, sees already-patched, writes nothing
    mtime = core.stat().st_mtime_ns
    outcome, reason, rc = vt.tidy_after_mwse_update(0, "aaa111", str(game.dir), log=lambda *a: None)
    assert outcome == "updated" and rc == 0
    assert core.read_bytes() == patched and core.stat().st_mtime_ns == mtime


def test_allow_core_writes_is_limited_to_mwse_core(game):
    core = game.data / "MWSE" / "core" / "x.lua"
    other = game.data / "Loose.esp"
    mods = game.data / "MWSE" / "mods" / "x.lua"
    with MS.staged_run(str(game.staging), str(game.dir)):
        with pytest.raises(MS.DataFilesWriteError):
            MS.check_write(str(core))
        with MS.allow_core_writes():
            MS.check_write(str(core))
            with pytest.raises(MS.DataFilesWriteError):
                MS.check_write(str(other))
            with pytest.raises(MS.DataFilesWriteError):
                MS.check_write(str(mods))
        with pytest.raises(MS.DataFilesWriteError):
            MS.check_write(str(core))


def _stock_core():
    with open(os.path.join(os.path.dirname(__file__), "fixtures", "mwse", "ExclusionsPage.lua"), "rb") as f:
        return f.read().replace(b"\r\n", b"\n")


class _OkChecker:
    name = "fake"

    def check(self, text):
        return True, ""


def _prep_core(game, monkeypatch):
    """Stock unpatched ExclusionsPage.lua, a fake syntax checker, no Morrowind, and free locks."""
    put(game.data / "MWSE" / "core" / "mcm" / "components" / "pages" / "ExclusionsPage.lua", _stock_core())
    monkeypatch.setattr(vt, "morrowind_process_running", lambda: False)
    monkeypatch.setattr(lf, "find_checker", lambda *a, **k: _OkChecker())
    monkeypatch.setattr(vt.MP, "acquire_run_lock", lambda: True)
    monkeypatch.setattr(vt.MP, "acquire_game_lock", lambda *a, **k: True)
