"""mwdialog_media.py - asset file formats: DDS textures (reading, reducing, placeholders), NIF models (texture
names, text keys, empty models) and sound files (MP3/WAV sanity, silent stand-ins).
"""
import os
import re
import struct


SOUND_ROOTS = []                                 # the Data Files folders the sound index came from

_SOUND_PROBLEMS = {}


def mp3_first_frame(b):
    """Offset of the first MPEG layer-3 frame that's followed by another one where its length says (so not a
    chance match inside a tag), or None."""
    BR = {3: (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320),
          2: (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)}
    SR = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}

    def frame_len(j):
        if j + 4 > len(b) or b[j] != 0xFF or (b[j + 1] & 0xE0) != 0xE0:
            return None
        ver, layer, bri, sri, pad = (b[j + 1] >> 3) & 3, (b[j + 1] >> 1) & 3, b[j + 2] >> 4, (b[j + 2] >> 2) & 3, \
            (b[j + 2] >> 1) & 1
        if ver == 1 or layer != 1 or bri in (0, 15) or sri == 3:
            return None
        br = BR[3 if ver == 3 else 2][bri] * 1000
        sr = SR[ver][sri]
        return (144 if ver == 3 else 72) * br // sr + pad
    j = b.find(b"\xff")
    while j != -1 and j + 4 <= len(b):
        n = frame_len(j)
        if n and (j + n + 4 > len(b) or frame_len(j + n)):
            return j
        j = b.find(b"\xff", j + 1)
    return None


def sound_file_problem(rel):
    """Why a loose sound file (relative, e.g. 'sound/vo/i/m/hlo_im001.mp3') could hang or crash the game's
    audio, or None. Reads only the start of the file. Files only in a BSA aren't checked."""
    if rel in _SOUND_PROBLEMS:
        return _SOUND_PROBLEMS[rel]
    path = next((os.path.join(d, rel) for d in SOUND_ROOTS if os.path.isfile(os.path.join(d, rel))), None)
    prob = None
    if path:
        try:
            with open(path, "rb") as f:
                b = f.read(8192)
        except OSError:
            b = None
        lo = rel.lower()
        if b is None:
            prob = "can't be read"
        elif len(b) < 64:
            prob = "is empty"
        elif lo.endswith(".mp3"):
            if b[:4] == b"RIFF":
                prob = "is a WAV file named .mp3"
            else:
                tag_end = 0
                if b[:3] == b"ID3" and len(b) >= 10:
                    tag_end = 10 + ((b[6] << 21) | (b[7] << 14) | (b[8] << 7) | b[9])
                    if tag_end > 65536:
                        prob = "has a very large tag (embedded artwork?) before the sound"
                first = mp3_first_frame(b) if prob is None else None
                if prob is None:
                    if first is None:
                        if tag_end < len(b):
                            prob = "has no MP3 audio in it"
                    elif first - tag_end > 64:
                        prob = ("has a damaged tag in front of the sound (its header doesn't match what follows, "
                                "so a player reading from the start hits junk)") if tag_end else \
                               "has junk in front of the sound"
        elif lo.endswith(".wav"):
            if b[:3] == b"ID3" or b[:2] in (b"\xff\xfb", b"\xff\xf3"):
                prob = "is an MP3 file named .wav"
            elif b[:4] != b"RIFF" or b[8:12] != b"WAVE":
                prob = "isn't a real WAV file"
            else:
                k, fmt = 12, None
                while k + 8 <= len(b):
                    cid, csz = b[k:k + 4], struct.unpack_from("<I", b, k + 4)[0]
                    if cid == b"fmt ":
                        fmt = b[k + 8:k + 24]
                        break
                    k += 8 + csz + (csz & 1)
                if not fmt or len(fmt) < 16:
                    prob = "is a WAV with no format block"
                else:
                    tag, ch, _rate, _br, _al, bits = struct.unpack_from("<HHIIHH", fmt)
                    if tag not in (1, 2, 0x11):
                        prob = f"is a WAV in a codec the game can't play ({tag})"
                    elif tag == 1 and bits not in (8, 16):
                        prob = f"is a {bits}-bit WAV (the game plays 8 or 16 bit)"
                    elif ch > 2:
                        prob = f"is a {ch}-channel WAV"
    _SOUND_PROBLEMS[rel] = prob
    return prob


