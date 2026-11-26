r"""The one Off layout, Off\<plugin>\<reason>\<path>: the fixed reasons, the owner (<plugin>) rule, the migration of
every older layout (loose files, Off\<reason>\<plugin>\, Off\OpenMW\<mod>\, Off\<path>), idempotence, collisions,
--undo byte for byte, omw2mwse output left alone, and the MAX_PATH list (max_path_too_long.txt). Temporary folders
only; tidy never runs on live data. Python 3.9+."""
import json
import os
import sys
from pathlib import Path

import pytest

from conftest import _load, vt

OL = _load("mwdialog_offlayout")
LONG = "max_path_too_long.txt"


@pytest.fixture
def env(tmp_path, monkeypatch):
    staging = tmp_path / "staging"
    mod = staging / "Foo-1-1-0"
    mod.mkdir(parents=True)
    (mod / "Foo.esp").write_bytes(b"TES3")
    monkeypatch.setattr(vt, "JOURNAL", str(tmp_path / "journal.jsonl"))
    monkeypatch.setattr(vt, "PLAN", str(tmp_path / "vortex_tidy_plan.txt"))
    monkeypatch.setattr(vt, "BLACKLIST_FILE", str(tmp_path / "bl.txt"))
    monkeypatch.setattr(vt, "HERE", str(tmp_path))

    def run(*extra):
        vt.NOTES.clear()
        monkeypatch.setattr(sys, "argv", ["vortex_tidy.py", "--staging", str(staging), "--no-lua", "--no-assets",
                                          *extra])
        return vt.main()
    run.mod, run.tmp, run.staging = mod, tmp_path, staging
    return run


def put(mod, rel, data=b"x"):
    p = mod.joinpath(*rel.replace("/", os.sep).split(os.sep))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def snap(root):
    files = {}
    dirs = set()
    for base, ds, fns in os.walk(str(root)):
        for d in ds:
            dirs.add(os.path.relpath(os.path.join(base, d), str(root)))
        for f in fns:
            p = os.path.join(base, f)
            with open(p, "rb") as fh:
                files[os.path.relpath(p, str(root))] = fh.read()
    return files, dirs


def off_files(mod):
    return sorted("Off/" + p.replace(os.sep, "/") for p in snap(mod / "Off")[0])


def plan(env):
    assert env() == 0
    return open(vt.PLAN).read()


# ------------------------------------------------------------------------------------------------ the fixed list
def test_every_reason_has_a_meaning_and_every_older_spelling_maps_to_one():
    names = [n for n, _m in OL.REASONS]
    assert len(set(n.lower() for n in names)) == len(names) and all(m.strip() for _n, m in OL.REASONS)
    assert set(OL.LEGACY.values()) <= set(names)
    assert OL.reason_for("Names") == "ascii" and OL.reason_for("LONGPATHS") == "shortened paths"
    assert OL.reason_for("texture-reduction") == "reduced textures"
    assert OL.reason_for("openmw") == "OpenMW" and OL.reason_for("Damaged assets") == "broken"
    with pytest.raises(ValueError):
        OL.reason_for("whatever")


def test_the_spec_lists_every_reason_and_the_max_path_list():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = os.path.join(here, "docs", "OFF-LAYOUT.md")
    if not os.path.isfile(spec):
        pytest.skip("docs/ is not vendored here")                    # MWManager's copy of the tests has no docs folder
    with open(spec, encoding="utf-8") as f:
        text = f.read()
    for name, meaning in OL.REASONS:
        assert "`%s`" % name in text and meaning.split(";")[0][:20] in text
    assert "Off\\<plugin>\\" + LONG in text


# ------------------------------------------------------------------------------------------------ the owner rule
def test_owner_is_the_first_root_plugin_else_omwscripts_else_off_plugin_else_hint_else_mod_name(tmp_path):
    a = tmp_path / "A"
    put(a, "zeta.esp")
    put(a, "Alpha Beta.esm")
    put(a, "x.omwscripts")
    assert OL.owner_name(str(a)) == "AlphaBeta"                       # first plugin (sorted), sanitised
    b = tmp_path / "B"
    put(b, "My Mod.omwscripts")
    assert OL.owner_name(str(b)) == "MyMod"                           # the converter's mod_name_for
    c = tmp_path / "C"
    put(c, "Off/Old Thing.esp")
    assert OL.owner_name(str(c)) == "OldThing"
    d = tmp_path / "D"
    d.mkdir()
    assert OL.owner_name(str(d), hint="Hinted.esp") == "Hinted"
    assert OL.owner_name(str(d), fallback="My Mod-1-0") == "MyMod-1-0"
    assert OL.owner_name(str(tmp_path / "E!!")) == "E"
    assert OL.owner_name(str(tmp_path / "!!")) == "OpenMWMod"


