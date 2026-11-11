"""Asset health for mwdialog_check --asset-check (reports) and --fix (repairs). Loose files in Data Files only
(BSA contents can't be changed; their models are read for texture references).

Checks, and what --fix does:
  DDS a DirectX 8 game can't read (DX10/BC7 header) ...... ERROR  converted to DXT (texconv)
  DDS shorter than its header says (truncated) ........... ERROR  report only (reinstall the mod)
  DDS without mipmaps (64 px and up) ..................... WARN   mipmaps generated (texconv)
  DDS uncompressed 32-bit (256 px and up) ................ WARN   compressed to DXT1/DXT5 (texconv)
  DDS not a power of two / DXT not a multiple of 4 ....... WARN   resized to the nearest power of two (texconv)
  NIF/KF that isn't a Morrowind file (not 4.0.0.2) ....... ERROR  report only
  absolute texture path inside a NIF (C:\\...) ............ ERROR  rewritten to a normal relative path
  empty (0-byte) asset ................................... ERROR  moved to Off when a BSA has the real file
  file name with non-ASCII characters .................... ERROR  report only (plugins/models name it)
  stereo sound under Sound\\ (3D sounds must be mono) ..... WARN   down-mixed to mono (ffmpeg)
  sound at an unusual sample rate (or over 48 kHz) ....... WARN   resampled to 44.1 kHz (ffmpeg)
  x*.kf animation without its x*.nif ..................... WARN   report only
  texture or sound nothing refers to ..................... INFO   moved to the mod's Off\\unused\\ (not deployed)
Originals of changed files go to <mod>\\Off\\<plugin>\\<path> (backup_asset_original). Unused files are moved
(not copied) and listed in mwdialog_unused_assets.txt, which --restore-unused uses to put them back.
Not checked: mesh vertex counts (the 4.0.0.2 format can't exceed 65535) and folder-name case duplicates
(the same folder on Windows)."""
import os, re, struct, shutil, subprocess, sys, time

TEX_DIRS = ("textures", "icons", "bookart", "splash")
SOUND_DIRS = ("sound", "music")
ASSET_DIRS = ("meshes",) + TEX_DIRS + SOUND_DIRS + ("video", "fonts")
NIF_HEAD = b"NetImmerse File Format, Version 4.0.0.2"
UNUSED_RECORD = "mwdialog_unused_assets.txt"
STD_RATES = {11025, 22050, 44100, 48000}
# textures the engine, MGE XE or MWSE load by name, never named by a plugin or model
IMPLICIT_TEX = re.compile(r"^(menu_|tx_menu|cursor|levelup|scroll|tx_scroll|tx_sky|sky_|tx_water|water|"
                          r"tx_moon|tx_sun|tx_cursor|target|compass|tx_compass|black|white|"
                          r"tx_b_|tx_a_|tx_w_|tx_s_|tx_h_|tx_i_|tx_ic|tx_glow|vfx_|tx_bm_|tx_rain|tx_snow|"
                          r"tx_ash|tx_blight|tx_raindrop|ripple|caustic|fog|noise)", re.I)
MAP_SUFFIX = re.compile(r"_(n|nm|nh|h|spec|s|gloss|g|ao|em|e|r|m|param|disp|d|emissive|glow)$", re.I)
REF_TEXT_EXT = (".lua", ".json", ".ini", ".txt", ".fx", ".fxh", ".hlsl", ".toml", ".cfg", ".xml", ".html",
                ".htm", ".css", ".mwscript")


NOT_EMPTY_TAGS = (b"NiKeyframeController", b"NiKeyframeData", b"NiTextKeyExtraData", b"NiPointLight",
                  b"NiSpotLight", b"NiAmbientLight", b"NiDirectionalLight", b"NiCamera", b"NiBSAnimationNode",
                  b"NiBSParticleNode", b"NiVisController", b"NiPathController",
                  b"Bip01")                  # a skeleton: the body parts are put on it in the game
SHAPE_TAGS = (b"NiTriShape", b"NiTriStrips", b"NiParticle", b"NiAutoNormalParticles", b"NiRotatingParticles",
              b"NiLines", b"NiSkinInstance")


def nif_without_shapes(data):
    """True for a model with nothing to draw (no shapes, particles or lines): an invisible object. Some mods
    use these on purpose (hiding an object); it's only worth a warning."""
    if len(data) < 512:
        return False                      # a lone empty node: made empty on purpose (a body-part creature's
                                          # base, an attach point, a hidden object)
    return data.startswith(NIF_HEAD) and not any(t in data for t in SHAPE_TAGS + NOT_EMPTY_TAGS)


CACHE_FILE = "mwdialog_asset_cache.json"           # the old format: converted once, then renamed
CACHE_DB = "mwdialog_asset_cache.sqlite"
MIGRATED_SUFFIX = ".migrated"
# what vortex_tidy found in each mod: tidy3:<mod folder>|<path in the mod>; raise the number when a check is
# added or made stricter, and every file is looked at again once
TIDY_KEY = "tidy3:"
KNOWN_PREFIXES = {"clean2", "seen2", "clean", "seen", "texh", "tex2", "nif", "bsa", "bsa2", "snd", "refs", "names",
                  "fixed", "tidy3"}
# tidy's "found clean" entries carry the version of the checks: raise it when a check is added or made
# stricter, and every file is looked at again once
# the old cache's tidy entries (per path, not per mod): dropped when it is converted
CLEAN_KEY = "clean2:"
SEEN_KEY = "seen2:"
EXT_RE = re.compile(rb"\.(dds|tga|bmp|wav|mp3)(?![A-Za-z0-9_])", re.I)
NAME_CHARS = set(range(0x21, 0x7f)) | {0x20}


def names_by_ext(b, exts=(b"dds", b"tga", b"bmp", b"wav", b"mp3")):
    """[(stem lower, ext lower)] of file names ending in one of exts: finds the extension first, then reads
    the name backwards (fast on any input, unlike a regex that scans for the name's start)."""
    out = []
    for mm in EXT_RE.finditer(b):
        ext = mm.group(1).lower()
        if ext not in exts:
            continue
        i = mm.start()
        j = i
        while j > 0 and i - j < 250 and b[j - 1] in NAME_CHARS:
            j -= 1
        name = b[j:i].replace(b"/", b"\\").rsplit(b"\\", 1)[-1].strip().lower()
        if name:
            out.append((name.decode("latin1"), ext.decode()))
            for sep in (b" ", b"\t", b"\"", b"'", b"=", b",", b";", b"(", b"[",   # also the last word alone
                        b".dds", b".tga", b".bmp", b".wav", b".mp3"):
                if sep in name:
                    tail = name.rsplit(sep, 1)[-1].strip()
                    if tail:
                        out.append((tail.decode("latin1"), ext.decode()))
    return out


