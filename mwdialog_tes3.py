"""mwdialog_tes3.py - the TES3 plugin file format: record and subrecord reading, the lossless text codec,
cached reads and safe in-place writes. No knowledge of load orders, fixes or reports; every other mwdialog
module builds on this one.
"""
from collections import OrderedDict
import codecs
import hashlib
import os
import struct

ENC = "cp1252"          # --encoding: mwdialog_check sets this (and its own copy) at start-up

DIAL_TYPES = {0: "Topic", 1: "Voice", 2: "Greeting", 3: "Persuasion", 4: "Journal"}

JOURNAL = 4

ITEM_TAGS = {"ALCH", "APPA", "ARMO", "BOOK", "CLOT", "INGR", "LIGH", "LOCK",
             "MISC", "PROB", "REPA", "WEAP", "LEVI"}

ACTOR_TAGS = {"NPC_", "CREA"}


# Records whose script (SCRI), enchantment (ENAM) or inventory (NPCO) the game resolves at load;
# a name that points at nothing gives "Unable to locate Enchanting", "Unable to find script ... on
# object" or "Item ... not found on ..." in Warnings.txt.
REF_TAGS = {"ALCH", "APPA", "ARMO", "BOOK", "CLOT", "INGR", "LIGH", "LOCK", "MISC", "PROB", "REPA",
            "WEAP", "NPC_", "CREA", "ACTI", "CONT", "DOOR"}

ENAM_TAGS = {"ARMO", "BOOK", "CLOT", "WEAP"}


# Records with a 3D model (MODL), checked against the meshes and textures that exist
MODEL_TAGS = {"ACTI", "ALCH", "APPA", "ARMO", "BODY", "BOOK", "CLOT", "CONT", "CREA", "DOOR", "INGR", "LIGH",
              "LOCK", "MISC", "PROB", "REPA", "STAT", "WEAP"}


# Files records name: (subrecord, kind). Kinds: mesh (Meshes, with its textures), icon (Icons),
# texture (Textures), sound (Sound).
ICON_TAGS = {"ALCH", "APPA", "ARMO", "BOOK", "CLOT", "INGR", "LIGH", "LOCK", "MISC", "PROB", "REPA", "WEAP"}

ASSET_SUBS = {t: [("MODL", "mesh")] + ([("ITEX", "icon")] if t in ICON_TAGS else []) for t in MODEL_TAGS}


ASSET_SUBS.update({"NPC_": [("MODL", "mesh")], "SOUN": [("FNAM", "sound")], "LTEX": [("DATA", "texture")],
                   "BSGN": [("TNAM", "texture")]})


# where each record keeps its kind: (subrecord, struct format, offset)
SUBTYPE_AT = {"CLOT": (b"CTDT", "<i", 0), "ARMO": (b"AODT", "<i", 0), "WEAP": (b"WPDT", "<h", 8),
              "BODY": (b"BYDT", "<B", 0), "BOOK": (b"BKDT", "<i", 8), "APPA": (b"AADT", "<i", 0)}

ID_TAGS = ITEM_TAGS | ACTOR_TAGS | {
    "ACTI", "CONT", "DOOR", "STAT", "BODY", "SPEL", "ENCH", "LEVC", "SOUN",
    "RACE", "CLAS", "FACT", "GLOB", "SCPT", "BSGN", "REGN", "SNDG", "SSCR"}

CONDITION_TYPES = {
    "1": "Function", "2": "Global", "3": "Local", "4": "Journal", "5": "Item",
    "6": "Dead", "7": "Not ID", "8": "Not Faction", "9": "Not Class",
    "A": "Not Race", "B": "Not Cell", "C": "Not Local"}

COMPARE_OPS = set("012345")


class FormatError(Exception):
    pass


def _mw_bytes_errors(err):
    """Codec error handler "mw_bytes": a byte the code page doesn't define (cp1252: 0x81, 0x8D, 0x8F, 0x90,
    0x9D) decodes to the character of the same number, and encodes back to that byte, so IDs and links
    survive a read/write unchanged in any --encoding. surrogateescape characters encode back to their byte
    too; anything else the code page can't hold becomes '?' (never an exception)."""
    if isinstance(err, UnicodeDecodeError):
        return "".join(chr(b) for b in err.object[err.start:err.end]), err.end
    out = bytearray()
    for ch in err.object[err.start:err.end]:
        o = ord(ch)
        out.append(o - 0xDC00 if 0xDC80 <= o <= 0xDCFF else o if o < 0x100 else 0x3F)
    return bytes(out), err.end


codecs.register_error("mw_bytes", _mw_bytes_errors)


MW_ERRORS = "mw_bytes"


