"""mwdialog_footing.py - for --fix (Cell Fixes): people left over water because a later mod took away what they
stood on (a fisherman whose dock another mod rebuilt a little to the side, or a guard whose land another mod sank).
An NPC is moved only when the structure or land they were placed on is gone and only water is under them now: to
level footing of about the same height close by, else to the closest dry level footing within WIDE_REACH, so that
nobody (perhaps someone a quest needs) is left cut off on the seabed. When the land they stood on is in use
unchanged a few cells away (a mod moved the island), they go to the same spot there. Someone moved into another
cell is moved there (MVRF), as the CS does when a reference is dragged across a cell border.
Footing is worked out from the land heights and the collision triangles of the models.
"""
from collections import defaultdict
import functools
import hashlib
import json
import math
import os
import re
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mwdialog_bsa import bsa_index  # noqa: E402
from mwdialog_records import height_at, land_heights, split_cell  # noqa: E402
from mwdialog_tes3 import FormatError, cstr, first_sub  # noqa: E402
from mwdialog_cellmods import FLOAT_ITEM_TAGS, FLOAT_TOLERANCE, float_items  # noqa: E402

RESCUE_DATA = "mwfloatfix_rescue.json"         # Data Files\MWSE\config\, read by the mwfloatfix MWSE mod

SUNK = -64.0                                    # lower than this under their feet, a person is in over the waist
REACH, RING_STEP = 128, 8                       # footing is looked for this far around, in rings this far apart
SAME_LEVEL = 64.0                               # new footing is at most this much above or below the old
WIDE_REACH, WIDE_STEP = 4096, 64                # then any dry footing this far around, across cell borders
CLIMB = 256.0                                   # out there, footing at most this much above or below the old first
SETTLE = 1024.0                                 # ...but footing at another height this much closer wins
SKY = 1e9
MOVE_CELLS = 16                                 # land a mod moved (an island set elsewhere) is looked for this far
LEVEL, STAND = 24.0, 24.0                       # footing: five probes this far apart, at most this uneven
FEET = 8.0                                      # what is right under someone: five probes this far apart
EYE = 64.0                                      # rays start this far over the feet
HEAD_ROOM = 128.0
UNREADABLE_NEAR = 1024.0                        # a model that can't be read this close: no telling what is there
NO_LAND = -2048.0                               # the game's ground in a cell without land

SUPPORT_TAGS = frozenset(("STAT", "ACTI", "CONT", "DOOR"))
STAND_ON_TAGS = frozenset(("STAT", "ACTI", "LAND"))     # not a crate or a door

BLOCK_RE = re.compile(rb"(?=([\x06-\x30]\x00\x00\x00)((?:Ni|RootCollisionNode|AvoidNode)[A-Za-z0-9]*))")
SHAPE = b"NiTriShape"
COLLISION_ROOT, AVOID = b"RootCollisionNode", b"AvoidNode"
NODE_TYPES = frozenset((b"NiNode", SHAPE, COLLISION_ROOT, AVOID, b"NiBSAnimationNode", b"NiBSParticleNode",
                        b"NiBillboardNode", b"NiCollisionSwitch", b"NiSwitchNode", b"NiLODNode"))
NO_COLLISION = (b"\x03\x00\x00\x00NCO", b"\x02\x00\x00\x00NC")


def nif_triangles(data):
    """The triangles an actor stands on in a Morrowind model (RootCollisionNode's, where it has one), or None
    when the model can't be read."""
    try:
        return _triangles(data)
    except (ValueError, IndexError, struct.error, RecursionError):
        return None