def test_an_owner_folder_already_in_the_layout_is_kept(tmp_path):
    a = tmp_path / "A"
    put(a, "Foo.esp")
    put(a, "Off/Shown Name/broken/Meshes/x.nif")
    assert OL.owner_name(str(a)) == "Shown Name"                      # the one folder in the layout is the owner
    put(a, "Off/Other/broken/Meshes/y.nif")
    assert OL.owner_name(str(a)) == "Foo"                             # two: the computed one


# ------------------------------------------------------------------------------------------------ the migration
LEGACY_TREE = {
    "Off/Foo.esp": b"loose plugin", "Off/Foo.bsa": b"loose bsa", "Off/tool.exe": b"exe", "Off/main.omwscripts": b"os",
    "Off/normal maps/Foo/textures/a_n.dds": b"n",
    "Off/Damaged assets/Foo/Meshes/b.nif": b"bad",
    "Off/names/Foo/Textures/ä.dds": b"nm",
    "Off/longpaths/Foo/Meshes/c.nif": b"lp",
    "Off/sound/Foo/Sound/s.wav": b"sw",
    "Off/Reprocessed textures/Foo/Textures/t.dds": b"tx",
    "Off/Unused assets/Foo/Textures/u.dds": b"un",
    "Off/OpenMW/Foo-1-1-0/scripts/a.lua": b"lua",
    "Off/OpenMW/Foo-1-1-0/Foo.omwaddon": b"add",
    "Off/Meshes/orig.nif": b"orig1",
    "Off/Foo/Meshes/orig2.nif": b"orig2",
    "Off/Foo/unused/Textures/v.dds": b"v",
    "Off/Foo/Foo2.esp": b"in plugin folder",
    "MWSE/mods/foo/main.lua": b"mwse lua",                 # real MWSE Lua: the OpenMW scripts are a hybrid's, not a package
}
EXPECT = {
    "Off/Foo/disabled plugins/Foo.esp", "Off/Foo/disabled plugins/Foo.bsa", "Off/Foo/executables/tool.exe",
    "Off/Foo/OpenMW/main.omwscripts", "Off/Foo/normal maps/textures/a_n.dds",
    "Off/Foo/broken/Meshes/b.nif", "Off/Foo/ascii/Textures/\u00e4.dds", "Off/Foo/shortened paths/Meshes/c.nif",
    "Off/Foo/converted sounds/Sound/s.wav", "Off/Foo/converted textures/Textures/t.dds",
    "Off/Foo/unused assets/Textures/u.dds", "Off/Foo/OpenMW/scripts/a.lua", "Off/Foo/OpenMW/Foo.omwaddon",
    "Off/Foo/repaired originals/Meshes/orig.nif", "Off/Foo/repaired originals/Meshes/orig2.nif",
    "Off/Foo/unused assets/Textures/v.dds", "Off/Foo/disabled plugins/Foo2.esp",
}


def build(env, tree):
    for rel, data in tree.items():
        put(env.mod, rel, data)


def test_every_older_layout_is_migrated_into_off_plugin_reason(env):
    build(env, LEGACY_TREE)
    text = plan(env)
    assert env("--apply", "--yes") == 0
    got = set(off_files(env.mod))
    assert got == EXPECT, (sorted(got ^ EXPECT), text)
    assert not [d for d in os.listdir(env.mod / "Off") if d != "Foo"]            # nothing left beside the owner


def test_migration_is_idempotent(env):
    build(env, LEGACY_TREE)
    env()
    env("--apply", "--yes")
    after = snap(env.mod)
    assert env() == 0
    assert "move(s)" in open(vt.PLAN).read() and "0 to change" in open(vt.PLAN).read()
    assert snap(env.mod) == after