TEXT_KEY_TAG = b"\x12\x00\x00\x00NiTextKeyExtraData"


def nif_text_keys_lf(data):
    """Animation text keys (NiTextKeyExtraData, Morrowind NIF/KF 4.0.0.2) with Unix line endings: the engine
    splits a key's lines on CR LF, and a key joined with a bare LF crashes the game (seen from a .kf
    injector). Returns (number of bad keys, repaired file data or None)."""
    if not data.startswith(b"NetImmerse File Format, Version 4.0.0.2") or TEXT_KEY_TAG not in data:
        return 0, None
    out, last, bad, pos = [], 0, 0, 0
    while True:
        k = data.find(TEXT_KEY_TAG, pos)
        if k < 0:
            break
        q = k + len(TEXT_KEY_TAG)
        pos = q
        try:
            _next, _unk, n = struct.unpack_from("<iII", data, q)
            q += 12
            if n > 100000:
                continue
            keys = []
            for _ in range(n):
                (ln,) = struct.unpack_from("<I", data, q + 4)
                if ln > 65536 or q + 8 + ln > len(data):
                    raise ValueError
                keys.append((q + 4, ln))
                q += 8 + ln
        except (struct.error, ValueError):
            continue                                # not a block we can read: leave it alone
        for at, ln in keys:
            txt = data[at + 4:at + 4 + ln]
            fixed = re.sub(rb"(?<!\r)\n", b"\r\n", txt)
            if fixed != txt:
                bad += 1
                out.append(data[last:at])
                out.append(struct.pack("<I", len(fixed)) + fixed)
                last = at + 4 + ln
        pos = q
    if not bad:
        return 0, None
    out.append(data[last:])
    return bad, b"".join(out)


_NIF_TEX_CHARS = b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-\\/ .@#$%&'()+,;=[]{}~!"

_NIF_TEX_OK = bytearray(256)

_NIF_EXT_RE = re.compile(rb"\.(?:dds|tga|bmp)", re.I)


def nif_texture_names(b):
    """NIF_TEXTURE_RE.findall(b), about 15x faster: finds each extension first, then the start of the run of
    name characters before it. Like the regex, one name per run: from the run's start to its last .dds/.tga/
    .bmp that has a character before it."""
    out = []
    start = match_end = scanned = -1
    for mm in _NIF_EXT_RE.finditer(b):
        i, e = mm.span()
        if not (scanned >= 0 and not b[scanned:i].translate(None, _NIF_TEX_CHARS)):
            if match_end >= 0:                          # a new run: the last one's name is done
                out.append(b[start:match_end])
            match_end = -1
            start = i
            while start > 0 and _NIF_TEX_OK[b[start - 1]]:
                start -= 1
        if i > start:
            match_end = e
        scanned = e
    if match_end >= 0:
        out.append(b[start:match_end])
    return out


def nif_texture_refs(b):
    """The textures a NIF names: paths under Textures, lowercase, backslashes, with the extension the model
    gives (sorted, no repeats)."""
    out = set()
    for raw in nif_texture_names(b):
        s = raw.decode("latin-1", "ignore").strip().replace("/", "\\").lower().lstrip("\\")
        s = s.lstrip(" .")
        if len(s) <= 4:
            continue
        i = s.find("textures\\")
        if i != -1:
            s = s[i + 9:]
        out.add(s)
    return sorted(out)


