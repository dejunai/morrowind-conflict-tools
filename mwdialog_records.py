"""mwdialog_records.py - working on single records: ids and digests, splitting and cleaning CELL records,
renumbering references, leveled-list and object merging, and what a plugin defines and refers to.
"""
from collections import Counter, defaultdict
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_text as MT  # noqa: E402
import mwdialog_tes3 as _T  # noqa: E402
from mwdialog_tes3 import (  # noqa: E402
    ENAM_TAGS, MW_ERRORS, cstr, digest, first_sub, iter_records,
    iter_subs, pack_sub, plugin_masters, read_plugin_bytes, record_id)
print = MT.printer()  # noqa: A001


def rewrite_cell_refs(body, off, drops, moves):
    """Rebuild a CELL body: remove reference blocks whose FRMR is in `drops`, and move blocks whose FRMR
    is in `moves` (FRMR -> True for temporary, False for persistent). A block runs from its MVRF or FRMR
    to the next one. NAM0 (count of temporary references) is kept in step. Returns (new body, changes)."""
    head, persistent, temporary, nam0 = [], [], [], None
    block, in_temp = None, False

    def flush():
        if block is not None:
            (temporary if in_temp else persistent).append(block)

    for n, d in iter_subs(body, off):
        starts_mvrf_frmr = block and block[0][0] == "MVRF" and not any(x[0] == "FRMR" for x in block)
        if n == "MVRF" or (n == "FRMR" and not starts_mvrf_frmr):
            flush()
            block = [[n, d]]
        elif n == "NAM0":
            flush()
            block, in_temp, nam0 = None, True, d
        elif block is not None:
            block.append([n, d])
        else:
            head.append([n, d])
    flush()

    def frmr(b):
        for n, d in b:
            if n == "FRMR" and len(d) >= 4:
                return struct.unpack_from("<I", d)[0]
        return None

    changes, temp_delta = 0, 0
    new_p, new_t = [], []
    for group, is_temp in ((persistent, False), (temporary, True)):
        for b in group:
            v = frmr(b)
            if v in drops:
                changes += 1
                temp_delta -= 1 if is_temp else 0
                continue
            dest = moves.get(v, is_temp)
            if dest != is_temp:
                changes += 1
                temp_delta += 1 if dest else -1
            (new_t if dest else new_p).append(b)
    if not changes:
        return body, 0
    out = head + [x for b in new_p for x in b]
    if new_t or nam0 is not None:
        count = (struct.unpack_from("<I", nam0)[0] if nam0 and len(nam0) >= 4 else 0) + temp_delta
        out.append(["NAM0", struct.pack("<I", max(0, count))])
        out += [x for b in new_t for x in b]
    return b"".join(pack_sub(n, d) for n, d in out), changes


def extract_record(path, tag, oid):
    """Raw bytes of the last record of this type with this NAME in a plugin (None if absent)."""
    found = None
    with open(path, "rb") as f:
        data = f.read()
    for off, t, _flags, body in iter_records(data):
        if t == tag:
            nm = first_sub(body, b"NAME")
            if nm is not None and cstr(nm).lower() == oid:
                found = data[off:off + 16 + len(body)]
    return found


def record_refs(tag, body):
    """The script, enchantment and inventory item names a record uses."""
    refs = {}
    for n, d in iter_subs(body):
        if n == "SCRI":
            refs["SCRI"] = cstr(d)
        elif n == "ENAM" and tag in ENAM_TAGS:
            refs["ENAM"] = cstr(d)
        elif n == "NPCO" and len(d) >= 36:
            refs.setdefault("NPCO", []).append(cstr(d[4:36]))
    return refs


JUNKCELL_SUBTYPES = {"NAME", "DATA", "RGNN"}


