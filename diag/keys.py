import os, sys, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
GAME = os.path.dirname(TOOLS)
DATA = os.path.join(GAME, "Data Files")
spec = importlib.util.spec_from_file_location("mwn", os.path.join(TOOLS, "mwdialog_check.py"))
M = importlib.util.module_from_spec(spec); sys.modules["mwn"] = M; spec.loader.exec_module(M)
def state_file(game, tools, name):
    """The tools' state file: conflict-tools\\generated\\name when present, else game\\name.
    Looks only; it does not move a leftover copy."""
    gen = os.path.join(tools, "generated", name)
    old = os.path.join(game, name)
    return gen if os.path.exists(gen) else old
files = M.index_dir(DATA)
order = [l.strip() for l in open(state_file(GAME, TOOLS, M.LOAD_ORDER_FILE), encoding="utf-8") if l.strip() and not l.startswith(";")]
mi = M.merged_inputs_of(GAME, DATA); am = M.AUTO_MERGE_NAME.lower()
vorder, _ = M.expand_merged([(n, files[n.lower()]) for n in order], mi)
WANT = {("ALCH", "p_fortify_intelligence_b"), ("CLOT", "aryongloveleft")}
for n, p in vorder:
    if not M.multipatch_source(n): continue
    for _o, t, _f, b in M.iter_records(M.read_plugin_bytes(p)):
        if t in ("ALCH", "CLOT") and M.record_id(t, b) in WANT:
            sub = [(k, (M.cstr(v) if k in ("MODL", "ITEX", "BNAM", "CNAM", "FNAM", "SCRI") else v.hex()[:16])) for k, v in M.iter_subs(b) if k != "NAME"]
            print(t, n, "| masters:", [x for x in M.read_header_masters(p) if not x.lower().endswith(".esm")][:6], "|", sub[:8])