DDS_BLOCK_FOURCC = {b"DXT1": 8, b"DXT2": 16, b"DXT3": 16, b"DXT4": 16, b"DXT5": 16, b"ATI1": 8, b"BC4U": 8,
                    b"BC4S": 8, b"ATI2": 16, b"BC5U": 16, b"BC5S": 16}

DDS_DXGI_BLOCK = {**{f: 8 for f in (70, 71, 72, 79, 80, 81)},
                  **{f: 16 for f in (73, 74, 75, 76, 77, 78, 82, 83, 84, 94, 95, 96, 97, 98, 99)}}

DDS_DXGI_BPP = {27: 32, 28: 32, 29: 32, 87: 32, 88: 32, 91: 32, 85: 16, 86: 16, 61: 8}

TEXTURE_MAX_EDGE = 2048


def dds_info(head):
    """(width, height, mip levels, header length, bytes per 4x4 block or None, bits per pixel or None),
    or None for a DDS this can't handle (cube maps, volume textures, unknown formats)."""
    if len(head) < 128 or head[:4] != b"DDS ":
        return None
    h, w, _pitch, depth, mips = struct.unpack_from("<5I", head, 12)
    caps2 = struct.unpack_from("<I", head, 112)[0]
    if caps2 & 0x200 or caps2 & 0x200000 or depth > 1:          # cube map / volume
        return None
    pf_flags, fourcc, bits = struct.unpack_from("<I4sI", head, 80)
    hdr, block, bpp = 128, None, None
    if pf_flags & 0x4:                                       # FourCC
        if fourcc == b"DX10":
            if len(head) < 148:
                return None
            fmt, dim, misc, arr = struct.unpack_from("<4I", head, 128)
            if dim != 3 or arr > 1 or misc & 0x4:             # only plain 2D textures
                return None
            hdr = 148
            block, bpp = DDS_DXGI_BLOCK.get(fmt), DDS_DXGI_BPP.get(fmt)
        else:
            block = DDS_BLOCK_FOURCC.get(fourcc)
    elif pf_flags & (0x40 | 0x20000 | 0x2 | 0x200):          # RGB, luminance, alpha, YUV: uncompressed
        bpp = bits
    if not block and not bpp:
        return None
    return w, h, max(1, mips), hdr, block, bpp


def dds_level_size(w, h, block, bpp):
    if block:
        return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * block
    return max(1, (w * bpp + 7) // 8) * h


def dds_reduce(data, max_edge=TEXTURE_MAX_EDGE):
    """The same DDS with its largest mipmap levels dropped, so no edge is over max_edge. Uses the
    smaller versions the file already holds: nothing is re-encoded. Returns (bytes, (w, h, new w,
    new h)) or (None, reason)."""
    info = dds_info(data[:148])
    if info is None:
        return None, "a format this can't shrink (cube map, volume or unusual format)"
    w, h, mips, hdr, block, bpp = info
    k = 0
    while max(w >> k, 1) > max_edge or max(h >> k, 1) > max_edge:
        k += 1
    if k == 0:
        return None, "already small enough"
    if mips <= k:
        return None, "it has no smaller versions inside it (mipmaps) to fall back on"
    sizes = [dds_level_size(max(w >> i, 1), max(h >> i, 1), block, bpp) for i in range(mips)]
    if hdr + sum(sizes) > len(data):
        return None, "the file is shorter than its header says"
    start = hdr + sum(sizes[:k])
    body = data[start:start + sum(sizes[k:])]
    nw, nh = max(w >> k, 1), max(h >> k, 1)
    head = bytearray(data[:hdr])
    struct.pack_into("<3I", head, 12, nh, nw, sizes[k] if block else max(1, (nw * bpp + 7) // 8))
    struct.pack_into("<I", head, 28, mips - k)
    flags = struct.unpack_from("<I", head, 8)[0]
    flags = (flags | 0x80000) & ~0x8 if block else (flags | 0x8) & ~0x80000     # LINEARSIZE vs PITCH
    struct.pack_into("<I", head, 8, flags | 0x20000)                            # MIPMAPCOUNT
    return bytes(head) + body, (w, h, nw, nh)


def placeholder_dds(name):
    """A 4x4 uncompressed DDS for a missing texture: a flat normal map for *_nm / *_n, black for glow,
    reflection and specular maps (so they add nothing), plain grey otherwise."""
    stem = os.path.splitext(os.path.basename(name).lower())[0]
    if stem.endswith(("_nm", "_n", "_normal", "_nrm")):
        bgra = (255, 128, 128, 255)
    elif stem.endswith(("_glow", "_g", "_ref", "_spec", "_s", "_em", "_lum")):
        bgra = (0, 0, 0, 255)
    else:
        bgra = (128, 128, 128, 255)
    w = h = 4
    head = struct.pack("<4sIIIIIII44sIIIIIIIIIIIII", b"DDS ", 124, 0x100F, h, w, w * 4, 0, 0, bytes(44),
                       32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000, 0x1000, 0, 0, 0, 0)
    return head + bytes(bgra) * (w * h)


def stand_in_bytes(rel):
    ext = os.path.splitext(rel)[1].lower()
    if ext == ".kf":                        # an animation: the game's smallest one (a few frames, harmless)
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), DUMMY_KF), "rb") as f:
            return f.read()
    if ext == ".nif":                       # a missing model: a small coin, not the engine's huge "!" marker
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), DUMMY_NIF), "rb") as f:
            return f.read()
    if ext == ".dds" and rel.replace("/", "\\").lower().startswith("icons\\"):
        return placeholder_icon()
    if ext == ".dds":
        return placeholder_dds(rel)
    return silent_audio(ext or ".wav")