def split_cell(body, off=0):
    """A CELL body as (head, persistent blocks, NAM0 data or None, temporary blocks). A block is a list
    of [name, data] from an FRMR (or an MVRF and its FRMR) up to the next one."""
    head, pers, temp = [], [], []
    nam0, block, in_temp = None, None, False
    for n, d in iter_subs(body, off):
        in_moved = block is not None and block[0][0] == "MVRF" and not any(x[0] == "FRMR" for x in block)
        if n == "MVRF" or (n == "FRMR" and not in_moved):
            if block is not None:
                (temp if in_temp else pers).append(block)
            block = [[n, d]]
        elif n == "NAM0":
            if block is not None:
                (temp if in_temp else pers).append(block)
            block, in_temp, nam0 = None, True, d
        elif block is not None:
            block.append([n, d])
        else:
            head.append([n, d])
    if block is not None:
        (temp if in_temp else pers).append(block)
    return head, pers, nam0, temp


def block_key(block, masters_l, own):
    """(owner file, reference index) of a reference block, or None for a moved reference."""
    if block[0][0] != "FRMR" or len(block[0][1]) < 4:
        return None
    v = struct.unpack_from("<I", block[0][1])[0]
    k = v >> 24
    owner = own if k == 0 else (masters_l[k - 1] if k <= len(masters_l) else None)
    return (owner, v & 0xFFFFFF) if owner else None


def block_digest(block):
    return digest(*(n.encode("ascii") + struct.pack("<I", len(d)) + d for n, d in block[1:]))


def index_masters(needs, lookup):
    """Read each needed master once, keeping only what the plugins being cleaned can be compared to.
    needs: master lower -> (set of record ids, set of cell keys)."""
    recs, cells = {}, {}
    for m, (want_recs, want_cells) in needs.items():
        path = lookup.get(m)
        if not path:
            continue
        print(f"  indexing master {os.path.basename(path)}", file=sys.stderr)
        data = read_plugin_bytes(path)
        mmasters = [x.lower() for x in plugin_masters(data)]
        r, c = recs.setdefault(m, {}), cells.setdefault(m, {})
        for off, tag, flags, body in iter_records(data):
            if tag == "TES3":
                continue
            rid = record_id(tag, body)
            if rid is None:
                continue
            if rid in want_recs:
                r[rid] = (digest(body), flags)
            if tag == "CELL" and rid[1] in want_cells:
                head, pers, _nam0, temp = split_cell(body, off)
                hd = {}
                for n, d in head:
                    hd.setdefault(n, bytes(d))
                refs = {}
                for b in pers + temp:
                    bk = block_key(b, mmasters, m)
                    if bk:
                        refs[bk] = block_digest(b)
                c[rid[1]] = {"head": hd, "refs": refs}
    return recs, cells


