"""mwdialog_hashes.py - the hash check --play makes before it starts the game.

What is checked (all in Data Files):
  * the core files: Morrowind.esm, Tribunal.esm, Bloodmoon.esm and Morrowind.bsa, Tribunal.bsa, Bloodmoon.bsa.
    Tribunal and Bloodmoon are optional: when one is missing it is skipped quietly (never a mismatch).
  * every plugin these tools generate (the patches, AutoMerge and --merge outputs), recorded by the code that
    writes it, once the file is final. A rebuild records the new hash: that is expected.

The baseline is recorded the first time a file is seen (never shipped, never in the repository) in
mwdialog_play_hashes.json, in the tools' generated folder (state_path: <game>\\conflict-tools\\generated\\ when
installed in the game). Later --play runs compare against it. A file that changed, or a recorded patch that is
gone from Data Files while the load order still lists it, makes --play refuse to start the game (exit 4) with
one line per file; --play-force prints the same warning and starts it anyway. --rebaseline-hashes accepts the
current files as the new baseline.

The check never changes a game file. Python 3.9+, standard library only.
"""
import datetime
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_paths as MP  # noqa: E402
import mwdialog_tes3 as T  # noqa: E402

RECORD = "mwdialog_play_hashes.json"
SCHEMA = "mwdialog-play-hashes"
VERSION = 1
CORE = ("Morrowind.esm", "Tribunal.esm", "Bloodmoon.esm", "Morrowind.bsa", "Tribunal.bsa", "Bloodmoon.bsa")
OPTIONAL = frozenset(n.lower() for n in CORE if not n.lower().startswith("morrowind."))
OUR_AUTHOR = b"mwdialog_check"          # the TES3 header author of every plugin these tools generate
CHUNK = 1 << 20
SHORT = 12                              # hex digits of a hash shown in messages
REFUSED = 4                             # --play's exit code when the hash check fails


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def find(data_dir, name):
    """The path of `name` in data_dir, matched without regard to case; None when it isn't there."""
    p = os.path.join(data_dir, name)
    if os.path.isfile(p):
        return p
    try:
        for n in os.listdir(data_dir):
            if n.lower() == name.lower() and os.path.isfile(os.path.join(data_dir, n)):
                return os.path.join(data_dir, n)
    except OSError:
        pass
    return None


def record_path(data_dir):
    """Where the baseline is kept: the tools' generated folder for this game (never Data Files)."""
    return MP.state_path(os.path.dirname(os.path.abspath(data_dir)), RECORD)


def empty_record():
    return {"schema": SCHEMA, "version": VERSION, "core": {}, "patches": {}}


def read_record(path):
    """(record, error). No file yet: a new empty record and no error."""
    if not os.path.isfile(path):
        return empty_record(), None
    try:
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError) as e:
        return None, f"{path} can't be read ({e})"
    if not isinstance(rec, dict) or rec.get("schema") != SCHEMA or not isinstance(rec.get("core"), dict) \
            or not isinstance(rec.get("patches"), dict):
        return None, f"{path} is not a --play hash record"
    if not isinstance(rec.get("version"), int) or rec["version"] > VERSION:
        return None, f"{path} has version {rec.get('version')!r}, newer than this script's {VERSION}"
    return rec, None


def write_record(path, rec):
    MP._write_json_atomic(path, rec)


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _entry(sha, size):
    return {"sha256": sha, "size": size, "recorded": _now()}


def _get(table, name):
    """(key, entry) of `name` in a record table, any case; (None, None) when it isn't there."""
    for k, v in table.items():
        if k.lower() == name.lower():
            return k, v
    return None, None


def is_ours(data):
    """Do these plugin bytes come from these tools? (the TES3 header's author field)"""
    head = bytes(data[:16 + 8 + 300])
    if head[:4] != b"TES3" or head[16:20] != b"HEDR":
        return False
    author = head[24 + 8:24 + 8 + 32].split(b"\0", 1)[0].strip().lower()
    return author.startswith(OUR_AUTHOR)


