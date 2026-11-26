"""tes3diff.py - developer tool (repository only; never deployed): a record-level diff of two plugins, through the
optional tes3conv converter, plus the helpers the golden tests use.

tes3conv (https://github.com/Greatness7/tes3conv, by Greatness7, MIT license; pinned to v0.4.1) converts a Morrowind
plugin (.esp/.esm) to JSON and back. Nothing shipped needs it, and neither does the rest of the test suite: tests that
use it skip when it is not found.

Usage: python tes3diff.py OLD NEW [--tes3conv PATH] [--limit N]
       python tes3diff.py --check [--tes3conv PATH]
       python tes3diff.py -h | --help
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

VERSION = "v0.4.1"
ENV_VAR = "TES3CONV"
OFF_VALUES = ("off", "none", "0", "disabled")      # TES3CONV=off switches the lookup off (to try the skips)
RELEASE_URL = "https://github.com/Greatness7/tes3conv/releases/tag/" + VERSION
# The official v0.4.1 Windows release asset, windows-latest.zip, has this SHA-256 (GitHub's own digest for it) and
# holds tes3conv.exe with the SHA-256 below. tes3conv has no --version switch, so the file's hash is the check.
ASSET_SHA256 = {"windows": "2783e835efdd4e28e9d31d63674c9c036f1332ef948707d581af33e7618a87a9"}
EXE_SHA256 = {"windows": "3c259868c9deca42a658ff6c69cbc8578f8eeee99ebab5342bdb73beef650b40"}
LAG_NOTE = ("tes3conv may lag the tes3 library it is built on: newer record types or fields may not round-trip, so "
            "treat a diff as a view of what the converter understands, not as proof of byte-for-byte equality.")

HELP = r"""tes3diff.py - record-level diff of two Morrowind plugins through tes3conv (developer tool, repository only).

Usage: python tes3diff.py OLD NEW [--tes3conv PATH] [--limit N]
       python tes3diff.py --check [--tes3conv PATH]
       python tes3diff.py -h | --help

Arguments and switches (anything else is refused with exit code 2 and NOTHING is done):
  OLD NEW         the two plugins (.esp/.esm) to compare. Both are only read; nothing is written anywhere.
  --check         look for tes3conv, verify it against the pinned release and report; compares nothing.
  --tes3conv PATH the tes3conv program (or a folder holding it). Default: the TES3CONV environment variable, then
                  PATH, then an untracked dev tools folder: .devtools\tes3conv\ in the repository, or
                  _devtools\tes3conv\ beside it (searched below those folders). TES3CONV=off switches the
                  environment, PATH and dev folder lookup off, as if it were not installed (this switch still wins).
  --limit N       print at most N changed fields per record (default 20; 0 for all).
  -h, --help      print this text and exit. Writes nothing.

Output: one line per record that was added (+), removed (-) or changed (~), with each changed field as
`path: old -> new`; then a summary. Records are matched by type and id (cell by name and grid), not by position, so
a record that only moved is not a difference. The two plugins' headers are compared too.

