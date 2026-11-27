"""Creature / NPC models whose Bounding Box makes the game divide by zero when a hit spawns blood
(SplashController::spawnBloodParticle, Morrowind.exe 0x54B8FF): the asset check finds the deployed copy and
--fix moves it to its mod's Off\\<plugin>\\broken\\. And the missing-file search in Vortex's staging folder
never offers back what was quarantined under Off\\ or Extras\\ ...\\broken\\. Credit: dej (dejunai)."""
import os
import struct
import types

import mwdialog_datatree as DT  # noqa: E402  (conftest put the tools on sys.path)
from conftest import ah, m

CRR = (-81.33909, 81.60149, 147.2294)           # Cliff Racer Remastered 1.3: center.y, extent.y, extent.z
PB = (-5.580498, 81.60149, 147.2294)            # the same box with the older replacer's center.y


def _s(b):
    return struct.pack("<I", len(b)) + b


def _node(kind, name, box=None, props=0, has=None):
    """One NiNode-like block: type, name, extra data, controller, flags, transform, scale, velocity, properties,
    bounding volume (type 1: a box) and no children."""
    b = _s(kind) + _s(name) + struct.pack("<ii", -1, -1) + struct.pack("<H", 8)
    b += struct.pack("<3f", 0, 0, 0) + struct.pack("<9f", 1, 0, 0, 0, 1, 0, 0, 0, 1) + struct.pack("<f", 1.0)
    b += struct.pack("<3f", 0, 0, 0) + struct.pack("<I", props) + struct.pack(f"<{props}i", *range(props))
    if box is None:
        return b + struct.pack("<I", 0 if has is None else has) + struct.pack("<I", 0)
    (cx, cy, cz), (ex, ey, ez) = box
    b += struct.pack("<II", 1 if has is None else has, 1) + struct.pack("<3f", cx, cy, cz)
    b += struct.pack("<9f", 1, 0, 0, 0, 1, 0, 0, 0, 1) + struct.pack("<3f", ex, ey, ez)
    return b + struct.pack("<I", 0)


def box_nif(cy=None, ey=None, ez=None, name=b"Bounding Box", props=0, has=None):
    blocks = _node(b"NiNode", b"Root")
    if cy is not None:
        blocks += _node(b"NiNode", name, ((0.0, cy, 290.0), (100.0, ey, ez)), props, has)
    return ah.NIF_HEAD + b"\n" + struct.pack("<II", 0x04000002, 2) + blocks


# ---------------------------------------------------------------- reading the box, and the engine's arithmetic
def test_bounding_box_is_read_from_the_named_node():
    box = ah.nif_bounding_box(box_nif(*CRR))
    assert box is not None
    (cx, cy, cz), (ex, ey, ez) = box
    assert abs(cy - CRR[0]) < 1e-4 and abs(ey - CRR[1]) < 1e-4 and abs(ez - CRR[2]) < 1e-4
    assert ah.nif_bounding_box(box_nif(*CRR, name=b"BOUNDING BOX", props=2)) is not None    # any case; properties
    assert ah.nif_bounding_box(box_nif()) is None                       # no Bounding Box node: not judged
    assert ah.nif_bounding_box(box_nif(*CRR, has=0)) is None            # a node without a box
    assert ah.nif_bounding_box(b"not a model") is None


def test_cliff_racer_remastered_box_divides_by_zero_and_the_old_one_does_not():
    d = ah.actor_box_divisors(ah.nif_bounding_box(box_nif(*CRR)))
    assert d["raw_w"] == 8 and d["div_w"] == 0                          # 0.262 units: the crash in the dump
    assert ah.actor_box_problem(ah.nif_bounding_box(box_nif(*CRR))).startswith("0.262 units wide")
    d = ah.actor_box_divisors(ah.nif_bounding_box(box_nif(*PB)))
    assert d["raw_w"] == 2432 and d["div_w"] == 38 and d["div_h"] > 0   # 76.02 units
    assert ah.actor_box_problem(ah.nif_bounding_box(box_nif(*PB))) is None


def test_the_limits_are_two_units_wide_and_one_and_a_quarter_high():
    box = (lambda w, h: ((0.0, 0.0, 0.0), (1.0, w, h / 2)))
    assert ah.actor_box_problem(box(2.0, 50)) is None                    # raw 64: divisor 1
    assert "wide" in ah.actor_box_problem(box(1.99, 50))
    assert ah.actor_box_problem(box(50, 1.25)) is None                   # raw 40 * 0.03125 * 0.8f: 1
    assert "high" in ah.actor_box_problem(box(50, 1.2))
    assert ah.actor_box_problem(box(0.0, 0.0)).count("units") == 2


