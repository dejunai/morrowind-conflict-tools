"""mwdialog_mgeghosts.py - MGE XE distant-land overrides for the objects mwcollide hides as exterior cells load.

MGE XE builds distant land from the plugins and never sees those hides, so a hidden object still shows far off
as a ghost. An object (G7 fork: TOML, by object ID) or a mesh (other forks: .ovr, by mesh) is excluded only when
every one of its exterior placements is hidden; one still placed somewhere else is listed instead, since
excluding it would take those copies out of distant land too."""
import json
import os
from collections import Counter

from mwdialog_cellmods import COLLIDE_DATA, object_info
from mwdialog_records import block_key, split_cell
from mwdialog_tes3 import FormatError, cell_key, cstr, iter_records, read_header_masters

NAME = "Conflict Tools Ghost Statics"


def is_g7(game_dir):
    """The G7 fork keeps its settings in mgeXE.toml in the game folder; the others use mge3\\MGE.ini."""
    return os.path.isfile(os.path.join(game_dir, "mgeXE.toml"))


def hidden_exteriors(data_dir):
    """object id -> how many exterior copies mwcollide hides."""
    try:
        with open(os.path.join(data_dir, "MWSE", "config", COLLIDE_DATA), encoding="utf-8") as f:
            config = json.load(f)
            cells = config.get("cells", {}) if isinstance(config, dict) else {}
    except (OSError, ValueError):
        return Counter()
    if not isinstance(cells, dict):
        return Counter()
    return Counter(o["id"].lower() for key, objs in cells.items()
                   if isinstance(key, str) and key.startswith("#") and isinstance(objs, list)
                   for o in objs if isinstance(o, dict) and isinstance(o.get("id"), str))


def exterior_placements(plugins):
    """(object id -> exterior placements left after the whole load order (later plugins win, deletions count),
    ids placed at least once without a teleport destination - a door there swings open in place)."""
    final = {}
    for name, path in plugins:
        try:
            with open(path, "rb") as f:
                data = f.read()
            masters = [x.lower() for x in read_header_masters(path)]
        except (OSError, FormatError):
            continue
        for _off, tag, _flags, body in iter_records(data):
            if tag != "CELL":
                continue
            key, _label = cell_key(body)
            if key is None or key[0] != "e":
                continue
            _head, pers, _nam0, temp = split_cell(body)
            for block in pers + temp:
                bk = block_key(block, masters, name.lower())
                if bk is None:
                    continue
                if any(s == "DELE" for s, _d in block):
                    final.pop(bk, None)
                    continue
                oid = next((cstr(d) for s, d in block if s == "NAME"), "")
                if oid:
                    final[bk] = (oid.lower(), any(s == "DODT" for s, _d in block))
    return (Counter(oid for oid, _t in final.values()),
            {oid for oid, teleports in final.values() if not teleports})


def plan(plugins, data_dir):
    """(object ids to exclude, meshes to exclude, ids hidden in some places but still placed in others).
    Doors that swing open in place are always excluded: distant land bakes them shut, so an opened gate leaves
    a closed ghost behind. Load doors never move and stay."""
    hidden = hidden_exteriors(data_dir)
    placed, in_place = exterior_placements(plugins)
    tag_of, model_of, _scripted = object_info(plugins)
    doors = {i for i in in_place if tag_of.get(i) == "DOOR"}
    hidden_all = {i for i, n in hidden.items() if n >= placed.get(i, 0) > 0}
    ids = sorted(hidden_all | doors)
    shared = sorted(i for i in hidden if i not in hidden_all)
    mesh_hidden, mesh_placed = Counter(), Counter()
    for counts, out in ((hidden, mesh_hidden), (placed, mesh_placed)):
        for i, n in counts.items():
            if model_of.get(i):
                out[model_of[i]] += n
    meshes = {m for m, n in mesh_hidden.items() if n >= mesh_placed.get(m, 0) > 0}
    meshes |= {model_of[i] for i in doors if model_of.get(i)}
    return ids, sorted(meshes), shared


def render(ids, meshes, g7):
    if g7:
        lines = [f"# {NAME}: written by mwdialog_check --cell-conflicts; rewritten on every cell-conflict check.",
                 "# Doors that swing open in place, and objects mwcollide hides everywhere they are placed.",
                 "# Load this file in the",
                 "# distant land generator's static overrides, then regenerate distant land.",
                 "", "[tools.mge-xe.distantland]", "", "exclude_objects = ["]
        lines += [f"{json.dumps(i)}," for i in ids] + ["]"]
    else:
        lines = [f": {NAME}: written by mwdialog_check --cell-conflicts; rewritten on every cell-conflict check.",
                 ": Doors that swing open in place, and meshes whose every exterior copy mwcollide hides.",
                 ": Load this file in the distant land",
                 ": generator's static overrides, then regenerate distant land."]
        lines += [f"{m}=ignore" for m in meshes]
    return "\n".join(lines) + "\n"


def write(game_dir, data_dir, plugins, log=print):
    """Write mge3\\<NAME>.toml (G7) or .ovr (other forks); remove it when nothing needs excluding. Returns its
    path, or None (no MGE XE, or nothing to exclude)."""
    mge3 = os.path.join(game_dir, "mge3")
    if not os.path.isdir(mge3):
        return None
    g7 = is_g7(game_dir)
    ids, meshes, shared = plan(plugins, data_dir)
    path = os.path.join(mge3, NAME + (".toml" if g7 else ".ovr"))
    other = os.path.join(mge3, NAME + (".ovr" if g7 else ".toml"))
    for stale in ([other] + ([path] if not (ids if g7 else meshes) else [])):
        if os.path.exists(stale):
            os.remove(stale)
    if shared:
        log(f"  distant land: {len(shared)} hidden object(s) also placed elsewhere, left in distant land "
            f"(e.g. {', '.join(shared[:3])})")
    if not (ids if g7 else meshes):
        return None
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(render(ids, meshes, g7))
    os.replace(tmp, path)
    log(f"  distant land: {len(ids) if g7 else len(meshes)} ghost static(s) excluded in mge3\\{os.path.basename(path)}"
        f" - add it to the distant land generator's overrides and regenerate")
    return path
