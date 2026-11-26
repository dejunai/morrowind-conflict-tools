"""sync.py - carry the tools from this repository into MWManager, one way: repository -> MWManager.

Developer tool (repository only; never deployed). It never opens, reads or writes the Morrowind install: deploy.py is
the only tool that writes there. It takes nothing back from MWManager either: the repository is the source and the
files here are never changed by it.

  Source: the repository's WORKING TREE (the files git tracks, as they are on disk), not HEAD, so a change can be
  tried in MWManager before it is committed. Tracked files with uncommitted changes are listed in a WARNING, and
  MWManager's UPSTREAM.json names HEAD: commit, then run sync.py again (the second run copies nothing).
  Destination: tools\\steam-upstream\\ (the entries in COPY_MANIFEST.json), MWManager's root copies of the upstream
  modules (byte-identical to steam-upstream), reference\\mwse-lua-guards\\ (the mw* suite, SOURCE_MANIFEST.json)
  and reference\\mwmanager-menu\\. Sizes and hashes in both manifests follow the copied bytes. The repository's tests
  (tests\\, fixtures included) and suite Lua (lua tools\\MWSE\\mods\\mwsuite\\) go along always: a new one is added to
  COPY_MANIFEST.json, since the vendored tests run them. Other repository files neither manifest lists are
  reported, not added: adding one to MWManager is a decision.

Never puts an older version of a "lua tools\\" file over a newer one: the file is skipped with one WARNING line
saying what to do, and the rest goes on. Hash lineage decides (mwdialog_paths.downgrade_reason): MWManager's git
log already has the source's content and MWManager has moved past it; modification times only for content no
commit knows (an uncommitted edit). MWManager's file is read only to compare it; nothing flows back.

A mod that is gone from the repository (retired) is removed from MWManager too: its files leave tools\\steam-upstream\\
and reference\\mwse-lua-guards\\ and their manifest entries are dropped, after a backup to
<MWManager's parent>\\_deploy_backups\\mwmanager-retired-<stamp> (SHA256SUMS.txt + a relative ROLLBACK.ps1), with one
RETIRED line per mod. A file changed since the last sync is kept with a WARNING.

Commits and pushes nothing. The MWManager folder is given once and saved in sync.ini beside this script (this
machine's path; not committed).
Usage: python sync.py [MWMANAGER] [--dry-run] | -h | --help   (any other switch is refused; --help has the details)
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HELP = r"""sync.py - carry the conflict-tools from this repository into MWManager (one way: repository -> MWManager).

Usage: python sync.py [MWMANAGER] [--dry-run]
       python sync.py -h | --help

Arguments and switches (these are all of them; anything else is refused with exit code 2 and NOTHING is synced):
  MWMANAGER     the MWManager folder to sync into. Saved in sync.ini beside sync.py (machine-specific, never
                committed); with none given the saved one is used. Refused when it is, or is inside, a Morrowind
                install (a folder holding Morrowind.exe or Data Files).
  -h, --help    print this text and exit. Writes nothing.
  --dry-run     report everything a real run would do (copies, retirements, manifest and UPSTREAM.json changes)
                and write nothing at all (not even sync.ini). Run this first.
With no switch it does a REAL sync: it writes files in MWManager (and nothing in this repository).

What it does:
  It never opens, reads or writes the Morrowind install: deploy.py is the only tool that writes there. It never
  changes this repository and takes nothing back from MWManager.
  Source        the repository's working tree: the files git tracks, as they are on disk. Tracked files with
                uncommitted changes are listed in a WARNING.
  Destination   tools\steam-upstream\ (the entries in COPY_MANIFEST.json), MWManager's root copies of the upstream
                modules, reference\mwse-lua-guards\ (the mw* suite named in mwguard's exemptMods,
                SOURCE_MANIFEST.json) and reference\mwmanager-menu\. Sizes and hashes in both manifests follow the
                copied bytes.
    - the repository's tests\ (fixtures included) and the suite Lua (lua tools\MWSE\mods\mwsuite\) always go
      along; a new one is added to COPY_MANIFEST.json. reference\mwmanager-menu\ follows its twins in "lua tools".
    - other repository files neither manifest lists are only reported ("repository files no manifest lists"):
      adding one to MWManager is a decision, so add it by hand.
    - UPSTREAM.json is stamped with the repository's HEAD commit. If tracked files have uncommitted changes, the
      run says so: commit, then run sync.py again so UPSTREAM.json names that commit (the second run copies
      nothing).

