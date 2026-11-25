"""mwdialog_cellmods.py - what --cell-conflicts hands to the MWSE mods: doubled objects for mwcollide
(mwcollide_data.json), loose items that could float for mwfloatfix (mwfloatfix_data.json) and objects stranded
by a rebuilt interior for mwstranded (mwstranded_data.json).
"""
from collections import defaultdict
import hashlib
import inspect
import json
import math
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_text as MT  # noqa: E402
from mwdialog_tes3 import (  # noqa: E402
    FormatError, ITEM_TAGS, cstr, first_sub, iter_records, read_plugin_bytes)
from mwdialog_records import height_at, land_heights  # noqa: E402
import mwdialog_paths as MP  # noqa: E402
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
    cells, count = {}, 0
    for key, hide in doubled_objects(args, order, new_objs, pos, name_of, deps, cells_of).items():
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


FLOAT_DATA = "mwfloatfix_data.json"            # Data Files\MWSE\config\, read by the mwfloatfix MWSE mod

FLOAT_ITEM_TAGS = {"MISC", "BOOK", "INGR", "ALCH", "WEAP", "AMMO", "ARMO", "CLOT", "APPA", "LOCK", "PROB", "REPA"}

FLOAT_SUPPORT_TAGS = {"STAT", "CONT", "ACTI"}  # what an item can rest on (Morrowind's furniture is statics)

FLOAT_TOLERANCE = 4.0                          # mwfloatfix's default: a gap up to this still rests

# shortcut: no NIF bounds, so "on it" is within this many units across (times its scale) and from FLOAT_BELOW to
# FLOAT_ABOVE over its origin; reading each mesh's bounding box would make this exact
FLOAT_REACH, FLOAT_BELOW, FLOAT_ABOVE = 128.0, -32.0, 256.0

FLOAT_ON_LAND = 32.0                           # an item at most this far above the land it was placed on rests on it


