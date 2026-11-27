"""--asset-check reads every model the game can load (each loose file under Meshes and each BSA copy), not only
the ones records name, and gives every texture it names that the game can't find a stand-in: the x-prefixed
twin a creature is drawn with (r\\XCliffRacer.NIF), normal maps named by bare file name (XNetch_Bull.NIF), and
textures found the way the game looks them up. Credit: dej (dejunai)."""
import os
import struct

from conftest import m
import mwdialog_media as MD


def _nif(*names):
    """A minimal model naming these textures (length-prefixed strings, as in a NiSourceTexture)."""
    b = b"NetImmerse File Format, Version 4.0.0.2\n" + struct.pack("<I", 0x04000002)
    for n in names:
        b += struct.pack("<I", len(n)) + n.encode() + b"\x01\x00\x00\x00"
    return b


def _bsa(files):
    c = len(files)
    names = b"".join(n.encode() + b"\0" for n, _d in files)
    noffs, o = [], 0
    for n, _d in files:
        noffs.append(o)
        o += len(n) + 1
    so, doff = b"", 0
    for _n, d in files:
        so += struct.pack("<II", len(d), doff)
        doff += len(d)
    dir_ = so + struct.pack(f"<{c}I", *noffs) + names
    return struct.pack("<III", 0x100, len(dir_), c) + dir_ + b"\0" * 8 * c + b"".join(d for _n, d in files)


def _put(df, rel, b):
    p = df.joinpath(*rel.split("\\"))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b)


def _world(df, bsas=(), vortex=None):
    w = m.World(m.Report())
    w.assets = m.ModelAssets([str(df)], [str(b) for b in bsas])
    w.vortex = vortex
    return w


def _gen(w):
    return {g[0].replace("/", "\\").lower(): g for g in w.generated}


def test_the_x_twin_and_bare_normal_maps_get_stand_ins_without_any_record(tmp_path):
    df = tmp_path / "Data Files"
    _put(df, "Meshes\\r\\cliffracer.nif", _nif("TX_Cliffracer_head_00.dds"))
    _put(df, "Meshes\\r\\xcliffracer.nif", _nif("textures\\betcreat\\tx_cliffracer_feather_nm.dds",
                                                 "textures\\betcreat\\tx_cliffracer_head_nm.dds",
                                                 "textures\\tx_cliffracer_head_00.dds"))
    _put(df, "Meshes\\r\\xnetch_bull.nif", _nif("TX_Creature_Netchi_01.tga", "tx_creature_netchi_01_nrm.dds",
                                                "textures\\tx_creature_netch_04a_nrm.dds"))
    _put(df, "Textures\\tx_cliffracer_head_00.dds", b"DDS ")
    _put(df, "Textures\\betcreat\\tx_cliffracer_head_nm.dds", b"DDS ")
    _put(df, "Textures\\tx_creature_netchi_01.dds", b"DDS ")       # the .tga the model names, as .dds
    w = _world(df)
    w._deployed_mesh_textures()
    g = _gen(w)
    assert set(g) == {"textures\\betcreat\\tx_cliffracer_feather_nm.dds", "textures\\tx_creature_netchi_01_nrm.dds",
                      "textures\\tx_creature_netch_04a_nrm.dds"}
    assert all(x[2] is None for x in g.values())                     # placeholders: no copy anywhere
    assert "r\\xcliffracer.nif" in g["textures\\betcreat\\tx_cliffracer_feather_nm.dds"][1]
    assert ("Meshes\\r\\xnetch_bull.nif", "tx_creature_netchi_01_nrm.dds") in w.assets.ignored_normals
    infos = [i for i in w.r.issues if i[0] == "INFO" and "tex not found" in i[-1]]
    assert len(infos) == 1 and "2 model(s)" in infos[0][-1] and "3 texture(s)" in infos[0][-1]


