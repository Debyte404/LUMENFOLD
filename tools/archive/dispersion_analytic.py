"""dispersion_analytic.py - bisect the dispersion sign fault.

The solver's --flat path is exactly a single-refraction cylinder (air -> medium
at radius R), which tools/analytic_caustic.py reproduces independently and which
verified to 0.1 mm on a 320 mm patch.

Second, and the comparison that matters: the statistic must MATCH the reference.
SPPM's caustic centroid tracks the caustic RIDGE, not the mean over all rays -
those two respond to index with opposite signs, because the mean includes the
wide unconverged tails. So measure the ridge: the FOLD locus, where |d hit/dphi|
vanishes, which is the same feature analytic_caustic.py already located at
(+76.4, +40.1) mm with phi = 207.70 deg.
"""
import sys
import numpy as np
sys.path.insert(0, "D:/ValueProjects/caustics/tools")
from analytic_caustic import hit

M = 200000
dphi = 2.0 * np.pi / M
print("  n        mean r (all rays)     fold r (ridge)    fold phi")
for n in (1.30, 1.33, 1.35, 1.40, 1.45):
    rs, js, phis = [], [], []
    prev = None
    for i in range(M):
        phi = (i + 0.5) * dphi
        h = hit(phi, n)
        if h is None:
            prev = None
            continue
        rs.append(float(np.hypot(h[0], h[1])))
        if prev is not None:
            js.append(float(np.hypot(h[0] - prev[0], h[1] - prev[1])) / dphi)
            phis.append(phi)
        prev = h
    js = np.array(js); phis = np.array(phis)
    i = int(np.argmin(js))
    rf = 1000 * rs[i + 1] if i + 1 < len(rs) else float("nan")
    print(f"  {n:.3f}   {1000*np.mean(rs):9.3f} mm      {rf:9.3f} mm     "
          f"{np.degrees(phis[i]):8.2f} deg")