Never carried: anything inside a "dummy", "dummy assets" or "generated" folder (the stand-in files are made in code or
copied out of Morrowind.bsa at run time, into <tools>\generated\dummy\). Such a path is skipped, and a manifest entry
for one is dropped (the file in MWManager is left alone).

Checks it makes along the way:
  No-downgrade  a "lua tools" file is never replaced by an older one. Hash lineage decides: if MWManager's git
                history already contains the source's content and MWManager has moved past it, the file is skipped
                with one WARNING line saying what to do and the rest goes on. Modification times are used only for
                content no commit knows (an uncommitted edit). MWManager's file is read only to compare.
  Retire        a mod that is gone from the repository is removed from MWManager too: its files leave
                tools\steam-upstream\ and reference\mwse-lua-guards\ and its manifest entries are dropped, after a
                backup to <MWManager's parent>\_deploy_backups\mwmanager-retired-<stamp> (SHA256SUMS.txt plus a
                relative ROLLBACK.ps1). One RETIRED line per mod; a file changed since the last sync is kept with a
                WARNING. With --dry-run these show as WOULD RETIRE.

Before a real run, back up the MWManager files it will change (and UPSTREAM.json, COPY_MANIFEST.json,
SOURCE_MANIFEST.json) yourself; only retirements are backed up automatically. Close Morrowind and MWManager first.
sync.py commits and pushes nothing: review with git status in both repos, and commit MWManager through its own bot.
Exit codes: 0 done, 1 refused or failed, 2 an unknown switch."""

HERE = Path(__file__).resolve().parent
INI = HERE / "sync.ini"
sys.path.insert(0, str(HERE))
import mwdialog_paths as MP  # noqa: E402  (beside this script, in the repository)

REPO = HERE                                         # the source: this repository's working tree
MWM = UP = REF = None                               # the destination, set by configure()
SUITE = "lua tools/MWSE/mods/mwsuite/"
AUTO = ("tests/", SUITE)                            # the vendored tests and the suite they test: always copied
# MWManager keeps its own snapshot of these (COPY_MANIFEST "Excluded": user-state records)
MWM_KEEPS = {"lua tools/MWSE/config/mwguard.json"}
DRY = False
LUA = "lua tools/"
SKIPPED = []                                        # (destination, why): left alone, newer than the source
BACKUP = {}                                         # the one backup folder this run uses for retired files
META_END = "-metadata.toml"


def configure(repo, mwmanager, dry=False):
    """Set the one source (the repository) and the one destination (MWManager) for this run."""
    global REPO, MWM, UP, REF, DRY
    REPO, MWM, DRY = Path(repo), Path(mwmanager), bool(dry)
    UP = MWM / "tools" / "steam-upstream"
    REF = MWM / "reference" / "mwse-lua-guards"
    SKIPPED.clear()
    BACKUP.clear()


def git(repo, *args, stdin=None):
    r = subprocess.run(["git", "-C", str(repo), *args], input=stdin, capture_output=True, check=False)
    if r.returncode not in (0, 1):                     # check-ignore answers 1 for "nothing ignored"
        raise SystemExit(f"git {' '.join(args)} failed in {repo}: {r.stderr.decode(errors='replace').strip()}")
    return [p for p in r.stdout.decode("utf-8").split("\0") if p]


def copy(src, dst):
    """Copy src over dst when the content differs. True if it changed (or would, with --dry-run). A line-ending
    difference alone is not a change: the repository checks out CRLF, MWManager LF."""
    data = src.read_bytes()
    if dst.is_file() and dst.read_bytes().replace(b"\r\n", b"\n") == data.replace(b"\r\n", b"\n"):
        return False
    if not DRY:
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".synctmp")
        tmp.write_bytes(data)
        os.replace(tmp, dst)
    return True


def guarded(src, dst, rel, repo, repo_rel, src_repo=None, names=("the repo", "MWManager")):
    """copy(), except a lua tools file is never put over a newer version (one WARNING line, then skipped)."""
    if rel.startswith(LUA) and dst.is_file():
        s, d = src.read_bytes(), dst.read_bytes()
        if s.replace(b"\r\n", b"\n") != d.replace(b"\r\n", b"\n"):
            why = MP.downgrade_reason(MP.git_blob_ids(s), MP.git_blob_ids(d), MP.git_path_history(repo, repo_rel),
                                      src.stat().st_mtime, dst.stat().st_mtime,
                                      MP.git_path_history(src_repo, rel) if src_repo else ())
            if why:
                how = (f"{names[0]}'s copy is a version {names[1]} already had" if why == "lineage"
                       else f"{names[1]}'s copy was changed outside sync.py, after {names[0]}'s")
                SKIPPED.append((repo_rel, why))
                print(f"WARNING: skipped {repo_rel} in {names[1]}: newer than {names[0]}'s ({how}); put the newer "
                      f"one in the repo's lua tools (or revert {names[1]}'s), then run sync.py again")
                return False
    return copy(src, dst)


def is_dummy(rel):
    """A path inside a stand-in ("dummy" or "dummy assets") or generated-records folder. Stand-ins are made in code or
    copied out of Morrowind.bsa at run time, so these are never carried to MWManager and never listed in a manifest."""
    return any(p in ("dummy", "dummy assets", "generated") for p in rel.replace("\\", "/").lower().split("/")[:-1])


def is_metadata(rel):
    """A mod's MWSE metadata toml, directly under lua tools/."""
    return rel.startswith(LUA) and "/" not in rel[len(LUA):] and rel.endswith(META_END)