def _triangles(b):
    def u32(p):
        return struct.unpack_from("<I", b, p)[0]
    count = u32(b.index(b"\n") + 5)
    blocks, after = [], None
    for found in BLOCK_RE.finditer(b):
        size, word = u32(found.start()), found.group(2)
        if size > len(word) or found.start() == after:
            continue                             # the latter: a node's name that is spelt like a type
        after = found.start() + 4 + size
        blocks.append((word[:size], after))
    if len(blocks) != count:
        raise ValueError("blocks not found")
    nodes = {}
    for i, (kind, p) in enumerate(blocks):
        if kind not in NODE_TYPES:
            continue
        p += 4 + u32(p) + 8                      # name, extra data, controller
        hidden = struct.unpack_from("<H", b, p)[0] & 1
        transform = struct.unpack_from("<13f", b, p + 2)
        p += 2 + 52 + 12                         # flags, transform, velocity
        p += 4 + 4 * u32(p)                      # properties
        p += 4 + (64 if u32(p) else 0)           # bounding box
        kids = struct.unpack_from("<i", b, p) if kind == SHAPE else struct.unpack_from(f"<{u32(p)}i", b, p + 4)
        nodes[i] = (kind, hidden, transform, kids)
    rooted = any(n[0] == COLLISION_ROOT for n in nodes.values())
    if not rooted and any(mark in b for mark in NO_COLLISION):
        return []
    out = []

    def walk(i, chain, solid):
        if i not in nodes:
            return
        kind, hidden, transform, kids = nodes[i]
        if kind == AVOID:
            return
        solid = solid or kind == COLLISION_ROOT
        chain = [transform] + chain
        if kind != SHAPE:
            for k in kids[:1] if kind in (b"NiSwitchNode", b"NiLODNode") else kids:
                walk(k, chain, solid)
            return
        if (rooted and not solid) or (not rooted and hidden) or not 0 <= kids[0] < len(blocks):
            return
        data_kind, p = blocks[kids[0]]
        if data_kind != b"NiTriShapeData":
            return
        n, has_vertices = struct.unpack_from("<HI", b, p)
        p += 6
        if not has_vertices:
            return
        vs = list(struct.iter_unpack("<3f", b[p:p + 12 * n]))
        p += 12 * n
        for tx, ty, tz, a, c, d, e, f, g, h, j, k, s in chain:
            vs = [(tx + s * (a * x + c * y + d * z), ty + s * (e * x + f * y + g * z),
                   tz + s * (h * x + j * y + k * z)) for x, y, z in vs]
        p += 4 + (12 * n if u32(p) else 0) + 16  # normals, bounding sphere
        p += 4 + (16 * n if u32(p) else 0)       # colours
        uv_sets, has_uv = struct.unpack_from("<HI", b, p)
        p += 6 + (8 * n * uv_sets if has_uv else 0)
        faces = struct.unpack_from("<H", b, p)[0]
        p += 6
        out.extend((vs[u], vs[v], vs[w]) for u, v, w in struct.iter_unpack("<3H", b[p:p + 6 * faces]))
    children = {k for n in nodes.values() if n[0] != SHAPE for k in n[3]}
    for i in nodes:
        if i not in children:
            walk(i, [], False)
    return out


def to_world(pos, scale):
    """A model point -> where it is in the world, for a reference at pos (x, y, z and its three rotations)."""
    x0, y0, z0, rx, ry, rz = pos
    ca, sa = math.cos(-rx), math.sin(-rx)
    cb, sb = math.cos(-ry), math.sin(-ry)
    cc, sc = math.cos(-rz), math.sin(-rz)

    def place(v):                                # about z, then y, then x, as the game turns a reference
        a, b, c = v[0] * scale, v[1] * scale, v[2] * scale
        a, b = a * cc - b * sc, a * sc + b * cc
        a, c = a * cb + c * sb, -a * sb + c * cb
        b, c = b * ca - c * sa, b * sa + c * ca
        return a + x0, b + y0, c + z0
    return place


class ModelShapes:
    """Each model's collision triangles, read once, and those of the placed models looked at."""

    def __init__(self, data_dir, archives):
        self.read = model_reader(data_dir, archives)
        self.triangles = functools.cache(self._triangles)
        self.radius = functools.cache(self._radius)
        self.placed = functools.cache(self._placed)
        self.digest = functools.cache(self._digest)

    def _digest(self, model):
        """The model's bytes as a hash ("" for none): a replacer swapped in changes it."""
        data = self.read(model)
        return "" if data is None else hashlib.sha1(data).hexdigest()

    def _triangles(self, model):
        data = self.read(model)
        return None if data is None else nif_triangles(data)

    def _radius(self, model):
        return max((math.hypot(*v) for t in self.triangles(model) or () for v in t), default=0.0)

    def _placed(self, pos, scale, model):
        """(triangles in the world, their box), or None for nothing to stand on."""
        tris = self.triangles(model)
        if not tris:
            return None
        place, at = to_world(pos, scale), {}
        for t in tris:
            for v in t:
                if v not in at:
                    at[v] = place(v)
        xs, ys, zs = zip(*at.values())
        return [(at[u], at[v], at[w]) for u, v, w in tris], (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))

    def top(self, pos, scale, model):
        """The highest point of a placed model, or None when that can't be told."""
        tris = self.triangles(model) if model else None
        if not tris:
            return None
        place = to_world(pos, scale)
        return max(place(v)[2] for v in {v for t in tris for v in t})


