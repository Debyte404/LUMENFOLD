"""fold_diag.py — is the Airy fold treatment resolution-stable?

Suspicion raised by efficiency_study: at 256^2 our wave-corrected field sits
FURTHER from a converged wave reference (0.135) than the raw geometric field
does (0.074). If the fold band were handled correctly, refining the grid should
converge our field toward the reference. Here we sweep resolution and also
compare the two candidate fold detectors:

  percentile : fold = geom > 98th percentile      (what the C++ currently does)
  detj       : fold = |det J| < eps of the surface->floor ray map, the actual
               mathematical caustic locus (zero area element), threshold-free.

Metrics are reported against a high-resolution truth of the SAME model, so a
correct implementation must improve monotonically with resolution.
"""
import numpy as np
from scipy import ndimage
from scipy.special import airy

SIZE, DEPTH = 6.0, 1.0
ETA = 1.0 / 1.333
LAMBDAS = np.array([650e-9, 550e-9, 450e-9])
WAVES = [(0.035, 1.40, 1.0, 0.2, 0.9), (0.022, 0.70, 0.3, 1.0, 1.3),
         (0.014, 0.35, -0.6, 0.8, 1.7), (0.008, 0.18, 0.8, -0.6, 2.2)]
SUN = np.array([-0.35, -0.25, -1.0]); SUN = SUN / np.linalg.norm(SUN)
T = 1.7


def surface(t, n):
    ax = np.linspace(-SIZE / 2, SIZE / 2, n)
    X, Y = np.meshgrid(ax, ax)
    h = np.zeros_like(X); gx = np.zeros_like(X); gy = np.zeros_like(X)
    for amp, lam, dx, dy, sp in WAVES:
        nn = np.hypot(dx, dy); dx, dy = dx / nn, dy / nn
        k = 2 * np.pi / lam
        ph = k * (dx * X + dy * Y) - sp * k * t
        h += amp * np.sin(ph)
        c = amp * k * np.cos(ph)
        gx += c * dx; gy += c * dy
    return X, Y, h, gx, gy


def ray_map(t, n):
    """Surface -> floor plane mapping (Hx, Hy) plus Jacobian determinant."""
    X, Y, h, gx, gy = surface(t, n)
    inv = 1 / np.sqrt(1 + gx * gx + gy * gy)
    Nrm = np.stack([-gx * inv, -gy * inv, inv], axis=-1)
    cosi = np.clip(-(SUN[0] * Nrm[..., 0] + SUN[1] * Nrm[..., 1] + SUN[2] * Nrm[..., 2]), -1, 1)
    sin2t = ETA * ETA * (1 - cosi * cosi)
    cost = np.sqrt(np.clip(1 - sin2t, 0, 1))
    R = np.empty_like(Nrm)
    for c in range(3):
        R[..., c] = ETA * SUN[c] + (ETA * cosi - cost) * Nrm[..., c]
    nrm = np.linalg.norm(R, axis=-1, keepdims=True)
    R = R / np.maximum(nrm, 1e-12)
    s = (-DEPTH - h) / R[..., 2]
    return X + R[..., 0] * s, Y + R[..., 1] * s


def jacobian_det(Hx, Hy, n):
    d = SIZE / (n - 1)
    dHx_dx = np.gradient(Hx, d, axis=1)
    dHx_dy = np.gradient(Hx, d, axis=0)
    dHy_dx = np.gradient(Hy, d, axis=1)
    dHy_dy = np.gradient(Hy, d, axis=0)
    return dHx_dx * dHy_dy - dHx_dy * dHy_dx


def splat(Hx, Hy, n):
    px = (Hx + SIZE / 2) / SIZE * n - 0.5
    py = (Hy + SIZE / 2) / SIZE * n - 0.5
    ok = np.isfinite(px) & np.isfinite(py)
    px, py = px[ok], py[ok]
    x0 = np.floor(px).astype(np.int64); y0 = np.floor(py).astype(np.int64)
    fx = px - x0; fy = py - y0
    n2 = n * n

    def acc(ix, iy, w):
        m = (ix >= 0) & (ix < n) & (iy >= 0) & (iy < n)
        return np.bincount(iy[m] * n + ix[m], weights=w[m], minlength=n2).reshape(n, n)

    return (acc(x0, y0, (1 - fx) * (1 - fy)) + acc(x0 + 1, y0, fx * (1 - fy))
            + acc(x0, y0 + 1, (1 - fx) * fy) + acc(x0 + 1, y0 + 1, fx * fy))


def geom_field(t, n):
    Hx, Hy = ray_map(t, n)
    f = splat(Hx, Hy, n)
    return f / (f.mean() + 1e-12), Hx, Hy


def airy_profile(s, w):
    u = np.clip(s / w, 0, 8)
    ai = np.abs(airy(-u)[0]) ** 2
    return ai / ai.max()