def mod_label(rel):
    """The mod a retired lua tools file belonged to (the report has one line per mod); other files name themselves."""
    if rel.startswith(SUITE):
        return rel[len(SUITE):].split("/", 1)[0]
    return rel[len(LUA):-len(META_END)] if is_metadata(rel) else rel


def unchanged(path, sha):
    """path still holds the bytes its manifest entry recorded (a line-ending difference alone does not count)."""
    data = path.read_bytes()
    lf = data.replace(b"\r\n", b"\n")
    return sha.lower() in {hashlib.sha256(b).hexdigest() for b in (data, lf, lf.replace(b"\n", b"\r\n"))}


ROLLBACK = r"""# Rollback the sync.py run that produced this backup (files it retired from MWManager).
# Restores them from this folder. Run from anywhere:  powershell -NoProfile -File ROLLBACK.ps1
$ErrorActionPreference = "Stop"
$BackupRoot = $PSScriptRoot
$DestRoot = (Resolve-Path (Join-Path $BackupRoot "..\..\@NAME@")).Path
$Sums = Join-Path $BackupRoot "SHA256SUMS.txt"

Get-Content -LiteralPath $Sums | ForEach-Object {
    $line = $_.Trim()
    if (-not $line) { return }
    $hash, $rel = $line -split '  ', 2
    if (-not $rel.StartsWith("@NAME@/")) { throw "unexpected path in SHA256SUMS: $rel" }
    $relInside = $rel.Substring("@NAME@/".Length)
    $src = Join-Path $BackupRoot ($rel -replace "/", "\")
    $dst = Join-Path $DestRoot ($relInside -replace "/", "\")
    New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
    Copy-Item -LiteralPath $src -Destination $dst -Force
    $got = (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash.ToLower()
    if ($got -ne $hash.ToLower()) { throw "rollback hash mismatch: $relInside" }
}
Write-Host "Rollback complete to $DestRoot"
"""


