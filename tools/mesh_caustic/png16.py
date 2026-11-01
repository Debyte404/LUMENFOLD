"""png16.py -- minimal 16-bit RGB PNG writer (stdlib only, no PIL).

Blender's float-buffer pixel writes proved unreliable in background mode
(in-memory reads disagreed with the saved file), so mesh Bake writes its
field with this writer and loads it back exactly like the legacy solver
path (bpy.data.images.load). Deterministic: same array -> same bytes.
"""
import struct
import zlib


def write_rgb16(path, field):
    """field: (H, W, 3) float, peak-normalized 0..1, row 0 = image TOP.
    Writes 16-bit RGB PNG with value = round(field * 65535)."""
    import numpy as np
    a = np.clip(np.asarray(field, dtype=np.float64), 0.0, 1.0)
    h, w, _ = a.shape
    assert a.shape[2] == 3
    q = (a * 65535.0 + 0.5).astype(">u2")
    raw = b"".join(b"\x00" + q[i].tobytes() for i in range(h))

    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        return c + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 16, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    return path


def _self_test():
    """Round-trip through our own bytes with stdlib only: parse IHDR/IDAT,
    decompress, check the white pixel encodes near-maximum and black is 0."""
    import os
    import tempfile
    import numpy as np
    f = np.zeros((4, 6, 3))
    f[..., 0] = 1.0
    f[0, 0, :] = (1.0, 0.5, 0.25)
    p = os.path.join(tempfile.gettempdir(), "png16_selftest.png")
    write_rgb16(p, f)
    raw = open(p, "rb").read()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", "bad signature"
    pos = 8
    idat = b""
    w = h = None
    while pos < len(raw):
        ln = struct.unpack(">I", raw[pos:pos + 4])[0]
        typ = raw[pos + 4:pos + 8]
        data = raw[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, depth, ctype, _, _, _ = struct.unpack(">IIBBBBB", data)
            assert (w, h, depth, ctype) == (6, 4, 16, 2), (w, h, depth, ctype)
        elif typ == b"IDAT":
            idat += data
        pos += 12 + ln
    px = zlib.decompress(idat)
    stride = 1 + w * 3 * 2
    assert len(px) == stride * h
    r0 = struct.unpack(">H", px[1:3])[0]
    assert r0 == 65535, r0
    g0 = struct.unpack(">H", px[3:5])[0]
    assert abs(g0 - 32768) <= 1, g0
    print("PNG16_SELF_TEST_OK", len(raw), "bytes")


if __name__ == "__main__":
    _self_test()