def placeholder_icon():
    """A 32x32 inventory icon: grey square with a red exclamation mark, so a missing icon is visible."""
    w = h = 32
    head = struct.pack("<4sIIIIIII44sIIIIIIIIIIIII", b"DDS ", 124, 0x100F, h, w, w * 4, 0, 0, bytes(44),
                       32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000, 0x1000, 0, 0, 0, 0)
    px = bytearray()
    for y in range(h):
        for x in range(w):
            edge = x in (0, w - 1) or y in (0, h - 1)
            bar = 13 <= x <= 18 and 4 <= y <= 20 and not (y >= 17 and x in (13, 18))   # tapers at the foot
            dot = 13 <= x <= 18 and 23 <= y <= 27
            px += bytes((40, 40, 210, 255)) if bar or dot else \
                bytes((60, 60, 60, 255)) if edge else bytes((110, 110, 110, 255))
    return head + bytes(px)


def silent_audio(ext):
    """A short silent sound: a WAV (22,050 Hz mono, 16-bit, 0.2 s) or an MP3 (MPEG-1 Layer III frames
    with no audio data, which decode as silence)."""
    if ext.lower() == ".mp3":
        frame = b"\xff\xfb\x90\x64" + bytes(413)          # 128 kbit/s, 44.1 kHz: 417-byte frames
        return frame * 8
    rate, n = 22050, 4410
    data = bytes(2 * n)
    return (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " +
            struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + b"data" + struct.pack("<I", len(data)) + data)


DUMMY_NIF = "mwdialog_dummy.nif"       # next to this file: a small vanilla Dwemer coin, for missing models

DUMMY_KF = "mwdialog_dummy.kf"                   # the game's xin_dagoth_bridge00.kf (510 bytes): broken animations


def nif_is_empty(data):
    """A model with nothing to draw: a NIF without any shape (RR's ex_dummy.nif, the 'hide this object'
    models). A mod uses one on purpose, but only alongside its own replacement - carried into a merge
    without that, it just makes the object vanish."""
    if not data.startswith((b"NetImmerse File Format", b"Gamebryo File Format")):
        return False
    return len(data) < 4096 and not any(t in data for t in (b"NiTriShape", b"NiTriStrips", b"NiParticle",
                                                              b"NiSkinInstance", b"NiLines"))