class AssetCache:
    """Per-file results of the asset checks, keyed by path + size + date, so the next run only reads new or
    changed files. Kept in mwdialog_asset_cache.sqlite next to Morrowind.ini: read once when a run starts,
    and written as the run goes (a few hundred entries per transaction), so a run that is stopped or
    crashes keeps everything up to its last batch, and the file is never left half-written (SQLite
    commits each batch whole or not at all). The old mwdialog_asset_cache.json (and its .add file) is
    converted the first time and kept as mwdialog_asset_cache.json.migrated."""
    BATCH = 500

    def __init__(self, game_dir):
        self.game_dir = game_dir
        self.path = os.path.join(game_dir, CACHE_DB)
        self.d = {}                  # key -> [stamp, result as JSON text]
        self._dec = {}               # key -> result, decoded on first use
        self._dirty = {}             # key -> (stamp, text), or None for a deleted key, not yet written
        self.touched = set()         # keys read or written by this run (the rest may be pruned)
        self._tidx = None            # rel -> [tidy keys], built when first needed
        self.db = None
        self._warned = False
        try:
            self._open()
        except Exception as e:                     # a damaged file: keep it aside and start a new one
            print(f"(asset cache {CACHE_DB} could not be read ({e}); starting a new one, the old file is "
                  f"kept as {CACHE_DB}.bad)", file=sys.stderr)
            self._close_quietly()
            self.d.clear()
            try:
                os.replace(self.path, self.path + ".bad")
            except OSError:
                pass
            try:
                self._open()
            except Exception:
                self._close_quietly()              # no cache file this run: everything is read again

    def _open(self):
        import sqlite3
        self.db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS c (k TEXT PRIMARY KEY, s TEXT NOT NULL, r TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
        for k, s, r in self.db.execute("SELECT k, s, r FROM c"):
            self.d[k] = [s, r]
        self._migrate()

    def _close_quietly(self):
        try:
            if self.db is not None:
                self.db.close()
        except Exception:
            pass
        self.db = None

    def _migrate(self):
        """The old JSON cache, once: its entries are converted, then the file is renamed .json.migrated."""
        import json
        old = os.path.join(self.game_dir, CACHE_FILE)
        if not os.path.exists(old):
            return
        done = self.db.execute("SELECT v FROM meta WHERE k='migrated'").fetchone()
        if not done:
            t0 = time.time()
            try:
                mb = os.path.getsize(old) / 1048576
            except OSError:
                mb = 0
            print(f"Asset cache: converting {CACHE_FILE} ({mb:.0f} MB) to {CACHE_DB}, once...", file=sys.stderr,
                  flush=True)
            d = {}
            try:
                with open(old, encoding="utf-8") as f:
                    d = json.load(f)
            except (OSError, ValueError, MemoryError) as e:
                print(f"  (could not read it: {e}; starting with an empty cache)", file=sys.stderr)
                d = {}
            try:
                with open(old + ".add", encoding="utf-8") as f:
                    for line in f:
                        try:
                            k, v = json.loads(line)
                            d[k] = v
                        except (ValueError, TypeError):
                            pass
            except OSError:
                pass
            rows = []
            own = os.path.normcase(os.path.abspath(self.game_dir))
            for k, v in d.items():
                if not isinstance(v, dict) or "s" not in v or "r" not in v:
                    continue
                k2 = migrate_key(k, own)
                if k2 is None:
                    continue
                rows.append((k2, str(v["s"]), json.dumps(v["r"], separators=(",", ":"))))
            del d
            self.db.execute("BEGIN")
            self.db.executemany("INSERT OR REPLACE INTO c VALUES (?, ?, ?)", rows)
            self.db.execute("INSERT OR REPLACE INTO meta VALUES ('migrated', ?)", (time.strftime("%Y-%m-%d %H:%M"),))
            self.db.execute("COMMIT")
            for k, s, r in rows:
                self.d[k] = [s, r]
            print(f"Asset cache: {len(rows):,} entries kept, in {time.time() - t0:.0f}s; the old file is now "
                  f"{CACHE_FILE}{MIGRATED_SUFFIX} (delete it when you like)", file=sys.stderr, flush=True)
        for src in (old, old + ".add"):
            try:
                if os.path.exists(src):
                    os.replace(src, src + MIGRATED_SUFFIX)
            except OSError as e:
                print(f"  (could not rename {os.path.basename(src)}: {e})", file=sys.stderr)

    # --- entries
    def get(self, key, stamp):
        v = self.d.get(key)
        if v is None or v[0] != stamp:
            return None
        self.touched.add(key)
        r = self._dec.get(key, _MISSING)
        if r is _MISSING:
            import json
            r = self._dec[key] = json.loads(v[1])
        return r

    def has(self, key):
        return key in self.d

    def touch(self, key):
        if key in self.d:
            self.touched.add(key)

    def put(self, key, stamp, result):
        import json
        t = json.dumps(result, separators=(",", ":"))
        self.touched.add(key)
        v = self.d.get(key)
        if v is not None and v[0] == stamp and v[1] == t:
            return
        self.d[key] = [stamp, t]
        self._dec[key] = result
        self._dirty[key] = (stamp, t)
        if key.startswith(TIDY_KEY):
            self._tidx = None
        if len(self._dirty) >= self.BATCH:
            self.flush()

    def delete(self, key):
        if self.d.pop(key, None) is not None:
            self._dec.pop(key, None)
            self._dirty[key] = None
            if key.startswith(TIDY_KEY):
                self._tidx = None

    def prune(self, prefixes, keep=None):
        """Delete the entries under these key prefixes that this run neither read nor wrote (their files are
        gone or renamed), except those keep(key) says to keep. Returns how many went."""
        gone = [k for k in self.d if k.startswith(prefixes) and k not in self.touched and not (keep and keep(k))]
        for k in gone:
            self.delete(k)
        return len(gone)

    # --- what vortex_tidy found in each mod (keys tidy3:<mod folder>|<path>)
    def tidy_lookup(self, rel_key, stamp):
        """tidy's record of a mod file at this Data Files path with the same size and date (the same file: a
        Vortex hard link, or a copy that kept its date), or None."""
        if self._tidx is None:
            self._tidx = {}
            for k in self.d:
                if k.startswith(TIDY_KEY):
                    self._tidx.setdefault(k.split("|", 1)[-1], []).append(k)
        for k in self._tidx.get(rel_key, ()):
            r = self.get(k, stamp)
            if r is not None:
                return r
        return None

    # --- writing
    def flush(self):
        """Write what changed since the last call, in one transaction. Never raises."""
        if not self._dirty or self.db is None:
            return True
        items = list(self._dirty.items())
        try:
            self.db.execute("BEGIN")
            self.db.executemany("INSERT OR REPLACE INTO c VALUES (?, ?, ?)",
                                [(k, v[0], v[1]) for k, v in items if v is not None])
            self.db.executemany("DELETE FROM c WHERE k = ?", [(k,) for k, v in items if v is None])
            self.db.execute("COMMIT")
        except Exception as e:
            try:
                self.db.execute("ROLLBACK")
            except Exception:
                pass
            if not self._warned:
                self._warned = True
                print(f"(could not write the asset cache {CACHE_DB}: {e}; the next run reads those files again)",
                      file=sys.stderr)
            return False
        for k, _v in items:
            if self._dirty.get(k) is _v:
                del self._dirty[k]
        return True

    def save(self, force=False):
        """Write what changed (kept for older callers; the cache is also written as the run goes)."""
        return self.flush()

    def close(self):
        """Write what is left and close; when pruning freed a quarter of the file or more, compact it."""
        self.flush()
        if self.db is not None:
            try:
                free = self.db.execute("PRAGMA freelist_count").fetchone()[0]
                pages = self.db.execute("PRAGMA page_count").fetchone()[0]
                if free > 256 and free * 4 > pages:
                    self.db.execute("VACUUM")
            except Exception:
                pass
        self._close_quietly()


_MISSING = object()


def migrate_key(k, game_dir_nc):
    """The new key for an entry of the old JSON cache, or None to drop it: models get the nif: prefix, paths
    use backslashes; tidy's rel-only clean2:/seen2: entries (now kept per mod), the BSA name lists (now with
    each model's textures) and the word lists of this tool's own files are dropped."""
    pre, sep, rest = k.partition(":")
    if not sep or pre not in KNOWN_PREFIXES:          # a model's facts (no prefix in the old file)
        return "nif:" + norm_rel(k)
    if pre in ("clean2", "seen2", "bsa", "clean", "seen"):
        return None
    if pre in ("texh", "snd"):
        return pre + ":" + norm_rel(rest)
    if pre in ("refs", "names"):
        p = os.path.normcase(os.path.abspath(rest)).lower()
        if os.path.dirname(p) == game_dir_nc.lower():   # a file in the Morrowind folder itself: one of ours
            return None
        return pre + ":" + rest.lower()
    return k


def norm_rel(rel):
    """A path under Data Files (or a mod folder) as the cache keys it: lowercase, backslashes."""
    return rel.replace("/", "\\").lower()


def stamp_of(st):
    return f"{st.st_size}:{int(st.st_mtime)}"


_CACHES = {}


def shared_cache(game_dir):
    """One AssetCache per game folder for the whole run: read once, not once per mod."""
    key = os.path.normcase(os.path.abspath(game_dir))
    if key not in _CACHES:
        _CACHES[key] = AssetCache(game_dir)
        import atexit
        atexit.register(lambda c=_CACHES[key]: c.close())
    return _CACHES[key]


def close_caches():
    """Write and close every open cache (tests; a long-running caller)."""
    for c in list(_CACHES.values()):
        c.close()
    _CACHES.clear()


def model_facts(b, m):
    """What the checks need from one model file, small enough to cache. "tn": the textures it names (paths
    under Textures, for the missing-texture check); "tex": their names alone (for "unused")."""
    if not b.startswith(NIF_HEAD):
        return {"bad": b[:40].split(b"\n")[0].decode("latin1", "replace"), "tn": []}
    bad_keys = m.nif_text_keys_lf(b)[0] if m.TEXT_KEY_TAG in b else 0
    return {"tex": sorted({n for n, e in names_by_ext(b, (b"dds", b"tga", b"bmp"))}),
            "abs": bool(nif_absolute_textures(b)), "noshape": nif_without_shapes(b), "keys": bad_keys,
            "tn": m.nif_texture_refs(b)}


def model_facts_cached(cache, key, full, st, m, generated=(), need_tn=False):
    """model_facts for the model at Data Files path `key` (norm_rel) with os.stat `st`: vortex_tidy's record of
    the same file (same size and date: a Vortex hard link) or this cache's when it is unchanged, else read.
    A stand-in this tool made is always read. need_tn: an entry from the old cache, without the texture
    paths, is read again. None if the file can't be read."""
    stamp = stamp_of(st)
    if key not in generated and cache is not None:
        t = cache.tidy_lookup(key, stamp)
        if t is not None and isinstance(t.get("f"), dict) and "tn" in t["f"]:
            return t["f"]
        f = cache.get("nif:" + key, stamp)
        # an old entry without "tn" whose noshape came from an older, stricter test: read it again
        if f is not None and ("tn" in f or not (need_tn or f.get("noshape"))):
            return f
    try:
        with open(full, "rb") as fh:
            f = model_facts(fh.read(), m)
    except OSError:
        return None
    if cache is not None and key not in generated:
        cache.put("nif:" + key, stamp, f)
    return f


def texture_facts(head, m):
    """What the texture checks need from a DDS's first 148 bytes: ["bad"] (not a DDS), ["dx10", alpha],
    ["?"] (a DDS this can't judge) or ["dds", [w, h, mips, header, block, bpp], alpha flag]."""
    if head[:4] != b"DDS ":
        return ["bad"]
    if head[84:88] == b"DX10":
        return ["dx10", bool(dx10_has_alpha(head))]
    info = m.dds_info(head)
    if info is None:
        return ["?"]
    return ["dds", list(info), struct.unpack_from("<I", head, 80)[0] & 0x1 if len(head) >= 84 else 0]


def prune_tidy(cache, checked, present=None):
    """After vortex_tidy's asset check: drop the records of files a checked mod no longer has, and (present:
    every mod folder in staging, when all were checked) of mods that are gone."""
    def keep(k):
        mod = k[len(TIDY_KEY):].split("|", 1)[0]
        if mod in checked:
            return False                        # checked now: untouched means the file is gone
        return present is None or mod in present
    return cache.prune((TIDY_KEY,), keep)


def kf_model_name(rel):
    """The model an x*.kf animates: the .nif of the same name next to it."""
    return rel[:-3] + ".nif"


FEATURE_OF = {"snd": "sound", "tex": "textures", "keys": "text keys", "abs": "texture paths",
              "broken": "broken", "orphan": "orphaned", "unused": "unused"}


def broken_dest(root_or_mod, rel, sub="broken", plugin=None):
    """<mod>\\Off\\<sub: broken, orphaned...>\\<plugin name>\\<rel>."""
    import mwdialog_check as _m
    return _m.off_dest(root_or_mod, sub, plugin, rel)


UI_TEX_RE = re.compile(r"^(?:data files[\\/])?(?:textures[\\/](?:menu_|tx_menu|tx_cursor|compass|target|scroll|"
                       r"(?:bookart|splash|levelup|birthsigns?|mwse|ui|menu)[\\/])|icons[\\/]|bookart[\\/]|splash[\\/])",
                       re.I)


def ui_texture(rel):
    """A menu / book / splash / icon picture: drawn at its own size on screen, so it keeps its size, its
    pixels (no compression) and needs no mipmaps; only the over-2048 limit applies."""
    return bool(UI_TEX_RE.search(rel.replace("/", "\\")))


def _pow2(n):
    p = 1
    while p * 2 <= n:
        p *= 2
    return p * 2 if n - p > p // 2 else p


def _walk(data_dir, tops):
    try:
        names = {fn.lower(): fn for fn in os.listdir(data_dir)}
    except OSError:
        return
    for top in tops:
        fn = names.get(top)
        if not fn:
            continue
        root = os.path.join(data_dir, fn)
        for dp, ds, fs in os.walk(root):
            ds[:] = [d for d in ds if d.lower() not in (".orphaned", "off")]
            for f in fs:
                full = os.path.join(dp, f)
                yield top, os.path.relpath(full, data_dir), full


def _wav_info(b):
    if b[:4] != b"RIFF" or b[8:12] != b"WAVE":
        return None
    p = 12
    while p + 8 <= len(b):
        cid, sz = b[p:p + 4], struct.unpack_from("<I", b, p + 4)[0]
        if cid == b"fmt " and p + 24 <= len(b):
            fmt, ch, rate = struct.unpack_from("<HHI", b, p + 8)
            return ch, rate
        p += 8 + sz + (sz & 1)
    return None


def _mp3_info(b, first_frame):
    j = first_frame(b)
    if j is None:
        return None
    ver, sri, mode = (b[j + 1] >> 3) & 3, (b[j + 2] >> 2) & 3, b[j + 3] >> 6
    rate = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}[ver][sri]
    return (1 if mode == 3 else 2), rate


