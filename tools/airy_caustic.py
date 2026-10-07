"""airy_caustic.py — analytic pool caustics with wave-corrected Airy fringes.
Method (documented, honest approximations flagged):
 1. Water surface = sum of 4 directional sine waves over a 6x6 m patch.
 2. Sun rays refract through the surface (vector Snell, air->water n=1.333),
    hit the pool floor at z=-1; flux splatted to a floor grid = GEOMETRIC field.
    Where the mapping folds (det J -> 0) this spikes toward "infinity".
 3. WAVE field: fold ridges detected (top percentile), distance-to-fold via
    EDT, intensity replaced in a band around folds by the fold-caustic profile
    I ~ |Ai(-s/w)|^2 (Airy, Berry & Upstill 1980), per-channel wavelength
    scaling w ~ lambda^{2/3} -> real chromatic fringes. Flux renormalized so
    total energy is conserved (wave correction redistributes, never invents).
HONEST SCALE NOTE: physical fringe width at pool scale is sub-mm (invisible).
 w0 default 0.02 m exaggerates for visibility; --airy-scale sets it. The C++
 port keeps the same parameter.
Outputs: docs/caustic_compare.png, docs/caustic_wave.npy (+ stats to stdout).
"""
import argparse
import numpy as np
from scipy import ndimage
from scipy.special import airy

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAVE_MPL = True
except ImportError:
    HAVE_MPL = False

N = 512          # grid resolution
SIZE = 6.0       # water patch, meters
DEPTH = 1.0      # floor depth below surface
ETA = 1.0 / 1.333  # air -> water
LAMBDAS = np.array([650e-9, 550e-9, 450e-9])  # R, G, B

WAVES = [  # (amp m, wavelength m, dirx, diry, speed m/s)
    (0.035, 1.40, 1.0, 0.2, 0.9),
    (0.022, 0.70, 0.3, 1.0, 1.3),
    (0.014, 0.35, -0.6, 0.8, 1.7),
    (0.008, 0.18, 0.8, -0.6, 2.2),
]


def surface(t):
    ax = np.linspace(-SIZE / 2, SIZE / 2, N)
    X, Y = np.meshgrid(ax, ax)
    h = np.zeros_like(X)
    gx = np.zeros_like(X)
    gy = np.zeros_like(X)
    for amp, lam, dx, dy, sp in WAVES:
        n = np.hypot(dx, dy)
        dx, dy = dx / n, dy / n
        k = 2 * np.pi / lam
        ph = k * (dx * X + dy * Y) - sp * k * t
        h += amp * np.sin(ph)
        c = amp * k * np.cos(ph)
        gx += c * dx
        gy += c * dy
    return h, gx, gy


def refract(I, Nrm, eta):
    # vector Snell; I,Nrm unit, Nrm up (+z). Returns refracted dirs (air->water).
    cosi = -(I[0] * Nrm[..., 0] + I[1] * Nrm[..., 1] + I[2] * Nrm[..., 2])
    cosi = np.clip(cosi, -1, 1)
    sin2t = eta * eta * (1 - cosi * cosi)
    valid = sin2t <= 1.0
    cost = np.sqrt(np.clip(1 - sin2t, 0, 1))
    R = np.empty_like(Nrm)
    for c in range(3):
        R[..., c] = eta * I[c] + (eta * cosi - cost) * Nrm[..., c]
    R[~valid] = np.nan
    n = np.linalg.norm(R, axis=-1, keepdims=True)
    return R / np.maximum(n, 1e-12)


