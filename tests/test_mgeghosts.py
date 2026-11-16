"""Objects mwcollide hides in exterior cells are kept out of MGE XE distant land (G7: TOML by id; others: .ovr)."""
import json
import os
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

from conftest import _load  # noqa: E402
mge_ghosts = _load("mwdialog_mgeghosts")


class GhostStaticsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.game = Path(tmp.name)
        self.data = self.game / "Data Files"
        (self.data / "MWSE" / "config").mkdir(parents=True)
        (self.game / "mge3").mkdir()
        cells = {"#1,2": [{"id": "Ex_Tower_Ghost", "pos": [0, 0, 0]}, {"id": "ex_wall_shared", "pos": [9, 9, 9]}],
                 "balmora, guild": [{"id": "in_only", "pos": [1, 1, 1]}]}
        (self.data / "MWSE" / "config" / mge_ghosts.COLLIDE_DATA).write_text(json.dumps({"cells": cells}))
        placed = Counter({"ex_tower_ghost": 1, "ex_wall_shared": 4, "ex_de_sn_gate": 2, "ex_load_door": 1})
        in_place = {"ex_tower_ghost", "ex_wall_shared", "ex_de_sn_gate"}      # ex_load_door teleports
        models = {"ex_tower_ghost": "x\\tower.nif", "ex_wall_shared": "x\\wall.nif",
                  "ex_de_sn_gate": "x\\ex_de_sn_gate.nif", "ex_load_door": "d\\load.nif"}
        tags = {"ex_de_sn_gate": "DOOR", "ex_load_door": "DOOR"}
        for target, value in (("exterior_placements", lambda plugins: (placed, in_place)),
                              ("object_info", lambda plugins: (tags, models, set()))):
            patcher = mock.patch.object(mge_ghosts, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_classic_mge_gets_an_ovr_of_meshes_whose_every_copy_is_hidden(self):
        path = mge_ghosts.write(str(self.game), str(self.data), [], log=lambda s: None)
        self.assertTrue(path.endswith(".ovr"))
        text = Path(path).read_text(encoding="utf-8")
        self.assertIn("x\\tower.nif=ignore", text)
        self.assertNotIn("wall", text)                    # still placed elsewhere: left in distant land

    def test_g7_gets_a_toml_of_object_ids_and_the_old_ovr_goes(self):
        mge_ghosts.write(str(self.game), str(self.data), [], log=lambda s: None)
        (self.game / "mgeXE.toml").write_text("")
        path = mge_ghosts.write(str(self.game), str(self.data), [], log=lambda s: None)
        self.assertTrue(path.endswith(".toml"))
        text = Path(path).read_text(encoding="utf-8")
        self.assertIn("[tools.mge-xe.distantland]", text)
        self.assertIn('"ex_tower_ghost",', text)
        self.assertNotIn("ex_wall_shared", text)
        self.assertNotIn("in_only", text)                 # interiors have no distant land
        self.assertIn('"ex_de_sn_gate",', text)           # swings open: its baked closed copy would stay
        self.assertNotIn("ex_load_door", text)            # a load door never moves
        self.assertFalse((self.game / "mge3" / (mge_ghosts.NAME + ".ovr")).exists())

    def test_no_mge3_folder_writes_nothing(self):
        os.rmdir(self.game / "mge3")
        self.assertIsNone(mge_ghosts.write(str(self.game), str(self.data), [], log=lambda s: None))


if __name__ == "__main__":
    unittest.main()
