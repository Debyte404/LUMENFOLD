"""pbrt_comparison_figure.py — side-by-side figure: PBRT SPPM vs our solver.

PBRT's image must be mirrored in X first. Its LookAt computes the camera's right
axis as cross(up, direction), which for a top-down view with up = +y gives
(-1, 0, 0) - a left-handed frame - so the rendered image is mirrored relative to
a world-space top-down map. Skipping this step produced a spurious 122 deg
azimuth disagreement and r = +0.07; with it, r = +0.93.
"""
import sys

import numpy as np
from PIL import Image

ROOT = "D:/ValueProjects/caustics"
sys.path.insert(0, f"{ROOT}/third_party/luxvenv/Lib/site-packages")
import mitsuba as mi  # noqa: E402

mi.set_variant("scalar_spectral")


def exr(p):
    return np.array(mi.Bitmap(p)).astype(np.float32)


def norm(a, lo=1.0, hi=99.5):
    lo, hi = np.percentile(a, lo), np.percentile(a, hi)
    return np.clip((a - lo) / max(hi - lo, 1e-12), 0, 1)


def main():
    w = exr(f"{ROOT}/out/pbrt/pbrt_conv_optics.exr")
    o = exr(f"{ROOT}/out/pbrt/pbrt_conv_nooptics.exr")
    d = (w - o).mean(axis=2)
    H, W = d.shape

    f = np.array(Image.open(f"{ROOT}/out/caustic_wavy.png").convert("F").resize((W, H)))
    f = np.clip(f - np.median(f), 0, None)

    # the mirror correction, in one place, with the reason attached
    dl = d[:, ::-1]

    def to_rgb(a, tint):
        n = norm(a)
        rgb = np.zeros((H, W, 3), np.float32)
        rgb[..., 0] = n * tint[0]
        rgb[..., 1] = n * tint[1]
        rgb[..., 2] = n * tint[2]
        return (np.clip(rgb, 0, 1) ** 0.4545 * 255).astype(np.uint8)

    p_pbrt = to_rgb(np.clip(dl, 0, None), (1.0, 0.55, 0.25))
    p_ours = to_rgb(f, (0.35, 0.75, 1.0))
    both = np.zeros((H, W, 3), np.float32)
    both[..., 0] = norm(np.clip(dl, 0, None))
    both[..., 2] = norm(f)
    both = (np.clip(both, 0, 1) ** 0.4545 * 255).astype(np.uint8)

    strip = np.concatenate([p_pbrt, np.full((H, 6, 3), 60, np.uint8), p_ours,
                            np.full((H, 6, 3), 60, np.uint8), both], axis=1)
    out = f"{ROOT}/docs/pbrt_vs_ours.png"
    Image.fromarray(strip).save(out)
    print(f"wrote {out}  ({strip.shape[1]}x{strip.shape[0]})")
    print("  left: PBRT-v4 SPPM photon-mapping reference (X-corrected)")
    print("  mid : our wave-corrected solver")
    print("  right: overlay - orange = PBRT, blue = ours, white = both agree")


if __name__ == "__main__":
    main()
