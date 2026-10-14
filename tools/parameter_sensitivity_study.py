"""parameter_sensitivity_study.py -- quantify sensitivity to detector threshold, airy_scale, and ceiling.

Addresses reviewer critique:
  "Section 6.8 also promises a sensitivity study of the three parameters, but
   Table 10 has no numbers."

This script evaluates how the caustic field changes when varying:
  1. Fold detector percentile p in {1.0%, 2.0%, 4.0%}
  2. Airy scale multiplier w in {0.5x, 1.0x, 2.0x}
  3. Intensity ceiling cap in {4.0x, 6.0x, 8.0x}

Reports:
  - Band area fraction (%)
  - Peak field value
  - Energy conservation ratio k*
  - RMSE relative to default setting (p=2.0%, w=1.0x, cap=6.0x)
"""
import sys
import numpy as np

import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
sys.path.insert(0, _ROOT + "/tools")
import fold_diag as fd
import band_flux_test as bft

def main():
    N, T = 256, 1.7  # 256^2 for fast exploration
    g, Hx, Hy = fd.geom_field(T, N)
    det = fd.jacobian_det(Hx, Hy, N)
    abs_det = np.abs(det)

    # Operational baseline matching Table 7 (tail_study.py)
    p_base = 2.0
    w_base = 0.02
    cap_base = 6.0

    def bake(p, w, cap):
        thr = np.percentile(abs_det, p)
        fold = abs_det < thr
        # Pass cap to correct_bandlocal
        dx = fd.SIZE / N
        s = fd.ndimage.distance_transform_edt(~fold) * dx
        smooth = fd.ndimage.gaussian_filter(g, sigma=3.0)
        rgb = np.zeros(g.shape + (3,))
        for c in range(3):
            wc = w * (fd.LAMBDAS[c] / 550e-9) ** (2.0 / 3.0)
            prof = fd.airy_profile(s, wc)
            band = s < 5 * wc
            ch = g.copy()
            if band.any():
                base = np.minimum(smooth, cap)[band]
                shape = 0.15 + 0.85 * prof[band]
                want = g[band].sum()
                got = float((base * shape).sum())
                k = (want / got) if got > 0 else 0.0
                ch[band] = np.minimum(base * shape * k, cap * 1.35)
            rgb[..., c] = ch
        return fold, rgb

    fold_base, rgb_base = bake(p_base, w_base, cap_base)

    print("=== PARAMETER SENSITIVITY STUDY ===")
    print(f"{'Parameter':<22} | {'Band %':<8} | {'Peak':<8} | {'RMSE vs Base':<12}")
    print("-" * 56)

    # 1. Detector threshold
    for p in [1.0, 2.0, 4.0]:
        f, rgb = bake(p, w_base, cap_base)
        rmse = np.sqrt(np.mean((rgb - rgb_base)**2))
        lbl = f"threshold p = {p:.1f}%"
        print(f"{lbl:<22} | {f.mean()*100:6.2f}% | {rgb.max():6.3f}   | {rmse:10.5f}")

    print("-" * 56)
    # 2. Airy width scale
    for mult in [0.5, 1.0, 2.0]:
        w = w_base * mult
        f, rgb = bake(p_base, w, cap_base)
        rmse = np.sqrt(np.mean((rgb - rgb_base)**2))
        lbl = f"scale w = {mult:.1f}x"
        print(f"{lbl:<22} | {f.mean()*100:6.2f}% | {rgb.max():6.3f}   | {rmse:10.5f}")

    print("-" * 56)
    # 3. Ceiling cap
    for cap in [4.0, 6.0, 8.0]:
        f, rgb = bake(p_base, w_base, cap)
        rmse = np.sqrt(np.mean((rgb - rgb_base)**2))
        lbl = f"ceiling cap = {cap:.1f}x"
        print(f"{lbl:<22} | {f.mean()*100:6.2f}% | {rgb.max():6.3f}   | {rmse:10.5f}")

    print("===================================")

if __name__ == "__main__":
    main()