tes3conv is optional: when it is not found, tes3diff.py says so and exits with code 3. It is pinned to tes3conv v0.4.1
(Greatness7, MIT): the program's SHA-256 is compared with the one from the official release asset and a warning is
printed when it differs. """ + LAG_NOTE + """
Exit codes: 0 no differences, 1 differences found, 2 an unknown switch or missing argument, 3 tes3conv not found or
failed."""


class Tes3convError(Exception):
    """tes3conv could not be run, or refused a file."""


def _platform():
    return "windows" if sys.platform.startswith("win") else sys.platform


def _exe_names():
    return ("tes3conv.exe",) if _platform() == "windows" else ("tes3conv", "tes3conv.exe")


def dev_dirs():
    """The untracked dev tools folders searched last, relative to the repository: .devtools\\tes3conv here, and
    _devtools\\tes3conv beside the repository."""
    return [HERE / ".devtools" / "tes3conv", HERE.parent / "_devtools" / "tes3conv"]


def _pick(base, depth=3):
    """A tes3conv program at base (a file) or below it (a folder, searched a few levels down), newest folder first."""
    base = Path(base)
    if base.is_file():
        return base
    if not base.is_dir():
        return None
    hits = []
    for root, dirs, files in os.walk(str(base)):
        if len(Path(root).relative_to(base).parts) >= depth:
            dirs[:] = []
        for n in files:
            if n.lower() in _exe_names():
                hits.append(Path(root) / n)
    return sorted(hits, reverse=True)[0] if hits else None


def find_tes3conv(explicit=None, environ=None, search_dirs=None, which=None):
    """The tes3conv program, or None: explicit path, then TES3CONV, then PATH, then the dev tools folders."""
    env = os.environ if environ is None else environ
    if explicit:
        hit = _pick(explicit)
        if hit:
            return hit
    if str(env.get(ENV_VAR, "")).strip().lower() in OFF_VALUES:
        return None                                     # TES3CONV=off: pretend it is not installed (tests skip)
    if env.get(ENV_VAR):
        hit = _pick(env[ENV_VAR])
        if hit:
            return hit
    found = (which or shutil.which)("tes3conv")
    if found:
        return Path(found)
    for d in (dev_dirs() if search_dirs is None else search_dirs):
        hit = _pick(d)
        if hit:
            return hit
    return None


def sha256_of(path):
    h = hashlib.sha256()
    with open(str(path), "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify(path):
    """('ok'|'mismatch'|'unpinned', message): the program's SHA-256 against the official v0.4.1 release asset's."""
    want = EXE_SHA256.get(_platform())
    if not want:
        return "unpinned", (f"no SHA-256 is pinned for {_platform()} (pinned: tes3conv {VERSION}, {RELEASE_URL}); "
                            f"{path} was not verified")
    got = sha256_of(path)
    if got == want:
        return "ok", f"tes3conv {VERSION} verified (SHA-256 {got[:12]} matches the official release asset)"
    return "mismatch", (f"{path} is not the pinned tes3conv {VERSION} (SHA-256 {got[:12]}, expected {want[:12]} from "
                        f"{RELEASE_URL}); results may differ")


_warned = set()


def checked(path, warn=None):
    """verify(), printing the warning (once per file) when it is not the pinned program. Returns the status."""
    status, msg = verify(path)
    key = (str(path), status)
    if status != "ok" and key not in _warned:
        _warned.add(key)
        (warn or (lambda m: print("warning: " + m, file=sys.stderr)))(msg)
    return status


def _run(args, data=None):
    try:
        r = subprocess.run([str(a) for a in args], input=data, capture_output=True, check=False, timeout=300)
    except (OSError, subprocess.SubprocessError) as e:
        raise Tes3convError(f"could not run tes3conv: {e}")
    if r.returncode:
        raise Tes3convError("tes3conv failed (exit %d): %s" % (r.returncode, r.stderr.decode("utf-8", "replace").strip()))
    return r.stdout


def to_records(plugin_path, exe):
    """The plugin's records as tes3conv's JSON list (header first). Reads the plugin; writes nothing."""
    return json.loads(_run([exe, "-c", plugin_path]).decode("utf-8"))


def write_plugin(records, out_path, exe):
    """records (a tes3conv JSON list) back to a plugin at out_path (overwritten). The JSON goes in on stdin."""
    _run([exe, "-o", "-", out_path], json.dumps(records).encode("utf-8"))
    return out_path


# ---------------------------------------------------------------- the diff

def record_key(rec, ordinal):
    """What a record is matched by: its type and id (a cell by name and grid, a landscape by grid)."""
    t = rec.get("type", "?")
    for f in ("id", "effect_id", "skill_id"):
        if f in rec:
            return (t, str(rec[f]).lower())
    data = rec.get("data") if isinstance(rec.get("data"), dict) else {}
    grid = rec.get("grid") or data.get("grid")
    if grid:
        return (t, "%s@%s,%s" % (str(rec.get("name", "")).lower(), grid[0], grid[1]))
    if "name" in rec:
        return (t, str(rec["name"]).lower())
    return (t, "#%d" % ordinal)


def index(records):
    """{key: record} with a #n suffix on a repeated key (a record can legitimately repeat)."""
    out, seen = {}, {}
    for i, rec in enumerate(records):
        k = record_key(rec, i)
        seen[k] = seen.get(k, 0) + 1
        out[k if seen[k] == 1 else (k[0], "%s#%d" % (k[1], seen[k]))] = rec
    return out


def _show(v, width=96):
    s = json.dumps(v, ensure_ascii=True, sort_keys=False)
    return s if len(s) <= width else s[:width - 3] + "..."


