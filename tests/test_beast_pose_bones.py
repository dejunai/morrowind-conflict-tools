"""Beast bones in a mod's pose model (rule approved by dej / dejunai, 2026-11-26): beast-race NPCs left alone
with a mod's pose model get a Multipatch copy of the pose with the beast bones it lacks grafted from the beast
skeleton. Tiny synthetic 4.0.0.2 models only; no game files."""
import argparse
import os
import struct

from conftest import fold, m, plugin
from test_beast_skeleton import BASE, modl, npc

import mwdialog_multipatch as MP
import mwdialog_footing as NB
from mwdialog_footing import nif_triangles


def _s(text):
    return struct.pack("<I", len(text)) + text


def _block(kind, name, kids=(), t=(0.0, 0.0, 0.0), flags=0xC):
    head = _s(kind) + _s(name) + struct.pack("<iiH", -1, -1, flags) + \
        struct.pack("<13f", *t, 1, 0, 0, 0, 1, 0, 0, 0, 1, 1) + struct.pack("<3f", 0, 0, 0) + struct.pack("<II", 0, 0)
    if kind == b"NiTriShape":
        return head + struct.pack("<ii", -1, -1)
    return head + struct.pack(f"<I{len(kids)}i", len(kids), *kids) + struct.pack("<I", 0)


def skel(tree):
    """tree: (name, [children], kind?, translation?) -> model bytes; blocks numbered depth first."""
    blocks = []

    def add(t):
        name, kids = t[0], t[1]
        kind = t[2] if len(t) > 2 else b"NiNode"
        tr = t[3] if len(t) > 3 else (0.0, 0.0, 0.0)
        i = len(blocks)
        blocks.append(None)
        refs = [add(k) for k in kids]
        blocks[i] = _block(kind, name, refs, tr)
        return i
    add(tree)
    return NB.NIF_HEADER + struct.pack("<II", NB.NIF_VERSION, len(blocks)) + b"".join(blocks) + struct.pack("<Ii", 1, 0)


def legs(beast):
    toe = lambda side: [(b"Bip01 %s Toe0" % side, [], b"NiNode", (6.5, 20.25, 0.0))] if beast else []
    return [(b"Bip01 L Foot", toe(b"L")), (b"Bip01 R Foot", toe(b"R"))]


def spine(beast):
    tail = [(b"Bip01 Tail", [(b"Bip01 Tail1", [], b"NiNode", (18.0, 0.0, 0.0)),
                             (b"Tail", [(b"Tri Tail", [], b"NiTriShape")])], b"NiNode", (-3.5, -4.25, 0.0))]
    return (b"Bip01 Spine", legs(beast) + (tail if beast else []))


REF = skel((b"base_animKnA.nif", [(b"Bip01", [spine(True)])]))
HUMAN = skel((b"base_anim.nif", [(b"Bip01", [spine(False)])]))
POSE_HUMAN = skel((b"sit.nif", [(b"Bip01", [spine(False)])]))       # a pose made on the humanoid skeleton
POSE_FULL = skel((b"sit.nif", [(b"Bip01", [spine(True)])]))
KF = b"NetImmerse File Format, Version 4.0.0.2\nkeyframes"
NEED = {"bip01 l toe0", "bip01 r toe0", "bip01 tail", "bip01 tail1", "tail"}


def reader(files):
    return lambda rel: files.get(rel.lower())


def test_fixture_reads_like_the_game_models():
    for data in (REF, HUMAN, POSE_HUMAN):
        info = NB.read_nif(data)
        assert info["count"] == len(info["blocks"]) and info["roots"] == [0]
        assert nif_triangles(data) is not None       # the footing reader agrees on the layout


def test_beast_bones_come_from_the_two_skeletons():
    assert MP.beast_bones(reader({"base_animkna.nif": REF, "base_anim.nif": HUMAN})) == NEED
    assert MP.beast_bones(reader({"base_animkna.nif": REF})) is None


def test_missing_toes_and_tail_are_grafted_at_the_right_parents():
    original = bytes(POSE_HUMAN)
    new, grafted = NB.graft_bones(POSE_HUMAN, REF, NEED)
    assert POSE_HUMAN == original                    # the input is never changed
    assert sorted(g.lower() for g in grafted) == sorted(NEED)
    info, ref = NB.read_nif(new), NB.read_nif(REF)
    sk, rs = NB.skeleton(info), NB.skeleton(ref)
    assert info["count"] == NB.read_nif(POSE_HUMAN)["count"] + 5
    for b in NEED:
        i, par = sk[b]
        ri, rpar = rs[b]
        assert info["nodes"][par]["name"] == ref["nodes"][rpar]["name"]
        assert info["nodes"][i]["transform"] == ref["nodes"][ri]["transform"]   # bind transform
        assert info["nodes"][i]["name"] == ref["nodes"][ri]["name"]           # spelt as the skeleton has it
    assert "tri tail" not in sk                      # bones only, never the skeleton's meshes
    assert nif_triangles(new) is not None
    again, more = NB.graft_bones(new, REF, NEED)     # round trip: nothing left to add
    assert more == [] and again == new