def test_undo_puts_every_older_layout_back_byte_for_byte(env):
    build(env, LEGACY_TREE)
    before = snap(env.mod)
    env()
    env("--apply", "--yes")
    assert snap(env.mod) != before
    assert vt.undo() == 0
    assert snap(env.mod) == before


def test_a_name_taken_in_the_new_place_gets_a_number_and_nothing_is_overwritten(env):
    put(env.mod, "Off/Foo/broken/Meshes/b.nif", b"already there")
    put(env.mod, "Off/Damaged assets/Foo/Meshes/b.nif", b"older")
    env()
    env("--apply", "--yes")
    got = snap(env.mod / "Off" / "Foo" / "broken" / "Meshes")[0]
    assert got == {"b.nif": b"already there", "b (2).nif": b"older"}
    assert vt.undo() == 0
    assert (env.mod / "Off" / "Damaged assets" / "Foo" / "Meshes" / "b.nif").read_bytes() == b"older"


def test_the_hybrid_move_goes_to_off_plugin_openmw(env):
    put(env.mod, "MWSE/mods/foo/main.lua", b"mwse")
    put(env.mod, "scripts/a.lua", b"lua")
    put(env.mod, "Foo.omwscripts", b"s")
    put(env.mod, "Meshes/m.nif", b"m")
    env()
    env("--apply", "--yes")
    got = off_files(env.mod)
    assert got and all(g.startswith("Off/Foo/OpenMW/") for g in got), got


def test_a_folder_already_in_the_layout_is_not_touched_under_any_name(env):
    put(env.mod, "Off/Shown Name/broken/Meshes/b.nif", b"b")
    before = snap(env.mod)
    env()
    assert "0 to change" in open(vt.PLAN).read()
    env("--apply", "--yes")
    assert snap(env.mod) == before


def test_what_is_not_recognised_is_left_alone_with_one_note(env):
    put(env.mod, "Off/readme.txt", b"hello")
    put(env.mod, "Off/Foo/weird/thing.dat", b"?")
    put(env.mod, "Off/Foo/OtherStuff/more.dat", b"?")
    before = snap(env.mod)
    text = plan(env)
    assert text.count("left where they are") == 1 and "NOTE" in text
    env("--apply", "--yes")
    assert snap(env.mod) == before


def test_converter_output_in_an_omw2mwse_manifest_is_never_moved(env):
    man = "MWSE/mods/mwsuite/openmw/Foo/omw2mwse-manifest.json"
    put(env.mod, man, json.dumps({"files": {"Off/OpenMW/Foo/scripts/a.lua": "h",
                                            "Extras/Foo/Foo.esp": "h"},
                                  "plugins": [{"path": "Off/OpenMW/Foo/Foo.omwaddon"}]}).encode())
    put(env.mod, "Off/OpenMW/Foo/scripts/a.lua", b"lua")
    put(env.mod, "Off/OpenMW/Foo/Foo.omwaddon", b"add")
    put(env.mod, "Off/Foo/OpenMW/scripts/a.lua", b"lua")             # the converter's own (canonical) copy
    put(env.mod, "Off/old.dll", b"dll")                              # tidy's own leftover is still tidied
    before = snap(env.mod)
    env()
    env("--apply", "--yes")
    after = snap(env.mod)[0]
    assert after["Off\\OpenMW\\Foo\\scripts\\a.lua".replace("\\", os.sep)] == b"lua"
    assert after[os.path.join("Off", "OpenMW", "Foo", "Foo.omwaddon")] == b"add"
    assert os.path.join("Off", "Foo", "executables", "old.dll") in after
    assert vt.undo() == 0
    assert snap(env.mod) == before


# ------------------------------------------------------------------------------------------------ MAX_PATH
def _limit(monkeypatch, mod, extra):
    monkeypatch.setattr(OL, "MAX_PATH_CHARS", len(str(mod)) + extra)


