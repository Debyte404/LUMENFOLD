"""Refine the rotating-source camera: smallest zoom that never crops.

The coarse sweep found zoom 1.60 keeps the caustic in frame for a full revolution while
1.30 and 1.00 crop it (2-4 of 8 sun positions). So 1.60 is safe but smaller than it
needs to be. Search the narrow band between them for the largest subject that still
survives the whole rotation.

A cropped frame is the failure that matters -- the animation appears to lose its subject
part-way round -- so "not cropped" is a hard constraint and area is maximised subject
to it.
"""
import itertools
import os
import sys

import numpy as np

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
from camera_sweep import render, score                   # noqa: E402
from colour_experiments import REF_AZ                    # noqa: E402

os.chdir(ROOT)
TMP = os.path.join("out", "cam_refine")
os.makedirs(TMP, exist_ok=True)

azs = (-75, -60, -45, -30)
els = (45, 55, 60, 65)
zooms = (1.30, 1.40, 1.50, 1.60, 1.70)
suns = [REF_AZ + 360.0 * k / 8 for k in range(8)]

total = len(azs) * len(els) * len(zooms) * len(suns)
print("  %d cameras x %d suns = %d renders" % (len(azs) * len(els) * len(zooms),
                                               len(suns), total))
print()
print("  %-6s %-5s %-6s %10s %7s %8s"
      % ("az", "el", "zoom", "worst-area", "cropped", "off-centre"))

rows = []
for az, el, z in itertools.product(azs, els, zooms):
    areas, crops, offs = [], 0, []
    for s in suns:
        p = os.path.join(TMP, "r_%d_%d_%03d_%d.png"
                         % (int(az), int(el), int(z * 100), int(s)))
        if not render(p, az, el, z, s, 600, 1280):
            continue
        ar, cr, off = score(p)
        areas.append(ar)
        crops += int(cr)
        offs.append(off)
    if not areas:
        continue
    rows.append((min(areas), crops, float(np.mean(offs)), az, el, z))
    print("  %-6d %-5d %-6.2f %10.4f %7d %8.3f%s"
          % (az, el, z, min(areas), crops, rows[-1][2],
             "" if crops == 0 else "  <- crops"))

clean = [r for r in rows if r[1] == 0]
print()
if clean:
    clean.sort(key=lambda r: r[0], reverse=True)
    b = clean[0]
    print("  largest safe subject: az=%d el=%d zoom=%.2f  worst-area %.4f  off-centre %.3f"
          % (b[3], b[4], b[5], b[0], b[2]))
    s = min(clean, key=lambda r: r[5])
    print("  smallest safe zoom  : az=%d el=%d zoom=%.2f  worst-area %.4f"
          % (s[3], s[4], s[5], s[0]))
else:
    print("  NOTHING clean in this band -- keep zoom 1.60")