def record_patch(path, data_dir=None, sha=None, size=None):
    """Record the hash of one of our generated plugins once it is final. data_dir: the Data Files folder the
    game loads it from (default: the folder it was written to). Never raises: a record that can't be written
    is one line on stderr, and the patch itself stays as written."""
    data_dir = os.path.abspath(data_dir or os.path.dirname(os.path.abspath(path)))
    name = os.path.basename(path)
    try:
        if sha is None:
            sha, size = sha256_file(path), os.path.getsize(path)
        rp = record_path(data_dir)
        rec, err = read_record(rp)
        if err:
            print(f"  (the hash of {name} was not recorded: {err}; --rebaseline-hashes writes a new record)",
                  file=sys.stderr)
            return None
        key, _old = _get(rec["patches"], name)
        if key is not None and key != name:
            del rec["patches"][key]
        rec["patches"][name] = _entry(sha, size)
        write_record(rp, rec)
        return sha
    except OSError as e:
        print(f"  (the hash of {name} was not recorded: {e})", file=sys.stderr)
        return None


def note_written_plugin(path, data):
    """mwdialog_tes3.write_plugin_bytes calls this after every plugin it writes. A plugin of ours (by its header)
    written into a Data Files folder, or one already in the record (rewritten in place), gets its hash recorded.
    Anything else (a mod's plugin, a temporary stage file) is left alone."""
    folder = os.path.dirname(os.path.abspath(path))
    if os.path.basename(folder).lower() != "data files":
        return
    ours = is_ours(data)
    if not ours:
        rec, err = read_record(record_path(folder)) if os.path.isfile(record_path(folder)) else (None, None)
        if err or rec is None or _get(rec["patches"], os.path.basename(path))[0] is None:
            return
    data = bytes(data)
    record_patch(path, folder, sha=hashlib.sha256(data).hexdigest(), size=len(data))


if note_written_plugin not in T.AFTER_PLUGIN_WRITE:
    T.AFTER_PLUGIN_WRITE.append(note_written_plugin)


def verify(data_dir, listed=(), dry=False):
    """Check the core files and the recorded patches against the record. listed: the plugin names the load order
    lists (a recorded patch missing from Data Files is a problem only while it is listed; otherwise it was taken
    out on purpose and is forgotten). New core files are recorded (unless dry). Returns a dict:
      changed:   [(name, kind, recorded entry, new sha)]
      missing:   [(name, kind)]
      recorded:  [names whose first hash was recorded now]
      forgotten: [patch names dropped from the record]
      checked:   count of files compared
      error:     the record can't be used (message) or None
      path:      the record's path"""
    data_dir = os.path.abspath(data_dir)
    rp = record_path(data_dir)
    out = {"changed": [], "missing": [], "recorded": [], "forgotten": [], "checked": 0, "error": None, "path": rp}
    rec, err = read_record(rp)
    if err:
        out["error"] = err
        return out
    dirty = False
    for name in CORE:
        p = find(data_dir, name)
        key, ent = _get(rec["core"], name)
        if p is None:
            if name.lower() not in OPTIONAL:
                out["missing"].append((name, "core"))
            continue                                          # Tribunal / Bloodmoon not installed: quietly skipped
        sha = sha256_file(p)
        if ent is None:
            rec["core"][name] = _entry(sha, os.path.getsize(p))
            out["recorded"].append(name)
            dirty = True
        else:
            out["checked"] += 1
            if ent.get("sha256") != sha:
                out["changed"].append((key, "core", ent, sha))
    listed_l = {n.lower() for n in listed}
    for name in sorted(rec["patches"], key=str.lower):
        ent = rec["patches"][name]
        p = find(data_dir, name)
        if p is None:
            if name.lower() in listed_l:
                out["missing"].append((name, "patch"))
            else:
                del rec["patches"][name]
                out["forgotten"].append(name)
                dirty = True
            continue
        out["checked"] += 1
        sha = sha256_file(p)
        if ent.get("sha256") != sha:
            out["changed"].append((name, "patch", ent, sha))
    if dirty and not dry:
        try:
            write_record(rp, rec)
        except OSError as e:
            print(f"--play: could not write {rp}: {e}", file=sys.stderr)
    return out


def failed(res):
    return bool(res["error"] or res["changed"] or res["missing"])


