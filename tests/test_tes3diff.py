"""tes3diff.py (repository only): finding and verifying the optional tes3conv converter, and the record-level diff.
These tests do not need tes3conv: they use fake program files and hand-written records."""
import hashlib
import os
import re

import pytest

from conftest import SRC, _load

pytestmark = pytest.mark.skipif(not os.path.isfile(os.path.join(SRC, "tes3diff.py")),
                                reason="tes3diff.py is a repository-only dev tool, not vendored here (MWManager)")
T = _load("tes3diff") if os.path.isfile(os.path.join(SRC, "tes3diff.py")) else None
EXE = "tes3conv.exe" if os.name == "nt" else "tes3conv"


def fake(folder, name=None, data=b"not really tes3conv"):
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / (name or EXE)
    p.write_bytes(data)
    return p


# ------------------------------------------------------------------------------------------- finding it
def test_the_lookup_order_is_explicit_then_vendored_then_env_then_path_then_dev_folders(tmp_path):
    a, b, c, d, v = (fake(tmp_path / n) for n in "abcdv")
    dev, ven = [tmp_path / "d"], [tmp_path / "v"]
    on_path = lambda name: str(c)
    assert T.find_tes3conv(str(a), {"TES3CONV": str(b)}, dev, on_path, ven) == a              # --tes3conv first
    assert T.find_tes3conv(None, {"TES3CONV": str(b)}, dev, on_path, ven) == v                # then the vendored copy
    assert T.find_tes3conv(None, {"TES3CONV": str(b)}, dev, on_path, []) == b                 # then TES3CONV
    assert T.find_tes3conv(None, {}, dev, on_path, []) == c                                   # then PATH
    assert T.find_tes3conv(None, {}, dev, lambda name: None, []) == d                         # then the dev folders
    assert T.find_tes3conv(None, {"TES3CONV": str(tmp_path / "missing")}, dev, lambda name: None, []) == d
    assert T.find_tes3conv(None, {}, [tmp_path / "nothing"], lambda name: None, []) is None
    assert T.find_tes3conv(None, {}, dev, on_path, [tmp_path / "gone"]) == c                  # no vendored copy: on down


def test_the_default_vendored_copy_is_third_party_tes3conv_in_the_repository():
    assert T.vendored_dirs() == [T.HERE / "third_party" / "tes3conv"]
    if (T.HERE / "third_party" / "tes3conv" / "tes3conv.exe").is_file() and os.name == "nt":
        assert T.find_tes3conv(None, {}, [], lambda name: None) == T.HERE / "third_party" / "tes3conv" / "tes3conv.exe"


def test_a_folder_is_searched_below_and_the_newest_version_folder_wins(tmp_path):
    fake(tmp_path / "tes3conv" / "v0.4.0")
    new = fake(tmp_path / "tes3conv" / "v0.4.1")
    assert T.find_tes3conv(None, {}, [tmp_path / "tes3conv"], lambda name: None, []) == new
    assert T.find_tes3conv(str(tmp_path / "tes3conv" / "v0.4.1"), {}, [], lambda name: None, []) == new


@pytest.mark.parametrize("value", ["off", "OFF", "none", "0", "disabled"])
def test_tes3conv_off_switches_the_lookup_off(tmp_path, value):
    p = fake(tmp_path / "x")
    assert T.find_tes3conv(None, {"TES3CONV": value}, [tmp_path / "x"], lambda name: str(p)) is None   # the vendored copy too
    assert T.find_tes3conv(None, {"TES3CONV": value}, [], lambda name: None, [tmp_path / "x"]) is None
    assert T.find_tes3conv(str(p), {"TES3CONV": value}, [], lambda name: None) == p      # --tes3conv still wins


def test_the_default_dev_folders_are_relative_to_the_repository_and_the_source_names_no_absolute_path():
    dirs = T.dev_dirs()
    assert dirs[0] == T.HERE / ".devtools" / "tes3conv" and dirs[1] == T.HERE.parent / "_devtools" / "tes3conv"
    text = open(os.path.join(SRC, "tes3diff.py"), encoding="utf-8").read()
    assert not re.search(r"[A-Za-z]:\\\\(?!\\\\)", text.replace(".devtools\\\\tes3conv", ""))      # no drive-letter path
    assert "Users" not in text and "Program Files" not in text


# ------------------------------------------------------------------------------------------ verifying it
def test_the_pin_matches_the_official_asset_digests():
    assert T.VERSION == "v0.4.1"
    assert T.ASSET_SHA256["windows"] == "2783e835efdd4e28e9d31d63674c9c036f1332ef948707d581af33e7618a87a9"
    assert re.fullmatch(r"[0-9a-f]{64}", T.EXE_SHA256["windows"])


def test_a_program_with_the_pinned_hash_is_ok_and_another_warns_once(tmp_path, monkeypatch):
    p = fake(tmp_path / "x")
    monkeypatch.setattr(T, "_platform", lambda: "windows")
    monkeypatch.setattr(T, "EXE_SHA256", {"windows": hashlib.sha256(p.read_bytes()).hexdigest()})
    warnings = []
    assert T.checked(p, warn=warnings.append) == "ok" and warnings == []
    monkeypatch.setattr(T, "EXE_SHA256", {"windows": "0" * 64})
    monkeypatch.setattr(T, "_warned", set())
    assert T.checked(p, warn=warnings.append) == "mismatch" and T.checked(p, warn=warnings.append) == "mismatch"
    assert len(warnings) == 1 and "not the pinned tes3conv v0.4.1" in warnings[0] and "github.com/Greatness7" in warnings[0]


