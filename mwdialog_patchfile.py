"""mwdialog_patchfile.py - building the generated fix patch: placeholder records and cells, item-record
fixes, and writing the patch plugin itself.
"""
from collections import OrderedDict
import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_tes3 as _T  # noqa: E402
from mwdialog_backup import (  # noqa: E402
    backup_path)
from mwdialog_records import (  # noqa: E402
    split_cell)
from mwdialog_tes3 import (  # noqa: E402
    ASSET_SUBS, ENAM_TAGS, MW_ERRORS, REF_TAGS, cell_key, cstr,
    first_sub, iter_records, iter_subs, pack_sub, set_hedr_count, write_plugin_bytes)


def patch_supports(op):
    """Can this fix be expressed as an override in a separate patch plugin?"""
    return op[0] not in ("drop_ref", "move_ref") and op != ("delete", "local")


PATCH_NAME = "mwdialog_check - ESM fixes.esp"


def next_free_date(data_dir, exclude):
    """One day after the newest plugin: matches a one-plugin-per-day, date-based load order."""
    newest = 0
    for fn in os.listdir(data_dir):
        if fn.lower().endswith((".esp", ".esm")) and fn.lower() != exclude.lower():
            try:
                newest = max(newest, os.path.getmtime(os.path.join(data_dir, fn)))
            except OSError:
                pass
    return newest + 86400 if newest else None


def fix_item_body(body, fx):
    """A record body with its dangling script/enchantment replaced or removed and missing
    inventory entries dropped (see World._check_item_refs)."""
    if fx.get("lev_drop"):
        subs, kept, skip_intv = [], 0, False
        for n, d in iter_subs(body):
            if n in ("INAM", "CNAM") and cstr(d).lower() in fx["lev_drop"]:
                skip_intv = True
                continue
            if n == "INTV" and skip_intv:
                skip_intv = False
                continue
            skip_intv = False
            if n in ("INAM", "CNAM"):
                kept += 1
            subs.append([n, d])
        for s in subs:
            if s[0] == "INDX":
                s[1] = struct.pack("<I", kept)
        body = b"".join(pack_sub(n, d) for n, d in subs)
    out = []
    in_head = True
    for n, d in iter_subs(body):
        if n in ("FRMR", "MVRF", "NAM0"):
            in_head = False
        if fx.get("head_only") and not in_head and n in fx["set"]:
            out.append(pack_sub(n, d))
            continue
        if n in fx["set"] and (n != "ENAM" or fx["tag"] in ENAM_TAGS):
            v = fx["set"][n]
            if not v:
                continue
            d = v.encode(_T.ENC, MW_ERRORS) + b"\0"
        elif n == "NPCO" and len(d) >= 36 and cstr(d[4:36]).lower() in fx["npco"]:
            continue
        out.append(pack_sub(n, d))
    return b"".join(out)


def apply_item_fixes(path, plugin, fixes, log, backup=True, collect=None):
    """Rewrite the records named in `fixes` in place (.bak first, file date kept). With `collect`,
    nothing is written: the corrected records are appended to it (for the ESM patch)."""
    want = {}
    for fx in fixes:
        k = ("CELL", fx["key"]) if fx["tag"] == "CELL" else (fx["tag"], fx["id"].lower())
        if k in want:                                  # several fixes to one record: combine them
            w = want[k] = dict(want[k], set=dict(want[k]["set"]), msgs=list(want[k]["msgs"]),
                               npco=set(want[k]["npco"]))
            w["set"].update(fx["set"])
            w["msgs"] += fx["msgs"]
            w["npco"] |= fx["npco"]
            w["lev_drop"] = set(w.get("lev_drop") or ()) | set(fx.get("lev_drop") or ())
            w["head_only"] = w.get("head_only") or fx.get("head_only") or fx["tag"] == "CELL"
        else:
            want[k] = dict(fx, head_only=fx.get("head_only") or fx["tag"] == "CELL")
    with open(path, "rb") as f:
        data = f.read()
    out, changes = [], 0
    for off, tag, flags, body in iter_records(data):
        raw = data[off:off + 16 + len(body)]
        if tag == "CELL":
            fx = want.get(("CELL", cell_key(body)[0]))
        else:
            nm = first_sub(body, b"NAME") if tag in REF_TAGS or tag in ASSET_SUBS or tag in ("LEVI", "LEVC") else None
            fx = want.get((tag, cstr(nm).lower())) if nm is not None else None
        if fx is None:
            out.append(raw)
            continue
        if fx.get("drop_record"):
            changes += 1
            for msg, action in fx["msgs"]:
                log.append((plugin, msg, action))
            if fx.get("delete_in_patch") and collect is not None:
                # a master's record can't be dropped from the master: the patch deletes it instead
                nm = first_sub(body, b"NAME") or b""
                nb = pack_sub("NAME", nm) + pack_sub("DELE", b"\0\0\0\0")
                collect.append(tag.encode("ascii") + struct.pack("<I", len(nb)) + data[off + 8:off + 16] + nb)
            continue
        nb = fix_item_body(body, fx)
        if tag == "CELL" and collect is not None:      # a patch carries only the cell's header, never
            head, _p, _n0, _t = split_cell(nb)          # copies of its references
            nb = b"".join(pack_sub(n, d) for n, d in head)
        rec = tag.encode("ascii") + struct.pack("<I", len(nb)) + data[off + 8:off + 16] + nb
        out.append(rec)
        if collect is not None:
            collect.append(rec)
        changes += 1
        for msg, action in fx["msgs"]:
            log.append((plugin if collect is None else PATCH_NAME,
                        msg + (f" (in {plugin})" if collect is not None else ""), action))
    if not changes or collect is not None:
        return changes
    out[0] = set_hedr_count(out[0], len(out) - 1)    # records may have been dropped: keep the count true
    st = os.stat(path)
    if backup:
        bak = backup_path(path)
        shutil.copy2(path, bak)
    write_plugin_bytes(path, b"".join(out), keep_times=st)   # checked copy, then in place (hard links stay)
    if backup:
        log.append((plugin, "", f"backup saved as {os.path.basename(bak)}"))
    return changes


