"""Detect incompatible edits left at the old location of moved land.

The normal Cell Fixes workflow does not relocate whole land masses, pathgrids or scripts.
KNOWN_MOVES adds known Solstheim movers when their moved terrain cannot be matched exactly.
"""
from collections import Counter, defaultdict
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mwdialog_footing import _state  # noqa: E402

MIN_CELLS = 8           # unchanged land cells by one offset before land counts as moved
MAX_CELLS = 32          # moves farther than this many cells aren't looked for
ON_GROUND = 64.0        # an object this close to the land stands on it
ABSOLUTE_SETPOS = re.compile(r'^\s*(?:"([^"]+)"|([\w]+))\s*->\s*setpos\s*,?\s*([xyz])\s*,?\s*'
                             r'([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s*$', re.IGNORECASE)

# (cells east, cells north) -> plugins that move land by it
KNOWN_MOVES = {
    (7, 6): frozenset({"anthologysolstheimpatched.esm", "solstheim tomb of the snow prince.esm"}),
}
# made for the moved land without naming a mover as a master
MADE_FOR_MOVED = frozenset({
    "anthology solstheim spire.esp",
    "blackthorn barrow (anthology patch).esp",
    "cutting room floor - anthology solstheim.esp",
    "well diversified - anthology solstheim.esp",
    "totsp td content integration - spiders.esp",
    "totsp_forceful_travel_npc_override.esp",
    "totsp_patch_for_purists_5.0.6.esp",
})


class Move:
    def __init__(self, offset, movers, base, old, new):
        self.offset, self.movers, self.base, self.old, self.new = offset, movers, base, old, new


def _move(world, off, movers):
    """The Move by off of movers' land, or None when nothing of the old place is left behind."""
    names, lv = world.names, world.land_vers
    base = frozenset(set().union(*(world.knows(m) for m in movers)) - movers)
    mover_land = {c for c, vs in lv.items() if any(names[pi] in movers for pi, _d, _o in vs)}
    old = set()
    for g, vs in lv.items():
        if (g[0] + off[0], g[1] + off[1]) not in mover_land:
            continue
        v = next((v for v in reversed(vs) if names[v[0]] in base), None)
        if v is None or v[1] == vs[-1][1]:
            continue                             # the land there is still the one it had
        h = world._land_of(g, base)
        sunk = world._land_of(g, movers)         # a mover's own land there: the old place under the sea
        if h and max(h) > 0 and sunk and max(sunk) <= 0:
            old.add(g)
    return Move(off, movers, base, old, mover_land) if old else None


def find_moves(world, known=None):
    """The land moves in world's load order (a Placements), as [Move]: found from the land, plus known's."""
    names, lv = world.names, world.land_vers
    where = defaultdict(set)                     # land digest -> {(cell, plugin index)}
    for c, vs in lv.items():
        for pi, d, _o in vs:
            where[d].add((c, pi))
    votes = defaultdict(Counter)                 # offset -> {mover: cells}
    for g, vs in lv.items():
        for pi, d, _o in vs[:-1]:
            if d == vs[-1][1]:
                continue
            hits = {(c, pj) for c, pj in where[d] if c != g and pj > pi}
            if len({c for c, _p in hits}) != 1:
                continue                         # land found in many places (flat sea floor) proves nothing
            for c, pj in hits:
                off = (c[0] - g[0], c[1] - g[1])
                if max(abs(off[0]), abs(off[1])) <= MAX_CELLS:
                    votes[off][names[pj]] += 1
    found = {}
    for off, by in votes.items():
        movers = {m for m, n in by.items() if n >= 2}
        if sum(by[m] for m in movers) >= MIN_CELLS:
            found[off] = movers
    present = set(names)
    for off, ms in (KNOWN_MOVES if known is None else known).items():
        if ms & present:
            found.setdefault(off, set()).update(ms & present)
    return [m for m in (_move(world, off, frozenset(ms)) for off, ms in found.items()) if m]


def incompatible_land_plugins(world, pathgrids, scripts=()):
    """Find independent old-site edits; only complex, evidenced conflicts require a choice."""
    pairs = defaultdict(lambda: {"cells": set(), "evidence": set()})
    present = set(world.names)
    scripted = defaultdict(list)
    for owner, commands in scripts:
        for oid, axis, value in commands:
            scripted[oid].append((owner, axis, float(value)))
    for move in find_moves(world):
        def unaware(name):
            return (name in present and name not in move.base and name not in move.movers and name not in MADE_FOR_MOVED
                    and not move.movers.intersection(world.knows(name)))

        def note(owner, grid, kind):
            if not unaware(owner):
                return
            for mover in move.movers:
                pairs[(owner, mover)]["cells"].add(grid)
                pairs[(owner, mover)]["evidence"].add(kind)

        for grid in sorted(move.old):
            for pi, _digest, _off in world.land_vers.get(grid, ()):
                owner = world.names[pi]
                if unaware(owner):
                    heights = world._land_of(grid, frozenset({owner}))
                    if heights and max(heights) > 0:
                        note(owner, grid, "terrain")
            if grid in pathgrids:
                note(world.names[pathgrids[grid][0]], grid, "pathgrid")
            versions = defaultdict(list)
            for pi, key, _grid, _group, block in world.cell(grid):
                versions[key].append((pi, block))
            for key, rows in versions.items():
                owner = key[0]
                if not unaware(owner) or not any(world.names[pi] == owner for pi, _block in rows):
                    continue
                if any(block[0][0] == "MVRF" for _pi, block in rows):
                    continue
                pos, _scale, oid, deleted = _state([block for _pi, block in rows])
                if deleted or not pos:
                    continue
                height = world.land(frozenset(world.knows(owner)))(pos[0], pos[1])
                if height > 0 and abs(pos[2] - height) < ON_GROUND:
                    note(owner, grid, "placed objects")
                for script_owner, axis, value in scripted.get(oid, ()):
                    index = {"x": 0, "y": 1}.get(axis)
                    if index is not None and move.offset[index] and abs(value - pos[index]) < 0.01:
                        note(script_owner, grid, "script coordinates")
    for evidence in pairs.values():
        evidence["requires_choice"] = bool(evidence["evidence"] & {"terrain", "pathgrid", "script coordinates"})
    return dict(pairs)


def absolute_script_positions(text):
    """Explicit object->SetPos axis numeric-literal commands, excluding comments and variable expressions."""
    out = []
    for line in text.splitlines():
        match = ABSOLUTE_SETPOS.match(line.split(";", 1)[0])
        if match:
            out.append(((match.group(1) or match.group(2)).lower(), match.group(3).lower(), match.group(4)))
    return out
