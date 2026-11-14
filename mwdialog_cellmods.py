"""mwdialog_cellmods.py - what --cell-conflicts hands to the MWSE mods: doubled objects for mwcollide
(mwcollide_data.json) and objects stranded by a rebuilt interior for mwstranded (mwstranded_data.json).
"""
from collections import defaultdict
import json
import math
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_text as MT  # noqa: E402
from mwdialog_tes3 import (  # noqa: E402
    FormatError, ITEM_TAGS, cstr, first_sub, iter_records)
print = MT.printer()  # noqa: A001

COLLIDE_DATA = "mwcollide_data.json"           # Data Files\MWSE\config\, read by the mwcollide MWSE mod

COLLIDE_RADIUS = 64.0                           # "the same thing in the same spot"

COLLIDE_ANY_RADIUS = 32.0                       # anything of the earlier mod this close to the later mod's: hidden

COLLIDE_STRUCTURE_RE = re.compile(r"cliff|rock|terrain|mountain|menhir|^ex_|\\ex_|_ex_|^in_|\\in_|_in_|wall|floor|"
                                  r"ceil|stair|ramp|bridge|dock|pier|plat|tower|house|shack|hut|tent|road|path|"
                                  r"ground|cave|mine|ruin|shrine|temple|canton|fence|gate|arch|pillar|column|"
                                  r"beam|roof|window|land|isle|island|snow_?drift|dune|mud|lava", re.I)

COLLIDE_SKIP_TAGS = {"NPC_", "CREA", "LEVC", "DOOR", "CONT"}   # never hidden: people, creatures, doors (each