def test_complete_skeleton_is_left_alone():
    new, grafted = NB.graft_bones(POSE_FULL, REF, NEED)
    assert grafted == [] and new == POSE_FULL


def test_unreadable_model_raises():
    try:
        NB.graft_bones(b"not a model", REF, NEED)
    except NB.NifError:
        return
    raise AssertionError("no NifError")


def load(tmp_path, files):
    out = []
    for name, recs in files:
        p = str(tmp_path / name)
        plugin(p, [] if name.endswith(".esm") else [("Morrowind.esm", 0)], recs)
        out.append((name, p))
    return out


def poses_of(tmp_path, *files):
    poses = []
    MP.beast_skeleton_fixes(load(tmp_path, [BASE, *files]), None, poses)
    return poses


MODELS = {"base_animkna.nif": REF, "base_anim.nif": HUMAN, "mymod\\sit.nif": POSE_HUMAN,
          "mymod\\xsit.nif": POSE_HUMAN, "mymod\\xsit.kf": KF, "mymod\\full.nif": POSE_FULL}


def test_beast_npc_gets_the_copy_and_humanoids_keep_the_original(tmp_path):
    poses = poses_of(tmp_path, ("Sitters.esp", [npc("kha_sit", "Khajiit", "mymod\\sit.nif"),
                                                npc("dunmer_sit", "Dark Elf", "mymod\\sit.nif")]))
    assert [p["id"] for p in poses] == ["kha_sit"]  # humanoids never get here
    fixes, report = MP.beast_pose_fixes(poses, reader(MODELS))
    assert len(fixes) == 1 and fixes[0]["id"] == "kha_sit"
    f = fixes[0]
    assert f["after"] == "mwdialog_beastpose\\mymod\\sit_animkna.nif" and modl(f["record"]) == f["after"]
    assert MP.is_beast_skeleton(f["after"])          # next time the copy counts as a beast skeleton
    assert set(f["files"]) == {"mwdialog_beastpose\\mymod\\sit_animkna.nif",
                               "mwdialog_beastpose\\mymod\\xsit_animkna.nif",
                               "mwdialog_beastpose\\mymod\\xsit_animkna.kf"}
    assert f["files"]["mwdialog_beastpose\\mymod\\xsit_animkna.kf"] == KF     # the animation, unchanged
    assert sorted(g.lower() for g in f["grafted"]["mwdialog_beastpose\\mymod\\xsit_animkna.nif"]) == sorted(NEED)
    assert report["mymod\\sit.nif"]["lacks"] == sorted(NEED) and report["mymod\\sit.nif"]["npcs"] == 1


def test_the_drawn_x_file_decides(tmp_path):
    """The game draws x<name>.nif when there is one: a complete x-file means nothing to do, even when the
    editor's file lacks bones."""
    poses = poses_of(tmp_path, ("A.esp", [npc("arg_sit", "Argonian", "mymod\\sit.nif")]))
    files = dict(MODELS, **{"mymod\\xsit.nif": POSE_FULL})
    fixes, report = MP.beast_pose_fixes(poses, reader(files))
    assert fixes == [] and report["mymod\\sit.nif"]["note"] == "has every beast bone"


def test_complete_pose_and_animkna_skeletons_are_left_alone(tmp_path):
    poses = poses_of(tmp_path, ("A.esp", [npc("full", "Khajiit", "mymod\\full.nif"),
                                          npc("own", "Khajiit", "mymod\\base_animkna_sit.nif"),
                                          npc("ours", "Khajiit", "mwdialog_beastpose\\mymod\\sit_animkna.nif")]))
    assert [p["id"] for p in poses] == ["full"]      # 'animkna' in the name: already a beast skeleton
    fixes, report = MP.beast_pose_fixes(poses, reader(MODELS))
    assert fixes == [] and report["mymod\\full.nif"]["lacks"] == []


def test_without_the_skeletons_nothing_is_done(tmp_path):
    poses = poses_of(tmp_path, ("A.esp", [npc("kha_sit", "Khajiit", "mymod\\sit.nif")]))
    assert MP.beast_pose_fixes(poses, reader({"mymod\\sit.nif": POSE_HUMAN})) == ([], {})


def test_actor_model_names():
    assert MP.actor_model_names("Meshes\\AM\\II\\Cleaner.nif") == ("am\\ii\\cleaner.nif", "am\\ii\\xcleaner.nif",
                                                                   "am\\ii\\xcleaner.kf")
    assert MP.actor_model_names("va_sitting.nif") == ("va_sitting.nif", "xva_sitting.nif", "xva_sitting.kf")