def test_a_negative_width_wraps_and_does_not_crash_but_nan_does():
    d = ah.actor_box_divisors(((0.0, -18.0, 17.0), (5.0, 5.0, 17.0)))  # abot's bee: -13 units
    assert d["raw_w"] == (-416) & 0xFFFF and d["div_w"] > 0
    assert ah.actor_box_problem(((0.0, -18.0, 17.0), (5.0, 5.0, 17.0))) is None
    assert ah.actor_box_problem(((0.0, float("nan"), 0.0), (0.0, 0.0, 50.0))) is not None
    assert ah.actor_box_problem(((0.0, 2048.0, 0.0), (0.0, 1.0, 50.0))) is not None   # wraps back under 64


# ---------------------------------------------------------------- the check: the deployed copy of each actor model
def _world(models):
    return types.SimpleNamespace(models={k: v for k, v in models.items()})


def _assets(data, rels, bsas=()):
    loose = {r.lower(): str(data / "Meshes" / r) for r in rels}
    return types.SimpleNamespace(mesh_loose=loose, bsa_paths=list(bsas), norm=DT.ModelAssets.norm)


def _put(data, rel, b):
    p = data / "Meshes" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b)
    return p


def test_check_flags_the_deployed_actor_model_and_its_x_twin(tmp_path):
    data = tmp_path / "Data Files"
    _put(data, "r\\cliffracer.nif".replace("\\", os.sep), box_nif(*CRR))
    _put(data, "r\\xcliffracer.nif".replace("\\", os.sep), box_nif(*CRR))
    _put(data, "r\\fine.nif".replace("\\", os.sep), box_nif(*PB))
    _put(data, "o\\statue.nif".replace("\\", os.sep), box_nif(*CRR))       # a static: never judged
    rels = ["r\\cliffracer.nif", "r\\xcliffracer.nif", "r\\fine.nif", "o\\statue.nif"]
    A = _assets(data, [])
    A.mesh_loose = {r: str(data / "Meshes" / r.replace("\\", os.sep)) for r in rels}
    world = _world({
        ("CREA", "cliff racer"): [(0, "Morrowind.esm", {("MODL", "mesh"): "r\\CliffRacer.NIF"}, False, "cliff racer")],
        ("CREA", "guar"): [(0, "Morrowind.esm", {("MODL", "mesh"): "r\\Fine.nif"}, False, "guar")],
        ("CREA", "gone"): [(0, "a.esp", {("MODL", "mesh"): "r\\cliffracer.nif"}, True, "gone")],
        ("STAT", "statue"): [(0, "a.esp", {("MODL", "mesh"): "o\\statue.nif"}, False, "statue")],
    })
    ah.BROKEN_MODELS.clear()
    found, fixes = ah.actor_box_check(world, A, str(data))
    assert sorted(os.path.basename(f[2]).lower() for f in fixes) == ["cliffracer.nif", "xcliffracer.nif"]
    assert all(f[0] == "actorbox" and "0.262 units wide" in f[3] for f in fixes)
    assert all(not os.path.isabs(f[2]) and f[2].lower().startswith("meshes") for f in fixes)
    assert [s for s, _r, _t in found] == ["ERROR", "ERROR"]
    assert "cliff racer" in found[0][2] and "Off\\<plugin>\\broken\\" in found[0][2]
    assert len(ah.BROKEN_MODELS) == 2
    ah.BROKEN_MODELS.clear()


def test_a_losing_copy_is_not_judged_only_the_winner(tmp_path, monkeypatch):
    # the winner is whatever WinningFiles says the game loads; here a BSA copy with a bad box: report only
    data = tmp_path / "Data Files"
    bsa = tmp_path / "Data Files" / "Mod.bsa"
    bsa.parent.mkdir(parents=True)
    bad = box_nif(*CRR)
    bsa.write_bytes(b"\0" * 10 + bad)

    class Winner:
        def __init__(self, *a, **k):
            pass

        def names(self):
            return {"r\\cliffracer.nif"}

        def winner(self, rel):
            return ("bsa", (str(bsa), 10, len(bad)))
    monkeypatch.setattr(ah, "WinningFiles", Winner)
    world = _world({("CREA", "cliff racer"): [(0, "Morrowind.esm", {("MODL", "mesh"): "r\\cliffracer.nif"}, False,
                                               "cliff racer")]})
    found, fixes = ah.actor_box_check(world, _assets(data, []), str(data))
    assert fixes == [] and len(found) == 1 and found[0][0] == "WARN" and "Mod.bsa" in found[0][2]