def clean_cell(body, off, masters_l, own, infos, persistent):
    """Clean one CELL against its masters' versions. Returns (new body or None to delete, [what]).
    masters_l: the plugin's masters in MAST order (FRMR numbers count them); infos: the masters' versions of
    this cell in LOAD order. Each part is compared with the version that wins before this plugin (the last
    master that has it), never with just any master: a copy of an older master's value deliberately undoes
    a later master's change and must stay."""
    head, pers, nam0, temp = split_cell(body, off)
    what = []

    def keep(block):
        bk = block_key(block, masters_l, own)
        if bk is None or bk[0] == own:            # moved references and the plugin's own are kept
            return True
        obj = next((cstr(d) for n, d in block if n == "NAME"), "")
        if obj.lower() in persistent:            # tes3cmd: never clean instances of persistent objects
            return True
        dg = block_digest(block)
        winner = next((info["refs"][bk] for info in reversed(infos) if bk in info["refs"]), None)
        if winner == dg:
            what.append(f"duplicate object instance {obj} (#{bk[1]} from {bk[0]})")
            return False
        return True

    new_pers = [b for b in pers if keep(b)]
    new_temp = [b for b in temp if keep(b)]
    if nam0 is not None and len(new_temp) != len(temp) and len(nam0) >= 4:
        nam0 = struct.pack("<I", max(0, struct.unpack_from("<I", nam0)[0] - (len(temp) - len(new_temp))))

    dd = next((d for n, d in head if n == "DATA"), None)
    interior = dd is not None and len(dd) >= 4 and struct.unpack_from("<I", dd)[0] & 1
    if interior:
        ambi = next((d for n, d in head if n == "AMBI"), None)
        last_ambi = next((info["head"]["AMBI"] for info in reversed(infos) if "AMBI" in info["head"]), None)
        if ambi is not None and last_ambi == bytes(ambi):
            head = [x for x in head if x[0] != "AMBI"]
            what.append("redundant AMBI")
        wh = next((d for n, d in head if n == "WHGT"), None)
        if wh is not None and len(wh) >= 4:
            pw = struct.unpack_from("<f", wh)[0]
            for info in reversed(infos):            # the last master that sets a water height wins
                mw = info["head"].get("WHGT")
                mi = info["head"].get("INTV")   # Morrowind.esm keeps some water heights in INTV
                mval = (struct.unpack_from("<f", mw)[0] if mw and len(mw) >= 4 else
                        struct.unpack_from("<i", mi)[0] if mi and len(mi) >= 4 else None)
                if mval is None:
                    continue
                if pw == mval:
                    head = [x for x in head if x[0] != "WHGT"]
                    what.append("redundant WHGT")
                break

    n_subs = len(head) + sum(len(b) for b in new_pers + new_temp) + (1 if nam0 is not None else 0)
    if n_subs < 4 and all(n in JUNKCELL_SUBTYPES for n, _d in head) and not new_pers and not new_temp:
        last = infos[-1] if infos else None             # the master version this cell overrides
        if last is not None and all(last["head"].get(n) == bytes(d) for n, d in head):
            return None, what + ["junk cell (nothing new compared to its master)"]
    if not what:
        return body, []
    out = head + [x for b in new_pers for x in b]
    if nam0 is not None:
        out.append(["NAM0", nam0])
        out += [x for b in new_temp for x in b]
    return b"".join(pack_sub(n, d) for n, d in out), what


SPEAKER_SUBS = {"ONAM": "speaker", "RNAM": "race", "CNAM": "class", "FNAM": "faction", "ANAM": "cell",
                "DNAM": "PC faction"}

COND_KINDS = {"4": "journal", "5": "item", "6": "dead", "7": "not id", "8": "not faction", "9": "not class",
              "A": "not race", "B": "not cell"}


def plugin_references(data):
    """What a dialogue plugin's responses refer to: [(kind, name)]. Cells are matched by prefix."""
    refs = []
    for off, tag, flags, body in iter_records(data):
        if tag != "INFO":
            continue
        for n, d in iter_subs(body, off):
            if n in SPEAKER_SUBS:
                v = cstr(d)
                if v and not (n == "FNAM" and v.upper() == "FFFF"):
                    refs.append((SPEAKER_SUBS[n], v))
            elif n == "SCVR" and len(d) > 5:
                kind = COND_KINDS.get(chr(d[1]))
                v = d[5:].decode(_T.ENC, MW_ERRORS).split("\0")[0]
                if kind and v:
                    refs.append((kind, v))
    return refs


def unresolved_refs(refs, known, cells, topics):
    """The references that nothing defines: (kind, name) -> count."""
    miss = Counter()
    for kind, name in refs:
        low = name.lower()
        if kind in ("cell", "not cell"):
            ok = low in cells or any(c.startswith(low) for c in cells)
        elif kind == "journal":
            ok = low in topics
        elif kind in ("faction", "not faction", "PC faction"):
            ok = low in known["FACT"]
        elif kind in ("class", "not class"):
            ok = low in known["CLAS"]
        elif kind in ("race", "not race"):
            ok = low in known["RACE"]
        else:
            ok = low in known["*"]
        if not ok:
            miss[(kind, name)] += 1
    return miss


