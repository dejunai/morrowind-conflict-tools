"""mwdialog_multipatch.py - build MULTI_PATCH_NAME: merged leveled lists, fog fixes, reverted cell names,
and merged objects (like TES3Merge / tes3cmd multipatch).
"""
from collections import Counter, defaultdict
import datetime
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mwdialog_backup import index_dir  # noqa: E402
from mwdialog_bsa import bsa_file_names  # noqa: E402
from mwdialog_console import print  # noqa: E402
from mwdialog_datatree import ModelAssets  # noqa: E402
from mwdialog_loadorder import read_load_order, set_game_files  # noqa: E402
from mwdialog_media import nif_is_empty  # noqa: E402
from mwdialog_patchfile import next_free_date, write_patch  # noqa: E402
from mwdialog_records import merge_levlist, merge_object  # noqa: E402
from mwdialog_redundant import OUR_PATCHES  # noqa: E402
from mwdialog_state import read_merge_record  # noqa: E402
from mwdialog_tes3 import (  # noqa: E402
    FormatError, cstr, first_sub, iter_records, pack_sub,
    read_header_masters, read_plugin_bytes)
import mwdialog_text as MT  # noqa: E402

MULTI_PATCH_NAME = "mwdialog_check Multipatch.esp"
BETHESDA_MASTERS = {"morrowind.esm", "tribunal.esm", "bloodmoon.esm"}
NOT_A_MOD = {"multipatch.esp", "mashed lists.esp", "merged_leveled_lists.esp", "merged_objects.esp",
             "merged_dialogs.esp", "fogpatch.esp", "cellnamepatch.esp"}

MERGE_TAGS = ("NPC_", "CREA", "ARMO", "CLOT", "WEAP", "MISC", "BOOK", "ALCH", "INGR", "LIGH", "APPA", "LOCK",
              "PROB", "REPA", "CONT", "ACTI", "DOOR", "SPEL", "ENCH", "CLAS", "RACE", "BSGN", "BODY")


def multipatch_source(plugin, cells=False):
    """Plugins the multipatch reads from. tes3cmd skips merged/patch plugins, and for cells also the
    Bethesda masters."""
    low = (plugin or "").lower()
    if low in NOT_A_MOD or low in [x.lower() for x in OUR_PATCHES]:
        return False
    return not (cells and low in BETHESDA_MASTERS)


def merge_file_check(args, world):
    """For the object merge: does a model/icon path load? The asset index when this run built one, else a
    quick look at loose files and the game's own archives."""
    A = getattr(world, "assets", None)
    if A is not None:
        def ok_indexed(kind, v):
            if ModelAssets.fatal(A.field_problem(kind, v)):
                return False
            if kind == "mesh":
                try:
                    return not nif_is_empty(A._mesh_bytes(A.norm(v)) or b"")
                except OSError:
                    return True
            return True
        return ok_indexed
    data_dir = os.path.abspath(args.data_dir)
    bsa = set()
    for b in ("Morrowind.bsa", "Tribunal.bsa", "Bloodmoon.bsa"):
        try:
            bsa |= {n.replace("/", "\\") for n in bsa_file_names(os.path.join(data_dir, b))}
        except (OSError, FormatError, NameError):
            pass
    cache = {}

    def ok(kind, v):
        top = {"mesh": "meshes", "icon": "icons"}[kind]
        rel = (top + "\\" + v.strip().lower().replace("/", "\\")).replace("\\\\", "\\")
        if rel in cache:
            return cache[rel]
        full = os.path.join(data_dir, rel)
        good = False
        if os.path.isfile(full):
            if kind == "mesh":
                try:
                    with open(full, "rb") as f:
                        data = f.read(65536)
                    good = data.startswith((b"NetImmerse File Format", b"Gamebryo File Format")) \
                        and not nif_is_empty(data)
                except OSError:
                    good = False
            else:
                good = True
        elif rel in bsa:
            good = True
        elif kind == "icon":                         # icons: a .dds may stand for the named .tga
            stem = os.path.splitext(rel)[0]
            good = any(os.path.isfile(os.path.join(data_dir, stem + e)) or stem + e in bsa
                       for e in (".dds", ".tga", ".bmp"))
        cache[rel] = good
        return good
    return ok


