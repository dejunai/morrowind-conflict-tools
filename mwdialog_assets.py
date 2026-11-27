"""Asset health for mwdialog_check --asset-check (reports) and --fix (repairs). Loose files in Data Files only
(BSA contents can't be changed; their models are read for texture references).

Checks, and what --fix does:
  DDS a DirectX 8 game can't read (DX10/BC7 header) ...... ERROR  converted to DXT (texconv)
  DDS shorter than its header says (truncated) ........... ERROR  report only (reinstall the mod)
  DDS without mipmaps (64 px and up) that a world model .. WARN   mipmaps generated (texconv)
    draws (each winning model vs the winning texture, loose or BSA; menu / MCM / icon / book / splash /
    effect textures and effect models exempt: MIP_EXEMPT_DEFAULTS, mwdialog_mip_exempt.txt)
  DDS uncompressed 32-bit (256 px and up) ................ WARN   compressed to DXT1/DXT5 (texconv)
  DDS not a power of two / DXT not a multiple of 4 ....... WARN   resized to the nearest power of two (texconv)
  NIF/KF that isn't a Morrowind file (not 4.0.0.2) ....... ERROR  report only
  absolute texture path inside a NIF ....................... ERROR  rewritten to a normal relative path
  empty (0-byte) asset ................................... ERROR  moved to Off when a BSA has the real file
  file name with non-ASCII characters .................... ERROR  report only (plugins/models name it)
  stereo sound under Sound\\ (3D sounds must be mono) ..... WARN   down-mixed to mono (ffmpeg)
  sound at an unusual sample rate (or over 48 kHz) ....... WARN   resampled to 44.1 kHz (ffmpeg)
  x*.kf animation without its x*.nif ..................... WARN   report only
  creature/NPC model whose Bounding Box is under 2 units . ERROR  moved to its mod's Off\\<plugin>\\broken\\ (the
    wide or 1.25 high (a hit's blood splash divides by       next copy, or a BSA's, is used); in a BSA: WARN only
    zero: actor_box_check, the deployed copy only)
  texture or sound nothing refers to ..................... INFO   moved to the mod's Off\\<plugin>\\unused assets\\ (not deployed)
Originals of changed files go to <mod>\\Off\\<plugin>\\<reason>\\<path> (backup_asset_original). Unused files are moved
(not copied) and listed in mwdialog_unused_assets.txt, which --restore-unused uses to put them back.
Not checked: mesh vertex counts (the 4.0.0.2 format can't exceed 65535) and folder-name case duplicates
(the same folder on Windows)."""
import os, re, struct, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mwdialog_backup as MB  # noqa: E402
import mwdialog_console as MC  # noqa: E402
import mwdialog_offlayout as OL  # noqa: E402
import mwdialog_paths as MP  # noqa: E402
import mwdialog_staged as MS  # noqa: E402
import mwdialog_text as MT  # noqa: E402
print = MT.printer()  # noqa: A001

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
                ".htm", ".css", ".mwscript",
                ".omw", ".omwscripts")      # OpenMW Lua hosted by omw2mwse: main.lua.omw, <Mod>.omwscripts


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


def nif_links_past_end(data):
    """[header's block count, block a node points at] when a node points at a block number at or past the count in
    the header, else None. The game builds only that many blocks and crashes following the link (a model cut down
    from another without renumbering its links). Checked on every model of an 840-plugin install, BSAs included:
    it flags only models broken that way."""
    if not data.startswith(NIF_HEAD):
        return None
    from mwdialog_footing import BLOCK_RE, NODE_TYPES, SHAPE

    def u32(p):
        return struct.unpack_from("<I", data, p)[0]
    try:
        count = u32(data.index(b"\n") + 5)
    except (ValueError, struct.error):
        return None
    blocks, after = [], None
    for found in BLOCK_RE.finditer(data):
        size, word = u32(found.start()), found.group(2)
        if size > len(word) or found.start() == after:
            continue                             # a name spelt like a type, inside the block just found
        after = found.start() + 4 + size
        blocks.append((word[:size], after))
    top = -1
    for kind, p in blocks[:count]:
        if kind not in NODE_TYPES:
            continue
        try:
            p += 4 + u32(p) + 8                  # name, extra data, controller
            p += 2 + 52 + 12                     # flags, transform, velocity
            n = u32(p)
            links = list(struct.unpack_from(f"<{n}i", data, p + 4)) if n < 64 else []     # properties
            p += 4 + 4 * n
            p += 4 + (64 if u32(p) else 0)       # bounding box
            if kind == SHAPE:
                links += struct.unpack_from("<i", data, p)                                  # its data
            else:
                n = u32(p)
                links += struct.unpack_from(f"<{n}i", data, p + 4) if n < 4096 else ()       # children
        except (struct.error, IndexError):
            continue
        # a link under -1 means this scan mislaid the block (a string ending in a type name, read as the type), so
        # its "links" are other bytes; a real node's links are -1 (none) or block numbers
        if any(x < -1 for x in links):
            continue
        # a link far past the end (over 1024 past the count) is text read as a number, not a real link: a cut-down
        # model's links stay near its original block count
        top = max([top] + [x for x in links if 0 <= x < count + 1024])
    return [count, top] if top >= count else None


BROKEN_MODELS = []          # (rel, what is done about it): repeated at the end of the run, where it isn't missed


def broken_models_notice(out=None):
    """The last lines of a run: every broken model found (a line lost in a long report is a crash in game)."""
    if not BROKEN_MODELS:
        return
    out = out or (lambda t: print(t, file=sys.stderr, flush=True))
    found = dict(BROKEN_MODELS)
    out(f"\n*** {len(found)} broken model(s): the game crashes loading each one:")
    for rel, what in found.items():
        out(f"    {rel}: {what}")
    BROKEN_MODELS.clear()


def _is_stand_in(b, m, rel):
    try:
        return b == m.stand_in_bytes(rel)
    except OSError:                         # no dummy folder: no stand-in was ever put anywhere
        return False


def _broken_original(root, rel):
    """True when <mod>\\Off\\<plugin>\\broken\\<rel> (or an older layout's) keeps a model with links past its end:
    the file at rel is then the stand-in --fix put in its place."""
    for base in OL.reason_dirs(root, "broken"):
        try:
            with open(os.path.join(base, rel), "rb") as f:
                if nif_links_past_end(f.read()):
                    return True
        except OSError:
            pass
    return False


CACHE_FILE = "mwdialog_asset_cache.json"           # the old format: converted once, then renamed
CACHE_DB = "mwdialog_asset_cache.sqlite"
MIGRATED_SUFFIX = ".migrated"
# what vortex_tidy found in each mod: tidy3:<mod folder>|<path in the mod>; raise the number when a check is
# added or made stricter, and every file is looked at again once
TIDY_KEY = "tidy3:"
KNOWN_PREFIXES = {"clean2", "seen2", "clean", "seen", "texh", "tex2", "nif", "bsa", "bsa2", "snd", "refs", "names",
                  "fixed", "tidy3"}
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
        self.path = MP.state_path(game_dir, CACHE_DB)
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
        old = MP.state_path(self.game_dir, CACHE_FILE)
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
            "past": nif_links_past_end(b),
            "tn": m.nif_texture_refs(b)}


def model_facts_cached(cache, key, full, st, m, generated=(), need_tn=False):
    """model_facts for the model at Data Files path `key` (norm_rel) with os.stat `st`: vortex_tidy's record of
    the same file (same size and date: a Vortex hard link) or this cache's when it is unchanged, else read.
    A stand-in this tool made is always read. need_tn: an entry from the old cache, without the texture
    paths, is read again. None if the file can't be read."""
    stamp = stamp_of(st)
    if key not in generated and cache is not None:
        t = cache.tidy_lookup(key, stamp)
        if t is not None and isinstance(t.get("f"), dict) and "tn" in t["f"] and "past" in t["f"]:
            return t["f"]
        f = cache.get("nif:" + key, stamp)
        # an old entry without "tn" whose noshape came from an older, stricter test, or from before the
        # links-past-the-end check ("past"): read it again
        if f is not None and "past" in f and ("tn" in f or not (need_tn or f.get("noshape"))):
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


def _over_texture_cap(facts, m):
    """A texture cached clean while the edge cap was off (or larger) that the current cap would reduce."""
    return bool(facts) and facts[0] == "dds" and max(facts[1][0], facts[1][1]) > m.TEXTURE_MAX_EDGE


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


FEATURE_OF = {"snd": "converted sounds", "tex": "converted textures", "keys": "fixed text keys",
              "abs": "fixed texture paths", "broken": "broken", "orphan": "orphaned animations",
              "unused": "unused assets", "splash": "converted splash screens"}     # Off reasons (docs/dev/OFF-LAYOUT.md)


def broken_dest(root_or_mod, rel, sub="broken", plugin=None):
    """<mod>\\Off\\<plugin>\\<reason: broken, orphaned animations...>\\<rel>."""
    import mwdialog_check as _m
    return _m.off_dest(root_or_mod, sub, plugin, rel)


UI_TEX_RE = re.compile(r"^(?:data files[\\/])?(?:textures[\\/](?:menu_|tx_menu|tx_cursor|compass|target|scroll|"
                       r"(?:bookart|splash|levelup|birthsigns?|mwse|ui|menu)[\\/])|icons[\\/]|bookart[\\/]|splash[\\/])",
                       re.I)