def defined_names(data):
    """IDs, cell names and topic names a plugin defines (for treating merge inputs as known)."""
    ids, cells, topics = defaultdict(set), set(), set()
    for off, tag, flags, body in iter_records(data):
        if tag == "TES3":
            continue
        if tag == "DIAL":
            nm = first_sub(body, b"NAME")
            if nm is not None:
                topics.add(cstr(nm).lower())
            continue
        if tag == "CELL":
            nm = first_sub(body, b"NAME")
            if nm is not None and cstr(nm):
                cells.add(cstr(nm).lower())
            continue
        rid = record_id(tag, body)
        if rid and isinstance(rid[1], str):
            ids[tag].add(rid[1])
            ids["*"].add(rid[1])
    return ids, cells, topics


def remap_frmr(v, masters_from, merged_index, own_map, own_counter):
    """An FRMR/MVRF value from one input, re-expressed for the merged plugin."""
    k, ref = v >> 24, v & 0xFFFFFF
    if k == 0:                                         # the input's own reference: give it a new number
        if ref not in own_map:
            own_counter[0] += 1
            own_map[ref] = own_counter[0]
        return own_map[ref], ("own", own_map[ref])
    if k > len(masters_from):
        return None, None
    m = masters_from[k - 1].lower()
    return (merged_index[m] << 24) | ref, (m, ref)


def parse_levlist(tag, body):
    """(flags, chance none, [(element id, level)]) of a LEVC/LEVI record."""
    flags, chance, entries, cur = 0, 0, [], None
    elem = b"CNAM" if tag == "LEVC" else b"INAM"
    for n, d in iter_subs(body):
        nb = n.encode("ascii")
        if nb == b"DATA" and len(d) >= 4:
            flags = struct.unpack_from("<I", d)[0]
        elif nb == b"NNAM" and len(d) >= 1:
            chance = d[0]
        elif nb == elem:
            cur = cstr(d)
        elif nb == b"INTV" and cur is not None and len(d) >= 2:
            entries.append((cur, struct.unpack_from("<H", d)[0]))
    return flags, chance, entries


def merge_levlist(tag, defs, known=None, masters_of=None):
    """Merge the definitions [(plugin, body, deleted)] of one leveled list, in load order. Start from the
    first; each later definition's changes are measured against the version it was made from - the latest
    earlier definition by one of its masters (masters_of(plugin) -> lowercase names of all its masters,
    masters' masters included), else the first - and applied: (id, level) entries it adds or whose count it
    changes, and entries it removed (so a patch can take out what its mod added). Flags and chance-none come
    from the last definition that changed them. Without masters_of every definition is measured against the
    first (tes3cmd's merge)."""
    levlist, casing = {}, {}
    parsed = []
    for plugin, body, _deleted in defs:
        f, c, entries = parse_levlist(tag, body)
        cur = Counter()
        for eid, lvl in entries:
            cur[(eid.lower(), lvl)] += 1
            casing[eid.lower()] = eid
        parsed.append(((plugin or "").lower(), f, c, cur))
    flags, chance = parsed[0][1], parsed[0][2]
    levlist = dict(parsed[0][3])
    for k in range(1, len(parsed)):
        plugin, f, c, cur = parsed[k]
        base = 0
        if masters_of is not None:
            mine = masters_of(plugin)
            base = next((j for j in range(k - 1, -1, -1) if parsed[j][0] in mine), 0)
        _pp, pf, pc, par = parsed[base]
        for key, n in cur.items():                   # additions and changes
            if par.get(key) != n:
                levlist[key] = n
        par_ids = {e for e, _l in par}
        cur_ids = {e for e, _l in cur}
        for key in par:                              # removals from the version it was made from
            if key not in cur:
                levlist.pop(key, None)
        for e in par_ids - cur_ids:
            for key in [key for key in levlist if key[0] == e]:
                levlist.pop(key, None)
        if f != pf:
            flags = f
        if c != pc:
            chance = c
    if known is not None:                            # an entry no active plugin defines: the game can't find it
        levlist = {k: n for k, n in levlist.items() if k[0] in known}
    out = sorted(((lvl, eid) for (eid, lvl), n in levlist.items() for _ in range(n)))
    elem = "CNAM" if tag == "LEVC" else "INAM"
    name = cstr(first_sub(defs[-1][1], b"NAME"))
    subs = [pack_sub("NAME", name.encode(_T.ENC, MW_ERRORS) + b"\0"), pack_sub("DATA", struct.pack("<I", flags)),
            pack_sub("NNAM", bytes([chance])), pack_sub("INDX", struct.pack("<I", len(out)))]
    for lvl, eid in out:
        subs += [pack_sub(elem, casing[eid].encode(_T.ENC, MW_ERRORS) + b"\0"), pack_sub("INTV", struct.pack("<H", lvl))]
    nb = b"".join(subs)
    return tag.encode("ascii") + struct.pack("<III", len(nb), 0, 0) + nb, len(out)


