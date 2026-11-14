"""mwdialog_redundant.py - which plugins do the same job: who uses whose objects, what each plugin is,
and the pairs where one makes the other redundant.
"""
from collections import Counter, defaultdict
import hashlib
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_tes3 as _T  # noqa: E402
from mwdialog_console import (  # noqa: E402
    print)
from mwdialog_datatree import (  # noqa: E402
    hard_link_names)
from mwdialog_patchfile import (  # noqa: E402
    PATCH_NAME)
from mwdialog_state import (  # noqa: E402
    CELL_WINNER_PATCH)
from mwdialog_tes3 import (  # noqa: E402
    FormatError, MW_ERRORS, cstr, first_sub, iter_records, iter_subs,
    record_id)


# Placeholder coins and the hidden cell go in a second patch that loads LAST: a placed reference is
# resolved when its plugin loads, so the objects it names (often from .esp mods) must already exist.
PLACE_PATCH_NAME = "mwdialog_check PlaceholderCell ESP Patch.esp"

PERFORMER_PATCH = "mwdialog_check Performers Patch.esp"

OUR_PATCHES = (PATCH_NAME, PLACE_PATCH_NAME, "mwdialog_check Multipatch.esp", CELL_WINNER_PATCH, PERFORMER_PATCH)

AUTO_SKIP_TAGS = {"CELL", "LAND", "PGRD"}          # placing/moving objects, land, pathgrids: not merged


