"""Known Bugs policy (2026-11-26): luafix's general rules come first. A new KB/KR entry is only for what no rule can
express, and its description says why: "... (no rule can express this: <why>)". The ids below were in the table
when the policy started; any other id must carry the justification."""
import re

from conftest import _load

lf = _load("mwdialog_luafix")

LEGACY = frozenset(
    ["KB%d" % n for n in (1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 19, 23)]
    + ["KB%d" % n for n in range(29, 51)] + ["KR1", "KR2", "KR3"])
WHY = re.compile(r"\(no rule can express this: (?P<why>[^)]*\S[^)]*)\)")
RETIRED = frozenset({"KB5", "KB20", "KB21", "KB22", "KB24", "KB25", "KB26", "KB27", "KB28", "KB51",
                     "KP1", "KP2", "KP3", "KP4"})        # KB20/21/22/24/25/26/27: icon and texture paths, removed 2026-11-26


def test_every_new_known_bug_says_why_no_rule_can_express_it():
    for rule, plugin, path, _old, _new, what in lf.KNOWN_BUGS:
        if rule in LEGACY:
            continue
        m = WHY.search(what or "")
        assert m and len(m.group("why").strip()) >= 10, (
            f"{rule} ({plugin}, {path}): a new Known Bugs entry must end its description with "
            f"'(no rule can express this: <why>)'")


def test_retired_and_removed_ids_are_not_reused():
    assert not RETIRED & {r[0] for r in lf.KNOWN_BUGS}


def test_the_policy_check_catches_a_missing_reason(monkeypatch):
    monkeypatch.setattr(lf, "KNOWN_BUGS", lf.KNOWN_BUGS + [("KB99", "X", "x/main.lua", "a", "b", "a bug")])
    try:
        test_every_new_known_bug_says_why_no_rule_can_express_it()
    except AssertionError:
        return
    raise AssertionError("an entry without a reason passed")
