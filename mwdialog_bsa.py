"""mwdialog_bsa.py - reading Morrowind BSA archives: the directory, the file names, and a memo so each
archive is read once per run while it is unchanged.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mwdialog_tes3 import (  # noqa: E402
    FormatError, cstr)


def _bsa_directory(path):
    """(count, hash table offset, directory block) of a TES3 BSA, or None if it isn't one. A header whose
    numbers don't fit the file raises FormatError (a damaged or unusual archive), never struct.error."""
    with open(path, "rb") as f:
        head = f.read(12)
        if len(head) < 12:
            return None
        version, hash_off, count = struct.unpack("<III", head)
        if version != 0x100:
            return None
        size = os.fstat(f.fileno()).st_size
        if 12 * count > hash_off or 12 + hash_off > size:
            raise FormatError(f"{os.path.basename(path)}: BSA header doesn't fit the file "
                              f"({count} files, directory {hash_off} bytes, file {size} bytes)")
        block = f.read(hash_off)
    if len(block) < hash_off:
        raise FormatError(f"{os.path.basename(path)}: BSA directory is cut short")
    return count, hash_off, block


_BSA_MEMO = {}            # (what, path) -> ((size, mtime_ns), result): a BSA is read once per run while unchanged


def _bsa_memo(kind, path, read):
    """read(path), remembered for this run while the BSA's size and date stay the same. The result is shared:
    callers must not change it."""
    try:
        st = os.stat(path)
    except OSError:
        return read(path)
    sig = (st.st_size, st.st_mtime_ns)
    key = (kind, os.path.normcase(os.path.abspath(path)))
    hit = _BSA_MEMO.get(key)
    if hit is not None and hit[0] == sig:
        return hit[1]
    res = read(path)
    _BSA_MEMO[key] = (sig, res)
    return res


def bsa_file_names(path):
    """Return lowercase forward-slash paths of every file in a TES3 BSA (FormatError if it's damaged).
    Remembered for the run while the BSA is unchanged (don't change the set you get)."""
    return _bsa_memo("names", path, _bsa_file_names)


def _bsa_file_names(path):
    names = set()
    d = _bsa_directory(path)
    if d is None:
        return names
    count, _hash_off, block = d
    name_offsets = struct.unpack_from(f"<{count}I", block, 8 * count)
    names_start = 12 * count
    for o in name_offsets:
        if names_start + o >= len(block):
            raise FormatError(f"{os.path.basename(path)}: a file name lies outside the BSA directory")
        names.add(cstr(block[names_start + o:names_start + o + 260]).lower().replace("\\", "/"))
    return names


def bsa_index(path):
    """{lowercase backslash path: (absolute offset, size)} of every file in a TES3 BSA. Remembered for the run
    while the BSA is unchanged (don't change the dict you get)."""
    return _bsa_memo("index", path, _bsa_index)


def _bsa_index(path):
    out = {}
    d = _bsa_directory(path)
    if d is None:
        return out
    count, hash_off, block = d
    sizes_offs = [struct.unpack_from("<II", block, 8 * i) for i in range(count)]
    name_offs = struct.unpack_from(f"<{count}I", block, 8 * count)
    names = block[12 * count:]
    data_start = 12 + hash_off + 8 * count
    for (size, off), no in zip(sizes_offs, name_offs):
        if no >= len(names):
            raise FormatError(f"{os.path.basename(path)}: a file name lies outside the BSA directory")
        end = names.find(b"\0", no)
        nm = names[no:end].decode("latin-1", "ignore").replace("/", "\\").lower().strip("\\")
        out[nm] = (data_start + off, size)
    return out
