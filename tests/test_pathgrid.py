"""--fix (Cell Fixes): a pathgrid path that a later mod's object stands across is sent round it, a path point inside
it is moved out, and the pathgrid's own objects are left alone (a stall at one end of Seyda Neen)."""
import struct
import types

from conftest import m, plugin, rec, sub, z
from mwdialog_pathgrid import parse_pgrd
from nif_fixture import deck


def land():
    return rec("LAND", sub("INTV", struct.pack("<ii", 0, 0)) + sub("VHGT", bytes(4 + 4225 + 3)))


def cell(*refs):
    return rec("CELL", sub("NAME", z("")) + sub("DATA", struct.pack("<Iii", 0, 0, 0)) + b"".join(refs))


def ref(index, oid, x, y):
    return sub("FRMR", struct.pack("<I", index)) + sub("NAME", z(oid)) + \
        sub("DATA", struct.pack("<6f", x, y, 0.0, 0.0, 0.0, 0.0))


def pgrd(points, edges):
    links = [[b for a2, b in edges if a2 == a] + [a2 for a2, b in edges if b == a] for a in range(len(points))]
    pgrp = b"".join(struct.pack("<iiiBBh", x, y, 0, 1, len(links[i]), 0) for i, (x, y) in enumerate(points))
    pgrc = b"".join(struct.pack("<%dI" % len(lk), *lk) for lk in links)
    return rec("PGRD", sub("DATA", struct.pack("<iiHH", 0, 0, 256, len(points))) + sub("NAME", z(""))
               + sub("PGRP", pgrp) + sub("PGRC", pgrc))


def run(tmp_path, points, edges, stall_at, stall_in_master=False, dry_run=False, report=None, mesh=True):
    data = tmp_path / "Data Files"
    (data / "Meshes").mkdir(parents=True, exist_ok=True)
    if mesh:
        (data / "Meshes" / "stall.nif").write_bytes(deck(64, 60))       # a counter 60 high, 128 across
    stall = [ref(1, "stall", *stall_at)] if stall_in_master else []
    size = len(plugin(data / "Master.esm", [], [
        rec("STAT", sub("NAME", z("stall")) + sub("MODL", z("stall.nif"))), land(), cell(*stall), pgrd(points, edges)]))
    order = ["Master.esm"]
    if not stall_in_master:
        plugin(data / "Stall.esp", [("Master.esm", size)], [cell(ref(1, "stall", *stall_at))])
        order.append("Stall.esp")
    (tmp_path / "Morrowind.ini").write_text("[Game Files]\n" + "".join(f"GameFile{i}={n}\n" for i, n in enumerate(order)))
    m.write_load_order(str(tmp_path), order, "test")
    args = types.SimpleNamespace(data_dir=str(data), dry_run=dry_run, ini=str(tmp_path / "Morrowind.ini"),
                                 fix_log="fix.log", fix=False)
    m.fix_cell_winners(args, [(n, str(data / n)) for n in order], report)
    patch = data / m.CELL_WINNER_PATCH
    if not patch.exists():
        return None
    for _o, t, _f, body in m.iter_records(patch.read_bytes()):
        if t == "PGRD":
            _subs, pts, links = parse_pgrd(body)
            return pts, links
    return None


def test_path_across_a_new_stall_goes_round_it(tmp_path):
    pts, links = run(tmp_path, [(1000, 2000), (3000, 2000)], [(0, 1)], (2000, 2000))
    assert 1 not in links[0] and len(pts) > 2                     # no longer straight through the stall
    seen, todo = {0}, [0]
    while todo:
        for b in links[todo.pop()]:
            if b not in seen:
                seen.add(b)
                todo.append(b)
    assert 1 in seen                                             # still joined, round it
    assert all(abs(p[0] - 2000) > 64 or abs(p[1] - 2000) > 64 for p in pts)
    assert all(a in links[b] for a, lk in enumerate(links) for b in lk)
    lines = (tmp_path / m.PATHGRID_FIXES_FILE).read_text(encoding="utf-8").splitlines()[1:]
    assert len(lines) == 1 and lines[0].startswith("FIXED     #0,0 (master.esm's pathgrid): the path 0-1")