def model_reader(data_dir, archives):
    """model path under Meshes -> its bytes or None: the loose file, else the last of the archives that has it."""
    packed = {}
    for bsa in archives:
        try:
            packed.update((name, (bsa, at)) for name, at in bsa_index(bsa).items() if name.startswith("meshes\\"))
        except (OSError, FormatError, struct.error):
            continue

    def read(model):
        try:
            with open(os.path.join(data_dir, "Meshes", model), "rb") as f:
                return f.read()
        except (OSError, ValueError):
            pass
        hit = packed.get("meshes\\" + model.replace("/", "\\").lower())    # archive names are lowercase
        if hit:
            try:
                with open(hit[0], "rb") as f:
                    f.seek(hit[1][0])
                    return f.read(hit[1][1])
            except OSError:
                pass
        return None
    return read


class Surfaces:
    """Placed models and the land: what is under a point."""

    def __init__(self, placed, land, shapes):
        self.land, self.shapes = land, shapes
        self.grid = defaultdict(list)
        for p in placed:                         # (position and rotation, scale, model, object, record type)
            self.grid[(int(p[0][0] // 2048), int(p[0][1] // 2048))].append(p)

    def near(self, x, y):
        gx, gy = int(x // 2048), int(y // 2048)
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                yield from self.grid.get((gx + dx, gy + dy), ())

    def unreadable(self, x, y):
        return next((p[3] for p in self.near(x, y) if math.dist(p[0][:2], (x, y)) <= UNREADABLE_NEAR
                     and self.shapes.triangles(p[2]) is None), None)

    def floor(self, x, y, top):
        """(height, object, record type) of the highest surface at (x, y) not above top."""
        h = self.land(x, y)
        best = (h, "land", "LAND") if h <= top else (-math.inf, "", "")
        for p in self.near(x, y):
            (px, py, pz), reach = p[0][:3], self.shapes.radius(p[2]) * abs(p[1])
            if (px - x) ** 2 + (py - y) ** 2 > reach * reach or pz - reach > top or pz + reach < best[0]:
                continue                         # too far to matter: not worth placing its triangles
            built = self.shapes.placed(*p[:3])
            if built is None:
                continue
            tris, (x1, x2, y1, y2, z1, z2) = built
            if x < x1 or x > x2 or y < y1 or y > y2 or z1 > top or z2 <= best[0]:
                continue
            for (ax, ay, az), (bx, by, bz), (cx, cy, cz) in tris:
                if (ax < x and bx < x and cx < x) or (ax > x and bx > x and cx > x):
                    continue
                det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
                if abs(det) < 1e-6:
                    continue                     # a wall
                u = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / det
                v = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / det
                if u < 0 or v < 0 or u + v > 1:
                    continue
                h = u * az + v * bz + (1 - u - v) * cz
                if best[0] < h <= top:
                    best = (h, p[3], p[4])
        return best

    def under(self, x, y, top):
        return max((self.floor(x + dx, y + dy, top)
                    for dx, dy in ((0, 0), (FEET, 0), (-FEET, 0), (0, FEET), (0, -FEET))), key=lambda f: f[0])

    def _spot(self, px, py, top):
        """(height, object) of a dry, level place to stand at (px, py) under top, or None."""
        h, what, tag = self.floor(px, py, top)
        if h < 0 or tag not in STAND_ON_TAGS:
            return None
        around = [self.floor(px + dx, py + dy, top)[0] for dx, dy in ((STAND, 0), (-STAND, 0), (0, STAND), (0, -STAND))]
        if min(around) < 0 or max(around + [h]) - min(around + [h]) > LEVEL:
            return None
        if self.floor(px, py, h + HEAD_ROOM)[0] > h + LEVEL:
            return None                          # inside or under something
        return h, what

    def stand_near(self, x, y, z, was, grid):
        """(x, y, height, object) of the closest place to stand, or None: level footing about as high in the cell
        within REACH; else the closest dry level footing within WIDE_REACH, anywhere, within CLIMB of the old
        height unless footing at another height is SETTLE closer."""
        top = max(z, was) + EYE
        for radius in range(0, REACH + 1, RING_STEP):
            spots = []
            for i in range(16 if radius else 1):
                px, py = x + radius * math.cos(i * math.pi / 8), y + radius * math.sin(i * math.pi / 8)
                if (math.floor(px / 8192), math.floor(py / 8192)) != grid:
                    continue
                s = self._spot(px, py, top)
                if s and abs(s[0] - was) <= SAME_LEVEL:
                    spots.append((abs(s[0] - was), px, py, *s))
            if spots:
                return min(spots)[1:]
        other, other_at, radius = None, 0, RING_STEP
        while radius <= WIDE_REACH:
            if other and radius > other_at + SETTLE:
                return other
            n = max(16, math.ceil(2 * math.pi * radius / WIDE_STEP))
            spots = []
            for i in range(n):
                px, py = x + radius * math.cos(i * 2 * math.pi / n), y + radius * math.sin(i * 2 * math.pi / n)
                s = self._spot(px, py, SKY)
                if s:
                    spots.append((abs(s[0] - was), px, py, *s))
            near = [s for s in spots if s[0] <= CLIMB]
            if near:
                return min(near)[1:]
            if spots and other is None:
                other, other_at = min(spots)[1:], radius
            radius += RING_STEP if radius < REACH else WIDE_STEP
        return other


def _ref_key(block, masters, own):
    if len(block[0][1]) < 4:                     # FRMR, or MVRF for one moved to another cell
        return None
    v = struct.unpack_from("<I", block[0][1])[0]
    k = v >> 24
    owner = own if k == 0 else (masters[k - 1] if k <= len(masters) else None)
    return (owner, v & 0xFFFFFF) if owner else None


def _state(blocks):
    """(position and rotation, scale, object, deleted) of a reference after these versions of it, in load order."""
    pos, scale, oid, dele = None, 1.0, "", False
    for blk in blocks:
        dele = False
        for s, d in blk:
            if s == "DATA" and len(d) >= 24:
                pos = struct.unpack_from("<6f", d)
            elif s == "XSCL" and len(d) >= 4:
                scale = struct.unpack_from("<f", d)[0]
            elif s == "NAME":
                oid = cstr(d).lower()
            elif s == "DELE":
                dele = True
    return pos, scale, oid, dele


class Placements:
    """The exterior cells and land of a load order, read only around the places asked about."""

    def __init__(self, order, ext_recs, land_vers, masters_of):
        self.order, self.ext_recs, self.land_vers, self.masters_of = order, ext_recs, land_vers, masters_of
        self.names = [n.lower() for n, _p in order]
        self._knows, self._cells, self._around, self._heights = {}, {}, {}, {}

    def knows(self, name):
        if name not in self._knows:
            seen, stack = {name}, list(self.masters_of.get(name, []))
            while stack:
                x = stack.pop()
                if x not in seen:
                    seen.add(x)
                    stack += self.masters_of.get(x, [])
            self._knows[name] = seen
        return self._knows[name]

    def _record(self, pi, off):
        with open(self.order[pi][1], "rb") as f:
            f.seek(off + 4)
            size = struct.unpack("<I", f.read(4))[0]
            f.seek(off + 16)
            return f.read(size)

    def cell(self, g):
        if g not in self._cells:
            rows = self._cells[g] = []
            for pi, off in self.ext_recs.get(g, ()):
                own = self.names[pi]
                _head, pers, _n0, temp = split_cell(self._record(pi, off), off)
                for grp, blocks in (("p", pers), ("t", temp)):
                    for blk in blocks:
                        bk = _ref_key(blk, self.masters_of.get(own, []), own)
                        if bk:
                            rows.append((pi, bk, g, grp, blk))
        return self._cells[g]

    def around(self, g):
        """ref key -> [(plugin, cell, group, block)] in load order, in this cell and the eight around it."""
        if g not in self._around:
            found = defaultdict(list)
            rows = [r for dx in (-1, 0, 1) for dy in (-1, 0, 1) for r in self.cell((g[0] + dx, g[1] + dy))]
            for pi, bk, cell, grp, blk in sorted(rows, key=lambda r: r[0]):
                found[bk].append((self.names[pi], cell, grp, blk))
            self._around[g] = found
        return self._around[g]

    def may_be_wet(self, g):
        """Some of cell g's land in use is deep enough to be in over the waist."""
        h = self._land_of(g)
        return h is None or min(h) < SUNK

    def _land_of(self, g, known=None):
        v = next((v for v in reversed(self.land_vers.get(g, ()))
                  if known is None or self.names[v[0]] in known), None)
        if v is None:
            return None
        key = (v[0], v[2])
        if key not in self._heights:
            self._heights[key] = land_heights(first_sub(self._record(v[0], v[2]), b"VHGT"))
        return self._heights[key]

    def moved_land(self, g, known):
        """(dx, dy) in cells when the land a plugin knowing only `known` had at g was put, unchanged, in exactly
        one other cell within MOVE_CELLS (a mod moved the island; later mods may touch it up there), else None."""
        v = next((v for v in reversed(self.land_vers.get(g, ())) if self.names[v[0]] in known), None)
        if v is None or self.land_vers[g][-1][1] == v[1]:
            return None
        hits = [(c[0] - g[0], c[1] - g[1]) for c, vs in self.land_vers.items()
                if any(x[1] == v[1] for x in vs) and c != g and max(abs(c[0] - g[0]), abs(c[1] - g[1])) <= MOVE_CELLS]
        return hits[0] if len(hits) == 1 else None

    def versions(self, g, bk):
        """The versions of one reference in cell g, as around() gives them."""
        return [(self.names[pi], cell, grp, blk) for pi, key, cell, grp, blk in self.cell(g) if key == bk]

    def land(self, known=None):
        """(x, y) -> the land's height: the land in use, or the one a plugin knowing only `known` was made on."""
        def at(x, y):
            g = (math.floor(x / 8192), math.floor(y / 8192))
            h = height_at(self._land_of(g, known), g, x, y)
            return NO_LAND if h is None else h
        return at


def surfaces_of(world, patched, tag_of, model_of, shapes):
    """grid, known -> the Surfaces around that exterior cell: with the patch's versions (known None), or as a plugin
    knowing only `known` saw them."""
    @functools.cache
    def surfaces(g, known=None):
        placed = []
        for bk, vers in world.around(g).items():
            blocks = [v[3] for v in vers if known is None or v[0] in known]
            if known is None:
                blocks += [patched[ck][bk][1] for ck in {("e", v[1][0], v[1][1]) for v in vers}
                           if bk in patched.get(ck, ())]
            if not blocks:
                continue
            pos, scale, oid, dele = _state(blocks)
            tag, model = tag_of.get(oid), model_of.get(oid)
            if dele or not pos or tag not in SUPPORT_TAGS or not model:
                continue
            if "editormarker" in model or model.startswith("marker_"):
                continue
            placed.append((pos, scale, model, oid, tag))
        return Surfaces(placed, world.land(known), shapes)
    return surfaces


FLOAT_MAX_DROP = 160.0                          # mwfloatfix's maxDrop: further down than this, it isn't the floor
FLOAT_REST = 0.5                                # left this far over the floor, as mwfloatfix does: no sinking in


def find_float_drops(world, grids, patched, tag_of, model_of, shapes, ours_name, esm_only=frozenset(),
                     tol=FLOAT_TOLERANCE, max_drop=FLOAT_MAX_DROP):
    """(drops, left) for the loose items in the exterior cells `grids` left hanging over what a plugin their own
    plugin doesn't know took away (float_items, with the patch's versions as the last word): each is put down on
    the highest surface under it, the land or a placed model's collision, when that is between tol and max_drop
    below it, dry, and no model nearby that can't be read could be in the way. The same fix mwfloatfix makes in
    the game, made once in the patch, so it holds in every save and needs no ray test.
      drops: (ref key, cell key, group, block) to write in the patch, with the new height
      left:  what was found and not moved, as text
    patched: what the patch already changes, cell key -> {ref key: (group, block)}; ours_name: the patch (lower).
    Interiors aren't looked at: Placements reads only the exterior cells."""
    n = len(world.names)
    ref_hist, land_v, finals = {}, {}, {}
    for g in sorted(grids):
        key = ("e",) + tuple(g)
        refs, blocks = defaultdict(list), defaultdict(list)
        for pi, bk, _cell, grp, blk in world.cell(g):
            if blk[0][0] == "MVRF":
                refs[bk].append(None)                     # moved between cells: left to the game
                continue
            pos, scale, oid, dele = _state([blk])
            refs[bk].append((pi, world.names[pi], oid, pos[:3] if pos else None, scale, dele))
            blocks[bk].append((grp, blk))
        for bk, (grp, blk) in patched.get(key, {}).items():
            pos, scale, oid, dele = _state([blk])
            refs[bk].append((n, ours_name, oid, pos[:3] if pos else None, scale, dele))
            blocks[bk].append((grp, blk))
        refs = {bk: vs for bk, vs in refs.items() if None not in vs}
        ref_hist[key] = refs
        for bk, vs in refs.items():
            last = vs[-1]
            if not last[5] and last[3] and tag_of.get(last[2]) in FLOAT_ITEM_TAGS:
                x, y, z = last[3]
                ck = f"#{int(math.floor(x / 8192))},{int(math.floor(y / 8192))}"
                finals[(ck, last[2], int(math.floor(x + 0.5)), int(math.floor(y + 0.5)), int(math.floor(z + 0.5)))] = \
                    (g, bk, blocks[bk])
        lv = world.land_vers.get(g, ())
        if len(lv) > 1:
            land_v[g] = [(pi, world.names[pi], first_sub(world._record(pi, off), b"VHGT")) for pi, _d, off in lv]
    found = float_items(ref_hist, land_v, world.knows, tag_of, tol=tol, ours=frozenset({ours_name}),
                        esm_only=frozenset(esm_only))
    surfaces = surfaces_of(world, patched, tag_of, model_of, shapes)
    drops, left = [], []
    for ck, hits in sorted(found.items()):
        for k, (author, why) in sorted(hits.items()):
            hit = finals.get((ck,) + k)
            if hit is None:
                continue
            g, bk, vers = hit
            grp, blk = vers[-1]
            pos, scale, oid, _dele = _state([b for _g, b in vers])
            x, y, z = pos[:3]
            where = f"{oid} ({ck}, from {author}; {why})"
            box = shapes.placed(tuple(pos), scale, model_of[oid]) if model_of.get(oid) else None
            bottom = box[1][4] if box else z
            now = surfaces(g)
            probes = [(x, y)]
            if box:
                x1, x2, y1, y2 = box[1][:4]
                probes += [(x + (cx - x) * 0.7, y + (cy - y) * 0.7) for cx in (x1, x2) for cy in (y1, y2)]
            h, what, _tag = max((now.floor(px, py, bottom + tol) for px, py in probes), key=lambda f: f[0])
            gap = bottom - h
            if gap <= tol:
                continue                                  # resting on something after all
            cant_tell = now.unreadable(x, y)
            if cant_tell:
                left.append(f"{where}: {cant_tell}'s model can't be read, so it may be resting on it")
                continue
            if gap > max_drop:
                left.append(f"{where}: nothing to rest on within {max_drop:.0f} units below it")
                continue
            if h < 0:
                left.append(f"{where}: what is under it ({what}) is under water")
                continue
            new_z = z - gap + FLOAT_REST
            data = next(d for s_, d in blk if s_ == "DATA" and len(d) >= 24)
            data = data[:8] + struct.pack("<f", new_z) + data[12:]
            new = [[s_, data if s_ == "DATA" and len(d) >= 24 else d] for s_, d in blk]
            drops.append((bk, ("e",) + tuple(g), grp, new, f"{where}: down {gap - FLOAT_REST:.0f} onto {what} "
                                                          f"(z {z:.1f} -> {new_z:.1f})"))
    return drops, left


def find_footing(world, npcs, patched, kept_dry, tag_of, model_of, shapes):
    """(moves, rescue, left) for the living exterior NPCs in npcs (ref key -> grid):
      moves:  (ref key, cell key, group, block) to write in the patch
      rescue: what mwfloatfix puts right in a save made while they were under water
      left:   what was found and not moved, as text
    patched: what the patch already changes, cell key -> {ref key: (group, block)}. kept_dry: the references
    kept from following land under the sea."""
    surfaces = surfaces_of(world, patched, tag_of, model_of, shapes)

    final_land = world.land()
    moves, rescue, left = [], [], []
    for bk, g in sorted(npcs.items()):
        if not world.may_be_wet(g):
            continue
        vers = world.versions(g, bk)
        if not vers or any(v[3][0][0] == "MVRF" for v in vers):
            continue
        placed_at, _scale, oid, dele = _state([v[3] for v in vers])
        if dele or not placed_at:
            continue
        ck = ("e", g[0], g[1])
        base = patched[ck][bk][1] if bk in patched.get(ck, ()) else None
        pos, _scale, _oid, dele = _state([v[3] for v in vers] + ([base] if base else []))
        x, y, z = pos[:3]
        if dele or z < SUNK or final_land(x, y) >= SUNK:
            continue
        now = surfaces(g)
        if now.under(x, y, z + EYE)[0] >= SUNK:
            if bk in kept_dry:                   # an older patch put this one under, and saves keep that
                rescue.append(_rescue(oid, g, placed_at[:3], (x, y, z)))
            continue
        author = next((v[0] for v in vers if _state([v[3]])[0] == placed_at), vers[-1][0])
        was, stood_on, kind = surfaces(g, frozenset(world.knows(author))).under(*placed_at[:2], placed_at[2] + EYE)
        if was < SUNK:
            continue                             # never had footing that could be found: a swimmer, or placed so
        where = f"{oid} (#{g[0]},{g[1]}, from {author})"
        cant_tell = now.unreadable(x, y) if kind != "LAND" else None
        if cant_tell:
            left.append(f"{where}: {stood_on} is gone, but {cant_tell}'s model can't be read, so there may be footing")
            continue
        spot = None
        off = world.moved_land(g, frozenset(world.knows(author))) if kind == "LAND" else None
        if off:                                  # the same spot where the island is now
            g2 = (g[0] + off[0], g[1] + off[1])
            spot = surfaces(g2).stand_near(placed_at[0] + off[0] * 8192, placed_at[1] + off[1] * 8192,
                                           placed_at[2], was, g2)
        if spot is None:
            spot = now.stand_near(x, y, z, was, g)
        if spot is None:
            lost = "the land they stood on is under the sea now" if kind == "LAND" else f"{stood_on} is gone"
            left.append(f"{where}: {lost}, and there is no dry footing within {WIDE_REACH} units")
            continue
        blk = base or next((v[3] for v in reversed(vers) if any(s == "DATA" and len(d) >= 24 for s, d in v[3])), None)
        if blk is None:
            continue
        px, py, h, _what = spot
        to = (px, py, h + 3.0)
        data = struct.pack("<6f", *to, *pos[3:])
        new = [[s, data + d[24:] if s == "DATA" and len(d) >= 24 else d] for s, d in blk
               if s not in ("MVRF", "CNDT", "CNAM")]
        g_to = (math.floor(px / 8192), math.floor(py / 8192))
        if g_to != g:                            # into the cell the spot is in, so it loads with that cell
            new = [["MVRF", new[0][1]], ["CNDT", struct.pack("<ii", *g_to)]] + new
        moves.append((bk, ck, vers[-1][2], new))
        rescue.append(_rescue(oid, g, placed_at[:3], to))
    return moves, rescue, left


def _rescue(oid, g, was, to):
    return {"id": oid, "cell": f"#{g[0]},{g[1]}", "from": [round(v) for v in was], "to": [round(v) for v in to]}


def write_rescue_data(data_dir, rescue, left):
    out_dir = os.path.join(data_dir, "MWSE", "config")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, RESCUE_DATA)
    payload = {"version": 1, "generated": time.strftime("%Y-%m-%d %H:%M:%S"), "npcs": rescue, "left": left}
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)
