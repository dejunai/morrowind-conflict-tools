"""tes3script:recompile crashed the game before the main menu (2026-11-22, ScriptCompiler::MatchFunctionName). An access
violation can't be caught from Lua, so the suite never calls it."""
import re
from pathlib import Path

MODS = Path(__file__).resolve().parents[1] / "Data Files" / "MWSE" / "mods" / "mwsuite"


def test_no_suite_mod_recompiles_a_script():
    users = [p.name for p in MODS.rglob("*.lua") if re.search(r"[:.]recompile\s*\(", p.read_text(encoding="utf-8"))]
    assert not users, users
