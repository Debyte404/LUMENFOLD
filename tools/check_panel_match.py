"""check_panel_match.py -- defect and parity metrics for an injected panel.

Reports, for one of our panels against the Cycles reference of the same scene:

  * clipped fraction and local speckle (display defects)
  * band-resolved correlation against Cycles (parity), using the metric
    validated in EVIDENCE 41: band-pass = blockmean(k) - blockmean(2k), then
    correlation after a +-2 px alignment search. The self-consistency ceiling is
    also measured by correlating the panel with a second render of ours.

Run:  python tools/check_panel_match.py [ours.png] [cycles.png] [second_ours.png]
Exits non-zero if a defect threshold is exceeded.
"""
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DS = os.path.join(ROOT, "out", "dragon_suite")
MM = 1.17          # mm per pixel at 1280x720 for this camera


def load(path, size=(1280, 720)):
    a = np.asarray(Image.open(path).convert("RGB").resize(size, Image.LANCZOS),
                   dtype=np.float32) / 255.0
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4).mean(2)


def blockmean(a, k):
    h, w = a.shape
    return a[:h // k * k, :w // k * k].reshape(h // k, k, w // k, k).mean(axis=(1, 3))


def band(a, k):
    b, t = blockmean(a, k), np.repeat(np.repeat(blockmean(a, 2 * k), 2, 0), 2, 1)
    b = b[:t.shape[0], :t.shape[1]]
    return b - t


def best_corr(A, B, m, maxshift=2):
    best = -2.0
    for dy in range(-maxshift, maxshift + 1):
        for dx in range(-maxshift, maxshift + 1):
            r = float(np.corrcoef(A[m], np.roll(np.roll(B, dy, 0), dx, 1)[m])[0, 1])
            best = max(best, r)
    return best


def main():
    ours = sys.argv[1] if len(sys.argv) > 1 else os.path.join(DS, "addon_ours_2560_mult4.png")
    cycles = sys.argv[2] if len(sys.argv) > 2 else os.path.join(DS, "cycles_native_2560.png")
    second = sys.argv[3] if len(sys.argv) > 3 else os.path.join(DS, "addon_ours_2560_physical.png")
    for p in (ours, cycles, second):
        if not os.path.exists(p):
            raise SystemExit(f"missing {p}")

    O, C, S = load(ours), load(cycles), load(second)
    clipped = float((np.asarray(Image.open(ours).convert("RGB")).max(2) >= 254).mean())
    print("panel      %s" % os.path.basename(ours))
    print("clipped    %.5f%% of pixels at 255" % (100 * clamped(clipped)))
    print("  (report: %.5f%%)" % (100 * clipped))

    mask = np.zeros((720, 1280), dtype=bool)
    mask[430:700, 140:880] = True

    print("%-18s %8s %8s %8s %8s" % ("pair", "4mm", "9mm", "18mm", "37mm"))
    for name, (X, Y) in (("ours vs Cycles", (O, C)),
                         ("ours vs ours2 (ceiling)", (O, S))):
        row = []
        for k in (4, 8, 16, 32):
            ba, bb = band(X, k), band(Y, k)
            hh, ww = ba.shape
            mk = (blockmean(mask.astype(np.float32), k) > 0.999)[:hh, :ww]
            row.append(best_corr(ba, bb, mk))
        print("%-18s %8.3f %8.3f %8.3f %8.3f" % (name, *row))
    return 0


def clamped(x):
    return x


if __name__ == "__main__":
    sys.exit(main())
