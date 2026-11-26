r"""diag/luafix_kb_compare.py - read-only: do luafix's general rules reproduce the Known Bugs repairs?

For every Known Bugs part (KB/KP/KR) whose file is under the given MWSE folder, the file is read and put back to the
text the part was written for (an installed file that already has the repair gets it reversed, in memory only). The
general rules alone (Known Bugs switched off, --level medium) then work out their patch, and the part is classed:
  same      the rule patch contains the part's repaired text exactly
  compiles  every line the part changes is changed by a rule too, and the whole rule patch compiles
  none      neither (or the part's text is not in the file: 'absent')
It also lists every finding of the rules added on 2026-11-26 (Y1, F3, R1/H2/H4 fixes, A1 at medium, the new A3
lookups, I1's icons/BSA/doubled/unique-name cases) over the whole folder, for false-positive review. Nothing is
written except the report files given with --out.

    python diag/luafix_kb_compare.py --mwse "<Morrowind>\\Data Files\\MWSE" --out <folder> [--originals <dir>]

--originals (repeatable): folders of older copies to read too (luafix's backups\luafix): for each Known Bugs file the
copy holding the most of its parts' original text is used, before reversing repairs in the installed copy.
"""
import argparse
import collections
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mwdialog_luafix as lf                     # noqa: E402

NEW_LOOKUPS = ("tes3.getCurrentWeather", "tes3.getPlayerCell", "tes3.getPlayerRef", "tes3.findGlobal")


