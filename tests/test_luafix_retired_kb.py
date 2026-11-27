"""Known Bugs entries retired on 2026-11-26 stay as regression fixtures (tests/fixtures/luafix_retired_kb.py): the
text as released goes in, the general rule that replaced the entry must repair it, the result must compile, and it
must change the same lines the old exact repair changed."""
import difflib
import os
import sys

import pytest

from conftest import _load

lf = _load("mwdialog_luafix")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures"))
import luafix_retired_kb as R                                 # noqa: E402

CHECKER = lf.find_checker()                                   # luajit -b (tools\\luajit or PATH), else lupa
need_checker = pytest.mark.skipif(CHECKER is None, reason="no Lua syntax checker (luajit or lupa)")
CFG = dict(lf.DEFAULTS)


def compiles(text):
    return CHECKER.check(text)[0]


def changed(a, b):
    out = set()
    for tag, i1, i2, _j1, _j2 in difflib.SequenceMatcher(None, a.split("\n"), b.split("\n"),
                                                         autojunk=False).get_opcodes():
        if tag != "equal":
            out |= set(range(i1, i2)) if i2 > i1 else {i1}
    return out


def strip_head(text):
    m = lf.MARK_RE.match(text, lf.insert_point(text))
    return text[:m.start()] + text[m.end():] if m else text


def wrap(rule, old):
    """A whole file around the released text (it is a fragment of the mod's file)."""
    if rule == "KB28":
        return "local t = {\n" + old + '      "last"\n}\nreturn t\n'
    if old.rstrip().endswith("("):
        return ("local MUSE = { DebugLog = function(...) end }\n"
                "local category = { createOnOffButton = function(self, t) end }\n"
                "local function f()\n" + old + "\n  {}\n  )\nend\nreturn f\n")
    return "local x = {\n" + old + "}\nreturn x\n"


def test_the_retired_ids_are_gone_from_the_table():
    ids = {r[0] for r in R.RETIRED}
    assert ids == {"KB5", "KB28", "KB51"}
    assert not ids & {r[0] for r in lf.KNOWN_BUGS} and not ids & set(lf.KNOWN_BUGS_WHOLE)


@need_checker
@pytest.mark.parametrize("entry", R.RETIRED, ids=lambda e: f"{e[0]}:{e[2]}")
def test_the_rule_repairs_what_the_retired_entry_did(entry):
    rule, _mod, rel, old, new, _what, by = entry
    src, kb = wrap(rule, old), wrap(rule, new)
    a = lf._analyse(src, "testmod", "testmod/" + rel.split("/")[-1], CFG)
    found = [f for f in a.findings if f["rule"] == by]
    assert found and all(f["conf"] == "high" for f in found)
    fixed, rules = lf.build_patch(a.src, found, "testmod", CFG, "high", False)
    if fixed is None:                                        # a text repair (Y1's commas) is already in a.src
        fixed, rules = a.src, [by]
    assert not compiles(src)
    assert rules == [by]
    body = strip_head(fixed)
    assert compiles(body)
    assert changed(src, body) == changed(src, kb)            # the same lines as the old exact repair
