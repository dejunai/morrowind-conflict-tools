import os, sys, importlib.util
GAME = r"G:\Program Files\Steam\steamapps\common\Morrowind"; DATA = os.path.join(GAME, "Data Files")
spec = importlib.util.spec_from_file_location("mwn", os.path.join(os.path.dirname(os.path.abspath(__file__)), "mwdialog_check_new.py"))
M = importlib.util.module_from_spec(spec); sys.modules["mwn"] = M; spec.loader.exec_module(M)
files = M.index_dir(DATA)
order = [l.strip() for l in open(os.path.join(GAME, M.LOAD_ORDER_FILE), encoding="utf-8") if l.strip() and not l.startswith(";")]
mi = M.merged_inputs_of(GAME, DATA); am = M.AUTO_MERGE_NAME.lower()
vorder, _ = M.expand_merged([(n, files[n.lower()]) for n in order], mi)
WANT = {("ALCH", "p_fortify_intelligence_b"), ("CLOT", "aryongloveleft")}
for n, p in vorder:
    if not M.multipatch_source(n): continue
    for _o, t, _f, b in M.iter_records(M.read_plugin_bytes(p)):
        if t in ("ALCH", "CLOT") and M.record_id(t, b) in WANT:
            sub = [(k, (M.cstr(v) if k in ("MODL", "ITEX", "BNAM", "CNAM", "FNAM", "SCRI") else v.hex()[:16])) for k, v in M.iter_subs(b) if k != "NAME"]
            print(t, n, "| masters:", [x for x in M.read_header_masters(p) if not x.lower().endswith(".esm")][:6], "|", sub[:8])
