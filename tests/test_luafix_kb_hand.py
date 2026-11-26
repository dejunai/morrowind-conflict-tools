"""MUSE 2.02 DebugLog calls that LuaJIT rejects (KB51, repaired by Y1 since 2026-11-26), and the KB20+ hand-repair
table."""
import os
import subprocess
import tempfile

import pytest

from conftest import _load

lf = _load("mwdialog_luafix")
KBH = _load("mwdialog_luafix_kb")

CFG = dict(lf.DEFAULTS)
LUAJIT = os.environ.get("MWMANAGER_LUAJIT", "/usr/bin/luajit")
if os.name == "nt" and not os.path.isfile(LUAJIT):
    # same search the existing known-bug tests use
    LUAJIT = os.environ.get("MWMANAGER_LUAJIT", os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "luajit", "luajit.exe"))


def compile_ok(text):
    """Compile-only check. Prefer lupa (what the Windows test suite uses); the bundled
    luajit.exe needs its own folder as cwd so jit.* modules load."""
    try:
        return lf.LupaChecker().check(text)
    except Exception:
        pass
    if not os.path.isfile(LUAJIT):
        pytest.skip("neither lupa nor a LuaJIT executable is available")
    fd, tmp = tempfile.mkstemp(suffix=".lua")
    try:
        os.close(fd)
        open(tmp, "wb").write(text.encode("latin-1"))
        r = subprocess.run([LUAJIT, "-b", tmp, "NUL" if os.name == "nt" else os.devnull],
                           capture_output=True, timeout=30,
                           cwd=os.path.dirname(LUAJIT) or None)
        msg = (r.stderr or r.stdout or b"").decode("utf-8", "replace")
        if r.returncode != 0 and "unknown luaJIT command" in msg:
            pytest.skip("LuaJIT has no bytecode command here; lupa is not installed")
        return r.returncode == 0, msg
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def muse_src(old):
    # old ends with '(' ; close the call and the function.
    return ("local MUSE = { DebugLog = function(...) end }\n"
            "local function report()\n"
            f"    {old}\n"
            "        1\n"
            "    )\n"
            "end\n")


# region.lua has three split calls (different tab depths). KB51 was retired on 2026-11-26: Y1 repairs any call whose
# '(' is on a later line, whatever the depth, and keeps every line number.
REGION_ALL = (
    muse_src("MUSE.DebugLog\n\t\t\t\t\t\t(")
    + "\nlocal function b()\n    "
    + "MUSE.DebugLog\n\t\t\t\t(\n        1\n    )\nend\n"
    + "\nlocal function c()\n    "
    + "MUSE.DebugLog\n\t\t\t(\n        1\n    )\nend\n"
)

@pytest.mark.parametrize("rel,source", [
    ("music/cell.lua", muse_src("MUSE.DebugLog\n                (")),
    ("music/combat.lua", muse_src("MUSE.DebugLog\n                (")),
    ("music/interior.lua", muse_src("MUSE.DebugLog\n\t\t\t\t(")),
    ("music/region.lua", REGION_ALL),
])
@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_Y1_joins_the_debuglog_call(rel, source, eol):
    source = source.replace("\n", eol)
    findings = [f for f in lf.FileAnalysis(source, "music", rel, CFG).run() if f["rule"] == "Y1"]
    assert findings and all(f["conf"] == "high" for f in findings)
    repaired, applied = lf.build_patch(source, findings, "music", CFG, "high", False)
    assert set(applied) == {"Y1"}
    assert "MUSE.DebugLog(" in repaired
    # the split form is gone, and no line moved
    assert "MUSE.DebugLog" + eol not in repaired and repaired.count(eol) == source.count(eol)
    assert not [f for f in lf.FileAnalysis(repaired, "music", rel, CFG).run() if f["rule"] == "Y1"]
    if os.path.isfile(LUAJIT):
        ok, msg = compile_ok(source)
        assert not ok, msg
        ok, msg = compile_ok(repaired)
        assert ok, msg
    # a general rule: any path
    assert [f for f in lf.FileAnalysis(source, "music", "music/other.lua", CFG).run() if f["rule"] == "Y1"]


