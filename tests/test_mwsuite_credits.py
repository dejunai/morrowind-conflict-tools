"""mwcriminal, mwconsole and mwcompanions credit the mods they borrow ideas from: a Credits page in each MCM
(source mod, author and a link when the original has a public page). Self-credits (suite mods by dejunai)
may have no link. Compatibility and interop alone are not credited."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODS = ROOT / "lua tools" / "MWSE" / "mods" / "mwsuite"
CASES = ["mwcriminal", "mwcompanions", "mwconsole"]
URL = re.compile(r'url = "(https://www\.nexusmods\.com/morrowind/mods/\d+)"')
ENTRY = re.compile(
    r'\{ mod = "([^"]+)", author = "([^"]+)",\s*idea = "([^"]+)"(?:,\s*url = "([^"]+)")? \}'
)
SELF = {"mwcompanionsneak", "mweffectinspector"}
# interop/compatibility only: not a borrowed idea the original author would recognize as theirs
REMOVED = {
    "Modern Lockpicking (MWSE)",
    "Stealth Overhaul 2",
    "Essential Indicators",
    "More Attentive Guards",
    "UI Expansion",
    "Attend Me (OpenMW)",
}
REQUIRED = {
    "mwcriminal": {"Accidental Theft Protection", "Door Locks (abotDoorLocks)", "mwcompanionsneak"},
    "mwcompanions": {"Smart Companions", "Easy Escort", "Attend Me Expanded MWSE"},
    "mwconsole": {"More Console Commands", "Blue - Smart Console", "Easy Console Commands",
                  "Selection Details", "mweffectinspector"},
}


def read(path):
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("mod", CASES)
def test_mcm_has_a_credits_page(mod):
    mcm = read(MODS / mod / "mcm.lua")
    assert 'createPage({ label = "Credits" })' in mcm
    entries = ENTRY.findall(mcm)
    names = {e[0] for e in entries}
    assert names >= REQUIRED[mod]
    assert names.isdisjoint(REMOVED)
    # Attend Me recruits were compatibility-only on mwcriminal
    if mod == "mwcriminal":
        assert "Attend Me Expanded MWSE" not in names
    linked = [e for e in entries if e[3]]
    assert len(linked) == len(URL.findall(mcm))
    for name, author, idea, url in entries:
        assert name and author and idea
        if url:
            assert url.startswith("https://")
            assert "interop" not in idea.lower()
        else:
            assert name in SELF
            assert "dejunai" in author
    if linked:
        assert "createHyperlink" in mcm
    assert "by dejunai" in mcm


def test_self_credits_dej_confirmed():
    criminal = read(MODS / "mwcriminal" / "mcm.lua")
    console = read(MODS / "mwconsole" / "mcm.lua")
    assert 'mod = "mwcompanionsneak"' in criminal and "dej (dejunai)" in criminal
    assert 'mod = "mweffectinspector"' in console and "dej (dejunai)" in console
    assert "url =" not in re.search(r'\{ mod = "mwcompanionsneak".*?\}', criminal, re.S).group()
    assert "url =" not in re.search(r'\{ mod = "mweffectinspector".*?\}', console, re.S).group()