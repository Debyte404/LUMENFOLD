"""camera_sweep.py -- choose the rotating-source camera by measurement.

The orbit has a FIXED camera and a rotating sun, so the caustic travels right round the
glass and the WORST sun position is the one that matters: a camera that looks fine at
0 deg but puts the caustic behind the glass at 180 deg gives an animation that appears
to break halfway through.

Metric design, calibrated against real frames rather than guessed. The table surface
sits around L = 124-144 and the caustic at L = 200-243, so there is a clean gap: the
caustic is isolated at med + 0.6*(P99.9 - med). An earlier version used med + 0.55 of
the MAX and flagged every camera as cropped, because the mask was picking up table.

Score = worst-case caustic AREA over a full sun revolution, penalised when the caustic
runs off the frame, because a rotation that loses the subject is worse than one that
shows it smaller. `zoom` scales the camera distance, so framing is searched too.

Usage:  python tools/camera_sweep.py [--quick]
"""
import argparse
import itertools
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "build", "src", "app", "Release", "showcase.exe")
TMP = os.path.join(ROOT, "out", "cam_sweep")
sys.path.insert(0, os.path.join(ROOT, "tools"))
from colour_experiments import REF_AZ, REF_CENTROID, REF_EXTENT     # noqa: E402

SUN_EL = 25.449840953628105


def render(path, az, el, zoom, sun_az, n, res):
    cmd = [EXE, "--n", str(n), "--res", str(res), "--out", path,
           "--sun-az", "%.4f" % sun_az, "--sun-el", "%.4f" % SUN_EL,
           "--cam-fixed", "%.6f" % REF_CENTROID[0], "%.6f" % REF_CENTROID[1],
           "%.6f" % REF_EXTENT,
           "--eye-az", "%.2f" % az, "--eye-el", "%.2f" % el,
           "--eye-zoom", "%.3f" % zoom]
    os.system(" ".join(cmd) + " > NUL 2>&1")
    return os.path.exists(path)


def score(path):
    """Caustic area fraction, cropped?, and how centred it is."""
    a = np.asarray(Image.open(path).convert("L"), dtype=float)
    med = np.median(a)
    hi = np.percentile(a, 99.9)
    if hi <= med:
        return 0.0, True, 1.0
    m = a > med + 0.6 * (hi - med)
    area = float(m.mean())
    b = 3
    cropped = bool(m[:b, :].any() or m[-b:, :].any()
                   or m[:, :b].any() or m[:, -b:].any())
    ys, xs = np.nonzero(m)
    if len(xs) == 0:
        return 0.0, cropped, 1.0
    h, w = a.shape
    off = (abs(xs.mean() - w / 2) / w + abs(ys.mean() - h / 2) / h) / 2.0
    return area, cropped, float(off)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()

    if a.quick:
        n, res = 520, 1024
        azs = (-150, -120, -90, -60)
        els = (30, 45)
        zooms = (1.0,)
    else:
        n, res = 600, 1280
        azs = (-165, -135, -105, -75, -45)
        els = (30, 40, 50, 60)
        zooms = (1.0, 1.3, 1.6)
    suns = [REF_AZ + 360.0 * k / 8 for k in range(8)]

    os.makedirs(TMP, exist_ok=True)
    print("  %d cameras x %d sun positions = %d renders"
          % (len(azs) * len(els) * len(zooms), len(suns),
             len(azs) * len(els) * len(zooms) * len(suns)))
    print()
    print("  %-6s %-5s %-6s %10s %10s %7s %8s"
          % ("az", "el", "zoom", "worst-area", "mean-area", "cropped", "off-centre"))

    rows = []
    for az, el, z in itertools.product(azs, els, zooms):
        areas, crops, offs = [], 0, []
        for s in suns:
            p = os.path.join(TMP, "c_%d_%d_%03d_%d.png"
                             % (int(az), int(el), int(z * 100), int(s)))
            if not render(p, az, el, z, s, n, res):
                areas.append(0.0)
                continue
            ar, cr, off = score(p)
            areas.append(ar)
            crops += int(cr)
            offs.append(off)
        rows.append((min(areas), float(np.mean(areas)), crops,
                     float(np.mean(offs)) if offs else 1.0, az, el, z))

    # prefer nothing cropped, then the largest worst-case caustic
    rows.sort(key=lambda r: (r[2] == 0, r[0]), reverse=True)
    for worst, mean, crops, off, az, el, z in rows[:14]:
        note = "" if crops == 0 else "%d cropped" % crops
        print("  %-6d %-5d %-6.2f %10.4f %10.4f %7d %8.3f  %s"
              % (az, el, z, worst, mean, crops, off, note))

    b = rows[0]
    print()
    print("  BEST: az=%d el=%d zoom=%.2f  worst-area %.4f  cropped %d  off-centre %.3f"
          % (b[4], b[5], b[6], b[0], b[2], b[3]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
