"""Door ownership report (OWNERSHIP_REPAIR.md, step 1): a door owned by someone who isn't placed behind it is
reported, with a guess (public place, the one resident); deliberate owners are left alone. Report only."""
import struct

from conftest import m, plugin, rec, sub, z


def npc(id_, name, cls="commoner"):
    return rec("NPC_", sub("NAME", z(id_)) + sub("FNAM", z(name)) + sub("CNAM", z(cls)))


def door(id_):
    return rec("DOOR", sub("NAME", z(id_)) + sub("MODL", z("d\\door.nif")))


def cell(name, *refs, x=None, y=0):
    flags, gx = (1, 0) if x is None else (0, x)
    return rec("CELL", sub("NAME", z(name)) + sub("DATA", struct.pack("<Iii", flags, gx, y)) + b"".join(refs))


def ref(n, obj, owner=None, faction=None, dest=None):
    b = sub("FRMR", struct.pack("<I", n)) + sub("NAME", z(obj)) + sub("DATA", struct.pack("<6f", 0, 0, 0, 0, 0, 0))
    b += sub("ANAM", z(owner)) if owner else b""
    b += sub("CNAM", z(faction)) if faction else b""
    b += sub("DNAM", z(dest)) if dest else b""
    return b


BASE = [npc("vendor", "Vendor", "publican"), npc("hermit", "Hermit"), npc("kalir", "Kalir"),
        npc("ghost", "Ghost"), door("zz_door"),
        cell("Far Town, Hut", ref(1, "hermit")), cell("Town, Tavern", ref(2, "vendor")),
        cell("Town, Home", ref(3, "kalir")), cell("Town, Shed"), npc("smuggler", "Smuggler"),
        cell("Holding Cell", ref(4, "smuggler")), cell("Far Town, Gate", ref(5, "zz_door", dest="Far Town, Hut"))]


def warnings(tmp_path, esm_refs=(), esp_refs=(), esp_x=0):
    df = tmp_path / "Data Files"
    df.mkdir()
    plugin(df / "Morrowind.esm", [], BASE + ([cell("", *esm_refs, x=5)] if esm_refs else []))
    plugin(df / "Mod.esp", [("Morrowind.esm", (df / "Morrowind.esm").stat().st_size)],
           [cell("", *esp_refs, x=esp_x)] if esp_refs else [])
    w = m.World(m.Report())
    w.file_sizes, w.trace = {}, set()
    for n in ("Morrowind.esm", "Mod.esp"):
        w.load_plugin(str(df / n), n)
    w._check_ownership()
    return [(i[1], i[-1]) for i in w.r.issues if "is owned by" in i[-1]]


def test_a_public_door_owned_by_a_stranger_is_reported(tmp_path):
    ((_p, msg),) = warnings(tmp_path, esp_refs=[ref(10, "zz_door", owner="hermit", dest="Town, Tavern")])
    assert "'hermit'" in msg and "public place" in msg


def test_a_home_door_names_its_one_resident(tmp_path):
    ((_p, msg),) = warnings(tmp_path, esp_refs=[ref(10, "zz_door", owner="hermit", dest="Town, Home")])
    assert "'kalir': --fix gives it to them" in msg


def test_an_owner_that_is_no_npc_is_reported(tmp_path):
    ((_p, msg),) = warnings(tmp_path, esp_refs=[ref(10, "zz_door", owner="census and excise", dest="Town, Home")])
    assert "no NPC" in msg


def test_deliberate_owners_are_left_alone(tmp_path):
    assert warnings(tmp_path, esp_refs=[
        ref(10, "zz_door", owner="kalir", dest="Town, Home"),           # lives there
        ref(11, "zz_door", owner="ghost", dest="Town, Shed"),           # placed nowhere: a theft-blocker
        ref(14, "zz_door", owner="smuggler", dest="Town, Shed"),        # only in a cell no door leads to
        ref(12, "zz_door", faction="fighters guild", dest="Town, Shed"),  # faction owner
        ref(13, "zz_door", owner="kalir", dest="Kalir's Shed"),         # named in the destination
    ]) == []


