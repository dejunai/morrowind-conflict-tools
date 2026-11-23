"""mwdialog_cellorder.py - for --sort: order rules from the cells dialogue filters name.

The game checks each dialogue response's cell filter as its plugin loads, against the cells that exist at that
moment ("Cell 'Fatleg's Camp' not found"). A plugin whose dialogue filters on a cell only another .esp names
(a patch between two mods that lists neither as a master) must load after that .esp, and before every plugin
that then blanks or renames the cell (until --fix gives a blanking .esp the name back). A cell an .esm names
needs no rule: .esm files load first, and --fix gives an .esm's name back to a cell a later plugin took it from.

lost_cell_filter: the same question for --auto-merge, which moves a plugin to the merge's place.
"""
from collections import defaultdict
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mwdialog_tes3 import FormatError, cell_key, cstr, first_sub, iter_records, read_plugin_bytes  # noqa: E402

WHY = "cell:"                                   # start of every rule's reason, as --sort reports it


def _read(path):
    """(cell key -> name, set of cell filters, set of region names) of one plugin."""
    cells, filters, regions = {}, set(), set()
    for _off, tag, _flags, body in iter_records(read_plugin_bytes(path)):
        if tag == "CELL":
            key, _label = cell_key(body)
            if key is not None:
                cells[key] = cstr(first_sub(body, b"NAME") or b"").strip().lower()
        elif tag == "INFO":
            a = first_sub(body, b"ANAM")
            if a:
                c = cstr(a).strip().lower()
                if c:
                    filters.add(c)
        elif tag == "REGN":
            fn = first_sub(body, b"FNAM")
            if fn:
                regions.add(cstr(fn).strip().lower())
    return cells, filters, regions


def cell_filter_rules(plugins, ours=frozenset()):
    """[("order", [first, then], why)] for the .esp plugins (in load order) whose dialogue filters on a cell
    only an .esp names: after the last .esp naming it, and before every .esp that takes the name away after
    that; one that takes it away before that .esp stays before it. Plugins in `ours` (lower case) get no rules."""
    hist = defaultdict(list)                    # cell key -> [(load index, name)]
    givers = defaultdict(list)                  # name -> [(load index, cell key)]
    filters, regions = {}, {"wilderness"}
    for i, (_n, p) in enumerate(plugins):
        try:
            cells, f, r = _read(p)
        except (OSError, FormatError):
            continue
        for key, nm in cells.items():
            hist[key].append((i, nm))
            if nm:
                givers[nm].append((i, key))
        filters[i] = f
        regions |= r
    names = [n for n, _p in plugins]
    esm = [n.lower().endswith(".esm") for n in names]
    rules, seen = [], set()

    def add(a, b, why):
        if a != b and (a, b) not in seen and names[a].lower() not in ours and names[b].lower() not in ours:
            seen.add((a, b))
            rules.append(("order", [names[a], names[b]], f"{WHY} {why}"))

    for u, cells in filters.items():
        if esm[u]:
            continue
        for c in sorted(cells - regions):
            g = givers.get(c)
            if not g or any(esm[i] or i == u for i, _k in g):
                continue
            _i, key = min(g)
            last = max(i for i, nm in hist[key] if nm == c)
            add(last, u, f"{names[u]}'s dialogue filters on cell '{c}', which {names[last]} names")
            # every .esp taking the name away is pinned: before the giver if it loads before it now, else after
            # the user. Only the first later one would let the sort put another between giver and user.
            for i, nm in sorted(hist[key]):
                if i == u or esm[i] or nm == c:
                    continue
                what = f"renames it '{nm}'" if nm else "blanks its name"
                if i < last:
                    add(i, last, f"{names[u]}'s dialogue filters on cell '{c}', which {names[i]} {what}; "
                                 f"{names[last]} names it again")
                else:
                    add(u, i, f"{names[u]}'s dialogue filters on cell '{c}', which {names[i]} {what}")
    return rules


def lost_cell_filter(filters, hist, to, skip=frozenset()):
    """A dialogue cell filter that doesn't find its cell at load position `to`: a plugin there or before it
    names the cell, and a later one (up to `to`) blanks or renames it again. hist: cell key -> [(load index,
    name lower)] in load order; positions in `skip` don't count. (filter, index of the plugin that takes the
    name, the name it gives instead) or None."""
    for f in sorted(filters):
        lost = None
        for h in hist.values():
            h = [(i, nm) for i, nm in h if i <= to and i not in skip]
            gave = [j for j, (_i, nm) in enumerate(h) if nm == f]
            if not gave:
                continue
            if h[-1][1] == f:
                lost = None
                break
            lost = lost or next(e for e in h[gave[-1] + 1:] if e[1] != f)
        if lost:
            return (f,) + lost
    return None