def float_items(ref_hist, land_v, deps, tag_of, tol=FLOAT_TOLERANCE, ours=frozenset(), esm_only=frozenset()):
    """What write_float_data lists: cell key ("name" / "#x,y") -> {(id, x, y, z): (plugin, why)} for loose items
    whose final version sits on something changed by a plugin the item's plugin doesn't know about: a static,
    container or activator within reach below it moved, rescaled or deleted, or, outside, the land under it
    lowered by more than tol. (A replacer's new mesh isn't counted: without NIF bounds nearly every piece of
    furniture would count.) ref_hist: cell key -> ref ->
    [(plugin index, plugin, object, (x, y, z) or None, scale, deleted)]; land_v: grid -> [(plugin index,
    plugin, VHGT)].
    ours: this tool's own patches (Cell Fixes, the auto-merge, ...). Their versions are the final word on where a
    thing is or whether it is gone, but they "know" every plugin, so an item whose last version is one of them is
    judged by what its real author knew (the last version not from `ours`); an item only `ours` ever placed (an
    auto-merged plugin's) is judged against the .esm files alone (`esm_only`)."""
    lands = {g: sorted(v, key=lambda t: t[0]) for g, v in land_v.items() if len(v) > 1}
    heights = {}

    def height(g, i, x, y):
        if (g, i) not in heights:
            heights[(g, i)] = land_heights(lands[g][i][2])
        return height_at(heights[(g, i)], g, x, y)

    found = defaultdict(dict)
    for key, refs in ref_hist.items():
        items, grid = [], defaultdict(list)
        for vs in refs.values():
            vs.sort(key=lambda t: t[0])
            oid = next((v[2] for v in vs if v[2]), "")
            tag = tag_of.get(oid.lower())
            if tag in FLOAT_ITEM_TAGS:
                if not vs[-1][5] and vs[-1][3]:
                    items.append((oid, vs[-1], vs))
            elif tag in FLOAT_SUPPORT_TAGS and len(vs) > 1:
                for v in vs:                       # filed under every spot it was ever at
                    if v[3]:
                        grid[(int(v[3][0] // FLOAT_REACH), int(v[3][1] // FLOAT_REACH))].append((oid, vs))
        if not items:
            continue
        for oid, last, ivs in items:
            author = next((v for v in reversed(ivs) if v[1] not in ours), None)
            known = (deps(author[1]) | {author[1]}) if author else set(esm_only)
            x, y, z = last[3]
            why, looked = None, set()
            gx, gy = int(x // FLOAT_REACH), int(y // FLOAT_REACH)
            for sid, vs in (s for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2) for s in grid.get((gx + dx, gy + dy), ())):
                if id(vs) in looked:
                    continue
                looked.add(id(vs))
                seen = next((v for v in reversed(vs) if v[1] in known), None)
                if seen is None or seen[5] or not seen[3]:
                    continue                       # not there when the item was put down
                sx, sy, sz = seen[3]
                reach = min(FLOAT_REACH * max(seen[4], 0.1), 2 * FLOAT_REACH)
                if (x - sx) ** 2 + (y - sy) ** 2 > reach * reach or not FLOAT_BELOW <= z - sz <= FLOAT_ABOVE:
                    continue
                fin = vs[-1]
                if fin[1] != seen[1] and (fin[5] or not fin[3] or abs(fin[4] - seen[4]) > 0.01
                                          or max(abs(a - b) for a, b in zip(fin[3], seen[3])) > tol):
                    why = f"{sid} {'deleted' if fin[5] else 'moved'} by {fin[1]}"
                    break
            if why is None and key[0] == "e":
                g = (int(math.floor(x / 8192)), int(math.floor(y / 8192)))
                lv = lands.get(g)
                si = next((i for i in range(len(lv) - 1, -1, -1) if lv[i][1] in known), None) if lv else None
                if si is not None and si != len(lv) - 1:
                    was, now = height(g, si, x, y), height(g, len(lv) - 1, x, y)
                    if was is not None and now is not None and z - was <= FLOAT_ON_LAND and was - now > tol:
                        why = f"land lowered {was - now:.0f} by {lv[-1][1]}"
            if why:
                ck = key[1] if key[0] == "i" else f"#{int(math.floor(x / 8192))},{int(math.floor(y / 8192))}"
                found[ck][(oid, int(math.floor(x + 0.5)), int(math.floor(y + 0.5)), int(math.floor(z + 0.5)))] = \
                    ((author or last)[1], why)
    return found


# the patch whose contents the MWSE side hashes too: the last word on what is where (mwdialog_state.CELL_WINNER_PATCH)
HASHED_SOURCES = frozenset({"mwdialog_check cell fixes.esp"})


def fnv1a_file(path):
    """FNV-1a (32 bit) of a file as eight hex digits: the sum mwfloatfix (LuaJIT, no hashlib) works out the same way."""
    h = 0x811C9DC5
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            for b in chunk:
                h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return f"{h:08x}"


def patch_sources(data_dir, names):
    """{file name: {"size"[, "fnv1a"]}} of the generated patches the data was built against, so the MWSE side can tell
    when one was rebuilt (or removed) after the data was written and stop trusting the list. Not the file time:
    --fix sets its plugins' dates to fix the load order, so a date never says which build a file is. Cell Fixes (the
    last word on what is where) also gets a content hash: a rebuild can come out the same size."""
    out = {}
    for n in names:
        path = os.path.join(data_dir, n)
        try:
            st = os.stat(path)
        except OSError:
            continue
        out[n] = {"size": st.st_size}
        if n.lower() in HASHED_SOURCES:
            try:
                out[n]["fnv1a"] = fnv1a_file(path)
            except OSError:
                pass
    return out


def write_float_data(args, order, ref_hist, land_v, labels, name_of, deps, ours=(), ours_names=()):
    """For the mwfloatfix MWSE mod: the loose items that could float (float_items), so it checks only those.
    ours / ours_names: this tool's patches that were read as history (lower-case / as on disk)."""
    data_dir = os.path.abspath(args.data_dir)
    tag_of, _model_of, _scripted = object_info(order)
    esm_only = {n.lower() for n, _p in order if n.lower().endswith(".esm")}
    found = float_items(ref_hist, land_v, deps, tag_of, ours=frozenset(ours), esm_only=frozenset(esm_only))
    cells, count = {}, 0
    for ck, hits in sorted(found.items()):
        name = ck if ck.startswith("#") else (labels.get(("i", ck)) or ck).lower()
        cells[name] = [{"id": k[0], "pos": [k[1], k[2], k[3]], "from": name_of.get(v[0], v[0]), "why": v[1]}
                       for k, v in sorted(hits.items())]
        count += len(hits)
    out_dir = os.path.join(data_dir, "MWSE", "config")
    os.makedirs(out_dir, exist_ok=True)
    payload = {"version": 1, "generated": time.strftime("%Y-%m-%d %H:%M:%S"), "count": count, "cells": cells,
               "sources": patch_sources(data_dir, ours_names)}
    tmp = os.path.join(out_dir, FLOAT_DATA + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(out_dir, FLOAT_DATA))
    print(f"  mwfloatfix data: {count} loose item(s) that could float in {len(cells)} of {len(ref_hist)} cell(s) "
          f"for the game to check (MWSE\\config\\{FLOAT_DATA})")
    return count


def doubled_objects(args, order, new_objs, pos, name_of, deps, cells_of):
    """What write_collide_data lists: cell key -> {(id, x, y, z): (id, losing plugin, winning plugin, the
    winner's object, (owner, index) of the losing reference, its group "p"/"t")}."""
    tag_of, model_of, scripted = object_info(order)   # scripted: a script may need this very copy, never hidden
    found = {}
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
                                    hide.setdefault(k, (o[0], name_of.get(a, a), name_of.get(b, b), q[0], o[4], o[5]))
        if hide:
            found[key] = hide
    return found


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

OBJECT_CACHE_FILE = "mwdialog_object_cache.json"   # beside Data Files: each plugin's objects, by its content
OBJECT_CACHE_DAYS = 60                             # an entry no run has used for this long is dropped


def _plugin_objects(data):
    """[[id, tag, scripted 0/1, model or ""]] of one plugin's object records, in file order (up to any damage)."""
    out = []
    try:
        for _off, tag, _flags, body in iter_records(data):
            if tag in ("CELL", "DIAL", "INFO", "LAND", "PGRD", "TES3", "SCPT", "GMST"):
                continue
            nm = first_sub(body, b"NAME")
            if nm is None:
                continue
            md = first_sub(body, b"MODL")
            out.append([cstr(nm).lower(), tag, 1 if first_sub(body, b"SCRI") else 0,
                        cstr(md).lower().replace("/", "\\") if md else ""])
    except FormatError:
        pass
    return out


def _parser_version():
    """A change to how a plugin's objects are read starts the cache afresh."""
    try:
        src = inspect.getsource(_plugin_objects) + inspect.getsource(iter_records) + inspect.getsource(first_sub)
    except (OSError, TypeError):
        src = "unknown"
    return hashlib.sha1(src.encode("utf-8")).hexdigest()


def object_info(order):
    """(tag_of, model_of, scripted) for every object id the plugins define (the last definition wins). Each
    plugin's objects are kept in mwdialog_object_cache.json under the SHA-1 of its bytes, so a plugin is only read
    record by record again once its content changes."""
    parts = []
    for n, p in order:
        try:
            st = os.stat(p)
            parts.append((n.lower(), st.st_size, st.st_mtime_ns))
        except OSError:
            parts.append((n.lower(), None, None))
    key = tuple(parts)
    if key in _OBJECT_INFO:
        return _OBJECT_INFO[key]
    cache_path = MP.state_path(os.path.dirname(os.path.dirname(os.path.abspath(order[0][1]))),
                              OBJECT_CACHE_FILE) if order else None
    version, cached = _parser_version(), {}
    if cache_path:
        try:
            with open(cache_path, encoding="utf-8") as f:
                saved = json.load(f)
            if saved.get("parser") == version and isinstance(saved.get("plugins"), dict):
                cached = saved["plugins"]
        except (OSError, ValueError, AttributeError):
            pass
    now, changed = int(time.time()), False
    model_of, tag_of, scripted = {}, {}, set()
    for _n, p in order:
        try:
            data = read_plugin_bytes(p)
            digest = hashlib.sha1(data).hexdigest()
            entry = cached.get(digest)
            if not isinstance(entry, dict) or not isinstance(entry.get("objects"), list):
                entry = cached[digest] = {"objects": _plugin_objects(data)}
                changed = True
            if entry.get("used", 0) < now - 86400:
                entry["used"], changed = now, True
            objects = entry["objects"]
        except (OSError, FormatError):
            continue
        for rid, tag, scr, model in objects:
            tag_of[rid] = tag
            if scr:
                scripted.add(rid)
            else:
                scripted.discard(rid)
            if model:
                model_of[rid] = model
    stale = [d for d, e in cached.items() if not isinstance(e, dict) or e.get("used", 0) < now - OBJECT_CACHE_DAYS * 86400]
    for d in stale:
        del cached[d]
    if cache_path and (changed or stale):
        try:
            tmp = cache_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"parser": version, "plugins": cached}, f)
            os.replace(tmp, cache_path)
        except OSError as e:
            print(f"  (could not write {OBJECT_CACHE_FILE}: {e})", file=sys.stderr)
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