def field_changes(a, b, path=""):
    """[(path, old, new)] where two JSON values differ; a missing side is shown as <absent>."""
    absent = "<absent>"
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in list(a) + [k for k in b if k not in a]:
            sub = path + "." + k if path else k
            if k not in b:
                out.append((sub, a[k], absent))
            elif k not in a:
                out.append((sub, absent, b[k]))
            else:
                out += field_changes(a[k], b[k], sub)
    elif isinstance(a, list) and isinstance(b, list):
        for i in range(max(len(a), len(b))):
            sub = "%s[%d]" % (path, i)
            if i >= len(b):
                out.append((sub, a[i], absent))
            elif i >= len(a):
                out.append((sub, absent, b[i]))
            else:
                out += field_changes(a[i], b[i], sub)
    elif a != b:
        out.append((path or "<value>", a, b))
    return out


def diff_records(old, new, limit=20):
    """(lines, counts): the normalized record-level diff of two tes3conv JSON lists. counts: added, removed, changed,
    unchanged."""
    a, b = index(old), index(new)
    lines, added, removed, changed, same = [], 0, 0, 0, 0
    for k in sorted(set(a) | set(b)):
        label = "%s %s" % (k[0], k[1])
        if k not in b:
            lines.append("- " + label)
            removed += 1
        elif k not in a:
            lines.append("+ " + label)
            added += 1
        else:
            ch = field_changes(a[k], b[k])
            if not ch:
                same += 1
                continue
            changed += 1
            lines.append("~ " + label)
            for path, o, n in (ch if not limit else ch[:limit]):
                lines.append("    %s: %s -> %s" % (path, _show(o) if o != "<absent>" else o, _show(n) if n != "<absent>" else n))
            if limit and len(ch) > limit:
                lines.append("    ... and %d more field(s)" % (len(ch) - limit))
    return lines, {"added": added, "removed": removed, "changed": changed, "unchanged": same}


def diff_plugins(old_path, new_path, exe, limit=20):
    return diff_records(to_records(old_path, exe), to_records(new_path, exe), limit)


def summary(c):
    return "%d added, %d removed, %d changed, %d unchanged" % (c["added"], c["removed"], c["changed"], c["unchanged"])


# ---------------------------------------------------------------- command line

def parse_args(argv):
    """(plugins, explicit program, limit, check). -h/--help exits 0; anything unknown exits 2, doing nothing."""
    if any(a in ("-h", "--help") for a in argv):
        print(HELP)
        raise SystemExit(0)
    plugins, exe, limit, check, bad, i = [], None, 20, False, [], 0
    while i < len(argv):
        a = argv[i]
        if a == "--check":
            check = True
        elif a == "--tes3conv" and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            exe = argv[i + 1]
            i += 1
        elif a.startswith("--tes3conv=") and a.split("=", 1)[1]:
            exe = a.split("=", 1)[1]
        elif a == "--limit" and i + 1 < len(argv) and argv[i + 1].isdigit():
            limit = int(argv[i + 1])
            i += 1
        elif a.startswith("--limit=") and a.split("=", 1)[1].isdigit():
            limit = int(a.split("=", 1)[1])
        elif a.startswith("-"):
            bad.append(a)
        else:
            plugins.append(a)
        i += 1
    if bad or (check and plugins) or (not check and len(plugins) != 2):
        sys.stderr.write("tes3diff.py: unknown switch or wrong arguments: " + " ".join(bad or plugins or ["(none)"])
                         + "\nNothing was done. Run: python tes3diff.py --help\n")
        raise SystemExit(2)
    return plugins, exe, limit, check


def main(argv=None):
    plugins, explicit, limit, check = parse_args(sys.argv[1:] if argv is None else argv)
    exe = find_tes3conv(explicit)
    if exe is None:
        print("tes3diff.py: tes3conv not found. Set %s, put it on PATH, or unpack the official %s release into "
              ".devtools\\tes3conv\\ (repository) or _devtools\\tes3conv\\ (beside it). It is optional: nothing "
              "shipped needs it. %s" % (ENV_VAR, VERSION, RELEASE_URL), file=sys.stderr)
        return 3
    status = checked(exe)
    if check:
        print("tes3conv: %s\n%s" % (exe, verify(exe)[1]))
        print(LAG_NOTE)
        return 0 if status == "ok" else 1
    try:
        lines, counts = diff_plugins(plugins[0], plugins[1], exe, limit)
    except Tes3convError as e:
        print("tes3diff.py: %s" % e, file=sys.stderr)
        return 3
    print("tes3diff: %s -> %s" % (plugins[0], plugins[1]))
    for ln in lines:
        print(ln)
    print("Summary: " + summary(counts))
    return 1 if (counts["added"] or counts["removed"] or counts["changed"]) else 0


if __name__ == "__main__":
    sys.exit(main())