def backup_file(path):
    """Copy a MWManager file into this run's backup folder (made on first use) and check the copy's hash."""
    if "dir" not in BACKUP:
        BACKUP["dir"] = MWM.parent / "_deploy_backups" / ("mwmanager-retired-" + time.strftime("%Y%m%d-%H%M%S"))
        BACKUP["dir"].mkdir(parents=True, exist_ok=True)
        (BACKUP["dir"] / "ROLLBACK.ps1").write_bytes(
            ROLLBACK.replace("@NAME@", MWM.name).replace("\n", "\r\n").encode("ascii"))
        (BACKUP["dir"] / "NEW_FILES.txt").write_bytes(b"")
        (BACKUP["dir"] / "SHA256SUMS.txt").write_bytes(b"")
    rel = path.relative_to(MWM).as_posix()
    keep = BACKUP["dir"] / MWM.name / rel
    keep.parent.mkdir(parents=True, exist_ok=True)
    data = path.read_bytes()
    keep.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    if hashlib.sha256(keep.read_bytes()).hexdigest() != digest:
        raise SystemExit(f"backup of {path} did not hash-check; nothing was removed")
    with open(BACKUP["dir"] / "SHA256SUMS.txt", "ab") as f:
        f.write(f"{digest}  {MWM.name}/{rel}\r\n".encode("utf-8"))


def retire(gone, root, where):
    """Remove vendored files whose source left the repo: gone is [(manifest key, repo rel, MWManager path,
    recorded SHA-256)].
    Backs each up first; one RETIRED line per mod. Returns the keys whose manifest entries should be dropped
    (a file changed since the last sync is kept, with a WARNING). --dry-run only reports."""
    done, by_mod = set(), {}
    for key, rel, dst, sha in gone:
        by_mod.setdefault(mod_label(rel), []).append((key, dst, sha))
    for label, files in by_mod.items():
        n = 0
        for key, dst, sha in files:
            if dst.is_file() and not unchanged(dst, sha):
                print(f"WARNING: kept {where}/{key} in MWManager: it is gone from the repo but was changed after "
                      f"the last sync; remove it by hand if the mod is retired")
                continue
            done.add(key)
            if not dst.is_file():
                continue
            n += 1
            if not DRY:
                backup_file(dst)
                dst.unlink()
                for parent in dst.parents:                  # empty folders go with the last file
                    if parent == root or any(parent.iterdir()):
                        break
                    parent.rmdir()
        if n:
            print(f"{'WOULD RETIRE' if DRY else 'RETIRED'} {label} ({where}): gone from the repo; "
                  f"{'would remove' if DRY else 'removed'} {n} file(s)"
                  + ("" if DRY else f", backup {BACKUP['dir']}"))
    return done


def suite_mods():
    """The mods the reference snapshot mirrors: the names in mwguard's exemptMods that the repo has a folder for."""
    main = REPO / SUITE / "mwguard" / "main.lua"
    if not main.is_file():
        return set()
    text = main.read_text("utf-8-sig")
    block = text[text.index("exemptMods"):]
    return {n for n in re.findall(r'"([^"]+)"', block[:block.index("}")]) if (REPO / SUITE / n / "main.lua").is_file()}


def load_manifest(path):
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    eol = "\r\n" if "\r\n" in text else "\n"
    data = json.loads(text)
    again = json.dumps(data, indent=2, ensure_ascii=False).replace("\n", eol)
    if again != text.rstrip("\r\n"):
        raise SystemExit(f"{path}: not in the json.dumps(indent=2) layout this script rewrites; update it by hand")
    return data, (raw.startswith(b"\xef\xbb\xbf"), eol, text.endswith(("\n", "\r\n")))


def save_manifest(path, data, fmt):
    bom, eol, final = fmt
    out = json.dumps(data, indent=2, ensure_ascii=False).replace("\n", eol) + (eol if final else "")
    if not DRY:
        path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + out.encode("utf-8"))


# The "Source" label in a manifest entry records where MWManager first got the file (the Steam install). It is
# text only: nothing here reads that place.


def refresh(entry, src, size_key):
    """A copied file's manifest entry follows its new bytes; untouched entries keep their fingerprints."""
    data = src.read_bytes()
    entry[size_key], entry["SHA256"] = len(data), hashlib.sha256(data).hexdigest()
    if "SourceModified" in entry:
        entry["SourceModified"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(src.stat().st_mtime))




