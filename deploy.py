"""deploy.py - copy the conflict-tools' runtime files and docs from this project to a runtime install.

Usage: python deploy.py [TARGET] [--backups DIR] [--dry-run]
       python deploy.py -h | --help
--help has the details. Credit: dej (dejunai). Python 3.9+, standard library only.
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time

HELP = r"""deploy.py - copy the conflict-tools' runtime files and docs from this project to a runtime install
(usually <Morrowind>\conflict-tools\; any folder works).

Usage: python deploy.py [TARGET] [--backups DIR] [--dry-run]
       python deploy.py -h | --help

  TARGET          the folder to deploy into. It is saved in deploy.ini beside deploy.py (machine-specific, never
                  committed); with no TARGET the saved one is used, and a new TARGET replaces it. With neither,
                  deploy.py stops and changes nothing.
  --backups DIR   where the backup of the files a deploy overwrites goes (saved in deploy.ini too). Default: a
                  _deploy_backups folder beside this project. Never inside TARGET or inside a game install.
  --dry-run       report what a real run would copy, skip and back up, and write nothing at all (not even
                  deploy.ini). Run this first.
  -h, --help      print this text and exit. Writes nothing.
Any other switch is refused with exit code 2 and NOTHING is done.

What ships: the files git tracks that deploy_manifest.txt includes (and does not exclude). Tests, .git and CI
files, deploy.py and its own files, sync.py, tes3diff.py, the dummy stand-in folder, generated records, audits,
backups and personal notes never ship, whatever the
manifest says. Nothing in TARGET is ever deleted; files only TARGET has (records, plans, backups, caches) stay.

Before copying it backs up every file it will overwrite to <backups>\conflict-tools-deploy-<stamp>\ with
SHA256SUMS.txt, NEW_FILES.txt (files the deploy adds) and ROLLBACK.ps1 (relative paths; it restores the old
files, hash-checked, and removes the added ones), checks each backup's hash, copies, then checks the hash of
every copied file.

No-downgrade: a file under "lua tools\" is never put over a newer copy. If TARGET's copy is a version this
project's git history knows and the project has moved past it, it is replaced; if TARGET's copy is a later
committed version than the project's, or content no commit knows (an edit made in TARGET) that is newer than the
project's file, it is skipped with one WARNING line saying what to do, and the rest goes on.

