"""accuracy_vs_ground_truth.py — which method's caustic is closer to an
independent geometric ground truth?

The critique's main complaint about the noise comparison is that each method was
scored against its own reference. This measures something the self-references
cannot: distance from an INDEPENDENT reference that neither method produced.

The ground truth is the brute-force trace in tools/verify_ray_map.py — uniform
ray launch, explicit intersections, no parametrisation, no Jacobian. Its density
of hits IS the refracted light distribution, which is exactly the quantity both
methods are trying to reproduce.

Compared against it:
  ours    the baked field itself (the thing we inject)
  Cycles  its caustic-only signal: (caustics ON) minus (caustics OFF), which
          cancels the shadow and leaves the light the glass concentrated

A trap that caught this file's first version: correlating a RENDER against the
ground truth is dominated by the render's shadow, which the ground truth does not
contain. Both methods scored negative (-0.54 and -0.80) not because they were
wrong but because dark-shadow-pixel-versus-bright-caustic-pixel is an inverse
relationship. Only shadow-cancelled or geometric quantities may be compared here.

Run:  python tools/accuracy_vs_ground_truth.py
"""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify_ray_map as V

OUT = "D:/ValueProjects/caustics/out"


def srgb_to_linear(a):
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def lum(p):
    return srgb_to_linear(
        np.asarray(Image.open(p).convert("RGB")).astype(np.float32) / 255.0).mean(axis=2)


def read_png16(path):
    """Our exporter writes 16-bit RGB; PIL would silently downconvert it."""
    import struct
    import zlib
    d = open(path, "rb").read()
    pos, idat, w = 8, b"", None
    while pos < len(d):
        ln, typ = struct.unpack(">I4s", d[pos:pos + 8])
        body = d[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, depth, ct = struct.unpack(">IIBB", body[:10])
            assert depth == 16 and ct == 2, (depth, ct)
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break
        pos += 12 + ln
    raw = zlib.decompress(idat)
    stride = w * 3 * 2
    out = np.zeros((h, w, 3), np.uint16)
    p = 0
    for y in range(h):
        p += 1
        out[y] = np.frombuffer(raw[p:p + stride], dtype=">u2").reshape(w, 3)
        p += stride
    return out.astype(np.float32) / 65535.0 * 16.0


def corr(a, b, k):
    A, B = V.tiles(a, k), V.tiles(b, k)
    A = A - A.mean()
    B = B - B.mean()
    d = np.sqrt((A * A).sum() * (B * B).sum())
    return float((A * B).sum() / d) if d > 0 else 0.0


def main():
    print("building the independent ground truth (brute-force trace)...")
    X, Y, nhit, nwall, nesc = V.trace(n_side=1400)
    gt = V.to_grid(X, Y)
    print(f"  {nhit} hits from {1400*1400} rays "
          f"({100*(gt > 0).mean():.2f}% of pixels carry refracted light)")

    field = read_png16(f"{OUT}/caustic_wavy.png")
    fld = field.mean(axis=2)
    fld = np.asarray(Image.fromarray(fld.astype(np.float32), mode="F")
                     .resize(gt.shape[::-1], Image.BOX))

    on = lum(f"{OUT}/ortho_glass.png")
    off = lum(f"{OUT}/ortho_nocaustic.png")
    cyc = np.clip(on - off, 0, None)          # caustic only, shadow cancelled

    print()
    print("correlation against the independent ground truth")
    print("(higher = that method's caustic is closer to the real one)")
    print(f"  {'tiles':>6} {'tile':>6} {'OUR FIELD':>11} {'CYCLES':>9}")
    for k in (8, 16, 32, 64):
        c2 = corr(gt, cyc, k)
        print(f"  {k:>6} {320//k:>5}mm {corr(gt, fld, k):>11.3f} {c2:>9.3f}")

    print()
    # overlap: of the pixels the ground truth says carry caustic light, how many
    # does each method actually mark bright?
    gt_mask = gt > np.percentile(gt[gt > 0], 90)
    f_mask = fld > np.percentile(fld, 95)
    c_mask = cyc > np.percentile(cyc, 95)
    print(f"  ground-truth caustic core: {100*gt_mask.mean():.2f}% of frame")
    print(f"    our field covers : {100*(f_mask & gt_mask).sum()/gt_mask.sum():5.1f}% of it")
    print(f"    Cycles covers    : {100*(c_mask & gt_mask).sum()/gt_mask.sum():5.1f}% of it")


if __name__ == "__main__":
    main()