def changed_lines(a, b):
    """0-based line numbers of a that b changes (an insert counts against the line it goes before)."""
    out = set()
    al, bl = a.split("\n"), b.split("\n")
    for tag, i1, i2, _j1, _j2 in difflib.SequenceMatcher(None, al, bl, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        out |= set(range(i1, i2)) if i2 > i1 else {i1}
    return out


def strip_head(text):
    """The rule patch without what build_patch puts at the start of line 1 (marker and helpers)."""
    ip = lf.insert_point(text)
    m = lf.MARK_RE.match(text, ip)
    if not m:
        return text
    rest = text[m.end():]
    for helper in (lf.GATE_HELPER, lf.SAVE_HELPER):
        if rest.startswith(helper):
            rest = rest[len(helper):]
    return text[:ip] + rest


def rule_patch(orig, key, rel, cfg, roots, bsa, level):
    """(patched text or None, rules, findings) from the general rules only, at level."""
    a = lf._analyse(orig, key, rel, cfg)
    images = lf.image_findings(a.src, roots, bsa)
    findings = [f for f in a.findings + images if not lf._kb_rule(f["rule"])]
    new, rules = lf.build_patch(a.src, findings, key, cfg, level, False)
    if new is None and a.src != orig:
        new = a.src
    return new, rules, findings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mwse", required=True, help="the Data Files\\MWSE folder to read")
    ap.add_argument("--out", required=True, help="folder for kb_compare.txt / kb_compare.json")
    ap.add_argument("--originals", action="append", default=[], help="folder of older copies (read only)")
    args = ap.parse_args(argv)
    mwse = os.path.abspath(args.mwse)
    data_dir = os.path.dirname(mwse)
    cfg = dict(lf.DEFAULTS)
    lf.ensure_own_mods(cfg, data_dir)
    checker = lf.find_checker()
    bsa = lf.bsa_names(data_dir)
    kb_all, kb_whole = list(lf.KNOWN_BUGS), set(lf.KNOWN_BUGS_WHOLE)
    by_path = collections.defaultdict(list)
    for rule, plugin, path, old, new, _what in kb_all:
        by_path[path].append((rule, plugin, old, new))
    rows, per_rule, per_rule_med = [], collections.defaultdict(list), collections.defaultdict(list)
    older = collections.defaultdict(list)            # lower-case path under MWSE -> older copies
    for top in args.originals:
        for dp, _dn, fns in os.walk(top):
            for fn in fns:
                if fn.lower().endswith(".lua"):
                    low = os.path.join(dp, fn).replace("\\", "/").lower()
                    i = low.rfind("/mwse/")
                    if i >= 0:
                        rel = low[i + len("/mwse/"):]
                        older[rel[len("mods/"):] if rel.startswith("mods/") else rel].append(os.path.join(dp, fn))
    lf.KNOWN_BUGS[:] = []                         # the rules alone
    try:
        for path, parts in sorted(by_path.items()):
            full = os.path.join(mwse, *path.split("/")) if path.startswith(lf.KB_ROOTS) else \
                os.path.join(mwse, "mods", *path.split("/"))
            if not os.path.isfile(full):
                for rule, _pl, _o, _n in parts:
                    per_rule[rule].append("missing")
                    per_rule_med[rule].append("missing")
                    rows.append({"rule": rule, "path": path, "class": "missing"})
                continue
            with open(full, "rb") as fh:
                text = lf.unbrand(fh.read().decode("latin-1"))
            def olds_in(t):
                c = "\r\n" in t
                return sum(1 for _r, _pl, old, _n in parts if (old.replace("\n", "\r\n") if c else old) in t)
            orig = text
            for cand in older.get(path, ()):         # the older copy with the most original text
                with open(cand, "rb") as fh:
                    t = lf.unbrand(fh.read().decode("latin-1"))
                if olds_in(t) > olds_in(orig):
                    orig = t
            crlf = "\r\n" in orig
            for _r, _pl, old, new in parts:          # back to the text the parts were written for
                o, n = (old.replace("\n", "\r\n"), new.replace("\n", "\r\n")) if crlf else (old, new)
                if o not in orig and orig.count(n) == 1:
                    orig = orig.replace(n, o)
            mroot, rel = lf.mods_root_of(full)
            key = lf.mod_key_of(mroot, rel) if mroot else path.split("/")[0]
            roots = [data_dir]
            got = {}
            for level in ("high", "medium"):
                err = None
                try:
                    patched, rules, _f = rule_patch(orig, key, path, cfg, roots, bsa, level)
                except Exception as e:               # the rules can't read it either
                    patched, rules, err = None, [], str(e)[:120]
                body = strip_head(patched) if patched else orig
                compiles = bool(patched) and (checker is None or checker.check(patched)[0])
                got[level] = (patched, rules, err, body, compiles, changed_lines(orig, body))
            for rule, _pl, old, new in parts:
                o, n = (old.replace("\n", "\r\n"), new.replace("\n", "\r\n")) if crlf else (old, new)
                i = orig.find(o)
                cls = {}
                for level, (patched, rules, err, body, compiles, rl) in got.items():
                    if i < 0:
                        cls[level] = "absent"
                        continue
                    base = orig.count("\n", 0, i)
                    kl = {base + x for x in changed_lines(o, n)}
                    if patched and body.count(n) > orig.count(n):
                        cls[level] = "same"
                    elif patched and kl <= rl and compiles:
                        cls[level] = "compiles"
                    else:
                        cls[level] = "none"
                per_rule[rule].append(cls["high"])
                per_rule_med[rule].append(cls["medium"])
                rows.append({"rule": rule, "path": path, "class": cls["high"], "class_medium": cls["medium"],
                             "rules": got["high"][1], "rules_medium": got["medium"][1], "error": got["high"][2],
                             "compiles": got["high"][4]})
    finally:
        lf.KNOWN_BUGS[:] = kb_all
        lf.KNOWN_BUGS_WHOLE.clear()
        lf.KNOWN_BUGS_WHOLE.update(kb_whole)
    retire = sorted((r for r, c in per_rule.items() if c and all(x in ("same", "compiles") for x in c)),
                    key=lf._kb_order)
    # new-rule findings over the whole folder (plan mode: nothing is written)
    rep = lf.check_paths([os.path.join(mwse, "mods")], cfg, checker=checker, level="medium", data_dir=data_dir,
                         use_cache=False)
    review = []
    for p, ent in sorted(rep.files.items()):
        for f in ent["findings"]:
            r, w = f["rule"], f["what"]
            new_kind = r in ("Y1", "F3") or (r in ("R1", "H2", "H4") and f["conf"] in ("high", "medium")) or \
                (r == "A1" and f["conf"] == "medium") or (r == "A3" and any(x in w for x in NEW_LOOKUPS)) or \
                (r == "I1" and ("extension twice" in w or "only file of that name" in w))
            if new_kind and f["conf"] in ("high", "medium"):
                review.append({"file": os.path.relpath(p, mwse), "rule": r, "conf": f["conf"], "line": f["line"],
                               "what": w, "fix": f["fix"][:200], "kb_file": ent["rel"] in by_path})
    os.makedirs(args.out, exist_ok=True)
    tally = collections.Counter(x["class"] for x in rows)
    with open(os.path.join(args.out, "kb_compare.json"), "w", encoding="utf-8") as fh:
        json.dump({"tally": tally, "per_rule": per_rule, "per_rule_medium": per_rule_med, "retire": retire, "rows": rows, "review": review}, fh,
                  indent=1)
    tally_med = collections.Counter(x["class_medium"] for x in rows if "class_medium" in x)
    lines = [f"Known Bugs parts, rules at --level high (the default): {dict(tally)}",
             f"  at --level medium: {dict(tally_med)}",
             f"retire (every part same/compiles at high): {' '.join(retire) or '-'}", ""]
    for r in sorted(per_rule, key=lf._kb_order):
        lines.append(f"{r:5} high {dict(collections.Counter(per_rule[r]))}  medium "
                     f"{dict(collections.Counter(per_rule_med[r]))}")
    outside = [x for x in review if not x["kb_file"]]
    lines += ["", f"new-rule findings: {len(review)} ({len(outside)} outside Known Bugs files); by rule: "
              f"{dict(collections.Counter(x['rule'] + ':' + x['conf'] for x in review))}", ""]
    for x in review:
        lines.append(f"{x['rule']} {x['conf']:6} {x['file']}:{x['line']}  {x['what'][:150]}"
                     + ("  [KB file]" if x["kb_file"] else ""))
    with open(os.path.join(args.out, "kb_compare.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines[:5 + len(per_rule) + 3]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