A real run into a Morrowind install (TARGET is, or is inside, a folder holding Morrowind.exe or Data Files)
refuses while Morrowind or MWManager is running (their files may be in use; it never stops them). Any other
TARGET is not a game install, so running programs don't matter there.
Line endings alone are not a change (git may check out CRLF)."""

HERE = os.path.dirname(os.path.abspath(__file__))
INI = os.path.join(HERE, "deploy.ini")
MANIFEST = os.path.join(HERE, "deploy_manifest.txt")
LUA = "lua tools/"
BACKUP_PREFIX = "conflict-tools-deploy-"
# Never shipped, whatever deploy_manifest.txt says (matched case-insensitively against the project path)
NEVER = ("tests/**", "**/tests/**", ".git*", "**/.git*", ".github/**", ".gitlab-ci.yml", ".pytest_cache/**",
         "**/__pycache__/**", "*.pyc", "deploy.py", "deploy.ini", "deploy_manifest.txt", "doc_scan.py", "sync.py", "tes3diff.py", "gather_steam_lua.py",
         "conftest.py", "dummy assets/**", "**/dummy assets/**", "dummy/**", "**/dummy/**", "generated/**", "**/generated/**",
         "*audit*", "**/*audit*", "backups/**", "_backup/**", "_deploy_backups/**", "diag/**", "docs/dev/**", "docs/CHANGES.md", "AGENTS.md",
         "*.prev.txt", "*plan_reviewed.txt", "*plan_enacted.txt", "mwdialog.lock")
BUSY = ("morrowind", "mwmanager")        # process names (start) that mean the game or MWManager is running


class DeployError(Exception):
    pass


# ---------------------------------------------------------------- arguments and deploy.ini

def parse_args(argv):
    """(target or None, backups or None, dry_run). -h/--help prints HELP and exits 0; anything unknown exits 2
    before anything is read or written."""
    if any(a in ("-h", "--help") for a in argv):
        print(HELP)
        raise SystemExit(0)
    target = backups = None
    dry = False
    bad = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--dry-run":
            dry = True
        elif a == "--backups" and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            backups = argv[i + 1]
            i += 1
        elif a.startswith("--backups="):
            backups = a.split("=", 1)[1]
        elif a.startswith("-") or target is not None:
            bad.append(a)
        else:
            target = a
        i += 1
    if bad or backups == "":
        sys.stderr.write("deploy.py: unknown switch or argument: " + " ".join(bad or ["--backups"])
                         + "\nNothing was done. Run: python deploy.py --help\n")
        raise SystemExit(2)
    return target, backups, dry


def read_ini(path=None):
    """{"target", "backups"} saved in deploy.ini ({} when there is none)."""
    out = {}
    try:
        with open(path or INI, encoding="utf-8-sig") as f:
            for ln in f:
                ln = ln.strip()
                if "=" in ln and not ln.startswith(("#", ";", "[")):
                    k, v = ln.split("=", 1)
                    if k.strip() in ("target", "backups") and v.strip():
                        out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def write_ini(values, path=None):
    text = ("# deploy.py's saved paths for this machine (not committed; see .gitignore)\n[deploy]\n"
            + "".join(f"{k} = {values[k]}\n" for k in ("target", "backups") if values.get(k)))
    p = path or INI
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, p)


# ---------------------------------------------------------------- what ships

def _glob_re(pat):
    out, i = "", 0
    while i < len(pat):
        if pat.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pat.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pat[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pat[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pat[i]), i + 1
    return re.compile(out + r"\Z", re.I)


def matches(pat, rel):
    return bool(_glob_re(pat).match(rel))


def read_manifest(path=None):
    """[(kind, glob, target path or None)] from deploy_manifest.txt; DeployError on a line it can't read."""
    rules = []
    with open(path or MANIFEST, encoding="utf-8-sig") as f:
        for n, ln in enumerate(f, 1):
            ln = re.split(r"\s#", ln.rstrip("\r\n"), maxsplit=1)[0].strip()
            if not ln or ln.startswith("#"):
                continue
            kind, _, rest = ln.partition(" ")
            rest = rest.strip()
            dest = None
            if "=>" in rest:
                rest, dest = (x.strip() for x in rest.split("=>", 1))
            if kind not in ("include", "exclude") or not rest or (dest is not None and (kind != "include" or not dest)):
                raise DeployError(f"{path or MANIFEST}:{n}: can't read this rule: {ln}")
            rules.append((kind, rest.replace("\\", "/"), dest.replace("\\", "/") if dest else None))
    return rules


def never(rel):
    return any(matches(p, rel) for p in NEVER)


def ship_list(tracked, rules):
    """[(project path, target path)] of the tracked files the rules ship, sorted; NEVER always wins."""
    out = {}
    for rel in tracked:
        if never(rel) or any(k == "exclude" and matches(g, rel) for k, g, _d in rules):
            continue
        for k, g, d in rules:
            if k == "include" and matches(g, rel):
                out[rel] = d or rel
                break
    dests = {}
    for rel, d in out.items():
        if d.lower() in dests:
            raise DeployError(f"two files would go to {d}: {dests[d.lower()]} and {rel}")
        dests[d.lower()] = rel
    return sorted(out.items(), key=lambda x: x[1].lower())


def tracked_files(project=None):
    project = project or HERE
    try:
        r = subprocess.run(["git", "-C", project, "ls-files", "-z"], capture_output=True, check=False, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        raise DeployError(f"git could not list the project's files ({e}); deploy.py needs a git checkout")
    if r.returncode:
        raise DeployError(f"{project} is not a git checkout (git ls-files failed): deploy.py ships only what git "
                          f"tracks")
    return [p for p in r.stdout.decode("utf-8").split("\0") if p]


# ---------------------------------------------------------------- safety checks

def _inside(path, folder):
    p, f = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(folder))
    return p == f or p.startswith(f.rstrip("\\/") + os.sep)


