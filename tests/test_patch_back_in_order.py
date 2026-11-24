"""A generated patch --cell-conflicts set aside (it named a plugin that was turned off) goes back into the load
order when --fix rebuilds it: the ESM fixes patch right after the masters, the others before the Multipatch."""
import types

from conftest import m


def order_args(tmp_path, order, dry=False):
    (tmp_path / "Data Files").mkdir(exist_ok=True)
    (tmp_path / "Morrowind.ini").write_text("[Game Files]\n", encoding="cp1252")
    m.write_load_order(str(tmp_path), order, "test")
    return types.SimpleNamespace(data_dir=str(tmp_path / "Data Files"), ini=str(tmp_path / "Morrowind.ini"), dry_run=dry)


def test_set_aside_patches_go_back_in_their_places(tmp_path):
    args = order_args(tmp_path, ["Morrowind.esm", "Tribunal.esm", "A.esp", m.AUTO_MERGE_NAME, m.MULTI_PATCH_NAME])
    assert m.back_in_load_order(args, m.PATCH_NAME)
    assert m.back_in_load_order(args, m.PLACE_PATCH_NAME)
    assert m.read_load_order(args) == ["Morrowind.esm", "Tribunal.esm", m.PATCH_NAME, "A.esp", m.AUTO_MERGE_NAME,
                                       m.PLACE_PATCH_NAME, m.MULTI_PATCH_NAME]
    assert not m.back_in_load_order(args, m.PATCH_NAME)          # already there: nothing changes


def test_a_dry_run_changes_nothing(tmp_path):
    args = order_args(tmp_path, ["Morrowind.esm", "A.esp"], dry=True)
    assert not m.back_in_load_order(args, m.PLACE_PATCH_NAME)
    assert m.read_load_order(args) == ["Morrowind.esm", "A.esp"]
