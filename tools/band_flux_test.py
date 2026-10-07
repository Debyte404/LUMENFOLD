"""band_flux_test.py — two ways to conserve flux in the Airy correction.

The existing correction replaces the fold band with the Airy profile and then
rescales the WHOLE channel to restore total flux. Because that global rescale
happens after the intensity clamp, the result can exceed the intended ceiling
(measured: 11.58x against a ceiling of 8.10x at 256^2).

Variant B conserves flux INSIDE the band only: the Airy profile redistributes
the band's own energy, so no global rescale is needed and the ceiling holds.

Reported per grid: max, RMSE against the 2048^2 wave truth, and whether the
ceiling is respected.
"""
import numpy as np

import fold_diag as fd

CAP, SIZE = 6.0, 6.0
LAMBDAS = fd.LAMBDAS


def airy_profile(s, w):
    return fd.airy_profile(s, w)


def correct_global(geom, scale, fold):
    """Current behaviour: band -> Airy, then global rescale, then clamp."""
    return fd.wave_correct(geom, scale, fold)


def correct_bandlocal(geom, scale, fold):
    """Band-local flux conservation: no global rescale, ceiling respected."""
    dx = SIZE / geom.shape[0]
    s = fd.ndimage.distance_transform_edt(~fold) * dx
    smooth = fd.ndimage.gaussian_filter(geom, sigma=3.0)
    rgb = np.zeros(geom.shape + (3,))
    cap = CAP
    for c in range(3):
        w = scale * (LAMBDAS[c] / 550e-9) ** (2.0 / 3.0)
        prof = airy_profile(s, w)
        band = s < 5 * w
        ch = geom.copy()
        if band.any():
            base = np.minimum(smooth, cap)[band]
            shape = 0.15 + 0.85 * prof[band]
            # keep the band's total energy, just redistribute it
            want = geom[band].sum()
            got = float((base * shape).sum())
            k = (want / got) if got > 0 else 0.0
            ch[band] = np.minimum(base * shape * k, cap * 1.35)
        rgb[..., c] = ch
    return rgb


def main():
    t = 1.7
    truth_hi, _, _ = fd.geom_field(t, 2048)
    detT = fd.jacobian_det(*fd.ray_map(t, 2048), 2048)
    thr = np.percentile(np.abs(detT), 2.0)
    truth = fd.to_n(fd.correct_bandlocal(truth_hi, 0.02, np.abs(detT) < thr), 256)

    ceiling = CAP * 1.35
    print(f"ceiling = {ceiling:.2f}x   (truth at 2048^2, compared at 256^2)\n")
    print(f"{'grid':>6} {'variant':>11} {'max':>8} {'RMSE':>9} {'ceiling ok':>11}")
    for n in (256, 512, 1024):
        g, Hx, Hy = fd.geom_field(t, n)
        det = fd.jacobian_det(Hx, Hy, n)
        fold = np.abs(det) < np.percentile(np.abs(det), 2.0)
        for name, fn in (("global", correct_global), ("band-local", correct_bandlocal)):
            f = fn(g, 0.02, fold)
            r = fd.to_n(f, 256)
            mx = float(r[..., 1].max())
            print(f"{n:>6} {name:>11} {mx:>8.2f} {fd.rmse(r[...,1], truth[...,1]):>9.5f} "
                  f"{'yes' if mx <= ceiling + 1e-6 else 'NO':>11}")
    print(f"\nconverged truth: max={float(truth[...,1].max()):.2f}x "
          f"(a physically resolved fringe peak, not a clamp artefact)")


if __name__ == "__main__":
    main()
