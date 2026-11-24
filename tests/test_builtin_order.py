"""No default rules travel with the tools: the rules file is made with only its instruction header, and the
sorter itself puts the ESM fixes patch early and XE Sky Variations (when installed) last, before our patches."""
import types

from conftest import m
from test_near_order import _game, BASE


def sort_like_sort(tmp_path, plugins):
    args = types.SimpleNamespace(data_dir=str(tmp_path / "Morrowind" / "Data Files"), no_mlox_rules=True,
                                 no_content_order=True, ini=None)
    rule_sets, _files = m.sort_rule_sources(args, plugins, quiet=True)
    return m.compute_order(plugins, rule_sets, [n for n, _p in plugins])[0]


def test_the_new_rules_file_is_only_a_header():
    assert m.parse_rules("x", m.DEFAULT_RULES)[0] == []
    assert all(ln.startswith(";") or not ln.strip() for ln in m.DEFAULT_RULES.splitlines())


def test_esm_fixes_early_and_xe_sky_last_before_our_patches_with_no_rules_file(tmp_path):
    esp = ["Morrowind.esm"]
    plugins = _game(tmp_path, BASE + [("A.esp", esp), (m.MULTI_PATCH_NAME, esp), ("XE Sky Variations.esp", esp),
                                      ("B.esp", esp), (m.PATCH_NAME, esp), ("C.esp", esp)])
    order = sort_like_sort(tmp_path, plugins)
    assert order.index(m.PATCH_NAME) == 1                                   # right after the masters
    assert order[-2:] == ["XE Sky Variations.esp", m.MULTI_PATCH_NAME]
    assert not (tmp_path / "Morrowind" / m.RULES_FILE).exists()             # a sort reads it; --sort makes it


def test_without_xe_sky_nothing_changes(tmp_path):
    esp = ["Morrowind.esm"]
    plugins = _game(tmp_path, BASE + [("A.esp", esp), (m.MULTI_PATCH_NAME, esp), ("B.esp", esp)])
    assert sort_like_sort(tmp_path, plugins) == ["Morrowind.esm", "A.esp", "B.esp", m.MULTI_PATCH_NAME]
