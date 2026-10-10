"""clip_flicker.py — the metric that matters for an ANIMATION.

For a still, the cost of a noisy caustic is a grainy image. For an animation it
is worse: Monte-Carlo draw-to-draw variation appears as flicker, and a caustic is
the worst place for it because it is the brightest, thinnest, slowest-converging
feature in the frame. Two clips can look identical frame by frame and one can
still shimmer.

So the comparison here is temporal, not spatial:

    flicker = mean |frame_t - frame_(t+1)|  inside the caustic region

Both clips are rendered with the identical camera path, water geometry, wave
phase schedule and sample count, so the only source of frame-to-frame variation
that is not genuine motion is sampling noise. Our caustic is deterministic and
adds none; Cycles' is path-traced and does.

A control region is measured too: pixels far from the caustic, where both renders
are dominated by smooth, genuinely-moving shading. If the control numbers are
similar while the caustic numbers diverge, the difference is the caustic, not the
motion.

Run:  python tools/clip_flicker.py
"""
import glob
import os

import numpy as np
from PIL import Image

OUT = "D:/ValueProjects/caustics/out"
FRAMES = f"{OUT}/frames"

PAIRS = [
    ("ripple", "ours: animated caustic (injected)"),
    ("cycles_ripple", "Cycles: caustic path-traced"),
    ("combined", "ours: orbit + animated caustic"),
    ("cycles_combined", "Cycles: same clip"),
]


def load_dir(d):
    files = sorted(glob.glob(f"{d}/*.png"))
    if not files:
        return None, None
    arr = np.stack([
        np.asarray(Image.open(f).convert("RGB")).astype(np.float32).mean(axis=2)
        for f in files])
    return arr, files


def main():
    results = {}
    for name, label in PAIRS:
        a, files = load_dir(f"{FRAMES}/{name}")
        if a is None:
            print(f"[{name}] no frames found, skipped")
            continue
        n = a.shape[0]
        # caustic region: where the clip is bright on average (the caustic is the
        # brightest thing in frame) - q0 maps to it regardless of the setting
        mean = a.mean(axis=0)
        dist = np.abs(np.diff(a, axis=0)).mean(axis=0)
        caus = mean >= np.percentile(mean, 97)
        control = mean <= np.percentile(mean, 50)
        results[name] = {
            "frames": n,
            "flicker_caustic": float(dist[caus].mean()),
            "flicker_control": float(dist[control].mean()),
            "caustic_pct": float(100 * caus.mean()),
        }
        print(f"[{name}] {n} frames  {a.shape[1]}x{a.shape[2]}")
        print(f"   flicker in the caustic region {dist[caus].mean():6.3f} levels")
        print(f"   flicker in the control region {dist[control].mean():6.3f} levels")
        print(f"   caustic covers {100*caus.mean():.1f}% of the frame")

    print()
    for a, b in (("ripple", "cycles_ripple"), ("combined", "cycles_combined")):
        if a in results and b in results:
            ra, rb = results[a], results[b]
            print(f"=== {a} vs {b} ===")
            print(f"   caustic flicker : ours {ra['flicker_caustic']:.3f}  "
                  f"Cycles {rb['flicker_caustic']:.3f}  "
                  f"-> {rb['flicker_caustic']/max(ra['flicker_caustic'],1e-9):.1f}x")
            print(f"   control flicker : ours {ra['flicker_control']:.3f}  "
                  f"Cycles {rb['flicker_control']:.3f}")
            print(f"   (the control is the check: if it is similar, the caustic "
                  f"difference is not the motion)")


if __name__ == "__main__":
    main()
