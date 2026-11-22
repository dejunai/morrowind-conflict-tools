"""mwdialog_mergeplan.py - recommend merges --auto-merge doesn't make: plugins with cells, land or pathgrids
(dungeons, quests, landscape) grouped into several merged plugins.

Read-only: it writes a report (mwdialog_merge_plan.txt) and the plan for the GUI (mwdialog_merge_plan.json),
both rewritten from scratch each run. Rules:

  A plugin can go into a merge when
    - it is an active .esp, readable, not made by these tools and not already a merge;
    - no other active plugin lists it as a master, and no MWSE Lua mod looks for it by name;
    - every master it lists is active;
    - it shares no leveled list or Multipatch-merged object with an earlier recommended plugin (inside
      one merge only the later version would reach the Multipatch).
  A merge takes the load-order place of its last input ("replaces"), so every input must still win what
  it wins today: no plugin outside the merge may load between an input and that place and change what
  the input changes, use an object it adds, or link dialogue to or from it.
  Plugins that use each other's objects or dialogue, or change the same records, go into the same merge
  (it keeps their order). A merge never holds two plugins that touch the same cell, or whose doors lead
  into the same exterior cell.
  Plugins are grouped by kind (dungeons, landscape, quests, other), at most --plan-size per merge;
  small patches (PATCH_RECORDS records or fewer) all go into one merge, split only by cells and exits.
  Merging plugins that place objects in cells needs a new game: saves record placed objects by plugin.
"""
from collections import defaultdict
import json
import math
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mwdialog_multipatch import MERGE_TAGS, NOT_A_MOD  # noqa: E402
from mwdialog_redundant import (  # noqa: E402
    OUR_PATCHES, lua_named_plugins, plugin_profile)
from mwdialog_state import read_merge_record  # noqa: E402
from mwdialog_tes3 import FormatError, cell_key, cstr, first_sub, iter_records, iter_subs  # noqa: E402

PLAN_TXT = "mwdialog_merge_plan.txt"
PLAN_JSON = "mwdialog_merge_plan.json"
PLAN_SIZE = 8
CELL_SIZE = 8192.0
PATCH_RECORDS = 40                                 # this few records: a small patch, gathered into one merge
KINDS = (("patch", "Small patches"), ("dungeon", "Dungeons and interiors"),
         ("exterior", "Landscape and exteriors"), ("quest", "Quests, scripts and dialogue"), ("other", "Other"))


def cell_footprint(path):
    """{"interiors": names, "exteriors": grids it edits (cells, land, pathgrids, moved references),
    "exits": exterior grids its doors lead to}."""
    with open(path, "rb") as f:
        data = f.read()
    fp = {"interiors": set(), "exteriors": set(), "exits": set()}
    for off, tag, _flags, body in iter_records(data):
        if tag == "LAND":
            iv = first_sub(body, b"INTV")
            if iv is not None and len(iv) >= 8:
                fp["exteriors"].add(struct.unpack_from("<ii", iv))
        elif tag == "PGRD":
            d = first_sub(body, b"DATA")
            xy = struct.unpack_from("<ii", d) if d is not None and len(d) >= 8 else (0, 0)
            if xy != (0, 0):
                fp["exteriors"].add(xy)
            else:
                fp["interiors"].add(cstr(first_sub(body, b"NAME") or b"").lower())
        elif tag == "CELL":
            key, _label = cell_key(body)
            if key is None:
                continue
            if key[0] == "i":
                fp["interiors"].add(key[1])
            else:
                fp["exteriors"].add(key[1:])
            door, to_interior, in_ref = None, False, False
            for n, d in iter_subs(body, off):
                if n in ("FRMR", "MVRF"):
                    if door is not None and not to_interior:
                        fp["exits"].add(door)
                    door, to_interior, in_ref = None, False, True
                elif not in_ref:
                    continue
                elif n == "CNDT" and len(d) >= 8:
                    fp["exteriors"].add(struct.unpack_from("<ii", d))
                elif n == "DODT" and len(d) >= 8:
                    x, y = struct.unpack_from("<ff", d)
                    if math.isfinite(x) and math.isfinite(y):
                        door = (math.floor(x / CELL_SIZE), math.floor(y / CELL_SIZE))
                elif n == "DNAM":
                    to_interior = True
            if door is not None and not to_interior:
                fp["exits"].add(door)
    fp["interiors"].discard("")
    return fp