def ui_texture(rel):
    """A menu / book / splash / icon picture: drawn at its own size on screen, so it keeps its size, its
    pixels (no compression) and needs no mipmaps; only the over-2048 limit applies."""
    return bool(UI_TEX_RE.search(rel.replace("/", "\\")))


# ---------------------------------------------------------------------------------------------------------
# Mipmaps: only textures a WORLD model draws need them (seen at a distance, shrunk on screen). Pictures drawn
# at their own size (menus, MCM logos, icons, book art, splash screens, cursors) and effect textures (spell
# particles, glows, blood sprites, whose look depends on every pixel) are left alone. Patterns are fnmatch
# globs on the lowercase path with backslashes: "path" ones on the whole path under Data Files
# (textures\..., meshes\...), "name" ones on the file name alone. "*" also crosses folders.
# Add or remove your own in mwdialog_mip_exempt.txt next to Morrowind.ini, one per line:
#     texture: textures\my_hud\*        (another texture path glob)
#     texture-name: *_sprite*           (another texture file-name glob)
#     mesh: meshes\my_spells\*          (models whose textures don't count, like the effect models)
#     mesh-name: *_spell*
#     !texture-name: *splash*           (a leading ! drops a default pattern)
# ---------------------------------------------------------------------------------------------------------
MIP_EXEMPT_RECORD = "mwdialog_mip_exempt.txt"
MIP_MIN_EDGE = 64                      # smaller textures don't get the "no mipmaps" finding at all
MIP_EXEMPT_DEFAULTS = {
    # textures never mip-flagged, whoever uses them
    "texture": ("icons\\*", "bookart\\*", "splash\\*", "mwse\\*", "*\\mwse\\*", "*\\mcm\\*",
                "textures\\menu\\*", "textures\\menus\\*", "textures\\ui\\*", "textures\\gui\\*",
                "textures\\hud\\*", "textures\\levelup\\*", "textures\\splash\\*", "textures\\bookart\\*",
                "textures\\birthsigns\\*", "textures\\birthsign\\*", "textures\\cursor*\\*",
                "textures\\vfx\\*", "textures\\fx\\*", "textures\\effects\\*", "textures\\*\\vfx\\*"),
    "texture-name": ("menu_*", "tx_menu*", "*logo*", "*splash*", "cursor*", "tx_cursor*", "compass*",
                     "tx_compass*", "levelup*", "vfx_*", "*_vfx*",
                     "tx_*fx*", "fx_*", "tx_blood*", "blood_*", "tx_glow*", "*_glowsheet*",
                     "*spritesheet*"),
    # models that aren't world objects: their textures don't count as "used by a world model"
    "mesh": ("meshes\\e\\*", "meshes\\vfx\\*", "meshes\\fx\\*", "meshes\\*\\vfx\\*", "meshes\\mwse\\*",
             "meshes\\*\\mwse\\*", "meshes\\menu\\*", "meshes\\ui\\*"),
    "mesh-name": ("vfx_*", "*_vfx*", "fx_*"),
}
_MIP_RULES = {}