ABS_TEX = re.compile(rb"[A-Za-z]:[\\/][\x20-\x7e]{1,250}?\.(?:dds|tga|bmp)", re.I)


def nif_absolute_textures(data):
    """[(offset of the length field, old path)] for length-prefixed texture paths that start with a drive."""
    out = []
    for m in ABS_TEX.finditer(data):
        s = m.start()
        if s >= 4 and struct.unpack_from("<I", data, s - 4)[0] == m.end() - s:
            out.append((s - 4, m.group(0)))
    return out


def relative_texture(path):
    p = path.replace(b"/", b"\\")
    low = p.lower()
    i = low.rfind(b"\\textures\\")
    return p[i + 10:] if i >= 0 else p.rsplit(b"\\", 1)[-1]


def rewrite_absolute(data):
    hits = nif_absolute_textures(data)
    if not hits:
        return 0, None
    out, last = [], 0
    for at, old in hits:
        new = relative_texture(old)
        out.append(data[last:at])
        out.append(struct.pack("<I", len(new)) + new)
        last = at + 4 + len(old)
    out.append(data[last:])
    return len(hits), b"".join(out)


def sound_job(top, info):
    """What --fix would do to a sound with header info (channels, rate): {} when nothing."""
    ch, rate = info
    job = {}
    if top == "sound" and ch > 1:
        job["mono"] = True
    if rate not in STD_RATES:
        job["rate"] = 44100
    return job