def merged_objects(plugins, known=None, file_ok=None, merged_inputs=None, only=None):
    """Records of MERGE_TAGS that several plugins change in different ways, merged field by field: what each
    plugin changed (compared with the version it was made against: its masters' latest, or the original)
    is kept; where two changed the same field, the later one wins. Returns ([record bytes], [notes]).
    merged_inputs: {merged plugin lower: [(input name, path)]} - see object_merges. only: a set of
    (tag, id lower) to look at, the rest is skipped."""
    out = object_merges(plugins, known, file_ok, merged_inputs, only)
    return [r for _k, r, _n in out], [n for _k, _r, n in out]


def expand_merged(plugins, merged_inputs):
    """The load order with each merged plugin (--merge/--auto-merge) replaced by the plugins it was built
    from, in their order, when all of them can still be read. A merged plugin lists every input's masters,
    so measured as one plugin its records look like they were made against all of those: an input made
    against Morrowind.esm alone then seems to undo what another master changed (Expanded Sounds' script
    and sound on the prison ship lanterns). Measured as its inputs, each record is compared with the
    version its own plugin was made against. Returns (order, {input lower: merged plugin lower})."""
    if not merged_inputs:
        return list(plugins), {}
    active = {n.lower() for n, _p in plugins}
    out, owner = [], {}
    for n, p in plugins:
        ins = merged_inputs.get(n.lower())
        if ins and all(ip and os.path.isfile(ip) for _i, ip in ins) \
                and not any(i.lower() in active for i, _ip in ins):
            for i, ip in ins:
                out.append((i, ip))
                owner[i.lower()] = n.lower()
        else:
            out.append((n, p))
    return out, owner


def object_merges(plugins, known=None, file_ok=None, merged_inputs=None, only=None):
    """merged_objects' work: [((tag, id), record bytes, note)]. With merged_inputs, a merged plugin is
    looked at as the plugins it was built from (expand_merged); a result the merged plugin already has
    is left out."""
    real = [(n, p) for n, p in plugins if multipatch_source(n)]
    vorder, owner = expand_merged(real, merged_inputs)
    real_path = {n.lower(): p for n, p in real}
    order = [(n, p) for n, p in vorder if multipatch_source(n)]
    names = [n.lower() for n, _p in order]
    masters = {}
    for n, p in order:
        try:
            masters[n.lower()] = [m.lower() for m in read_header_masters(p)]
        except (OSError, FormatError):
            masters[n.lower()] = []
    closure = {}

    def deps(n):
        if n not in closure:
            seen, stack = set(), list(masters.get(n, []))
            while stack:
                x = stack.pop()
                if x not in seen:
                    seen.add(x)
                    stack += masters.get(x, [])
            closure[n] = seen
        return closure[n]
    print("  Reading objects several plugins change...", file=sys.stderr)
    want = set(MERGE_TAGS)
    versions = defaultdict(list)                     # (tag, id) -> [(plugin index, digest, offset, deleted)]
    defined = set()                                  # every id an active plugin defines (scripts too)
    for i, (n, p) in enumerate(order):
        try:
            data = read_plugin_bytes(p)
            recs_i = list(iter_records(data))        # a damaged file is left out, not half-read
        except (OSError, FormatError) as e:
            print(f"  {n}: left out of the object merge ({e})", file=sys.stderr)
            continue
        for pos, tag, fl, body in recs_i:
            try:
                if tag == "SCPT":
                    hd = first_sub(body, b"SCHD")
                    if hd:
                        defined.add(cstr(hd[:32]).lower())
                elif tag not in ("CELL", "INFO", "DIAL", "LAND", "PGRD", "TES3"):
                    nm = first_sub(body, b"NAME")
                    if nm:
                        defined.add(cstr(nm).lower())
                if tag in want:
                    nm = first_sub(body, b"NAME")
                    if nm and (only is None or (tag, cstr(nm).lower()) in only):
                        dele = bool(fl & 0x20) or first_sub(body, b"DELE") is not None
                        versions[(tag, cstr(nm).lower())].append((i, hashlib.md5(body, usedforsecurity=False).digest(), pos, dele))
            except FormatError:
                continue
    cands = {k: v for k, v in versions.items() if len(v) >= 3 and not any(x[3] for x in v)
             and len({x[1] for x in v[1:]}) >= 2}
    need = defaultdict(set)
    for v in cands.values():
        for i, _d, off, _x in v:
            need[i].add(off)
    bodies = {}
    for i, offs in need.items():
        data = read_plugin_bytes(order[i][1])
        for off in offs:
            size, _u, fl = struct.unpack_from("<III", data, off + 4)
            bodies[(i, off)] = (data[off + 16:off + 16 + size], fl)
    merged_recs = {}                                 # merged plugin lower -> {(tag, id): body}

    def merged_body(mp, key):
        if mp not in merged_recs:
            got = {}
            try:
                for _o, t, _f, b in iter_records(read_plugin_bytes(real_path[mp])):
                    if t in want:
                        nm = first_sub(b, b"NAME")
                        if nm:
                            got[(t, cstr(nm).lower())] = b
            except (OSError, FormatError, KeyError):
                pass
            merged_recs[mp] = got
        return merged_recs[mp].get(key)
    out = []
    for (tag, rid), v in sorted(cands.items()):
        vers = [(i, bodies[(i, off)][0]) for i, _d, off, _x in v]

        def parent_of(k, vers=vers):
            seen = deps(names[vers[k][0]])
            return next((j for j in range(k - 1, -1, -1) if names[vers[j][0]] in seen), 0)
        try:
            body = merge_object(tag, vers, parent_of, known, defined, file_ok)
        except FormatError:
            continue
        if body is None:
            continue
        mp = owner.get(names[v[-1][0]])
        if mp is not None and merged_body(mp, (tag, rid)) == body:
            continue                                 # the merged plugin already has it (its own object merge)
        fl = bodies[(v[-1][0], v[-1][2])][1]
        out.append(((tag, rid), tag.encode("ascii") + struct.pack("<III", len(body), 0, fl) + body,
                    f"{tag} {rid}: merged from " + ", ".join(order[i][0] for i, *_r in v[1:])))
    return out


