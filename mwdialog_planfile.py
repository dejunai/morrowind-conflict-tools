"""mwdialog_planfile.py - plan files that can't be enacted twice (vortex_tidy.py, mwdialog_luafix.py).

After an --apply the plan file it enacted is blanked: only a header comment is left, and a plan file whose
every non-empty line is a "#" comment holds no actions, so the next --apply stops ("run plan mode first").
When some actions were not applied (an error, a refused patch, an interruption) the plan is rewritten with
only those. Every write is atomic (a temp file, then a rename). A copy of the plan as reviewed and as enacted
goes to the run's backup folder for auditing. --undo never reads the plan file (it works from the journal).
"""
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_text as MT                                  # noqa: E402
print = MT.printer()                                        # noqa: A001

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
            if i < 9:
                time.sleep(0.2)
    # still held open by a program that doesn't allow a rename over it: write it in place instead (a plan left
    # pending after its --apply is the thing to avoid), and say so
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"(note: {path} is open in another program, so it was rewritten in place rather than replaced)")
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


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


# ---------------------------------------------------------------------------------------------- strict --apply
# --apply enacts a plan only when the plan it works out lists the same actions as the plan file on disk (the
# one you reviewed). Actions are compared as a multiset of (context, action line): the mod / Lua file they
# belong to and the action itself; headers, comments, dates, notes, summaries, report-only findings and the
# order of the lines are ignored (the order --apply uses is computed the same deterministic way plan mode
# does, so the same set means the same run).
import collections                                                     # noqa: E402
import re                                                              # noqa: E402

SECTION_HEADS = ("LUA CHECK", "ASSET CHECK")
_DATED_HEAD = re.compile(r"\bplan\b.*\d{4}-\d\d-\d\d")
_FINDING = re.compile(r"^[A-Z]\d+ (high|medium)\s")
_ACTION_START = ("remove empty", "=> patch ready", "repair ", "shorten ")


def sections(text):
    """{"moves": ..., "LUA CHECK": ..., "ASSET CHECK": ...}: the parts of a plan file's text (each without
    its heading line)."""
    out, cur = {"moves": []}, "moves"
    for ln in (text or "").splitlines():
        if ln.strip() in SECTION_HEADS and not ln.startswith(" "):
            cur = ln.strip()
            out.setdefault(cur, [])
            continue
        out.setdefault(cur, []).append(ln)
    return {k: "\n".join(v) for k, v in out.items()}


def actions(text):
    """The actions a plan text lists: Counter of (context, action)."""
    got = collections.Counter()
    mod = lua = ""
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if not ln.startswith(" "):
            if s in SECTION_HEADS or _DATED_HEAD.search(s):
                continue
            mod, lua = s, ""
            continue
        if s.startswith("lua "):
            lua = s
            continue
        if not ln.startswith("    "):
            continue                                    # head notes, "left alone", summaries
        if "  ->  " in s or s.startswith(_ACTION_START) or _FINDING.match(s):
            got[(mod + (" | " + lua if lua else ""), s)] += 1
    return got


def compare(reviewed_text, fresh_text, parts=None):
    """(added, removed): actions in the fresh plan but not the reviewed one, and the other way round, over the
    given parts (None: the whole plan)."""
    if parts is None:
        a, b = actions(reviewed_text), actions(fresh_text)
    else:
        rs, fs = sections(reviewed_text), sections(fresh_text)
        a, b = collections.Counter(), collections.Counter()
        for p in parts:
            a += actions(rs.get(p, ""))
            b += actions(fs.get(p, ""))
    return list((b - a).elements()), list((a - b).elements())


def has_any_actions(text, parts=None):
    if parts is None:
        return bool(actions(text))
    s = sections(text)
    return any(actions(s.get(p, "")) for p in parts)


def prev_path(path):
    base, ext = os.path.splitext(path)
    return base + ".prev" + (ext or ".txt")


def diff_summary(added, removed, show=5):
    def fmt(x):
        ctx, a = x
        return f"      {ctx}: {a}" if ctx else f"      {a}"
    out = [f"  {len(added)} action(s) added, {len(removed)} removed since the plan you reviewed"]
    if added:
        out.append("    added:")
        out += [fmt(x)[:220] for x in added[:show]] + ([f"      ... and {len(added) - show} more"]
                                                       if len(added) > show else [])
    if removed:
        out.append("    removed:")
        out += [fmt(x)[:220] for x in removed[:show]] + ([f"      ... and {len(removed) - show} more"]
                                                         if len(removed) > show else [])
    return out


def refuse_mismatch(path, fresh_text, added, removed, tool, log=print):
    """The plan changed since it was reviewed: keep the reviewed file as <plan>.prev.txt, write the fresh one
    (to review), say what changed. Nothing is enacted."""
    prev = prev_path(path)
    if os.path.exists(path):
        shutil.copyfile(path, prev)
    write_atomic(path, fresh_text)
    log(f"\nREFUSED: the plan {tool} --apply works out now is not the one in the plan file you reviewed. "
        f"Nothing was changed.")
    for ln in diff_summary(added, removed):
        log(ln)
    log(f"The plan you reviewed was saved as {prev}; the new plan is in {path}.")
    log(f"Review {path}, then run {tool} --apply again.")


def no_plan_message(path, tool):
    st = state(path)
    why = {"missing": "there is no plan file", "applied": f"the plan is empty / already applied "
           f"({header_of(path)})"}.get(st, "the plan file lists no actions")
    return (f"REFUSED: {why} ({path}). Run {tool} in plan mode first (without --apply), review the plan, "
            f"then --apply. Nothing was changed.")