def test_unfixable_pathgrid_is_reported_with_why(tmp_path):
    run(tmp_path, [(1000, 2000), (3000, 2000)], [(0, 1)], (2000, 2000), mesh=False)
    lines = (tmp_path / m.PATHGRID_FIXES_FILE).read_text(encoding="utf-8").splitlines()[1:]
    assert lines == ["REPORTED  #0,0 (master.esm's pathgrid): stall's model can't be read; it may stand in a path"]


def test_point_inside_a_new_stall_is_moved_out_and_nothing_removed(tmp_path):
    pts, links = run(tmp_path, [(2000, 2000), (2000, 3200)], [(0, 1)], (2000, 2000))
    assert len(pts) >= 2 and (abs(pts[0][0] - 2000) > 64 or abs(pts[0][1] - 2000) > 64)
    assert pts[1][:2] == [2000, 3200] and links[0] and links[1]


def test_the_pathgrids_own_stall_is_left_alone(tmp_path):
    assert run(tmp_path, [(1000, 2000), (3000, 2000)], [(0, 1)], (2000, 2000), stall_in_master=True) is None


def test_an_unchanged_cell_is_taken_from_the_cache(tmp_path, capsys):
    first = run(tmp_path, [(1000, 2000), (3000, 2000)], [(0, 1)], (2000, 2000))
    before = (tmp_path / m.PATHGRID_FIXES_FILE).read_text(encoding="utf-8").splitlines()[1:]
    capsys.readouterr()
    assert run(tmp_path, [(1000, 2000), (3000, 2000)], [(0, 1)], (2000, 2000)) == first
    assert (tmp_path / m.PATHGRID_FIXES_FILE).read_text(encoding="utf-8").splitlines()[1:] == before
    assert "1 cell(s) unchanged" in capsys.readouterr().out


def test_a_moved_object_or_new_mesh_is_worked_out_again(tmp_path, capsys):
    run(tmp_path, [(1000, 2000), (3000, 2000)], [(0, 1)], (2000, 2000))
    capsys.readouterr()
    pts, _links = run(tmp_path, [(1000, 2000), (3000, 2000)], [(0, 1)], (2000, 2020))
    assert "unchanged" not in capsys.readouterr().out
    assert all(abs(p[0] - 2000) > 64 or abs(p[1] - 2020) > 64 for p in pts)
    (tmp_path / "Data Files" / "Meshes" / "stall.nif").unlink()
    run(tmp_path, [(1000, 2000), (3000, 2000)], [(0, 1)], (2000, 2020), mesh=False)
    assert "unchanged" not in capsys.readouterr().out
    assert "stall's model can't be read" in (tmp_path / m.PATHGRID_FIXES_FILE).read_text(encoding="utf-8")


def test_dry_run_writes_nothing(tmp_path):
    assert run(tmp_path, [(1000, 2000), (3000, 2000)], [(0, 1)], (2000, 2000), dry_run=True) is None


def test_report_warns_of_fixed_pathgrids_and_notes_the_rest(tmp_path):
    fixed, left = m.Report(), m.Report()
    run(tmp_path / "a", [(1000, 2000), (3000, 2000)], [(0, 1)], (2000, 2000), dry_run=True, report=fixed)
    run(tmp_path / "b", [(1000, 2000), (3000, 2000)], [(0, 1)], (2000, 2000), dry_run=True, report=left, mesh=False)
    assert [i[:3] for i in fixed.issues] == [("WARN", "Master.esm", "pathgrid #0,0")]
    assert "goes round it" in fixed.issues[0][4] and m.NOT_OWN_BUG.search(fixed.issues[0][4])
    assert [i[:3] for i in left.issues] == [("INFO", "Master.esm", "pathgrid #0,0")]