def test_a_file_whose_path_is_too_long_is_not_moved_and_is_listed(env, monkeypatch):
    short = put(env.mod, "Off/Damaged assets/Foo/Meshes/ok.nif", b"ok")
    long_rel = "Off/Damaged assets/Foo/Meshes/" + "a" * 60 + ".nif"
    put(env.mod, long_rel, b"long")
    _limit(monkeypatch, env.mod, 50)
    text = plan(env)
    assert LONG in text and "not moved" in text
    env("--apply", "--yes")
    listed = (env.mod / "Off" / "Foo" / LONG).read_text(encoding="utf-8").splitlines()
    assert listed == [long_rel.replace("/", "\\")]                     # relative to the staged mod folder
    assert (env.mod / long_rel.replace("/", os.sep)).read_bytes() == b"long"      # still where it was
    assert not short.exists() and (env.mod / "Off" / "Foo" / "broken" / "Meshes" / "ok.nif").exists()


def test_a_move_whose_new_path_would_be_too_long_is_left_and_listed(env, monkeypatch):
    rel = "Off/longpaths/Foo/Meshes/" + "b" * 20 + ".nif"
    put(env.mod, rel, b"n")
    _limit(monkeypatch, env.mod, len(rel) + 2)                         # fine where it is; "<plugin>\shortened paths\" tips it over
    env()
    env("--apply", "--yes")
    assert (env.mod / rel.replace("/", os.sep)).exists()
    assert (env.mod / "Off" / "Foo" / LONG).read_text(encoding="utf-8").strip() == rel.replace("/", "\\")


def test_the_list_is_deduped_refreshed_and_idempotent(env, monkeypatch):
    for n in ("one", "two"):
        put(env.mod, "Off/Damaged assets/Foo/Meshes/%s%s.nif" % (n, "z" * 60), b"1")
    _limit(monkeypatch, env.mod, 50)
    env()
    env("--apply", "--yes")
    lst = env.mod / "Off" / "Foo" / LONG
    first = lst.read_bytes()
    lines = first.decode("utf-8").splitlines()
    assert len(lines) == 2 and len(set(lines)) == 2
    env()
    assert "0 to change" in open(vt.PLAN).read()                         # nothing to write: same text
    env("--apply", "--yes")
    assert lst.read_bytes() == first
    os.remove(str(env.mod / "Off" / "Damaged assets" / "Foo" / "Meshes" / ("one" + "z" * 60 + ".nif")))
    env()
    env("--apply", "--yes")
    assert len(lst.read_text(encoding="utf-8").splitlines()) == 1        # refreshed: the gone one is dropped
    monkeypatch.setattr(OL, "MAX_PATH_CHARS", 259)                       # nothing is too long any more
    env()
    env("--apply", "--yes")
    assert not lst.exists()                                              # the list goes when it is empty


def test_undo_removes_the_list_it_made_and_restores_the_one_it_changed(env, monkeypatch):
    put(env.mod, "Off/Damaged assets/Foo/Meshes/" + "a" * 60 + ".nif", b"1")
    _limit(monkeypatch, env.mod, 50)
    before = snap(env.mod)
    env()
    env("--apply", "--yes")
    lst = env.mod / "Off" / "Foo" / LONG
    assert lst.exists()
    assert vt.undo() == 0
    assert not lst.exists() and snap(env.mod) == before
    lst.parent.mkdir(parents=True)
    lst.write_bytes(b"Meshes\\stale.nif\r\n")                                  # an older list, no longer true
    env()
    env("--apply", "--yes")
    assert lst.read_bytes() != b"Meshes\\stale.nif\r\n" and lst.exists() is True
    assert vt.undo() == 0
    assert lst.read_bytes() == b"Meshes\\stale.nif\r\n"


def test_a_stale_list_is_not_rewritten_over_a_changed_file_on_undo_without_force(env, monkeypatch):
    put(env.mod, "Off/Damaged assets/Foo/Meshes/" + "a" * 60 + ".nif", b"1")
    _limit(monkeypatch, env.mod, 50)
    env()
    env("--apply", "--yes")
    lst = env.mod / "Off" / "Foo" / LONG
    lst.write_bytes(b"edited by hand\r\n")
    assert vt.undo() != 0 and lst.exists()


def test_an_openmw_only_package_set_aside_the_old_way_ends_in_off_plugin_openmw_and_stays_there(env):
    os.remove(str(env.mod / "Foo.esp"))
    put(env.mod, "Foo.omwscripts", b"s")
    put(env.mod, "scripts/a.lua", b"lua")
    put(env.mod, "Off/OpenMW/Foo-1-1-0/scripts/old.lua", b"old")
    before = snap(env.mod)
    env()
    env("--apply", "--yes")
    got = off_files(env.mod)
    assert got and all(g.startswith("Off/Foo/OpenMW/") for g in got) and "Off/Foo/OpenMW/scripts/old.lua" in got, got
    again = snap(env.mod)
    env()
    env("--apply", "--yes")
    assert snap(env.mod) == again
    assert vt.undo() == 0 and snap(env.mod) == before