def _kind(prof, fp, new_interiors):
    if len(prof["keys"]) <= PATCH_RECORDS:
        return "patch"
    if new_interiors:
        return "dungeon"
    if fp["exteriors"] or fp["interiors"]:
        return "exterior"
    if prof["scripts"] or prof["infos"]:
        return "quest"
    return "other"


def recommend(order, data_dir, game_dir, plan_size=PLAN_SIZE, log=None):
    """order: active plugins [(name, path)] in load order. Returns {"groups": [...], "left_out": {name: why}}."""
    log = log or (lambda *_a: None)
    rec = read_merge_record(game_dir)
    pos = {n.lower(): i for i, (n, _p) in enumerate(order)}
    ours = {x.lower() for x in OUR_PATCHES}
    profs = {}
    for i, (n, p) in enumerate(order, 1):
        if i % 100 == 0:
            log(f"  read {i}/{len(order)} plugins...")
        try:
            profs[n.lower()] = plugin_profile(p)
        except (OSError, FormatError) as e:
            log(f"  could not read {n}: {e}")
    master_of = defaultdict(list)
    for k, pr in profs.items():
        if k not in ours:
            for m in pr["masters"]:
                master_of[m.lower()].append(k)
    lua_names = lua_named_plugins(data_dir)
    merges = {o.lower() for o in rec}
    left, cands = {}, []
    for n, _p in order:
        low, pr = n.lower(), profs.get(n.lower())
        why = None
        if pr is None:
            why = "could not be read"
        elif not low.endswith(".esp"):
            why = "master file"
        elif low in ours or low in merges or low in NOT_A_MOD:
            why = "made by mwdialog_check"
        elif master_of.get(low):
            why = f"{len(master_of[low])} plugin(s) list it as a master"
        elif low in lua_names:
            why = "an MWSE Lua mod looks for it by name"
        elif any(m.lower() not in pos for m in pr["masters"]):
            why = "a master isn't active"
        if why:
            left[n] = why
        else:
            cands.append(n)

    definers, referrers, info_at, linkers, first_pos = (defaultdict(list), defaultdict(list),
                                                        defaultdict(list), defaultdict(list), {})
    for n, _p in order:
        low = n.lower()
        pr = profs.get(low)
        if pr is None or low in ours:
            continue
        i = pos[low]
        for k in pr["keys"]:
            definers[k].append(i)
        for x in pr["ids"]:
            first_pos.setdefault(x, i)
        for x in pr["refs"]:
            referrers[x].append(i)
        for x in pr["infos"]:
            info_at[x].append(i)
        for x in pr["links"]:
            linkers[x].append(i)

    # Leveled lists and objects the Multipatch merges field by field: two recommended plugins changing the
    # same one can't share a merge (only the later version would reach the Multipatch), so the later is left
    # out. Other records they share are fine: a merge keeps its inputs' order.
    owner = {}
    for c in list(cands):
        keys = [k for k in profs[c.lower()]["keys"] if k[0] in ("LEVI", "LEVC") or k[0] in MERGE_TAGS]
        clash = next((k for k in keys if k in owner), None)
        if clash:
            cands.remove(c)
            left[c] = f"{owner[clash]} (recommended) also changes {clash[0]} '{clash[-1]}'"
            continue
        for k in keys:
            owner.setdefault(k, c)

    # A merge takes the place of its last input. Every input must still win what it wins today, so nothing
    # outside the merge may load between an input and that place and change, use or link to what the input
    # does. hits[c]: the later plugins that do, in load order.
    hits = {}
    for c in cands:
        pr, ci = profs[c.lower()], pos[c.lower()]
        h = [(i, f"changes {k[0]} '{k[-1]}'") for k in pr["keys"] if k[0] != "DIAL" for i in definers[k]]
        h += [(i, f"uses '{x}', which it adds") for x in pr["ids"] if first_pos.get(x) == ci for i in referrers[x]]
        h += [(i, "has dialogue linked with it") for x in pr["links"] for i in info_at[x]]
        h += [(i, "has dialogue linked with it") for x in pr["infos"] for i in linkers[x]]
        hits[c.lower()] = sorted({i: r for i, r in sorted(h, reverse=True) if i > ci}.items())

    def limit(members):
        """Where the merge must load before: the first plugin outside it that any input depends on."""
        at = {pos[n.lower()] for n in members}
        return min((next((i for i, _r in hits[n.lower()] if i not in at), len(order)) for n in members),
                   default=len(order))

    fps, kinds, paths = {}, {}, dict(order)
    for c in cands:
        low = c.lower()
        try:
            fps[low] = cell_footprint(paths[c])
        except (OSError, FormatError) as e:
            fps[low] = {"interiors": set(), "exteriors": set(), "exits": set()}
            log(f"  could not read cells of {c}: {e}")
        new_int = {nm for nm in fps[low]["interiors"]
                   if min(definers[("CELL", ("i", nm))], default=pos[low]) >= pos[low]}
        kinds[low] = _kind(profs[low], fps[low], new_int)

    # Pack into merges by kind, in load order: each plugin joins the first merge it can (the merge must still
    # load before its limit, and cells and door exits stay apart).
    groups = []
    for kind, label in KINDS:
        cap = 10 ** 6 if kind == "patch" else plan_size
        open_groups = []
        for c in cands:
            low = c.lower()
            if kinds[low] != kind:
                continue
            fp = fps[low]
            ci, co = fp["interiors"], fp["exteriors"] | fp["exits"]
            target = next((g for g in open_groups
                           if len(g["inputs"]) < cap and not (ci & g["cells"]) and not (co & g["outside"])
                           and pos[low] < limit(g["inputs"] + [c])), None)
            if target is None:
                target = {"kind": kind, "label": label, "inputs": [], "cells": set(), "outside": set()}
                open_groups.append(target)
            target["inputs"].append(c)
            target["cells"] |= ci
            target["outside"] |= co
        for g in open_groups:
            if len(g["inputs"]) < 2:
                n = g["inputs"][0]
                first = hits[n.lower()][0] if hits[n.lower()] else None
                left[n] = (f"nothing to merge it with before {order[first[0]][0]} {first[1]}" if first
                           else "nothing safe to merge it with")
                continue
            groups.append(g)

    out = []
    for i, g in enumerate(sorted(groups, key=lambda g: min(pos[n.lower()] for n in g["inputs"])), 1):
        inputs = sorted(g["inputs"], key=lambda n: pos[n.lower()])
        out.append({
            "name": f"mwdialog_check Merge {i:02d} - {g['label']}.esp",
            "kind": g["kind"], "label": g["label"], "inputs": inputs, "replaces": inputs[-1],
            "size": sum(profs[n.lower()]["size"] for n in inputs),
            "new_game": any(fps[n.lower()]["interiors"] or fps[n.lower()]["exteriors"] for n in inputs),
            "scripts": sorted(n for n in inputs if profs[n.lower()]["scripts"]),
            "cells": len(g["cells"]), "exteriors": len(g["outside"]),
        })
    return {"groups": out, "left_out": {n: left[n] for n, _p in order if n in left}}


