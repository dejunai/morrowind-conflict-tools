"""mwcriminal, mwconsole and mwcompanions credit the mods they borrow ideas from: a Credits page in each MCM
(source mod, author and a link per entry) and a Credits section in the mod's design doc with the same links."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODS = ROOT / "lua tools" / "MWSE" / "mods" / "mwsuite"
DOCS = ROOT / "docs" / "dev"
CASES = [
    ("mwcriminal", "MWCRIMINAL_DESIGN.md"),
    ("mwcompanions", "MWCOMPANIONS_DESIGN.md"),
    ("mwconsole", "MWCONSOLE_DESIGN.md"),
]
URL = re.compile(r'url = "(https://www\.nexusmods\.com/morrowind/mods/\d+)"')
ENTRY = re.compile(r'\{ mod = "([^"]+)", author = "([^"]+)",\s*idea = "([^"]+)",\s*url = "([^"]+)" \}')


def read(path):
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("mod,doc", CASES)
def test_mcm_has_a_credits_page_with_links(mod, doc):
    mcm = read(MODS / mod / "mcm.lua")
    assert 'createPage({ label = "Credits" })' in mcm
    assert "createHyperlink" in mcm
    entries = ENTRY.findall(mcm)
    assert len(entries) >= 4
    assert len(entries) == len(URL.findall(mcm))
    for name, author, idea, url in entries:
        assert name and author and idea and url.startswith("https://")
    assert "by dejunai" in mcm


@pytest.mark.parametrize("mod,doc", CASES)
def test_doc_credits_list_every_mcm_link(mod, doc):
    mcm = read(MODS / mod / "mcm.lua")
    text = read(DOCS / doc)
    assert "## " in text and "Credits" in text
    credits = text[text.index("Credits"):]
    for name, author, _idea, url in ENTRY.findall(mcm):
        assert url in credits, (mod, url)
        assert name in credits and author.split(" (")[0] in credits, (mod, name)