import os, sys
GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else GAME)
import mwdialog_check as M
DATA = os.path.join(GAME, "Data Files")
files = {f.lower(): os.path.join(DATA, f) for f in os.listdir(DATA) if f.lower().endswith((".esp", ".esm"))}
order = [l.strip() for l in open(os.path.join(GAME, M.LOAD_ORDER_FILE), encoding="utf-8", errors="replace")
         if l.strip() and not l.strip().startswith(";")]
rec = M.read_merge_record(GAME)
inputs = rec.get(M.AUTO_MERGE_NAME, [])
WANT = ("LIGH", "light_com_lantern_02_200_boat")
def show(name, path):
    data = M.read_plugin_bytes(path)
    for off, tag, fl, body in M.iter_records(data):
        if tag == "LIGH" and M.record_id(tag, body) == WANT:
            subs = [(n, (M.cstr(d) if n in ("NAME","SCRI","SNAM","MODL","FNAM","ITEX") else d.hex()[:40])) for n, d in M.iter_subs(body)]
            print(f"  {name}: {subs}")
            return True
    return False
print("active plugins:", len(order), " merge inputs:", len(inputs))
print("Active plugins with the lantern:")
for i, n in enumerate(order):
    p = files.get(n.lower())
    if p and show(f"#{i} {n}", p):
        pass
print("Merge inputs with the lantern:")
for n in inputs:
    p = files.get(n.lower())
    if not p:
        print("  (missing file)", n); continue
    if show(n, p):
        print("     masters:", M.read_header_masters(p))
am = M.read_header_masters(files[M.AUTO_MERGE_NAME.lower()])
print("AutoMerge masters:", len(am), "Expanded Sounds in them:", [m for m in am if "expanded sounds" in m.lower()])