def dec(b):
    """Plugin bytes -> str, losslessly (see _mw_bytes_errors)."""
    return bytes(b).decode(ENC, MW_ERRORS)


def enc(s):
    """str -> plugin bytes; the exact inverse of dec(), and never raises."""
    return s.encode(ENC, MW_ERRORS)


_TAGS = {}


def _tag(b4):
    """A record/subrecord name as str (cached: there are only a few dozen)."""
    t = _TAGS.get(b4)
    if t is None:
        t = _TAGS[b4] = bytes(b4).decode("latin-1")
    return t


_READ_CACHE = OrderedDict()            # normcase path -> (size, mtime_ns, bytes)

_READ_CACHE_MAX = 256 * 1024 * 1024    # keeps the big masters of one run in memory (Morrowind.esm is ~80 MB)


def read_plugin_bytes(path):
    """The bytes of a plugin, from a small cache when nothing changed it since (size and date, and every
    write these tools make goes through safe_write_bytes, which drops the cached copy)."""
    key = os.path.normcase(os.path.abspath(path))
    st = os.stat(path)
    hit = _READ_CACHE.get(key)
    if hit is not None and hit[0] == st.st_size and hit[1] == st.st_mtime_ns:
        _READ_CACHE.move_to_end(key)
        return hit[2]
    with open(path, "rb") as f:
        data = f.read()
    _READ_CACHE[key] = (st.st_size, st.st_mtime_ns, data)
    total = sum(len(v[2]) for v in _READ_CACHE.values())
    while total > _READ_CACHE_MAX and len(_READ_CACHE) > 1:
        _k, v = _READ_CACHE.popitem(last=False)
        total -= len(v[2])
    return data


def forget_cached(path):
    _READ_CACHE.pop(os.path.normcase(os.path.abspath(path)), None)


def validate_plugin_bytes(data):
    """Raise FormatError unless `data` is a whole TES3 plugin: a TES3 header first and every record and
    subrecord inside the file."""
    first = True
    for _off, tag, _flags, body in iter_records(data):
        if first:
            if tag != "TES3":
                raise FormatError("does not start with a TES3 header")
            first = False
        for _s in iter_subs(body):
            pass
    if first:
        raise FormatError("empty file")


def safe_write_bytes(path, data, validate=None, keep_times=None):
    """Write `data` over `path` safely, keeping hard links (Vortex) intact:
      1. the new contents go to <path>.mwdtmp first, flushed to disk, and are read back and checked
         (validate(bytes) may raise to stop here, with the original untouched);
      2. then they are copied over the existing file in place (same file, so its hard links stay) and
         flushed; a brand-new file is simply moved into place.
    If step 2 fails, the checked copy is left as <path>.mwdtmp and the error is raised.
    keep_times: an os.stat_result whose dates are put back afterwards (date-based load order)."""
    data = bytes(data)
    tmp = path + ".mwdtmp"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    try:
        with open(tmp, "rb") as f:
            back = f.read()
        if back != data:
            raise OSError(f"{tmp}: read back differently from what was written")
        if validate is not None:
            validate(back)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    forget_cached(path)
    if not os.path.exists(path):
        os.replace(tmp, path)
    else:
        with open(path, "r+b") as f:             # in place: no truncation until the new bytes are written
            f.write(data)
            f.truncate()
            f.flush()
            os.fsync(f.fileno())
        os.remove(tmp)
    if keep_times is not None:
        os.utime(path, ns=(keep_times.st_atime_ns, keep_times.st_mtime_ns))
    forget_cached(path)


def write_plugin_bytes(path, data, keep_times=None):
    """safe_write_bytes for a plugin: refuses to write anything that isn't a whole TES3 file."""
    safe_write_bytes(path, data, validate=validate_plugin_bytes, keep_times=keep_times)


def set_hedr_count(head, count):
    """The TES3 record (bytes) with its HEDR record count set to `count`; unchanged when HEDR isn't the
    first subrecord or is shorter than its 300 bytes (writing there would overwrite the next subrecord)."""
    head = bytearray(head)
    if head[:4] == b"TES3" and head.find(b"HEDR") == 16 and len(head) >= 24 + 300 \
            and struct.unpack_from("<I", head, 20)[0] >= 300:
        struct.pack_into("<I", head, 16 + 8 + 296, count)
    return bytes(head)


def cstr(b):
    i = b.find(b"\0")
    if i >= 0:
        b = b[:i]
    return b.decode(ENC, MW_ERRORS)