def to_mwmanager():
    changed, unlisted = [], []
    listed = set()
    man_path = UP / "COPY_MANIFEST.json"
    man, fmt = load_manifest(man_path)
    carried = [e["RelativePath"] for e in man["Files"] if is_dummy(e["RelativePath"].replace("\\", "/"))]
    if carried:                                         # a dummy folder is never carried: its entries go (files stay)
        man["Files"] = [e for e in man["Files"] if e["RelativePath"] not in carried]
        for r in carried:
            print(f"DROPPED {r} from COPY_MANIFEST.json: the dummy folder is never carried (the file on disk is left alone)")
        changed += ["COPY_MANIFEST.json: dropped %d dummy entr%s" % (len(carried), "y" if len(carried) == 1 else "ies")]
    ok = (REPO / LUA).is_dir()                         # a checkout without lua tools\\ retires nothing
    gone = []
    for e in man["Files"]:
        rel = e["RelativePath"].replace("\\", "/")
        listed.add(rel)
        src = REPO / rel
        if rel in MWM_KEEPS:
            continue
        if not src.is_file():
            if ok and rel.startswith((LUA, "tests/")):       # retired in the repo: it leaves MWManager too
                gone.append((rel, rel, UP / rel, e["SHA256"]))
            continue
        if guarded(src, UP / rel, rel, MWM, "tools/steam-upstream/" + rel, REPO, ("the repo", "MWManager")):
            changed.append("tools/steam-upstream/" + rel)
            refresh(e, src, "Bytes")
    dropped = retire(gone, UP, "tools/steam-upstream")
    if dropped:
        man["Files"] = [e for e in man["Files"] if e["RelativePath"].replace("\\", "/") not in dropped]
        changed += ["tools/steam-upstream/" + r + " (retired)" for r in sorted(dropped)]
    for rel in git(REPO, "ls-files", "-z"):
        if is_dummy(rel):
            continue
        if (rel.startswith(AUTO) or is_metadata(rel)) and rel not in listed and rel not in MWM_KEEPS and (REPO / rel).is_file():
            listed.add(rel)
            guarded(REPO / rel, UP / rel, rel, MWM, "tools/steam-upstream/" + rel, REPO, ("the repo", "MWManager"))
            if any(k == "tools/steam-upstream/" + rel for k, _ in SKIPPED):
                continue                                    # newer in MWManager: not listed with the repo's bytes
            win = rel.replace("/", "\\")
            e = {"RelativePath": win, "Source": "<Steam Morrowind>\\" + win, "Bytes": 0, "SHA256": "",
                 "SourceModified": ""}
            man["Files"].append(e)
            copy(REPO / rel, UP / rel)
            changed.append("tools/steam-upstream/" + rel)
            refresh(e, REPO / rel, "Bytes")
    for root_copy in [*MWM.glob("mwdialog_*.py"), MWM / "vortex_tidy.py"]:  # MWManager runs these: same bytes
        vend = UP / root_copy.name
        src = REPO / root_copy.name if DRY and (REPO / root_copy.name).is_file() else vend
        if vend.is_file() and copy(src, root_copy):
            changed.append(root_copy.name)

    ref_path = REF / "SOURCE_MANIFEST.json"
    ref, rfmt = load_manifest(ref_path)
    seen = [e["Path"] for e in ref["Files"] if is_dummy(e["Path"])]
    if seen:
        ref["Files"] = [e for e in ref["Files"] if e["Path"] not in seen]
        changed += ["SOURCE_MANIFEST.json: dropped %d dummy entr%s" % (len(seen), "y" if len(seen) == 1 else "ies")]
    gone, have = [], set()
    for e in ref["Files"]:
        kind, rest = e["Path"].split("/", 1)
        rel = SUITE + rest if kind == "mods" else "lua tools/" + rest
        listed.add(rel)
        have.add(rel)
        src = REPO / rel
        if not src.is_file():
            if ok:                                          # retired in the repo
                gone.append((e["Path"], rel, REF / e["Path"], e["SHA256"]))
            continue
        if guarded(src, REF / e["Path"], rel, MWM, "reference/mwse-lua-guards/" + e["Path"], REPO,
                   ("the repo", "MWManager")):
            changed.append("reference/mwse-lua-guards/" + e["Path"])
            refresh(e, src, "Length")
    menu = REF.parent / "mwmanager-menu"                    # the unified menu's files that have a twin in lua tools\\
    for mine, rel in (("mods/mwmanagermenu/main.lua", SUITE + "mwmanagermenu/main.lua"),
                      ("metadata/mwmanagermenu-metadata.toml", LUA + "mwmanagermenu-metadata.toml"),
                      ("metadata/mwsuite-metadata.toml", LUA + "mwsuite-metadata.toml")):
        if (REPO / rel).is_file() and (menu / mine).is_file() and guarded(
                REPO / rel, menu / mine, rel, MWM, "reference/mwmanager-menu/" + mine, REPO,
                ("the repo", "MWManager")):
            changed.append("reference/mwmanager-menu/" + mine)
    dropped = retire(gone, REF, "reference/mwse-lua-guards")
    if dropped:
        ref["Files"] = [e for e in ref["Files"] if e["Path"] not in dropped]
        changed += ["reference/mwse-lua-guards/" + p + " (retired)" for p in sorted(dropped)]

    mods = suite_mods()                                     # new suite mods and files join the snapshot
    for rel in git(REPO, "ls-files", "-z"):
        if is_dummy(rel):
            continue
        if rel.startswith(SUITE):
            rest = rel[len(SUITE):]
            mine = "/" in rest and rest.split("/", 1)[0] in mods
            path, source = "mods/" + rest, "Data Files\\MWSE\\mods\\mwsuite\\" + rest.replace("/", "\\")
        else:
            mine = is_metadata(rel) and rel[len(LUA):-len(META_END)] in mods
            path, source = "metadata/" + rel[len(LUA):], "Data Files\\" + rel[len(LUA):]
        if not mine or rel in have or not (REPO / rel).is_file():
            continue
        listed.add(rel)
        e = {"Path": path, "Source": "<Steam Morrowind>\\" + source, "SHA256": "", "Length": 0, "SourceModified": ""}
        ref["Files"].append(e)
        copy(REPO / rel, REF / path)
        changed.append("reference/mwse-lua-guards/" + path)
        refresh(e, REPO / rel, "Length")

    for rel in git(REPO, "ls-files", "-z"):
        if rel not in listed and (rel.startswith(SUITE) or ("/" not in rel and rel.endswith(".py"))):
            unlisted.append(rel)
    if changed:
        man["SyncedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        ref["CopiedAt"] = time.strftime("%Y-%m-%d") + " (sync.py)"
    save_manifest(man_path, man, fmt)
    save_manifest(ref_path, ref, rfmt)
    return changed, unlisted


def stamp_upstream():
    """UPSTREAM.json names the repo commit MWManager's copy came from. Returns (commit, subject, dirty tracked files)."""
    def out(*args):
        r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, check=False)
        if r.returncode:
            raise SystemExit(f"git {' '.join(args)} failed in {REPO}: {r.stderr.decode(errors='replace').strip()}")
        return r.stdout.decode("utf-8", "replace").strip()
    commit, subject = out("rev-parse", "--short=7", "HEAD"), out("log", "-1", "--format=%s")
    dirty = [ln[3:] for ln in out("status", "--porcelain", "--untracked-files=no").split("\n") if ln.strip()]
    path = MWM / "UPSTREAM.json"
    data, fmt = load_manifest(path)
    if (data.get("commit"), data.get("commit_subject")) != (commit, subject):
        data["commit"], data["commit_subject"] = commit, subject
        save_manifest(path, data, fmt)
    return commit, subject, dirty


