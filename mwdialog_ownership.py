"""Ownership checks shared by the scanner and Cell Fixes patch builder."""

import re
from collections import Counter, defaultdict


PUBLIC_PLACE_RE = re.compile(r"tavern|tradehouse|cornerclub|\bclub\b|\binn\b|guild|\bshop\b|smithy|outfitter|"
                             r"pawnbroker|bookseller|alchemist|apothecary|trader|temple|market", re.I)
HOME_RE = re.compile(r"house|home|shack|hut|manor|quarters|room|apartment|tent|shanty|hovel|cabin|farmhouse", re.I)


def door_owner_verdicts(doors, placements, npc_class, npc_name, reachable):
    """Find doors whose owner is not placed behind them and return safe fixes."""
    where, placed, inside = defaultdict(set), Counter(), defaultdict(set)
    for key, npc in placements:
        where[npc].add(key)
        placed[npc] += 1
        inside[key].add(npc)

    def near(a, b):
        return a == b or (a[0] == b[0] == "e" and abs(a[1] - b[1]) <= 1 and abs(a[2] - b[2]) <= 1)

    def building(name):
        return name.lower().split(":")[0].strip()

    out = []
    for key, door, owner, dest, vanilla in doors:
        if not owner or not dest or vanilla == owner:
            continue
        if "guard" in owner or "guard" in npc_class.get(owner, ""):
            continue
        to = ("i", dest.lower())
        homes = where.get(owner, set())
        if owner in npc_class:
            if to in homes or not homes or (key[0] == "i" and key in homes):
                continue
            if placed[owner] == 1 and near(key, next(iter(homes))):
                continue
            if all(c[0] == "i" and c[1] not in reachable for c in homes):
                continue
            rooms = {building(c[1]) for c in homes if c[0] == "i"}
            if building(dest) in rooms or (key[0] == "i" and building(key[1]) in rooms):
                continue
            if any(len(w) >= 4 and w in dest.lower() for w in re.findall(r"[\w']+", npc_name.get(owner, ""))):
                continue
            lives = ", ".join(sorted((c[1] if c[0] == "i" else f"({c[1]}, {c[2]})") for c in homes)[:3])
            who = f"'{owner}', who is placed in {lives}, not there"
        else:
            who = f"'{owner}', which is no NPC (a faction or class name in the person slot?)"
        residents = sorted(inside.get(to, ()))
        if PUBLIC_PLACE_RE.search(dest):
            out.append((door, f"door to '{dest}' is owned by {who}; it leads to a public place, so the owner was "
                              f"copied with the door: --fix takes it off", ""))
        elif (len(residents) == 1 and placed[residents[0]] == 1 and "guard" not in residents[0]
              and "guard" not in npc_class.get(residents[0], "") and HOME_RE.search(dest)
              and not re.search(r"common|bunk|barrack|dorm|\bhall\b|hold_", dest, re.I)
              and dest.lower().split(",")[0] not in {c[1].split(",")[0] for c in homes if c[0] == "i"}):
            out.append((door, f"door to '{dest}' is owned by {who}; the one person living there is "
                              f"'{residents[0]}': --fix gives it to them", residents[0]))
        else:
            out.append((door, f"door to '{dest}' is owned by {who}; who it belongs to isn't clear, so it is left "
                              f"as it is", None))
    return out


def item_owner_verdicts(items, placements, npc_class, npc_name, reachable):
    """Find grouped interior objects owned by someone placed elsewhere."""
    where, placed, inside = defaultdict(set), Counter(), defaultdict(set)
    for key, npc in placements:
        where[npc].add(key)
        placed[npc] += 1
        inside[key].add(npc)

    def towns(name):
        return {name.split(":")[0].strip(), name.split(",")[0].strip()}

    groups = defaultdict(list)
    for key, item, owner, kind, vanilla in items:
        if not owner or key[0] != "i" or vanilla == owner or "guard" in owner or "guard" in npc_class.get(owner, ""):
            continue
        homes = where.get(owner, set())
        if key in homes or not homes or key[1] not in reachable or any(c[0] == "e" for c in homes):
            continue
        if all(c[1] not in reachable for c in homes) or towns(key[1]) & {p for c in homes for p in towns(c[1])}:
            continue
        if any(len(w) >= 4 and w in key[1] for w in re.findall(r"[\w']+", npc_name.get(owner, "").lower())):
            continue
        groups[(key, owner)].append((item, kind))
    out = []
    for (key, owner), members in sorted(groups.items(), key=repr):
        kinds = Counter(k for _i, k in members)
        lives = ", ".join(sorted(c[1] for c in where[owner])[:3])
        what = ", ".join(f"{n} {k}(s)" for k, n in sorted(kinds.items()))
        residents = sorted(inside.get(key, ()))
        if (len(residents) == 1 and placed[residents[0]] == 1 and "guard" not in residents[0]
                and "guard" not in npc_class.get(residents[0], "") and HOME_RE.search(key[1])
                and not re.search(r"common|bunk|barrack|dorm|\bhall\b|hold_", key[1])):
            verdict, action = f"the one person living here is '{residents[0]}': --fix gives them to them", residents[0]
        else:
            verdict, action = "who they belong to isn't clear, so they are left as they are", None
        out.append((key, owner, [i for i, _k in members],
                    f"{what} here owned by '{owner}', who is placed in {lives}, not here; {verdict}", action))
    return out
