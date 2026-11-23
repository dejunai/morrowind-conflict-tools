"""mwdialog_anthology_override.py - for --fix (Cell Fixes): land a mod moved elsewhere (Anthology Solstheim and Tomb of the
Snow Prince put Solstheim where the lore puts it, 7 cells east and 6 north of Bloodmoon's).
The move is found from the land alone: land a plugin replaced that a later plugin put down, unchanged, in other
cells, all by one offset. KNOWN_MOVES adds the Solstheim movers even when their land isn't matched. What mods made
for the old place put there goes with it, by the same offset and up or down with the land there: their own objects
(moved into the new cell, MVRF, as the CS does when a reference is dragged across a cell border) and door arrivals.
A mod counts as made for the old place when it doesn't have a mover among its masters, isn't in MADE_FOR_MOVED,
and its objects stand on the old land at least as often as on the land in use.
Nothing here is Solstheim-specific but the two tables; another moved land set is found and handled the same way.
"""
from collections import Counter, defaultdict
import math
import os
import statistics
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mwdialog_footing import NO_LAND, _state  # noqa: E402

CELL = 8192
MIN_CELLS = 8           # unchanged land cells by one offset before land counts as moved
MAX_CELLS = 32          # moves farther than this many cells aren't looked for
ON_GROUND = 64.0        # an object this close to the land stands on it

# (cells east, cells north) -> plugins that move land by it
KNOWN_MOVES = {
    (7, 6): frozenset({"anthologysolstheimpatched.esm", "solstheim tomb of the snow prince.esm"}),
}
# made for the moved land without naming a mover as a master: never moved
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


class LandMoves:
    """The moves of a load order, and who was made for the land where it was."""

    def __init__(self, world, known=None, made_for_moved=None):
        self.world = world
        self.moves = find_moves(world, known)
        self.made_for_moved = MADE_FOR_MOVED if made_for_moved is None else made_for_moved
        self.made_for_old = {}                   # (move index, plugin) -> True: moved with it / False: stays
        self._land = {}

    def _land_seen(self, name):
        if name not in self._land:
            self._land[name] = self.world.land(frozenset(self.world.knows(name)))
        return self._land[name]

    def _knows_move(self, i, name):
        m = self.moves[i]
        return name in m.movers or name in self.made_for_moved or bool(m.movers & self.world.knows(name))

    def _move_of(self, x, y):
        g = (math.floor(x / CELL), math.floor(y / CELL))
        return next((i for i, m in enumerate(self.moves) if g in m.old), None)

    def plan(self, patched):
        """(moves, by): moves [(ref key, cell key, group, block)] to write; by: Counter of (owner, mover) ->
        objects moved. Decides who was made for the old place (made_for_old)."""
        world, final = self.world, self.world.land()
        out, by = [], Counter()
        for i, m in enumerate(self.moves):
            votes, cand = defaultdict(Counter), defaultdict(list)
            for g in sorted(m.old | m.new):
                vers = defaultdict(list)
                for pi, bk, _g, grp, blk in world.cell(g):
                    vers[bk].append((world.names[pi], grp, blk))
                for bk, vs in vers.items():
                    owner = bk[0]
                    if owner in m.base or self._knows_move(i, owner):
                        continue
                    own = next((blk for n, _gr, blk in vs if n == owner), None)
                    if own is None:
                        continue
                    pos, _s, _oid, dele = _state([own])
                    if dele or not pos:
                        continue
                    x, y, z = pos[:3]
                    h_old, h_new = self._land_seen(owner)(x, y), final(x, y)
                    on_old = h_old > NO_LAND and abs(z - h_old) < ON_GROUND
                    on_new = h_new > NO_LAND and abs(z - h_new) < ON_GROUND
                    if on_old != on_new:
                        votes[owner][on_new] += 1
                    if g in m.old:
                        cand[owner].append((bk, g, vs))
            for owner, items in cand.items():
                v = votes[owner]
                gone = self.made_for_old[(i, owner)] = v[True] == 0 or v[False] > v[True]
                if gone:
                    for bk, g, vs in items:
                        moved = self._move_ref(i, owner, bk, g, vs, patched, final)
                        out += moved
                        if moved:
                            by[(owner, sorted(m.movers)[0])] += 1
        return self._settle(out, final), by

    def _move_ref(self, i, owner, bk, g, vs, patched, final):
        m = self.moves[i]
        if any(blk[0][0] == "MVRF" for _n, _gr, blk in vs):
            return []                            # already moved to another cell by its own mod
        last = vs[-1][0]
        if last != owner and self._knows_move(i, last):
            return []                            # a mod made for the moved land put it where it wants it
        ck = ("e", g[0], g[1])
        grp = vs[-1][1]
        blk = patched[ck][bk][1] if bk in patched.get(ck, ()) else vs[-1][2]
        pos, _s, _oid, dele = _state([blk])
        if dele or not pos or not any(s == "DATA" and len(d) >= 24 for s, d in blk):
            return []
        x, y, z = pos[:3]
        nx, ny = x + m.offset[0] * CELL, y + m.offset[1] * CELL
        h_old = self._land_seen(owner)(x, y)
        dz = final(nx, ny) - h_old if h_old > 0 else None
        return [(bk, ck, grp, blk, (nx, ny, z), dz, owner)]

    def _settle(self, items, final):
        """Each mod's objects in a cell rise or fall by the middle of their land's rises and falls there; those
        put over water stay at sea level."""
        rise = defaultdict(list)
        for bk, ck, grp, blk, (nx, ny, z), dz, owner in items:
            if dz is not None:
                rise[(owner, math.floor(nx / CELL), math.floor(ny / CELL))].append(dz)
        out = []
        for bk, ck, grp, blk, (nx, ny, z), dz, owner in items:
            key = (owner, math.floor(nx / CELL), math.floor(ny / CELL))
            nz = z + statistics.median(rise[key]) if dz is not None else z
            out.append((bk, ck, grp, moved_block(blk, nx, ny, nz)))
        return out

    def arrival(self, introducer, x, y, z):
        """Where a door arrival (x, y, z) set by introducer goes now, or None when it stays."""
        i = self._move_of(x, y)
        if i is None or self._knows_move(i, introducer) or self.made_for_old.get((i, introducer)) is False:
            return None
        m = self.moves[i]
        nx, ny = x + m.offset[0] * CELL, y + m.offset[1] * CELL
        h_old = self._land_seen(introducer)(x, y)
        h_new = self.world.land()(nx, ny)
        return nx, ny, z + (h_new - h_old if h_old > 0 and h_new > NO_LAND else 0.0)


def moved_block(blk, x, y, z):
    """blk placed at x, y, z, moved into the cell that is in (MVRF + CNDT before its FRMR)."""
    new = []
    for s, d in blk:
        if s in ("MVRF", "CNDT", "CNAM"):
            continue
        if s == "DATA" and len(d) >= 24:
            d = struct.pack("<3f", x, y, z) + d[12:]
        new.append([s, d])
    return [["MVRF", new[0][1]], ["CNDT", struct.pack("<ii", math.floor(x / CELL), math.floor(y / CELL))]] + new