def show(title, items):
    print(f"{title}: {len(items)}")
    for x in items[:40]:
        print("   ", x)
    if len(items) > 40:
        print(f"    ... and {len(items) - 40} more")


# ---------------------------------------------------------------- arguments, sync.ini, the run

def _check_args(argv):
    """(MWManager folder or None, dry run). -h/--help prints HELP and exits 0; an unknown switch or argument exits 2
    before anything is read or written (a real sync is the default, so a guessed switch must never fall through
    to one)."""
    if any(a in ("-h", "--help") for a in argv):
        print(HELP)
        raise SystemExit(0)
    target, dry, bad = None, False, []
    for a in argv:
        if a == "--dry-run":
            dry = True
        elif a.startswith("-") or target is not None:
            bad.append(a)
        else:
            target = a
    if bad:
        sys.stderr.write("sync.py: unknown switch or argument: " + " ".join(bad)
                         + "\nNothing was synced. Run: python sync.py --help\n")
        raise SystemExit(2)
    return target, dry


def read_ini(path=None):
    """The MWManager folder saved in sync.ini ("" when there is none)."""
    try:
        with open(path or INI, encoding="utf-8-sig") as f:
            for ln in f:
                ln = ln.strip()
                if "=" in ln and not ln.startswith(("#", ";", "[")):
                    k, v = ln.split("=", 1)
                    if k.strip() == "mwmanager" and v.strip():
                        return v.strip()
    except OSError:
        pass
    return ""


