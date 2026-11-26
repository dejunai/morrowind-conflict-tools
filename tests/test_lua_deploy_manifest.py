"""--play's lua tools deploy record (manifest): what it deployed, per mod with SHA-256; files of mods taken out
of lua tools removed with a backup and a journal (and put back by --undo-lua-prune); the retired-suite-mod
bootstrap; config ownership (what a module writes, or ownmods.json declares); mods outside mwsuite (a made-up
"SomeMod" here: no such folder ships in lua tools). Temporary folders only."""
import hashlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mwdialog_backup                           # noqa: E402
import mwdialog_paths as P                       # noqa: E402


@pytest.fixture(autouse=True)
def _own_backups(monkeypatch):
    monkeypatch.setattr(mwdialog_backup, "ROOT", None)


def w(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def suite_mod(src, leaf, extra=""):
    w(src / "MWSE" / "mods" / "mwsuite" / leaf / "main.lua",
      f'local CONFIG_NAME = "{leaf}"\nlocal config = mwse.loadConfig(CONFIG_NAME, {{}})\n'
      f'local other = mwse.loadConfig("Easy Escort")\nmwse.saveConfig("{leaf}_extra", {{}})\n'
      f'local function save() mwse.saveConfig(CONFIG_NAME, config) end\n{extra}')
    w(src / "MWSE" / "mods" / "mwsuite" / leaf / "mcm.lua", f"-- {leaf} mcm\n")
    w(src / f"{leaf}-metadata.toml", f'[package]\nname = "{leaf}"\n')


def setup(tmp_path):
    src = tmp_path / "lua tools"
    game = tmp_path / "game"
    data = game / "Data Files"
    data.mkdir(parents=True)
    w(src / "MWSE" / "mods" / "mwsuite" / "main.lua", "-- suite root\n")
    w(src / "mwsuite-metadata.toml", "[package]\n")
    suite_mod(src, "alpha")
    suite_mod(src, "beta")
    w(src / "MWSE" / "config" / "beta.json", '{"shipped": true}')
    return src, game, data


def deploy(src, data):
    return P.deploy_lua_tools(str(data), str(src))


def manifest(game):
    return json.loads((game / P.LUA_MANIFEST).read_text(encoding="utf-8"))


def rm_mod(src, leaf):
    import shutil
    shutil.rmtree(src / "MWSE" / "mods" / "mwsuite" / leaf)
    (src / f"{leaf}-metadata.toml").unlink()
    cfg = src / "MWSE" / "config" / f"{leaf}.json"
    if cfg.exists():
        cfg.unlink()


def test_lua_mod_of_groups_files_by_mod():
    leaves, tops = ["mwconsole"], ["SomeMod"]
    assert P.lua_mod_of(os.path.join("MWSE", "mods", "mwsuite", "mwconsole", "a", "b.lua"), leaves, tops) == \
        ("mwsuite/mwconsole", True)
    assert P.lua_mod_of(os.path.join("MWSE", "mods", "mwsuite", "main.lua"), leaves, tops) == ("mwsuite", True)
    assert P.lua_mod_of("MWConsole-metadata.toml", leaves, tops) == ("mwsuite/mwconsole", True)
    assert P.lua_mod_of(os.path.join("MWSE", "config", "mwconsole.json"), leaves, tops) == ("mwsuite/mwconsole", True)
    assert P.lua_mod_of(os.path.join("MWSE", "mods", "SomeMod", "interop.lua"), leaves, tops) == ("SomeMod", False)
    assert P.lua_mod_of("SomeMod-metadata.toml", leaves, tops) == ("SomeMod", False)
    assert P.lua_mod_of("mwsuite-metadata.toml", leaves, tops) == ("mwsuite", True)


def test_manifest_records_what_play_deployed(tmp_path):
    src, game, data = setup(tmp_path)
    res = deploy(src, data)
    assert len(res["copied"]) == 9 and res["pruned"] == [] and res["manifest_error"] is None
    assert res["manifest"] == str(game / P.LUA_MANIFEST)
    assert not any(p.name == P.LUA_MANIFEST for p in data.rglob("*"))      # nothing of ours in Data Files
    man = manifest(game)
    assert man["schema"] == P.LUA_MANIFEST_SCHEMA and man["version"] == 1
    assert set(man["mods"]) == {"mwsuite", "mwsuite/alpha", "mwsuite/beta"}
    beta = man["mods"]["mwsuite/beta"]
    assert beta["suite"] is True
    assert beta["configs"] == ["beta", "beta_extra"]                       # not another mod's "Easy Escort"
    assert set(beta["files"]) == {"MWSE/mods/mwsuite/beta/main.lua", "MWSE/mods/mwsuite/beta/mcm.lua",
                                  "beta-metadata.toml", "MWSE/config/beta.json"}
    assert beta["files"]["MWSE/config/beta.json"]["config"] is True
    for mrel, ent in beta["files"].items():
        assert ent["sha256"] == sha(src.joinpath(*mrel.split("/")))
    assert "retired_done" in man and "mweffectinspector" in man["retired_done"]


def test_removed_mod_is_pruned_with_its_toml_and_configs(tmp_path):
    src, game, data = setup(tmp_path)
    deploy(src, data)
    w(data / "MWSE" / "config" / "beta_extra.json", '{"written by": "the game"}')
    w(data / "MWSE" / "config" / "beta.json", '{"my": "settings"}')            # the player changed them
    rm_mod(src, "beta")
    res = deploy(src, data)
    gone = {p["rel"] for p in res["pruned"]}
    assert gone == {os.path.join("MWSE", "mods", "mwsuite", "beta", "main.lua"),
                    os.path.join("MWSE", "mods", "mwsuite", "beta", "mcm.lua"), "beta-metadata.toml",
                    os.path.join("MWSE", "config", "beta.json"), os.path.join("MWSE", "config", "beta_extra.json")}
    assert res["edited"] == []                                                  # settings aren't "edits"
    assert not (data / "MWSE" / "mods" / "mwsuite" / "beta").exists()          # empty folder removed
    assert (data / "MWSE" / "config").is_dir() and (data / "MWSE" / "mods" / "mwsuite").is_dir()
    assert not (data / "beta-metadata.toml").exists()
    bak = res["prune_backup"]
    assert bak.startswith(str(game / "mwdialog_backup" / P.LUA_PRUNE_DIR))
    assert open(os.path.join(bak, "Data Files", "MWSE", "config", "beta.json")).read() == '{"my": "settings"}'
    rows = [json.loads(x) for x in open(res["journal"], encoding="utf-8")]
    assert rows[0]["op"] == "run" and sum(r["op"] == "pruned" for r in rows) == 5
    assert any(r["op"] == "rmdir" and r["rel"] == "MWSE/mods/mwsuite/beta" for r in rows)
    assert (data / "MWSE" / "mods" / "mwsuite" / "alpha" / "main.lua").exists()
    assert "mwsuite/beta" not in manifest(game)["mods"]
    lines = [line for _err, line in P.lua_prune_report(res)]
    assert any("mwsuite/beta (mod removed from lua tools)" in x for x in lines)
    assert any("--undo-lua-prune" in x for x in lines)


def test_file_dropped_from_a_module_is_pruned_but_its_settings_stay(tmp_path):
    src, game, data = setup(tmp_path)
    deploy(src, data)
    (src / "MWSE" / "mods" / "mwsuite" / "beta" / "mcm.lua").unlink()
    res = deploy(src, data)
    assert [p["rel"] for p in res["pruned"]] == [os.path.join("MWSE", "mods", "mwsuite", "beta", "mcm.lua")]
    assert res["pruned"][0]["why"] == "file removed from lua tools"
    assert (data / "MWSE" / "config" / "beta.json").exists()


def test_unrelated_and_third_party_files_are_left_alone(tmp_path):
    src, game, data = setup(tmp_path)
    deploy(src, data)
    others = {
        data / "MWSE" / "mods" / "abot" / "main.lua": "third party",
        data / "abot-metadata.toml": "third party toml",
        data / "MWSE" / "config" / "Easy Escort.json": "{}",                   # read by beta, not beta's
        data / "MWSE" / "config" / "abot.json": "{}",
        data / "MWSE" / "config" / "betamax.json": "{}",                       # starts with beta, not beta_
        data / "MWSE" / "mods" / "mwsuite" / "handmade" / "x.lua": "by hand",
        data / "Morrowind.esm": "esm",
    }
    for p, t in others.items():
        w(p, t)
    rm_mod(src, "beta")
    res = deploy(src, data)
    assert len(res["pruned"]) == 4
    for p, t in others.items():
        assert p.read_text() == t
    assert os.path.join("MWSE", "mods", "mwsuite", "handmade", "x.lua") in res["retired"]


def test_edited_file_is_still_removed_and_reported_loudly(tmp_path):
    src, game, data = setup(tmp_path)
    deploy(src, data)
    edited = data / "MWSE" / "mods" / "mwsuite" / "beta" / "main.lua"
    w(edited, "-- my own fix\n")
    rm_mod(src, "beta")
    res = deploy(src, data)
    rel = os.path.join("MWSE", "mods", "mwsuite", "beta", "main.lua")
    assert res["edited"] == [rel] and not edited.exists()
    assert open(os.path.join(res["prune_backup"], "Data Files", rel)).read() == "-- my own fix\n"
    report = P.lua_prune_report(res)
    assert any(err and "EDITED" in line for err, line in report)
    assert any("<-- EDITED" in line for _e, line in report)


def test_undo_puts_pruned_files_back_and_they_stay(tmp_path):
    src, game, data = setup(tmp_path)
    deploy(src, data)
    before = {p: p.read_bytes() for p in data.rglob("*") if p.is_file() and "beta" in str(p)}
    rm_mod(src, "beta")
    pruned = deploy(src, data)
    assert pruned["pruned"] and not any(p.exists() for p in before)
    res = P.undo_lua_prune(str(data))
    assert res["run"] == pruned["prune_backup"] and res["failed"] == []
    assert len(res["restored"]) == len(before)
    for p, b in before.items():
        assert p.read_bytes() == b
    again = deploy(src, data)                     # the record no longer lists them: not removed again
    assert again["pruned"] == [] and all(p.exists() for p in before)
    assert P.undo_lua_prune(str(data))["run"] is None


def test_undo_command_line(tmp_path, capsys):
    src, game, data = setup(tmp_path)
    deploy(src, data)
    rm_mod(src, "beta")
    deploy(src, data)
    try:
        assert P._main(["--undo-lua-prune", "--data-dir", str(data)]) == 0
    finally:
        P.release_game_locks()
    assert "Put back 4 file(s)" in capsys.readouterr().out
    assert (data / "beta-metadata.toml").exists()


def test_undo_leaves_a_file_put_there_since(tmp_path):
    src, game, data = setup(tmp_path)
    deploy(src, data)
    rm_mod(src, "beta")
    deploy(src, data)
    w(data / "beta-metadata.toml", "something new")
    res = P.undo_lua_prune(str(data))
    assert ("beta-metadata.toml", "another file is there now; left alone") in res["skipped"]
    assert (data / "beta-metadata.toml").read_text() == "something new"


def test_bootstrap_removes_retired_mweffectinspector_once(tmp_path):
    src, game, data = setup(tmp_path)
    mei = data / "MWSE" / "mods" / "mwsuite" / "mweffectinspector"
    for fn in ("config.lua", "inspector.lua", "main.lua", "mcm.lua"):
        w(mei / fn, f"-- {fn}\n")
    w(data / "mweffectinspector-metadata.toml", "[package]\n")
    w(data / "MWSE" / "config" / "mweffectinspector.json", '{"enabled": true}')
    w(data / "MWSE" / "mods" / "mwsuite" / "handmade" / "x.lua", "by hand")
    w(data / "MWSE" / "mods" / "mweffectinspector" / "main.lua", "not the suite's folder")
    assert not (game / P.LUA_MANIFEST).exists()
    res = deploy(src, data)
    assert {p["rel"] for p in res["pruned"]} == {
        os.path.join("MWSE", "mods", "mwsuite", "mweffectinspector", fn)
        for fn in ("config.lua", "inspector.lua", "main.lua", "mcm.lua")} | {
        "mweffectinspector-metadata.toml", os.path.join("MWSE", "config", "mweffectinspector.json")}
    assert not mei.exists() and not (data / "MWSE" / "config" / "mweffectinspector.json").exists()
    assert (data / "MWSE" / "mods" / "mwsuite" / "handmade" / "x.lua").exists()
    assert (data / "MWSE" / "mods" / "mweffectinspector" / "main.lua").exists()
    assert "mweffectinspector" in manifest(game)["retired_done"]
    P.undo_lua_prune(str(data))
    assert (mei / "main.lua").exists()
    assert deploy(src, data)["pruned"] == []      # once only
    assert (mei / "main.lua").exists()


def test_bootstrap_skips_a_retired_name_back_in_lua_tools(tmp_path):
    src, game, data = setup(tmp_path)
    suite_mod(src, "mweffectinspector")
    w(data / "MWSE" / "config" / "mweffectinspector.json", "{}")
    res = deploy(src, data)
    assert res["pruned"] == [] and (data / "MWSE" / "config" / "mweffectinspector.json").exists()
    assert "mweffectinspector" not in manifest(game)["retired_done"]


def test_non_suite_mod_is_deployed_tracked_updated_and_pruned(tmp_path):
    src, game, data = setup(tmp_path)
    stub = src / "MWSE" / "mods" / "SomeMod" / "interop.lua"
    w(stub, "-- SomeMod interop stub v1\n")
    w(src / "SomeMod-metadata.toml", '[package]\nname = "SomeMod interop stub"\n')
    res = deploy(src, data)
    assert os.path.join("MWSE", "mods", "SomeMod", "interop.lua") in res["copied"]
    other = manifest(game)["mods"]["SomeMod"]
    assert other["suite"] is False
    assert set(other["files"]) == {"MWSE/mods/SomeMod/interop.lua", "SomeMod-metadata.toml"}
    assert other["files"]["MWSE/mods/SomeMod/interop.lua"]["sha256"] == sha(stub)
    w(stub, "-- SomeMod interop stub v2\n")
    os.utime(stub, (1_000_000, 1_000_000))       # older date, but the deployed copy is still --play's own
    res = deploy(src, data)
    assert res["updated"] == [os.path.join("MWSE", "mods", "SomeMod", "interop.lua")]
    assert (data / "MWSE" / "mods" / "SomeMod" / "interop.lua").read_text() == "-- SomeMod interop stub v2\n"
    stub.unlink()
    (src / "SomeMod-metadata.toml").unlink()
    stub.parent.rmdir()
    res = deploy(src, data)
    assert {p["rel"] for p in res["pruned"]} == {os.path.join("MWSE", "mods", "SomeMod", "interop.lua"),
                                                 "SomeMod-metadata.toml"}
    assert not (data / "MWSE" / "mods" / "SomeMod").exists()
    assert "SomeMod" not in manifest(game)["mods"]


def test_another_mods_file_is_never_overwritten_or_removed(tmp_path):
    src, game, data = setup(tmp_path)
    w(src / "MWSE" / "mods" / "SomeMod" / "interop.lua", "-- stub\n")
    real = data / "MWSE" / "mods" / "SomeMod" / "interop.lua"
    w(real, "-- the real SomeMod\n")
    w(data / "MWSE" / "mods" / "SomeMod" / "main.lua", "-- the real SomeMod main\n")
    res = deploy(src, data)
    assert res["foreign"] == [os.path.join("MWSE", "mods", "SomeMod", "interop.lua")]
    assert real.read_text() == "-- the real SomeMod\n" and "SomeMod" not in manifest(game)["mods"]
    assert any(err and "another mod" in line for err, line in P.lua_prune_report(res))
    # the stub deployed first, then the real mod installed over it, then the stub taken out of lua tools
    src2, game2, data2 = setup(tmp_path / "second")
    stub = src2 / "MWSE" / "mods" / "SomeMod" / "interop.lua"
    w(stub, "-- stub\n")
    deploy(src2, data2)
    w(data2 / "MWSE" / "mods" / "SomeMod" / "interop.lua", "-- the real SomeMod\n")
    stub.unlink()
    res = deploy(src2, data2)
    assert res["pruned"] == [] and res["kept"]
    assert (data2 / "MWSE" / "mods" / "SomeMod" / "interop.lua").read_text() == "-- the real SomeMod\n"


def test_deploy_is_idempotent(tmp_path):
    src, game, data = setup(tmp_path)
    deploy(src, data)
    first = manifest(game)
    res = deploy(src, data)
    assert res["copied"] == res["updated"] == res["pruned"] == res["newer"] == res["foreign"] == []
    assert manifest(game)["mods"] == first["mods"]
    rm_mod(src, "beta")
    deploy(src, data)
    after = manifest(game)
    res = deploy(src, data)
    assert res["pruned"] == [] and res["prune_backup"] is None and manifest(game)["mods"] == after["mods"]
    assert len(os.listdir(game / "mwdialog_backup" / P.LUA_PRUNE_DIR)) == 1
    assert P.lua_prune_report(res) == []


def test_unreadable_manifest_prunes_nothing_and_is_replaced(tmp_path):
    src, game, data = setup(tmp_path)
    w(data / "MWSE" / "config" / "mweffectinspector.json", "{}")
    w(game / P.LUA_MANIFEST, "{not json")
    res = deploy(src, data)
    assert res["pruned"] == [] and "can't be read" in res["manifest_error"]
    assert (data / "MWSE" / "config" / "mweffectinspector.json").exists()
    assert manifest(game)["schema"] == P.LUA_MANIFEST_SCHEMA
    assert any(n.startswith(P.LUA_MANIFEST + ".unreadable-") for n in os.listdir(game))


def test_newer_manifest_version_is_left_alone(tmp_path):
    src, game, data = setup(tmp_path)
    w(game / P.LUA_MANIFEST, json.dumps({"schema": P.LUA_MANIFEST_SCHEMA, "version": 99, "mods": {}}))
    res = deploy(src, data)
    assert res["pruned"] == [] and "newer" in res["manifest_error"]
    assert json.loads((game / P.LUA_MANIFEST).read_text())["version"] == 99


def test_bootstrap_removes_mwpersonaleffects_config(tmp_path):
    src, game, data = setup(tmp_path)
    w(data / "MWSE" / "config" / "mwpersonaleffects.json", '{"enabled": true}')
    res = deploy(src, data)
    assert [p["rel"] for p in res["pruned"]] == [os.path.join("MWSE", "config", "mwpersonaleffects.json")]
    assert res["pruned"][0]["why"] == "settings of a retired mod" and res["pruned"][0]["config"]
    assert set(P.RETIRED_SUITE_MODS) <= set(manifest(game)["retired_done"])


def lua(*lines):
    return "\n".join(lines) + "\n"


def test_configs_belong_to_the_module_that_writes_them_whatever_the_name(tmp_path):
    src, game, data = setup(tmp_path)
    w(src / "MWSE" / "mods" / "mwsuite" / "classes" / "main.lua", lua(
        r'local CONFIG_FILE = "savedCustomClasses"',
        r'local saved = mwse.loadConfig(CONFIG_FILE, {})',
        r'local s = mwse.loadConfig("classes", {})',                        # read only: not its config
        r'local paper = mwse.loadConfig("mwplainpaperfix")',                # another mod's, read only
        r'mwse.saveConfig(CONFIG_FILE, saved)',
        r'json.savefile("config\\classes_journal", {})',
        r'local fh = io.open("Data Files\\MWSE\\config\\classes raw.json", "w")',
        r'local rd = io.open("Data Files\\MWSE\\config\\Easy Escort.json", "r")',
        r'template:saveOnClose("classes_mcm", saved)',
        r'local ok = pcall(mwse.saveConfig, "classes_cache", {})',
        r'local ok2, o = pcall(mwse.loadConfig, "AttendMeMWSE")'))
    deploy(src, data)
    owned = ["classes raw", "classes_cache", "classes_journal", "classes_mcm", "savedCustomClasses"]
    assert manifest(game)["mods"]["mwsuite/classes"]["configs"] == owned
    for n in owned + ["classes", "mwplainpaperfix", "Easy Escort", "AttendMeMWSE"]:
        w(data / "MWSE" / "config" / f"{n}.json", "{}")
    import shutil
    shutil.rmtree(src / "MWSE" / "mods" / "mwsuite" / "classes")          # its Lua is gone: the record decides
    res = deploy(src, data)
    assert {p["rel"] for p in res["pruned"] if p["config"]} == {os.path.join("MWSE", "config", f"{n}.json")
                                                 for n in owned}
    for n in ("classes", "mwplainpaperfix", "Easy Escort", "AttendMeMWSE"):
        assert (data / "MWSE" / "config" / f"{n}.json").exists()


def test_a_config_still_used_by_a_module_in_lua_tools_is_kept(tmp_path):
    src, game, data = setup(tmp_path)
    w(src / "MWSE" / "mods" / "mwsuite" / "old" / "main.lua", lua('mwse.saveConfig("shared_cfg", {})'))
    deploy(src, data)
    w(data / "MWSE" / "config" / "shared_cfg.json", "{}")
    w(src / "MWSE" / "mods" / "mwsuite" / "alpha" / "migrate.lua", lua('local o = mwse.loadConfig("shared_cfg")'))
    import shutil
    shutil.rmtree(src / "MWSE" / "mods" / "mwsuite" / "old")
    res = deploy(src, data)
    assert (data / "MWSE" / "config" / "shared_cfg.json").exists()
    assert any(rel == os.path.join("MWSE", "config", "shared_cfg.json") and "read by mwsuite/alpha" in why
               for rel, _m, why in res["kept"])


def test_config_folder_written_by_a_module_is_removed_and_restored(tmp_path):
    src, game, data = setup(tmp_path)
    w(src / "MWSE" / "mods" / "mwsuite" / "cons" / "store.lua", lua(
        'local store = {}', r'store.BASE = "Data Files\\MWSE\\config\\cons"', 'pcall(lfs.mkdir, store.BASE)'))
    deploy(src, data)
    assert manifest(game)["mods"]["mwsuite/cons"]["configs"] == ["cons/"]
    w(data / "MWSE" / "config" / "cons" / "user_commands.json", "{}")
    w(data / "MWSE" / "config" / "cons" / "scripts" / "a.lua", "-- mine")
    (data / "MWSE" / "config" / "cons" / "scripts" / "removed").mkdir()
    import shutil
    shutil.rmtree(src / "MWSE" / "mods" / "mwsuite" / "cons")
    res = deploy(src, data)
    assert sum(p["config"] for p in res["pruned"]) == 2 and not (data / "MWSE" / "config" / "cons").exists()
    assert (data / "MWSE" / "config").is_dir()
    P.undo_lua_prune(str(data))
    assert (data / "MWSE" / "config" / "cons" / "scripts" / "a.lua").read_text() == "-- mine"


def test_ownmods_configs_override_detection(tmp_path):
    src, game, data = setup(tmp_path)
    own = src / "MWSE" / "mods" / "mwsuite" / "ownmods.json"
    w(own, json.dumps({"version": 1, "ownMods": ["alpha", "beta"]}))                 # no "configs": detection
    deploy(src, data)
    assert manifest(game)["mods"]["mwsuite/beta"]["configs"] == ["beta", "beta_extra"]
    w(own, json.dumps({"version": 1, "ownMods": ["alpha", "beta"],
                       P.OWNMODS_CONFIGS_KEY: {"beta": ["beta", "beta data/", "../escape", 5]}}))
    deploy(src, data)
    assert manifest(game)["mods"]["mwsuite/beta"]["configs"] == ["beta", "beta data/"]
    w(data / "MWSE" / "config" / "beta_extra.json", "{}")                            # not declared: stays
    w(data / "MWSE" / "config" / "beta data" / "x.json", "{}")
    rm_mod(src, "beta")
    res = deploy(src, data)
    gone = {p["rel"] for p in res["pruned"]}
    assert os.path.join("MWSE", "config", "beta data", "x.json") in gone
    assert (data / "MWSE" / "config" / "beta_extra.json").exists()
    w(own, "{broken")
    assert P.own_config_overrides(str(src)) == {}
    own.unlink()
    assert P.own_config_overrides(str(src)) == {}
