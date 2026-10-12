"""metric_parity_check.py -- score ours, SPPM and Cycles against the SAME
ground truth with the SAME two conventions, side by side.

Why: spmm_vs_groundtruth.py returned SPPM r = +0.400 at 40 mm tiles against the
brute-force ground truth, while SPPM correlates r = +0.932 with our field and
our field correlates 0.916 (40 mm) / 0.720 (5 mm) with that same ground truth.
Those three numbers cannot all be right under one metric -- if A~B and A~C then
B~C is bounded below by roughly |r_AB + r_AC - 1| style constraints, not 0.4.

The suspicion is the metric, not the renderers:
  * tools/compare_pbrt.py (SPPM vs ours) clips to the POSITIVE part before
    correlating: pos = clip(d - mean, 0, None).
  * tools/accuracy_vs_ground_truth.py (ours/Cycles vs ground truth) correlates
    the raw mean-subtracted maps.
If SPPM's differential carries a negative mean (it does: -0.0215), the raw
convention lets negative pixels dominate the fine tiles.

This tool scores all three methods, both conventions, and reports where the
ordering depends on the metric. A claim that flips with the convention is not
a result.

Run:  luxvenv/Scripts/python tools/metric_parity_check.py
"""
import os
import struct
import sys
import zlib

import numpy as np
from PIL import Image


# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_ray_map as V

ROOT = _ROOT
OUT = f"{ROOT}/out"


def exr(path):
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


def corr(a, b, k):
    h, w = a.shape
    A = a[:h // k * k, :w // k * k].reshape(h // k, k, w // k, k).mean(axis=(1, 3))
    B = b[:h // k * k, :w // k * k].reshape(h // k, k, w // k, k).mean(axis=(1, 3))
    A = A - A.mean()
    B = B - B.mean()
    dd = np.sqrt((A * A).sum() * (B * B).sum())
    return float((A * B).sum() / dd) if dd > 0 else 0.0


def main():
    X, Y, nhit, nwall, nesc = V.trace()
    gt = V.to_grid(X, Y)
    H, W = gt.shape

    # --- our field
    fld = read_png16(f"{OUT}/caustic_wavy.png").mean(axis=2)
    ours = np.asarray(Image.fromarray(fld.astype(np.float32), mode="F").resize((W, H), Image.BOX))

    # --- Cycles' caustic-only signal (caustics on minus off)
    def srgb_to_linear(a):
        return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)

    def lum(p):
        return srgb_to_linear(np.asarray(Image.open(p).convert("RGB")).astype(np.float32) / 255.0).mean(axis=2)

    cyc = np.clip(lum(f"{OUT}/ortho_glass.png") - lum(f"{OUT}/ortho_nocaustic.png"), 0, None)
    cyc = np.asarray(Image.fromarray(cyc.astype(np.float32), mode="F").resize((W, H), Image.BOX))

    # --- SPPM differential
    d = ((exr(f"{OUT}/pbrt/pbrt_shape_optics.exr") - exr(f"{OUT}/pbrt/pbrt_shape_nooptics.exr")).mean(axis=2))[:, ::-1]
    spmm = np.asarray(Image.fromarray(d.astype(np.float32), mode="F").resize((W, H), Image.BOX))

    methods = {"ours": ours, "SPPM": spmm, "Cycles": cyc}

    print("ground truth:", f"{gt.sum():.0f} hits, {100*(gt>0).mean():.2f}% of pixels")
    print()
    for conv in ("raw mean-subtracted", "positive part only"):
        print(f"--- convention: {conv} ---")
        gt_v = gt - gt.mean() if conv == "raw mean-subtracted" else np.clip(gt - np.median(gt), 0, None)
        print(f"  {'tiles':>6} {'ours':>8} {'SPPM':>8} {'Cycles':>8}")
        for k in (8, 16, 32, 64):
            row = []
            for name, m in methods.items():
                v = m - m.mean() if conv == "raw mean-subtracted" else np.clip(m - np.median(m), 0, None)
                row.append(corr(gt_v, v, k))
            print(f"  {k:>6} {row[0]:>8.3f} {row[1]:>8.3f} {row[2]:>8.3f}")
        print()

    print("--- diagnostic: does SPPM's differential carry a negative mean? ---")
    print(f"  SPPM differential mean {d.mean():+.5f}  min {d.min():+.4f}  max {d.max():+.4f}")
    print(f"  negative pixels: {100*(d < 0).mean():.1f}%   |neg| sum / |pos| sum = "
          f"{np.abs(d[d < 0]).sum() / max(d[d > 0].sum(), 1e-9):.3f}")
    print()
    print("--- cross-check: SPPM vs OUR field (the comparison that gave 0.932) ---")
    a = np.clip(spmm - spmm.mean(), 0, None)
    b = np.clip(ours - ours.mean(), 0, None)
    for k in (8, 16, 32, 64):
        print(f"  k={k:>3}  r = {corr(a, b, k):+.3f}")


if __name__ == "__main__":
    main()