def check(world, m):
    """Runs the checks for World `world` (module `m` = mwdialog_check). Stores world.asset_health (fix list)."""
    import builtins, time as _time
    _t0 = _time.time()

    def print(*a, **k):                            # every status line says how long the check has run
        if k.get("file") is sys.stderr and a:
            a = (f"[{int(_time.time() - _t0)}s] {a[0]}",) + a[1:]
            k["flush"] = True
        builtins.print(*a, **k)
    A = world.assets
    data_dir = os.path.abspath(world.args_data_dir)
    r = world.r
    fixes = []                       # (kind, full, rel, detail)
    print("Asset health: reading textures, models, sounds...", file=sys.stderr)
    tex_files, snd_files, nif_files, kf_files = [], [], [], []
    tree = getattr(world, "tree", None)
    if tree is None or not tree.covers(data_dir):
        tree = m.DataTree(data_dir)
    stats = {}                                   # full path -> os.stat: one per file for the whole pass
    listed = getattr(tree, "listed_stamp", None)
    entries = tree.asset_entries(ASSET_DIRS) if listed else ((None,) + t for t in tree.asset_files(ASSET_DIRS))
    for i, top, rel, full in entries:
        low = rel.lower()
        # sounds and music: the directory listing's size and date first (a voice pack can have a million
        # files, and an os.stat each takes minutes); the sound check below calls os.stat only when the
        # cache has no "nothing wrong" entry for that stamp. An empty file is always confirmed by os.stat.
        ls = listed(i) if listed and top in SOUND_DIRS and low.endswith((".wav", ".mp3")) else None
        if ls is not None and not ls.startswith("0:"):
            if any(ord(c) > 127 for c in rel):
                r.add("ERROR", "Data Files", "", "", f"{rel}: the file name has non-ASCII characters; the game "
                                                     f"can't open it (rename it, and the plugin/model that names it)")
            snd_files.append((top, rel, full, ls))
            continue
        try:
            st = stats[full] = tree.stat(full)
        except OSError:
            continue
        size = st.st_size
        if any(ord(c) > 127 for c in rel):
            r.add("ERROR", "Data Files", "", "", f"{rel}: the file name has non-ASCII characters; the game can't "
                                                 f"open it (rename it, and the plugin/model that names it)")
        if size == 0:
            in_bsa = low[len("meshes\\"):] in A.mesh_bsa if low.startswith("meshes\\") else False
            r.add("ERROR", "Data Files", "", "", f"{rel}: empty file (0 bytes)"
                  + ("; a BSA has the real one, --fix moves the empty one to Off" if in_bsa else
                     "; --fix moves it to Off\\...\\broken\\ and puts a stand-in in its place"))
            fixes.append(("unused", full, rel, "empty, the BSA copy is used instead") if in_bsa else
                         ("broken", full, rel, "empty file"))
            continue
        if top in TEX_DIRS and low.endswith(".dds"):
            tex_files.append((rel, full, size))
        elif top in SOUND_DIRS and low.endswith((".wav", ".mp3")):
            snd_files.append((top, rel, full, None))
        elif top == "meshes" and low.endswith(".nif"):
            nif_files.append((rel, full))
        elif top == "meshes" and low.endswith(".kf"):
            kf_files.append((rel, full))
    cache = shared_cache(os.path.dirname(data_dir))
    generated = m.generated_rels(os.path.dirname(data_dir))
    # a file vortex_tidy checked in its mod (the same file: a Vortex hard link, or a copy with the same size
    # and date) gets the light check only (name, empty file); the stand-ins this tool made always the full one
    def tidy_clean(rel, full):
        key = norm_rel(rel)
        if key in generated or full not in stats:
            return False
        return cache.tidy_lookup(key, stamp_of(stats[full])) is not None
    # --- textures
    print(f"Asset health: textures ({len(tex_files)})...", file=sys.stderr)
    for k, (rel, full, size) in enumerate(tex_files, 1):
        if k % 2000 == 0:
            print(f"Asset health: textures {k}/{len(tex_files)}...", file=sys.stderr)
        if tidy_clean(rel, full):
            continue
        key = norm_rel(rel)
        gen = key in generated
        stamp = stamp_of(stats[full])
        tf = None if gen else cache.get("tex2:" + key, stamp)
        if tf is None:
            hx = None if gen else cache.get("texh:" + key, stamp)      # the old cache's header: converted
            if hx is not None:
                head = bytes.fromhex(hx)
            else:
                try:
                    with open(full, "rb") as f:
                        head = f.read(148)
                except OSError:
                    continue
            tf = texture_facts(head, m)
            cache.delete("texh:" + key)
            if not gen:
                cache.put("tex2:" + key, stamp, tf)
        if tf[0] == "bad":
            r.add("ERROR", "Data Files", "", "", f"{rel}: not a DDS file (renamed?); the game can't load it. "
                                                 f"--fix moves it to Off\\...\\broken\\, a placeholder replaces it")
            fixes.append(("broken", full, rel, "not a DDS file"))
            continue
        if tf[0] == "dx10":
            r.add("ERROR", "Data Files", "", "", f"{rel}: DX10/BC7-style DDS; Morrowind (DirectX 8) can't read it. "
                                                 f"--fix converts it to DXT")
            fixes.append(("tex", full, rel, {"dxt": True, "mips": True, "alpha": tf[1]}))
            continue
        if tf[0] != "dds":
            continue
        w, h, mips, hdr, block, bpp = tf[1]
        need = hdr
        lw, lh = w, h
        for _ in range(mips):
            need += m.dds_level_size(lw, lh, block, bpp)
            lw, lh = max(1, lw // 2), max(1, lh // 2)
        if size < need:
            r.add("ERROR", "Data Files", "", "", f"{rel}: truncated ({size} of {need} bytes); can crash the game "
                                                 f"when it loads. --fix moves it to Off\\...\\broken\\ and puts a "
                                                 f"placeholder in its place (reinstall the mod for the real one)")
            fixes.append(("broken", full, rel, "truncated"))
            continue
        job = {}
        if mips <= 1 and max(w, h) >= 64:
            job["mips"] = True
        if not block and bpp and bpp >= 24 and max(w, h) >= 256:
            job["dxt"] = True
            job["alpha"] = bool(tf[2])
        pw, ph = _pow2(w), _pow2(h)
        if (pw, ph) != (w, h):              # 1, 2: fine even compressed (the block is padded)
            job["size"] = (pw, ph)
        if ui_texture(rel):
            job = {}
        if job:
            what = ", ".join(x for x, k in (("no mipmaps", "mips"), ("uncompressed", "dxt"),
                                            (f"{w}x{h} isn't a power of two", "size")) if k in job)
            r.add("WARN", "Data Files", "", "", f"{rel}: {what}; --fix converts it (texconv)")
            fixes.append(("tex", full, rel, job))
    # --- models: version, absolute texture paths; and texture names they use (for "unused")
    used = set()
    tex_name = re.compile(rb"([\x21-\x7e][\x20-\x7e]{0,250}?)\.(?:dds|tga|bmp)", re.I)

    def note_refs(b):
        for mm in tex_name.finditer(b):
            stem = mm.group(1).replace(b"/", b"\\").rsplit(b"\\", 1)[-1].lower()
            used.add(stem.decode("latin1"))

    cache = shared_cache(os.path.dirname(data_dir))
    world.text_key_fixes = []
    allm = nif_files + kf_files
    for k, (rel, full) in enumerate(allm, 1):
        if k % 2000 == 0:
            print(f"Asset health: models {k}/{len(allm)}...", file=sys.stderr)
        if full not in stats:
            continue
        facts = model_facts_cached(cache, norm_rel(rel), full, stats[full], m, generated)
        if facts is None:
            continue
        if facts.get("keys"):
            world.text_key_fixes.append((full, rel, facts["keys"]))
            r.add("ERROR", "Data Files", "", "", f"{rel}: {facts['keys']} animation text key(s) use Unix line endings "
                                                 f"(LF without CR); the game can crash when the animation plays. "
                                                 f"--fix rewrites them with Windows line endings (original kept)")
        if "bad" in facts:
            first = facts["bad"]
            r.add("ERROR", "Data Files", "", "", f"{rel}: not a Morrowind model (header '{first}'); "
                                                 f"the game crashes loading it. --fix moves it to "
                                                 f"Off\\...\\broken\\ and puts a stand-in model in its place")
            fixes.append(("broken", full, rel, "not a Morrowind file"))
            continue
        used.update(facts.get("tex", ()))
        if rel.lower().endswith(".nif") and facts.get("noshape") and "marker" not in rel.lower():
            r.add("WARN", "Data Files", "", "", f"{rel}: model has no polygons (draws nothing); fine if the mod "
                                                f"hides something on purpose")
        if facts.get("abs"):
            r.add("ERROR", "Data Files", "", "", f"{rel}: names its texture(s) by a full drive path; the game "
                                                 f"doesn't find them. --fix makes the paths relative")
            fixes.append(("abs", full, rel, None))
    kf_orphans = []
    for rel, full in kf_files:
        fn = os.path.basename(rel)
        if fn.lower().startswith("x"):
            twin_rel = kf_model_name(rel).lower().replace("/", "\\").split("\\", 1)[-1]   # under Meshes
            if not os.path.exists(os.path.join(data_dir, kf_model_name(rel))) and twin_rel not in A.mesh_bsa \
                    and twin_rel not in getattr(A, "mesh_loose", {}):
                kf_orphans.append((rel, full))
    # the texture names in the BSAs' models: read once per BSA, then cached while the BSA is unchanged
    for bsa in sorted({v[0] for v in A.mesh_bsa.values()}):
        if hasattr(A, "bsa_facts"):
            used.update(A.bsa_facts(bsa).get("stems", ()))
    cache.flush()
    # --- sounds
    ff = find_ffmpeg()
    print(f"Asset health: sounds ({len(snd_files)})...", file=sys.stderr)
    for k, (top, rel, full, ls) in enumerate(snd_files, 1):
        if k % 5000 == 0:
            print(f"Asset health: sounds {k}/{len(snd_files)}...", file=sys.stderr)
        key = norm_rel(rel)
        skey = "snd:" + key
        info = None
        if ls is not None and key not in generated:
            # the listing's stamp: trusted for tidy's "checked clean" and a cached result that needs nothing;
            # a cached problem, or no entry, is confirmed with a real os.stat below
            if cache.tidy_lookup(key, ls) is not None:
                continue
            info = cache.get(skey, ls)
            if info and sound_job(top, info):
                info = None
        if info is None:
            if full not in stats:
                try:
                    stats[full] = tree.stat(full)
                except OSError:
                    continue
                if stats[full].st_size == 0:
                    r.add("ERROR", "Data Files", "", "", f"{rel}: empty file (0 bytes); --fix moves it to "
                                                         f"Off\\...\\broken\\ and puts a stand-in in its place")
                    fixes.append(("broken", full, rel, "empty file"))
                    continue
            if tidy_clean(rel, full):
                continue
            sstamp = stamp_of(stats[full])
            info = None if key in generated else cache.get(skey, sstamp)
        if info is None:
            try:
                with open(full, "rb") as f:
                    b = f.read(131072)
            except OSError:
                continue
            info = _wav_info(b) if rel.lower().endswith(".wav") else _mp3_info(b, m.mp3_first_frame)
            cache.put(skey, sstamp, list(info) if info else False)
        if not info:
            continue
        ch, rate = info
        job = sound_job(top, info)
        if job:
            what = ", ".join(x for x, k in (("stereo (3D sounds must be mono)", "mono"), (f"{rate} Hz", "rate"))
                             if k in job)
            r.add("WARN", "Data Files", "", "", f"{rel}: {what}; --fix converts it (ffmpeg)"
                  + ("" if ff else " - ffmpeg not found on PATH"))
            fixes.append(("snd", full, rel, job))
    # --- unused textures and sounds (conservative: any mention anywhere counts as used)
    print("Asset health: collecting every name plugins, scripts, Lua and configs use...", file=sys.stderr)
    word_re = re.compile(rb"[A-Za-z0-9_\-]{3,}")
    sounds_used, words = set(), set()

    def note_names(b, with_words):
        found = names_by_ext(b)
        for name, ext in found:
            (sounds_used if ext in ("wav", "mp3") else used).add(name)
        wl = []
        if with_words:                               # Lua etc. may build names: every word counts
            wl = sorted({w.lower().decode("latin1") for w in word_re.findall(b)})
            words.update(wl)
        return [list(x) for x in found], wl

    def note_file(path, with_words):
        """note_names for a file, remembered in the cache by size + date: unchanged files aren't read again."""
        try:
            st = os.stat(path)
        except OSError:
            return
        key, stamp = ("refs:" if with_words else "names:") + os.path.abspath(path).lower(), stamp_of(st)
        got = cache.get(key, stamp)
        if got is not None:
            for name, ext in got[0]:
                (sounds_used if ext in ("wav", "mp3") else used).add(name)
            words.update(got[1])
            return
        try:
            with open(path, "rb") as f:
                res = note_names(f.read(), with_words)
        except OSError:
            return
        cache.put(key, stamp, [res[0], res[1]])

    for p in getattr(world, "plugin_paths", []):
        note_file(p, False)
    game_dir = os.path.dirname(data_dir)
    skip_top = {"meshes", "textures", "sound", "music", "icons", "bookart", "splash", "video", "off", ".orphaned"}
    for top, rel, full in tree.files:                   # Data Files outside the asset folders (Lua, configs...)
        fl = full.lower()
        if top not in skip_top and fl.endswith(REF_TEXT_EXT) and not fl.endswith(".bugreport.txt"):
            note_file(full, True)
    # the Morrowind folder: Morrowind.ini, and the MGE XE and MWSE folders. Not this tool's own files there
    # (its cache, report and lists name every texture: each would count as used, and "unused" never shrink)
    try:
        game_entries = sorted(os.listdir(game_dir))
    except OSError:
        game_entries = []
    for fn in game_entries:
        full = os.path.join(game_dir, fn)
        if fn.lower() == "morrowind.ini":
            note_file(full, True)
        elif fn.lower() in ("mge3", "mwse") and os.path.isdir(full):
            for dp, _ds, fs in os.walk(full):
                for f2 in fs:
                    if f2.lower().endswith(REF_TEXT_EXT):
                        note_file(os.path.join(dp, f2), True)
    unused = []
    for rel, full, size in tex_files:
        top = rel.split(os.sep, 1)[0].lower()
        if top != "textures":
            continue                                   # icons/bookart/splash: named in odd ways; left alone
        stem = os.path.splitext(os.path.basename(rel))[0].lower()
        base = MAP_SUFFIX.sub("", stem)
        sub = rel.lower().split(os.sep)
        if stem in used or base in used or stem in words or base in words or IMPLICIT_TEX.match(stem) \
                or len(sub) > 2 and sub[1] in ("distantland", "mwse", "mge", "shaders", "menu", "sky", "water",
                                                "levelup", "splash"):
            continue
        unused.append((rel, full, size))
    for top, rel, full, _ls in snd_files:
        if top != "sound" or rel.lower().split(os.sep)[1:2] == ["vo"]:
            continue                                   # music plays by folder; voices are left alone
        stem = os.path.splitext(os.path.basename(rel))[0].lower()
        if stem in sounds_used or stem in words:
            continue
        unused.append((rel, full, os.path.getsize(full)))
    for rel, full in kf_orphans:
        stem = os.path.splitext(os.path.basename(rel))[0].lower()
        if stem in words or stem in used:          # a Lua mod or plugin loads it by name: keep it
            r.add("INFO", "Data Files", "", "", f"{rel}: animation without its model, but something names it; kept")
            continue
        r.add("WARN", "Data Files", "", "", f"{rel}: orphaned animation (no {os.path.basename(kf_model_name(rel))} "
                                            f"anywhere); --fix moves it to Off\\...\\orphaned\\")
        fixes.append(("orphan", full, rel, "orphaned animation"))
    gone = {u[0] for u in unused}
    fixes[:] = [f for f in fixes if f[2] not in gone]  # nothing to repair in a file that is moved out
    if unused:
        mb = sum(u[2] for u in unused) / 1048576
        r.add("INFO", "Data Files", "", "", f"{len(unused)} texture/sound file(s) ({mb:.0f} MB) that no plugin, model, "
                                            f"script, Lua mod or config names; --fix moves them to their mod's "
                                            f"Off\\unused\\ (listed in {UNUSED_RECORD}; --restore-unused puts them back)")
        for rel, full, size in unused:
            fixes.append(("unused", full, rel, "nothing names it"))
    world.asset_health = fixes
    # the pass saw every file: entries for files that are gone (or renamed) go, and what was learnt is written
    # now, not only when the program ends
    cache.prune(("tex2:", "texh:", "nif:", "snd:", "refs:", "names:", "bsa2:"))
    cache.flush()


def apply(fixes, data_dir, game_dir, m, log, dry=False):
    """--fix: repair what check() found. Returns a summary string."""
    texconv = next((p for p in (os.path.join(game_dir, "texconv.exe"), shutil.which("texconv")) if p and
                    os.path.exists(p)), None)
    ff = find_ffmpeg()
    done = {"tex": 0, "abs": 0, "snd": 0, "unused": 0, "broken": 0, "orphan": 0}
    skipped = []
    moves = []
    tmp = os.path.join(game_dir, "mwdialog_tmp_assets")
    for kind, full, rel, job in fixes:
        if dry:
            done[kind] += 1
            continue
        try:
            if kind == "tex":
                if not texconv:
                    skipped.append(f"{rel} (texconv.exe not found)")
                    continue
                os.makedirs(tmp, exist_ok=True)
                args = [texconv, "-nologo", "-y", "-dx9", "-o", tmp]
                if job.get("dxt"):
                    args += ["-f", "BC3_UNORM" if job.get("alpha", True) else "BC1_UNORM"]
                args += ["-m", "0"] if job.get("mips") or job.get("size") or job.get("dxt") else []
                if job.get("size"):
                    args += ["-w", str(job["size"][0]), "-h", str(job["size"][1])]
                res = subprocess.run(args + [full], capture_output=True, text=True)
                out = os.path.join(tmp, os.path.basename(full))
                if res.returncode or not os.path.exists(out):
                    skipped.append(f"{rel} (texconv failed: {(res.stdout + res.stderr).strip()[-120:]})")
                    continue
                new = open(out, "rb").read()
                os.remove(out)
            elif kind == "abs":
                n, new = rewrite_absolute(open(full, "rb").read())
                if not new:
                    continue
            elif kind == "snd":
                if not ff:
                    skipped.append(f"{rel} (ffmpeg not found)")
                    continue
                os.makedirs(tmp, exist_ok=True)
                out = os.path.join(tmp, "x" + os.path.splitext(full)[1].lower())
                a = [ff, "-y", "-v", "error", "-i", full]
                if job.get("mono"):
                    a += ["-ac", "1"]
                if job.get("rate"):
                    a += ["-ar", str(job["rate"])]
                a += (["-c:a", "pcm_s16le"] if out.endswith(".wav") else ["-c:a", "libmp3lame", "-q:a", "2",
                                                                         "-id3v2_version", "0"]) + [out]
                res = subprocess.run(a, capture_output=True, text=True)
                if res.returncode or not os.path.exists(out):
                    skipped.append(f"{rel} (ffmpeg failed: {res.stderr.strip()[-120:]})")
                    continue
                new = open(out, "rb").read()
                os.remove(out)
            elif kind == "orphan":                     # out of Data Files, into the mod's Off\...\orphaned\
                mod, _pl = m.asset_owner_folder(data_dir, rel)
                if mod:
                    dest = broken_dest(mod, rel, "orphaned", _pl)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    stage = os.path.join(mod, rel)
                    if os.path.exists(stage) and not os.path.exists(dest):
                        os.replace(stage, dest)
                    if os.path.exists(full):
                        os.remove(full)
                else:
                    dest = os.path.join(game_dir, "mwdialog_backup", "asset_originals", "orphaned", rel)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    os.replace(full, dest)
                moves.append((rel, dest, job))
                done["unused"] += 1
                log.append(("Data Files", f"'{rel}' ({job})", f"moved to {dest}"))
                continue
            elif kind == "broken":                     # keep the broken file in Off, a stand-in in its place
                mod, _pl = m.asset_owner_folder(data_dir, rel)
                dest = broken_dest(mod, rel, "broken", _pl) if mod else \
                    os.path.join(game_dir, "mwdialog_backup", "asset_originals", "broken", rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                if not os.path.exists(dest):
                    shutil.copy2(full, dest)
                m.replace_asset_in_place(full, m.stand_in_bytes(rel))
                done.setdefault("broken", 0)
                done["broken"] += 1
                log.append(("Data Files", f"'{rel}' ({job})", f"broken file kept in {dest}; stand-in put in its place"))
                continue
            else:                                      # unused / empty: move out of Data Files
                mod, _pl = m.asset_owner_folder(data_dir, rel)
                if mod:
                    dest = broken_dest(mod, rel, "unused", _pl)
                    src_stage = os.path.join(mod, rel)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    if os.path.exists(src_stage) and not os.path.exists(dest):
                        os.replace(src_stage, dest)    # the staging copy moves into Off (never deployed)
                    if os.path.exists(full):
                        os.remove(full)                # the Data Files hard link
                else:
                    dest = os.path.join(game_dir, "mwdialog_backup", "asset_originals", "unused", rel)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    os.replace(full, dest)
                moves.append((rel, dest, job))
                log.append(("Data Files", f"'{rel}' ({job})", f"moved to {dest}"))
                done["unused"] += 1
                continue
            bak = m.backup_asset_original(data_dir, rel, feature=FEATURE_OF.get(kind, "converted"))
            m.replace_asset_in_place(full, new)
            done[kind] += 1
            log.append(("Data Files", f"'{rel}' ({kind})", f"repaired (original: {bak})"))
        except OSError as e:
            skipped.append(f"{rel} ({e})")
    if moves:
        with open(os.path.join(game_dir, UNUSED_RECORD), "a", encoding="utf-8") as f:
            for rel, dest, why in moves:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{rel}\t{dest}\t{why}\n")
    shutil.rmtree(tmp, ignore_errors=True)
    msg = (f"{done.get('broken', 0)} broken file(s) replaced by stand-ins (kept in Off\\...\\broken\\), "
           f"{done['tex']} texture(s) converted, {done['abs']} model(s) with absolute texture paths fixed, "
           f"{done['snd']} sound(s) converted, {done['unused']} unused/empty file(s) moved to Off")
    if skipped:
        msg += f"; {len(skipped)} skipped, e.g. " + "; ".join(skipped[:3])
    return ("Dry run: would do " if dry else "") + msg


# <mod>\Off\<unused|orphaned|broken>\... (any case, either slash): a file these tools took out of a mod
OFF_MARKER_RE = re.compile(r"[\\/]off[\\/](?:unused|orphaned|broken)[\\/]", re.IGNORECASE)


def restore_unused(game_dir, data_dir):
    """--restore-unused: put back every file listed in mwdialog_unused_assets.txt (staging copy back into the
    mod folder; Vortex redeploys it, or it is copied into Data Files when it wasn't Vortex's)."""
    path = os.path.join(game_dir, UNUSED_RECORD)
    if not os.path.exists(path):
        print("Nothing to restore.")
        return 0
    back, failed = 0, []
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        rel, dest = parts[1], parts[2]
        if not os.path.exists(dest):
            continue
        try:
            m = OFF_MARKER_RE.search(dest)
            if m:                                    # from a Vortex mod: back into the mod, linked into Data Files
                mod = dest[:m.start()]
                staged = os.path.join(mod, rel)
                os.makedirs(os.path.dirname(staged), exist_ok=True)
                os.replace(dest, staged)
                target = os.path.join(data_dir, rel)
                if not os.path.exists(target):
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    try:
                        os.link(staged, target)
                    except OSError:
                        shutil.copy2(staged, target)
            else:
                os.makedirs(os.path.dirname(os.path.join(data_dir, rel)), exist_ok=True)
                os.replace(dest, os.path.join(data_dir, rel))
            back += 1
        except OSError as e:
            failed.append(line)
            print(f"  could not put back '{rel}': {e}")
    if failed:                                       # keep the record so a later run can finish the job
        print(f"{back} file(s) put back; {len(failed)} could not be (still listed in {UNUSED_RECORD}).")
        return 1
    os.replace(path, path + ".restored")
    print(f"{back} file(s) put back.")
    return 0


# ---------------------------------------------------------------------------------------------------------
# Per-folder check/repair, for vortex_tidy (one mod's staging folder at a time). The same per-file checks as
# check() plus the text-key check, the 2048 texture limit and the sound repairs; no "unused" check (that
# needs the whole load order). Files are repaired IN PLACE (hard links to Data Files stay links); the
# original goes to <mod>\Off\<plugin or mod name>\<path>.
# ---------------------------------------------------------------------------------------------------------

# DXGI formats (DX10 header) with no alpha worth keeping beyond DXT1's 1-bit one: BC1, BC4, BC5, BC6H,
# B5G6R5, B8G8R8X8. Everything else (BC2, BC3, BC7, RGBA, unknown) may have real alpha.
DXGI_NO_ALPHA = {70, 71, 72, 79, 80, 81, 82, 83, 84, 85, 88, 93, 94, 95, 96}


def dx10_has_alpha(head):
    """Whether a DX10-header DDS (its first 148 bytes) may need DXT5 (BC3) alpha when converted to DXT; an
    opaque one becomes DXT1 (BC1, half the size). Unknown: True (the old behaviour, never loses alpha)."""
    if len(head) < 148:
        return True
    dxgi = struct.unpack_from("<I", head, 128)[0]
    alpha_mode = struct.unpack_from("<I", head, 144)[0] & 0x7
    if alpha_mode == 3:                              # DDS_ALPHA_MODE_OPAQUE
        return False
    return dxgi not in DXGI_NO_ALPHA


def _examine_dds(rel, full, size, m):
    """[(severity, message)], job or None."""
    try:
        with open(full, "rb") as f:
            head = f.read(148)
    except OSError:
        return [], None
    if head[:4] != b"DDS ":
        return [("ERROR", "not a DDS file (renamed?); the game can't load it")], "broken"
    if head[84:88] == b"DX10":
        return [("ERROR", "DX10/BC7-style DDS; Morrowind (DirectX 8) can't read it -> converted to DXT")], \
            {"dxt": True, "mips": True, "alpha": dx10_has_alpha(head)}
    info = m.dds_info(head)
    if info is None:
        return [], None
    w, h, mips, hdr, block, bpp = info
    need, lw, lh = hdr, w, h
    for _ in range(mips):
        need += m.dds_level_size(lw, lh, block, bpp)
        lw, lh = max(1, lw // 2), max(1, lh // 2)
    if size < need:
        return [("ERROR", f"truncated ({size} of {need} bytes)")], "broken"
    job, why = {}, []
    if max(w, h) > m.TEXTURE_MAX_EDGE:
        job["max"] = m.TEXTURE_MAX_EDGE
        why.append(f"{w}x{h} (over {m.TEXTURE_MAX_EDGE})")
    if mips <= 1 and max(w, h) >= 64:
        job["mips"] = True
        why.append("no mipmaps")
    if not block and bpp and bpp >= 24 and max(w, h) >= 256:
        job["dxt"] = True
        job["alpha"] = bool(struct.unpack_from("<I", head, 80)[0] & 0x1)
        why.append("uncompressed")
    pw, ph = _pow2(w), _pow2(h)
    if (pw, ph) != (w, h):              # 1, 2: fine even compressed (the block is padded)
        job["size"] = (pw, ph)
        why.append(f"{w}x{h} isn't a power of two")
    if ui_texture(rel):
        for k in ("size", "dxt", "mips", "alpha"):
            job.pop(k, None)
        why = [t for t in why if t.startswith(f"{w}x{h} (over")]
    return ([("WARN", ", ".join(why) + " -> converted")] if job else []), (job or None)


_PLUGIN_TEXT = {}
HIGH_BYTE_RE = re.compile(rb"[\x80-\xff]+")
FILE_EXT_RE = re.compile(rb"\.(?:nif|kf|dds|tga|bmp|wav|mp3)\b")


def _other_plugins_naming(name_b, root, data_dir):
    """Active-folder plugins (Data Files) other than this mod's own that hold name_b (lower bytes)."""
    if not data_dir or not os.path.isdir(data_dir):
        return []
    if not _PLUGIN_TEXT:
        for fn in os.listdir(data_dir):
            if fn.lower().endswith((".esp", ".esm")):
                try:                           # only what is near a non-ASCII byte and names a file
                    data = open(os.path.join(data_dir, fn), "rb").read()
                    bits, last = [], -1
                    for mm in HIGH_BYTE_RE.finditer(data):
                        k = mm.start()
                        if k < last:
                            continue
                        win = data[max(0, k - 200):k + 200].lower()
                        last = k + 200
                        if FILE_EXT_RE.search(win):
                            bits.append(win)
                    _PLUGIN_TEXT[fn] = b"\0".join(bits)
                except OSError:
                    pass
        _PLUGIN_TEXT.setdefault("", b"")
    own = {fn.lower() for fn in os.listdir(root)}
    return [fn for fn, t in _PLUGIN_TEXT.items() if fn and fn.lower() not in own and name_b in t
            and "mwdialog_check" not in fn.lower()]


_MODEL_TEXT = {}               # mod folder (normcase) -> text near non-ASCII bytes in its .nif/.kf files


def _models_naming(name_b, root):
    """True when a .nif/.kf in mod folder `root` holds name_b (lower bytes): a model names the file, and the
    rename can't change models, so it would lose its texture."""
    key = os.path.normcase(os.path.abspath(root))
    if key not in _MODEL_TEXT:
        bits = []
        for dp, _ds, fs in os.walk(root):
            if os.path.basename(dp).lower() == "off" or (os.sep + "off" + os.sep) in (dp.lower() + os.sep):
                continue
            for fn in fs:
                if not fn.lower().endswith((".nif", ".kf")):
                    continue
                try:
                    data = open(os.path.join(dp, fn), "rb").read()
                except OSError:
                    continue
                last = -1
                for mm in HIGH_BYTE_RE.finditer(data):
                    k = mm.start()
                    if k < last:
                        continue
                    bits.append(data[max(0, k - 200):k + 200].lower())
                    last = k + 200
        _MODEL_TEXT[key] = b"\0".join(bits)
    return name_b in _MODEL_TEXT[key]


def check_folder(root, m, data_dir=None, bsa_meshes=None):
    """(issues [(severity, rel, message)], fixes [(kind, full, rel, job)]) for one mod folder. data_dir and
    bsa_meshes (lowercase paths under Meshes in every BSA) let an animation's model be found elsewhere."""
    issues, fixes = [], []
    own_text = b""
    try:
        for e in os.listdir(root):
            if e.lower().endswith((".esp", ".esm")):
                own_text += open(os.path.join(root, e), "rb").read().lower()
        for dp, ds, fs in os.walk(os.path.join(root, "MWSE")) if os.path.isdir(os.path.join(root, "MWSE")) else ():
            for fn in fs:
                if fn.lower().endswith((".lua", ".json", ".toml")):
                    own_text += open(os.path.join(dp, fn), "rb").read().lower()
    except OSError:
        pass
    tops = ASSET_DIRS
    # files already found clean (here or by an earlier tidy / check run) aren't read again: keyed by the
    # Data Files path + size + date, which a Vortex hard link shares with the deployed copy
    cache = shared_cache(os.path.dirname(data_dir) if data_dir else os.path.dirname(os.path.abspath(__file__)))
    mod_key = TIDY_KEY + os.path.basename(os.path.normpath(root)).lower() + "|"
    pending = None

    def settle():
        if pending:
            # one record per mod file (tidy3:<mod>|<path>, its size + date): the full check of Data Files trusts
            # the same file there (what tidy can't fix, it can't either; tidy's bug report has it) and takes a
            # model's texture list from it. Clean ("c"): not even tidy reads it again.
            key, stamp, n_issues, n_fixes, facts = pending
            rec = {"c": len(issues) == n_issues and len(fixes) == n_fixes}
            if facts is not None:
                rec["f"] = facts
            cache.put(key, stamp, rec)
    for top, rel, full in _walk(root, tops):
        settle()
        pending = None
        low = rel.lower()
        try:
            st = os.stat(full)
            size = st.st_size
        except OSError:
            continue
        stamp = stamp_of(st)
        key = mod_key + norm_rel(rel)
        got = cache.get(key, stamp)
        if got is not None and got.get("c"):
            continue
        pending = [key, stamp, len(issues), len(fixes), None]
        if any(ord(c) > 127 for c in rel):
            new_rel = ascii_name(rel)
            tail = rel.replace("/", "\\").split("\\", 1)[-1]
            try:
                tail_b = tail.lower().encode("cp1252")
            except UnicodeEncodeError:
                tail_b = None                  # Cyrillic etc.: no plugin can name it the way Windows needs
            others = _other_plugins_naming(tail_b, root, data_dir) if tail_b else []
            base_b = os.path.basename(tail_b.replace(b"\\", b"/")) if tail_b else None
            if not others and base_b and _models_naming(base_b, root):
                issues.append(("WARN", rel, "non-ASCII file name, named so by a model (.nif) in this mod; left "
                                            "as it is (renaming it would leave the model without it)"))
            elif others:
                issues.append(("WARN", rel, f"non-ASCII file name, named so by {', '.join(others[:3])}; left as "
                                            f"it is (renaming it would break that plugin)"))
            else:
                issues.append(("ERROR", rel, f"non-ASCII file name; the game can't open it -> renamed "
                                             f"{new_rel}, and the mod's plugins changed to name it so"))
                fixes.append(("ascii", full, rel, new_rel))
        if size == 0:
            issues.append(("ERROR", rel, "empty file (0 bytes) -> kept in Off\\...\\broken\\, stand-in put there"))
            fixes.append(("broken", full, rel, "empty"))
            continue
        if top in TEX_DIRS and low.endswith(".dds"):
            msgs, job = _examine_dds(rel, full, size, m)
            if job == "broken":
                issues += [(s, rel, t + " -> kept in Off\\...\\broken\\, placeholder put there") for s, t in msgs]
                fixes.append(("broken", full, rel, msgs[0][1] if msgs else "broken"))
                continue
            issues += [(s, rel, t) for s, t in msgs]
            if job:
                fixes.append(("tex", full, rel, job))
        elif top == "meshes" and low.endswith((".nif", ".kf")):
            try:
                with open(full, "rb") as f:
                    b = f.read()
            except OSError:
                continue
            pending[4] = model_facts(b, m)
            if not b.startswith(NIF_HEAD):
                first = b[:40].split(b"\n")[0].decode("latin1", "replace")
                issues.append(("ERROR", rel, f"not a Morrowind file (header '{first}'); the game crashes on it"
                                             " -> kept in Off\\...\\broken\\, a stand-in put there"))
                fixes.append(("broken", full, rel, "not a Morrowind file"))
                continue
            if low.endswith(".nif") and nif_without_shapes(b) and "marker" not in low:
                issues.append(("WARN", rel, "model has no polygons (draws nothing); fine if it hides something on "
                                            "purpose"))
            bad, _new = m.nif_text_keys_lf(b)
            if bad:
                issues.append(("ERROR", rel, f"{bad} animation text key(s) with Unix line endings -> CR LF"))
                fixes.append(("keys", full, rel, None))
            if nif_absolute_textures(b):
                issues.append(("ERROR", rel, "texture(s) named by a full drive path -> made relative"))
                fixes.append(("abs", full, rel, None))
            if low.endswith(".kf") and os.path.basename(low).startswith("x") \
                    and not os.path.exists(full[:-3] + ".nif"):
                twin = kf_model_name(rel)
                twin_low = twin.lower().replace("/", "\\").split("\\", 1)[-1]
                elsewhere = (data_dir and os.path.exists(os.path.join(data_dir, twin))) or \
                    (bsa_meshes is not None and twin_low in bsa_meshes)
                named = os.path.splitext(os.path.basename(low))[0].encode("latin1", "replace") in own_text
                if not elsewhere and not named:
                    issues.append(("WARN", rel, "orphaned animation (its model is nowhere) -> Off\\...\\orphaned\\"))
                    fixes.append(("orphan", full, rel, "orphaned animation"))
        elif top in SOUND_DIRS and low.endswith((".wav", ".mp3")):
            try:
                with open(full, "rb") as f:
                    b = f.read(262144)
            except OSError:
                continue
            job, why = {}, []
            if low.endswith(".mp3"):
                j = m.mp3_first_frame(b)
                if j is None and b[:3] == b"ID3" and len(b) >= 10:          # tag bigger than what was read
                    tsz = (b[6] << 21) | (b[7] << 14) | (b[8] << 7) | b[9]
                    with open(full, "rb") as f:
                        f.seek(10 + tsz)
                        b = b[:10] + f.read(262144)
                        j = m.mp3_first_frame(b)
                        if j is not None:
                            j = j - 10 + 10 + tsz if j >= 10 else j
                if j is None:
                    issues.append(("ERROR", rel, "no MPEG audio found (damaged MP3) -> kept in Off\\...\\broken\\, "
                                                 "silence put there"))
                    fixes.append(("broken", full, rel, "damaged MP3"))
                    continue
                if j > 4096:
                    job["strip"] = j
                    why.append(f"{j // 1024} KB tag before the audio")
                if job.get("strip"):                   # judge the audio itself, after the tag
                    with open(full, "rb") as f:
                        f.seek(j)
                        info = _mp3_info(f.read(65536), m.mp3_first_frame)
                else:
                    info = _mp3_info(b, m.mp3_first_frame)
            else:
                info = _wav_info(b)
                fmt_bits = None
                p = b.find(b"fmt ")
                if p != -1 and p + 24 <= len(b):
                    fmt_tag, _ch, _r, _br, _al, fmt_bits = struct.unpack_from("<HHIIHH", b, p + 8)
                    if fmt_tag not in (1, 0xFFFE) or fmt_bits not in (8, 16):
                        job["pcm16"] = True
                        why.append(f"{fmt_bits}-bit / codec {fmt_tag} (needs 16-bit PCM)")
            if info:
                ch, rate = info
                if top == "sound" and ch > 1:
                    job["mono"] = True
                    why.append("stereo (3D sounds must be mono)")
                if rate not in STD_RATES:
                    job["rate"] = 44100
                    why.append(f"{rate} Hz")
            if job:
                issues.append(("WARN", rel, ", ".join(why) + " -> converted"))
                fixes.append(("snd", full, rel, job))
    settle()
    cache.flush()
    return issues, fixes


FIX_ORDER = {"ascii": 0, "broken": 1, "orphan": 2, "snd": 3, "keys": 4, "abs": 5, "tex": 6}


def _backup_in_mod(root, rel, full, plugin_name, feature="converted"):
    """The original into <mod>\\Off\\<feature>\\<plugin name>\\<rel>, once: not when one is kept already
    (by any feature, or where earlier versions put it: Off\\<plugin name>\\<rel>) - unless the file now there
    is a new original (a mod update): then that is kept too, with a date added (see keep_new_original)."""
    import mwdialog_check as _m
    off = os.path.join(root, "Off")
    if os.path.isdir(off):
        for f in os.listdir(off):
            fp = os.path.join(off, f)
            if os.path.exists(os.path.join(fp, rel)):
                return _m.keep_new_original(os.path.join(fp, rel), full)     # old layout
            if os.path.isdir(fp) and f.lower() not in ("broken", "orphaned", "unused"):
                for d in os.listdir(fp):
                    if os.path.exists(os.path.join(fp, d, rel)):
                        return _m.keep_new_original(os.path.join(fp, d, rel), full)
    dest = _m.off_dest(root, feature, plugin_name, rel)
    if not os.path.exists(dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(full, dest)
        _m._ASSET_BACKUP_OF[os.path.normcase(os.path.abspath(full))] = dest
        return dest
    return _m.keep_new_original(dest, full)


def find_ffmpeg():
    """ffmpeg on PATH, or ffmpeg.exe next to these scripts (the game folder)."""
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ffmpeg.exe")
    return shutil.which("ffmpeg") or (here if os.path.exists(here) else None)


LOOKALIKES = dict(zip("аеорсхуікмтнвАЕОРСХУІКМТНВЅјѕԁԛԝοαρτνιΑΒΕΗΙΚΜΝΟΡΤΧΥΖ",
                      "aeopcxyikmthbAEOPCXYIKMTHBSjsdqwoaptviABEHIKMNOPTXYZ"))


def ascii_name(rel):
    """rel with every non-ASCII letter made plain (é -> e, ß -> s), one character for one, so a name in a
    plugin keeps its length."""
    import unicodedata
    out = []
    for c in rel:
        if ord(c) < 128:
            out.append(c)
        elif c in LOOKALIKES:                  # Cyrillic / Greek letters drawn like Latin ones (х, о, а...)
            out.append(LOOKALIKES[c])
        else:
            d = unicodedata.normalize("NFKD", c).encode("ascii", "ignore").decode()
            out.append(d[:1] or "_")
    return "".join(out)


def rename_ascii(root, full, rel, new_rel, log):
    """Rename a file (and the folders on its way) to its ASCII name, and change the name in the mod's own
    plugins (Windows-1252, as Morrowind writes them; same length, so changed in place)."""
    new_full = os.path.join(root, new_rel)
    os.makedirs(os.path.dirname(new_full), exist_ok=True)
    if not os.path.exists(new_full):
        os.replace(full, new_full)
    elif os.path.exists(full):
        # renamed before (the ASCII copy is there, maybe repaired since): the old-named file is the
        # untouched original; it goes to Off\names\<mod>\<old path>, out of the way
        import mwdialog_check as _m
        keep = _m.off_dest(root, "names", None, rel)
        os.makedirs(os.path.dirname(keep), exist_ok=True)
        if os.path.exists(keep):
            os.remove(full)
        else:
            os.replace(full, keep)
        log(f"{rel}: already renamed {new_rel} by an earlier run; the old-named original moved to Off\\names\\")
    # drop the old folders when emptied
    d = os.path.dirname(full)
    while os.path.normcase(d) != os.path.normcase(root) and os.path.isdir(d) and not os.listdir(d):
        try:
            os.rmdir(d)
        except OSError:
            break
        d = os.path.dirname(d)
    # the name as plugins have it: no "Meshes\" etc. in front (or, rarely, with it)
    parts_old, parts_new = rel.replace("/", "\\").split("\\"), new_rel.replace("/", "\\").split("\\")
    pairs = []
    for k in (1, 0):
        o, n = "\\".join(parts_old[k:]), "\\".join(parts_new[k:])
        try:
            ob, nb = o.encode("cp1252"), n.encode("cp1252")
        except UnicodeEncodeError:
            continue
        if ob != nb and len(ob) == len(nb):
            pairs.append((ob.lower(), nb))
    if not pairs:
        return
    import mwdialog_check as _m
    for pf in os.listdir(root):
        if not pf.lower().endswith((".esp", ".esm", ".omwaddon")):
            continue
        pp = os.path.join(root, pf)
        try:
            data = open(pp, "rb").read()
            new, hits = plugin_path_rename(data, pairs)
        except (OSError, _m.FormatError) as e:
            log(f"{pf}: not changed ({e})")
            continue
        if hits:
            bak = _m.off_dest(root, "names", pf, pf)     # Off\\names\\<plugin>\\<plugin file>, once
            if not os.path.exists(bak):
                os.makedirs(os.path.dirname(bak), exist_ok=True)
                shutil.copy2(pp, bak)
            # checked temp copy, then in place: keeps a Vortex hard link (and the date: load order)
            _m.write_plugin_bytes(pp, new, keep_times=os.stat(pp))
            log(f"{pf}: {hits} name(s) of {rel} changed to {new_rel}")


# subrecords whose whole value is a file path: (record tag, or None for any record; subrecord)
PATH_SUBS = {(None, "MODL"), (None, "ITEX"), ("ALCH", "TEXT"), ("SOUN", "FNAM"), ("LTEX", "DATA"),
             ("BSGN", "TNAM"), ("INFO", "SNAM"), ("MGEF", "PTEX")}
# subrecords holding script text a full path can appear inside (same length, so changed in place)
PATH_TEXT_SUBS = {("SCPT", "SCTX"), ("SCPT", "SCDT"), ("INFO", "BNAM")}


def plugin_path_rename(data, pairs):
    """Change file paths in a plugin: a path subrecord whose whole value (any case, either slash) is one of
    pairs' old names, and the full old path (with its folders) inside script text. Book and dialogue text,
    ids, and other folders' files that only share the file name are left alone.
    pairs: [(old lower bytes, new bytes)] of equal lengths, the first the path without its top folder.
    Returns (new bytes, number of changes)."""
    import mwdialog_check as _m
    new, hits = bytearray(data), 0
    script_old, script_new = pairs[0]
    for off, tag, _flags, body in _m.iter_records(data):
        p, end = 0, len(body)
        while p + 8 <= end:
            sn = bytes(body[p:p + 4]).decode("latin-1")
            size = struct.unpack_from("<I", body, p + 4)[0]
            d = bytes(body[p + 8:p + 8 + size])
            at = off + 16 + p + 8
            if (tag, sn) in PATH_SUBS or (None, sn) in PATH_SUBS:
                val = d.split(b"\0", 1)[0].lower().replace(b"/", b"\\")
                for ob, nb in pairs:
                    if val == ob:
                        new[at:at + len(nb)] = nb
                        hits += 1
                        break
            elif (tag, sn) in PATH_TEXT_SUBS and b"\\" in script_old:   # never a bare file name in text
                low = d.lower().replace(b"/", b"\\")
                i = low.find(script_old)
                while i >= 0:
                    new[at + i:at + i + len(script_new)] = script_new
                    hits += 1
                    i = low.find(script_old, i + len(script_old))
            p += 8 + size
    return bytes(new), hits


def apply_folder(root, fixes, m, game_dir, plugin_name):
    """Repair what check_folder() found, in place. Returns (done count, [skipped notes])."""
    texconv = next((p for p in (os.path.join(game_dir, "texconv.exe"), shutil.which("texconv")) if p and
                    os.path.exists(p)), None)
    ff = find_ffmpeg()
    tmp = os.path.join(game_dir, "mwdialog_tmp_assets")
    done, skipped = 0, []
    # every repair of one file is done in this one run: the renames first, then the other fixes find the
    # file under its new name (each fix reads the file as the one before left it)
    renamed = {}
    # files this tool changed before (any run): their original is already kept, so no new backup
    cache = shared_cache(game_dir)
    def was_fixed(r):
        return cache.d.get("fixed:" + os.path.join(root, r).lower()) is not None

    def mark_fixed(r):
        cache.put("fixed:" + os.path.join(root, r).lower(), "", True)
    for kind, full, rel, job in fixes:
        if kind == "ascii":
            try:
                rename_ascii(root, full, rel, job, lambda t: print("  " + t))
                renamed[full] = (os.path.join(root, job), job)
                mark_fixed(job)
                done += 1
            except OSError as e:
                skipped.append(f"{rel} ({e})")
    # the order: names first (above), then what takes the file out (broken, orphaned), then sound (tag,
    # stereo, rate: one ffmpeg pass), models (line endings, then drive paths), textures (size, compression,
    # mipmaps, power of two: one texconv pass). Each reads the file as the one before left it.
    orig_rel = {renamed[f][0]: r for k, f, r, j in fixes if k == "ascii" and f in renamed}
    fixes = sorted(((k, *renamed.get(f, (f, r)), j) for k, f, r, j in fixes if k != "ascii"),
                   key=lambda x: FIX_ORDER.get(x[0], 9))
    gone = set()
    for kind, full, rel, job in fixes:
        if full in gone:
            continue                               # already moved out (broken / orphaned)
        if kind in ("broken", "orphan"):
            gone.add(full)
        try:
            data = open(full, "rb").read()
            new = None
            if kind == "orphan":
                dest = broken_dest(root, rel, "orphaned", plugin_name)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                if not os.path.exists(dest):
                    os.replace(full, dest)
                done += 1
                continue
            if kind == "broken":
                dest = broken_dest(root, rel, "broken", plugin_name)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                if not os.path.exists(dest):
                    shutil.copy2(full, dest)
                m.replace_asset_in_place(full, m.stand_in_bytes(rel))
                done += 1
                continue
            if kind == "keys":
                _n, new = m.nif_text_keys_lf(data)
            elif kind == "abs":
                _n, new = rewrite_absolute(data)
            elif kind == "tex":
                if job.get("max") and set(job) == {"max"}:
                    new, _info = m.dds_reduce(data, job["max"])   # just drop the big mip levels
                    if new is None and not texconv:
                        skipped.append(f"{rel} ({_info})")
                        continue
                if new is None:
                    if not texconv:
                        skipped.append(f"{rel} (texconv.exe not found)")
                        continue
                    os.makedirs(tmp, exist_ok=True)
                    a = [texconv, "-nologo", "-y", "-dx9", "-o", tmp, "-m", "0"]
                    if job.get("dxt"):
                        a += ["-f", "BC3_UNORM" if job.get("alpha", True) else "BC1_UNORM"]
                    w, h = job.get("size") or (None, None)
                    if job.get("max"):
                        info = m.dds_info(data[:148])
                        w0, h0 = (w or info[0]), (h or info[1])
                        k = max(w0, h0) / job["max"]
                        if k > 1:
                            w, h = max(4, int(w0 / k)), max(4, int(h0 / k))
                    if w:
                        a += ["-w", str(w), "-h", str(h)]
                    res = subprocess.run(a + [full], capture_output=True, text=True)
                    out = os.path.join(tmp, os.path.basename(full))
                    if res.returncode or not os.path.exists(out):
                        skipped.append(f"{rel} (texconv: {(res.stdout + res.stderr).strip()[-100:]})")
                        continue
                    new = open(out, "rb").read()
                    os.remove(out)
            elif kind == "snd":
                if job.get("strip") and set(job) == {"strip"}:
                    new = data[job["strip"]:]
                else:
                    if not ff:
                        skipped.append(f"{rel} (ffmpeg not found)")
                        continue
                    os.makedirs(tmp, exist_ok=True)
                    out = os.path.join(tmp, "x" + os.path.splitext(full)[1].lower())
                    a = [ff, "-y", "-v", "error", "-i", full]
                    if job.get("mono"):
                        a += ["-ac", "1"]
                    if job.get("rate"):
                        a += ["-ar", str(job["rate"])]
                    a += (["-c:a", "pcm_s16le"] if out.endswith(".wav") else
                          ["-c:a", "libmp3lame", "-q:a", "2", "-id3v2_version", "0", "-map_metadata", "-1"]) + [out]
                    res = subprocess.run(a, capture_output=True, text=True)
                    if res.returncode or not os.path.exists(out):
                        skipped.append(f"{rel} (ffmpeg: {res.stderr.strip()[-100:]})")
                        continue
                    new = open(out, "rb").read()
                    os.remove(out)
            if not new:
                continue
            # only the original is kept: a backup that exists already (an earlier fix of this run, or a run
            # before) is never overwritten; a renamed file's original is kept under its original name
            if not was_fixed(rel) or full in orig_rel:
                _backup_in_mod(root, orig_rel.get(full, rel), full, plugin_name, FEATURE_OF.get(kind, "converted"))
            m.replace_asset_in_place(full, new)
            mark_fixed(rel)
            done += 1
        except OSError as e:
            skipped.append(f"{rel} ({e})")
    shutil.rmtree(tmp, ignore_errors=True)
    cache.save()
    return done, skipped


# ---------------------------------------------------------------------------------------------------------
# <plugin>.bugreport.txt: what is wrong with a plugin ON ITS OWN (not conflicts with other mods), ready to
# post on the mod's page. Each tool owns one section and rewrites only that one.
# ---------------------------------------------------------------------------------------------------------
BUG_SECTION = "======== {} ========"
BUG_END = "======== end of {} ========"


def update_bug_report(path, section, header, lines):
    """Write/replace `section` in the bug report at `path` (the header is rewritten too). An empty `lines`
    removes the section; a report left with no sections is deleted."""
    old = ""
    try:
        with open(path, encoding="utf-8") as f:
            old = f.read()
    except OSError:
        pass
    sections, cur, buf = {}, None, []
    for ln in old.splitlines():
        if ln.startswith("======== end of ") and cur:
            sections[cur] = buf
            cur, buf = None, []
        elif ln.startswith("======== ") and ln.endswith(" ========") and not ln.startswith("======== end of "):
            cur, buf = ln[9:-9], []
        elif cur:
            buf.append(ln)
    if lines:
        sections[section] = list(lines)
    else:
        sections.pop(section, None)
    if not sections:
        try:
            os.remove(path)
        except OSError:
            pass
        return None
    out = list(header) + [""]
    for name in sorted(sections):
        out.append(BUG_SECTION.format(name))
        out += sections[name]
        out.append(BUG_END.format(name))
        out.append("")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(out))
    return path


def bug_report_header(plugin_path, m, mod_folder=None):
    """Name, size, date, masters of a plugin (and its Nexus page), for the top of its bug report."""
    name = os.path.basename(plugin_path)
    try:
        st = os.stat(plugin_path)
        with open(plugin_path, "rb") as f:
            masters = m.plugin_masters(f.read(65536))
        info = f"{st.st_size} bytes, dated {time.strftime('%Y-%m-%d', time.localtime(st.st_mtime))}"
    except OSError:
        masters, info = [], "?"
    nid = nexus_id(mod_folder) if mod_folder else None
    if mod_folder is None:
        try:
            mod_folder, _pl = m.asset_owner_folder(os.path.dirname(plugin_path), name)
            nid = nexus_id(mod_folder) if mod_folder else None
        except Exception:
            nid = None
    return [f"Bug report for {name}",
            f"Plugin: {name} ({info})"] + \
        ([f"Mod page: https://www.nexusmods.com/morrowind/mods/{nid}"] if nid else []) + [
            "Masters: " + (", ".join(masters) if masters else "none"),
            f"Generated {time.strftime('%Y-%m-%d %H:%M')} by mwdialog_check / vortex_tidy (Morrowind + MWSE + MGE XE).",
            "Only problems the plugin has on its own are listed (not conflicts with other mods).",
            "Paths are relative to Data Files."]


def nexus_id(folder):
    """The Nexus mod id in a Vortex folder name ('MUSE 2.02-46200-2-02-1593543300' -> '46200'), or None."""
    name = os.path.basename(folder.rstrip("\\/"))
    for pat in (r" (\d{2,7}) \S+ \d{4}-\d\d-\d\dT\d\d-\d\dZ \w+$",       # 'Name 56060 1.0 2026-10-17T08-23Z abc'
                r"-(\d{2,7})-(?:[\w.]+-)*\d{9,11}$",                         # 'Name-46200-2-02-1593543300'
                r"-(\d{2,7})-[\w.\- ()]+$",                                 # 'Name-42009-2-1', '...-0-5-2RC (1)'
                r"-(\d{2,7})-?$"):                                            # 'AnimatedSoulgemsV0_4-25278' 
        mm = re.search(pat, name)
        if mm:
            return mm.group(1)
    return None


def bug_report_path(data_dir, game_dir, plugin_name, m):
    """<mod folder>\\bugreports\\<plugin name>.bugreport.txt (Vortex), else <game>\\bugreports\\."""
    mod = None
    try:
        mod, _pl = m.asset_owner_folder(data_dir, plugin_name)
    except Exception:
        mod = None
    nid = nexus_id(mod) if mod else None
    base = os.path.splitext(plugin_name)[0] + (f" [Nexus {nid}]" if nid else "") + ".bugreport.txt"
    return os.path.join(mod or game_dir, "bugreports", base)
