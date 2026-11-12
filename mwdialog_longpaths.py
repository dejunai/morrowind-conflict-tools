"""Asset paths too long for Windows or for Morrowind, for mwdialog_check (Data Files) and vortex_tidy (each
mod's staging folder).

Limits (checked against MWSE's reverse-engineered engine structures, MWSE/TES3*.h):
  * Morrowind.exe is a 32-bit program without Windows' long-path opt-in, so a file it opens must have a full
    path of at most 259 characters (MAX_PATH 260 with the closing NUL): "<game>\\Data Files\\Meshes\\...".
    The game keeps its Data Files folder in a MAX_PATH buffer too (TES3DataHandler dataFilesPath[MAX_PATH]).
  * Sound records keep the file name in a fixed 32-byte field (TES3Sound.h filename[32]: at most 31
    characters under Sound\\); magic effects keep their icon and particle texture in 32-byte fields
    (TES3MagicEffect.h icon[32], particleTexture[32]). Longer values are cut off when the game loads them.
  * Models, icons, body parts and birthsign textures are pointers to strings (no record-level limit);
    landscape textures use a MAX_PATH buffer (TES3LandTexture.h texturePath[MAX_PATH]).
  * The Construction Set refuses mesh paths over 32 characters (an editor limit, not the game's).
  * Files inside a BSA are found by a hash of their name: the Windows limit doesn't apply to them, and a BSA
    can't be changed anyway, so they are never moved.

What is done (report first; --fix / tidy --apply make the changes):
  * a file whose path under Data Files is too long moves to <top>\\lp\\<first 16 characters of its name>_<6+
    hex digits of a hash of its old path>.<ext> (meshes, textures, icons, sound, splash); a model's x*.nif /
    x*.kf animation files move with it under the same new name;
  * .esp records that name it get the new path (in place, backed up first);
  * .esm records (never edited) get a corrected copy in the ESM patch (mwdialog_check - ESM fixes.esp);
  * loose models that name a moved texture get the new texture path written into them (the same
    length-prefixed strings the absolute-path repair rewrites; original kept). A model inside a BSA can't be
    changed: a texture such a model names is left where it is (reported);
  * every move is listed in mwdialog_longpaths.json next to Morrowind.ini; mwdialog_check --longpaths-undo
    puts the files back and the paths in plugins and models (the ESM patch drops its copies on the next
    --fix). A file already moved is never shortened again (its new name is short; the list ties the two).
"""
import hashlib
import json
import os
import re
import shutil
import struct
import time

MAX_PATH_CHARS = 259                 # longest full path a non-long-path-aware Windows program can open
NEAR_CHARS = 240                     # reported as "close to the limit"
FIELD_LIMITS = {("SOUN", "FNAM"): 31, ("MGEF", "ITEX"): 31, ("MGEF", "PTEX"): 31}
SHORT_DIR = "lp"
STEM_KEEP = 16
RECORD = "mwdialog_longpaths.json"
ASSET_TOPS = ("meshes", "textures", "icons", "bookart", "splash", "sound", "music", "video")
MOVABLE_TOPS = ("meshes", "textures", "icons", "sound", "splash")   # music, video, book art: named in scripts/text
KIND_TOP = {"mesh": "meshes", "icon": "icons", "texture": "textures", "sound": "sound"}
STEM_TOPS = ("textures", "icons")    # the game takes the .dds of a .tga/.bmp name
# path fields in plugins: (record tag or None for any; subrecord) -> top folder the value is under
PATH_FIELDS = {(None, "MODL"): "meshes", (None, "ITEX"): "icons", ("MGEF", "PTEX"): "textures",
               ("SOUN", "FNAM"): "sound", ("LTEX", "DATA"): "textures", ("BSGN", "TNAM"): "textures",
               ("INFO", "SNAM"): "sound"}
TEX_STR_RE = re.compile(rb"\.(?:dds|tga|bmp)(?![A-Za-z0-9_])", re.I)


