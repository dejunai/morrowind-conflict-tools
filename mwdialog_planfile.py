"""mwdialog_planfile.py - plan files that can't be enacted twice (vortex_tidy.py, mwdialog_luafix.py).

After an --apply the plan file it enacted is blanked: only a header comment is left, and a plan file whose
every non-empty line is a "#" comment holds no actions, so the next --apply stops ("run plan mode first").
When some actions were not applied (an error, a refused patch, an interruption) the plan is rewritten with
only those. Every write is atomic (a temp file, then a rename). A copy of the plan as reviewed and as enacted
goes to the run's backup folder for auditing. --undo never reads the plan file (it works from the journal).
"""
import os
import shutil
import time

APPLIED_TAG = "nothing pending"


def tz_abbrev():
    z = time.strftime("%Z") or ""
    return "".join(w[0] for w in z.split()) if " " in z else z


def stamp():
    return f"{time.strftime('%Y-%m-%d %H:%M:%S')} {tz_abbrev()}".strip()


def write_atomic(path, text):
    """Write text (utf-8) through a temp file in the same folder and a rename, so a reader never sees half a
    plan; an interruption leaves the old file or the new one."""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, f".{os.path.basename(path)}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    for i in range(10):                     # Windows: a reader (an editor, a virus scanner) can hold it a moment
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == 9:
                os.remove(tmp)
                raise
            time.sleep(0.2)


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def state(path):
    """'missing', 'applied' (only comments: no actions) or 'pending'."""
    t = read(path)
    if t is None:
        return "missing"
    if all(not ln.strip() or ln.lstrip().startswith("#") for ln in t.splitlines()):
        return "applied"
    return "pending"


def header_of(path):
    t = read(path) or ""
    return next((ln.strip() for ln in t.splitlines() if ln.strip()), "")


def refuse_message(path, tool):
    return (f"The plan is empty / already applied ({header_of(path) or os.path.basename(path)}): nothing to do. "
            f"Run {tool} in plan mode first (without --apply), review it, then --apply.")


def blank_text(tool, note=""):
    return (f"# applied {stamp()} by {tool} --apply; {APPLIED_TAG}. Rerun in plan mode to regenerate."
            + (f"\n# {note}" if note else "") + "\n")


def partial_text(tool, remaining, note=""):
    n = sum(1 for ln in remaining if ln.strip())
    head = (f"# partially applied {stamp()} by {tool} --apply: the actions below were NOT applied (everything "
            f"else in the plan was). Rerun in plan mode to regenerate.")
    return head + (f"\n# {note}" if note else "") + "\n" + "\n".join(remaining).rstrip("\n") + "\n" \
        if n else blank_text(tool, note)


def audit_copy(audit_dir, reviewed=None, enacted=None):
    """Keep the plan as it was when --apply started (reviewed) and as this run computed it (enacted)."""
    os.makedirs(audit_dir, exist_ok=True)
    out = []
    for name, text in (("plan_reviewed.txt", reviewed), ("plan_enacted.txt", enacted)):
        if text is not None:
            p = os.path.join(audit_dir, name)
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            out.append(p)
    return out


def finish(path, tool, remaining, audit_dir, reviewed=None, enacted=None, note="", log=print):
    """After --apply: audit copies, then the plan blanked (or cut down to what is left), atomically."""
    copies = audit_copy(audit_dir, reviewed, read(path) if enacted is None else enacted)
    text = partial_text(tool, remaining, note) if remaining else blank_text(tool, note)
    write_atomic(path, text)
    left = sum(1 for ln in remaining if ln.strip()) if remaining else 0
    if left:
        log(f"Plan {path}: cut down to the {left} line(s) NOT applied (copy of the enacted plan: "
            f"{copies[-1] if copies else audit_dir}).")
    else:
        log(f"Plan {path}: applied and blanked, so it can't be applied twice (copy: "
            f"{copies[-1] if copies else audit_dir}).")
    return copies


def same_actions(a, b):
    """Do two plan texts list the same actions (ignoring the dated first line and comments)?"""
    def body(t):
        ls = [ln.rstrip() for ln in (t or "").splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
        return ls[1:] if ls and ("plan" in ls[0].lower()) else ls
    return body(a) == body(b)