MERGE_GROUPS = {
    "NPC_": {"AI_W": "AI", "AI_T": "AI", "AI_F": "AI", "AI_E": "AI", "AI_A": "AI", "CNDT": "AI",
             "DODT": "TRAVEL", "DNAM": "TRAVEL"},
    "CREA": {"AI_W": "AI", "AI_T": "AI", "AI_F": "AI", "AI_E": "AI", "AI_A": "AI", "CNDT": "AI",
             "DODT": "TRAVEL", "DNAM": "TRAVEL"},
    "ARMO": {"INDX": "PARTS", "BNAM": "PARTS", "CNAM": "PARTS"},
    "CLOT": {"INDX": "PARTS", "BNAM": "PARTS", "CNAM": "PARTS"},
}

MERGE_LISTS = {"NPCO": lambda d: cstr(d[4:36]).lower() if len(d) >= 36 else None,      # inventory, by item
               "NPCS": lambda d: cstr(d).lower()}                                       # spells, by spell


def merge_fields(tag, body):
    """A record as [(field, value)] in order. A field is a subrecord, or a run of related ones (AI packages,
    travel destinations, body parts, repeated subrecords) kept as one value; inventory and spell lists are
    {(key, occurrence): data} so each entry merges on its own (an item listed twice is two entries)."""
    groups = MERGE_GROUPS.get(tag, {})
    out, idx = [], {}
    seen_keys = Counter()
    prev = None
    for n, d in iter_subs(body):
        if n in MERGE_LISTS:
            k = MERGE_LISTS[n](d)
            if k is not None:
                seen_keys[(n, k)] += 1
                k = (k, seen_keys[(n, k)])
            if n not in idx:
                idx[n] = len(out)
                out.append([n, {}])
            if k is not None:
                out[idx[n]][1][k] = d
            prev = n
            continue
        g = groups.get(n, n)
        if g == prev and g in idx:                  # continuing a run
            out[idx[g]][1].append((n, d))
            continue
        if g in idx:                                # the same field again later: still one value
            out[idx[g]][1].append((n, d))
        else:
            idx[g] = len(out)
            out.append([g, [(n, d)]])
        prev = g
    return out


MERGE_REF_FIELDS = {"SCRI": None, "ENAM": ("ARMO", "CLOT", "WEAP", "BOOK"), "RNAM": ("NPC_",), "CNAM": ("NPC_",),
                    "ANAM": ("NPC_",), "BNAM": ("NPC_",), "KNAM": ("NPC_",)}

MERGE_FILE_FIELDS = {"MODL": "mesh", "ITEX": "icon"}


