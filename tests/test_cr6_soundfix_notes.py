"""CR-6: mwsoundfix_data.json says why --soundfix left a script alone and which version of the rules built it, and
mwsoundguard quotes that under each RUNAWAY line (so a runaway reads 'left as it is: ...', 'rewrote' or 'no script')."""
import json
import os
import re
import subprocess

import pytest

import mwdialog_soundfix as SF  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUAJIT = os.path.join(ROOT, "tools", "luajit", "luajit.exe")
GUARD = os.path.join(ROOT, "lua tools", "MWSE", "mods", "mwsuite", "mwsoundguard", "main.lua")


def test_the_code_digest_tells_a_patch_built_by_other_rules(tmp_path):
    cfg = tmp_path / "MWSE" / "config"
    cfg.mkdir(parents=True)
    assert not SF.soundfix_is_stale(str(tmp_path))                    # no patch data: nothing to call stale
    (cfg / SF.DATA_JSON).write_text(json.dumps({"scripts": {}, "code": SF._code_digest()}), encoding="utf-8")
    assert not SF.soundfix_is_stale(str(tmp_path))
    (cfg / SF.DATA_JSON).write_text(json.dumps({"scripts": {}, "code": "000000000000"}), encoding="utf-8")
    assert SF.soundfix_is_stale(str(tmp_path))
    (cfg / SF.DATA_JSON).write_text(json.dumps({"scripts": {}}), encoding="utf-8")   # written before CR-6
    assert SF.soundfix_is_stale(str(tmp_path))


def test_run_soundfix_records_skip_reasons_and_the_code_digest(tmp_path, monkeypatch):
    """Without MWRecompile: build() is replaced by what it returns, the data file is what is checked."""
    game = tmp_path / "Morrowind"
    data = game / "Data Files"
    data.mkdir(parents=True)
    import mwdialog_paths as MP
    monkeypatch.setattr(MP, "find_mwrecompile", lambda *_a, **_k: "MWRecompile.exe")
    rec = SF.raw_record("SCPT", b"")
    monkeypatch.setattr(SF, "build", lambda *_a, **_k: (
        [SF.epoch_global(), rec], [], {"loopscript": {"owner": "A.esp", "groups": [
            {"var": "mwsfOn1", "kind": "loop", "ref": "", "sounds": ["hum"]}]}},
        {"swampsoundscript": ("Yet Another Better Sounds Patch.esp",
                              "'swampnight' belongs to more than one guarded group")}))
    monkeypatch.setattr(SF, "_load_order_with", lambda *_a, **_k: False)
    import types
    args = types.SimpleNamespace(data_dir=str(data), dry_run=False, soundfix_report=False, soundfix_loop_mode="flag",
                                 mwrecompile=None, ini=None)
    assert SF.run_soundfix(args, [], []) == 0
    got = json.loads((data / "MWSE" / "config" / SF.DATA_JSON).read_text(encoding="utf-8"))
    assert got["skipped"] == {"swampsoundscript": {"owner": "Yet Another Better Sounds Patch.esp",
                                                   "why": "'swampnight' belongs to more than one guarded group"}}
    assert got["code"] == SF._code_digest() and list(got["scripts"]) == ["loopscript"]


def _note_block():
    src = open(GUARD, encoding="utf-8").read()
    m = re.search(r"-- mwsoundfix_data\.json \(mwdialog_check --soundfix\).*?(?=\nlocal function cachedDuration)", src, re.S)
    assert m, "mwsoundguard's soundfix note block"
    return m.group(0)


@pytest.mark.skipif(not os.path.isfile(LUAJIT), reason="LuaJIT not available")
def test_mwsoundguard_says_why_a_runaway_script_was_not_rewritten():
    script = """
mwse = { loadConfig = function(name) if name == "mwsoundfix_data" then return {
    scripts = { loopscript = { owner = "A.esp" } },
    skipped = { swampsoundscript = { owner = "Y.esp", why = "'swampnight' belongs to more than one guarded group" } } } end end }
""" + _note_block() + """
print(soundfixNote("SwampSoundScript"))
print(soundfixNote("LoopScript"))
print(soundfixNote("SignRotate"))
print(soundfixNote(nil))
"""
    out = subprocess.run([LUAJIT, "-"], input=script, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    lines = out.stdout.strip().splitlines()
    assert lines[0] == "MWSoundFix left this script as it is: 'swampnight' belongs to more than one guarded group"
    assert lines[1] == "MWSoundFix rewrote this script (A.esp)"
    assert lines[2].startswith("not in MWSoundFix")
    assert lines[3].startswith("no script on the object")
