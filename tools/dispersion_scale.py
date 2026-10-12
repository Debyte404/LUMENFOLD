"""dispersion_scale.py — how large must the Airy band be for dispersion to be VISIBLE?

Finding that motivated this: at airy_scale=0.02 the wave field's per-channel
spread is mean 0.0014 / max 0.057 against a field mean of 1.0 - about 0.1%
colour, i.e. invisible after tonemapping. w scales only as lambda^(2/3), so the
R and B bands differ in width by ~12%; the visible colour difference therefore
comes from how much of the Airy profile the band covers, which grows with w.

Sweeps airy_scale at the real-time grid (1024^2, fringe width must stay >= ~3 px
= 17.6 mm there) and reports:
  spread_mean / spread_max : per-channel deviation from the field mean
  frac > 5%                : pixels whose R-B difference exceeds 5% of the mean
  fringes                  : Airy peaks crossing a mid-row (resolved structure)
"""
import sys

import numpy as np


# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

sys.path.insert(0, _ROOT + "/tools")
import fold_diag as fd  # noqa: E402

N, T = 1024, 1.7
MIN_W_PX = 3.0
px = fd.SIZE / N

g, Hx, Hy = fd.geom_field(T, N)
det = fd.jacobian_det(Hx, Hy, N)
fold = np.abs(det) < np.percentile(np.abs(det), 2.0)

print(f"grid {N}^2  pixel {px*1000:.2f} mm  (band needs >= {MIN_W_PX} px "
      f"-> airy_scale >= {MIN_W_PX*px:.4f} m)")
print()
hdr = f"{'scale':>7} {'w_px':>6} {'spread_mean':>12} {'spread_max':>11} {'frac>5%':>9} {'fringes':>8}"
print(hdr)
print("-" * len(hdr))

for scale in (0.02, 0.04, 0.08, 0.16, 0.32):
    rgb = fd.correct_bandlocal(g, scale, fold)
    mid = rgb[..., 1]
    dev = np.abs(rgb - mid[..., None])                    # per-channel deviation
    rb = np.abs(rgb[..., 0] - rgb[..., 2])
    frac = float((rb > 0.05 * mid.mean()).mean())
    # count resolved Airy peaks across a mid-row of the fold-heavy region
    row = mid[N // 2]
    pk = int(np.sum((row[1:-1] > row[:-2]) & (row[1:-1] > row[2:]) & (row[1:-1] > 2.0)))
    print(f"{scale:>7.3f} {scale/px:>6.1f} {dev.mean():>12.4f} {dev.max():>11.4f} "
          f"{frac*100:>8.2f}% {pk:>8d}")

print()
print("read: spread_mean is the average per-channel colour deviation (field mean")
print("is 1.0, so 0.05 = 5% colour). frac>5% counts pixels with visible R-B split.")
print(f"scales below {MIN_W_PX*px:.3f} m are under-resolved at this grid.")