def write_collide_data(args, order, new_objs, labels, pos, name_of, deps, cells_of):
    """For the mwcollide MWSE mod (interiors, and exterior cells keyed "#x,y"): objects that two plugins which don't know
    about each other both put in the same spot - the same object, or the same model, within 64 units, or
    anything at all within --collide-radius (default 32; markers and the like don't count). The
    earlier plugin's copy is listed, to be hidden as the cell loads; the later plugin's stays. Pairs a
    patch covers (a plugin with both as masters that has a record for the cell) are left alone, and so
    are people, creatures, doors, containers and anything with a script."""
    data_dir = os.path.abspath(args.data_dir)
    tag_of, model_of, scripted = object_info(order)   # scripted: a script may need this very copy, never hidden
    cells, count = {}, 0
    any_r = float(getattr(args, "collide_radius", COLLIDE_ANY_RADIUS) or 0)
    reach = max(COLLIDE_RADIUS, any_r)
    r2, a2 = COLLIDE_RADIUS * COLLIDE_RADIUS, any_r * any_r
    have_cell = defaultdict(list)                  # cell -> the plugins with a record for it (any could be a patch)
    for pl in pos:
        for c in cells_of.get(pl, ()):
            have_cell[c].append(pl)
    for key, per in new_objs.items():
        if len(per) < 2:
            continue
        plugins = sorted(per, key=lambda pl: pos.get(pl, -1))
        hide = {}
        grids = {}
        for i, a in enumerate(plugins):
            for b in plugins[i + 1:]:                      # a loads before b: b's copy stays
                if a in deps(b) or b in deps(a):
                    continue
                if any(a in deps(pl) and b in deps(pl) for pl in have_cell.get(key, ()) if pl not in (a, b)):
                    continue                                # a patch for both decides this cell
                grid = grids.get(b)
                if grid is None:
                    grid = grids[b] = defaultdict(list)
                    for o in per[b]:
                        grid[(int(o[1] // reach), int(o[2] // reach))].append(o)
                for o in per[a]:
                    oid = o[0].lower()
                    if tag_of.get(oid) in COLLIDE_SKIP_TAGS or oid in scripted:
                        continue
                    if INVISIBLE_RE.search(oid) or "marker" in model_of.get(oid, ""):
                        continue                    # markers: different ones share a model, and none is seen
                    # by nearness alone only clutter goes: never a piece of the land, a building, a wall or
                    # floor (its centre can be near something small that sits on or against it)
                    o_shown = not INVISIBLE_RE.search(oid) and not COLLIDE_STRUCTURE_RE.search(oid) \
                        and not COLLIDE_STRUCTURE_RE.search(model_of.get(oid, ""))
                    gx, gy = int(o[1] // reach), int(o[2] // reach)
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            for q in grid.get((gx + dx, gy + dy), ()):
                                qid = q[0].lower()
                                d2 = (q[1] - o[1]) ** 2 + (q[2] - o[2]) ** 2 + (q[3] - o[3]) ** 2
                                same = qid == oid or (model_of.get(oid) and model_of.get(oid) == model_of.get(qid))
                                # the same thing within 64 units, or (with --collide-radius) anything that
                                # shows within that of something of the later mod's that shows
                                close = d2 <= a2 and o_shown and not INVISIBLE_RE.search(qid) \
                                    and tag_of.get(qid) not in ("LEVC", "LEVI", "NPC_", "CREA")
                                if (same and d2 <= r2) or close:
                                    k = (oid, int(math.floor(o[1] + 0.5)), int(math.floor(o[2] + 0.5)), int(math.floor(o[3] + 0.5)))
                                    hide.setdefault(k, (o[0], name_of.get(a, a), name_of.get(b, b), q[0]))
        if hide:
            ck = (labels.get(key) or key[1]).lower() if key[0] == "i" else f"#{key[1]},{key[2]}"
            cells[ck] = [
                {"id": v[0], "pos": [k[1], k[2], k[3]], "from": v[1], "kept": v[2], "keptObject": v[3]}
                for k, v in sorted(hide.items())]
            count += len(hide)
    out_dir = os.path.join(data_dir, "MWSE", "config")
    os.makedirs(out_dir, exist_ok=True)
    payload = {"version": 2, "generated": time.strftime("%Y-%m-%d %H:%M:%S"), "radius": COLLIDE_RADIUS,
               "count": count, "cells": cells}
    tmp = os.path.join(out_dir, COLLIDE_DATA + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(out_dir, COLLIDE_DATA))
    print(f"  mwcollide data: {count} doubled object(s) in {len(cells)} cell(s) for the game to hide "
          f"(MWSE\\config\\{COLLIDE_DATA})")
    return count


REWORK_MIN_DELETED = 20       # a plugin that deletes at least this many of a cell's original objects...

REWORK_FRACTION = 0.3         # ...and at least this share of them has rebuilt the interior

RELOCATE_MIN_NEW = 100        # or adds this many objects, mostly outside the original layout's area

STRANDED_DISTANCE = 400.0     # an added object this far from everything else that is still there


# markers, sound and weather emitters, script holders: invisible, so where they end up doesn't show
INVISIBLE_RE = re.compile(r"marker|interiorweather|scriptholder|^_mca_|sound|^plx_es_|^rv_gh_|_trigger|^gvrm_.*_sc$|"
                          r"^g7_container", re.I)        # g7_container: MWSE Containers' storage, kept out of sight

STRANDED_DATA = "mwstranded_data.json"        # Data Files\MWSE\config\, read by the mwstranded MWSE mod

STRANDED_MOVE_TAGS = {"NPC_", "CREA", "LEVC", "CONT"} | ITEM_TAGS | {"MISC", "WEAP", "LEVI"}

STRANDED_KEEP_TAGS = set()                    # nothing is left in the void: doors and scripted things move too

_OBJECT_INFO = {}


def object_info(order):
    """(tag_of, model_of, scripted) for every object id the plugins define (the last definition wins)."""
    key = tuple(n.lower() for n, _p in order)
    if key in _OBJECT_INFO:
        return _OBJECT_INFO[key]
    model_of, tag_of, scripted = {}, {}, set()
    for n, p in order:
        try:
            with open(p, "rb") as f:
                data = f.read()
            for off, tag, flags, body in iter_records(data):
                if tag in ("CELL", "DIAL", "INFO", "LAND", "PGRD", "TES3", "SCPT", "GMST"):
                    continue
                nm = first_sub(body, b"NAME")
                if nm is None:
                    continue
                rid = cstr(nm).lower()
                tag_of[rid] = tag
                if first_sub(body, b"SCRI"):
                    scripted.add(rid)
                else:
                    scripted.discard(rid)
                md = first_sub(body, b"MODL")
                if md:
                    model_of[rid] = cstr(md).lower().replace("/", "\\")
        except (OSError, FormatError):
            continue
    _OBJECT_INFO.clear()
    _OBJECT_INFO[key] = (tag_of, model_of, scripted)
    return _OBJECT_INFO[key]


def report_rearranged(order, own_pos, deletions, new_objs, labels, pos, name_of, deps, cells_of,
                      doors=None, arrivals=None, lost=None):
    """--cell-conflicts: interiors a plugin has rebuilt (deleted much of the original, or built a new
    layout beside it), and what that breaks:
      - REBUILT TWICE: two plugins that don't know about each other both rebuild the same interior; the
        game shows a mix of both layouts
      - STRANDED: another plugin's additions (an NPC, a door, an item...) placed for the original layout,
        now cut off from the rebuilt one: in a void, inside rock, or behind a wall nobody reaches
        (the Clean Tales / Vennin's Addamasartus kind)
    doors: interior key -> [((x, y, z) of a door there, destination cell (lower), (x, y, z, z-rot) arriving)];
    arrivals: cell name (lower) -> [(x, y, z, z-rot)] where the doors into it land; lost: filled with
    (interior, object, x, y, z, plugin, arrival) for each stranded object."""
    doors = doors or {}
    arrivals = arrivals or {}
    lost = lost if lost is not None else []
    findings = []
    for key in set(deletions) | {k for k, per in new_objs.items() if k[0] == "i"}:
        if key[0] != "i":
            continue
        refs = own_pos.get(key, {})
        if not refs:
            continue
        gone = set()
        for pl, bks in deletions.get(key, {}).items():
            gone |= bks
        by_owner = defaultdict(list)
        for bk, v in refs.items():
            by_owner[bk[0]].append(v)
        reworkers = {}
        for pl, bks in deletions.get(key, {}).items():
            owners = {bk[0] for bk in bks}
            base_n = sum(len(by_owner.get(o, ())) for o in owners)
            if len(bks) >= REWORK_MIN_DELETED and base_n and len(bks) >= REWORK_FRACTION * base_n:
                reworkers[pl] = f"deletes {len(bks)} of the {base_n} original objects"
        # a new layout built beside the original (the original left in place, cut off)
        plugins = sorted({v[4] for v in refs.values()}, key=lambda q: pos.get(q, -1))
        if plugins:
            base = [v for v in refs.values() if v[4] == plugins[0]]
            if len(base) >= 10:
                xs, ys = [v[1] for v in base], [v[2] for v in base]
                bx0, bx1, by0, by1 = min(xs) - 512, max(xs) + 512, min(ys) - 512, max(ys) + 512
                for pl in plugins[1:]:
                    mine = [v for v in refs.values() if v[4] == pl]
                    if len(mine) >= RELOCATE_MIN_NEW and pl not in reworkers:
                        outside = sum(1 for v in mine if not (bx0 <= v[1] <= bx1 and by0 <= v[2] <= by1))
                        if outside >= 0.5 * len(mine):
                            reworkers[pl] = f"builds {outside} of its {len(mine)} objects outside the original layout"
        if not reworkers:
            continue
        label = labels.get(key) or key[1]
        # 1. rebuilt twice
        rw = sorted(reworkers, key=lambda q: pos.get(q, -1))
        for i, a in enumerate(rw):
            for b in rw[i + 1:]:
                if a in deps(b) or b in deps(a):
                    continue
                if any(a in deps(pl) and b in deps(pl) and key in cells_of.get(pl, ()) for pl in pos if pl not in (a, b)):
                    continue
                findings.append((2, label, f"REBUILT TWICE: {name_of.get(a, a)} ({reworkers[a]}) and "
                                           f"{name_of.get(b, b)} ({reworkers[b]}); the game shows a mix of both"))
        # 2. stranded additions of other plugins: whatever isn't joined to the rebuilt layout. Everything
        # still there is linked to everything within STRANDED_DISTANCE; the groups that hold the rebuilding
        # plugin's objects (or what it kept of its masters') are the layout, and so is any group a door in
        # the layout leads to (a door to another spot of the same place, like a patch's way into an older wing)
        R = STRANDED_DISTANCE
        still = [(bk, v) for bk, v in refs.items() if bk not in gone]
        parent = list(range(len(still)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        grid = defaultdict(list)
        for i, (_bk, v) in enumerate(still):
            grid[(int(v[1] // R), int(v[2] // R))].append(i)
        for i, (_bk, v) in enumerate(still):
            gx, gy = int(v[1] // R), int(v[2] // R)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j in grid.get((gx + dx, gy + dy), ()):
                        if j > i:
                            w = still[j][1]
                            if (w[1] - v[1]) ** 2 + (w[2] - v[2]) ** 2 + (w[3] - v[3]) ** 2 <= R * R:
                                parent[find(i)] = find(j)

        def group_at(x, y, z):
            best = None
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j in grid.get((int(x // R) + dx, int(y // R) + dy), ()):
                        w = still[j][1]
                        d2 = (w[1] - x) ** 2 + (w[2] - y) ** 2 + (w[3] - z) ** 2
                        if d2 <= R * R and (best is None or d2 < best[0]):
                            best = (d2, find(j))
            return best[1] if best else None
        layout_of = set(reworkers) | {m for r in reworkers for m in deps(r)}
        live = {find(i) for i, (_bk, v) in enumerate(still) if v[4] in layout_of}
        lab_l = (labels.get(key) or key[1]).lower()
        links = [(d_at, d_to) for d_at, dest, d_to in doors.get(key, ()) if dest == lab_l and d_at]
        changed = True
        while changed:
            changed = False
            for d_at, d_to in links:
                if group_at(*d_at) in live:
                    g = group_at(*d_to[:3])
                    if g is not None and g not in live:
                        live.add(g)
                        changed = True
        # where people and things cut off are brought: a way in that lands among the rebuilding plugin's own
        # objects (not just in what's left of the original: a later plugin may have put the old entrance back)
        own_groups = {find(i) for i, (_bk, v) in enumerate(still) if v[4] in reworkers}
        arrival = None
        for d_to in sorted(arrivals.get(lab_l, ()), key=lambda a: group_at(*a[:3]) not in own_groups):
            if group_at(*d_to[:3]) in live:
                arrival = d_to
                break
        for pl in plugins:
            if pl in reworkers:
                continue
            if any(pl in deps(r) or r in deps(pl) for r in reworkers):
                continue                       # made for (or by) the rebuild: fits it
            stranded = []
            for i, (bk, v) in enumerate(still):
                if v[4] != pl or INVISIBLE_RE.search(v[0]) or find(i) in live:
                    continue
                stranded.append((v[0], round(v[1]), round(v[2]), round(v[3])))
            if stranded:
                who = ", ".join(name_of.get(r, r) for r in reworkers)
                ex = "; ".join(f"{o} at {x}, {y}, {z}" for o, x, y, z in stranded[:4])
                findings.append((1, label, f"STRANDED: {len(stranded)} of {name_of.get(pl, pl)}'s objects were "
                                           f"placed for the original layout, which {who} rebuilt, and are cut "
                                           f"off from it (e.g. {ex})"))
                for o, x, y, z in stranded:
                    lost.append((label, o, x, y, z, name_of.get(pl, pl), arrival))
        if not any(f[1] == label for f in findings):
            findings.append((0, label, "rebuilt by " + "; ".join(f"{name_of.get(r, r)} ({why})"
                                                                for r, why in reworkers.items())))
    shown = [f for f in findings if f[0] > 0]
    print("\n" + "=" * 70 + f"\nREARRANGED INTERIORS: {len({f[1] for f in findings})} rebuilt by a plugin; "
          f"{len(shown)} finding(s) worth a look\n" + "=" * 70)
    for lvl, label, text in sorted(shown, key=lambda f: (-f[0], f[1].lower())):
        print(f"  {label}: {text}")
    if not shown:
        print("  Nothing rebuilt twice, and nothing left stranded by a rebuild.")
    quiet = sorted(f[1] for f in findings if f[0] == 0)
    if quiet:
        print(f"  ({len(quiet)} more interior(s) rebuilt by one plugin with nothing else affected, e.g. "
              + ", ".join(quiet[:6]) + ")")
    return findings


def write_stranded_data(args, order, lost):
    """For the mwstranded MWSE mod: what to do, as each rebuilt interior loads, with the objects another
    plugin placed for its old layout (report_rearranged's STRANDED):
      move   people, creatures, containers and loose items: brought to where a door into the place lands
             in the rebuilt layout, so they can still be met, looted or picked up
      move   also doors (a door out of the place still leads where it did) and scripted things (a lever, a
             shrine: the player can still use them; their scripts run on them wherever they stand)
      hide   unscripted scenery (walls, rocks, furniture, lights...): disabled, never deleted
      leave  what would be moved, in a place with no way into its rebuilt layout to bring it to
    The doors elsewhere that arrive among these objects are sent to the rebuilt layout by the Cell Fixes
    patch (--fix), or removed there when the place has no way in to send them to."""
    data_dir = os.path.abspath(args.data_dir)
    tag_of, _model_of, scripted = object_info(order)
    cells, counts = {}, defaultdict(int)
    for label, oid, x, y, z, plugin, arrival in lost:
        t = tag_of.get(oid.lower(), "")
        if t in STRANDED_KEEP_TAGS:
            act = "leave"
        elif t == "DOOR" or oid.lower() in scripted or (t in STRANDED_MOVE_TAGS and t != "LIGH"):
            act = "move" if arrival else "leave"
        else:
            act = "hide"
        counts[act] += 1
        c = cells.setdefault(label.lower(), {
            "arrival": [round(v, 1) for v in arrival] if arrival else None, "objects": []})
        c["objects"].append({"id": oid, "pos": [x, y, z], "from": plugin, "type": t, "action": act})
    out_dir = os.path.join(data_dir, "MWSE", "config")
    os.makedirs(out_dir, exist_ok=True)
    payload = {"version": 1, "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
               "cells": dict(sorted(cells.items()))}       # sorted: the same list gives the same file
    tmp = os.path.join(out_dir, STRANDED_DATA + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(out_dir, STRANDED_DATA))
    print(f"  mwstranded data: in {len(cells)} interior(s), {counts['move']} to bring into the rebuilt layout, "
          f"{counts['hide']} to hide, {counts['leave']} left (no way into the rebuilt layout) "
          f"(MWSE\\config\\{STRANDED_DATA})")
