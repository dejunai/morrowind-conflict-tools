"""Author-facing findings: one plugin and its declared master chain, never unrelated mod interactions."""
import re
from collections import defaultdict


INTERACTION_TEXT = re.compile(
    r"later plugin|another plugin|other plugin|loads (?:after|before|between)|deleted by|"
    r"replaces it|conflict|load order|is a master of|lists it as a master|both change|"
    r"winner|loses to|overrid|already fixed by|carried over|not active", re.I)


def collect(m, plugins, report, world):
    names = {name.lower() for name, _path in plugins}
    masters = getattr(world, "masters", {})
    known = names | set(masters) | {name.lower() for group in masters.values() for name in group}
    known |= {name.lower() for name in m.OUR_PATCHES}
    mentioned = re.compile(r"(?<![\w])(?:" + "|".join(re.escape(name) for name in sorted(known, key=len, reverse=True))
                           + r")(?![\w])", re.I)
    dependencies = {}

    def allowed(plugin):
        low = plugin.lower()
        if low not in dependencies:
            found, pending = {low}, [low]
            while pending:
                for master in masters.get(pending.pop(), ()):
                    master = master.lower()
                    if master not in found:
                        found.add(master)
                        pending.append(master)
            dependencies[low] = found
        return dependencies[low]

    summaries = defaultdict(dict)
    for (plugin, master), verdict in getattr(world, "master_verdicts", {}).items():
        plugin, master = plugin.lower(), master.lower()
        if plugin not in names or master not in allowed(plugin) or m.is_our_patch(plugin):
            continue
        if verdict.get("obsolete") or verdict.get("none_left") == 0 or verdict["kind"] == "different mod" \
                or (verdict["kind"] == "other version" and verdict["confidence"] >= 0.5):
            summaries[plugin][master] = verdict

    def eligible(issue):
        _sev, plugin, _topic, _info, msg = issue
        if not plugin or plugin.lower() not in names or m.is_our_patch(plugin):
            return False
        related, master = getattr(report, "bug_context", {}).get(issue, ((), None))
        if related is None or (master and master in summaries.get(plugin.lower(), {})):
            return False
        sources = {name.lower() for name in mentioned.findall(msg)} | set(related)
        if master:
            sources.add(master)
        if not sources <= allowed(plugin):
            return False
        return bool(related or master) or not INTERACTION_TEXT.search(msg)

    per = defaultdict(lambda: {"ERROR": [], "WARN": [], "repaired": [], "missing": []})
    accepted = set()
    for issue in report.issues:
        sev, plugin, topic, info, msg = issue
        if sev == "INFO" and msg.endswith("(a master; not changed)"):
            sev = "WARN"
        if sev not in ("ERROR", "WARN") or not eligible(issue):
            continue
        where = " / ".join(x for x in (f"[{topic}]" if topic else "", info) if x)
        per[plugin.lower()][sev].append(f"  - {where + ': ' if where else ''}{msg}")
        accepted.add((plugin.lower(), m.issue_label(topic, info, msg)))
    for plugin, _off, _op, desc, label, _topic, _info in report.fixes:
        if plugin and (plugin.lower(), label) in accepted \
                and {name.lower() for name in mentioned.findall(desc)} <= allowed(plugin):
            per[plugin.lower()]["repaired"].append(f"  - {label}: {desc}")
    for plugin, items in m.OWN_FIXES.items():
        if plugin.lower() not in names or m.is_our_patch(plugin):
            continue
        for repaired, text in items:
            # Generated-patch names here are repair destinations, not evidence of a conflicting mod.
            sources = {name.lower() for name in mentioned.findall(text) if not m.is_our_patch(name)}
            if sources <= allowed(plugin) and not INTERACTION_TEXT.search(text):
                per[plugin.lower()]["repaired" if repaired else "WARN"].append(f"  - {text}")
    for item in getattr(world, "generated", ()):
        rel, why = item[:2]
        plugin = item[3] if len(item) > 3 else ""
        if plugin and plugin.lower() in names and not m.is_our_patch(plugin) and not (len(item) > 2 and item[2]):
            per[plugin.lower()]["missing"].append(f"  - {rel} (needed by {why}); a stand-in was put in its place")
    for plugin, verdicts in summaries.items():
        details = []
        for master, verdict in sorted(verdicts.items()):
            master = verdict["master"]
            if verdict.get("obsolete"):
                details.append(f"'{master}' already includes this plugin's repairs (obsolete patch)")
            else:
                details.append(f"does not match the installed '{master}' (a master update may have made its repairs obsolete)")
        per[plugin]["WARN"].append("  - Master compatibility: " + "; ".join(details) + ".")
    return per
