"""dispersion_pbrt.py - does our dispersion match converged photon mapping?

Index dispersion is the one thing a converged reference settles that a path
tracer cannot: Mitsuba needed monochromatic 16 nm bands and could still only
resolve the ORDER of red vs blue, never the magnitude. SPPM converges the
caustic fast enough to place it (EVIDENCE 19).

Method
  Three SPPM renders of the identical scene, differing ONLY in the index pair
  (water, glass) - one per spectral channel, using the measured data that
  showcase_main.cpp now evaluates. Each render is white light, so the channels
  within one image are identical and the dispersion lives BETWEEN renders.
  A fourth render with --hide-optics is the baseline.

  The lit table dominates the raw images (mean 0.86 almost uniformly), so the
  caustic is isolated as caustic = render - baseline, exactly as for the
  structure comparison in EVIDENCE 19. Scoring a raw render measures the
  ambient, not the caustic - that mistake produced a meaningless 7.31 mm
  centroid on the first attempt.

Metric, identical on both sides (photon map and our field)
  intensity-weighted centroid of the positive part inside r > R0 (the fan,
  clear of the bright zone at the glass base), reported as radius and azimuth
  in mm/degrees from the glass axis. An intensity centroid, not a peak: the
  peak of a caustic is a singularity and is not a stable position estimator.

  Images are mirrored in X before scoring: PBRT's LookAt builds the camera right
  axis as cross(up, direction) = (-1, 0, 0), a left-handed frame (EVIDENCE 19).

Run:  <luxvenv>/Scripts/python tools/dispersion_pbrt.py
"""
import numpy as np

OUT = "D:/ValueProjects/caustics/out/pbrt"
HALF = 160.0          # ortho camera frames a 0.32 m patch: +-160 mm
R0 = 25.0             # fan region

BANDS = [(650, "measured", 1.33167, 1.52104),
         (550, "measured", 1.33468, 1.52514),
         (450, "measured", 1.33961, 1.53192)]


def load(path):
    """EXR via Mitsuba's bitmap reader - no extra dependency."""
    import mitsuba as mi
    a = np.array(mi.Bitmap(path)).astype(np.float64)
    return a[:, ::-1, :]            # undo PBRT's X mirror


def grid(img):
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    X = (xx / (w - 1) - 0.5) * 2 * HALF
    Y = (0.5 - yy / (h - 1)) * 2 * HALF
    return X, Y, np.hypot(X, Y)


def edge_radius(img, X, Y, rad, frac=0.02, nb=160):
    """Outermost radius whose mean intensity exceeds frac of the image max.

    The feature comparable across renderers: relative threshold, so it is
    invariant to any uniform scale; the outer edge is unaffected by a ceiling on
    the core. Same definition as the solver's "edge" metric.
    """
    lum = np.maximum(img.mean(axis=2), 0.0)
    mx = lum.max()
    b = np.clip((rad / HALF * nb).astype(int), 0, nb - 1)
    prof = np.bincount(b.ravel(), weights=lum.ravel(), minlength=nb)
    cnt = np.bincount(b.ravel(), minlength=nb)
    mean = np.where(cnt > 0, prof / np.maximum(cnt, 1), 0.0)
    idx = np.nonzero(mean > frac * mx)[0]
    return float((idx.max() + 1) / nb * HALF) if idx.size else float("nan")


def centroid(img, X, Y, rad):
    """Intensity centroid of the positive part in r > R0."""
    lum = np.maximum(img.mean(axis=2) - 0.0, 0.0)
    m = (rad > R0) & (lum > 0)
    wsum = lum[m].sum()
    if wsum <= 0:
        return float("nan"), float("nan"), 0.0
    cx = (X[m] * lum[m]).sum() / wsum
    cy = (Y[m] * lum[m]).sum() / wsum
    return cx, cy, float(np.hypot(cx, cy))


def main():
    base = load(f"{OUT}/disp_base.exr")
    X, Y, rad = grid(base)
    print(f"  baseline: mean {base.mean():.6f} (uniform table lighting)")
    print()
    got = {}
    for lam, kind, nw, ng in BANDS:
        img = load(f"{OUT}/disp_{lam}.exr")
        c = img - base                        # isolate the caustic
        cx, cy, r = centroid(c, X, Y, rad)
        az = np.degrees(np.arctan2(cy, cx))
        peak = (img - base).max()
        e = edge_radius(c, X, Y, rad)
        got[lam] = (r, az, peak, e)
        print(f"  {lam} nm  (water {nw}, glass {ng})  "
              f"caustic centroid  r {r:6.2f} mm  azimuth {az:+7.2f} deg  "
              f"peak {peak:6.3f}")
    rR, azR, _, eR = got[650]
    rG, azG, _, eG = got[550]
    rB, azB, _, eB = got[450]
    print()
    print(f"  SPPM reference  R(650) r {rR:.2f} mm   B(450) r {rB:.2f} mm")
    print(f"  R - B radius    = {rR - rB:+.2f} mm   ({100 * (rR - rB) / rB:+.3f}% of B)")
    print(f"  R - G radius    = {rR - rG:+.2f} mm   ({100 * (rR - rG) / rG:+.3f}% of G)")
    print(f"  azimuth R {azR:+.2f}  G {azG:+.2f}  B {azB:+.2f} deg   "
          f"(spread {max(azR, azG, azB) - min(azR, azG, azB):.2f} deg)")
    print(f"  caustic EDGE radius   R {eR:.1f}  G {eG:.1f}  B {eB:.1f} mm"
          f"   -> R-B {eR - eB:+.1f} mm")
    print()
    print("  red farther from the axis than blue?",
          "YES" if rR > rB else "NO")


if __name__ == "__main__":
    main()
