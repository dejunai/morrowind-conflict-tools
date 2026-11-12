"""Builds "Chargen Ship - Original Model.esp": the chargen ship (and its trapdoors) get their own copy of the
original-shaped model. RR Better Ships n Boats replaces Meshes\\x\\ex_de_ship.nif with a differently shaped
ship; the chargen scene (vanilla and Tamriel Rebuilt - Alternate Start) is laid out around the original, so
crates float, the gangplank misses the deck and you can't walk off. Other ships keep RR's model.
Models used (in Data Files, not managed by Vortex):
  Meshes\\x\\mwfix_chargen_de_ship.nif       Correct Meshes' ex_de_ship.nif (original shape, fixed)
  Meshes\\d\\mwfix_cg_trapdoor.nif  the game's own ex_de_ship_trapdoor.nif (from Morrowind.bsa)
Run with Python from this folder:  python chargen_ship_patch.py
"""
import os, re, sys, struct, importlib.util
GAME = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(GAME, "Data Files")
spec = importlib.util.spec_from_file_location("mwd", os.path.join(GAME, "mwdialog_check.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
OUT = "Chargen Ship - Original Model.esp"
NEW = {"chargen boat": "x\\mwfix_chargen_de_ship.nif",
       "chargen_ship_trapdoor": "d\\mwfix_cg_trapdoor.nif",
       "chargen_shipdoor": "d\\mwfix_cg_trapdoor.nif"}
for rel in set(NEW.values()):
    if len(rel) > 31:
        sys.exit(f"Meshes\\{rel}: longer than the 31 characters a model path may have. Nothing written.")
    if not os.path.exists(os.path.join(DATA, "Meshes", *rel.split("\\"))):
        sys.exit(f"Missing Meshes\\{rel}. Nothing written.")

order = [n for n in (m.read_load_order(type("A", (), {"ini": os.path.join(GAME, "Morrowind.ini"),
                                                      "data_dir": DATA})()) or []) if n.lower() != OUT.lower()]
latest, owner = {}, {}
for n in order:
    p = os.path.join(DATA, n)
    if not os.path.exists(p):
        continue
    data = open(p, "rb").read()
    for off, tag, fl, body in m.iter_records(data):
        if tag in ("ACTI", "DOOR", "STAT"):
            oid = m.cstr(m.first_sub(body, b"NAME") or b"").lower()
            if oid in NEW:
                latest[oid] = (tag, fl, body); owner[oid] = n
recs = []
for oid, (tag, fl, body) in latest.items():
    out = b""
    p = 0
    while p < len(body):
        sn = body[p:p + 4]; sz = struct.unpack_from("<I", body, p + 4)[0]; d = body[p + 8:p + 8 + sz]
        if sn == b"MODL":
            d = NEW[oid].encode("cp1252") + b"\0"
        out += sn + struct.pack("<I", len(d)) + d
        p += 8 + sz
    recs.append(tag.encode() + struct.pack("<III", len(out), 0, fl) + out)
    print(f"  {oid} ({tag}, from {owner[oid]}) -> Meshes\\{NEW[oid]}")
# RR Better Ships builds its own chargen ship at Seyda Neen (-2, -9) out of pieces ("chargen boat_1".."_7")
# and hides the vanilla one; Tamriel Rebuilt - Alternate Start puts the vanilla ship back. Both then show,
# one inside the other: delete RR's pieces there (only when TR Alternate Start is loaded).
RR = "rr_better_ships_n_boats_eng.esp"
low_order = {n.lower(): n for n in order}
def cell_blocks(plugin_name):
    """{(cell key, owner, index): block} for one plugin, and {cell key: head}."""
    d = open(os.path.join(DATA, low_order[plugin_name]), "rb").read()
    ms = [x.lower() for x in m.plugin_masters(d)]
    out, heads = {}, {}
    for off, tag, fl, body in m.iter_records(d):
        if tag != "CELL":
            continue
        key = m.cell_key(body)[0]
        head, pers, _n0, temp = m.split_cell(body)
        heads.setdefault(key, head)
        for blk in pers + temp:
            bk = m.block_key(blk, ms, plugin_name)
            if bk:
                out[(key, bk[0], bk[1])] = blk
    return out, heads


cell_dels = []                       # (cell head subrecords, [(RR ref index, object id)])
restore = {}                         # cell key -> [vanilla block] for chargen objects RR moved and TRAS doesn't
if RR in low_order and "tamriel rebuilt - alternate start.esp" in low_order:
    rr_data = open(os.path.join(DATA, low_order[RR]), "rb").read()
    rr_masters = [x.lower() for x in m.plugin_masters(rr_data)]
    for off, tag, fl, body in m.iter_records(rr_data):
        if tag != "CELL" or m.cell_key(body)[0] != ("e", -2, -9):
            continue
        head, pers, _n0, temp = m.split_cell(body)
        dels = []
        for blk in pers + temp:
            oid = m.cstr(next((d for s_, d in blk if s_ == "NAME"), b"")).lower()
            bk = m.block_key(blk, rr_masters, RR)
            if re.match(r"chargen boat_\d$", oid) and bk and bk[0] == RR:
                dels.append((bk[1], oid))
        if dels:
            cell_dels.append((head, dels))
if cell_dels:
    rr_b, rr_heads = cell_blocks(RR)
    tr_b, _h = cell_blocks("tamriel rebuilt - alternate start.esp")
    mw_b, _h2 = cell_blocks("morrowind.esm")
    for (key, own, idx), blk in rr_b.items():
        oid = m.cstr(next((d for s_, d in blk if s_ == "NAME"), b"")).lower()
        if own != "morrowind.esm" or not oid.startswith("chargen") or (key, own, idx) in tr_b:
            continue
        van = mw_b.get((key, own, idx))
        if van is not None and m.cstr(next((d for s_, d in van if s_ == "NAME"), b"")).lower() == oid:
            restore.setdefault(key, []).append((idx, van, rr_heads.get(key)))
            print(f"  put '{oid}' back where Morrowind.esm has it (RR moved it for its own ship)")
masters = []
for n in order:
    if n.lower() == "morrowind.esm" or n.lower() in {o.lower() for o in owner.values()} \
            or (cell_dels and n.lower() == RR):
        masters.append((n, os.path.join(DATA, n)))
mindex = {n.lower(): i + 1 for i, (n, _p) in enumerate(masters)}
for head, dels in cell_dels:
    hb = b"".join(m.pack_sub(n_, d_) for n_, d_ in head if n_ in ("NAME", "DATA", "RGNN"))
    for idx, van, _hd in restore.pop(("e", -2, -9), []):
        hb += m.pack_sub("FRMR", struct.pack("<I", (mindex["morrowind.esm"] << 24) | idx))
        hb += b"".join(m.pack_sub(n_, d_) for n_, d_ in van if n_ not in ("FRMR", "MVRF", "CNDT", "NAM0"))
    for idx, oid in dels:
        hb += (m.pack_sub("FRMR", struct.pack("<I", (mindex[RR] << 24) | idx)) +
               m.pack_sub("NAME", oid.encode() + b"\0") + m.pack_sub("DELE", b"\0\0\0\0"))
        print(f"  delete RR's '{oid}' (#{idx}) at Seyda Neen (-2, -9)")
    recs.append(b"CELL" + struct.pack("<III", len(hb), 0, 0) + hb)
for key, items in restore.items():                 # other cells RR rearranged (rare)
    hd = items[0][2] or []
    hb = b"".join(m.pack_sub(n_, d_) for n_, d_ in hd if n_ in ("NAME", "DATA", "RGNN"))
    for idx, van, _hd in items:
        hb += m.pack_sub("FRMR", struct.pack("<I", (mindex["morrowind.esm"] << 24) | idx))
        hb += b"".join(m.pack_sub(n_, d_) for n_, d_ in van if n_ not in ("FRMR", "MVRF", "CNDT", "NAM0"))
    recs.append(b"CELL" + struct.pack("<III", len(hb), 0, 0) + hb)
m.write_patch(os.path.join(DATA, OUT), [], masters, [], extra=recs,
              description="Chargen ship keeps its original-shaped model (other ships unchanged)")
newest = m.next_free_date(DATA, OUT)
if newest:
    os.utime(os.path.join(DATA, OUT), (newest, newest))
print(f"Wrote {OUT}; masters: " + ", ".join(n for n, _ in masters))