def test_the_shared_module_is_python_39_syntax():
    import ast
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("mwdialog_offlayout.py", "vortex_tidy.py", "mwdialog_generated.py"):
        with open(os.path.join(here, name), encoding="utf-8") as f:
            ast.parse(f.read(), feature_version=(3, 9))


def test_off_copy_maps_legacy_and_live_paths_into_the_layout(tmp_path):
    mod = tmp_path / "Foo-1-0"
    put(mod, "Foo.esp")
    put(mod, "Meshes/x.nif")
    put(mod, "Off/Damaged assets/Foo/Meshes/b.nif")
    owner = "Foo"
    live = OL.off_copy(str(mod), "Meshes\\x.nif", owner)
    assert live.replace("/", os.sep).endswith(os.path.join("Off", "Foo", "OpenMW", "Meshes", "x.nif"))
    legacy = OL.off_copy(str(mod), "Off\\Damaged assets\\Foo\\Meshes\\b.nif", owner)
    assert legacy.replace("/", os.sep).endswith(os.path.join("Off", "Foo", "broken", "Meshes", "b.nif"))
    already = OL.off_copy(str(mod), "Off\\Foo\\OpenMW\\scripts\\a.lua", owner)
    assert already.replace("/", os.sep).endswith(os.path.join("Off", "Foo", "OpenMW", "scripts", "a.lua"))


def test_a_short_source_whose_off_copy_would_be_too_long_stays_listed_on_refresh(env, monkeypatch):
    """A file the converter listed (source short; Off\\<plugin>\\OpenMW\\<rel> would exceed MAX_PATH)
    must stay listed when tidy refreshes and is not itself moving the file."""
    rel = "Meshes/" + "b" * 20 + ".nif"
    put(env.mod, rel, b"n")
    _limit(monkeypatch, env.mod, len(rel.replace("/", "\\")) + 2)   # source fits; Off\\Foo\\OpenMW\\... does not
    dest = OL.off_copy(str(env.mod), rel, "Foo")
    assert not OL.too_long(str(env.mod / rel.replace("/", os.sep))) and OL.too_long(dest)
    lst = env.mod / "Off" / "Foo" / LONG
    lst.parent.mkdir(parents=True)
    text = OL.list_text([rel])
    lst.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    assert env() == 0
    assert "0 to change" in open(vt.PLAN).read()                         # refresh is a no-op: same list
    assert lst.read_text(encoding="utf-8").replace("\r\n", "\n") == text
    assert (env.mod / rel.replace("/", os.sep)).exists()


def test_list_update_keeps_a_short_source_whose_off_copy_is_too_long(tmp_path, monkeypatch):
    mod = tmp_path / "Foo-1-0"
    rel = "Meshes/" + "c" * 20 + ".nif"
    put(mod, "Foo.esp")
    put(mod, rel, b"n")
    monkeypatch.setattr(OL, "MAX_PATH_CHARS", len(str(mod)) + len(rel.replace("/", "\\")) + 2)
    owner = "Foo"
    lst_path = OL.list_path(str(mod), owner)
    lst = Path(lst_path)
    lst.parent.mkdir(parents=True)
    lst.write_bytes(OL.list_text([rel]).replace("\n", "\r\n").encode("utf-8"))
    assert OL.list_update(str(mod), owner, []) is None                    # same text: no rewrite
    gone = "Meshes/gone.nif"
    lst.write_bytes(OL.list_text([rel, gone]).replace("\n", "\r\n").encode("utf-8"))
    out = OL.list_update(str(mod), owner, [])
    assert out and out[1] == OL.list_text([rel])                          # the missing one is dropped; the short+too-long Off copy stays
    monkeypatch.setattr(OL, "MAX_PATH_CHARS", 259)
    out = OL.list_update(str(mod), owner, [])
    assert out == (str(lst), None)                                        # nothing is too long any more: the list goes