def test_a_good_winner_means_nothing_to_do(tmp_path):
    data = tmp_path / "Data Files"
    _put(data, os.path.join("r", "xcliffracer.nif"), box_nif(*PB))          # the local fix wins: a pass
    A = _assets(data, [])
    A.mesh_loose = {"r\\xcliffracer.nif": str(data / "Meshes" / "r" / "xcliffracer.nif")}
    world = _world({("CREA", "cliff racer"): [(0, "a.esp", {("MODL", "mesh"): "r\\CliffRacer.NIF"}, False, "c")]})
    assert ah.actor_box_check(world, A, str(data)) == ([], [])


# ---------------------------------------------------------------- --fix: out of Data Files, into Off\<plugin>\broken\
def test_fix_moves_the_staged_copy_to_off_broken_and_unlinks_data_files(tmp_path, monkeypatch):
    game = tmp_path / "game"
    data = game / "Data Files"
    mod = tmp_path / "staging" / "Cliff Racer Remastered"
    rel = os.path.join("Meshes", "r", "xcliffracer.nif")
    (mod / "Meshes" / "r").mkdir(parents=True)
    (mod / rel).write_bytes(box_nif(*CRR))
    (data / "Meshes" / "r").mkdir(parents=True)
    os.link(mod / rel, data / rel)                                      # Vortex's hard link
    monkeypatch.setattr(m, "asset_owner_folder", lambda d, r: (str(mod), "Cliff Racer Remastered"))
    fixes = [("actorbox", str(data / rel), rel, "Bounding Box 0.262 units wide")]
    log = []
    msg = ah.apply(fixes, str(data), str(game), m, log, dry=True)
    assert msg.startswith("Dry run") and "1 actor model(s)" in msg
    assert (mod / rel).exists() and (data / rel).exists()               # a dry run changes nothing
    msg = ah.apply(fixes, str(data), str(game), m, log)
    dest = m.off_dest(str(mod), "broken", "Cliff Racer Remastered", rel)
    assert "1 actor model(s)" in msg
    assert not (data / rel).exists() and not (mod / rel).exists()       # the next copy (or the BSA's) is used
    assert open(dest, "rb").read() == box_nif(*CRR)
    assert os.sep + "broken" + os.sep in dest and os.sep + "Off" + os.sep in dest
    record = (game / ah.UNUSED_RECORD).read_text(encoding="utf-8")
    assert rel in record and dest in record                             # --restore-unused can put it back
    ah.restore_unused(str(game), str(data))
    assert (mod / rel).read_bytes() == box_nif(*CRR) and (data / rel).exists()


def test_fix_without_a_vortex_owner_keeps_it_in_the_backups(tmp_path, monkeypatch):
    game = tmp_path / "game"
    data = game / "Data Files"
    rel = os.path.join("Meshes", "r", "xcliffracer.nif")
    (data / "Meshes" / "r").mkdir(parents=True)
    (data / rel).write_bytes(box_nif(*CRR))
    monkeypatch.setattr(m, "asset_owner_folder", lambda d, r: (None, None))
    monkeypatch.setattr(ah.MB, "backup_root", lambda g: str(tmp_path / "bk"))
    ah.apply([("actorbox", str(data / rel), rel, "why")], str(data), str(game), m, [])
    assert not (data / rel).exists()
    assert (tmp_path / "bk" / "asset_originals" / "broken" / rel).read_bytes() == box_nif(*CRR)


# ---------------------------------------------------------------- the staging search skips what was quarantined
def test_staging_search_never_offers_a_quarantined_file(tmp_path):
    st = tmp_path / "staging"
    nif = box_nif(*PB)
    for p in ("A/Off/A/broken/Meshes/xcliffracer.nif",          # Off\<plugin>\broken\
              "B/Off/broken/B/Meshes/xcliffracer.nif",          # the older Off\broken\<plugin>\
              "C/Extras/C/BROKEN/Meshes/xcliffracer.nif",       # Extras, any case
              "D/Off/D/unused assets/Meshes/kept.nif",          # other Off reasons: still found
              "E/Meshes/real.nif"):                               # an ordinary deployable copy: still found
        f = st / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(nif)
    repo = DT.VortexRepo(str(st))
    assert repo.find("meshes", "xcliffracer.nif") is None
    assert repo.find("meshes", "kept.nif")[1] == "D"
    assert repo.find("meshes", "real.nif")[1] == "E"
    good = st / "F" / "Extras" / "F" / "Meshes" / "xcliffracer.nif"
    good.parent.mkdir(parents=True)
    good.write_bytes(nif)
    hit = DT.VortexRepo(str(st)).find("meshes", "xcliffracer.nif")
    assert hit is not None and hit[1] == "F"


def test_quarantined_paths():
    q = DT.VortexRepo.quarantined
    assert q("Off\\Mod\\broken") and q("off/broken/Mod/meshes") and q("EXTRAS\\x\\Broken\\y")
    assert not q(".") and not q("Off\\Mod\\unused assets") and not q("Meshes\\broken") and not q("broken")