def merged_inputs_of(game_dir, data_dir):
    """{merged plugin lower: [(input name, path or None)]} from mwdialog_merged.txt."""
    files = index_dir(data_dir)
    return {k.lower(): [(i, files.get(i.lower())) for i in ins] for k, ins in read_merge_record(game_dir).items()}


def run_multipatch(args, plugins, world):
    """Build MULTI_PATCH_NAME: reverted cell names, fog-bugged cells, merged leveled lists."""
    print("\n" + "=" * 70 + "\nMULTIPATCH\n" + "=" * 70)
    if any(n.lower() == "multipatch.esp" for n, _p in plugins):
        print("  WARNING: tes3cmd's multipatch.esp is active. Deactivate it: two merged-list plugins override\n"
              "  each other, and the last one loaded wins completely.")
    recs, notes = [], []
    used = getattr(world, "script_cells", set())
    renamed = [(c, t) for c, t in sorted(world.rencells.items()) if t["reverted"] and t["rec"]
               and t["orig"].strip().lower() not in used]       # a master's name that scripts use wins
    heads = getattr(world, "cell_heads", {})

    def cell_header(key, nm, d, ambi=None):
        """The latest header of the cell (region, water, map colour... as the winning record has them), with
        only NAME (and for fog, DATA and AMBI) changed; just NAME/DATA(/AMBI) if no header was seen."""
        head = heads.get(key)
        if not head:
            subs = [("NAME", nm), ("DATA", d)] + ([("AMBI", ambi)] if ambi is not None else [])
        else:
            subs = []
            for n, v in head:
                if n == "NAME":
                    v = nm
                elif n == "DATA" and ambi is not None:
                    v = d
                elif n == "AMBI" and ambi is not None:
                    v = ambi
                subs.append((n, v))
            if not any(n == "NAME" for n, _v in subs):
                subs.insert(0, ("NAME", nm))
            if ambi is not None and not any(n == "AMBI" for n, _v in subs):
                subs.append(("AMBI", ambi))
        return b"".join(pack_sub(n, v) for n, v in subs)
    for (x, y), t in renamed:
        nm, d = t["rec"]
        nb = cell_header(("e", x, y), nm, d)
        recs.append(b"CELL" + struct.pack("<III", len(nb), 0, 0) + nb)
        notes.append(f"cell ({x}, {y}): keeps the name '{t['name']}' given by {t['plug']}")
    for low in sorted(world.fogcells):
        plugin, nm, d, ambi = world.fogcells[low]
        d = d[:8] + struct.pack("<f", 0.01) + d[12:]
        ambi = ambi[:12] + struct.pack("<f", 0.01) + ambi[16:]
        nb = cell_header(("i", low), nm, d, ambi)
        recs.append(b"CELL" + struct.pack("<III", len(nb), 0, 0) + nb)
        notes.append(f"cell '{cstr(nm)}': fog density 0 (from {plugin}) set to 0.01")
    counts = Counter()
    known = set(getattr(world, "all_ids", {}) or ()) or None     # ids an active plugin defines
    mclosure = {}

    def masters_of(plugin):
        """Every master of `plugin` (lowercase), masters' masters included."""
        if plugin not in mclosure:
            seen, stack = set(), [m.lower() for m in world.masters.get(plugin, [])]
            while stack:
                x = stack.pop()
                if x not in seen:
                    seen.add(x)
                    stack += [m.lower() for m in world.masters.get(x, [])]
            mclosure[plugin] = seen
        return mclosure[plugin]
    for tag in ("LEVC", "LEVI"):
        for (t, low), defs in sorted(world.levlists.items()):
            if t != tag:
                continue
            if defs[-1][2]:
                continue                             # the last plugin deletes the list: leave it deleted
            defs = [x for x in defs if not x[2]]
            if len(defs) < 3:
                continue                             # once: nothing to merge; twice: the last already wins
            rec, n = merge_levlist(tag, defs, known, masters_of)
            recs.append(rec)
            counts[tag] += 1
            notes.append(f"{tag} {cstr(first_sub(defs[-1][1], b'NAME'))}: merged from "
                         f"{len(defs)} plugins ({n} entries)")
    mrecs, mnotes = ([], []) if getattr(args, "no_merge_objects", False) else \
        merged_objects(plugins, known, file_ok=merge_file_check(args, world),
                       merged_inputs=merged_inputs_of(os.path.dirname(os.path.abspath(args.data_dir)),
                                                      args.data_dir))
    recs += mrecs
    notes += mnotes
    print(f"  {len(renamed)} cell name(s) protected, {len(world.fogcells)} fog-bugged cell(s), "
          f"{counts['LEVC']} creature and {counts['LEVI']} item list(s) merged, {len(mrecs)} object(s) several "
          f"mods change merged")
    if args.dry_run:
        print("Dry run: no files were changed.")
        return
    path = os.path.join(args.data_dir, MULTI_PATCH_NAME)
    is_new = not os.path.exists(path)
    if is_new and not recs:
        print("  No patching necessary; the multipatch was not created.")
        return
    write_patch(path, [], [], [], extra=recs,
                description="Merged leveled lists, fog bug and cell name fixes (tes3cmd multipatch), "
                            "generated by mwdialog_check.py. Load this LAST.")
    if is_new:
        when = next_free_date(args.data_dir, MULTI_PATCH_NAME)
        if when:
            os.utime(path, (when, when))
    with MT.open_log(args.fix_log, "a", encoding="utf-8") as f:
        f.write(f"\n==== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} multipatch ====\n")
        f.write("".join(f"{MULTI_PATCH_NAME}: {n}\n" for n in notes))
    print(f"  {MULTI_PATCH_NAME}: written with {len(recs)} record(s)" + (" (new: load it LAST)" if is_new else ""))
    # back in the load order (last) if it isn't there: new, or set aside by --full until now
    if not args.dry_run:
        cur = read_load_order(args) or []
        if cur and MULTI_PATCH_NAME.lower() not in {n.lower() for n in cur}:
            game_dir = os.path.dirname(os.path.abspath(args.data_dir))
            set_game_files(args.ini or os.path.join(game_dir, "Morrowind.ini"), cur + [MULTI_PATCH_NAME],
                           "--multipatch")
            print(f"  {MULTI_PATCH_NAME}: added to the load order (last)")