def ext_path(p):
    """p with Windows' \\\\?\\ prefix when it is long (so Python can still reach it); unchanged elsewhere."""
    if os.name != "nt" or len(p) < 240 or p.startswith("\\\\?\\"):
        return p
    return "\\\\?\\" + os.path.abspath(p)


def norm(rel):
    return rel.replace("/", "\\").replace(os.sep, "\\").strip().lower().lstrip("\\")


def full_len(data_dir, rel):
    """Length of the full Windows path of `rel` (a path under Data Files) once it is in Data Files."""
    return len(os.path.abspath(data_dir)) + 1 + len(rel)


def too_long(data_dir, rel):
    return full_len(data_dir, rel) > MAX_PATH_CHARS


def ref_key(top, value):
    """A path a plugin or model names, as a lowercase path under Data Files with its top folder."""
    v = norm(value)
    if v.startswith("data files\\"):
        v = v[11:]
    return v if v.startswith(top + "\\") else top + "\\" + v


def stem_key(key):
    top = key.split("\\", 1)[0]
    return os.path.splitext(key)[0] if top in STEM_TOPS else key


def under_top(rel):
    """'Meshes\\a\\b.nif' -> 'a\\b.nif' (what a record or model names)."""
    return rel.replace("/", "\\").replace(os.sep, "\\").split("\\", 1)[1]


def short_rel(rel, taken, mine=()):
    """The short path for `rel` (a path under Data Files): <Top>\\lp\\<name, 16 characters>_<hash><ext>. The
    hash is of the old path, so the same file always gets the same name; a name already used by another file
    (`taken`: lowercase paths; `mine`: names this file may reuse) gets a longer hash, then a number."""
    parts = rel.replace("/", "\\").replace(os.sep, "\\").split("\\")
    top = parts[0]
    stem, ext = os.path.splitext(parts[-1])
    clean = re.sub(r"[^A-Za-z0-9_\-]", "_", stem)[:STEM_KEEP].rstrip("_") or "f"
    h = hashlib.sha1(norm(rel).encode("utf-8")).hexdigest()
    for n in (6, 10, 16, 40):
        cand = f"{top}\\{SHORT_DIR}\\{clean}_{h[:n]}{ext}"
        if cand.lower() not in taken or cand.lower() in mine:
            return cand
    k = 2
    while True:
        cand = f"{top}\\{SHORT_DIR}\\{clean}_{h[:6]}_{k}{ext}"
        if cand.lower() not in taken or cand.lower() in mine:
            return cand
        k += 1


def is_short(rel):
    p = norm(rel).split("\\")
    return len(p) > 2 and p[1] == SHORT_DIR


def fs(rel):
    """A path with backslashes (as plugins and the record keep it) in this system's separators."""
    return rel.replace("\\", os.sep).replace("/", os.sep)


def _split(rel):
    p = rel.replace("/", "\\").replace(os.sep, "\\")
    d, _s, b = p.rpartition("\\")
    return d, b


def twins(rel, exists):
    """A model's animation files: x<name>.nif / x<name>.kf next to it (the game loads them by that name)."""
    if not rel.lower().endswith(".nif"):
        return []
    d, b = _split(rel)
    out = []
    for ext in (".nif", ".kf"):
        t = d + "\\x" + os.path.splitext(b)[0] + ext
        if exists(t):
            out.append(t)
    return out


def twin_short(short, twin):
    d, b = _split(short)
    return d + "\\x" + os.path.splitext(b)[0] + os.path.splitext(twin)[1]


def base_of_twin(rel, exists):
    """For x<name>.nif / .kf: the model <name>.nif next to it when there is one (it moves, the twin with it)."""
    d, b = _split(rel)
    if not b.lower().startswith("x") or not b.lower().endswith((".nif", ".kf")):
        return None
    base = d + "\\" + os.path.splitext(b[1:])[0] + ".nif"
    return base if exists(base) else None


# ------------------------------------------------------------------ the list of moves (mwdialog_longpaths.json)
class Record:
    """{"moves": [{"orig", "short" (paths under Data Files), "files": [[from, to] full paths], "esp": [plugin
    paths edited], "nif": [model paths edited], "esm": [master names whose records the patch corrects],
    "when", "by"}]}"""

    def __init__(self, game_dir):
        self.path = os.path.join(game_dir, RECORD)
        self.moves = []
        try:
            with open(self.path, encoding="utf-8") as f:
                self.moves = json.load(f).get("moves", [])
        except (OSError, ValueError, AttributeError):
            self.moves = []

    def by_orig(self):
        return {norm(e["orig"]): e for e in self.moves}

    def pairs(self, data_dir=None):
        """{old path key: new path under Data Files} for moves whose new file is there (or data_dir None)."""
        out = {}
        for e in self.moves:
            if data_dir is None or os.path.exists(ext_path(os.path.join(data_dir, fs(e["short"])))) \
                    or e.get("by") == "tidy":
                out[norm(e["orig"])] = e["short"]
        return out

    def add(self, entry):
        self.moves = [e for e in self.moves if norm(e["orig"]) != norm(entry["orig"])] + [entry]

    def save(self):
        if not self.moves:
            if os.path.exists(self.path):
                os.replace(self.path, self.path + ".undone")
            return
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"moves": self.moves}, f, indent=1)
        os.replace(tmp, self.path)


# ------------------------------------------------------------------ rewriting names in plugins and models
def _lookup_key(pairs, key):
    """(old path key, new path) for a path key: exact, or (textures, icons) by name without extension; else
    (None, None)."""
    if key in pairs:
        return key, pairs[key]
    if key.split("\\", 1)[0] in STEM_TOPS:
        sk = stem_key(key)
        for k, v in pairs.items():
            if stem_key(k) == sk:
                return k, v
    return None, None


def _lookup(pairs, key):
    return _lookup_key(pairs, key)[1]


def retarget_plugin_bytes(data, pairs, m):
    """A plugin with every path field (PATH_FIELDS) that names an old path in `pairs` ({old key: new path
    under Data Files}) changed to the new one (any length: record sizes are rebuilt). Returns (bytes,
    [(tag, id, subrecord, old value, new value)])."""
    out, hits = [], []
    for off, tag, flags, body in m.iter_records(data):
        raw = data[off:off + 16 + len(body)]
        new_subs, changed = [], False
        rid = ""
        for n, d in m.iter_subs(body):
            if n in ("NAME", "INAM") and not rid:
                rid = m.cstr(d)
            top = PATH_FIELDS.get((tag, n)) or PATH_FIELDS.get((None, n))
            if top:
                val = m.cstr(d).strip()
                newp = _lookup(pairs, ref_key(top, val)) if val else None
                if newp:
                    nv = under_top(newp)
                    new_subs.append(m.pack_sub(n, nv.encode(m.ENC, m.MW_ERRORS) + b"\0"))
                    hits.append((tag, rid, n, val, nv))
                    changed = True
                    continue
            new_subs.append(m.pack_sub(n, d))
        if changed:
            nb = b"".join(new_subs)
            out.append(tag.encode("latin-1") + struct.pack("<I", len(nb)) + data[off + 8:off + 16] + nb)
        else:
            out.append(raw)
    return b"".join(out), hits


def nif_texture_strings(data):
    """[(offset of the 4-byte length, the string)] of length-prefixed texture names in a model."""
    out, last = [], 0
    for mm in TEX_STR_RE.finditer(data):
        end = mm.end()
        for s in range(mm.start() - 1, max(last, mm.start() - 300, 3), -1):
            if struct.unpack_from("<I", data, s - 4)[0] == end - s:
                if all(0x20 <= c < 0x7f for c in data[s:end]):
                    out.append((s - 4, data[s:end]))
                    last = end
                break
    return out


def rewrite_nif_textures(data, pairs):
    """A model with each texture name that is an old path in `pairs` changed to the new path (under
    Textures, as models name them). Returns (bytes or None, count)."""
    hits = []
    for at, s in nif_texture_strings(data):
        name = s.decode("latin-1")
        low = norm(name)
        i = low.find("textures\\")
        key = "textures\\" + (low[i + 9:] if i != -1 else low)
        newp = _lookup(pairs, key)
        if newp:
            hits.append((at, s, under_top(newp).encode("latin-1")))
    if not hits:
        return None, 0
    out, pos = [], 0
    for at, old, new in hits:
        out.append(data[pos:at])
        out.append(struct.pack("<I", len(new)) + new)
        pos = at + 4 + len(old)
    out.append(data[pos:])
    return b"".join(out), len(hits)


def _move(src, dst):
    os.makedirs(ext_path(os.path.dirname(dst)), exist_ok=True)
    if os.path.exists(ext_path(dst)):
        os.remove(ext_path(dst))               # our own short copy of an older version of the file
    os.replace(ext_path(src), ext_path(dst))


# ------------------------------------------------------------------ mwdialog_check: Data Files
def check(world, m):
    """Plan the moves for Data Files (world.longpath_plan), point the asset index at files already moved, and
    add the record corrections (world.item_fixes: an .esp in place, an .esm through the ESM patch)."""
    A = world.assets
    tree = world.tree
    data_dir = os.path.abspath(world.args_data_dir)
    game_dir = os.path.dirname(data_dir)
    rec = Record(game_dir)
    world.longpath_plan = []
    r = world.r
    files = {}                                   # lowercase rel -> (rel, full) of asset files
    for top, rel, full in tree.files:
        if top in ASSET_TOPS:
            files[norm(rel)] = (rel, full)
    exists = lambda rel: norm(rel) in files       # noqa: E731
    long_ = [(rel, full) for k, (rel, full) in files.items() if too_long(data_dir, rel) and not is_short(rel)]
    near = sum(1 for k, (rel, full) in files.items() if NEAR_CHARS < full_len(data_dir, rel) <= MAX_PATH_CHARS)
    # sound records whose file name doesn't fit the game's 32-byte field: the file gets a short name too
    for (tag, rid), lst in world.models.items():
        if tag != "SOUN" or not lst:
            continue
        v = lst[-1][2].get(("FNAM", "sound"))
        if v and len(v) > FIELD_LIMITS[("SOUN", "FNAM")]:
            k = ref_key("sound", v)
            if k in files and not is_short(k) and files[k] not in long_:
                long_.append(files[k])
    if near:
        r.add("INFO", "Data Files", "", "", f"{near} asset file(s) are within {MAX_PATH_CHARS - NEAR_CHARS} characters "
                                            f"of Windows' {MAX_PATH_CHARS}-character path limit (with Data Files at "
                                            f"{data_dir})")
    # the textures models inside BSAs name: such a texture can't move (the model can't be changed)
    bsa_tex = None
    taken = set(files) | {norm(e["short"]) for e in rec.moves}
    known = rec.by_orig()
    plan = []
    seen = set()
    for rel, full in sorted(long_, key=lambda x: x[0].lower()):
        base = base_of_twin(rel, exists)
        if base:
            rel, full = files[norm(base)]
        if norm(rel) in seen:
            continue
        seen.add(norm(rel))
        top = norm(rel).split("\\", 1)[0]
        L = full_len(data_dir, rel)
        if top not in MOVABLE_TOPS:
            r.add("WARN", "Data Files", "", "", f"{rel}: its path is {L} characters long in Data Files; Windows' limit "
                                                f"is {MAX_PATH_CHARS}, so the game can't open it ({top} files are named "
                                                f"in scripts or book text: shorten it by hand)")
            continue
        if top == "textures":
            if bsa_tex is None:
                bsa_tex = {}
                for b in getattr(A, "bsa_paths", ()):
                    for mdl, tn in A.bsa_facts(b).get("tn", {}).items():
                        for t in tn:
                            bsa_tex.setdefault(stem_key(ref_key("textures", t)), os.path.basename(b) + ": " + mdl)
            who = bsa_tex.get(stem_key(norm(rel)))
            if who:
                r.add("WARN", "Data Files", "", "", f"{rel}: its path is {L} characters long in Data Files (limit "
                                                    f"{MAX_PATH_CHARS}), but a model inside a BSA names it ({who}), "
                                                    f"and a BSA can't be changed: left as it is")
                continue
        old = known.get(norm(rel))
        mine = {norm(old["short"])} if old else set()
        short = old["short"] if old else short_rel(rel, taken, mine)
        taken.add(norm(short))
        tw = [(files[norm(t)][0], files[norm(t)][1], twin_short(short, t)) for t in twins(rel, exists)]
        plan.append({"orig": rel, "short": short, "full": full, "twins": tw, "len": L})
    pairs = rec.pairs(data_dir)
    for p in plan:
        pairs[norm(p["orig"])] = p["short"]
    # files moved by an earlier run (or by tidy, before Vortex deployed them): the old names count as there
    for e in rec.moves:
        k = norm(e["orig"])
        if k in files:
            continue
        top = k.split("\\", 1)[0]
        sk = norm(e["short"])
        if sk not in files:
            continue
        sub = k.split("\\", 1)[1]
        if top == "meshes" and sk in files:
            A.mesh_loose.setdefault(sub, files[sk][1])
        A._add(top, sub)
    if not pairs:
        return
    # records naming an old path: every .esp record; of the masters only the last record of each object
    fixes = 0
    by_orig = {}
    for (tag, rid), lst in world.models.items():
        last_master = max((x for x in lst if not x[1].lower().endswith(m.FIXABLE_EXT)), key=lambda x: x[0],
                          default=None)
        for x in lst:
            idx, plugin, fields, deleted, oid = x
            if deleted or (not plugin.lower().endswith(m.FIXABLE_EXT) and x is not last_master):
                continue
            new, orig = {}, None
            for (sub, kind), v in fields.items():
                ok, np_ = _lookup_key(pairs, ref_key(KIND_TOP.get(kind, "meshes"), v))
                if np_:
                    new[sub] = under_top(np_)
                    orig = orig or ok
                    by_orig.setdefault(ok, []).append(plugin)
            if new:
                fixes += 1
                world.item_fixes.append({"plugin": plugin, "tag": tag, "id": oid, "set": new, "npco": set(),
                                         "longpath": orig,
                                         "msgs": [(f"names a path too long for Windows ({', '.join(new)})",
                                                   "now names " + ", ".join(new.values()))]})
    # loose models naming a moved texture: their texture names are rewritten
    nif_edits = {}
    for mdl, mfull in list(A.mesh_loose.items()):
        if not os.path.normcase(os.path.abspath(mfull)).startswith(os.path.normcase(data_dir) + os.sep):
            continue
        for t in A.texture_names(mdl):
            np_ = _lookup(pairs, ref_key("textures", t))
            if np_:
                nif_edits.setdefault(mfull, []).append((t, np_))
    world.longpath_nifs = nif_edits
    world.longpath_pairs = pairs
    world.longpath_plan = plan
    for p in plan:
        users = len(by_orig.get(norm(p["orig"]), []))
        models = sum(1 for v in nif_edits.values() for t, np_ in v if np_ == p["short"])
        r.add("WARN", "Data Files", "", "", f"{p['orig']}: its path is {p['len']} characters long in Data Files; "
                                            f"Windows' limit is {MAX_PATH_CHARS}, so the game can't open it. --fix "
                                            f"moves it to {p['short']}" + (f" (with {len(p['twins'])} animation file(s))"
                                                                           if p["twins"] else "")
              + f" and points {users} record(s) and {models} model(s) at the new path")
    stale = [e for e in rec.moves if norm(e["orig"]) not in files and norm(e["short"]) in files]
    if fixes and stale and not plan:
        r.add("INFO", "Data Files", "", "", f"{fixes} record(s) still name the old long path of a file moved earlier "
                                            f"(listed in {RECORD}); --fix points them at the new one")


def plan_lines(world):
    plan = getattr(world, "longpath_plan", [])
    out = []
    for p in plan:
        out.append(f"    - {p['orig']}  ->  {p['short']}" + (f" (+{len(p['twins'])} animation file(s))" if p["twins"] else ""))
    nifs = getattr(world, "longpath_nifs", {})
    if nifs:
        out.append(f"    and {len(nifs)} model(s) get the new texture paths (originals kept)")
    return out


def apply(world, m, data_dir, log):
    """Do the moves of world.longpath_plan (Data Files and, for a Vortex-deployed file, its mod folder) and the
    model edits. Returns the old paths whose move failed (their record fixes must not be written)."""
    data_dir = os.path.abspath(data_dir)
    game_dir = os.path.dirname(data_dir)
    rec = Record(game_dir)
    failed = set()
    when = time.strftime("%Y-%m-%d %H:%M:%S")
    for p in getattr(world, "longpath_plan", []):
        moved = []
        try:
            for rel, full, short in [(p["orig"], p["full"], p["short"])] + list(p["twins"]):
                dst = os.path.join(data_dir, fs(short))
                mod, _pl = (None, None)
                try:
                    mod, _pl = m.asset_owner_folder(data_dir, rel)
                except Exception:
                    mod = None
                if mod:                                      # the mod folder's copy: Vortex deploys that one
                    s_src, s_dst = os.path.join(mod, fs(rel)), os.path.join(mod, fs(short))
                    if os.path.exists(ext_path(s_src)):
                        _move(s_src, s_dst)
                        moved.append([s_src, s_dst])
                _move(full, dst)
                moved.append([full, dst])
        except OSError as e:
            failed.add(norm(p["orig"]))
            log.append(("Data Files", f"'{p['orig']}' (path too long)", f"NOT moved: {e}"))
            for src, dst in reversed(moved):                # put back what this one moved
                try:
                    _move(dst, src)
                except OSError:
                    pass
            continue
        esp = sorted({fx["plugin"] for fx in world.item_fixes if fx.get("longpath") == norm(p["orig"])
                      and fx["plugin"].lower().endswith(m.FIXABLE_EXT)})
        esm = sorted({fx["plugin"] for fx in world.item_fixes if fx.get("longpath") == norm(p["orig"])
                      and not fx["plugin"].lower().endswith(m.FIXABLE_EXT)})
        rec.add({"orig": p["orig"], "short": p["short"], "files": moved,
                 "esp": [os.path.join(data_dir, e) for e in esp], "esm": esm, "nif": [], "when": when,
                 "by": "mwdialog_check"})
        log.append(("Data Files", f"'{p['orig']}' (path too long)", f"moved to {p['short']}"))
    pairs = {k: v for k, v in getattr(world, "longpath_pairs", {}).items() if k not in failed}
    for mfull, _l in getattr(world, "longpath_nifs", {}).items():
        try:
            with open(ext_path(mfull), "rb") as f:
                data = f.read()
            new, n = rewrite_nif_textures(data, pairs)
            if not new:
                continue
            rel = os.path.relpath(mfull, data_dir)
            m.backup_asset_original(data_dir, rel, feature="longpaths")
            m.replace_asset_in_place(mfull, new)
            for e in rec.moves:
                if any(v == e["short"] for _t, v in _l) and mfull not in e.setdefault("nif", []):
                    e["nif"].append(mfull)
            log.append(("Data Files", f"'{rel}' (texture paths)", f"{n} texture name(s) now the short path"))
        except OSError as e:
            log.append(("Data Files", f"'{mfull}'", f"model NOT changed: {e}"))
    rec.save()
    return failed


def undo(game_dir, data_dir, m):
    """--longpaths-undo: every move in mwdialog_longpaths.json back, and the paths in the plugins and models
    that were pointed at the short names. Returns 0, or 1 when something couldn't be put back."""
    rec = Record(game_dir)
    if not rec.moves:
        print("Nothing to undo (no " + RECORD + ").")
        return 0
    pairs = {norm(e["short"]): e["orig"] for e in rec.moves}
    bad = 0
    plugins, nifs = set(), set()
    for e in reversed(rec.moves):
        for src, dst in reversed(e.get("files", [])):
            try:
                if os.path.exists(ext_path(dst)) and not os.path.exists(ext_path(src)):
                    _move(dst, src)
            except OSError as ex:
                bad += 1
                print(f"  could not put back {src}: {ex}")
        plugins.update(e.get("esp", []))
        nifs.update(e.get("nif", []))
    for pp in sorted(plugins):
        try:
            with open(pp, "rb") as f:
                data = f.read()
            new, hits = retarget_plugin_bytes(data, pairs, m)
            if hits:
                st = os.stat(pp)
                shutil.copy2(pp, m.backup_path(pp))
                m.write_plugin_bytes(pp, new, keep_times=st)
                print(f"  {os.path.basename(pp)}: {len(hits)} path(s) back to the long names")
        except (OSError, m.FormatError) as ex:
            bad += 1
            print(f"  {pp}: NOT changed ({ex})")
    for nf in sorted(nifs):
        try:
            with open(ext_path(nf), "rb") as f:
                data = f.read()
            new, n = rewrite_nif_textures(data, pairs)
            if new:
                m.replace_asset_in_place(nf, new)
        except OSError as ex:
            bad += 1
            print(f"  {nf}: NOT changed ({ex})")
    if bad:
        print(f"{bad} item(s) could not be put back; {RECORD} is kept so you can try again.")
        return 1
    n = len(rec.moves)
    rec.moves = []
    rec.save()
    print(f"{n} file(s) back at their long paths. Run --fix to rebuild the ESM patch without the corrected "
          f"master records (and Deploy in Vortex if tidy moved files in mod folders).")
    return 0


# ------------------------------------------------------------------ vortex_tidy: one mod's staging folder
def check_mod(root, data_dir, m, game_dir=None):
    """(issues [(severity, rel, message)], plan) for one mod folder: files whose path will be too long once
    deployed to data_dir (and, for information, ones whose path in the staging folder itself is)."""
    data_dir = os.path.abspath(data_dir)
    issues, plan = [], []
    rels = {}
    pre = ext_path(root) if os.name == "nt" else root
    for dp, ds, fs_ in os.walk(pre):
        rd = os.path.relpath(dp, pre)
        if rd == ".":
            ds[:] = [d for d in ds if d.lower() not in ("off", "bugreports")]
            continue
        top = rd.split(os.sep)[0].lower()
        if top not in ASSET_TOPS:
            ds[:] = []
            continue
        ds[:] = [d for d in ds if d.lower() not in ("off", ".orphaned")]
        for f in fs_:
            rel = os.path.join(rd, f)
            rels[norm(rel)] = rel
            if len(os.path.join(root, rel)) > MAX_PATH_CHARS and not too_long(data_dir, rel):
                issues.append(("INFO", rel, f"its path in the mod folder is {len(os.path.join(root, rel))} characters "
                                            f"(over {MAX_PATH_CHARS}); fine once deployed, but some Windows tools "
                                            f"can't open it here"))
    exists = lambda rel: norm(rel) in rels        # noqa: E731
    rec = Record(game_dir or os.path.dirname(data_dir))
    known = rec.by_orig()
    taken = set(rels) | {norm(e["short"]) for e in rec.moves}
    seen = set()
    for k, rel in sorted(rels.items()):
        if not too_long(data_dir, rel) or is_short(rel):
            continue
        base = base_of_twin(rel, exists)
        if base:
            rel = rels[norm(base)]
        if norm(rel) in seen:
            continue
        seen.add(norm(rel))
        top = norm(rel).split("\\", 1)[0]
        L = full_len(data_dir, rel)
        if top not in MOVABLE_TOPS:
            issues.append(("WARN", rel, f"{L} characters once deployed (limit {MAX_PATH_CHARS}); {top} files are named "
                                        f"in scripts or book text: shorten it by hand"))
            continue
        old = known.get(norm(rel))
        short = old["short"] if old else short_rel(rel, taken, {norm(old["short"])} if old else set())
        taken.add(norm(short))
        tw = [(rels[norm(t)], twin_short(short, t)) for t in twins(rel, exists)]
        plan.append({"orig": rel, "short": short, "twins": tw, "len": L})
        issues.append(("WARN", rel, f"{L} characters once deployed (Windows' limit is {MAX_PATH_CHARS}: the game "
                                    f"can't open it) -> moved to {short}, the mod's .esp files and models pointed "
                                    f"there (its .esm records: through mwdialog_check's ESM patch)"))
    return issues, plan


def apply_mod(root, plan, m, game_dir, plugin_name=None, log=print):
    """Do one mod's moves (in its folder), point its .esp files and its models at the new paths (originals
    in <mod>\\Off\\longpaths\\), and list everything in mwdialog_longpaths.json (an .esm of the mod is listed:
    mwdialog_check --fix writes the corrected records into its ESM patch). Returns the number moved."""
    if not plan:
        return 0
    rec = Record(game_dir)
    when = time.strftime("%Y-%m-%d %H:%M:%S")
    pairs, done = {}, []
    for p in plan:
        moved = []
        try:
            for rel, short in [(p["orig"], p["short"])] + [tuple(t) for t in p["twins"]]:
                src, dst = os.path.join(root, fs(rel)), os.path.join(root, fs(short))
                _move(src, dst)
                moved.append([src, dst])
        except OSError as e:
            log(f"  {p['orig']}: NOT moved ({e})")
            for src, dst in reversed(moved):
                try:
                    _move(dst, src)
                except OSError:
                    pass
            continue
        pairs[norm(p["orig"])] = p["short"]
        done.append((p, moved))
    if not pairs:
        return 0
    esp_done, esm_names, nif_done = [], [], []
    for pf in sorted(os.listdir(root)):
        pp = os.path.join(root, pf)
        if not pf.lower().endswith((".esp", ".esm")):
            continue
        try:
            with open(pp, "rb") as f:
                data = f.read()
            new, hits = retarget_plugin_bytes(data, pairs, m)
        except (OSError, m.FormatError) as e:
            log(f"  {pf}: not read ({e})")
            continue
        if not hits:
            continue
        if pf.lower().endswith(".esm"):
            esm_names.append(pf)                         # never edited: the ESM patch corrects its records
            continue
        bak = m.off_dest(root, "longpaths", pf, pf)
        if not os.path.exists(bak):
            os.makedirs(os.path.dirname(bak), exist_ok=True)
            shutil.copy2(pp, bak)
        m.write_plugin_bytes(pp, new, keep_times=os.stat(pp))
        esp_done.append(pp)
        log(f"  {pf}: {len(hits)} path(s) now short")
    mroot = next((os.path.join(root, d) for d in os.listdir(root) if d.lower() == "meshes"), None)
    for dp, _ds, fns in (os.walk(ext_path(mroot)) if mroot else ()):
        if (os.sep + "off" + os.sep) in (dp.lower() + os.sep):
            continue
        for fn in fns:
            if not fn.lower().endswith(".nif"):
                continue
            nf = os.path.join(dp, fn)
            try:
                with open(nf, "rb") as f:
                    data = f.read()
            except OSError:
                continue
            new, n = rewrite_nif_textures(data, pairs)
            if not new:
                continue
            rel = os.path.relpath(nf.replace("\\\\?\\", ""), root)
            bak = m.off_dest(root, "longpaths", plugin_name, rel)
            if not os.path.exists(ext_path(bak)):
                os.makedirs(ext_path(os.path.dirname(bak)), exist_ok=True)
                shutil.copy2(nf, ext_path(bak))
            m.replace_asset_in_place(nf, new)
            nif_done.append(nf.replace("\\\\?\\", ""))
    for p, moved in done:
        rec.add({"orig": p["orig"], "short": p["short"], "files": moved, "esp": esp_done, "esm": esm_names,
                 "nif": nif_done, "when": when, "by": "tidy", "mod": os.path.basename(os.path.normpath(root))})
    rec.save()
    if esm_names:
        log(f"  {', '.join(esm_names)}: master(s) name the moved file(s); run mwdialog_check --fix after deploying "
            f"(its ESM patch gets the corrected records)")
    return len(done)