def mip_rules(game_dir=None):
    """{kind: tuple of globs}: the defaults, changed by mwdialog_mip_exempt.txt in game_dir (read once)."""
    key = os.path.normcase(os.path.abspath(game_dir)) if game_dir else ""
    if key in _MIP_RULES:
        return _MIP_RULES[key]
    rules = {k: list(v) for k, v in MIP_EXEMPT_DEFAULTS.items()}
    if game_dir:
        try:
            with open(MP.state_path(game_dir, MIP_EXEMPT_RECORD), encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            lines = []
        for ln in lines:
            s = ln.strip()
            if not s or s.startswith(("#", ";")) or ":" not in s:
                continue
            drop = s.startswith("!")
            kind, _sep, pat = s.lstrip("!").partition(":")
            kind, pat = kind.strip().lower(), pat.strip().lower().replace("/", "\\")
            if kind not in rules or not pat:
                continue
            if drop:
                rules[kind] = [p for p in rules[kind] if p != pat]
            elif pat not in rules[kind]:
                rules[kind].append(pat)
    out = {k: tuple(v) for k, v in rules.items()}
    _MIP_RULES[key] = out
    return out


def _dfrel(rel):
    """A path under Data Files as the rules see it: lowercase, backslashes, no 'data files\\' in front."""
    p = rel.replace("/", "\\").lower().lstrip("\\")
    return p[11:] if p.startswith("data files\\") else p


def mip_exempt_texture(rel, rules=None):
    """The pattern that keeps texture `rel` (path under Data Files, with its top folder) from ever needing
    mipmaps, or None. Only Textures\\ can need them: icons, book art and splash screens never do."""
    import fnmatch
    rules = rules or mip_rules()
    p = _dfrel(rel)
    if not p.startswith("textures\\"):
        return p.split("\\", 1)[0] + "\\*"
    if ui_texture(p):
        return "ui texture"
    for pat in rules["texture"]:
        if fnmatch.fnmatchcase(p, pat):
            return pat
    name = os.path.splitext(p.rsplit("\\", 1)[-1])[0]
    for pat in rules["texture-name"]:
        if fnmatch.fnmatchcase(name, pat):
            return pat
    return None


def mip_exempt_mesh(rel, rules=None):
    """The pattern that makes model `rel` (path under Data Files, 'meshes\\...'; a path under Meshes is taken
    as one) an effect / UI model whose textures don't count, or None."""
    import fnmatch
    rules = rules or mip_rules()
    p = _dfrel(rel)
    if not p.startswith("meshes\\"):
        p = "meshes\\" + p
    for pat in rules["mesh"]:
        if fnmatch.fnmatchcase(p, pat):
            return pat
    name = os.path.splitext(p.rsplit("\\", 1)[-1])[0]
    for pat in rules["mesh-name"]:
        if fnmatch.fnmatchcase(name, pat):
            return pat
    return None


def tex_stem(name):
    """A texture name as a model gives it -> its path under Textures without extension (the game swaps in
    the .dds of a .tga/.bmp name), lowercase, backslashes."""
    s = name.replace("/", "\\").lower().strip().lstrip("\\")
    i = s.find("textures\\")
    if i != -1:
        s = s[i + 9:]
    return os.path.splitext(s)[0]


def needs_mips(tf):
    """True for texture facts (texture_facts) of a DDS with one level only and an edge of MIP_MIN_EDGE+."""
    if not tf or tf[0] != "dds":
        return False
    w, h, mips = tf[1][0], tf[1][1], tf[1][2]
    return mips <= 1 and max(w, h) >= MIP_MIN_EDGE


def read_try_archive_first(ini_path):
    """Morrowind.ini's TryArchiveFirst: 0 (default) the newer of the loose file and the BSA's copy wins,
    1 the BSA's copy, -1 loose files only."""
    if not ini_path:
        return 0
    try:
        with open(ini_path, encoding="cp1252", errors="replace") as f:
            for line in f:
                k, sep, v = line.partition("=")
                if sep and k.strip().lower() == "tryarchivefirst":
                    return int(v.strip().split(";")[0] or 0)
    except (OSError, ValueError):
        pass
    return 0


class WinningFiles:
    """Which copy of a file under one top folder (meshes, textures) the game loads: a loose file in Data
    Files or one in a registered BSA. Vanilla Morrowind (TryArchiveFirst=0) takes the NEWEST by date: of
    the BSAs, the latest-dated one (same date: the one registered later); then the loose file wins unless
    that BSA is newer than it. TryArchiveFirst=1: a BSA copy first; -1: loose only."""

    def __init__(self, top, loose, bsa_paths, try_archive_first=0, stat=os.stat):
        self.top = top
        self.loose = loose                       # rel under top (lowercase, backslashes) -> full path
        self.taf = try_archive_first
        self.stat = stat
        self.bsa = {}                            # rel -> (bsa path, offset, size, bsa mtime, order)
        import mwdialog_check as _m
        pre = top + "\\"
        for order, b in enumerate(bsa_paths):
            try:
                bt = os.stat(b).st_mtime
                idx = _m.bsa_index(b)
            except (OSError, struct.error, getattr(_m, "FormatError", ValueError)):
                continue
            for name, (off, size) in idx.items():
                if not name.startswith(pre):
                    continue
                rel = name[len(pre):]
                old = self.bsa.get(rel)
                if old is None or (bt, order) >= (old[3], old[4]):
                    self.bsa[rel] = (b, off, size, bt, order)

    def names(self):
        return set(self.loose) | (set(self.bsa) if self.taf != -1 else set())

    def winner(self, rel):
        """("loose", full path) or ("bsa", (bsa path, offset, size)) or None."""
        lp = self.loose.get(rel)
        bp = self.bsa.get(rel) if self.taf != -1 else None
        if lp is None and bp is None:
            return None
        if bp is None:
            return ("loose", lp)
        if lp is None or self.taf == 1:
            return ("bsa", bp[:3])
        try:
            lt = self.stat(lp).st_mtime
        except OSError:
            return ("bsa", bp[:3])
        return ("bsa", bp[:3]) if int(bp[3]) > int(lt) else ("loose", lp)


def texture_facts_cached(cache, key, full, st, m, generated=()):
    """texture_facts of the loose DDS at Data Files path `key` (norm_rel): vortex_tidy's record of the same
    file, or this cache's tex2: entry when unchanged, else its header is read (and cached)."""
    stamp = stamp_of(st)
    gen = key in generated
    if not gen and cache is not None:
        t = cache.tidy_lookup(key, stamp)
        if t is not None and t.get("t"):
            return t["t"]
        tf = cache.get("tex2:" + key, stamp)
        if tf is not None:
            return tf
    try:
        with open(full, "rb") as f:
            head = f.read(148)
    except OSError:
        return None
    tf = texture_facts(head, m)
    if cache is not None and not gen:
        cache.put("tex2:" + key, stamp, tf)
    return tf


def bsa_texture_facts(cache, bsa, off, size, rel, m):
    """texture_facts of a DDS inside a BSA, cached while the BSA's size and date are the same."""
    try:
        st = os.stat(bsa)
    except OSError:
        return None
    key, stamp = "tex2b:" + os.path.basename(bsa).lower() + "|" + rel, stamp_of(st)
    tf = cache.get(key, stamp) if cache is not None else None
    if tf is not None:
        return tf
    try:
        with open(bsa, "rb") as f:
            f.seek(off)
            head = f.read(min(148, size))
    except OSError:
        return None
    tf = texture_facts(head, m)
    if cache is not None:
        cache.put(key, stamp, tf)
    return tf


def mip_pairs(A, tree, data_dir, m, cache, generated=(), ini_path=None, game_dir=None):
    """The per-pair check of the whole install: every WINNING model (loose or BSA, by the game's override
    rules) that is a world model (not an effect / UI model), each texture it names resolved to the winning
    file (the .dds of a .tga/.bmp name first), and those without mipmaps that aren't exempt. A texture pack
    for existing models is covered here (tidy only judges a mod's textures by its own models).
    Returns (loose [(rel under Data Files, full, [models])], in_bsa [(rel, bsa name, [models])], stats)."""
    rules = mip_rules(game_dir)
    taf = read_try_archive_first(ini_path)
    bsas = list(getattr(A, "bsa_paths", ()))
    st_of = tree.stat if tree is not None else os.stat
    loose_tex = {}
    for top, rel, full in (tree.asset_files(("textures",)) if tree is not None else ()):
        loose_tex.setdefault(norm_rel(rel)[len("textures\\"):], full)
    meshes = WinningFiles("meshes", dict(A.mesh_loose), bsas, taf, st_of)
    textures = WinningFiles("textures", loose_tex, bsas, taf, st_of)
    users = {}                                           # texture rel under Textures -> [models]
    stats = {"models": 0, "effect_models": 0, "textures": 0, "exempt": 0}
    for mrel in sorted(meshes.names()):
        if not mrel.endswith(".nif"):
            continue
        if mip_exempt_mesh(mrel, rules):
            stats["effect_models"] += 1
            continue
        win = meshes.winner(mrel)
        if win is None:
            continue
        tn = []
        if win[0] == "loose":
            full = win[1]
            root = os.path.normcase(os.path.abspath(data_dir)) + os.sep
            if os.path.normcase(os.path.abspath(full)).startswith(root):
                try:
                    f = model_facts_cached(cache, norm_rel(os.path.relpath(full, data_dir)), full, st_of(full), m,
                                           generated, need_tn=True)
                except OSError:
                    f = None
                tn = (f or {}).get("tn", [])
            else:
                tn = A.texture_names(mrel)
        else:
            tn = A.bsa_facts(win[1][0]).get("tn", {}).get(mrel, [])
        if not tn:
            continue
        stats["models"] += 1
        for t in tn:
            stem = tex_stem(t)
            ext = os.path.splitext(t)[1].lower()
            for cand in (stem + ".dds",) + ((stem + ext,) if ext and ext != ".dds" else ()):
                if textures.winner(cand) is not None:
                    users.setdefault(cand, []).append("Meshes\\" + mrel)
                    break
    loose_out, bsa_out = [], []
    for trel in sorted(users):
        if not trel.endswith(".dds"):
            continue
        stats["textures"] += 1
        if mip_exempt_texture("textures\\" + trel, rules):
            stats["exempt"] += 1
            continue
        win = textures.winner(trel)
        if win[0] == "loose":
            full = win[1]
            key = "textures\\" + trel
            if key in generated:
                continue
            try:
                tf = texture_facts_cached(cache, key, full, st_of(full), m, generated)
            except OSError:
                continue
            if needs_mips(tf):
                loose_out.append((os.path.relpath(full, data_dir), full, users[trel]))
        else:
            b, off, size = win[1]
            tf = bsa_texture_facts(cache, b, off, size, trel, m)
            if needs_mips(tf):
                bsa_out.append(("Textures\\" + trel, os.path.basename(b), users[trel]))
    return loose_out, bsa_out, stats


# ---------------------------------------------------------------- actor models whose Bounding Box crashes hits
# When a hit draws blood, SplashController::spawnBloodParticle (Morrowind.exe 0x54B8B0) picks a spot on the
# struck actor with rand() % (int)(width / 2) and rand() % (int)(height * 0.8) (integer divides at 0x54B8FF and
# 0x54B954). width and height are the actor's mobile widthRescaled / heightRescaled: 16-bit, 1/32 units, set from
# the model's "Bounding Box" node (0x55A4B0: (int)(value * 32) stored in 16 bits): width = center.y + extent.y,
# height = 2 * extent.z (checked against 15 creatures in a crash dump; unscaled, the reference's scale is not
# applied). A box under 2 units wide or 1.25 units high makes a divisor 0: EXCEPTION_INT_DIVIDE_BY_ZERO the
# first time a hit on that actor spawns blood (Cliff Racer Remastered 1.3: center.y -81.339, extent.y 81.601,
# width 0.262). A negative width wraps in the 16 bits to a large value (no crash; only a width of 2048 units or
# more could wrap back under 64). No "Bounding Box" node: the engine uses the model's own bounds; not judged.
# NPCs: the engine scales the box by the race's height and weight first (0x54CC10), so their check is a guide.
ACTOR_BOX_TAGS = ("CREA", "NPC_")
BOX_NODE_RE = re.compile(rb"([\x02-\x40])\x00\x00\x00(Ni[A-Za-z]{1,62})\x0c\x00\x00\x00bounding box", re.I)
_F32_0_8 = struct.unpack("<f", struct.pack("<f", 0.8))[0]           # the engine's float constant 0.8


def nif_bounding_box(data):
    """((center x, y, z), (extent x, y, z)) of a model's "Bounding Box" node's box (its bounding volume of
    type 1, a box), or None: not a Morrowind model, no such node, or the node has no box."""
    if not data.startswith(NIF_HEAD):
        return None
    for found in BOX_NODE_RE.finditer(data):
        if found.group(1)[0] != len(found.group(2)):
            continue                                  # not a block's type name followed by the node's name
        p = found.end()
        try:
            p += 8 + 2 + 12 + 36 + 4 + 12             # extra data, controller, flags, translation, rotation,
            n = struct.unpack_from("<I", data, p)[0]  # scale, velocity; then the properties
            if n > 64:
                continue
            p += 4 + 4 * n
            has, kind = struct.unpack_from("<II", data, p)
            if has != 1 or kind != 1:
                continue
            center = struct.unpack_from("<3f", data, p + 8)
            extent = struct.unpack_from("<3f", data, p + 8 + 12 + 36)
        except struct.error:
            continue
        return center, extent
    return None


def _ftol(x):
    """The x87 float-to-int the game uses: truncated toward zero; NaN or out of range gives 0x80000000."""
    if x != x or x >= 2147483648.0 or x < -2147483648.0:
        return -2147483648
    return int(x)


def actor_box_divisors(box):
    """What spawnBloodParticle divides by for a model with this Bounding Box: {"width", "height" (units),
    "raw_w", "raw_h" (the 16-bit values the game keeps), "div_w", "div_h"}. A divisor of 0 crashes."""
    (_cx, cy, _cz), (_ex, ey, ez) = box
    f32 = (lambda v: struct.unpack("<f", struct.pack("<f", v))[0] if abs(v) < 3.4e38 else v)
    width, height = f32(cy + ey), f32(2.0 * ez)
    raw_w, raw_h = _ftol(width * 32.0) & 0xFFFF, _ftol(height * 32.0) & 0xFFFF
    return {"width": width, "height": height, "raw_w": raw_w, "raw_h": raw_h,
            "div_w": _ftol(raw_w * 0.03125 * 0.5), "div_h": _ftol(raw_h * 0.03125 * _F32_0_8)}


def actor_box_problem(box):
    """None when hits on an actor with this Bounding Box are safe, else what is wrong (a short text)."""
    if box is None:
        return None
    d = actor_box_divisors(box)
    bad = []
    if d["div_w"] == 0:
        bad.append(f"{d['width']:.3g} units wide (the game needs at least 2)")
    if d["div_h"] == 0:
        bad.append(f"{d['height']:.3g} units high (the game needs at least 1.25)")
    return " and ".join(bad) or None


def actor_models(world, A):
    """{model under Meshes (lowercase): [who uses it]} for the winning CREA and NPC_ records with a model (an
    NPC's MODL is its skeleton, when set). Each model's x-prefixed twin (the one the game animates) is checked
    with it."""
    out = {}
    for (tag, _rid), vers in getattr(world, "models", {}).items():
        if tag not in ACTOR_BOX_TAGS or not vers:
            continue
        win = vers[-1]
        if win[3]:
            continue                                  # deleted
        v = (win[2] or {}).get(("MODL", "mesh"))
        if not v or not v.strip():
            continue
        rel = A.norm(v)
        if rel.endswith(".nif"):
            out.setdefault(rel, []).append(f"{tag} '{win[4]}' ({win[1]})")
    return out


def _x_twin(rel):
    """meshes rel (backslashes) of the x-prefixed twin the game animates an actor with, or None."""
    d, _, f = rel.rpartition("\\")
    if f.startswith("x"):
        return None
    return (d + "\\" if d else "") + "x" + f


def actor_box_check(world, A, data_dir, cache=None, ini_path=None, stat=os.stat, generated=()):
    """The deployed (winning) model of every creature and NPC, loose or in a BSA, by the game's override rules
    (WinningFiles), and its x-prefixed twin: a Bounding Box that makes spawnBloodParticle divide by zero (see
    above). Returns (findings [(severity, rel, message)], fixes [("actorbox", full, rel under Data Files,
    why)]): a loose model in Data Files is moved out by --fix (apply: its Vortex mod's Off\\<plugin>\\broken\\,
    found by the hard link), so the next mod's copy (after Deploy) or the BSA's is used; one in a BSA can only
    be reported."""
    users = actor_models(world, A)
    if not users:
        return [], []
    meshes = WinningFiles("meshes", dict(getattr(A, "mesh_loose", {})), list(getattr(A, "bsa_paths", ())),
                          read_try_archive_first(ini_path), stat)
    names = meshes.names()
    data_abs = os.path.normcase(os.path.abspath(data_dir)) + os.sep
    found, fixes, seen = [], [], set()
    for base in sorted(users):
        who = users[base][0] + (f" (+{len(users[base]) - 1} more)" if len(users[base]) > 1 else "")
        for rel in (base, _x_twin(base)):
            if not rel or rel in seen or rel not in names:
                continue
            seen.add(rel)
            win = meshes.winner(rel)
            if win is None:
                continue
            box = None
            if win[0] == "loose":
                full = win[1]
                try:
                    st = stat(full)
                    key, stamp = "abox:" + norm_rel(full), stamp_of(st)
                    got = cache.get(key, stamp) if cache is not None and key not in generated else None
                    if got is None:
                        with open(full, "rb") as f:
                            b = nif_bounding_box(f.read())
                        got = [list(b[0]), list(b[1])] if b else []
                        if cache is not None:
                            cache.put(key, stamp, got)
                except OSError:
                    continue
                box = (tuple(got[0]), tuple(got[1])) if got else None
            else:
                bsa, off, size = win[1]
                try:
                    st = os.stat(bsa)
                    key = "aboxb:" + os.path.basename(bsa).lower() + "|" + rel
                    stamp = stamp_of(st)
                    got = cache.get(key, stamp) if cache is not None else None
                    if got is None:
                        with open(bsa, "rb") as f:
                            f.seek(off)
                            b = nif_bounding_box(f.read(size))
                        got = [list(b[0]), list(b[1])] if b else []
                        if cache is not None:
                            cache.put(key, stamp, got)
                except OSError:
                    continue
                box = (tuple(got[0]), tuple(got[1])) if got else None
            if box is None:
                continue
            what = actor_box_problem(box)
            d = actor_box_divisors(box)
            if what is None:
                if d["width"] < 0:
                    found.append(("INFO", "Meshes\\" + rel, f"actor model ({who}): its Bounding Box reaches only "
                                  f"behind the model (width {d['width']:.3g}); the game wraps it to "
                                  f"{d['raw_w']} / 32, so no crash"))
                continue
            why = f"Bounding Box {what}"
            if win[0] == "loose" and os.path.normcase(os.path.abspath(win[1])).startswith(data_abs):
                drel = os.path.relpath(win[1], data_dir)
                found.append(("ERROR", drel, f"actor model ({who}): {why}; the game divides by zero (crash) the "
                              f"first time a hit on it spawns blood. --fix moves it to its mod's "
                              f"Off\\<plugin>\\broken\\ (found by Vortex's hard link); then Deploy in Vortex, so "
                              f"the next mod's copy is used (until then, or with none, a BSA's copy)"))
                fixes.append(("actorbox", win[1], drel, why))
                BROKEN_MODELS.append((drel, "--fix moves it to its mod's Off\\<plugin>\\broken\\; then Deploy in "
                                            "Vortex so the next mod's copy (or a BSA's) is used"))
            elif win[0] == "loose":
                found.append(("WARN", "Meshes\\" + rel, f"actor model ({who}) in {win[1]}: {why}; the game "
                              f"divides by zero (crash) when a hit on it spawns blood. Not in Data Files: left "
                              f"as it is"))
            else:
                found.append(("WARN", "Meshes\\" + rel, f"actor model ({who}) in {os.path.basename(win[1][0])}: "
                              f"{why}; the game divides by zero (crash) when a hit on it spawns blood. A BSA "
                              f"can't be changed: install a loose copy with a proper box"))
    return found, fixes


def _free_dest(dest):
    """dest, or a dated name beside it when a different file is there already."""
    if not os.path.exists(dest):
        return dest
    stem, ext = os.path.splitext(dest)
    new, n = f"{stem}.{time.strftime('%Y%m%d-%H%M%S')}{ext}", 2
    while os.path.exists(new):
        new, n = f"{stem}.{time.strftime('%Y%m%d-%H%M%S')}-{n}{ext}", n + 1
    return new


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


# ---------------------------------------------------------------------------------------------------------
# Loading-screen splashes: the game shows only TGAs (a DDS-only Splash folder showed none), and reads RLE TGAs. A
# 4096x2048 one is 24-32 MB in memory: wider than 2048 is cut to 2048 (1024 lost too much detail). A loading screen
# is drawn full-screen over nothing, so an alpha channel has no use: every splash is 24-bit (230 of 706 in one install
# were 32-bit). One at most 2048 wide is only re-encoded - alpha dropped, RLE when smaller - and only when that saves
# at least SPLASH_MIN_GAIN of the file.
# ---------------------------------------------------------------------------------------------------------
SPLASH_MAX_WIDTH = 2048
SPLASH_MIN_GAIN = 0.10
SPLASH_RULE = 3                       # in the asset cache: a splash checked under this rule is not decoded again
SPLASH_IMAGE_EXTS = (".tga", ".dds", ".bmp", ".png", ".jpg", ".jpeg")


def _tga_head(path):
    """(width, bits per pixel) of a TGA, (0, 0) when unreadable."""
    try:
        with open(path, "rb") as f:
            head = f.read(18)
        return (struct.unpack_from("<H", head, 12)[0], head[16]) if len(head) == 18 else (0, 0)
    except OSError:
        return 0, 0


def _tga_width(path):
    return _tga_head(path)[0]


def _tga_read(data):
    """(width, height, bytes per pixel, rows top to bottom) of an uncompressed or RLE true-colour TGA."""
    id_len, cmap_type, kind = data[0], data[1], data[2]
    cmap_len, cmap_depth = struct.unpack_from("<H", data, 5)[0], data[7]
    w, h = struct.unpack_from("<HH", data, 12)
    depth, desc = data[16], data[17]
    if cmap_type or kind not in (2, 10) or depth not in (24, 32):
        raise ValueError(f"not a 24/32-bit true-colour TGA (type {kind}, {depth} bits)")
    bpp = depth // 8
    pos = 18 + id_len + cmap_len * ((cmap_depth + 7) // 8)
    need = w * h * bpp
    if kind == 2:
        pixels = data[pos:pos + need]
    else:
        out = bytearray()
        while len(out) < need:
            head = data[pos]
            pos += 1
            count = (head & 0x7F) + 1
            if head & 0x80:
                out += data[pos:pos + bpp] * count
                pos += bpp
            else:
                out += data[pos:pos + count * bpp]
                pos += count * bpp
        pixels = bytes(out[:need])
    rows = [pixels[i * w * bpp:(i + 1) * w * bpp] for i in range(h)]
    if not desc & 0x20:                       # stored bottom row first
        rows.reverse()
    return w, h, bpp, rows


def _tga_rle_row(row, bpp):
    out = bytearray()
    n = len(row) // bpp
    px = [row[i * bpp:(i + 1) * bpp] for i in range(n)]
    i = 0
    while i < n:
        j = i + 1
        while j < n and j - i < 128 and px[j] == px[i]:
            j += 1
        if j - i > 1:
            out.append(0x80 | (j - i - 1))
            out += px[i]
            i = j
            continue
        j = i + 1
        while j < n and j - i < 128 and not (j + 1 < n and px[j] == px[j + 1]):
            j += 1
        out.append(j - i - 1)
        out += b"".join(px[i:j])
        i = j
    return bytes(out)


def _tga_write(w, h, bpp, rows):
    """Bottom-up like the game's own splashes; RLE when that is smaller."""
    bottom_up = rows[::-1]
    raw = b"".join(bottom_up)
    rle = b"".join(_tga_rle_row(r, bpp) for r in bottom_up)
    kind, body = (10, rle) if len(rle) < len(raw) else (2, raw)
    return struct.pack("<BBBHHBHHHHBB", 0, 0, kind, 0, 0, 0, 0, 0, w, h, bpp * 8, 8 if bpp == 4 else 0) + body


def _texconv_tga(path, texconv, tmp, width=None, height=None):
    """(width, height, bytes per pixel, rows) of `path` converted by texconv to a 32-bit TGA, resized if asked."""
    a = [texconv, "-nologo", "-y", "-ft", "tga", "-f", "B8G8R8A8_UNORM", "-if", "FANT", "-o", tmp]
    if width:
        a += ["-w", str(width), "-h", str(height)]
    res = run_tool(a + [path])
    out = os.path.join(tmp, os.path.splitext(os.path.basename(path))[0] + ".tga")
    if res.returncode or not os.path.exists(out):
        raise OSError("texconv: " + (res.stdout + res.stderr).strip()[-100:])
    with open(out, "rb") as f:
        result = _tga_read(f.read())
    os.remove(out)
    return result


def keep_full_size(m, textures=False, splash=False):
    """--no-reduce-textures / --no-reduce-splash: m (the mwdialog_check module) reduces no texture, and
    splashes keep their width; other texture and splash repairs still apply."""
    global SPLASH_MAX_WIDTH
    if textures:
        m.TEXTURE_MAX_EDGE = 1 << 30
    if splash:
        SPLASH_MAX_WIDTH = None


def splash_too_wide(width):
    """SPLASH_MAX_WIDTH None: splashes keep their width (MWManager's reduce_splash_2048 = false)."""
    return SPLASH_MAX_WIDTH is not None and width > SPLASH_MAX_WIDTH


def splash_rule():
    """The asset-cache rule a splash was checked under: changes with the width cap, so a toggle rechecks them."""
    return SPLASH_RULE if SPLASH_MAX_WIDTH is not None else -SPLASH_RULE


def splash_target():
    return "RLE TGA" + (f", at most {SPLASH_MAX_WIDTH} wide" if SPLASH_MAX_WIDTH is not None else "")


def splash_needs_texconv(path):
    """A splash that has to be resized or converted (not only re-encoded)."""
    return not path.lower().endswith(".tga") or splash_too_wide(_tga_width(path))


def splash_tga(path, texconv, tmp):
    """A splash image (TGA, DDS, BMP...) as the TGA bytes to ship: at most SPLASH_MAX_WIDTH wide (aspect kept),
    24-bit (a loading screen has no use for alpha), RLE when smaller. A TGA that needs no resizing keeps its pixels."""
    if not splash_needs_texconv(path):
        with open(path, "rb") as f:
            w, h, bpp, rows = _tga_read(f.read())
        if bpp == 4:
            rows = [b"".join(row[i:i + 3] for i in range(0, len(row), 4)) for row in rows]
        return _tga_write(w, h, 3, rows)
    w, h, bpp, rows = _texconv_tga(path, texconv, tmp)
    if splash_too_wide(w):
        w, h, bpp, rows = _texconv_tga(path, texconv, tmp, SPLASH_MAX_WIDTH, max(1, round(h * SPLASH_MAX_WIDTH / w)))
    rows = [b"".join(row[i:i + 3] for i in range(0, len(row), 4)) for row in rows]      # 24-bit
    return _tga_write(w, h, 3, rows)


def run_tool(cmd, timeout=600):
    """texconv / ffmpeg with a time limit: a file that hangs the program counts as a failed conversion."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 1, "", f"timed out after {timeout} s")


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

    _out = MT.printer(builtins.print)

    def print(*a, **k):                            # every status line says how long the check has run
        if k.get("file") is sys.stderr and a:
            a = (f"[{int(_time.time() - _t0)}s] {a[0]}",) + a[1:]
            k["flush"] = True
        _out(*a, **k)
    A = world.assets
    data_dir = os.path.abspath(world.args_data_dir)
    r = world.r
    fixes = []                       # (kind, full, rel, detail)
    print("Asset health: reading textures, models, sounds...", file=sys.stderr)
    MC.set_title("mwdialog_check - asset health")
    MC.begin_count()
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
        if k == 1 or k == len(tex_files) or k % 2000 == 0:
            MC.count_title("mwdialog_check - asset health: textures", k, len(tex_files))
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
        job = {}                            # mipmaps: judged per model below (mip_pairs), not per file
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
    cache = shared_cache(os.path.dirname(data_dir))
    world.text_key_fixes = []
    allm = nif_files + kf_files
    for k, (rel, full) in enumerate(allm, 1):
        if k == 1 or k == len(allm) or k % 2000 == 0:
            MC.count_title("mwdialog_check - asset health: models", k, len(allm))
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
        if facts.get("past"):
            count, top = facts["past"]
            r.add("ERROR", "Data Files", "", "", f"{rel}: broken model: a node in it points at block {top}, but its "
                                                 f"header says it has only {count}; the game crashes loading it. "
                                                 f"--fix keeps it in Off\\...\\broken\\ and puts a stand-in model in "
                                                 f"its place; then run vortex_tidy --apply and Deploy in Vortex, so "
                                                 f"another mod's copy can win")
            fixes.append(("broken", full, rel, "broken model"))
            BROKEN_MODELS.append((rel, "--fix puts a stand-in in its place (original kept in Off\\...\\broken\\); "
                                       "then run vortex_tidy --apply and Deploy in Vortex, so another mod's copy wins"))
            continue
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
    # --- creature and NPC models whose Bounding Box makes a hit crash the game (spawnBloodParticle)
    try:
        box_found, box_fixes = actor_box_check(world, A, data_dir, cache, getattr(world, "ini_path", None),
                                               tree.stat if tree is not None else os.stat, generated)
    except Exception as e:                       # never stop the pass for this check
        print(f"Asset health: actor model check skipped ({e})", file=sys.stderr)
        box_found, box_fixes = [], []
    for sev, rel, msg in box_found:
        r.add(sev, "Data Files", "", "", f"{rel}: {msg}")
    fixes += box_fixes
    # --- mipmaps, per pair: each winning world model and the winning texture it draws (loose or BSA)
    print("Asset health: mipmaps of the textures world models use...", file=sys.stderr)
    try:
        mip_loose, mip_bsa, mst = mip_pairs(A, tree, data_dir, m, cache, generated,
                                            getattr(world, "ini_path", None), os.path.dirname(data_dir))
    except Exception as e:                       # never stop the pass for this check
        print(f"Asset health: mipmap check skipped ({e})", file=sys.stderr)
        mip_loose, mip_bsa, mst = [], [], {}
    tex_jobs = {f[1]: f[3] for f in fixes if f[0] == "tex"}
    for rel, full, users in mip_loose:
        more = f" (+{len(users) - 1})" if len(users) > 1 else ""
        r.add("WARN", "Data Files", "", "", f"{rel}: no mipmaps, and world model {users[0]}{more} draws it "
                                            f"(shimmers at a distance); --fix generates them (texconv)")
        if full in tex_jobs:
            tex_jobs[full]["mips"] = True
        else:
            tex_jobs[full] = {"mips": True}
            fixes.append(("tex", full, rel, tex_jobs[full]))
    if mip_bsa:
        r.add("INFO", "Data Files", "", "", f"{len(mip_bsa)} texture(s) inside BSAs have no mipmaps and world models "
                                            f"draw them (a BSA can't be changed; a loose copy with mipmaps would "
                                            f"fix it), e.g. {mip_bsa[0][0]} in {mip_bsa[0][1]}")
    if mst:
        print(f"Asset health: mipmaps: {mst['models']} world model(s), {mst['textures']} texture(s) they draw "
              f"({mst['exempt']} exempt), {len(mip_loose)} loose + {len(mip_bsa)} in BSAs without mipmaps; "
              f"{mst['effect_models']} effect/UI model(s) not counted", file=sys.stderr)
    cache.flush()
    # --- sounds
    ff = find_ffmpeg()
    print(f"Asset health: sounds ({len(snd_files)})...", file=sys.stderr)
    for k, (top, rel, full, ls) in enumerate(snd_files, 1):
        if k == 1 or k == len(snd_files) or k % 5000 == 0:
            MC.count_title("mwdialog_check - asset health: sounds", k, len(snd_files))
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
                                            f"anywhere); --fix moves it to Off\\...\\orphaned animations\\")
        fixes.append(("orphan", full, rel, "orphaned animation"))
    gone = {u[0] for u in unused}
    fixes[:] = [f for f in fixes if f[2] not in gone]  # nothing to repair in a file that is moved out
    if unused:
        mb = sum(u[2] for u in unused) / 1048576
        r.add("INFO", "Data Files", "", "", f"{len(unused)} texture/sound file(s) ({mb:.0f} MB) that no plugin, model, "
                                            f"script, Lua mod or config names; --fix moves them to their mod's "
                                            f"Off\\<plugin>\\unused assets\\ (listed in {UNUSED_RECORD}; --restore-unused puts them back)")
        for rel, full, size in unused:
            fixes.append(("unused", full, rel, "nothing names it"))
    world.asset_health = fixes
    # the pass saw every file: entries for files that are gone (or renamed) go, and what was learnt is written
    # now, not only when the program ends
    cache.prune(("tex2:", "tex2b:", "texh:", "nif:", "snd:", "refs:", "names:", "bsa2:", "abox:", "aboxb:"))
    cache.flush()
    print(f"Asset health: done, {len(fixes)} file(s) to fix", file=sys.stderr)   # [seconds]: the whole pass
    MC.end_count("mwdialog_check - asset health")
    MC.set_title("mwdialog_check - asset health: done")


def apply(fixes, data_dir, game_dir, m, log, dry=False):
    """--fix: repair what check() found. Returns a summary string."""
    texconv = MP.find_texconv(game_dir)
    ff = find_ffmpeg()
    done = {"tex": 0, "abs": 0, "snd": 0, "unused": 0, "broken": 0, "orphan": 0, "actorbox": 0}
    skipped = []
    moves = []
    tmp = os.path.join(game_dir, "mwdialog_tmp_assets")
    shutil.rmtree(tmp, ignore_errors=True)            # left over from a run that stopped early
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
                res = run_tool(args + [full])
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
                res = run_tool(a)
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
                    dest = os.path.join(MB.backup_root(game_dir), "asset_originals", "orphaned", rel)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    os.replace(full, dest)
                moves.append((rel, dest, job))
                done["unused"] += 1
                log.append(("Data Files", f"'{rel}' ({job})", f"moved to {dest}"))
                continue
            elif kind == "actorbox":                   # out of Data Files, no stand-in: the next copy is used
                mod, _pl = m.asset_owner_folder(data_dir, rel)
                if mod:                                # Vortex deployed it: its mod's Off\<plugin>\broken\
                    dest = _free_dest(broken_dest(mod, rel, "broken", _pl))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    stage = os.path.join(mod, rel)
                    if os.path.exists(stage):
                        os.replace(stage, dest)        # the staging copy (the hard link's other name)
                    elif os.path.exists(full):
                        shutil.copy2(full, dest)
                    if os.path.exists(full):
                        os.remove(full)                # the Data Files hard link
                else:
                    dest = _free_dest(os.path.join(MB.backup_root(game_dir), "asset_originals", "broken", rel))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    os.replace(full, dest)
                moves.append((rel, dest, job))
                done["actorbox"] += 1
                log.append(("Data Files", f"'{rel}' ({job})", f"moved to {dest}: the next mod's copy (after Deploy "
                                                              f"in Vortex) or a BSA's is used"))
                continue
            elif kind == "broken":                     # keep the broken file in Off, a stand-in in its place
                mod, _pl = m.asset_owner_folder(data_dir, rel)
                dest = broken_dest(mod, rel, "broken", _pl) if mod else \
                    os.path.join(MB.backup_root(game_dir), "asset_originals", "broken", rel)
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
                    if os.path.exists(full) and not os.path.exists(dest):
                        shutil.copy2(full, dest)       # no staging copy to keep: keep this one
                    if os.path.exists(full):
                        os.remove(full)                # the Data Files hard link
                else:
                    dest = os.path.join(MB.backup_root(game_dir), "asset_originals", "unused", rel)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    os.replace(full, dest)
                moves.append((rel, dest, job))
                log.append(("Data Files", f"'{rel}' ({job})", f"moved to {dest}"))
                done["unused"] += 1
                continue
            bak = m.backup_asset_original(data_dir, rel, feature=FEATURE_OF.get(kind, OL.REPAIRED))
            m.replace_asset_in_place(full, new)
            done[kind] += 1
            log.append(("Data Files", f"'{rel}' ({kind})", f"repaired (original: {bak})"))
        except OSError as e:
            skipped.append(f"{rel} ({e})")
    if moves:
        with open(MP.state_path(game_dir, UNUSED_RECORD), "a", encoding="utf-8") as f:
            for rel, dest, why in moves:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{rel}\t{dest}\t{why}\n")
    shutil.rmtree(tmp, ignore_errors=True)
    msg = (f"{done.get('broken', 0)} broken file(s) replaced by stand-ins (kept in Off\\...\\broken\\), "
           f"{done['actorbox']} actor model(s) with a crashing Bounding Box moved to Off\\...\\broken\\, "
           f"{done['tex']} texture(s) converted, {done['abs']} model(s) with absolute texture paths fixed, "
           f"{done['snd']} sound(s) converted, {done['unused']} unused/empty file(s) moved to Off")
    if skipped:
        msg += f"; {len(skipped)} skipped, e.g. " + "; ".join(skipped[:3])
    return ("Dry run: would do " if dry else "") + msg


# <mod>\Off\<unused|orphaned|broken>\... (any case, either slash): a file these tools took out of a mod
OFF_MARKER_RE = re.compile(r"[\\/]off[\\/](?:[^\\/]+[\\/])?(?:unused assets|orphaned animations|unused|orphaned|broken)[\\/]",
                           re.IGNORECASE)


def restore_unused(game_dir, data_dir):
    """--restore-unused: put back every file listed in mwdialog_unused_assets.txt (staging copy back into the
    mod folder; Vortex redeploys it, or it is copied into Data Files when it wasn't Vortex's)."""
    path = MP.state_path(game_dir, UNUSED_RECORD)
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
            dest = OL.relocated(dest)                # moved by vortex_tidy to the Off\\<plugin>\\<reason> layout
            if not dest:
                continue
        try:
            m = OFF_MARKER_RE.search(dest)
            if m:                                    # from a Vortex mod: back into the mod, linked into Data Files
                mod = dest[:m.start()]
                staged = os.path.join(mod, rel)
                if os.path.exists(staged):
                    raise FileExistsError("a newer file is there")
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
                if os.path.exists(os.path.join(data_dir, rel)):
                    raise FileExistsError("a newer file is there")
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


def _examine_dds(rel, full, size, m, want_mips=None, out=None):
    """[(severity, message)], job or None. want_mips(rel) -> bool: whether a missing mipmap chain counts
    (None: always, the old behaviour). out (a dict) gets "t": the texture facts, and "m": True when the
    mipmaps were missing but didn't count."""
    try:
        with open(full, "rb") as f:
            head = f.read(148)
    except OSError:
        return [], None
    if out is not None:
        out["t"] = texture_facts(head, m)
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
    if mips <= 1 and max(w, h) >= MIP_MIN_EDGE:
        if want_mips is None or want_mips(rel):
            job["mips"] = True
            why.append("no mipmaps")
        elif out is not None:
            out["m"] = True
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


_OWN_MASTER_TEXT = {}


def _high_byte_text(full):
    """The parts of a plugin near a non-ASCII byte that name a file (lower bytes), for name searches."""
    data = open(full, "rb").read()
    bits, last = [], -1
    for mm in HIGH_BYTE_RE.finditer(data):
        k = mm.start()
        if k < last:
            continue
        win = data[max(0, k - 200):k + 200].lower()
        last = k + 200
        if FILE_EXT_RE.search(win):
            bits.append(win)
    return b"\0".join(bits)


def _own_masters_naming(name_b, root):
    """This mod's own .esm files that hold name_b (lower bytes, either slash). A master is never edited, so a
    file one of them names keeps its name."""
    out = []
    for fn in sorted(os.listdir(root)):
        full = os.path.join(root, fn)
        if not fn.lower().endswith(".esm") or not os.path.isfile(full):
            continue
        try:
            st = os.stat(full)
            key = (os.path.normcase(full), st.st_size, st.st_mtime_ns)
            if key not in _OWN_MASTER_TEXT:
                _OWN_MASTER_TEXT[key] = _high_byte_text(full)
        except OSError:
            continue
        text = _OWN_MASTER_TEXT[key]
        if name_b in text or name_b.replace(b"\\", b"/") in text:
            out.append(fn)
    return out


def _other_plugins_naming(name_b, root, data_dir):
    """Active-folder plugins (Data Files) other than this mod's own that hold name_b (lower bytes). Before deploy
    (data_dir a mwdialog_staged.StagedData) the other staged mods' plugins instead; Data Files is not read."""
    if isinstance(data_dir, MS.StagedData):
        listing = [(fn, p) for fn, p in data_dir.plugins()
                   if os.path.normcase(os.path.dirname(p)) != os.path.normcase(os.path.abspath(root))]
    elif not data_dir or not os.path.isdir(data_dir):
        return []
    else:
        listing = [(fn, os.path.join(data_dir, fn)) for fn in os.listdir(data_dir)]
    if not _PLUGIN_TEXT:
        for fn, full in listing:
            if fn.lower().endswith((".esp", ".esm")):
                try:                           # only what is near a non-ASCII byte and names a file
                    data = open(full, "rb").read()
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


def check_folder(root, m, data_dir=None, bsa_meshes=None, stats=None):
    """(issues [(severity, rel, message)], fixes [(kind, full, rel, job)]) for one mod folder. data_dir and
    bsa_meshes (lowercase paths under Meshes in every BSA) let an animation's model be found elsewhere.
    Mipmaps: only a texture one of the mod's OWN world models draws is reported without them (not one of
    the exempt kinds: menu / MCM / icon / effect, see mip_rules); a texture pack for other mods' or the
    game's models is judged by mwdialog_check's per-pair check of the whole install. stats (a dict) gets
    "mips_skipped": textures without mipmaps that were left alone."""
    issues, fixes = [], []
    world_tex = set()                  # stems under Textures the mod's own world models draw
    game_dir = MS.game_dir_of(data_dir) if data_dir else (MP.find_game_dir() or MP.TOOL_DIR)
    rules = mip_rules(game_dir)

    def note_model(rel, tn):
        if rel.lower().endswith(".nif") and tn and not mip_exempt_mesh(rel, rules):
            world_tex.update(tex_stem(t) for t in tn)

    def want_mips(rel):
        p = _dfrel(rel)
        return p.startswith("textures\\") and not mip_exempt_texture(p, rules) \
            and os.path.splitext(p[9:])[0] in world_tex
    # read every text source once, then join: repeatedly extending one bytes object would copy
    # everything already read on each file (quadratic on big mod folders)
    parts = []
    for e in os.listdir(root):
        if e.lower().endswith((".esp", ".esm")):
            try:
                parts.append(open(os.path.join(root, e), "rb").read().lower())
            except OSError:
                pass
    for dp, ds, fs in os.walk(os.path.join(root, "MWSE")) if os.path.isdir(os.path.join(root, "MWSE")) else ():
        for fn in fs:
            if fn.lower().endswith((".lua", ".json", ".toml")):
                try:
                    parts.append(open(os.path.join(dp, fn), "rb").read().lower())
                except OSError:
                    pass
    own_text = b"".join(parts)
    tops = ASSET_DIRS
    # files already found clean (here or by an earlier tidy / check run) aren't read again: keyed by the
    # Data Files path + size + date, which a Vortex hard link shares with the deployed copy
    cache = shared_cache(MS.game_dir_of(data_dir) if data_dir else (MP.find_game_dir() or MP.TOOL_DIR))
    mod_key = TIDY_KEY + os.path.basename(os.path.normpath(root)).lower() + "|"
    pending = None

    def settle():
        if pending:
            # one record per mod file (tidy3:<mod>|<path>, its size + date): the full check of Data Files trusts
            # the same file there (what tidy can't fix, it can't either; tidy's bug report has it) and takes a
            # model's texture list from it. Clean ("c"): not even tidy reads it again.
            key, stamp, n_issues, n_fixes, facts = pending[:5]
            rec = {"c": len(issues) == n_issues and len(fixes) == n_fixes}
            if facts is not None:
                rec["f"] = facts
            rec.update(pending[5])             # a texture's facts ("t"), mipmaps missing but not needed ("m")
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
        if got is not None and got.get("c") and (top != "splash" or got.get("sr") == splash_rule()) \
                and not (top in TEX_DIRS and _over_texture_cap(got.get("t"), m)) \
                and not (low.endswith(".nif") and "past" not in (got.get("f") or {})):   # from before that check
            if top == "meshes":
                tn = (got.get("f") or {}).get("tn")
                if tn is None and low.endswith(".nif"):        # an older record: the model is read once
                    try:
                        with open(full, "rb") as f:
                            tn = m.nif_texture_refs(f.read())
                    except OSError:
                        tn = []
                note_model(rel, tn)
            # clean, unless its missing mipmaps count now (one of the mod's world models draws it)
            if not (got.get("m") and top == "textures" and want_mips(rel)):
                if got.get("m") and stats is not None:
                    stats["mips_skipped"] = stats.get("mips_skipped", 0) + 1
                continue
        pending = [key, stamp, len(issues), len(fixes), None, {}]
        if any(ord(c) > 127 for c in rel):
            new_rel = ascii_name(rel)
            tail = rel.replace("/", "\\").split("\\", 1)[-1]
            try:
                tail_b = tail.lower().encode("cp1252")
            except UnicodeEncodeError:
                tail_b = None                  # Cyrillic etc.: no plugin can name it the way Windows needs
            others = _other_plugins_naming(tail_b, root, data_dir) if tail_b else []
            own_masters = _own_masters_naming(tail_b, root) if tail_b else []
            base_b = tail_b.replace(b"\\", b"/").rsplit(b"/", 1)[-1] if tail_b else None   # ntpath decodes bytes as UTF-8
            if own_masters:
                issues.append(("WARN", rel, f"non-ASCII file name, named so by this mod's {', '.join(own_masters[:3])}; "
                                            f"left as it is (a master is never edited, and renaming the file "
                                            f"would leave the master without it)"))
            elif not others and base_b and _models_naming(base_b, root):
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
        if top == "splash" and low.endswith(SPLASH_IMAGE_EXTS):
            # the game shows only TGA splashes; one at most SPLASH_MAX_WIDTH wide is left as it is
            pending[5]["sr"] = splash_rule()
            if low.endswith(".tga"):
                width, depth = _tga_head(full)
                alpha = "an alpha channel a loading screen has no use for" if depth == 32 else ""
                if splash_too_wide(width):
                    issues.append(("WARN", rel, (f"splash screen with {alpha}; " if alpha else "splash screen ")
                                   + f"wider than {SPLASH_MAX_WIDTH} -> {SPLASH_MAX_WIDTH} wide, 24-bit RLE TGA "
                                     f"(the original kept in Off)"))
                    fixes.append(("splash", full, rel, None))
                else:
                    try:
                        smaller = 1 - len(splash_tga(full, None, None)) / size
                    except (OSError, ValueError, struct.error):
                        smaller = 0
                    if smaller >= SPLASH_MIN_GAIN:
                        issues.append(("WARN", rel, (f"splash screen with {alpha}" if alpha else
                                                     f"splash screen stored {round(smaller * 100)}% larger than it "
                                                     f"needs (no RLE)")
                                       + " -> 24-bit RLE TGA, same pixels (the original kept in Off)"))
                        fixes.append(("splash", full, rel, None))
            elif rel.replace("/", "\\").count("\\") > 1:
                pass                                 # Splash\<folder>\: the game never picks it; only a mod's code does
            elif os.path.isdir(os.path.join(root, "MWSE")):
                # a mod with MWSE code may load its own splash by this very name (Regional Splash Screens did)
                issues.append(("WARN", rel, "splash screen that is not a TGA; the game shows only TGA splashes, but "
                                            "this mod's MWSE code may load it by name, so it is left as it is"))
            else:
                issues.append(("ERROR", rel, "splash screen that is not a TGA (the game shows only TGA splashes) -> "
                                             f"{splash_target()} (the original kept in Off)"))
                fixes.append(("splash", full, rel, None))
            continue
        if top in TEX_DIRS and low.endswith(".dds"):
            msgs, job = _examine_dds(rel, full, size, m, want_mips, pending[5])
            if pending[5].get("m") and stats is not None:
                stats["mips_skipped"] = stats.get("mips_skipped", 0) + 1
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
            note_model(rel, pending[4].get("tn"))
            if not b.startswith(NIF_HEAD):
                first = b[:40].split(b"\n")[0].decode("latin1", "replace")
                issues.append(("ERROR", rel, f"not a Morrowind file (header '{first}'); the game crashes on it"
                                             " -> kept in Off\\...\\broken\\, a stand-in put there"))
                fixes.append(("broken", full, rel, "not a Morrowind file"))
                continue
            past = nif_links_past_end(b) if low.endswith(".nif") else None
            if past:
                issues.append(("ERROR", rel, f"broken model: a node in it points at block {past[1]}, but its header "
                                             f"says it has only {past[0]}; the game crashes loading it -> moved to "
                                             f"Off\\...\\broken\\; Deploy in Vortex so another mod's copy wins"))
                fixes.append(("brokenout", full, rel, "broken model"))
                BROKEN_MODELS.append((rel, f"in {os.path.basename(os.path.normpath(root))}: vortex_tidy --apply moves "
                                           f"it to Off\\...\\broken\\; then Deploy in Vortex so another mod's copy "
                                           f"wins (with none, objects using it show no model)"))
                continue
            if low.endswith(".nif") and OL.reason_dirs(root, "broken") \
                    and _is_stand_in(b, m, rel) and _broken_original(root, rel):
                issues.append(("ERROR", rel, "stand-in --fix put in place of a broken model -> removed; Deploy in "
                                             "Vortex so another mod's copy wins"))
                fixes.append(("brokenout", full, rel, "stand-in"))
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
                elsewhere = (data_dir and (data_dir.exists(twin) if isinstance(data_dir, MS.StagedData)
                                           else os.path.exists(os.path.join(data_dir, twin)))) or \
                    (bsa_meshes is not None and twin_low in bsa_meshes)
                named = os.path.splitext(os.path.basename(low))[0].encode("latin1", "replace") in own_text
                if not elsewhere and not named:
                    issues.append(("WARN", rel, "orphaned animation (its model is nowhere) -> Off\\...\\orphaned animations\\"))
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


FIX_ORDER = {"ascii": 0, "broken": 1, "brokenout": 1, "orphan": 2, "snd": 3, "keys": 4, "abs": 5, "tex": 6, "splash": 6}


def _backup_in_mod(root, rel, full, plugin_name, feature="repaired originals"):
    """The original into <mod>\\Off\\<plugin>\\<reason>\\<rel>, once: not when one is kept already (under any
    reason, in any older Off layout) - unless the file now there is a new original (a mod update): then that
    is kept too, with a date added (see keep_new_original)."""
    import mwdialog_check as _m
    kept = OL.find_original(root, rel)
    if kept:
        return _m.keep_new_original(kept, full)
    dest = _m.off_dest(root, feature, plugin_name, rel)
    if not os.path.exists(dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(full, dest)
        _m._ASSET_BACKUP_OF[os.path.normcase(os.path.abspath(full))] = dest
        return dest
    return _m.keep_new_original(dest, full)


def find_ffmpeg():
    return MP.find_program("ffmpeg", MP.find_game_dir())


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
        # untouched original; it goes to Off\<plugin>\ascii\<old path>, out of the way
        import mwdialog_check as _m
        keep = _m.off_dest(root, "ascii", None, rel)
        os.makedirs(os.path.dirname(keep), exist_ok=True)
        if os.path.exists(keep):
            _m.keep_new_original(keep, full)       # an update's file is a new original; raises if it can't be kept
            os.remove(full)
        else:
            os.replace(full, keep)
        log(f"{rel}: already renamed {new_rel} by an earlier run; the old-named original moved to Off\\<plugin>\\ascii\\")
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
        if not pf.lower().endswith((".esp", ".omwaddon")):      # a master (.esm) is never edited
            continue
        pp = os.path.join(root, pf)
        try:
            data = open(pp, "rb").read()
            new, hits = plugin_path_rename(data, pairs)
        except (OSError, _m.FormatError) as e:
            log(f"{pf}: not changed ({e})")
            continue
        if hits:
            bak = _m.off_dest(root, "ascii", pf, pf)     # Off\\<plugin>\\ascii\\<plugin file>, once
            if not os.path.exists(bak):
                os.makedirs(os.path.dirname(bak), exist_ok=True)
                shutil.copy2(pp, bak)
            _m.keep_new_original(bak, pp)
            # checked temp copy, then in place: keeps a Vortex hard link (and the date: load order)
            _m.write_plugin_bytes(pp, new, keep_times=os.stat(pp))
            _m.record_repair(pp, new)
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
    texconv = MP.find_texconv(game_dir)
    ff = find_ffmpeg()
    tmp = os.path.join(game_dir, "mwdialog_tmp_assets")
    shutil.rmtree(tmp, ignore_errors=True)            # left over from a run that stopped early
    done, skipped = 0, []
    # every repair of one file is done in this one run: the renames first, then the other fixes find the
    # file under its new name (each fix reads the file as the one before left it)
    renamed = {}
    for kind, full, rel, job in fixes:
        if kind == "ascii":
            try:
                rename_ascii(root, full, rel, job, lambda t: print("  " + t))
                renamed[full] = (os.path.join(root, job), job)
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
        if kind in ("broken", "orphan", "brokenout"):
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
            if kind == "brokenout":                  # out of the mod (no stand-in): Vortex deploys the next copy
                if job == "stand-in":
                    os.remove(full)                  # ours; the broken original is in Off already
                else:
                    dest = broken_dest(root, rel, "broken", plugin_name)
                    if os.path.exists(dest):
                        stem, ext = os.path.splitext(dest)
                        dest = f"{stem}.{time.strftime('%Y%m%d-%H%M%S')}{ext}"
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
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
            if kind == "splash":                      # at most 2048 wide, RLE TGA; a DDS/BMP... becomes a .tga
                if not texconv and splash_needs_texconv(full):
                    skipped.append(f"{rel} (texconv.exe not found)")
                    continue
                os.makedirs(tmp, exist_ok=True)
                new = splash_tga(full, texconv, tmp)
                target = full if full.lower().endswith(".tga") else os.path.splitext(full)[0] + ".tga"
                if target != full and os.path.exists(target):
                    skipped.append(f"{rel} (a TGA of that name exists already)")
                    continue
                _backup_in_mod(root, orig_rel.get(full, rel), full, plugin_name, FEATURE_OF[kind])
                if target == full:
                    m.replace_asset_in_place(full, new)          # in place: Vortex's hard link stays
                else:
                    with open(target, "wb") as f:
                        f.write(new)
                    os.remove(full)                              # its original is in Off
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
                    a = [texconv, "-nologo", "-y", "-dx9", "-o", tmp, "-m", "1" if job.get("nomips") else "0"]
                    if job.get("convert"):
                        a += ["-ft", job["convert"][1:], "-f", "BC3_UNORM"]
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
                    res = run_tool(a + [full])
                    out = os.path.join(tmp, os.path.splitext(os.path.basename(full))[0] + job["convert"]
                                       if job.get("convert") else os.path.basename(full))
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
                    out = os.path.join(tmp, "x" + (".mp3" if job.get("mp3") else os.path.splitext(full)[1].lower()))
                    a = [ff, "-y", "-v", "error", "-i", full]
                    if job.get("mono"):
                        a += ["-ac", "1"]
                    if job.get("rate"):
                        a += ["-ar", str(job["rate"])]
                    a += (["-c:a", "pcm_s16le"] if out.endswith(".wav") else
                          ["-c:a", "libmp3lame", "-q:a", "2", "-id3v2_version", "0", "-map_metadata", "-1"]) + [out]
                    res = run_tool(a)
                    if res.returncode or not os.path.exists(out):
                        skipped.append(f"{rel} (ffmpeg: {res.stderr.strip()[-100:]})")
                        continue
                    new = open(out, "rb").read()
                    os.remove(out)
            if not new:
                continue
            if kind == "snd" and job.get("mp3"):         # Morrowind falls back from x.wav to x.mp3
                mp3 = os.path.splitext(full)[0] + ".mp3"
                if os.path.exists(mp3):
                    skipped.append(f"{rel} (an MP3 of that name exists already)")
                    continue
                _backup_in_mod(root, orig_rel.get(full, rel), full, plugin_name, FEATURE_OF.get(kind, OL.REPAIRED))
                m.replace_asset_in_place(mp3, new)
                os.remove(full)
                done += 1
                continue
            if kind == "tex" and job.get("keep"):        # the original stays; only the DDS beside it is new
                m.replace_asset_in_place(os.path.splitext(full)[0] + job["convert"], new)
                done += 1
                continue
            # only the original is kept: a backup that exists already (an earlier fix of this run, or a run
            # before) is never overwritten; a renamed file's original is kept under its original name
            _backup_in_mod(root, orig_rel.get(full, rel), full, plugin_name, FEATURE_OF.get(kind, OL.REPAIRED))
            m.replace_asset_in_place(full, new)
            done += 1
        except OSError as e:
            skipped.append(f"{rel} ({e})")
    shutil.rmtree(tmp, ignore_errors=True)
    return done, skipped


# ---------------------------------------------------------------------------------------------------------
# <plugin>.bugreport.txt: what is wrong with a plugin ON ITS OWN (not conflicts with other mods), ready to
# post on the mod's page. Each tool owns one section and rewrites only that one.
# ---------------------------------------------------------------------------------------------------------
BUG_SECTION = "======== {} ========"
BUG_END = "======== end of {} ========"


def update_bug_report(path, section, header, lines):
    """Write/replace `section` in the bug report at `path`, preserving the existing header and other tools'
    sections. An empty `lines` removes only `section`; a report left with no sections is deleted."""
    old = ""
    try:
        with open(path, encoding="utf-8") as f:
            old = f.read()
    except OSError:
        pass
    old_header, sections, cur, buf = [], {}, None, []
    saw_section = False
    for ln in old.splitlines():
        if ln.startswith("======== end of ") and cur:
            sections[cur] = buf
            cur, buf = None, []
        elif ln.startswith("======== ") and ln.endswith(" ========") and not ln.startswith("======== end of "):
            cur, buf = ln[9:-9], []
            saw_section = True
        elif cur:
            buf.append(ln)
        elif not saw_section:
            old_header.append(ln)
    while old_header and not old_header[-1].strip():
        old_header.pop()
    if old.strip() and not saw_section and old_header:
        # A legacy unsectioned report: keep its text rather than discarding it.
        sections.setdefault("previous report", old_header)
        old_header = []
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
    kept_header = old_header if old_header else list(header)
    out = list(kept_header) + [""]
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
            "Only this plugin's own defects and declared-master compatibility issues are listed, not unrelated mod interactions.",
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


def package_bug_report_path(folder, plugin_name, report_kind=None):
    """A consistently named package report, optionally qualified by checker."""
    nid = nexus_id(folder)
    base = os.path.splitext(plugin_name)[0] + (f" [Nexus {nid}]" if nid else "")
    base += (f".{report_kind}" if report_kind else "") + ".bugreport.txt"
    return os.path.join(folder, "bugreports", base)


def package_bug_report_subject(folder, m, owner, tool="vortex_tidy"):
    """Package-wide files belong to a plugin only when the package contains exactly one."""
    plugins = [name for name in sorted(os.listdir(folder), key=str.lower)
               if name.lower().endswith((".esp", ".esm")) and os.path.isfile(os.path.join(folder, name))]
    if len(plugins) == 1:
        return plugins[0], bug_report_header(os.path.join(folder, plugins[0]), m, mod_folder=folder)
    return owner, [f"Bug report for {owner}", f"Mod: {owner} (package-wide files, not an individual plugin)",
                   f"Generated {time.strftime('%Y-%m-%d %H:%M')} by {tool}.",
                   "Paths are relative to the mod's folder (Data Files)."]


TEXTURE_REDUCTION = re.compile(r"^\d+x\d+ \(over \d+\)$")


def asset_bug_message(message):
    """The author-facing part of an asset finding, or None: shrinking an oversized texture or splash, or
    re-encoding a splash smaller, is our optimisation, not the author's bug (a splash's alpha channel is)."""
    if message.startswith("non-ASCII file name, named so by "):
        return "non-ASCII file name"
    if message.startswith(("splash screen wider than ", "splash screen stored ")):
        return None
    head, arrow, tail = message.partition(" -> ")
    if arrow and tail == "converted":
        parts = [part for part in head.split(", ") if not TEXTURE_REDUCTION.match(part)]
        return ", ".join(parts) + arrow + tail if parts else None
    return message


def package_asset_bug_lines(issues):
    """Bug-report lines for a package's own asset findings; [] when none is the author's bug."""
    found = [(severity, relative, text) for severity, relative, message in issues
             if (text := asset_bug_message(message))]
    if not found:
        return []
    return [f"Problems in the mod's files: {len(found)}"] + \
        [f"  - {severity} {relative}: {text}" for severity, relative, text in found]


def bug_report_path(data_dir, game_dir, plugin_name, m):
    """<mod folder>\\bugreports\\<plugin name>.bugreport.txt (Vortex), else <game>\\bugreports\\."""
    mod = None
    try:
        mod, _pl = m.asset_owner_folder(data_dir, plugin_name)
    except Exception:
        mod = None
    return package_bug_report_path(mod or game_dir, plugin_name)