def _game(tmp_path):
    df = tmp_path / "Data Files"
    for rel, data in MODELS.items():
        p = df / "Meshes" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    plugin(str(df / "Morrowind.esm"), [], BASE[1])
    plugin(str(df / "Sitters.esp"), [("Morrowind.esm", 0)],
           [npc("kha_sit", "Khajiit", "mymod\\sit.nif"), npc("dunmer_sit", "Dark Elf", "mymod\\sit.nif")])
    return df, [("Morrowind.esm", str(df / "Morrowind.esm")), ("Sitters.esp", str(df / "Sitters.esp"))]


def _run(tmp_path, monkeypatch, dry=False, **extra):
    df, plugins = _game(tmp_path)
    got = {}
    monkeypatch.setattr(m, "write_patch", lambda path, *a, extra=(), **k: got.setdefault("recs", list(extra)))
    monkeypatch.setattr(MP, "write_patch", lambda path, *a, extra=(), **k: got.setdefault("recs", list(extra)))
    monkeypatch.setattr(MP, "next_free_date", lambda *a, **k: None)
    monkeypatch.setattr(MP, "read_load_order", lambda *a, **k: [])
    monkeypatch.setattr(MP, "merged_objects", lambda *a, **k: ([], []))
    args = argparse.Namespace(dry_run=dry, data_dir=str(df), fix_log=str(tmp_path / "log.txt"),
                              no_merge_objects=True, ini=None, **extra)
    MP.run_multipatch(args, plugins, m.World(m.Report()))
    return df, got.get("recs", [])


def _snapshot(df):
    out = {}
    for root, _d, files in os.walk(df):
        for f in files:
            p = os.path.join(root, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, df)] = fh.read()
    return out


def test_multipatch_writes_the_copy_and_never_the_original(tmp_path, monkeypatch):
    df, recs = _run(tmp_path, monkeypatch)
    npcs = {m.cstr(dict(m.iter_subs(r[16:]))["NAME"]): modl(r) for r in recs if r[:4] == b"NPC_"}
    assert npcs == {"kha_sit": "mwdialog_beastpose\\mymod\\sit_animkna.nif"}    # the Dunmer keeps sit.nif
    copy = df / "Meshes" / "mwdialog_beastpose" / "mymod"
    assert sorted(p.name for p in copy.iterdir()) == ["sit_animkna.nif", "xsit_animkna.kf", "xsit_animkna.nif"]
    assert (df / "Meshes" / "mymod" / "sit.nif").read_bytes() == POSE_HUMAN
    assert (df / "Meshes" / "mymod" / "xsit.nif").read_bytes() == POSE_HUMAN
    assert NB.bone_names((copy / "xsit_animkna.nif").read_bytes()) >= NEED
    record = (tmp_path / "mwdialog_generated_files.txt").read_text(encoding="utf-8")
    assert "[mwdialog_check Multipatch.esp]" in record and "meshes\\mwdialog_beastpose\\mymod\\xsit_animkna.nif" in record
    assert "pose with the beast bones" in (tmp_path / "log.txt").read_text(encoding="utf-8")


def test_dry_run_lists_the_copies_and_writes_nothing(tmp_path, monkeypatch, capsys):
    df, plugins = _game(tmp_path)
    before = _snapshot(df)
    monkeypatch.setattr(MP, "write_patch", lambda *a, **k: (_ for _ in ()).throw(AssertionError("wrote")))
    monkeypatch.setattr(MP, "merged_objects", lambda *a, **k: ([], []))
    args = argparse.Namespace(dry_run=True, data_dir=str(df), fix_log=str(tmp_path / "log.txt"),
                              no_merge_objects=True, ini=None)
    MP.run_multipatch(args, plugins, m.World(m.Report()))
    out = fold(capsys.readouterr().out)
    assert "1 using 1 pose file(s); 0 have every beast bone, 1 lack some" in out
    assert "pose mymod\\sit.nif: 1 beast NPC(s), bones grafted (lacks bip01 l toe0" in out
    assert "kha_sit (khajiit) 'mymod\\sit.nif' -> 'mwdialog_beastpose\\mymod\\sit_animkna.nif'" in out
    assert "would write Meshes\\mwdialog_beastpose\\mymod\\xsit_animkna.nif: grafted" in out
    assert "would write Meshes\\mwdialog_beastpose\\mymod\\xsit_animkna.kf (copied)" in out
    assert _snapshot(df) == before and not (tmp_path / "mwdialog_generated_files.txt").exists()


def test_no_beast_skeleton_switch_skips_the_poses_too(tmp_path, monkeypatch):
    df, recs = _run(tmp_path, monkeypatch, no_beast_skeleton=True)
    assert not [r for r in recs if r[:4] == b"NPC_"]
    assert not (df / "Meshes" / "mwdialog_beastpose").exists()