def write_ini(mwmanager, path=None):
    p = str(path or INI)
    with open(p + ".tmp", "w", encoding="utf-8", newline="\n") as f:
        f.write("# sync.py's saved MWManager folder for this machine (not committed; see .gitignore)\n"
                "[sync]\nmwmanager = %s\n" % mwmanager)
    os.replace(p + ".tmp", p)


def game_install(path):
    """The Morrowind install `path` is in (itself or an ancestor holding Morrowind.exe or a Data Files folder), or
    None. Only the existence of those two names is looked at, in MWManager's own ancestors."""
    d = os.path.abspath(str(path))
    while True:
        if os.path.isfile(os.path.join(d, "Morrowind.exe")) or os.path.isdir(os.path.join(d, "Data Files")):
            return d
        up = os.path.dirname(d)
        if up == d:
            return None
        d = up


def git_status_tracked():
    r = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--untracked-files=no"],
                       capture_output=True, check=False)
    return [ln[3:] for ln in r.stdout.decode("utf-8", "replace").split("\n") if ln.strip()] if r.returncode == 0 else []


def run(repo, mwmanager, dry=False):
    """One sync, repository -> MWManager. Returns 0, or 1 when it was refused. Prints the report."""
    configure(repo, mwmanager, dry)
    for p in (REPO / ".git", UP / "COPY_MANIFEST.json", REF / "SOURCE_MANIFEST.json"):
        if not p.exists():
            print(f"not found: {p}", file=sys.stderr)
            return 1
    print("sync.py" + (" --dry-run (nothing is written)" if DRY else ""))
    dirty_now = git_status_tracked()
    if dirty_now:
        show("WARNING: tracked files with uncommitted changes (the working tree is what is copied; commit them, "
             "then run sync.py again so UPSTREAM.json names that commit)", dirty_now)
    mw_changed, unlisted = to_mwmanager()
    show("MWManager: updated", mw_changed)
    show("MWManager: repository files no manifest lists (not copied; add them by hand if MWManager should run them)",
         unlisted)
    commit, subject, _dirty = stamp_upstream()
    print(f"MWManager UPSTREAM.json: {commit} {subject}" + (" (--dry-run: not written)" if DRY else ""))
    if SKIPPED:
        print(f"{len(SKIPPED)} file(s) skipped by no-downgrade: see the WARNING lines above.")
    print("Nothing committed or pushed. Review with git status in MWManager (this repository is never changed).")
    return 0


def main(argv=None):
    target, dry = _check_args(sys.argv[1:] if argv is None else argv)
    saved = read_ini()
    mwm = target or saved
    if not mwm:
        print("sync.py: no MWManager folder given and none saved in sync.ini. Nothing was done.\n"
              "Run: python sync.py <MWManager folder> --dry-run", file=sys.stderr)
        return 1
    mwm = os.path.abspath(mwm)
    if not os.path.isdir(mwm):
        print(f"sync.py: not a folder: {mwm}. Nothing was done.", file=sys.stderr)
        return 1
    inst = game_install(mwm)
    if inst:
        print(f"sync.py: {mwm} is inside a Morrowind install ({inst}); sync.py never writes there (deploy.py does). "
              "Nothing was done.", file=sys.stderr)
        return 1
    rc = run(HERE, mwm, dry)
    if rc == 0 and target and not dry and os.path.normcase(mwm) != os.path.normcase(os.path.abspath(saved or "")):
        write_ini(mwm)
    return rc


if __name__ == "__main__":
    sys.exit(main())