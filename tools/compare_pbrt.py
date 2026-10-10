"""compare_pbrt.py — compare PBRT's caustic with our field.

PBRT is driven as the trusted photon-mapping reference (SPPM/BDPT/MLT), which
nothing else installed here provides: Mitsuba 3.9 and Cycles are both brute-force
path tracers and neither converges this caustic.

Both images cover the same 0.32 m patch from an orthographic top-down camera, so
they are directly comparable pixel for pixel.

EXR is read with Mitsuba's bitmap reader rather than adding another dependency.

Run:  python tools/compare_pbrt.py --a out/pbrt/pbrt_caustic.exr
"""
import argparse
import os
import struct
import sys
import zlib

import numpy as np
from PIL import Image

ROOT = "D:/ValueProjects/caustics"
OUT = f"{ROOT}/out"


def read_exr(path):
    sys.path.insert(0, f"{ROOT}/third_party/luxvenv/Lib/site-packages")
    import mitsuba as mi
    mi.set_variant("scalar_spectral")
    return np.array(mi.Bitmap(path)).astype(np.float32)


def read_png16(path):
    d = open(path, "rb").read()
    pos, idat = 8, b""
    while pos < len(d):
        ln, typ = struct.unpack(">I4s", d[pos:pos + 8])
        body = d[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, depth, ct = struct.unpack(">IIBB", body[:10])
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


def tiles(a, k):
    h, w = a.shape
    bh, bw = h // k, w // k
    return a[:bh * k, :bw * k].reshape(k, bh, k, bw).mean(axis=(1, 3))


def corr(a, b, k):
    A, B = tiles(a, k), tiles(b, k)
    A = A - A.mean()
    B = B - B.mean()
    d = np.sqrt((A * A).sum() * (B * B).sum())
    return float((A * B).sum() / d) if d > 0 else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default=f"{OUT}/pbrt/pbrt_caustic.exr",
                    help="PBRT's render")
    ap.add_argument("--field", default=f"{OUT}/caustic_wavy.png")
    args = ap.parse_args()

    p = read_exr(args.a)
    print(f"pbrt  : {p.shape}  mean {p.mean():.6f}  max {p.max():.4f}")
    lum = p.mean(axis=2)
    H, W = lum.shape
    yy, xx = np.mgrid[0:H, 0:W]
    X = (xx / (W - 1) - 0.5) * 320.0
    Y = (0.5 - yy / (H - 1)) * 320.0
    Rg = np.hypot(X, Y)

    # the caustic: what the optics did, relative to the frame's own background.
    # A PBRT render includes the shadow, so the deviation from the median is the
    # only self-contained signal available without a second render.
    sig = lum - np.median(lum)
    pos = np.clip(sig, 0, None)
    m = pos >= np.percentile(pos, 99.0)
    print(f"        caustic (brightest 1%): n={m.sum()}  "
          f"centroid ({X[m].mean():+.1f}, {Y[m].mean():+.1f}) mm  "
          f"|r| {Rg[m].mean():.1f} mm  az {np.degrees(np.arctan2(Y[m].mean(), X[m].mean())):+.1f} deg")
    hot = int((lum > lum.max() * 0.9).sum())
    print(f"        pixels within 10% of the max: {hot}"
          + ("   <- firefly-dominated, shape not trustworthy" if hot < 200 else ""))

    f = read_png16(args.field).mean(axis=2)
    f = np.asarray(Image.fromarray(f.astype(np.float32), mode="F")
                   .resize((W, H)))
    fsig = np.clip(f - np.median(f), 0, None)
    fm = fsig >= np.percentile(fsig, 99.0)
    print(f"ours  : caustic centroid ({X[fm].mean():+.1f}, {Y[fm].mean():+.1f}) mm  "
          f"|r| {Rg[fm].mean():.1f} mm  az "
          f"{np.degrees(np.arctan2(Y[fm].mean(), X[fm].mean())):+.1f} deg")
    print()
    print("correlation of the two caustic signals:")
    for k in (8, 16, 32, 64):
        print(f"   k={k:>3}   {corr(pos, fsig, k):+.3f}")


if __name__ == "__main__":
    main()
