"""doc_scan.py verifies documented command-line switches against the code, and lists code
switches no doc mentions. Temporary folders only. Python 3.9+."""
import os
import textwrap

import pytest

from conftest import SRC, _load

# doc_scan.py is a repository-only developer tool: deploy.py never ships it and MWManager does not vendor it, so
# where it is missing these tests skip (as test_deploy.py does for deploy.py) instead of failing to import.
DOC_SCAN = os.path.join(SRC, "doc_scan.py")
pytestmark = pytest.mark.skipif(not os.path.isfile(DOC_SCAN),
                                reason="doc_scan.py is a repository-only dev tool, not vendored here (MWManager)")
DS = _load("doc_scan") if os.path.isfile(DOC_SCAN) else None


def write(root, rel, text):
    path = os.path.join(root, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(textwrap.dedent(text).lstrip("\n"))
    return path


def tool_src(*flags, suppressed=()):
    lines = ["import argparse", "p = argparse.ArgumentParser()",
             *[('p.add_argument("%s", help=argparse.SUPPRESS)' % f if f in suppressed
                else 'p.add_argument("%s")' % f) for f in flags]]
    return "\n".join(lines) + "\n"


def project(tmp_path, files):
    for rel, text in files.items():
        write(tmp_path, rel, text)
    return str(tmp_path)


def test_a_stale_switch_is_reported(tmp_path, capsys):
    root = project(tmp_path, {
        "tool.py": tool_src("--alpha"),
        "README.md": "# Tool\n\nUse `--alpha` or `--ghost`.\n",
    })
    assert DS.main([root]) == 1
    out = capsys.readouterr().out
    assert "README.md:3: --ghost: not a switch of any tool" in out
    assert "--alpha" not in out.split("not a switch")[0] or "README.md:" not in [ln for ln in out.splitlines() if "--alpha" in ln and "not a switch" in ln]
    assert not any(ln.startswith("README.md:") and "--alpha:" in ln for ln in out.splitlines())
    assert "1 documented switch(es) not in the code" in out


def test_a_renamed_switch_is_reported_in_both_directions(tmp_path, capsys):
    root = project(tmp_path, {
        "tool.py": tool_src("--new-name"),
        "README.md": "The flag is `--old-name`.\n",
    })
    assert DS.main([root]) == 1
    out = capsys.readouterr().out
    assert "README.md:1: --old-name: not a switch of any tool" in out
    assert "tool.py: --new-name is not documented" in out


def test_opt_equals_value_matches_the_flag(tmp_path, capsys):
    root = project(tmp_path, {
        "tool.py": tool_src("--preserve-saves"),
        "README.md": "Use `--preserve-saves=strict` or `--preserve-saves=basic`.\n",
    })
    assert DS.main([root]) == 0
    assert "OK:" in capsys.readouterr().out


def test_third_party_flags_after_the_command_name_are_ignored(tmp_path, capsys):
    root = project(tmp_path, {
        "tool.py": tool_src("--alpha"),
        "README.md": (
            "Pass `--alpha` first.\n"
            "Then run omw2mwse --json --rollback, and `luajit -b` file.lua.\n"
            "CHANGES should not matter.\n"
        ),
        "docs/CHANGES.md": "Removed `--ancient`.\n",
    })
    assert DS.main([root]) == 0
    out = capsys.readouterr().out
    assert "OK:" in out
    assert "--json" not in out and "--rollback" not in out and "--ancient" not in out


def test_a_clean_project_exits_0_and_suppress_is_not_undocumented(tmp_path, capsys):
    root = project(tmp_path, {
        "tool.py": tool_src("--alpha", "--secret", suppressed=("--secret",)),
        "README.md": "### tool.py Switches\n\n`--alpha` is the switch.\n",
    })
    assert DS.main([root]) == 0
    out = capsys.readouterr().out
    assert "OK:" in out and "undocumented" in out
    assert "--secret" not in out and "--help" not in out


def test_an_undocumented_code_switch_is_reported(tmp_path, capsys):
    root = project(tmp_path, {
        "tool.py": tool_src("--alpha", "--beta"),
        "README.md": "Only `--alpha` is described.\n",
    })
    assert DS.main([root]) == 1
    out = capsys.readouterr().out
    assert "tool.py: --beta is not documented" in out
    assert "0 documented switch(es) not in the code, 1 undocumented." in out


def test_unknown_switch_exits_2_and_help_exits_0(tmp_path, capsys):
    assert DS.main(["--nope"], root=str(tmp_path)) == 2
    err = capsys.readouterr().err
    assert "unknown switch" in err and "Nothing was done" in err
    assert DS.main(["--help"]) == 0
    assert "doc_scan.py" in capsys.readouterr().out


def test_the_real_repo_scans_clean(capsys):
    """The docs and the code agree: every documented switch exists and every switch is documented (or hidden
    with help=argparse.SUPPRESS). A new stale or undocumented switch fails here."""
    rc = DS.main([SRC])
    out = capsys.readouterr().out
    tools, mentions, (stale, undoc) = DS.scan(SRC)
    assert tools and mentions
    assert not stale, "documented switch(es) not in the code: %s" % sorted((p, f) for p, _n, f, _d in stale)
    assert not undoc, "undocumented switch(es): %s" % sorted(undoc)
    assert rc == 0 and out.startswith("OK:")