def merge_object(tag, versions, parent_of, known, defined=None, file_ok=None):
    """versions: [(plugin index, body)] in load order. parent_of(k) -> the version index plugin k's changes
    are measured against (its masters' latest, else the first). Returns the merged body, or None if the
    last version already has every change."""
    fields = [dict((f, v) for f, v in merge_fields(tag, b)) for _i, b in versions]
    orders = [[f for f, _v in merge_fields(tag, b)] for _i, b in versions]
    merged = {f: (dict(v) if isinstance(v, dict) else v) for f, v in fields[0].items()}
    for k in range(1, len(versions)):
        cur, par = fields[k], fields[parent_of(k)]
        for f in set(cur) | set(par):
            a, b = par.get(f), cur.get(f)
            if f in MERGE_LISTS:
                a, b = a or {}, b or {}
                m = merged.setdefault(f, {})
                for e in set(a) | set(b):
                    if a.get(e) != b.get(e):
                        if e in b:
                            m[e] = b[e]
                        else:
                            m.pop(e, None)
            elif a != b:
                if b is None:
                    merged.pop(f, None)
                else:
                    merged[f] = b
    last = fields[-1]
    if defined is not None:                          # a field naming something no active plugin has (a script, a
        for f, tags in MERGE_REF_FIELDS.items():     # race...): the last version's value, as the game had it
            if tags is not None and tag not in tags:
                continue
            v = merged.get(f)
            if v is None or v == last.get(f):
                continue
            ref = cstr(v[0][1]).lower() if v else ""
            if ref and ref not in defined:
                if last.get(f) is None:
                    merged.pop(f, None)
                else:
                    merged[f] = last[f]
    if file_ok is not None:                          # a model or icon that wouldn't load (missing, not a real
        for f, kind in MERGE_FILE_FIELDS.items():    # model file, or an empty "hide it" model): the last version's
            v = merged.get(f)
            if v is None or v == last.get(f) or not v:
                continue
            path = cstr(v[0][1])
            if path.strip() and not file_ok(kind, path):
                if last.get(f) is None:
                    merged.pop(f, None)
                else:
                    merged[f] = last[f]
    for f in MERGE_LISTS:                            # entries for things no active plugin defines: left out
        if f in merged and known is not None:
            merged[f] = {e: d for e, d in merged[f].items() if e[0] in known or e in (last.get(f) or {})}
    order = list(orders[-1])
    for o in reversed(orders[:-1]):
        for i, f in enumerate(o):
            if f in order:
                continue
            before = next((g for g in reversed(o[:i]) if g in order), None)
            order.insert(order.index(before) + 1 if before else 0, f)
    out = []
    for f in order:
        v = merged.get(f)
        if v is None:
            continue
        if f in MERGE_LISTS:
            seen = last.get(f) or {}
            keys = [e for e in seen if e in v] + [e for e in v if e not in seen]
            out += [pack_sub(f, v[e]) for e in keys]
        else:
            out += [pack_sub(n, d) for n, d in v]
    body = b"".join(out)
    return None if body == versions[-1][1] else body


def land_heights(vhgt):
    """A LAND record's VHGT as 65 x 65 heights in game units (row by row, south to north)."""
    if not vhgt or len(vhgt) < 4 + 65 * 65:
        return None
    off = struct.unpack_from("<f", vhgt)[0]
    d = struct.unpack_from("<4225b", vhgt, 4)
    h = [0.0] * 4225
    row = off
    for y in range(65):
        row += d[y * 65]
        col = row
        h[y * 65] = col
        for x in range(1, 65):
            col += d[y * 65 + x]
            h[y * 65 + x] = col
    return [v * 8.0 for v in h]


def height_at(h, g, x, y):
    """The land's height at (x, y) in cell g (bilinear between the 128-unit vertices)."""
    if h is None:
        return None
    lx = min(max((x - g[0] * 8192) / 128.0, 0.0), 64.0)
    ly = min(max((y - g[1] * 8192) / 128.0, 0.0), 64.0)
    x0, y0 = min(int(lx), 63), min(int(ly), 63)
    fx, fy = lx - x0, ly - y0
    a, b = h[y0 * 65 + x0], h[y0 * 65 + x0 + 1]
    c, d = h[(y0 + 1) * 65 + x0], h[(y0 + 1) * 65 + x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy
