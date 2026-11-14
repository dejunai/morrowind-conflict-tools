"""mwdialog_datatree.py - what is on disk: the Data Files tree and its BSAs (DataTree), which models and
textures exist and are sound (ModelAssets), and the Vortex staging folders a file came from (VortexRepo).
"""
from collections import defaultdict
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_text as MT  # noqa: E402
from mwdialog_bsa import (  # noqa: E402
    bsa_file_names, bsa_index)
from mwdialog_media import (  # noqa: E402
    SOUND_ROOTS, nif_texture_refs)
from mwdialog_state import (  # noqa: E402
    read_generated_record)
from mwdialog_tes3 import (  # noqa: E402
    FormatError)
print = MT.printer()  # noqa: A001

GENERATED_RECORD = "mwdialog_generated_files.txt"


def asset_owner_folder(data_dir, rel):
    """(Vortex mod folder, plugin name) for a file in Data Files: the mod folder its hard link comes from
    and the first plugin at that folder's top; (None, None) for a file Vortex didn't deploy."""
    full = os.path.join(data_dir, rel)
    data_abs = os.path.normcase(os.path.abspath(data_dir))
    for other in hard_link_names(full):
        if os.path.normcase(other).startswith(data_abs + os.sep):
            continue
        # walk up from the file to the mod folder: the folder whose part of the path matches rel's start
        parts = rel.replace("/", os.sep).split(os.sep)
        mod = os.path.dirname(other)
        for _ in range(len(parts) - 1):
            mod = os.path.dirname(mod)
        plugin = next((f for f in sorted(os.listdir(mod)) if f.lower().endswith((".esp", ".esm", ".omwaddon"))),
                      None) if os.path.isdir(mod) else None
        return mod, plugin or os.path.basename(mod)
    return None, None


def _sibling(name):
    """A module that sits next to this file, loaded once: the file beside this one, not whatever copy of the
    same name comes first on sys.path."""
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    import importlib
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name + ".py")
    if not os.path.exists(path):
        return importlib.import_module(name)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod                       # before running it: modules it imports may import it by name
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return mod


def _check_module():
    """mwdialog_check, the module mwdialog_assets.py expects as `m` (it holds every name, moved ones too)."""
    return _sibling("mwdialog_check")


def mastercheck_module():
    """mwdialog_mastercheck.py (patches made for a different master than the installed one)."""
    return _sibling("mwdialog_mastercheck")


def longpaths_module():
    """mwdialog_longpaths.py (asset paths too long for Windows / the game's fields)."""
    return _sibling("mwdialog_longpaths")


def asset_health_module():
    """mwdialog_assets.py (texture/model/sound health checks and repairs)."""
    return _sibling("mwdialog_assets")


def sound_names_under(root):
    """"sound/<path>" (lowercase, forward slashes) of every file under the Sound folder `root`, like os.walk +
    relpath gave them, but with one scandir per folder and no per-file path arithmetic: a voice pack can put
    a million or more files there, and every scan of a --full lists them."""
    out = []
    if not os.path.isdir(root):
        return out
    stack = [(root, os.path.basename(os.path.normpath(root)).lower() + "/")]
    while stack:
        path, prefix = stack.pop()
        try:
            it = os.scandir(path)
        except OSError:
            continue
        with it:
            for e in it:
                try:
                    is_dir = e.is_dir()
                except OSError:
                    continue
                if is_dir:
                    if _real_dir(e):
                        stack.append((e.path, prefix + e.name.lower() + "/"))
                else:
                    out.append(prefix + e.name.lower())
    return out


def collect_sound_files(data_dirs, bsa_paths, tree=None):
    SOUND_ROOTS[:] = [d for d in data_dirs if os.path.isdir(d)]
    files = set()
    for d in data_dirs:
        if tree is not None and tree.covers(d):          # the asset pass's one walk of Data Files
            files.update(rel.replace("\\", "/").lower() for top, rel, _f in tree.files if top == "sound")
            continue
        root = os.path.join(d, "Sound")
        if not os.path.isdir(root):
            # case-insensitive match for the Sound folder
            for fn in os.listdir(d) if os.path.isdir(d) else []:
                if fn.lower() == "sound":
                    root = os.path.join(d, fn)
        files.update(sound_names_under(root))
    for b in bsa_paths:
        try:
            files |= bsa_file_names(b)
        except (OSError, struct.error, FormatError) as e:
            print(f"  note: couldn't read {os.path.basename(b)} ({e}); its files count as missing")
    return files


def generated_rels(game_dir):
    """The stand-ins this tool made (GENERATED_RECORD), as cache keys: lowercase paths under Data Files with
    backslashes. They are always checked in full, so a real file put in place of one is noticed."""
    try:
        return {k.replace("/", "\\").lower() for k in read_generated_record(os.path.join(game_dir, GENERATED_RECORD))}
    except (OSError, UnicodeError, ValueError):
        return set()


def _real_dir(e):
    try:
        return e.is_dir() and not e.is_symlink()
    except OSError:
        return False


class DataTree:
    """Every file under one Data Files folder, from a single walk with os.scandir: files is [(top folder
    lowercase - "" for files in Data Files itself -, path relative to Data Files, full path)]. stat() does one
    os.stat per file and keeps it for the pass. (The size and date in Windows' directory listing can be stale
    for a hard link changed through its other name - a mod file vortex_tidy repaired - so stat() never uses
    them.) For the sound and music folders (often a million or more voice files, where one os.stat each takes
    minutes on Windows) the listing's size and date are kept too, as listed_stamp(i): only good enough to
    accept a cached "nothing wrong" result; anything else is checked again with os.stat."""
    LISTED_TOPS = frozenset(("sound", "music"))

    def __init__(self, root):
        from array import array
        self.root = os.path.abspath(root)
        self.files = []
        self._st = {}
        self._lsize = array("q")                    # parallel to files: the listing's size, -1 if not kept
        self._ltime = array("q")                    # and its date (whole seconds)
        try:
            first = sorted(os.scandir(self.root), key=lambda e: e.name.lower())
        except OSError:
            return
        stack = []
        for e in first:
            try:
                is_dir = e.is_dir()
            except OSError:
                continue
            if is_dir:
                if _real_dir(e):
                    stack.append((e.name.lower(), e.path, e.name))
            else:
                self._add_file("", e.name, e)
        stack.reverse()
        while stack:
            top, path, rel = stack.pop()
            try:
                entries = sorted(os.scandir(path), key=lambda e: e.name.lower())
            except OSError:
                continue
            subdirs = []
            for e in entries:
                try:
                    is_dir = e.is_dir()
                except OSError:
                    continue
                if is_dir:
                    if _real_dir(e):
                        subdirs.append((top, e.path, rel + os.sep + e.name))
                else:
                    self._add_file(top, rel + os.sep + e.name, e)
            stack.extend(reversed(subdirs))

    def _add_file(self, top, rel, e):
        self.files.append((top, rel, e.path))
        size = mtime = -1
        if top in self.LISTED_TOPS:
            try:
                st = e.stat()                       # Windows: from the directory listing, no extra call
                size, mtime = st.st_size, int(st.st_mtime)
            except (OSError, OverflowError, ValueError):
                size = mtime = -1
        self._lsize.append(size)
        self._ltime.append(mtime)

    def listed_stamp(self, i):
        """files[i]'s size and date from the directory listing, as the asset cache stamps them ("size:date"),
        or None (not a sound/music file, or not listed)."""
        try:
            size = self._lsize[i]
        except IndexError:
            return None
        return None if size < 0 else f"{size}:{self._ltime[i]}"

    def covers(self, d):
        return os.path.normcase(os.path.abspath(d)) == os.path.normcase(self.root)

    def stat(self, full):
        st = self._st.get(full)
        if st is None:
            st = self._st[full] = os.stat(full)
        return st

    def asset_files(self, tops):
        """(top, rel, full) under these top folders, in that order, skipping Off and .Orphaned folders inside
        them (what the asset checks look at)."""
        for _i, top, rel, full in self.asset_entries(tops):
            yield top, rel, full

    def asset_entries(self, tops):
        """asset_files() with each file's index in files (for listed_stamp)."""
        for want in tops:
            for i, (top, rel, full) in enumerate(self.files):
                if top != want:
                    continue
                parts = rel.lower().split(os.sep)[1:-1]
                if ".orphaned" in parts or "off" in parts:
                    continue
                yield i, top, rel, full


class ModelAssets:
    """The meshes and textures that exist (loose files and BSAs), and which textures a mesh uses.
    Texture names are matched the way TextureAudit does: by path without extension (the game swaps
    in .dds), or by file name alone."""

    FOLDERS = ("meshes", "textures", "icons", "sound", "music", "video", "fonts", "bookart", "splash")

    def __init__(self, data_dirs, bsa_paths, tree=None, cache=None, generated=None):
        self.mesh_loose, self.mesh_bsa = {}, {}
        self.files = defaultdict(set)              # folder -> relative paths (lowercase, backslashes)
        self.stems, self.bases = defaultdict(set), defaultdict(set)   # image folders: names without extension
        self._tex_cache = {}
        self.orphaned = {}                         # (folder, rel) -> path in <folder>\\.Orphaned (TextureAudit)
        self.big_textures = []                     # (full path, rel, bytes): loose .dds over 1 MB, maybe > 2048
        self.tree = tree                           # DataTree of the main Data Files (one walk for the pass)
        self.cache = cache                         # mwdialog_assets' AssetCache: each model's textures
        self.generated = generated or set()        # stand-ins this tool made: never taken from the cache
        self._bsa_facts = {}
        self.bsa_paths = list(bsa_paths)           # registered BSAs, in Morrowind.ini order
        for d in data_dirs:
            if not os.path.isdir(d):
                continue
            if tree is not None and tree.covers(d):
                for top, rel, full in tree.files:
                    if top not in self.FOLDERS:
                        continue
                    parts = rel.split(os.sep)
                    if len(parts) > 2 and parts[1].lower() == ".orphaned":      # the game never looks there
                        orel = "\\".join(parts[2:]).lower()
                        self.orphaned[(top, orel)] = full
                        self.orphaned.setdefault((top, os.path.splitext(orel)[0]), full)
                        continue
                    self._add_loose(top, "\\".join(parts[1:]).lower(), full)
                continue
            tops = {fn.lower(): os.path.join(d, fn) for fn in os.listdir(d)}
            for top in self.FOLDERS:
                root = tops.get(top)
                if not root:
                    continue
                for dirpath, dirs, fns in os.walk(root):
                    if dirpath == root:                # the game never looks in .Orphaned
                        for o in [x for x in dirs if x.lower() == ".orphaned"]:
                            dirs.remove(o)
                            oroot = os.path.join(root, o)
                            for odp, _od, ofns in os.walk(oroot):
                                for ofn in ofns:
                                    full = os.path.join(odp, ofn)
                                    rel = os.path.relpath(full, oroot).replace("/", "\\").lower()
                                    self.orphaned[(top, rel)] = full
                                    self.orphaned.setdefault((top, os.path.splitext(rel)[0]), full)
                    for fn in fns:
                        full = os.path.join(dirpath, fn)
                        self._add_loose(top, os.path.relpath(full, root).replace("/", "\\").lower(), full)
        for b in bsa_paths:
            try:
                for name, where in bsa_index(b).items():
                    top, _, rel = name.partition("\\")
                    if top == "meshes":
                        self.mesh_bsa.setdefault(rel, (b,) + where)
                    if top in self.FOLDERS and rel:
                        self._add(top, rel)
            except (OSError, struct.error, FormatError) as e:
                print(f"  note: couldn't read {os.path.basename(b)} ({e}); its files count as missing")

    def _add_loose(self, top, rel, full):
        if top == "meshes":
            self.mesh_loose.setdefault(rel, full)
        elif top == "textures" and rel.endswith(".dds"):
            try:
                size = self.tree.stat(full).st_size if self.tree is not None else os.path.getsize(full)
            except OSError:
                size = 0
            if size > 1_000_000:           # a DDS over 2048 on an edge is at least ~1.4 MB
                self.big_textures.append((full, rel, size))
        self._add(top, rel)

    def _add(self, top, rel):
        self.files[top].add(rel)
        if top in ("textures", "icons", "bookart", "splash", "sound", "music"):
            stem = os.path.splitext(rel)[0]
            self.stems[top].add(stem)
            self.bases[top].add(os.path.basename(stem))

    @property
    def tex_stems(self):
        return self.stems["textures"]

    @property
    def tex_bases(self):
        return self.bases["textures"]

    @staticmethod
    def rel(path, top):
        p = path.replace("/", "\\").strip().lower().lstrip("\\")
        if p.startswith("data files\\"):
            p = p[11:]
        return p[len(top) + 1:] if p.startswith(top + "\\") else p

    def file_exists(self, kind, path):
        """Does the file a record, script or the ini names exist? Images match without their extension
        (the game swaps in .dds), and so do sounds and music (it plays the .mp3 when a .wav isn't there);
        video and fonts must match exactly."""
        if kind == "mesh":
            return self.mesh_exists(path)
        top = {"icon": "icons", "texture": "textures", "sound": "sound", "music": "music", "video": "video",
               "font": "fonts", "bookart": "bookart"}[kind]
        r = self.rel(path, top)
        if top in ("icons", "textures", "bookart"):
            stem = os.path.splitext(r)[0]
            if stem in self.stems[top] or (top == "textures" and os.path.basename(stem) in self.bases[top]):
                return True
            # book art and icons are sometimes given from Textures
            return top != "textures" and (stem in self.stems["textures"] or os.path.basename(stem) in self.bases["textures"])
        if top in ("sound", "music"):
            return r in self.files[top] or os.path.splitext(r)[0] in self.stems[top]
        return r in self.files[top]

    @staticmethod
    def norm(model):
        m = model.replace("/", "\\").strip().lower().lstrip("\\")
        return m[7:] if m.startswith("meshes\\") else m

    def mesh_exists(self, model):
        m = self.norm(model)
        return m in self.mesh_loose or m in self.mesh_bsa

    def _mesh_bytes(self, m):
        p = self.mesh_loose.get(m)
        if p:
            with open(p, "rb") as f:
                return f.read()
        b = self.mesh_bsa.get(m)
        if b:
            with open(b[0], "rb") as f:
                f.seek(b[1])
                return f.read(b[2])
        return None

    def bsa_facts(self, bsa):
        """{"tn": {model under Meshes: [textures it names]}, "stems": [texture names, for "unused"]} for every
        model in a BSA: read once, then kept in the asset cache while the BSA's size and date are the same."""
        if bsa in self._bsa_facts:
            return self._bsa_facts[bsa]
        key = "bsa2:" + os.path.basename(bsa).lower()
        try:
            st = os.stat(bsa)
            stamp = f"{st.st_size}:{int(st.st_mtime)}"
        except OSError:
            st = stamp = None
        f = self.cache.get(key, stamp) if self.cache is not None and stamp else None
        if f is None:
            ah = asset_health_module()
            tn, stems = {}, set()
            try:
                idx = bsa_index(bsa)
                items = sorted((v[0], v[1], name[7:]) for name, v in idx.items() if name.startswith("meshes\\"))
                print(f"Reading the models in {os.path.basename(bsa)} ({len(items)})...", file=sys.stderr)
                with open(bsa, "rb") as fh:
                    for off, n, rel in items:
                        fh.seek(off)
                        data = fh.read(n)
                        t = nif_texture_refs(data)
                        if t:
                            tn[rel] = t
                        stems.update(x for x, _e in ah.names_by_ext(data, (b"dds", b"tga", b"bmp")))
            except (OSError, struct.error, FormatError) as e:
                print(f"  note: couldn't read the models in {os.path.basename(bsa)} ({e})", file=sys.stderr)
            f = {"tn": tn, "stems": sorted(stems)}
            if self.cache is not None and stamp:
                self.cache.put(key, stamp, f)
        self._bsa_facts[bsa] = f
        return f

    def texture_names(self, m):
        """The textures model m (under Meshes, lowercase) names: from the asset cache (or vortex_tidy's record
        of the same file) when the file is unchanged, else read from the model."""
        p = self.mesh_loose.get(m)
        if p:
            if self.cache is not None and self.tree is not None \
                    and os.path.normcase(p).startswith(os.path.normcase(self.tree.root) + os.sep):
                ah = asset_health_module()
                try:
                    st = self.tree.stat(p)
                except OSError:
                    return []
                f = ah.model_facts_cached(self.cache, ah.norm_rel(os.path.relpath(p, self.tree.root)), p, st,
                                          _check_module(), self.generated, need_tn=True)
                return (f or {}).get("tn", [])
            try:
                with open(p, "rb") as fh:
                    return nif_texture_refs(fh.read())
            except OSError:
                return []
        b = self.mesh_bsa.get(m)
        if b:
            return self.bsa_facts(b[0])["tn"].get(m, [])
        return []

    def missing_textures(self, model):
        """Textures the mesh names that exist nowhere (cached per mesh)."""
        m = self.norm(model)
        if m in self._tex_cache:
            return self._tex_cache[m]
        out = []
        for s in self.texture_names(m):
            stem = os.path.splitext(s)[0]
            if stem not in self.tex_stems and os.path.basename(stem) not in self.tex_bases:
                if IGNORED_MAP_RE.search(os.path.basename(stem)):
                    # a normal map: the game still loads every texture a model names (a missing one is a
                    # "tex not found" warning, and MGE XE's per-pixel lighting may use it), so it gets the
                    # usual stand-in (a flat normal map); also listed
                    self.__dict__.setdefault("ignored_normals", set()).add((model, s))
                out.append(s)                      # path under Textures, as the model names it
        self._tex_cache[m] = out
        return out

    KIND_NAMES = {"mesh": "model", "icon": "icon", "texture": "texture", "sound": "sound file",
                  "music": "music file", "video": "video", "font": "font", "bookart": "book picture"}

    def find_orphaned(self, top, rel, any_ext=False):
        """A needed file that TextureAudit's orphan isolator moved to <folder>\\.Orphaned, or None."""
        rel = rel.replace("/", "\\").lower().strip("\\")
        return self.orphaned.get((top, rel)) or (self.orphaned.get((top, os.path.splitext(rel)[0])) if any_ext else None)

    @staticmethod
    def placeholder(path):
        """The Construction Set's 'Add World Art' / 'Add Art File' text: no file was ever chosen."""
        p = path.strip()
        return not os.path.splitext(p)[1] and p.lower().startswith("add ")

    def field_problem(self, kind, path):
        if self.placeholder(path):
            return f"{self.KIND_NAMES[kind]} not set (still the editor's placeholder '{path.strip()}')"
        if kind == "icon" and path.strip().lower().endswith(".nif"):
            return f"icon is a model file ('{path.strip()}' was put in the icon field)"
        if kind == "mesh":
            return self.problem(path)
        if not path.strip() or self.file_exists(kind, path):
            return None
        return f"{self.KIND_NAMES[kind]} '{path}' doesn't exist"

    @staticmethod
    def fatal(prob):
        """Problems the game trips over (a file it can't load), as opposed to a model with missing textures."""
        return bool(prob) and ("doesn't exist" in prob or "not set" in prob or "icon is a model" in prob
                               or "isn't a real model" in prob)

    def nif_ok(self, model):
        """False when the file named as a model isn't a NIF at all (a renamed text file, an empty
        'dummy.nif'): the game can't load it and the object doesn't appear."""
        m = self.norm(model)
        cache = self.__dict__.setdefault("_nif_ok", {})
        if m not in cache:
            head = b""
            p = self.mesh_loose.get(m)
            try:
                if p:
                    with open(p, "rb") as f:
                        head = f.read(32)
                elif self.mesh_bsa.get(m):
                    b = self.mesh_bsa[m]
                    with open(b[0], "rb") as f:
                        f.seek(b[1])
                        head = f.read(min(32, b[2]))
            except OSError:
                head = b""
            cache[m] = head.startswith((b"NetImmerse File Format", b"Gamebryo File Format")) or not head and not p
        return cache[m]

    def problem(self, model):
        """None if the model shows in game, else what is wrong with it."""
        if not model.strip():
            return None
        if not self.mesh_exists(model):
            return f"model '{model}' doesn't exist"
        if not self.nif_ok(model):
            return f"model '{model}' isn't a real model file (not a NIF), so the game can't load it"
        miss = sorted({os.path.basename(t) for t in self.missing_textures(model)})
        if miss:
            return f"model '{model}' uses missing texture(s) {', '.join(miss[:3])}" + \
                   (f" (+{len(miss) - 3})" if len(miss) > 3 else "")
        return None


class VortexRepo:
    """Files in the Vortex mod staging folder (every mod's own folder, including Extras/ and optional
    folders that were never deployed), to find assets that exist there but not in Data Files."""
    EXTS = {".nif", ".dds", ".tga", ".bmp", ".wav", ".mp3", ".fnt", ".bik", ".kf"}

    def __init__(self, root):
        self.root = root
        self._by_name = None

    def _index(self):
        self._by_name = defaultdict(list)
        try:
            mods = [os.path.join(self.root, d) for d in os.listdir(self.root) if os.path.isdir(os.path.join(self.root, d))]
        except OSError:
            mods = []
        print(f"Searching {len(mods)} Vortex mod folders for missing files...", file=sys.stderr)
        for mod in mods:
            for dirpath, _dirs, fns in os.walk(mod):
                for fn in fns:
                    stem, ext = os.path.splitext(fn.lower())
                    if ext in self.EXTS:
                        self._by_name[stem].append(os.path.join(dirpath, fn))

    SAME_KIND = {t: (".dds", ".tga", ".bmp") for t in ("icons", "textures", "bookart", "splash")}
    SAME_KIND.update({"sound": (".wav", ".mp3"), "music": (".mp3", ".wav"), "video": (".bik",)})

    def find(self, top, rel, any_ext=False):
        """(full path, mod folder name) of a file that would sit at Data Files\\<top>\\<rel>, or None.
        Only a path ending in the same folders counts; images and sounds may differ in extension."""
        if self._by_name is None:
            self._index()
        rel = rel.replace("/", "\\").lower().strip("\\")
        stem, ext = os.path.splitext(rel)
        # a normal map vortex_tidy put in a mod's Off\ folder (Off\normal maps\...) was taken out on
        # purpose: it never comes back as "the real file"; the flat stand-in is used instead
        normal_map = bool(IGNORED_MAP_RE.search(os.path.basename(stem)))
        best = None
        for full in self._by_name.get(os.path.basename(stem), ()):
            low = full.replace("/", "\\").lower()
            if normal_map and "\\off\\" in "\\" + os.path.relpath(full, self.root).replace("/", "\\").lower():
                continue
            fstem, fext = os.path.splitext(low)
            # "any extension" means another of the same kind (an icon .dds for a .tga), never a model
            # standing in for an icon because their names match
            if not (fext == ext or (any_ext and fext in self.SAME_KIND.get(top, (ext,)))):
                continue
            if fstem.endswith("\\" + top + "\\" + stem):
                score = 0
            elif fstem.endswith("\\" + stem) and "\\" in stem:
                score = 1
            else:
                continue
            if best is None or (score, len(low)) < best[0]:
                best = ((score, len(low)), full)
        if not best:
            return None
        full = best[1]
        mod = os.path.relpath(full, self.root).split(os.sep)[0]
        return full, mod


def hard_link_names(path):
    """Every other path of a hard-linked file (Windows), e.g. its copy in Vortex's staging folder."""
    if os.name != "nt":
        return []
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.FindFirstFileNameW.restype = wintypes.HANDLE
    k32.FindFirstFileNameW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR]
    k32.FindNextFileNameW.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR]
    k32.FindClose.argtypes = [wintypes.HANDLE]
    buf = ctypes.create_unicode_buffer(1024)
    n = wintypes.DWORD(1024)
    h = k32.FindFirstFileNameW(os.path.abspath(path), 0, ctypes.byref(n), buf)
    if h in (None, wintypes.HANDLE(-1).value):
        return []
    names = [buf.value]
    while True:
        n = wintypes.DWORD(1024)
        if not k32.FindNextFileNameW(h, ctypes.byref(n), buf):
            break
        names.append(buf.value)
    k32.FindClose(h)
    drive = os.path.splitdrive(os.path.abspath(path))[0]
    here = os.path.normcase(os.path.abspath(path))
    return [drive + nm for nm in names if os.path.normcase(drive + nm) != here]


IGNORED_MAP_RE = re.compile(r"_(n|nm|normal|nrm)$", re.I)      # texture stems that are normal maps
