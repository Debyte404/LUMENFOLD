"""tune_spmm_scale.py -- choose the SPMM exposure scale.

Matching the median alone (scale 15.0) put 5%+ of pixels at 255, because SPMM
gets a plain sRGB clip where the Blender frames went through AgX's highlight
rolloff. That reads as washed out. This searches for the largest scale that
keeps clipping negligible, and reports what happens to the table median so the
trade is explicit rather than hidden.
"""
import glob
import sys

import numpy as np
from PIL import Image

ROOT = "D:/ValueProjects/caustics"
PBRT = f"{ROOT}/out/gif_src/spmm"
REF = f"{ROOT}/out/gif_src/ours/f0000.png"


def linear_to_srgb(a):
    return np.where(a <= 0.0031308, a * 12.92,
                    1.055 * np.power(np.clip(a, 0, None), 1 / 2.4) - 0.055)


def main():
    sys.path.insert(0, f"{ROOT}/third_party/luxvenv/Lib/site-packages")
    import mitsuba as mi
    mi.set_variant("scalar_spectral")

    ref = np.asarray(Image.open(REF).convert("RGB")).astype(np.float32)
    ref_lum = ref.mean(axis=2)
    print(f"reference (ours): median {np.median(ref_lum):.1f}  "
          f"p99 {np.percentile(ref_lum,99):.1f}  blown {(ref_lum>=254).mean()*100:.2f}%")
    print()

    a = np.array(mi.Bitmap(sorted(glob.glob(f"{PBRT}/*.exr"))[0])).astype(np.float32)[:, ::-1, :]

    print(f"{'scale':>8} {'median':>8} {'p95':>6} {'p99':>6} {'blown%':>8}  note")
    print("-" * 62)
    best = None
    for scale in (6, 8, 10, 12, 15):
        out = np.clip(linear_to_srgb(a * scale), 0, 1) * 255
        lum = out.mean(axis=2)
        blown = (out.max(axis=2) >= 254).mean() * 100
        note = ""
        if 0.05 <= blown <= 0.8:
            note = "<-- usable: highlights kept"
            if best is None or scale > best[0]:
                best = (scale, np.median(lum), blown)
        print(f"{scale:>8} {np.median(lum):>8.1f} {np.percentile(lum,95):>6.1f} "
              f"{np.percentile(lum,99):>6.1f} {blown:>7.2f}%  {note}")
    print()
    if best:
        print(f"chosen scale {best[0]}: median {best[1]:.1f}, blown {best[2]:.2f}%")
        print(f"  (ours median {np.median(ref_lum):.1f}, blown {(ref_lum>=254).mean()*100:.2f}%)")
    else:
        print("no scale in the tested range kept clipping in band")


if __name__ == "__main__":
    main()