def bake(t):
    h, gx, gy = surface(t)
    inv = 1 / np.sqrt(1 + gx * gx + gy * gy)
    Nrm = np.stack([-gx * inv, -gy * inv, inv], axis=-1)
    ax = np.linspace(-SIZE / 2, SIZE / 2, N)
    X, Y = np.meshgrid(ax, ax)
    sun = np.array([-0.35, -0.25, -1.0])
    sun /= np.linalg.norm(sun)
    R = refract(sun, Nrm, ETA)
    s = (-DEPTH - h) / R[..., 2]  # floor z=-DEPTH
    Hx = X + R[..., 0] * s
    Hy = Y + R[..., 1] * s
    # splat to floor grid (same extent), bilinear
    px = (Hx + SIZE / 2) / SIZE * N - 0.5
    py = (Hy + SIZE / 2) / SIZE * N - 0.5
    ok = np.isfinite(px) & np.isfinite(py)
    x0 = np.floor(px[ok]).astype(int)
    y0 = np.floor(py[ok]).astype(int)
    fx = px[ok] - x0
    fy = py[ok] - y0
    flux = np.zeros((N, N))
    np.add.at(flux, (np.clip(y0, 0, N - 1), np.clip(x0, 0, N - 1)), (1 - fx) * (1 - fy))
    np.add.at(flux, (np.clip(y0, 0, N - 1), np.clip(x0 + 1, 0, N - 1)), fx * (1 - fy))
    np.add.at(flux, (np.clip(y0 + 1, 0, N - 1), np.clip(x0, 0, N - 1)), (1 - fx) * fy)
    np.add.at(flux, (np.clip(y0 + 1, 0, N - 1), np.clip(x0 + 1, 0, N - 1)), fx * fy)
    geom = flux / (flux.mean() + 1e-12)  # mean = 1
    return geom


def wave_correct(geom, airy_scale):
    dx = SIZE / N
    fold = geom > np.percentile(geom, 98)
    dist_px = ndimage.distance_transform_edt(~fold)
    s = dist_px * dx  # meters from fold ridge
    # true peak of |Ai(-u)|^2 is at u~1.02; normalize by sampling
    u = np.linspace(0, 8, 2048)
    Ai_max = float(np.max(np.abs(airy(-u)[0]) ** 2))
    smooth = ndimage.gaussian_filter(geom, sigma=3.0)
    cap = 6.0
    rgb = np.zeros((N, N, 3))
    w0 = airy_scale
    for c in range(3):
        w = w0 * (LAMBDAS[c] / 550e-9) ** (2.0 / 3.0)
        prof = (np.abs(airy(-np.clip(s / w, 0, 8))[0]) ** 2) / Ai_max
        band = s < 5 * w
        strength = np.minimum(smooth, cap)
        ch = geom.copy()
        ch[band] = strength[band] * (0.15 + 0.85 * prof[band])
        ch = np.minimum(ch, cap * 1.35)
        rgb[..., c] = ch
    # flux conservation per channel
    target = geom.sum()
    for c in range(3):
        rgb[..., c] *= target / (rgb[..., c].sum() + 1e-12)
    return rgb, geom


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--t", type=float, default=1.7)
    ap.add_argument("--airy-scale", type=float, default=0.02)
    a = ap.parse_args()
    geom = bake(a.t)
    rgb, _ = wave_correct(geom, a.airy_scale)
    print(f"geometric: mean={geom.mean():.3f} peak={geom.max():.1f}x")
    print(f"wave peak R/G/B: {rgb[...,0].max():.2f} / {rgb[...,1].max():.2f} / {rgb[...,2].max():.2f}x")
    print(f"flux ratio wave/geometric: {rgb[...,1].sum()/geom.sum():.4f} (must be ~1)")
    print(f"pixels >6x: geom={(geom>6).sum()} wave={(rgb[...,1]>6).sum()}")
    np.save("docs/caustic_wave.npy", rgb.astype(np.float32))
    if HAVE_MPL:
        fig, ax = plt.subplots(1, 2, figsize=(12, 5))
        ax[0].imshow(geom, cmap="hot", vmin=0, vmax=8)
        ax[0].set_title(f"geometric (peak {geom.max():.0f}x, blown out)")
        ax[1].imshow(np.clip(rgb / 8, 0, 1))
        ax[1].set_title("wave-corrected Airy (finite, chromatic fringes)")
        for x in ax:
            x.set_axis_off()
        fig.tight_layout()
        fig.savefig("docs/caustic_compare.png", dpi=90)
        print("wrote docs/caustic_compare.png + docs/caustic_wave.npy")
    else:
        print("matplotlib missing: npy saved, no png")


if __name__ == "__main__":
    main()