def lua_named_plugins(data_dir):
    """Plugin names that MWSE Lua mods mention (e.g. tes3.isModActive("X.esp")): never merged away."""
    names = set()
    pat = re.compile(r'"([^"\n]{1,120}\.(?:esp|esm))"|\'([^\'\n]{1,120}\.(?:esp|esm))\'|\[\[([^\]\n]{1,120}\.(?:esp|esm))\]\]',
                     re.I)
    files = []
    for base, _dirs, fns in os.walk(os.path.join(data_dir, "MWSE")):
        files += [os.path.join(base, fn) for fn in fns if fn.lower().endswith((".lua", ".toml", ".json"))]
    try:                                    # MWSE metadata files (*-metadata.toml) list required plugins
        files += [os.path.join(data_dir, fn) for fn in os.listdir(data_dir) if fn.lower().endswith(".toml")]
    except OSError:
        pass
    for path in files:
        try:
            text = open(path, "r", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for m in pat.finditer(text):
            names.add((m.group(1) or m.group(2) or m.group(3)).lower())
    return names


def plugin_profile(path):
    """What --auto-merge needs to know about one plugin."""
    with open(path, "rb") as f:
        data = f.read()
    prof = {"size": len(data), "masters": [], "scripts": False, "cells": False, "keys": set(),
            "refs": set(), "ids": set(), "infos": set(), "links": set(), "data": None}
    topic = None
    for off, tag, flags, body in iter_records(data):
        if tag == "TES3":
            prof["masters"] = [cstr(d) for n, d in iter_subs(body) if n == "MAST"]
            continue
        if tag in ("SCPT", "SSCR"):
            prof["scripts"] = True
            tx = first_sub(body, b"SCTX")
            if tx:                                   # names a script uses (resolved when it loads)
                for q, w in re.findall(r'"([^"\n]+)"|([A-Za-z_][\w\'\-]*)', tx.decode(_T.ENC, MW_ERRORS)):
                    prof["refs"].add((q or w).lower())
        if tag in AUTO_SKIP_TAGS:
            prof["cells"] = True
        if tag == "DIAL":
            topic = cstr(first_sub(body, b"NAME") or b"").lower()
            prof["keys"].add(("DIAL", topic))
            prof["ids"].add(topic)
            continue
        if tag == "INFO":
            iid = cstr(first_sub(body, b"INAM") or b"").lower()
            prof["keys"].add(("INFO", topic, iid))
            prof["infos"].add(iid)
            for n, d in iter_subs(body, off):
                if n in ("PNAM", "NNAM"):
                    v = cstr(d).lower()
                    if v:
                        prof["links"].add(v)
                elif n in ("ONAM", "ANAM", "RNAM", "CNAM", "FNAM", "DNAM"):
                    prof["refs"].add(cstr(d).lower())
                elif n == "SCVR" and len(d) > 5:
                    prof["refs"].add(d[5:].decode(_T.ENC, MW_ERRORS).split("\0")[0].lower())
            continue
        topic = None
        rid = record_id(tag, body)
        if rid is not None:
            prof["keys"].add(rid)
            if isinstance(rid[1], str):
                prof["ids"].add(rid[1])
        for n, d in iter_subs(body, off):
            if n == "NPCO" and len(d) >= 36:
                prof["refs"].add(cstr(d[4:36]).lower())
            elif n in ("ENAM", "SCRI", "SNAM", "BNAM") or (n in ("INAM", "CNAM") and tag in ("LEVI", "LEVC")):
                prof["refs"].add(cstr(d).lower())
            elif n == "NAME" and tag == "CELL":
                prof["refs"].add(cstr(d).lower())       # objects placed in cells
    return prof


USE_OBJ_TAGS = {"ACTI", "ALCH", "APPA", "ARMO", "BOOK", "CLOT", "CONT", "CREA", "DOOR", "INGR", "LEVC", "LEVI",
                "LIGH", "LOCK", "MISC", "NPC_", "PROB", "REPA", "STAT", "WEAP"}

_OBJECT_USE = {}


def object_use(plugins):
    """{plugin lower: (ids it defines, ids it uses)} for the active plugins (lists, inventories, placed
    objects). The merged plugin counts as one; our generated patches don't. Read once per run."""
    key = tuple(n.lower() for n, _p in plugins)
    if key in _OBJECT_USE:
        return _OBJECT_USE[key]
    skip = {x.lower() for x in OUR_PATCHES} | {CELL_WINNER_PATCH.lower(), PERFORMER_PATCH.lower()}
    print("  Reading which plugins use which objects...", file=sys.stderr)
    out = {}
    for n, p in plugins:
        if n.lower() in skip:
            continue
        try:
            data = open(p, "rb").read()
        except OSError:
            continue
        defs, uses = set(), set()
        for _off, tag, _fl, body in iter_records(data):
            if tag in USE_OBJ_TAGS:
                nm = first_sub(body, b"NAME")
                if nm:
                    defs.add(cstr(nm).lower())
                if tag in ("LEVC", "LEVI"):
                    want = "CNAM" if tag == "LEVC" else "INAM"
                    uses.update(cstr(d).lower() for s, d in iter_subs(body) if s == want)
                elif tag in ("NPC_", "CREA", "CONT"):
                    uses.update(cstr(d[4:36]).lower() for s, d in iter_subs(body) if s == "NPCO" and len(d) >= 36)
            elif tag == "CELL":
                uses.update(cstr(d).lower() for s, d in iter_subs(body) if s == "NAME")
        out[n.lower()] = (defs, uses - defs)
    _OBJECT_USE.clear()
    _OBJECT_USE[key] = out
    return out


def relied_on(plugins, x, also_off=()):
    """What turning plugin x off would break: {other active plugin: [ids only x defines that it uses]}."""
    use = object_use(plugins)
    x = x.lower()
    if x not in use:
        return {}
    gone = {x} | {o.lower() for o in also_off}
    elsewhere = set()
    for pl, (defs, _u) in use.items():
        if pl not in gone:
            elsewhere |= defs
    only = use[x][0] - elsewhere
    if not only:
        return {}
    hit = {}
    for pl, (_d, uses) in use.items():
        if pl in gone:
            continue
        lost = uses & only
        if lost:
            hit[pl] = sorted(lost)
    return hit


def relied_on_text(hit, name_of, n=3):
    users = sorted(hit, key=lambda k: -len(hit[k]))
    ids = sorted({i for v in hit.values() for i in v})
    return (f"{len(ids)} of its objects ({', '.join(ids[:4])}{', ...' if len(ids) > 4 else ''}) are used by "
            + ", ".join(name_of.get(u, u) for u in users[:n]) + (f" and {len(users) - n} more" if len(users) > n else ""))


REDUNDANT_VARIANT_SHARE = 0.5     # alternative versions: at least half of the smaller one's records shared...

REDUNDANT_VARIANT_SAME = 0.5      # ...and at least half of those shared records identical

REDUNDANT_VARIANT_MIN = 5         # ...and at least this many shared records

REDUNDANT_MAX_VERSIONS = 12       # records in more plugins than this (GMSTs, busy cells) don't pair plugins up


def plugin_summary(path):
    """What --redundant shows and compares for one plugin: {key: digest}, record counts by type, header."""
    with open(path, "rb") as f:
        data = f.read()
    recs, counts, info = {}, Counter(), {"author": "", "desc": "", "masters": []}
    for _off, tag, flags, body in iter_records(data):
        if tag == "TES3":
            h = first_sub(body, b"HEDR")
            if h is not None and len(h) >= 296:
                info["author"] = cstr(h[8:40])
                info["desc"] = cstr(h[40:296])
            info["masters"] = [cstr(d) for n, d in iter_subs(body) if n == "MAST"]
            continue
        if tag == "LTEX":                      # texture indexes are per plugin: never compared
            continue
        rid = record_id(tag, body)
        if rid is None:
            continue
        if rid[0] != tag:
            rid = (tag,) + tuple(rid[1:])
        counts[tag] += 1
        recs[rid] = hashlib.md5(struct.pack("<I", flags & 0x20) + body).digest()
    info["counts"] = counts
    return recs, info


def lua_required_plugins(data_dir):
    """Plugin names MWSE Lua code or mod metadata asks for (tes3.isModActive, *-metadata.toml), lowercase.
    Unlike lua_named_plugins, settings and caches (MWSE\\config, listing every plugin) and mods set aside in
    an 'off' folder don't count."""
    names = set()
    pat = re.compile(r'"([^"\n]{1,120}\.(?:esp|esm))"|\'([^\'\n]{1,120}\.(?:esp|esm))\'|\[\[([^\]\n]{1,120}\.(?:esp|esm))\]\]',
                     re.I)
    files = []
    for base, dirs, fns in os.walk(os.path.join(data_dir, "MWSE")):
        dirs[:] = [d for d in dirs if d.lower() not in ("config", "off")]     # settings; turned-off mods
        files += [os.path.join(base, fn) for fn in fns if fn.lower().endswith(".lua")
                  or fn.lower().endswith("-metadata.toml")]
    try:
        files += [os.path.join(data_dir, fn) for fn in os.listdir(data_dir) if fn.lower().endswith("-metadata.toml")]
    except OSError:
        pass
    for path in files:
        try:
            text = open(path, "r", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for mt in pat.finditer(text):
            names.add((mt.group(1) or mt.group(2) or mt.group(3)).lower())
    return names


def vortex_mod_name(path, root):
    """The Vortex mod folder a deployed plugin comes from (through its hard link), or ''."""
    if not root:
        return ""
    r = os.path.normcase(os.path.abspath(root)) + os.sep
    for other in hard_link_names(path):
        o = os.path.normcase(os.path.abspath(other))
        if o.startswith(r):
            return os.path.abspath(other)[len(r):].split(os.sep)[0]
    return ""


def _type_text(c, n=5):
    items = Counter(c).most_common()
    return ", ".join(f"{k} {v}" for k, v in items[:n]) + (f", +{len(items) - n} more types" if len(items) > n else "")


def _id_text(key):
    return str(key[1]) if len(key) == 2 else " ".join(str(x) for x in key[1:])


def find_redundant(plugins, needed=(), lua=(), keep_both=(), no_candidates=(), soft_masters=()):
    """Plugins in `plugins` ([(name, path)], load order) that do the same job as another one:
      exact - every record it has is either identical to the version before it (ITM) or identical to
              another active plugin's copy, and taking it out changes no record's winner: nothing of it is
              lost, and nothing it overrides changes. Found one at a time (two copies of each other: only
              one of them is redundant). High confidence when one plugin holds all its non-ITM records.
      variant - two plugins that share most of their records, most of them identical, and look like two
              versions of one mod (same description, or the same name up to an edit word): alternatives
              where one is normally picked. Never turned off without asking. Not when each has cells of its
              own (Animated Morrowind - Danae's Edits: Vv for Vvardenfell, TR for the mainland, sharing the
              objects they place): those are two halves.
    Plugins other active plugins need as masters, that MWSE Lua asks for, or in `no_candidates` (this
    tool's patches and merges) are never candidates. A master in `soft_masters` ({(plugin, master)}, lowercase:
    the masters --sort added from content rules, which no reference of the plugin uses) doesn't count: the
    plugin loads without it, and the tool takes such a master out again when it is turned off. Returns {"exact": [...], "variant": [...], "info": {...}}."""
    names = [n for n, _p in plugins]
    low = [n.lower() for n in names]
    pos = {l: i for i, l in enumerate(low)}
    recs, info = {}, {}
    for n, p in plugins:
        try:
            recs[n.lower()], info[n.lower()] = plugin_summary(p)
        except (OSError, FormatError):
            recs[n.lower()], info[n.lower()] = {}, {"author": "", "desc": "", "masters": [], "counts": Counter()}
    versions = defaultdict(list)                       # key -> [(position, plugin)] in load order
    for l in low:
        for k in recs[l]:
            versions[k].append(l)
    dependents = defaultdict(list)
    for l in low:
        for mname in info[l]["masters"]:
            if mname.lower() in pos:
                dependents[mname.lower()].append(l)
    soft = {(a.lower(), b.lower()) for a, b in soft_masters}
    hard_dependents = {mm: [d for d in ds if (d, mm) not in soft] for mm, ds in dependents.items()}
    needed = {x.lower() for x in needed}
    lua = {x.lower() for x in lua}
    blocked = {x.lower() for x in no_candidates}

    def why_not(l, gone):
        if l in blocked:
            return "this tool's own plugin"
        if l in needed or [d for d in hard_dependents.get(l, []) if d not in gone]:
            return "other active plugins need it as a master"
        if l in lua:
            return "an MWSE Lua mod asks for it by name"
        return None

    def exact_check(l, gone):
        """(itm, {other plugin: identical copies of its non-ITM records}) when l is redundant, else None."""
        own = recs[l]
        if not own:
            return None
        itm, copies = 0, Counter()
        for k, d in own.items():
            vs = [x for x in versions[k] if x not in gone]
            i = vs.index(l)
            if i > 0 and recs[vs[i - 1]][k] == d:
                itm += 1
                continue
            same = [x for x in vs if x != l and recs[x][k] == d]
            if not same:
                return None                            # something only it has (or its own version of it)
            if i == len(vs) - 1:
                return None                            # it wins this record; without it another version would
            for x in same:
                copies[x] += 1
        return itm, copies

    def classify(l, gone):
        """(phase, entry) for a redundant plugin: phase 0 all ITM, 1 one plugin holds all its other records,
        2 its records are spread over several plugins; None when it isn't redundant."""
        r = exact_check(l, gone)
        if r is None:
            return None
        itm, copies = r
        nonitm = len(recs[l]) - itm
        if copies:
            keep, n = max(copies.items(), key=lambda kv: (kv[1], pos[kv[0]]))
            phase = 1 if n == nonitm else 2
        else:                                          # all ITM: the plugin whose versions it repeats most
            prev = Counter()
            for k in recs[l]:
                vs = [x for x in versions[k] if x not in gone]
                prev[vs[vs.index(l) - 1]] += 1
            keep, _n = max(prev.items(), key=lambda kv: (kv[1], pos[kv[0]]))
            phase = 0
        return phase, {"plugin": l, "keep": keep, "records": len(recs[l]), "itm": itm, "copies": dict(copies),
                       "confidence": "high" if phase < 2 else "medium"}

    # one at a time, surest first (all-ITM, then contained in one plugin, then spread out); smaller and
    # earlier-loading first within each: of two copies of each other the later one already wins and stays
    exact, gone = [], set()
    order = sorted((l for l in low if not why_not(l, set())), key=lambda l: (len(recs[l]), pos[l]))
    while True:
        best = None
        for l in order:
            if l in gone or why_not(l, gone):
                continue
            c = classify(l, gone)
            if c is None:
                continue
            # a plugin restating one that loads before it (an add-on's copy) goes before one whose content a
            # later plugin carries (the later one may be the add-on)
            rank = (c[0], pos[c[1]["keep"]] > pos[l])
            if best is None or rank < best[0]:
                best = (rank, c[1])
                if rank == (0, False):
                    break
        if best is None:
            break
        e = best[1]
        gone.add(e["plugin"])
        if not any(frozenset((e["plugin"], x)) in keep_both for x in [e["keep"]] + list(e["copies"])):
            exact.append(e)

    # alternative versions of one mod
    co = Counter()
    for k, vs in versions.items():
        vs = [x for x in vs if x not in gone]
        if 1 < len(vs) <= REDUNDANT_MAX_VERSIONS:
            for i in range(len(vs)):
                for j in range(i + 1, len(vs)):
                    co[(vs[i], vs[j])] += 1
    variant = []
    for (a, b), shared in co.items():
        small = min(len(recs[a]), len(recs[b]))
        if shared < REDUNDANT_VARIANT_MIN or shared < REDUNDANT_VARIANT_SHARE * small:
            continue
        if frozenset((a, b)) in keep_both:
            continue
        ma = {x.lower() for x in info[a]["masters"]}
        mb = {x.lower() for x in info[b]["masters"]}
        if a in mb or b in ma:                          # a patch for the other, not another version of it
            continue
        same = sum(1 for k in recs[a] if k in recs[b] and recs[a][k] == recs[b][k])
        if same < REDUNDANT_VARIANT_SAME * shared:
            continue
        da, db = " ".join(info[a]["desc"].split()), " ".join(info[b]["desc"].split())
        if not ((da and da == db) or _same_mod_name(names[pos[a]], names[pos[b]])):
            continue
        own_cells = [sum(1 for k in recs[x] if k[0] == "CELL" and k not in recs[y]) for x, y in ((a, b), (b, a))]
        if min(own_cells) >= REDUNDANT_VARIANT_MIN:
            continue                                    # each places things in cells of its own: two halves
        later, other = (a, b) if pos[a] > pos[b] else (b, a)
        if da != db and PATCH_WORD_RE.search(names[pos[later]]) and not PATCH_WORD_RE.search(names[pos[other]]) \
                and not any(versions[k][0] == later for k in recs[later]):
            continue                                    # "X - Patch for Y" adding nothing of its own: a patch on top
        variant.append({"a": a, "b": b, "shared": shared, "same": same,
                        "blocked": {x: why_not(x, gone) for x in (a, b) if why_not(x, gone)}})
    variant.sort(key=lambda v: -v["same"] / max(1, min(len(recs[v["a"]]), len(recs[v["b"]]))))
    return {"exact": exact, "variant": variant, "recs": recs, "info": info, "versions": versions,
            "dependents": dependents, "soft": soft, "pos": pos, "names": dict(zip(low, names))}


PATCH_WORD_RE = re.compile(r"(?i)(?:^|[^a-z])(patch|fix(?:es|ed)?|compat\w*|add-?on|tweaks?)(?:$|[^a-z])")


def _same_mod_name(a, b):
    """Two plugin names that are one mod's name plus different edit/variant words."""
    def stem(n):
        s = os.path.splitext(n)[0].lower()
        s = re.sub(r"[\s_\-\.]+", " ", s)
        return s.strip()
    sa, sb = stem(a), stem(b)
    k = 0
    while k < min(len(sa), len(sb)) and sa[k] == sb[k]:
        k += 1
    return k >= 8 and k >= 0.6 * min(len(sa), len(sb))


def describe_plugin(res, l, vroot=None, paths=None):
    """Lines that say what one plugin is and does."""
    inf, recs, versions = res["info"][l], res["recs"][l], res["versions"]
    new = sum(1 for k in recs if versions[k][0] == l)
    wins = sum(1 for k in recs if versions[k][-1] == l)
    name = res["names"][l]
    mod = vortex_mod_name(paths[l], vroot) if paths and vroot else ""
    desc = " ".join(inf["desc"].split())
    out = [f"{name}  (#{res['pos'][l] + 1} in the load order" + (f"; Vortex mod: {mod}" if mod else "") + ")"]
    if desc or inf["author"]:
        out.append(f"    {(desc[:200] + ('...' if len(desc) > 200 else '')) or '(no description)'}"
                   + (f"  [by {inf['author']}]" if inf["author"] else ""))
    out.append(f"    {len(recs)} records ({_type_text(inf['counts'])}): {new} new, {len(recs) - new} change "
               f"earlier plugins' records; its version wins {wins}")
    deps = res["dependents"].get(l, [])
    soft = res.get("soft", set())
    if deps:
        out.append("    needed as a master by: " + ", ".join(res["names"][d] + (" (added by --sort; taken out again "
                                                                              "if this goes)" if (d, l) in soft else "")
                                                             for d in deps[:4])
                   + (f" and {len(deps) - 4} more" if len(deps) > 4 else ""))
    return out


def describe_overlap(res, a, b):
    ra, rb = res["recs"][a], res["recs"][b]
    shared = [k for k in ra if k in rb]
    same = [k for k in shared if ra[k] == rb[k]]
    differ = [k for k in shared if ra[k] != rb[k]]
    only_a = [k for k in ra if k not in rb]
    only_b = [k for k in rb if k not in ra]
    na, nb = res["names"][a], res["names"][b]
    pct = lambda x, n: f"{100 * x / n:.0f}%" if n else "-"
    out = [f"    shared records: {len(shared)} ({pct(len(shared), len(ra))} of {na}, {pct(len(shared), len(rb))} "
           f"of {nb}); identical: {len(same)}; different: {len(differ)}"]
    if differ:
        later = a if res["pos"][a] > res["pos"][b] else b
        out.append(f"    different ({_type_text(Counter(k[0] for k in differ))}), e.g. "
                   + ", ".join(_id_text(k) for k in differ[:4]) + f"; {res['names'][later]} loads later, so its "
                   f"version of these is the one used")
    for who, only in ((na, only_a), (nb, only_b)):
        out.append(f"    only in {who}: {len(only)}" + (f" ({_type_text(Counter(k[0] for k in only))}), e.g. "
                                                     + ", ".join(_id_text(k) for k in only[:4]) if only else ""))
    return out