def test_an_official_masters_own_owner_is_left_alone(tmp_path):
    assert warnings(tmp_path, esm_refs=[ref(10, "zz_door", owner="hermit", dest="Town, Home")]) == []


def test_a_plugin_changing_a_vanilla_owner_is_reported(tmp_path):
    (found,) = warnings(tmp_path, esm_refs=[ref(10, "zz_door", owner="kalir", dest="Town, Home")],
                        esp_refs=[ref((1 << 24) | 10, "zz_door", owner="hermit", dest="Town, Home")], esp_x=5)
    assert found[0] == "Mod.esp"


def test_fix_changes_clear_doors_in_the_cell_fixes_patch_and_lists_the_rest(tmp_path):
    g = tmp_path / "Morrowind"
    df = g / "Data Files"
    df.mkdir(parents=True)
    (g / "Morrowind.ini").write_text("[Game Files]\n")
    plugin(df / "Morrowind.esm", [], BASE + [npc("hand1", "Ann"), npc("hand2", "Bob"), rec("CONT", sub("NAME", z("zz_chest"))),
                                             cell("Town, Barn", ref(6, "hand1"), ref(7, "hand2"))])
    plugin(df / "Mod.esp", [("Morrowind.esm", (df / "Morrowind.esm").stat().st_size)], [cell("", *[
        ref(10, "zz_door", owner="hermit", dest="Town, Tavern"),   # public: owner off
        ref(11, "zz_door", owner="hermit", dest="Town, Home"),     # one resident: kalir's
        ref(12, "zz_door", owner="vendor", dest="Town, Barn"),     # two people there: left
    ], x=0), cell("Town, Home", ref(20, "zz_chest", owner="hermit")),   # kalir's now
             cell("Town, Barn", ref(21, "zz_chest", owner="hermit"))])      # two people there: left
    m.main([str(df), "--plugins", "Morrowind.esm", "Mod.esp", "--no-vortex", "--no-archive-lookup", "--fix",
            "--yes", "--fix-log", str(g / "mwdialog_fixes.log")])
    owners, chests = {}, []
    for _o, t, _f, body in m.iter_records((df / m.CELL_WINNER_PATCH).read_bytes()):
        if t == "CELL":
            for blk in m.split_cell(body, 0)[1] + m.split_cell(body, 0)[3]:
                d = dict(blk)
                if "DNAM" in d:
                    owners[m.cstr(d["DNAM"])] = m.cstr(d["ANAM"]) if "ANAM" in d else ""
                else:
                    chests.append(m.cstr(d["ANAM"]))
    assert owners == {"Town, Tavern": "", "Town, Home": "kalir"} and chests == ["kalir"]
    listed = (g / m.DOOR_OWNERS_LIST).read_text(encoding="utf-8")
    assert listed.count("CHANGED") == 3 and listed.count("LEFT") == 2 and "cell town, barn" in listed
    log = (g / "mwdialog_fixes.log").read_text(encoding="utf-8")
    assert log.count("door owner:") == 2 and log.count(": owner:") == 1


def test_containers_owned_by_someone_elsewhere_are_reported_once_per_cell(tmp_path):
    df = tmp_path / "Data Files"
    df.mkdir()
    plugin(df / "Morrowind.esm", [], BASE + [rec("CONT", sub("NAME", z("zz_chest"))),
                                         cell("Town, Gate", ref(8, "zz_door", dest="Town, Home"), x=1)])
    plugin(df / "Mod.esp", [("Morrowind.esm", (df / "Morrowind.esm").stat().st_size)],
           [cell("Town, Home", ref(20, "zz_chest", owner="hermit"), ref(21, "zz_chest", owner="hermit"),
                 ref(22, "zz_chest", owner="kalir"), ref(23, "zz_chest", owner="ghost"))])
    w = m.World(m.Report())
    w.file_sizes, w.trace = {}, set()
    for n in ("Morrowind.esm", "Mod.esp"):
        w.load_plugin(str(df / n), n)
    w._check_ownership()
    (msg,) = [i[-1] for i in w.r.issues if "here owned by" in i[-1]]
    assert "2 container(s)" in msg and "'hermit'" in msg and "'kalir': --fix gives them to them" in msg