def game_install(path):
    """The Morrowind install `path` is in (an ancestor, or itself, holding Morrowind.exe or a Data Files folder),
    else None."""
    d = os.path.abspath(path)
    while True:
        if os.path.isfile(os.path.join(d, "Morrowind.exe")) or os.path.isdir(os.path.join(d, "Data Files")):
            return d
        up = os.path.dirname(d)
        if up == d:
            return None
        d = up


def busy():
    """Names of running processes that mean Morrowind or MWManager is open ([] when none, or not Windows)."""
    if os.name != "nt":
        return []
    try:
        r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, check=False, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return []
    names = set()
    for ln in r.stdout.decode("utf-8", "replace").splitlines():
        name = ln.split('","', 1)[0].strip('"')
        if name.lower().startswith(BUSY):
            names.add(name)
    return sorted(names)


# ---------------------------------------------------------------- no-downgrade (lua tools)

def _blob_ids(data):
    out = {hashlib.sha256(data).hexdigest()}
    for d in {data, data.replace(b"\r\n", b"\n")}:
        out.add(hashlib.sha1(b"blob %d\0" % len(d) + d).hexdigest())
    return out


def _git_history(project, rel):
    try:
        r = subprocess.run(["git", "-C", project, "log", "--all", "--format=", "--raw", "--no-abbrev",
                            "--no-renames", "--", rel], capture_output=True, check=False, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return []
    out = []
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        f = line.split()
        if line.startswith(":") and len(f) >= 5:
            for blob in (f[3], f[2]):
                if blob.strip("0") and blob not in out:
                    out.append(blob)
    return out


def downgrade(project, rel, src, dst):
    """Why copying src over dst (a "lua tools\\" file, different content) would put an older version over a
    newer one, or None. Same rule as sync.py and --play (mwdialog_paths.downgrade_reason), with this project's
    git history as the only record: "lineage" when dst is a later commit than src; "mtime" when dst holds
    content no commit knows and is at least as new as src."""
    with open(src, "rb") as f:
        s = f.read()
    with open(dst, "rb") as f:
        d = f.read()
    hist = _git_history(project, rel)
    sid, did = _blob_ids(s), _blob_ids(d)

    def rank(ids):
        hits = [i for i, h in enumerate(hist) if h in ids]
        return min(hits) if hits else None
    rs, rd = rank(sid), rank(did)
    if rd is not None:
        return "lineage" if rs is not None and rs > rd else None
    return "mtime" if os.path.getmtime(dst) >= os.path.getmtime(src) else None


# ---------------------------------------------------------------- the deploy

def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _same(a, b):
    """Same content, line endings aside."""
    if os.path.getsize(a) == os.path.getsize(b) and _sha(a) == _sha(b):
        return True
    with open(a, "rb") as f:
        x = f.read()
    with open(b, "rb") as f:
        y = f.read()
    return x.replace(b"\r\n", b"\n") == y.replace(b"\r\n", b"\n")


def plan(project, target, files):
    """{"new": [...], "update": [...], "same": [...], "skip": [(dest, why)]} over [(project path, target path)]."""
    out = {"new": [], "update": [], "same": [], "skip": []}
    for rel, dest in files:
        src = os.path.join(project, *rel.split("/"))
        dst = os.path.join(target, *dest.split("/"))
        if not os.path.isfile(src):
            raise DeployError(f"{rel} is tracked but missing from the project folder")
        if not os.path.isfile(dst):
            out["new"].append((rel, dest))
        elif _same(src, dst):
            out["same"].append((rel, dest))
        elif rel.lower().startswith(LUA) and downgrade(project, rel, src, dst):
            out["skip"].append((dest, downgrade(project, rel, src, dst)))
        else:
            out["update"].append((rel, dest))
    return out


ROLLBACK = r"""# Rollback of one deploy.py run: restores the files it overwrote (hash-checked) and removes the files it added.
# Run: powershell -NoProfile -ExecutionPolicy Bypass -File .\ROLLBACK.ps1   (close Morrowind and MWManager first)
$ErrorActionPreference = "Stop"
$BackupRoot = $PSScriptRoot
$DestRoot = (Resolve-Path (Join-Path $BackupRoot "@REL@")).Path
Get-Content -LiteralPath (Join-Path $BackupRoot "SHA256SUMS.txt") | ForEach-Object {
    $line = $_.Trim()
    if (-not $line) { return }
    $hash, $rel = $line -split '  ', 2
    if (-not $rel.StartsWith("@NAME@/")) { throw "unexpected path in SHA256SUMS: $rel" }
    $inside = $rel.Substring("@NAME@/".Length)
    $src = Join-Path $BackupRoot ($rel -replace "/", "\")
    if ((Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash.ToLower() -ne $hash.ToLower()) { throw "backup hash mismatch: $rel" }
    $dst = Join-Path $DestRoot ($inside -replace "/", "\")
    New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
    Copy-Item -LiteralPath $src -Destination $dst -Force
    if ((Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash.ToLower() -ne $hash.ToLower()) { throw "rollback hash mismatch: $inside" }
}
Get-Content -LiteralPath (Join-Path $BackupRoot "NEW_FILES.txt") | ForEach-Object {
    $rel = $_.Trim()
    if (-not $rel) { return }
    $dst = Join-Path $DestRoot ($rel -replace "/", "\")
    if (Test-Path -LiteralPath $dst) { Remove-Item -LiteralPath $dst -Force }
}
Write-Host "Rollback complete to $DestRoot"
"""


def backup(target, backups, todo, stamp=None):
    """Back up the files `todo` will overwrite (and list the ones it adds) in a new folder under `backups`;
    every copy is hash-checked. Returns the folder."""
    name = os.path.basename(os.path.normpath(target)) or "target"
    folder = os.path.join(backups, BACKUP_PREFIX + (stamp or time.strftime("%Y%m%d-%H%M%S")))
    n = 1
    base = folder
    while os.path.exists(folder):
        n += 1
        folder = f"{base}-{n}"
    os.makedirs(folder)
    sums = []
    for _rel, dest in todo["update"]:
        src = os.path.join(target, *dest.split("/"))
        keep = os.path.join(folder, name, *dest.split("/"))
        os.makedirs(os.path.dirname(keep), exist_ok=True)
        shutil.copy2(src, keep)
        digest = _sha(src)
        if _sha(keep) != digest:
            raise DeployError(f"the backup of {dest} did not hash-check; nothing was deployed")
        sums.append(f"{digest}  {name}/{dest}")
    try:
        rel = os.path.relpath(os.path.abspath(target), folder)
    except ValueError:                                 # another drive: Windows has no relative path there
        rel = os.path.abspath(target)
        print(f"WARNING: the backups are on another drive than {target}, so ROLLBACK.ps1 names it in full")
    with open(os.path.join(folder, "SHA256SUMS.txt"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write("".join(s + "\n" for s in sums))
    with open(os.path.join(folder, "NEW_FILES.txt"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write("".join(dest + "\n" for _r, dest in todo["new"]))
    with open(os.path.join(folder, "ROLLBACK.ps1"), "w", encoding="ascii", newline="\r\n") as f:
        f.write(ROLLBACK.replace("@REL@", rel).replace("@NAME@", name))
    return folder


def copy_all(project, target, todo):
    """Copy every new and changed file (through a temp file, so a file in use is never half written), then check
    each copy's hash against the project's file. Returns the problems ([] when all is well)."""
    bad = []
    for rel, dest in todo["new"] + todo["update"]:
        src = os.path.join(project, *rel.split("/"))
        dst = os.path.join(target, *dest.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        tmp = dst + ".deploytmp"
        shutil.copyfile(src, tmp)
        shutil.copystat(src, tmp)
        os.replace(tmp, dst)
    for rel, dest in todo["new"] + todo["update"]:
        if _sha(os.path.join(project, *rel.split("/"))) != _sha(os.path.join(target, *dest.split("/"))):
            bad.append(dest)
    return bad


def show(title, items, limit=60):
    print(f"{title}: {len(items)}")
    for x in items[:limit]:
        print("   ", x)
    if len(items) > limit:
        print(f"    ... and {len(items) - limit} more")


def main(argv=None, project=None, ini=None, probe=None):
    """probe: what lists the running game/MWManager processes (default busy); asked only when the target is in
    a Morrowind install."""
    target_arg, backups_arg, dry = parse_args(sys.argv[1:] if argv is None else argv)
    project = os.path.abspath(project or HERE)
    ini = ini or INI
    saved = read_ini(ini)
    target = target_arg or saved.get("target")
    if not target:
        print("deploy.py: no target folder given and none saved in deploy.ini. Nothing was done.\n"
              "Run: python deploy.py <target folder>   (it is saved for next time; --help has the details)")
        return 2
    target = os.path.abspath(target)
    backups = os.path.abspath(backups_arg or saved.get("backups")
                              or os.path.join(os.path.dirname(project), "_deploy_backups"))
    try:
        if _inside(target, project) or _inside(project, target):
            raise DeployError(f"the target {target} and the project {project} must not contain each other")
        game = game_install(target)
        if _inside(backups, target) or (game and _inside(backups, game)):
            raise DeployError(f"the backups folder {backups} is inside the target or its game install; pass "
                              f"--backups with a folder outside it")
        files = ship_list(tracked_files(project), read_manifest(os.path.join(project, "deploy_manifest.txt")))
        if not files:
            raise DeployError("deploy_manifest.txt ships nothing")
        if os.path.exists(target) and not os.path.isdir(target):
            raise DeployError(f"{target} is not a folder")
        todo = plan(project, target, files) if os.path.isdir(target) else \
            {"new": list(files), "update": [], "same": [], "skip": []}
    except (DeployError, OSError) as e:
        print(f"deploy.py: {e}. Nothing was done.", file=sys.stderr)
        return 1
    print(f"deploy.py{' --dry-run (nothing is written)' if dry else ''}: {project} -> {target}")
    print(f"  {len(files)} file(s) ship by deploy_manifest.txt; backups go under {backups}")
    show("new", [d for _r, d in todo["new"]])
    show("updated", [d for _r, d in todo["update"]])
    print(f"unchanged: {len(todo['same'])}")
    for dest, why in todo["skip"]:
        how = ("the target has a later committed version than the project's" if why == "lineage"
               else "the target's copy was changed there, after the project's")
        print(f"WARNING: kept {dest}: newer than the project's copy ({how}); carry it into the project (or delete "
              f"it from the target) and deploy again")
    if dry:
        if target_arg and target_arg != saved.get("target"):
            print(f"(--dry-run: {target} would be saved in {ini})")
        return 0
    running = (probe or busy)() if game else []      # only a game install's files can be in use by them
    if running:
        print(f"deploy.py: {', '.join(running)} is running; close it first (deploy.py never stops it). Nothing was "
              f"done.", file=sys.stderr)
        return 1
    if target_arg or backups_arg:
        write_ini({"target": target, "backups": backups_arg and backups or saved.get("backups")}, ini)
    if not (todo["new"] or todo["update"]):
        print("Nothing to copy: the target is up to date.")
        return 0
    try:
        os.makedirs(target, exist_ok=True)
        folder = backup(target, backups, todo)
        bad = copy_all(project, target, todo)
    except (DeployError, OSError) as e:
        print(f"deploy.py: {e}", file=sys.stderr)
        return 1
    print(f"Backup: {folder} ({len(todo['update'])} file(s) kept, {len(todo['new'])} new listed; ROLLBACK.ps1 undoes "
          f"this deploy)")
    if bad:
        show("ERROR: these copies do not match the project's files (hash check)", bad)
        return 1
    print(f"Copied {len(todo['new']) + len(todo['update'])} file(s); every copy hash-checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
