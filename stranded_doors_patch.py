"""Builds "Stranded Doors - DRPV Patch.esp": puts two load doors that Dwemer Ruins Plus (DRPV1.9.ESP) left
in the void back into DRPV's rebuilt layout, each against a corridor end DRPV sealed with a wall panel.

  Mzahnch   Suran Underworld's door to the Goblin Fortress (with its frame, light and the quest wall
            a_ga_blockwall, which seals the doorway until SuranQuests reaches 25). Goes on the west edge of
            DRPV's first big hall. Its old corridor stub, now in the void, is deleted.
  Nchuleft  Rise of House Telvanni's door to "Nchuleft, Lower Level" (with its quest rubble, cleared at
            RoHT_EdwinnaQuests 80, and the DN tileset light over it). Goes at a sealed corridor end near
            DRPV's own way down; a door frame is added.

The doors on the other side (Goblin Fortress, Nchuleft Lower Level) are pointed at the new spots.
Each group is moved as one piece (turned and shifted), so everything keeps its place relative to the
door. Run with the game's Python from this folder:  python stranded_doors_patch.py
"""
import math, os, struct, sys, time, importlib.util

GAME = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(GAME, "Data Files")
spec = importlib.util.spec_from_file_location("mwd", os.path.join(GAME, "mwdialog_check.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
OUT = "Stranded Doors - DRPV Patch.esp"

SURAN, ROHT, MW, DNT = "suran_underworld_v3.esp", "rise of house telvanni.esm", "morrowind.esm", "dn_dwemer_tileset.esm"

# group: cell, anchor ref, new anchor position, turn (radians), members moved rigidly
GROUPS = [
    {"cell": "mzahnch", "anchor": (SURAN, 554), "to": (7392.0, 1536.0, 1504.0), "turn": math.pi,
     "move": [(SURAN, 554), (SURAN, 550), (SURAN, 553)],
     # the quest wall: right in front of the doorway, like DRPV's own wall panels
     "place": {(SURAN, 549): ((40.0, 0.0, 0.0), (0.0, 0.0, 0.0))},
     "delete": [(SURAN, 551), (SURAN, 552), (MW, 206015)],
     "arrive": {"cell": "goblin fortress", "door": (SURAN, 3950), "offset": (90.0, 0.0, -48.0), "face": math.pi / 2}},
    {"cell": "nchuleft", "anchor": (ROHT, 886), "to": (3730.0, -6496.0, 114.0), "turn": math.pi,
     "move": [(ROHT, 886)] + [(ROHT, i) for i in range(889, 921)] + [(DNT, 37)],
     "place": {}, "delete": [],
     "new": [("in_dwrv_doorjam00", (3736.0, -6496.0, 144.0), (0.0, 0.0, math.pi / 2))],
     "arrive": {"cell": "nchuleft, lower level", "door": (ROHT, 4877), "rigid": True}},
]


def main():
    order = [l.strip() for l in open(os.path.join(GAME, "mwdialog_load_order.txt"), encoding="utf-8")
             if l.strip() and not l.startswith(";") and l.strip().lower() != OUT.lower()]
    pos = {n.lower(): i for i, n in enumerate(order)}
    cells = {g["cell"] for g in GROUPS} | {g["arrive"]["cell"] for g in GROUPS}
    heads = {}                     # cell -> latest head subrecords
    blocks = {}                    # (cell, owner, idx) -> latest block
    group = {}                     # (cell, owner, idx) -> "p" / "t" as the owner itself lists it
    for n in order:
        p = os.path.join(DATA, n)
        if not os.path.exists(p):
            continue
        data = open(p, "rb").read()
        mast = [x.lower() for x in m.plugin_masters(data)]
        for off, tag, fl, body in m.iter_records(data):
            if tag != "CELL":
                continue
            key, label = m.cell_key(body)
            lab = (label or "").lower()
            if key is None or key[0] != "i" or lab not in cells:
                continue
            head, pers, _n0, temp = m.split_cell(body)
            # the latest full header (with the lighting): a short one would leave the place unlit
            if lab not in heads or any(s[0] == "AMBI" for s in head):
                heads[lab] = head
            for grp, blks in (("p", pers), ("t", temp)):
                for b in blks:
                    bk = m.block_key(b, mast, n.lower())
                    if bk:
                        blocks[(lab, bk[0], bk[1])] = [list(s) for s in b]
                        if bk[0] == n.lower():
                            group[(lab, bk[0], bk[1])] = grp

    def get(cell, ref):
        b = blocks.get((cell, ref[0], ref[1]))
        if b is None:
            sys.exit(f"Not found: {ref} in {cell}. Has the load order changed? Nothing written.")
        if any(s[0] == "DELE" for s in b):
            sys.exit(f"{ref} in {cell} is deleted by a later plugin. Nothing written.")
        return b

    def sub(b, name):
        return next((s for s in b if s[0] == name), None)

    out = {}                       # cell -> {(owner, idx) or ("", n): block}
    for g in GROUPS:
        c = g["cell"]
        ax = struct.unpack_from("<6f", sub(get(c, g["anchor"]), "DATA")[1])
        t, (nx, ny, nz) = g["turn"], g["to"]
        ct, st = math.cos(t), math.sin(t)

        def tf(x, y, z):
            dx, dy = x - ax[0], y - ax[1]
            return nx + dx * ct - dy * st, ny + dx * st + dy * ct, nz + (z - ax[2])

        for ref in g["move"]:
            b = get(c, ref)
            d = sub(b, "DATA")
            x, y, z, rx, ry, rz = struct.unpack_from("<6f", d[1])
            x, y, z = tf(x, y, z)
            d[1] = struct.pack("<6f", x, y, z, rx, ry, (rz + t) % (2 * math.pi)) + d[1][24:]
            out.setdefault(c, {})[ref] = b
        jam = out[c].get(g["anchor"])
        jx, jy, jz = struct.unpack_from("<3f", sub(jam, "DATA")[1])
        for ref, ((ox, oy, oz), rot) in g["place"].items():
            b = get(c, ref)
            d = sub(b, "DATA")
            d[1] = struct.pack("<6f", jx + ox, jy + oy, jz + oz, *rot) + d[1][24:]
            out[c][ref] = b
        for ref in g["delete"]:
            b = blocks.get((c, ref[0], ref[1]))
            if b is None or any(s[0] == "DELE" for s in b):
                continue
            nb = [s for s in b if s[0] != "DATA"] + [["DELE", b"\0\0\0\0"]] + [s for s in b if s[0] == "DATA"]
            out[c][ref] = nb
        for i, (oid, p, r) in enumerate(g.get("new", ())):
            out[c][("", i + 1)] = [["FRMR", b""], ["NAME", oid.encode("cp1252") + b"\0"],
                                   ["DATA", struct.pack("<6f", *p, *r)]]
        a = g["arrive"]
        db = get(a["cell"], a["door"])
        dd = sub(db, "DODT")
        x, y, z, rx, ry, rz = struct.unpack_from("<6f", dd[1])
        if a.get("rigid"):
            x, y, z = tf(x, y, z)
            rz = (rz + t) % (2 * math.pi)
        else:
            ox, oy, oz = a["offset"]          # from the door frame; here the room lies to +x
            x, y, z, rz = jx + ox, jy + oy, jz + oz, a["face"]
        dd[1] = struct.pack("<6f", x, y, z, rx, ry, rz) + dd[1][24:]
        out.setdefault(a["cell"], {})[a["door"]] = db

    owners = {o for refs in out.values() for (o, _i) in refs if o}
    owners.add(MW)
    masters = sorted(owners, key=lambda o: pos[o])
    name_of = {n.lower(): n for n in order}
    mindex = {o: i + 1 for i, o in enumerate(masters)}
    recs = []
    for c in sorted(out):
        refs = out[c]
        body = b"".join(m.pack_sub(n, d) for n, d in heads[c])
        # each master reference stays in the group its owner keeps it in: the game looks for it there only
        # (an .esp master's temporary reference listed as persistent is "missing in master file")
        pers, temp = [], []
        for (o, i), b in sorted(refs.items(), key=lambda kv: (kv[0][0] == "", kv[0][1])):
            frmr = struct.pack("<I", ((mindex[o] << 24) | i) if o else i)
            parts = [m.pack_sub("FRMR", frmr)] + [m.pack_sub(n, d) for n, d in b
                                                  if n not in ("FRMR", "MVRF", "CNDT", "NAM0")]
            (pers if o and group.get((c, o, i)) == "p" else temp).append(b"".join(parts))
        body += b"".join(pers)
        if temp:
            body += m.pack_sub("NAM0", struct.pack("<I", len(temp))) + b"".join(temp)
        recs.append(b"CELL" + struct.pack("<III", len(body), 0, 0) + body)
    path = os.path.join(DATA, OUT)
    log = []
    m.write_patch(path, [], [(name_of[o], os.path.join(DATA, name_of[o])) for o in masters], log,
                  extra=recs, description="Puts load doors DRPV left in the void back into its layout")
    newest = m.next_free_date(DATA, OUT)
    if newest:
        os.utime(path, (newest, newest))
    print(f"Wrote {OUT}: {sum(len(v) for v in out.values())} reference(s) in {len(out)} cell(s); masters: "
          + ", ".join(name_of[o] for o in masters))
    for c, refs in sorted(out.items()):
        for (o, i), b in refs.items():
            d = sub(b, "DATA")
            what = "deleted" if sub(b, "DELE") else ("moved to %.0f, %.0f, %.0f" % struct.unpack_from("<3f", d[1]))
            if sub(b, "DODT") and c in (GROUPS[0]["arrive"]["cell"], GROUPS[1]["arrive"]["cell"]):
                what = "now arrives at %.0f, %.0f, %.0f" % struct.unpack_from("<3f", sub(b, "DODT")[1])
            print(f"  {c}: {m.cstr(sub(b, 'NAME')[1])} ({o or 'new'} #{i}) {what}")


if __name__ == "__main__":
    main()
