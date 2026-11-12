import os, sys, importlib.util, struct, json
from collections import Counter, defaultdict
GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(GAME, "Data Files")
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod); return mod
OLD = load("mw_old", os.path.join(GAME, "mwdialog_check.py"))
NEW = load("mw_new", os.path.join(os.path.dirname(os.path.abspath(__file__)), "mwdialog_check_new.py"))
files = NEW.index_dir(DATA)
order = [l.strip() for l in open(os.path.join(GAME, NEW.LOAD_ORDER_FILE), encoding="utf-8", errors="replace")
         if l.strip() and not l.strip().startswith(";")]
active = [(n, files[n.lower()]) for n in order if n.lower() in files]
print("active", len(active), "of", len(order))
mi = NEW.merged_inputs_of(GAME, DATA)
am = NEW.AUTO_MERGE_NAME.lower()
missing = [i for i, p in mi.get(am, []) if not p]
print("merge inputs", len(mi.get(am, [])), "missing files", missing)

def desc(raw):
    b = raw[16:]
    d = defaultdict(list)
    for n, v in NEW.iter_subs(b):
        d[n].append(v)
    return d
def diffsum(a, b):
    da, db = desc(a), desc(b)
    out = []
    for k in sorted(set(da) | set(db)):
        if da.get(k) != db.get(k):
            va = NEW.cstr(da[k][0]) if k in da and k in ("SCRI","SNAM","MODL","ITEX","FNAM","ENAM","RNAM","CNAM","ANAM","BNAM","KNAM") else (len(da.get(k, [])) if k in da else None)
            vb = NEW.cstr(db[k][0]) if k in db and k in ("SCRI","SNAM","MODL","ITEX","FNAM","ENAM","RNAM","CNAM","ANAM","BNAM","KNAM") else (len(db.get(k, [])) if k in db else None)
            out.append(f"{k}: {va!r} -> {vb!r}")
    return out

# real winning body per key in active order
def winners(keys):
    want = {k[0] for k in keys}
    win = {}
    for n, p in active:
        if not NEW.multipatch_source(n):
            continue
        for _o, t, _f, b in NEW.iter_records(NEW.read_plugin_bytes(p)):
            if t in want:
                nm = NEW.first_sub(b, b"NAME")
                if nm is not None and (t, NEW.cstr(nm).lower()) in keys:
                    win[(t, NEW.cstr(nm).lower())] = (n, b"%s" % t.encode() + struct.pack("<III", len(b), 0, 0) + b)
    return win

print("== multipatch object merge: old vs new", file=sys.stderr)
old = {k: r for k, r, _n in OLD.object_merges(active)} if hasattr(OLD, "object_merges") else None
if old is None:
    recs, notes = OLD.merged_objects(active)
    old = {}
    for r in recs:
        b = r[16:]; nm = OLD.first_sub(b, b"NAME"); old[(r[:4].decode(), OLD.cstr(nm).lower())] = r
new = {k: r for k, r, _n in NEW.object_merges(active, merged_inputs=mi)}
new_only = sorted(set(new) - set(old)); old_only = sorted(set(old) - set(new))
changed = sorted(k for k in set(old) & set(new) if old[k][16:] != new[k][16:])
print(f"multipatch merged objects: old {len(old)}, new {len(new)}; new-only {len(new_only)}, dropped {len(old_only)}, different {len(changed)}")
allk = set(new_only) | set(old_only) | set(changed)
win = winners(allk)
by_tag = Counter(k[0] for k in allk)
print("by type:", dict(by_tag))
def eff(k):  # what the game would get: old vs new
    w = win.get(k, ("?", None))[1]
    o = old.get(k, w); n = new.get(k, w)
    return diffsum(o, n) if o and n else ["?"]
ex = []
for k in sorted(allk, key=lambda k: (k != ("LIGH", "light_com_lantern_02_200_boat"), k)):
    ex.append((k, win.get(k, ("?",))[0], eff(k)))
print("winner of affected keys:", Counter(e[1] for e in ex).most_common(5))
real = [e for e in ex if e[2]]
print("keys where the game record changes (old vs new, same settings):", len(real), "by type:", dict(Counter(e[0][0] for e in real)))
fc = Counter(f.split(":")[0] for e in real for f in e[2])
print("fields that change:", dict(fc))
for k, w, d in real[:12]:
    print(" ", k, "|", "; ".join(d)[:200])
print("dropped (old merged, new not):")
for k in old_only:
    print("  ", k, "|", "; ".join(eff(k))[:200])

sys.exit(0)
print("== AutoMerge itself: objects 2+ inputs change", file=sys.stderr)
ins = [(i, p) for i, p in mi.get(am, []) if p]
keys = defaultdict(list); bodies = {}
for i, p in ins:
    for _o, t, _f, b in NEW.iter_records(NEW.read_plugin_bytes(p)):
        rid = NEW.record_id(t, b)
        if rid is None or t in ("TES3", "CELL", "DIAL", "INFO", "LAND", "PGRD"):
            continue
        keys[rid].append(i); bodies.setdefault(rid, []).append(b)
shared = {k for k, v in keys.items() if len(v) >= 2}
shared_diff = {k for k in shared if len(set(bodies[k])) >= 2}
print(f"records 2+ inputs define: {len(shared)}, with different contents: {len(shared_diff)}; by type:",
      dict(Counter(k[0] for k in shared_diff)))
obj_shared = {k for k in shared if k[0] in NEW.MERGE_TAGS}
vorder, _own = NEW.expand_merged(active, mi)
got = NEW.object_merges(vorder, file_ok=NEW.merge_file_check(type("A", (), {"data_dir": DATA})(), None), only=obj_shared)
amb = {}
for _o, t, _f, b in NEW.iter_records(NEW.read_plugin_bytes(files[am])):
    rid = NEW.record_id(t, b)
    if rid in obj_shared:
        amb[rid] = b"%s" % t.encode() + struct.pack("<III", len(b), 0, 0) + b
chg = [(k, r) for k, r, _n in got if k in amb and amb[k][16:] != r[16:]]
print(f"AutoMerge records the in-merge object merge would change: {len(chg)} (of {len(obj_shared)} shared objects); by type:", dict(Counter(k[0] for k, _r in chg)))
for k, r in sorted(chg, key=lambda x: (x[0] != ("LIGH", "light_com_lantern_02_200_boat"), x[0]))[:25]:
    print(" ", k, "inputs:", keys[k], "|", "; ".join(diffsum(amb[k], r))[:300])
other = Counter(k[0] for k in shared_diff if k[0] not in NEW.MERGE_TAGS)
print("non-object types 2+ inputs change differently (still last-input-wins):", dict(other))
for k in sorted(k for k in shared_diff if k[0] not in NEW.MERGE_TAGS)[:15]:
    print("  ", k, keys[k])
