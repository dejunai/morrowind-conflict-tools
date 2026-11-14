"""mwdialog_masters.py - a plugin's master list: adding and removing a master, whether an added one is still
used, and which plugins a set of patches covers.
"""
import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_tes3 as _T  # noqa: E402
from mwdialog_backup import (  # noqa: E402
    backup_path, index_dir)
from mwdialog_loadorder import (  # noqa: E402
    LOAD_ORDER_FILE, sort_vanilla)
from mwdialog_tes3 import (  # noqa: E402
    FormatError, MW_ERRORS, cstr, iter_records, iter_subs, pack_sub,
    read_header_masters, set_hedr_count, write_plugin_bytes)


def check_masters_for_play(args, names):
    """Before the game starts: every active plugin's masters must be active and load before it, and
    every listed plugin must exist. Returns a list of problems (empty if all is well)."""
    data_dir = os.path.abspath(args.data_dir)
    lookup = index_dir(data_dir)
    problems = []
    paths = []
    for n in names:
        p = lookup.get(n.lower())
        if p is None:
            problems.append(f"{n}: listed in {LOAD_ORDER_FILE} but not in Data Files")
        else:
            paths.append(p)
    order = [os.path.basename(p) for p in sort_vanilla(paths)]       # how the game orders them: by date
    pos = {n.lower(): i for i, n in enumerate(order)}
    for n in order:
        try:
            masters = read_header_masters(lookup[n.lower()])
        except (OSError, FormatError) as e:
            problems.append(f"{n}: could not be read ({e})")
            continue
        for m in masters:
            ml = m.lower()
            if ml not in pos:
                where = ("it is in Data Files but not in the load order (turned off)" if ml in lookup
                         else "it isn't in Data Files at all (not installed)")
                problems.append(f"{n}: needs master '{m}', but {where}")
            elif pos[ml] > pos[n.lower()]:
                problems.append(f"{n}: needs master '{m}', but the master loads after it "
                                f"(load order position {pos[ml] + 1} vs {pos[n.lower()] + 1})")
    return problems


FIXABLE_EXT = (".esp",)


def covered_by_patches(issue, covered):
    """Is this issue one that the existing patches (their contents in `covered`) already fix?"""
    sev, plugin, topic, info, msg = issue
    if not plugin.lower().endswith(FIXABLE_EXT) and (topic.lower(), info.lower()) in covered:
        return True
    if topic.startswith("script ") and (("script-object", info.lower()) in covered
                                        or ("placed-object", info.lower()) in covered):
        return True
    if topic.startswith("cell ") and "isn't defined yet" in msg and ("early-object", info.lower()) in covered:
        return True
    if topic.startswith("script ") and ("loads later" in msg or "is temporary" in msg) \
            and "in a master" not in msg \
            and (("early-placed", info.lower()) in covered if ("copy of it is placed" in msg
                                                              or "is temporary" in msg)
                 else ("early-object", info.lower()) in covered):
        return True
    return False


def master_closure(world, plugins, patched):
    """The patched masters plus everything they depend on, in load order."""
    need, stack = set(), [p.lower() for p in patched]
    while stack:
        p = stack.pop()
        if p in need:
            continue
        need.add(p)
        stack.extend(m.lower() for m in world.masters.get(p, []))
    return [(n, path) for n, path in plugins if n.lower() in need]


def write_inplace(path, out, backup=True):
    """Write records over a plugin in place: .bak first, record count set, date kept (hard links stay)."""
    out[0] = set_hedr_count(out[0], len(out) - 1)
    st = os.stat(path)
    bak = None
    if backup:
        bak = backup_path(path)
        shutil.copy2(path, bak)
    write_plugin_bytes(path, b"".join(out), keep_times=st)
    return bak


def add_master(path, master_name, master_path):
    """Append `master_name` to a plugin's master list (MAST + DATA size), in place (.bak first, date kept).
    Appending keeps every existing master's index, so the plugin's references don't change."""
    with open(path, "rb") as f:
        data = f.read()
    recs = list(iter_records(data))
    off, tag, flags, body = recs[0]
    if tag != "TES3":
        raise FormatError("no TES3 header")
    subs = list(iter_subs(body))
    if any(n == "MAST" and cstr(d).lower() == master_name.lower() for n, d in subs):
        return None
    new = b"".join(pack_sub(n, d) for n, d in subs)
    new += pack_sub("MAST", master_name.encode(_T.ENC, MW_ERRORS) + b"\0") + pack_sub("DATA", struct.pack("<Q", os.path.getsize(master_path)))
    head = b"TES3" + struct.pack("<I", len(new)) + data[off + 8:off + 16] + new
    out = [head] + [data[o:o + 16 + len(b)] for o, _t, _f, b in recs[1:]]
    return write_inplace(path, out)


def _refs_use_master(recs, idx, n_masters):
    """True when a cell reference in these records points at master #idx (1-based), or at a later master
    while there is one (taking #idx out would renumber those)."""
    later = n_masters > idx
    for _o, t, _f, b in recs:
        if t == "CELL":
            for n, d in iter_subs(b):
                if n in ("FRMR", "MVRF") and len(d) >= 4 and (struct.unpack_from("<I", d)[0] >> 24) >= idx:
                    if later or (struct.unpack_from("<I", d)[0] >> 24) == idx:
                        return True
    return False


def added_master_in_use(path, master_name):
    """Would remove_master refuse? (a reference uses that master's index). False when it isn't a master."""
    with open(path, "rb") as f:
        data = f.read()
    recs = list(iter_records(data))
    names = [cstr(d) for n, d in iter_subs(recs[0][3]) if n == "MAST"]
    low = [x.lower() for x in names]
    if master_name.lower() not in low:
        return False
    return _refs_use_master(recs[1:], low.index(master_name.lower()) + 1, len(names))


def remove_master(path, master_name):
    """Take a master this tool added back out of a plugin (in place, .bak first). Refused when any
    reference in the plugin uses that master's index."""
    with open(path, "rb") as f:
        data = f.read()
    recs = list(iter_records(data))
    off, tag, flags, body = recs[0]
    subs = list(iter_subs(body))
    names = [cstr(d) for n, d in subs if n == "MAST"]
    low = [x.lower() for x in names]
    if master_name.lower() not in low:
        return None
    idx = low.index(master_name.lower()) + 1               # 1-based, as references count them
    if _refs_use_master(recs, idx, len(names)):
        raise FormatError(f"a reference uses master #{idx} or a later one")
    keep, skip_data = [], False
    for n, d in subs:
        if n == "MAST" and cstr(d).lower() == master_name.lower():
            skip_data = True
            continue
        if n == "DATA" and skip_data:
            skip_data = False
            continue
        keep.append(pack_sub(n, d))
    new = b"".join(keep)
    head = b"TES3" + struct.pack("<I", len(new)) + data[off + 8:off + 16] + new
    return write_inplace(path, [head] + [data[o:o + 16 + len(b)] for o, _t, _f, b in recs[1:]])