def iter_records(data):
    """Yield (offset, tag, flags, body) for each top-level record."""
    pos, n = 0, len(data)
    while pos < n:
        if n - pos < 16:
            raise FormatError(f"truncated record header at offset {pos}")
        tag = _tag(data[pos:pos + 4])
        size, _unused, flags = struct.unpack_from("<III", data, pos + 4)
        start = pos + 16
        end = start + size
        if end > n:
            raise FormatError(f"{tag} record at offset {pos} runs past end of file")
        yield pos, tag, flags, data[start:end]
        pos = end


_SUB_HEAD = struct.Struct("<4sI").unpack_from


def iter_subs(body, offset=0):
    """Yield (name, data) for each subrecord in a record body."""
    p, end = 0, len(body)
    tags, head = _TAGS, _SUB_HEAD
    while p < end:
        if end - p < 8:
            raise FormatError(f"truncated subrecord at offset {offset + 16 + p}")
        raw, size = head(body, p)
        name = tags.get(raw)
        if name is None:
            name = _tag(raw)
        sp = p + 8
        if sp + size > end:
            raise FormatError(f"subrecord {name} at offset {offset + 16 + p} runs past its record")
        yield name, body[sp:sp + size]
        p = sp + size


def first_sub(body, wanted):
    """Return the data of the first subrecord named `wanted`, or None."""
    p, end = 0, len(body)
    while p + 8 <= end:
        name = body[p:p + 4]
        size = struct.unpack_from("<I", body, p + 4)[0]
        if name == wanted:
            return body[p + 8:p + 8 + size]
        p += 8 + size
    return None


def cell_key(body):
    """(key, label) identifying a cell: interiors by name, exteriors by grid."""
    d = first_sub(body, b"DATA")
    nm = first_sub(body, b"NAME")
    name = cstr(nm) if nm is not None else ""
    if d is None or len(d) < 12:
        return None, name
    flags, x, y = struct.unpack_from("<Iii", d)
    if flags & 1:
        return ("i", name.lower()), name
    return ("e", x, y), (f"{name} ({x}, {y})" if name else f"({x}, {y})")


def has_sub(body, wanted):
    return first_sub(body, wanted) is not None


def set_link(subs, which, value):
    """Set an INFO's PNAM or NNAM in `subs` [[name, data]], adding it (after INAM, PNAM before NNAM) when
    the record has none - otherwise the fix would be logged without changing anything."""
    hit = False
    for x in subs:
        if x[0] == which:
            x[1] = value
            hit = True
    if hit:
        return
    order = ("INAM", "PNAM") if which == "NNAM" else ("INAM",)
    pos = max([k + 1 for k, x in enumerate(subs) if x[0] in order] or [0])
    subs.insert(pos, [which, value])


def pack_sub(name, data):
    return name.encode("latin-1") + struct.pack("<I", len(data)) + bytes(data)


def pack_str(s):
    return s.encode(ENC, MW_ERRORS) + b"\0" if s else b"\0"


def record_id(tag, body):
    """A record's identity across files (tes3cmd's rules, lowercased); None if it has none."""
    if tag == "INFO":
        return ("INFO", cstr(first_sub(body, b"INAM") or b"").lower())
    if tag == "CELL":
        key, _label = cell_key(body)
        return ("CELL", key) if key else None
    if tag == "PGRD":
        d = first_sub(body, b"DATA")
        xy = struct.unpack_from("<ii", d) if d is not None and len(d) >= 8 else (0, 0)
        return ("PGRD", cstr(first_sub(body, b"NAME") or b"").lower(), xy)
    if tag == "SCPT":
        hd = first_sub(body, b"SCHD")
        return ("SCPT", cstr(hd[:32]).lower()) if hd else None
    if tag == "LAND":
        iv = first_sub(body, b"INTV")
        return ("LAND", bytes(iv)) if iv else None
    if tag in ("SKIL", "MGEF"):
        ix = first_sub(body, b"INDX")
        return (tag, bytes(ix)) if ix else None
    nm = first_sub(body, b"NAME")
    return (tag, cstr(nm).lower()) if nm is not None else None


def digest(*parts):
    h = hashlib.blake2b(digest_size=16)
    for p in parts:
        h.update(p)
    return h.digest()


def plugin_masters(data):
    _off, tag, _flags, body = next(iter_records(data))
    return [cstr(d) for n, d in iter_subs(body) if n == "MAST"] if tag == "TES3" else []


def read_header_masters(path):
    """Masters listed in a plugin's TES3 header (reads only the header)."""
    with open(path, "rb") as f:
        head = f.read(16)
        if len(head) < 16 or head[:4] != b"TES3":
            return []
        size = struct.unpack_from("<I", head, 4)[0]
        body = f.read(size)
    return [cstr(d) for n, d in iter_subs(body) if n == "MAST"]
