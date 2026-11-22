"""A small Morrowind (4.0.0.2) model for the tests: a flat square, optionally as the game's special nodes."""
import struct


def _name(text):
    return struct.pack("<I", len(text)) + text


def _av(name=b"", extra=-1, flags=0):
    return _name(name) + struct.pack("<iiH", extra, -1, flags) + \
        struct.pack("<13f", 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 1) + struct.pack("<3f", 0, 0, 0) + struct.pack("<II", 0, 0)


def deck(half, height, root=b"NiNode", extra_text=None, node_name=b""):
    """A square `half` units each way from the origin, `height` over it, under a node of type `root`."""
    vs = [(-half, -half, height), (half, -half, height), (half, half, height), (-half, half, height)]
    node = _name(root) + _av(node_name, 3 if extra_text else -1) + struct.pack("<IiI", 1, 1, 0)
    shape = _name(b"NiTriShape") + _av() + struct.pack("<ii", 2, -1)
    data = _name(b"NiTriShapeData") + struct.pack("<HI", 4, 1) + b"".join(struct.pack("<3f", *v) for v in vs) + \
        struct.pack("<I", 0) + struct.pack("<4f", 0, 0, height, half * 2) + struct.pack("<I", 0) + \
        struct.pack("<HI", 0, 0) + struct.pack("<HI", 2, 6) + struct.pack("<6H", 0, 1, 2, 0, 2, 3) + struct.pack("<H", 0)
    blocks = [node, shape, data]
    if extra_text:
        blocks.append(_name(b"NiStringExtraData") + struct.pack("<iI", -1, 0) + _name(extra_text))
    return b"NetImmerse File Format, Version 4.0.0.2\n" + struct.pack("<II", 0x04000002, len(blocks)) + \
        b"".join(blocks) + struct.pack("<Ii", 1, 0)