def placeholder_record(world, oid):
    """A copy of gold_001 under a missing object's ID: a single gold coin, worth 1, no script."""
    if world.gold_template is None or len(oid) > 31:
        return None
    out = []
    for n, d in iter_subs(world.gold_template):
        if n == "NAME":
            d = oid.encode(_T.ENC, MW_ERRORS) + b"\0"
        elif n == "FNAM":
            d = b"Placeholder Coin\0"
        elif n == "SCRI":
            continue
        out.append(pack_sub(n, d))
    nb = b"".join(out)
    return b"MISC" + struct.pack("<III", len(nb), 0, 0) + nb


PLACEHOLDER_CELL = "mwdialog_check placeholders"


def placeholder_cell(ids, cell_name=PLACEHOLDER_CELL):
    """A hidden interior cell holding one placed (persistent) copy of each object ID."""
    subs = [pack_sub("NAME", cell_name.encode(_T.ENC, MW_ERRORS) + b"\0"),
            pack_sub("DATA", struct.pack("<Iii", 1, 0, 0)),               # interior
            pack_sub("AMBI", struct.pack("<IIIf", 0, 0, 0, 0.0))]
    for i, oid in enumerate(ids, 1):
        subs += [pack_sub("FRMR", struct.pack("<I", i)),                 # the patch's own reference #i
                 pack_sub("NAME", oid.encode(_T.ENC, MW_ERRORS) + b"\0"),
                 pack_sub("DATA", struct.pack("<6f", 0, 0, 0, 0, 0, 0))]
    subs.append(pack_sub("NAM0", struct.pack("<I", 0)))                  # no temporary references
    nb = b"".join(subs)
    return b"CELL" + struct.pack("<III", len(nb), 0, 0) + nb


def write_patch(path, entries, masters, log, backup=True, extra=(),
                description="Dialogue fixes for master files, generated by mwdialog_check.py"):
    """entries: [(DIAL record bytes, INFO record bytes)] in order; grouped under one DIAL per topic."""
    groups = OrderedDict()
    for dial_raw, info_raw in entries:
        key = cstr(first_sub(dial_raw[16:], b"NAME") or b"").lower()
        g = groups.setdefault(key, [dial_raw, OrderedDict()])
        if info_raw is None:
            continue
        iid = cstr(first_sub(info_raw[16:], b"INAM") or b"").lower()
        g[1].pop(iid, None)
        g[1][iid] = info_raw
    body = []
    for dial_raw, infos in groups.values():
        body.append(dial_raw)
        body.extend(infos.values())
    body = list(extra) + body
    hedr = (struct.pack("<fI", 1.3, 0) + b"mwdialog_check".ljust(32, b"\0")
            + description.encode(_T.ENC, MW_ERRORS)[:255].ljust(256, b"\0")
            + struct.pack("<I", len(body)))
    subs = [pack_sub("HEDR", hedr)]
    for name, mpath in masters:
        subs.append(pack_sub("MAST", name.encode(_T.ENC, MW_ERRORS) + b"\0"))
        subs.append(pack_sub("DATA", struct.pack("<Q", os.path.getsize(mpath))))
    hb = b"".join(subs)
    header = b"TES3" + struct.pack("<III", len(hb), 0, 0) + hb

    st = None
    if os.path.exists(path):
        st = os.stat(path)
        if backup:
            bak = backup_path(path)
            shutil.copy2(path, bak)
            log.append((os.path.basename(path), "", f"previous patch backed up as {os.path.basename(bak)}"))
    write_plugin_bytes(path, header + b"".join(body), keep_times=st)   # keeps its load-order position
    return len(groups), sum(len(g[1]) for g in groups.values())