def test_a_platform_with_no_pin_says_it_was_not_verified(tmp_path, monkeypatch):
    p = fake(tmp_path / "x")
    monkeypatch.setattr(T, "_platform", lambda: "plan9")
    monkeypatch.setattr(T, "_warned", set())
    warnings = []
    assert T.checked(p, warn=warnings.append) == "unpinned" and "not verified" in warnings[0]


# ------------------------------------------------------------------------------------------- the diff
def misc(id_, **kw):
    return dict({"type": "MiscItem", "id": id_, "name": "Thing", "data": {"weight": 1.0, "value": 1}}, **kw)


HEADER = {"type": "Header", "author": "t", "num_objects": 1, "masters": []}


def test_added_removed_changed_and_unchanged_records_are_told_apart():
    old = [HEADER, misc("a"), misc("b"), misc("c")]
    new = [HEADER, misc("a", name="Renamed"), misc("c"), misc("d")]
    lines, counts = T.diff_records(old, new)
    assert lines == ["~ MiscItem a", '    name: "Thing" -> "Renamed"', "- MiscItem b", "+ MiscItem d"]
    assert counts == {"added": 1, "removed": 1, "changed": 1, "unchanged": 2}
    assert T.summary(counts) == "1 added, 1 removed, 1 changed, 2 unchanged"


def test_a_record_that_only_moved_or_changed_id_case_is_not_a_difference():
    old = [HEADER, misc("Alpha"), misc("beta")]
    new = [HEADER, misc("BETA"), misc("alpha")]
    assert T.diff_records(old, new)[0] == ["~ MiscItem alpha", '    id: "Alpha" -> "alpha"', "~ MiscItem beta", '    id: "beta" -> "BETA"']


def test_nested_and_list_changes_get_a_path_and_a_missing_side_is_absent():
    old = [{"type": "LeveledItem", "id": "l", "items": [["a", 1], ["b", 2]], "data": {"x": 1}}]
    new = [{"type": "LeveledItem", "id": "l", "items": [["a", 1], ["b", 3], ["c", 1]], "data": {"x": 1, "y": 2}}]
    lines, _ = T.diff_records(old, new)
    assert lines == ["~ LeveledItem l", "    items[1][1]: 2 -> 3", '    items[2]: <absent> -> ["c", 1]', "    data.y: <absent> -> 2"]


def test_cells_and_landscapes_are_matched_by_grid_and_a_repeated_key_is_kept():
    cell = lambda name, x, y, **kw: dict({"type": "Cell", "name": name, "data": {"grid": [x, y]}}, **kw)
    old = [cell("", 1, 2), cell("Seyda Neen", 0, 0)]
    new = [cell("", 1, 2, extra=1), cell("Seyda Neen", 0, 0), {"type": "Dialogue", "id": "x"}, {"type": "Dialogue", "id": "x"}]
    lines, counts = T.diff_records(old, new)
    assert lines == ["~ Cell @1,2", "    extra: <absent> -> 1", "+ Dialogue x", "+ Dialogue x#2"]
    assert counts["added"] == 2 and counts["changed"] == 1 and counts["unchanged"] == 1


def test_limit_caps_the_fields_listed_per_record():
    old = [dict(type="X", id="r", **{"f%d" % i: 0 for i in range(5)})]
    new = [dict(type="X", id="r", **{"f%d" % i: 1 for i in range(5)})]
    lines, _ = T.diff_records(old, new, limit=2)
    assert len(lines) == 4 and lines[-1] == "    ... and 3 more field(s)"
    assert len(T.diff_records(old, new, limit=0)[0]) == 6


# ----------------------------------------------------------------------------------------- command line
def test_help_exits_0_and_an_unknown_switch_or_wrong_arguments_exit_2(capsys):
    with pytest.raises(SystemExit) as e:
        T.parse_args(["-h"])
    assert e.value.code == 0 and "record-level diff" in capsys.readouterr().out
    for bad in (["--bogus"], ["only_one.esp"], ["a.esp", "b.esp", "c.esp"], ["--check", "a.esp"], ["a", "b", "--limit", "x"]):
        with pytest.raises(SystemExit) as e:
            T.parse_args(bad)
        assert e.value.code == 2
        assert "Nothing was done" in capsys.readouterr().err
    assert T.parse_args(["a", "b", "--tes3conv", "x", "--limit", "3"]) == (["a", "b"], "x", 3, False)
    assert T.parse_args(["--check", "--tes3conv=y"]) == ([], "y", 20, True)


def test_not_found_is_exit_3_and_says_it_is_optional(capsys, monkeypatch):
    monkeypatch.setenv("TES3CONV", "off")
    assert T.main(["a.esp", "b.esp"]) == 3
    err = capsys.readouterr().err
    assert "tes3conv not found" in err and "optional" in err


def test_main_prints_the_diff_and_exits_1_on_differences_0_without(capsys, monkeypatch, tmp_path):
    exe = fake(tmp_path / "bin")
    recs = {"old.esp": [HEADER, misc("a")], "new.esp": [HEADER, misc("a", name="N")], "same.esp": [HEADER, misc("a")]}
    monkeypatch.setattr(T, "to_records", lambda path, e: recs[os.path.basename(path)])
    monkeypatch.setattr(T, "checked", lambda p, warn=None: "ok")
    assert T.main(["old.esp", "new.esp", "--tes3conv", str(exe)]) == 1
    out = capsys.readouterr().out
    assert "~ MiscItem a" in out and 'name: "Thing" -> "N"' in out and "Summary: 0 added, 0 removed, 1 changed, 1 unchanged" in out
    assert T.main(["old.esp", "same.esp", "--tes3conv", str(exe)]) == 0