def test_Y1_on_all_four_MUSE_files_through_check_paths(tmp_path):
    roots = tmp_path / "Data Files" / "MWSE" / "mods" / "music"
    roots.mkdir(parents=True)
    files = {
        "cell.lua": muse_src("MUSE.DebugLog\n                ("),
        "combat.lua": muse_src("MUSE.DebugLog\n                ("),
        "interior.lua": muse_src("MUSE.DebugLog\n\t\t\t\t(").replace("\n", "\r\n"),
        "region.lua": (muse_src("MUSE.DebugLog\n\t\t\t\t\t\t(")
                       + "\nlocal function b()\n    "
                       + "MUSE.DebugLog\n\t\t\t\t(\n        1\n    )\nend\n"
                       + "\nlocal function c()\n    "
                       + "MUSE.DebugLog\n\t\t\t(\n        1\n    )\nend\n").replace("\n", "\r\n"),
    }
    for name, text in files.items():
        (roots / name).write_bytes(text.encode("latin-1"))
    checker = None
    if os.path.isfile(LUAJIT):
        class Checker:
            name = "luajit-like"
            def check(self, text):
                return compile_ok(text)
        checker = Checker()
    rep = lf.check_paths([str(roots)], CFG, checker=checker, use_cache=False,
                         data_dir=str(tmp_path / "Data Files"))
    for name in files:
        ent = next(e for p, e in rep.files.items() if p.lower().endswith(name))
        assert ent["patch"] and ent["patch"]["ok"] and ent["patch"]["rules"] == ["Y1"], (name, ent.get("patch"))
        if os.path.isfile(LUAJIT):
            ok, msg = compile_ok(ent["patch"]["text"])
            assert ok, (name, msg)


def test_hand_repair_rules_are_keyed_idempotent_and_not_own_mods():
    seen = {}
    for rule, owner, path, old, new, what in KBH.RULES:
        assert path.lower() == path
        assert not path.lower().startswith("mwsuite/")
        first = path.split("/")[0].lower()
        # lib/ and third-party mods only; never a first-party folder
        if not path.startswith("lib/"):
            assert first not in lf.OWN_MODS_FALLBACK, path
        assert old and old != new  # new may be empty: a line is deleted
        assert old not in new
        key = (path, old)
        assert key not in seen, f"duplicate fingerprint for {path}"
        seen[key] = rule
        assert what and owner
    assert set(KBH.KB_WHOLE) <= lf.KNOWN_BUGS_WHOLE
    # a second listing of the same part would mean the table was appended twice
    assert len(list(KBH.RULES)) == len(KBH.RULES)


def test_Y1_repairs_the_creatures_and_critters_syntax_error(tmp_path):
    """Was KB28 (retired 2026-11-26): literals on separate lines with no ',' never compile; Y1 adds it."""
    src = (
        "local t = {\n"
        "  {\n"
        "    id = \"_plume\",\n"
        "    ids = {\n"
        "      \"aa_cr_ing_Twilight_feather\"\n"
        "      \"aa_RacerPlumes2\"\n"
        "      \"aa_RacerPlumes3\"\n"
        "      \"aa_RacerPlumes4\"\n"
        "    }\n"
        "  }\n"
        "}\n"
    )
    rel = "danae/cc/main.lua"
    path = tmp_path / "Data Files" / "MWSE" / "mods" / "danae" / "cc" / "main.lua"
    path.parent.mkdir(parents=True)
    path.write_bytes(src.encode("latin-1"))
    checker = None
    if os.path.isfile(LUAJIT):
        class Checker:
            name = "luajit-like"
            def check(self, text):
                return compile_ok(text)
        checker = Checker()
    rep = lf.check_paths([str(path.parent.parent.parent)], CFG, checker=checker, use_cache=False,
                         data_dir=str(tmp_path / "Data Files"))
    ent = next(iter(rep.files.values()))
    assert ent["error"] is None
    assert ent["patch"] and ent["patch"]["ok"] and "Y1" in ent["patch"]["rules"]
    assert ent["patch"]["text"].count("\n") == src.count("\n")
    assert '"aa_cr_ing_Twilight_feather",' in ent["patch"]["text"]
    if os.path.isfile(LUAJIT):
        ok, msg = compile_ok(ent["patch"]["text"])
        assert ok, msg
    # already fixed: no further change
    path.write_bytes(ent["patch"]["text"].encode("latin-1"))
    rep2 = lf.check_paths([str(path.parent.parent.parent)], CFG, checker=checker, use_cache=False,
                          data_dir=str(tmp_path / "Data Files"))
    ent2 = next(iter(rep2.files.values()))
    assert ent2["patch"] is None or "Y1" not in (ent2["patch"]["rules"] or [])