def write_plan(plan, game_dir, active):
    """Rewrite the report and the JSON plan (never appended)."""
    groups, left = plan["groups"], plan["left_out"]
    merged = sum(len(g["inputs"]) for g in groups)
    stamp = time.strftime("%Y-%m-%d %H:%M")
    lines = [f"; mwdialog_merge_plan.txt - recommended merges ({stamp}); rewritten every run.",
             f"; {active} active plugins; {merged} plugin(s) in {len(groups)} merge(s) would free "
             f"{merged - len(groups)} slot(s).", ""]
    for g in groups:
        lines.append(f"[{g['name']}]  {len(g['inputs'])} plugins, {g['size'] / 1048576:.1f} MB"
                     + ("  - NEW GAME NEEDED (places objects in cells)" if g["new_game"] else ""))
        lines += [f"    {n}" + ("   (scripts)" if n in g["scripts"] else "") for n in g["inputs"]]
        lines.append("")
    reasons = defaultdict(list)
    for n, why in left.items():
        if why != "master file":
            reasons[why].append(n)
    lines.append("Left out:")
    for why, names in sorted(reasons.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        lines.append(f"  {why}: " + ", ".join(names))
    for name, text in ((PLAN_TXT, "\n".join(lines) + "\n"),
                       (PLAN_JSON, json.dumps(dict(plan, generated=stamp, active=active), indent=1) + "\n")):
        path = os.path.join(game_dir, name)
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(path + ".tmp", path)
    return os.path.join(game_dir, PLAN_TXT)
