"""spmm_vs_groundtruth.py -- score PBRT-v4 SPPM on the SAME independent ground
truth we score our field and Cycles against, with a like-for-like metric.

The quality table in the paper gives SPPM only "shape correlation vs ours"
(r = +0.932). That is a comparison between two methods, not a score on the
independent axis. This puts all three on ONE axis.

Two traps this tool exists to avoid, both caught by tools/metric_parity_check.py:

 1. TILE NAMING. k here is tile SIZE IN PIXELS (the map is 512 px for a 320 mm
    patch, so 0.625 mm/px): k=8 -> 5 mm tiles, k=64 -> 40 mm tiles. EVIDENCE's
    tables name the 40 mm row "8", meaning EIGHT tiles per side. Same numbers,
    opposite convention -- the trap EVIDENCE 11.2 already documents once.

 2. SIGN CONVENTION. SPPM's caustic is isolated as optics - no_optics. That
    differential is NOT non-negative: removing the glass also removes its
    shadow, so 11.4% of pixels go negative with |neg| / |pos| = 1.40. Scored
    RAW it is dominated by shadow inversion and SPPM reads r = -0.046 at
    40 mm; scored on the POSITIVE PART (the caustic) it reads r = +0.853. The
    positive-part convention is the one that isolates the caustic, and it is
    the one used in the comparison. Both are printed so the choice is visible.

Run:  luxvenv/Scripts/python tools/spmm_vs_groundtruth.py
"""
import os
import sys

import numpy as np
from PIL import Image


# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_ray_map as V

ROOT = _ROOT
OUT = f"{ROOT}/out"
PATCH_MM = 320.0

# (tile size in pixels, the patch size that corresponds to)
TILES = [(64, 40), (32, 20), (16, 10), (8, 5)]


def exr(path):
    sys.path.insert(0, f"{ROOT}/third_party/luxvenv/Lib/site-packages")
    import mitsuba as mi
    mi.set_variant("scalar_spectral")
    return np.array(mi.Bitmap(path)).astype(np.float32)


def corr(a, b, size):
    """Correlate on a grid of `size` x `size` pixel tiles."""
    h, w = a.shape
    nh, nw = h // size, w // size
    A = a[:nh * size, :nw * size].reshape(nh, size, nw, size).mean(axis=(1, 3))
    B = b[:nh * size, :nw * size].reshape(nh, size, nw, size).mean(axis=(1, 3))
    A = A - A.mean()
    B = B - B.mean()
    dd = np.sqrt((A * A).sum() * (B * B).sum())
    return float((A * B).sum() / dd) if dd > 0 else 0.0


def main():
    print("=== SPPM vs the independent geometric ground truth ===")
    w = exr(f"{OUT}/pbrt/pbrt_shape_optics.exr")
    o = exr(f"{OUT}/pbrt/pbrt_shape_nooptics.exr")
    d = ((w - o).mean(axis=2))[:, ::-1]        # X-mirror correction, EVIDENCE 19.2

    X, Y, nhit, nwall, nesc = V.trace()
    gt = V.to_grid(X, Y)
    H, W = gt.shape
    sp = np.asarray(Image.fromarray(d.astype(np.float32), mode="F").resize((W, H), Image.BOX))

    print(f"  SPPM differential: {d.shape}  mean {d.mean():+.5f}  max {d.max():.4f}")
    print(f"  negative pixels {100*(d < 0).mean():.1f}%, |neg|/|pos| = "
          f"{np.abs(d[d < 0]).sum() / max(d[d > 0].sum(), 1e-9):.3f}  "
          f"(shadow inversion -- not caustic)")
    print(f"  ground truth: {gt.sum():.0f} hits on the patch ({100*(gt>0).mean():.2f}% of pixels)")
    print()

    # Like-for-like: caustic = positive part beyond the map median, both sides.
    gt_p = np.clip(gt - np.median(gt), 0, None)
    sp_p = np.clip(sp - np.median(sp), 0, None)
    gt_r = gt - gt.mean()
    sp_r = sp - sp.mean()

    print("  convention: POSITIVE PART (isolates the caustic -- used in the paper)")
    print(f"  {'tile':>8} {'SPPM':>8}")
    for size, mm in TILES:
        print(f"  {mm:>5} mm {corr(gt_p, sp_p, size):>8.3f}")

    print()
    print("  convention: RAW mean-subtracted (dominated by shadow inversion)")
    print(f"  {'tile':>8} {'SPPM':>8}")
    for size, mm in TILES:
        print(f"  {mm:>5} mm {corr(gt_r, sp_r, size):>8.3f}")

    print()
    print("  side by side on the SAME ground truth, positive-part metric")
    print("  (ours/Cycles re-measured here at 512^2 so the metric is identical):")

    import struct
    import zlib

    def read_png16(path):
        dd = open(path, "rb").read()
        pos, idat = 8, b""
        while pos < len(dd):
            ln, typ = struct.unpack(">I4s", dd[pos:pos + 8])
            body = dd[pos + 8:pos + 8 + ln]
            if typ == b"IHDR":
                ww, hh, depth, ct = struct.unpack(">IIBB", body[:10])
            elif typ == b"IDAT":
                idat += body
            elif typ == b"IEND":
                break
            pos += 12 + ln
        raw = zlib.decompress(idat)
        stride = ww * 3 * 2
        out = np.zeros((hh, ww, 3), np.uint16)
        p = 0
        for y in range(hh):
            p += 1
            out[y] = np.frombuffer(raw[p:p + stride], dtype=">u2").reshape(ww, 3)
            p += stride
        return out.astype(np.float32) / 65535.0 * 16.0

    fld = read_png16(f"{OUT}/caustic_wavy.png").mean(axis=2)
    ours = np.asarray(Image.fromarray(fld.astype(np.float32), mode="F").resize((W, H), Image.BOX))

    def srgb_to_linear(a):
        return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)

    def lum(p):
        return srgb_to_linear(np.asarray(Image.open(p).convert("RGB")).astype(np.float32) / 255.0).mean(axis=2)

    cyc = np.clip(lum(f"{OUT}/ortho_glass.png") - lum(f"{OUT}/ortho_nocaustic.png"), 0, None)
    cyc = np.asarray(Image.fromarray(cyc.astype(np.float32), mode="F").resize((W, H), Image.BOX))

    ours_p = np.clip(ours - np.median(ours), 0, None)
    cyc_p = np.clip(cyc - np.median(cyc), 0, None)

    print(f"  {'tile':>8} {'ours':>8} {'SPPM':>8} {'Cycles':>8}")
    res = {}
    for size, mm in TILES:
        r_o = corr(gt_p, ours_p, size)
        r_s = corr(gt_p, sp_p, size)
        r_c = corr(gt_p, cyc_p, size)
        res[mm] = (r_o, r_s, r_c)
        print(f"  {mm:>5} mm {r_o:>8.3f} {r_s:>8.3f} {r_c:>8.3f}")

    print()
    print("  ranking at 40 mm tiles (coarsest, most stable):")
    order = sorted(res[40], reverse=True)
    names = ["ours", "SPPM", "Cycles"]
    rank = sorted(zip(names, res[40]), key=lambda t: -t[1])
    for i, (n, v) in enumerate(rank, 1):
        print(f"    {i}. {n:6s} {v:.3f}")
    print()
    print("  NOTE: SPPM's estimate is radius-dependent (initial radius 6 mm, 256")
    print("  iterations x 1 M photons), so its 5 mm-tile number is limited by")
    print("  photon-map density rather than by any smoothing model.")


if __name__ == "__main__":
    main()
