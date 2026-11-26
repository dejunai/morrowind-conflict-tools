"""ownmods.json: the first-party list luafix never patches (unless --include-own)."""
import json
import os

from conftest import _load

lf = _load("mwdialog_luafix")

SCHEMA_VERSION = 1
SHIPPED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "lua tools", "MWSE", "mods", "mwsuite", "ownmods.json")


def write_own(data_dir, doc=None, raw=None):
    path = lf.own_mods_path(str(data_dir))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if raw is not None:
        open(path, "w", encoding="utf-8", newline="\n").write(raw)
    else:
        open(path, "w", encoding="utf-8", newline="\n").write(json.dumps(doc, indent=2) + "\n")
    return path


def test_shipped_ownmods_json_matches_the_fallback_and_has_mwconsole_not_mweffectinspector():
    data = json.loads(open(SHIPPED, encoding="utf-8").read())
    assert data["version"] == SCHEMA_VERSION and isinstance(data["ownMods"], list)
    names = {str(m).lower() for m in data["ownMods"]}
    assert names == set(lf.OWN_MODS_FALLBACK)
    assert "mwconsole" in names and "mweffectinspector" not in names
    assert "mwsuite" in names


def test_load_own_mods_reads_the_json_and_ignores_the_fallback(tmp_path):
    data_dir = tmp_path / "Data Files"
    write_own(data_dir, {"version": 1, "ownMods": ["mwconsole", "CustomMod"]})
    names, src = lf.load_own_mods(str(data_dir))
    assert names == frozenset({"mwconsole", "custommod"})
    assert src == lf.own_mods_path(str(data_dir))
    cfg = {}
    lf.ensure_own_mods(cfg, str(data_dir))
    assert "mwconsole" in lf.own_mod_names(cfg) and "custommod" in lf.own_mod_names(cfg)
    # the built-in names are not mixed in when the file is valid
    assert "mwcollide" not in lf.own_mod_names(cfg)


def test_load_own_mods_falls_back_quietly_when_mwsuite_is_absent(tmp_path, capsys):
    data_dir = tmp_path / "Data Files"
    data_dir.mkdir()
    names, src = lf.load_own_mods(str(data_dir), log=print)
    assert names == lf.OWN_MODS_FALLBACK and src == "built-in fallback"
    assert "warning:" not in capsys.readouterr().out


def test_load_own_mods_warns_when_mwsuite_is_present_but_the_file_is_missing(tmp_path, capsys):
    data_dir = tmp_path / "Data Files"
    (data_dir / "MWSE" / "mods" / "mwsuite").mkdir(parents=True)
    names, src = lf.load_own_mods(str(data_dir), log=print)
    assert names == lf.OWN_MODS_FALLBACK and src == "built-in fallback"
    assert "warning: using the built-in first-party mod list" in capsys.readouterr().out


def test_load_own_mods_warns_and_falls_back_when_the_file_is_not_version_1(tmp_path, capsys):
    data_dir = tmp_path / "Data Files"
    write_own(data_dir, {"version": 2, "ownMods": ["mwconsole"]})
    names, src = lf.load_own_mods(str(data_dir), log=print)
    assert names == lf.OWN_MODS_FALLBACK and src == "built-in fallback"
    assert "is not a version-1 ownMods file" in capsys.readouterr().out


def test_load_own_mods_warns_and_falls_back_when_the_file_is_not_json(tmp_path, capsys):
    data_dir = tmp_path / "Data Files"
    write_own(data_dir, raw="{")
    names, src = lf.load_own_mods(str(data_dir), log=print)
    assert names == lf.OWN_MODS_FALLBACK and src == "built-in fallback"
    assert "is not valid JSON" in capsys.readouterr().out


def test_check_paths_skips_mwconsole_and_uses_the_json_list(tmp_path):
    data_dir = tmp_path / "Data Files"
    write_own(data_dir, {"version": 1, "ownMods": ["mwsuite"]})
    root = data_dir / "MWSE" / "mods" / "mwsuite" / "mwconsole"
    root.mkdir(parents=True)
    # a nil lookup that would otherwise be A1 on a third-party file
    lua = "local function f(ref)\n ref.data.x = 1\nend\n"
    (root / "main.lua").write_text(lua, encoding="latin-1")
    # a third-party file of the same shape is still checked
    other = data_dir / "MWSE" / "mods" / "thirdparty"
    other.mkdir(parents=True)
    (other / "main.lua").write_text(lua, encoding="latin-1")
    cfg = dict(lf.DEFAULTS)
    rep = lf.check_paths([str(data_dir / "MWSE" / "mods")], cfg, checker=None, use_cache=False,
                         data_dir=str(data_dir))
    skipped = {os.path.normcase(p): why for p, why in rep.skipped}
    console = os.path.normcase(str(root / "main.lua"))
    assert console in skipped and "your own mod" in skipped[console]
    third = next(e for p, e in rep.files.items() if p.lower().endswith(os.path.join("thirdparty", "main.lua").lower())
                 or p.lower().endswith("thirdparty/main.lua") or p.lower().endswith("thirdparty\\main.lua"))
    assert any(f["rule"] == "A1" for f in third["findings"])


def test_fallback_own_mod_names_include_mwconsole_not_mweffectinspector():
    names = lf.own_mod_names()
    assert "mwconsole" in names and "mweffectinspector" not in names
    assert "mwsuite" in names
