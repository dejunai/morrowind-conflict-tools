"""The Performers Patch is gone from mwdialog_check: no flag builds it, --full forwards nothing for it, and a
patch an earlier version left is set aside (kept as a backup, never deleted) and taken out of the load order."""
import os
import types

import pytest

from conftest import m


def test_the_performers_flags_are_gone(tmp_path, capsys):
    for flag in ("--performers-patch", "--no-performers"):
        with pytest.raises(SystemExit):
            m.main([str(tmp_path / "Data Files"), flag])
        assert "unrecognized arguments: " + flag in capsys.readouterr().err
    assert not hasattr(m, "fix_performers") and not hasattr(m, "find_double_performers")
    assert not hasattr(m, "drop_performers_patch")


def test_an_earlier_versions_patch_is_set_aside_once(tmp_path, capsys):
    data = tmp_path / "Data Files"
    data.mkdir()
    (data / "Morrowind.esm").write_bytes(b"TES3")
    (data / m.PERFORMER_PATCH).write_bytes(b"TES3 old patch")
    m.write_load_order(str(tmp_path), ["Morrowind.esm", m.PERFORMER_PATCH], "test")
    args = types.SimpleNamespace(data_dir=str(data), ini=None)
    assert m.retire_performers_patch(args) == 1
    assert not (data / m.PERFORMER_PATCH).exists()
    kept = [p for root, _d, files in os.walk(tmp_path) for p in files if p.lower().startswith(m.PERFORMER_PATCH.lower())]
    assert kept, "the old patch is kept as a backup"
    assert [n.lower() for n in m.read_load_order(args)] == ["morrowind.esm"]
    assert "set aside" in capsys.readouterr().out
    assert m.retire_performers_patch(args) == 0          # nothing left to do: a no-op from then on