def correct_bandlocal(geom, airy_scale, fold):
    """CANONICAL correction: band -> Airy profile, band-local flux conservation.

    The Airy profile redistributes the band's OWN energy, so no global rescale is
    needed and the intensity ceiling holds. Matches src/render/caustic.cpp.
    """
    dx = SIZE / geom.shape[0]
    s = ndimage.distance_transform_edt(~fold) * dx
    smooth = ndimage.gaussian_filter(geom, sigma=3.0)
    cap = 6.0
    rgb = np.zeros(geom.shape + (3,))
    for c in range(3):
        w = airy_scale * (LAMBDAS[c] / 550e-9) ** (2.0 / 3.0)
        prof = airy_profile(s, w)
        band = s < 5 * w
        ch = geom.copy()
        if band.any():
            base = np.minimum(smooth, cap)[band]
            shape = 0.15 + 0.85 * prof[band]
            want = geom[band].sum()
            got = float((base * shape).sum())
            k = (want / got) if got > 0 else 0.0
            ch[band] = np.minimum(base * shape * k, cap * 1.35)
        rgb[..., c] = ch
    return rgb


def correct_global(geom, airy_scale, fold):
    """Superseded: global rescale applied after the clamp (breaks the ceiling)."""
    return wave_correct(geom, airy_scale, fold)


def wave_correct(geom, airy_scale, fold):
    dx = SIZE / geom.shape[0]
    s = ndimage.distance_transform_edt(~fold) * dx
    smooth = ndimage.gaussian_filter(geom, sigma=3.0)
    cap = 6.0
    rgb = np.zeros(geom.shape + (3,))
    for c in range(3):
        w = airy_scale * (LAMBDAS[c] / 550e-9) ** (2.0 / 3.0)
        prof = airy_profile(s, w)
        band = s < 5 * w
        ch = geom.copy()
        ch[band] = np.minimum(smooth, cap)[band] * (0.15 + 0.85 * prof[band])
        rgb[..., c] = np.minimum(ch, cap * 1.35)
    target = geom.sum()
    for c in range(3):
        rgb[..., c] *= target / (rgb[..., c].sum() + 1e-12)
    return rgb


def display(x):
    return np.clip(np.clip(x, 0, 8) / 8.0, 0, 1) ** (1 / 2.2)


def rmse(a, b):
    return float(np.sqrt(np.mean((display(a) - display(b)) ** 2)))


def blocks(a, k):
    n = a.shape[0] // k
    if a.ndim == 2:
        return a[:n * k, :n * k].reshape(n, k, n, k).mean(axis=(1, 3))
    return a[:n * k, :n * k].reshape(n, k, n, k, a.shape[2]).mean(axis=(1, 3))


def to_n(a, n):
    """Resample field a (square, maybe RGB) to n x n by block mean or nearest upsample."""
    cur = a.shape[0]
    if cur == n:
        return a
    if cur % n == 0:
        return blocks(a, cur // n)
    k = int(round(n / cur))
    return np.kron(a, np.ones((k, k) + (() if a.ndim == 2 else (1,)))) / (k * k if a.ndim == 3 else 1)


N_TRUTH = 2048
N_REF = 256
if __name__ == "__main__":
    print(f"truth: {N_TRUTH}^2, compared at {N_REF}^2\n")
    truth_geom, _, _ = geom_field(T, N_TRUTH)
    _, HxT, HyT = geom_field(T, N_TRUTH)
    detT = jacobian_det(HxT, HyT, N_TRUTH)
    scale = np.percentile(np.abs(detT), 2.0)
    truth_fold = np.abs(detT) < scale
    truth_wave = correct_bandlocal(truth_geom, 0.02, truth_fold)
    ref_wave = to_n(truth_wave, N_REF)
    ref_geom = to_n(truth_geom, N_REF)
    print(f"truth fold pixels (detJ): {truth_fold.mean()*100:.2f}% of grid")

    print(f"\n{'n':>6} {'fold%':>7} {'wave RMSE vs truth':>19} {'geom RMSE':>10}")
    for n in (128, 256, 512, 1024):
        g, Hx, Hy = geom_field(T, n)
        det = jacobian_det(Hx, Hy, n)
        thr = np.percentile(np.abs(det), 2.0)
        fold = np.abs(det) < thr
        wv = correct_bandlocal(g, 0.02, fold)
        wv_r = to_n(wv, N_REF)
        g_r = to_n(g, N_REF)
        print(f"{n:>6} {fold.mean()*100:>6.2f}% {rmse(wv_r[...,1], ref_wave[...,1]):>19.5f} "
              f"{rmse(g_r, ref_geom):>10.5f}")

    # percentile detector for comparison
    print(f"\npercentile-detector variant (what the C++ does today):")
    for n in (128, 256, 512, 1024):
        g, Hx, Hy = geom_field(T, n)
        fold = g > np.percentile(g, 98)
        wv = correct_bandlocal(g, 0.02, fold)
        wv_r = to_n(wv, N_REF)
        print(f"{n:>6} {fold.mean()*100:>6.2f}% {rmse(wv_r[...,1], ref_wave[...,1]):>19.5f}")