def test_the_placeholder_for_a_normal_map_is_flat():
    # what --fix writes for a texture with no copy anywhere (stand_in_bytes): flat for *_nm / *_nrm
    for rel in ("textures\\betcreat\\tx_cliffracer_feather_nm.dds", "textures\\tx_creature_netchi_01_nrm.dds"):
        data = MD.stand_in_bytes(rel)
        assert data[:4] == b"DDS " and data[-4:] == bytes((255, 128, 128, 255))


def test_textures_are_found_the_way_the_game_finds_them(tmp_path):
    df = tmp_path / "Data Files"
    _put(df, "Meshes\\a.nif", _nif("textures\\sub\\root.tga", "textures\\sub\\deep.dds", "sub\\swap.tga",
                                   "textures\\sub\\bsa.dds"))
    _put(df, "Textures\\root.dds", b"DDS ")              # same name directly under Textures: found
    _put(df, "Textures\\other\\deep.dds", b"DDS ")       # same name in another subfolder: the game never looks
    _put(df, "Textures\\sub\\swap.dds", b"DDS ")         # .tga named, .dds there: found
    b = tmp_path / "Data Files" / "x.bsa"
    b.write_bytes(_bsa([("textures\\sub\\bsa.dds", b"DDS ")]))
    w = _world(df, bsas=[b])
    assert w._texture_found_by_game("sub\\root.tga") and w._texture_found_by_game("sub\\swap.tga")
    assert w._texture_found_by_game("sub\\bsa.dds") and not w._texture_found_by_game("sub\\deep.dds")
    w._deployed_mesh_textures()
    assert set(_gen(w)) == {"textures\\sub\\deep.dds"}


def test_models_inside_a_bsa_are_read_too(tmp_path):
    df = tmp_path / "Data Files"
    df.mkdir()
    b = df / "Mod.bsa"
    b.write_bytes(_bsa([("meshes\\c\\x.nif", _nif("tx_gone_n.dds", "tx_here.dds")), ("textures\\tx_here.dds", b"D")]))
    w = _world(df, bsas=[b])
    w._deployed_mesh_textures()
    g = _gen(w)
    assert set(g) == {"textures\\tx_gone_n.dds"} and g["textures\\tx_gone_n.dds"][3] == "Mod.bsa"


def test_one_stand_in_per_texture_and_none_already_planned(tmp_path):
    df = tmp_path / "Data Files"
    _put(df, "Meshes\\a.nif", _nif("tx_shared_nm.dds", "tx_planned.dds"))
    _put(df, "Meshes\\b.nif", _nif("tx_shared_nm.dds"))
    w = _world(df)
    w.generated.append((os.path.join("Textures", "tx_planned.dds"), "a record's model", None, "x.esp", None))
    w._deployed_mesh_textures()
    rels = [g[0].replace("/", "\\").lower() for g in w.generated]
    assert rels.count("textures\\tx_shared_nm.dds") == 1 and rels.count("textures\\tx_planned.dds") == 1


def test_a_copy_in_a_vortex_folder_is_used_but_never_a_normal_map_tidy_put_in_off(tmp_path):
    df = tmp_path / "Data Files"
    _put(df, "Meshes\\a.nif", _nif("tx_wood.dds", "tx_wood_nm.dds"))
    st = tmp_path / "staging"
    _put(st, "Wood\\Textures\\tx_wood.dds", b"DDS real")
    _put(st, "Wood\\Off\\normal maps\\Wood\\Textures\\tx_wood_nm.dds", b"DDS nm")
    w = _world(df, vortex=m.VortexRepo(str(st)))
    w._deployed_mesh_textures()
    g = _gen(w)
    assert g["textures\\tx_wood.dds"][2].endswith("tx_wood.dds")
    assert g["textures\\tx_wood_nm.dds"][2] is None   # flat placeholder, not the Off copy


def test_nothing_missing_means_nothing_planned(tmp_path):
    df = tmp_path / "Data Files"
    _put(df, "Meshes\\a.nif", _nif("tx_a.dds"))
    _put(df, "Textures\\tx_a.dds", b"DDS ")
    w = _world(df)
    w._deployed_mesh_textures()
    assert w.generated == [] and not [i for i in w.r.issues if "tex not found" in i[-1]]