def report(res, force=False, prefix="--play"):
    """[(to_stderr, line)] for the result of verify: one short line when all is well, a loud block otherwise."""
    lines = []
    if res["recorded"]:
        lines.append((False, f"{prefix}: recorded the hash of {', '.join(res['recorded'])} (first time seen; later "
                             f"runs compare against it; record: {res['path']})"))
    if res["forgotten"]:
        lines.append((False, f"{prefix}: {len(res['forgotten'])} recorded patch(es) are no longer in Data Files or "
                             f"the load order; dropped from the hash record: {', '.join(res['forgotten'])}"))
    if not failed(res):
        if res["checked"]:
            lines.append((False, f"{prefix}: hash check: {res['checked']} file(s) match their recorded hashes."))
        return lines
    bar = "=" * 78
    head = ("HASH CHECK FAILED - starting the game anyway (--play-force)" if force
            else "HASH CHECK FAILED - NOT starting the game")
    lines += [(True, ""), (True, bar), (True, f"{prefix}: {head}")]
    if res["error"]:
        lines.append((True, f"  The hash record can't be used: {res['error']}"))
    for name, kind, ent, sha in res["changed"]:
        lines.append((True, f"  CHANGED  {name} ({'core file' if kind == 'core' else 'our patch'}): SHA-256 was "
                            f"{ent.get('sha256', '?')[:SHORT]}... (recorded {ent.get('recorded', '?')}), now "
                            f"{sha[:SHORT]}..."))
    for name, kind in res["missing"]:
        what = ("core file, required" if kind == "core" else
                "our patch: recorded, still in the load order, but gone from Data Files")
        lines.append((True, f"  MISSING  {name} ({what})"))
    lines += [(True, ""),
              (True, "  A changed patch: rebuild it with the step that made it (e.g. --fix); that records its new "
                     "hash."),
              (True, "  A core file you changed on purpose (cleaned, patched, reinstalled), or a patch you edited on "
                     "purpose:"),
              (True, "    python mwdialog_check.py --rebaseline-hashes   (accepts the files as they are now)")]
    if not force:
        lines.append((True, "  To start the game regardless: --play --play-force"))
    lines.append((True, bar))
    return lines


def our_plugins(data_dir):
    """Names of the plugins in data_dir whose TES3 header says these tools made them."""
    out = []
    try:
        names = sorted(os.listdir(data_dir), key=str.lower)
    except OSError:
        return out
    for n in names:
        p = os.path.join(data_dir, n)
        if n.lower().endswith((".esp", ".esm")) and os.path.isfile(p):
            try:
                with open(p, "rb") as f:
                    head = f.read(16 + 8 + 300)
            except OSError:
                continue
            if is_ours(head):
                out.append(n)
    return out


def rebaseline(data_dir, dry=False):
    """--rebaseline-hashes: record the current hash of every core file present, every recorded patch still in
    Data Files (dropping the ones gone), and every other plugin of ours found there (built before the record
    existed). Returns [lines]; writes nothing with dry."""
    data_dir = os.path.abspath(data_dir)
    rp = record_path(data_dir)
    old, err = read_record(rp)
    if err:
        old = empty_record()
    new = empty_record()
    lines = [f"--rebaseline-hashes{' (dry run: nothing is written)' if dry else ''}: {rp}"]
    if err:
        lines.append(f"  the old record was not usable ({err}); starting a new one")
    known = {n.lower() for n in old["patches"]}
    patches = sorted(old["patches"], key=str.lower) + [n for n in our_plugins(data_dir) if n.lower() not in known]
    for table, names in (("core", CORE), ("patches", patches)):
        for name in names:
            p = find(data_dir, name)
            _k, ent = _get(old[table], name)
            if p is None:
                if ent is not None:
                    lines.append(f"  {name}: not in Data Files; dropped from the record")
                continue
            sha = sha256_file(p)
            new[table][name] = _entry(sha, os.path.getsize(p))
            if ent is None:
                lines.append(f"  {name}: recorded {sha[:SHORT]}...")
            elif ent.get("sha256") != sha:
                lines.append(f"  {name}: CHANGED, accepted: was {ent.get('sha256', '?')[:SHORT]}..., now {sha[:SHORT]}...")
            else:
                lines.append(f"  {name}: unchanged")
    if not dry:
        write_record(rp, new)
    return lines