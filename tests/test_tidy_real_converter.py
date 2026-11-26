"""The real Tidy-to-converter handoff (audit extension 3): one disposable staged mod, the real omw2mwse, a plan
(its dry run), --apply and --undo. Checks the JSON paths tidy journals ('/'-separated and relative), the
root / Extras / Off placement, that the converter's manifest owns every file it placed, and that --undo restores
the folder exactly. Skipped when omw2mwse isn't found: set OMW2MWSE to a converter checkout, its bin\\omw2mwse or
an omw2mwse executable, or put it on PATH / beside these tools. The fixture lives in pytest's temporary folder,
which must not be inside the user profile (run pytest with --basetemp elsewhere) and is never in a game install.
Python 3.9+."""
import hashlib
import json
import os
import types

import pytest

from conftest import vt


def _converter():
    env = os.environ.get("OMW2MWSE", "").strip().strip('"')
    if env:
        for p in (os.path.join(env, "bin", "omw2mwse"), env):
            if os.path.isfile(p):
                return vt._converter_cmd(p), None, p
        return None, None, ""
    return vt.find_converter()


def snap(root):
    out = {}
    for base, _ds, fns in os.walk(str(root)):
        for fn in fns:
            p = os.path.join(base, fn)
            with open(p, "rb") as f:
                out[os.path.relpath(p, str(root)).replace(os.sep, "/")] = hashlib.sha256(f.read()).hexdigest()
    return out


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())


@pytest.fixture
def real(tmp_path, monkeypatch):
    cmd, cenv, where = _converter()
    if not cmd:
        pytest.skip("omw2mwse not found (set OMW2MWSE to a converter checkout to run the real handoff)")
    home = os.path.normcase(os.path.abspath(os.path.expanduser("~")))
    if os.path.normcase(str(tmp_path)).startswith(home + os.sep):
        pytest.skip("pytest's temporary folder is inside the user profile; run with --basetemp outside it")
    game, staging = tmp_path / "game", tmp_path / "staging"
    (game / "Data Files").mkdir(parents=True)
    staging.mkdir()
    monkeypatch.setattr(vt, "find_converter", lambda home=None: (cmd, cenv, where))
    monkeypatch.setattr(vt, "CONVERTER", dict(vt.CONVERTER))
    monkeypatch.setattr(vt, "vortex_info", lambda d: {"title": "Glow Test", "author": "dej (dejunai)"})
    monkeypatch.setattr(vt, "HERE", str(game))
    monkeypatch.setattr(vt, "CORE_MISSING", {})
    monkeypatch.setattr(vt, "JOURNAL", str(tmp_path / "journal.jsonl"))
    monkeypatch.setattr(vt, "PLAN", str(tmp_path / "vortex_tidy_plan.txt"))
    monkeypatch.setattr(vt, "AUDIT_ROOT", str(tmp_path / "audit"))
    monkeypatch.setattr(vt, "BLACKLIST_FILE", str(tmp_path / "bl.txt"))
    for d in (vt.NOTES, vt.REVIEW, vt.CONVERTED, vt.CONVERT):
        d.clear()

    def run(*extra):
        vt.NOTES.clear()
        monkeypatch.setattr(vt.sys, "argv", ["vortex_tidy.py", "--staging", str(staging), "--no-lua", "--no-assets",
                                             "--convert-omwscripts=normal", *extra])
        return vt.main()
    return types.SimpleNamespace(run=run, staging=staging, tmp=tmp_path)


def test_plan_apply_undo_with_the_real_converter(real, capsys):
    mod = real.staging / "Glow-1-0"
    put(mod / "Glow.omwscripts", "GLOBAL: scripts/Glow/g.lua\n")
    put(mod / "scripts" / "Glow" / "g.lua",
        "local world = require('openmw.world')\n"
        "local HOURS = 7\n"
        "return { engineHandlers = { onUpdate = function(dt) if world.getGameTime() < HOURS then end end } }\n")
    put(mod / "meshes" / "glow" / "a.nif", b"NIF fixture")
    put(mod / "Glow.omwaddon", b"TES3 not a real plugin")
    put(mod / "optional" / "Extra.omwaddon", b"TES3 optional")
    put(mod / "readme.txt", "Glow test fixture\n")
    before = snap(mod)
    seen = []
    orig = vt.run_converter

    def spy(mod_dir, mode, dry_run=False):
        got = orig(mod_dir, mode, dry_run)
        seen.append((dry_run, got[1]))
        return got
    vt.run_converter = spy
    try:
        _plan_apply_undo(real, capsys, mod, before)
    finally:
        vt.run_converter = orig
    for _dry, data in seen:                                             # the contract tidy reads
        assert data and data.get("pendingRecovery", []) == []
        for m in data["mods"]:
            if "partialApis" in m:
                assert isinstance(m["partialApis"], list)
            for key in ("source", "off", "relocatedFrom", "willRelocateTo"):
                if m.get(key) and str(data.get("version", "0")) >= "0.2.3":
                    assert "\\" not in m[key] or os.path.isabs(m[key]), (key, m[key])


def _plan_apply_undo(real, capsys, mod, before):
    assert real.run() == 0                                              # the plan: a dry run, nothing written
    with open(vt.PLAN, encoding="utf-8") as f:
        plan = f.read()
    assert "    convert with omw2mwse (normal): OpenMW-only" in plan
    assert f"    {vt.CHECK_LABEL} " in plan and "omw2mwse places Glow's plugin" in plan
    assert snap(mod) == before

    assert real.run("--apply", "--yes") == 0
    out = capsys.readouterr().out
    assert "converted Glow-1-0 with omw2mwse (normal)" in out, out
    assert vt.read_intent() is None
    with open(vt.JOURNAL, encoding="utf-8") as f:
        (op,) = [o for o in map(json.loads, filter(str.strip, f)) if "omw_convert" in o]
    for key in ("from", "off", "tree"):                                 # relative, '/'-separated
        assert "\\" not in op[key] and not os.path.isabs(op[key]), (key, op[key])
    assert op["files"] and all("\\" not in k and not os.path.isabs(k) for k in op["files"])
    after = snap(mod)
    off = op["off"].rstrip("/")
    assert off.lower().startswith("off/") and off.endswith("/OpenMW")
    assert f"{off}/Glow.omwscripts" in after and f"{off}/scripts/Glow/g.lua" in after
    manifest = os.path.join(str(mod), *op["tree"].split("/"), "omw2mwse-manifest.json")
    with open(manifest, encoding="utf-8") as f:
        man = json.load(f)
    for rel, h in man["files"].items():                                  # the manifest owns what it placed
        assert after.get(rel.replace("\\", "/")) == h, rel
    keys = {k.replace("\\", "/") for k in man["files"]}
    for pl in man.get("plugins") or []:
        path = pl["path"].replace("\\", "/")
        assert path in keys, path
        if pl["placement"] == "root":
            assert "/" not in path
        elif pl["placement"] == "extras":
            assert path.lower().startswith("extras/")
        else:
            assert path.lower().startswith("off/")
    assert {pl["placement"] for pl in man.get("plugins") or []} >= {"extras"}

    assert vt.undo() == 0
    assert snap(mod) == before
