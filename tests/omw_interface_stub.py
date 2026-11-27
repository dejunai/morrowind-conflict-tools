"""Test helper: turn an old-style omw2mwse stub (argv --convert-omwscripts=MODE DIR --json, its JSON on stdout,
exit 0/2/3/4) into one that answers tidy's interface-1 call (openmw-mwse docs/TIDY_INTERFACE.md, omw2mwse 0.3.1):
--staged-root DIR --result-json FILE [--mode M] [--dry-run], the result in FILE, exit 0 ready/none, 1 blocked,
2 failed (conflict, hardcode-not-accepted, error), 70 internal. Like the real converter, exits 1 and 2 and a dry run
leave the staged folder exactly as it was; written_files / moved_files / removed_files are what really changed.
Other calls (recover ...) go to the old stub unchanged. STUB_LOG gets the argv tidy really passed."""

SHIM = r'''
import io, json, os, sys
OLD = %r
argv = sys.argv[1:]
if "--staged-root" not in argv:
    exec(compile(OLD, "stub", "exec"), {"__name__": "__main__"})
    sys.exit(0)
if os.environ.get("STUB_LOG"):
    with open(os.environ["STUB_LOG"], "a", encoding="utf-8") as f:
        f.write(json.dumps(argv) + "\n")
def take(flag, default=None):
    if flag not in argv:
        return default
    i = argv.index(flag)
    v = argv[i + 1]
    del argv[i:i + 2]
    return v
root = take("--staged-root")
result = take("--result-json")
mode = take("--mode", "normal")
dry = "--dry-run" in argv
def snap():
    out = {}
    for b, ds, fs in os.walk(root):
        for fn in fs:
            p = os.path.join(b, fn)
            with open(p, "rb") as f:
                out[os.path.relpath(p, root).replace(os.sep, "/")] = f.read()
    return out
before = snap()
dirs_before = {b for b, ds, fs in os.walk(root)}
os.environ["STUB_LOG"] = os.devnull
sys.argv = [sys.argv[0], "--convert-omwscripts=" + mode, root, "--json"] + argv
buf, real = io.StringIO(), sys.stdout
sys.stdout = buf
code = 0
try:
    exec(compile(OLD, "stub", "exec"), {"__name__": "__main__"})
except SystemExit as e:
    code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
finally:
    sys.stdout = real
text = buf.getvalue()
try:
    old = json.loads(text[text.index("{"):])
except ValueError:
    sys.exit(70)
mods, errors, blockers, excluded = [], [], [], False
for m in old.get("mods") or []:
    if not isinstance(m, dict):
        continue
    m = dict(m)
    if m.get("verdict") == "partial":
        m["verdict"] = "ready"                        # interface 1 has no partial verdict
    r = m.get("reason")
    if isinstance(r, dict) and r.get("code") == "author-opt-out":
        m.pop("reason")
        m["excluded_by_author"] = excluded = True
        m["blockers"] = []
    else:
        m["blockers"] = [str(a.get("message")) for a in m.get("alerts") or []
                         if isinstance(a, dict) and a.get("code") == "blocker"]
    blockers += m["blockers"]
    for c in m.get("conflicts") or []:
        errors.append({"code": "conflict", "message": "%%s: %%s" %% (c.get("path"), c.get("reason")), "mod": m.get("name")})
    mods.append(m)
if code == 0 and old.get("pendingRecovery"):
    new = 70                                          # an unfinished run: interface 1's internal error
elif code == 0:
    new = 1 if any(m.get("verdict") == "blocked" for m in mods) else 0
elif code == 4:
    new = 2
elif code == 3:
    new = 2
    errors.append({"code": "hardcode-not-accepted", "message": next((m.get("message") for m in mods if m.get("message")),
                                                                    "hard-code conversions not accepted")})
elif code == 2:
    new = 2
    errors.append({"code": "error", "message": next((m.get("message") for m in mods if m.get("message")), "error")})
else:
    new = 70
after = snap()
if new in (1, 2) or (dry and new != 70):              # nothing is written but the result
    for rel in after:
        if rel not in before:
            os.remove(os.path.join(root, rel))
    for rel, data in before.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if after.get(rel) != data:
            with open(p, "wb") as f:
                f.write(data)
    for b, ds, fs in sorted(os.walk(root), key=lambda w: -len(w[0])):  # folders the stub made, emptied
        if b not in dirs_before and not os.listdir(b):
            os.rmdir(b)
    written = moved = removed = []
else:
    new_bytes = {after[k] for k in after if k not in before}
    written = sorted(k for k in after if before.get(k) != after[k])
    moved = sorted(k for k in before if k not in after and before[k] in new_bytes)
    removed = sorted(k for k in before if k not in after and k not in moved)
verdict = {0: ("ready" if mods else "none"), 1: "blocked", 2: "failed", 70: "error"}[new]
doc = {"interface": 1, "tool": "omw2mwse", "version": "0.3.1", "requiresPython": old.get("requiresPython", ">=3.9"),
       "staged_root": root, "dry_run": dry, "exit_code": new, "verdict": verdict, "blockers": blockers,
       "guards": [], "runtime_version": "0.4.0", "written_files": written, "planned_files": written,
       "removed_files": removed, "moved_files": moved, "excluded_by_author": excluded, "errors": errors, "mods": mods}
if old.get("pendingRecovery") is not None:
    doc["pendingRecovery"] = old["pendingRecovery"]
with open(result, "w", encoding="utf-8", newline="\n") as f:
    json.dump(doc, f, indent=1)
sys.exit(new)
'''


def new_interface_stub(old_stub):
    """The source of a stub script speaking interface 1, wrapping the old-style stub source old_stub."""
    return SHIM % old_stub


def mode_of(argv):
    """The --mode value of a logged interface-1 call (normal when it is not given)."""
    return argv[argv.index("--mode") + 1] if "--mode" in argv else "normal"
