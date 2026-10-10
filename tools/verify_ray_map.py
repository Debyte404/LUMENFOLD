"""verify_ray_map.py — independent brute-force ray trace of the same scene, to
check the ray map our field is built from.

Our solver builds the caustic from a PARAMETRIC map: it samples the wall by
(phi, z0), differentiates that map analytically to get the Jacobian, and splats
with 1/|det J|. Every one of those steps is an opportunity for a bookkeeping
error, and the field that comes out is the thing everything else is calibrated
against.

This traces the same geometry the dumb way: launch rays uniformly over the
incident cross-section, intersect explicitly with the outer wall, the inner wall,
the rippling water surface and the table, and just count where they land. No
parametrisation, no Jacobian, no flux renormalisation - the density IS the
caustic. Two independent methods agreeing on where the light lands is real
evidence; one method agreeing with itself is not.

Run:  python tools/verify_ray_map.py
"""
import numpy as np
from PIL import Image

OUT = "D:/ValueProjects/caustics/out"
R_OUT, R_IN, H_GLASS = 0.035, 0.0315, 0.090
WATER = 0.0594
EXT = 0.16
N = 512

SUN = np.array([0.80, 0.42, -0.43])
SUN = SUN / np.linalg.norm(SUN)


def water_index(lam_nm):
    # Cauchy, matching the solver's water model
    return 1.3208 + 5200.0 / (lam_nm ** 2)


def glass_index(lam_nm):
    return 1.5095 + 4200.0 / (lam_nm ** 2)


AMP = (0.00065, 0.00040, 0.00025, 0.00015)
LAM = (0.042, 0.027, 0.017, 0.011)
DX = (1.0, 0.35, -0.75, 0.6)
DY = (0.25, 1.0, 0.55, -0.9)
PHASE = 0.0


def wave_h(x, y, t=PHASE):
    h = np.zeros_like(x)
    for i in range(4):
        n = np.hypot(DX[i], DY[i])
        k = 2 * np.pi / LAM[i]
        h += AMP[i] * np.sin(k * ((DX[i] / n) * x + (DY[i] / n) * y) + t * (1 + i))
    return h


def refract(d, nrm, eta):
    """d, nrm unit; nrm faces the incoming ray. Returns refracted dir or None."""
    ci = -np.sum(d * nrm, axis=-1)
    ok = ci > 0
    ci = np.clip(ci, 1e-9, 1.0)
    si2 = eta ** 2 * (1.0 - ci ** 2)
    good = ok & (si2 <= 1.0)
    ct = np.sqrt(np.clip(1.0 - si2, 0.0, 1.0))
    out = eta * d + (eta * ci - ct)[..., None] * nrm
    out /= np.linalg.norm(out, axis=-1, keepdims=True)
    return out, good


def trace(n_side=900, lam_nm=550.0):
    """Return table-hit x,y for a grid of rays launched along -SUN."""
    # launch grid on a plane upstream, oriented across the sun direction
    up = np.array([0.0, 0.0, 1.0])
    ex = np.cross(SUN, up)
    ex /= np.linalg.norm(ex)
    ey = np.cross(ex, SUN)
    ey /= np.linalg.norm(ey)
    a = np.linspace(-0.045, 0.045, n_side)
    A, B = np.meshgrid(a, a)
    origin = (A[..., None] * ex + B[..., None] * ey) - SUN * 0.5
    d = np.broadcast_to(SUN, origin.shape).copy()

    nw, ng = water_index(lam_nm), glass_index(lam_nm)

    # --- outer wall: cylinder radius R_OUT about the z axis
    oxy, dxy = origin[:, :, :2], d[:, :, :2]
    A2 = np.sum(dxy * dxy, axis=-1)
    B2 = 2 * np.sum(oxy * dxy, axis=-1)
    C2 = np.sum(oxy * oxy, axis=-1) - R_OUT ** 2
    disc = B2 ** 2 - 4 * A2 * C2
    hit_wall = disc > 0
    t = np.where(hit_wall, (-B2 - np.sqrt(np.maximum(disc, 0))) / (2 * A2), np.nan)
    z = origin[:, :, 2] + t * d[:, :, 2]
    on_wall = hit_wall & (t > 0) & (z > 0) & (z < H_GLASS)

    P = origin + t[..., None] * d
    nrm = np.zeros_like(P)
    with np.errstate(invalid="ignore"):
        nrm[:, :, 0] = P[:, :, 0] / R_OUT
        nrm[:, :, 1] = P[:, :, 1] / R_OUT
    d2, ok2 = refract(d, nrm, 1.0 / ng)
    alive = on_wall & ok2

    # --- inner wall
    oxy, dxy = P[:, :, :2], d2[:, :, :2]
    A2 = np.sum(dxy * dxy, axis=-1)
    B2 = 2 * np.sum(oxy * dxy, axis=-1)
    C2 = np.sum(oxy * oxy, axis=-1) - R_IN ** 2
    disc = B2 ** 2 - 4 * A2 * C2
    t = np.where(disc > 0, (-B2 - np.sqrt(np.maximum(disc, 0))) / (2 * A2), np.nan)
    with np.errstate(invalid="ignore"):
        P2 = P + t[..., None] * d2
    nrm2 = np.zeros_like(P2)
    with np.errstate(invalid="ignore"):
        nrm2[:, :, 0] = P2[:, :, 0] / R_IN
        nrm2[:, :, 1] = P2[:, :, 1] / R_IN
    # The ray is still travelling INWARD here (it is leaving the glass shell and
    # entering the cavity), so the normal facing the incoming medium is the
    # OUTWARD radial one. Using the inward normal makes every ray fail the
    # cosine test - the same mistake that emptied the field in the C++ solver.
    n_in = nrm2
    # below the water line the next medium is water, above it is air then the
    # rippling surface; choose per-ray
    below = alive & (P2[:, :, 2] < WATER)
    d3w, okw = refract(d2, n_in, ng / nw)
    d3a, oka = refract(d2, n_in, ng / 1.0)
    d3 = np.where(below[..., None], d3w, d3a)
    alive = alive & np.where(below, okw, oka)

    # --- rays above the water line must cross the rippling surface
    above = alive & ~below
    W = P2.copy()
    dd = d3.copy()
    for _ in range(3):
        if above.any():
            zs = WATER + wave_h(W[:, :, 0], W[:, :, 1])
            dt = (zs - W[:, :, 2]) / np.where(dd[:, :, 2] < 0, dd[:, :, 2], -1e-9)
            Wn = W + dt[..., None] * dd
            W = np.where(above[..., None], Wn, W)
    # A ray entering ABOVE the water line travels through the air cavity and can
    # reach the FAR WALL before it ever meets the surface: the cavity is only
    # 31.5 mm across and the descent to the water line is ~16 mm at a slope of
    # about 0.38, so the horizontal run is ~42 mm. Those rays must be discarded,
    # not traced to a surface they never reach - leaving them in put a large
    # spurious population on the wrong side of the glass.
    with np.errstate(invalid="ignore"):
        escaped = above & (np.hypot(W[:, :, 0], W[:, :, 1]) > R_IN)
    alive = alive & ~escaped
    above = above & ~escaped

    # normal of the rippled surface
    eps = 2e-5
    hx = (wave_h(W[:, :, 0] + eps, W[:, :, 1]) - wave_h(W[:, :, 0] - eps, W[:, :, 1])) / (2 * eps)
    hy = (wave_h(W[:, :, 0], W[:, :, 1] + eps) - wave_h(W[:, :, 0], W[:, :, 1] - eps)) / (2 * eps)
    nrm3 = np.stack([-hx, -hy, np.ones_like(hx)], axis=-1)
    nrm3 /= np.linalg.norm(nrm3, axis=-1, keepdims=True)
    d4, ok4 = refract(dd, nrm3, 1.0 / nw)
    d3 = np.where(above[..., None], d4, d3)
    alive = alive & (~above | ok4)
    hit_from = np.where(above[..., None], W, P2)

    # --- straight to the table
    dz = np.where(d3[:, :, 2] < 0, d3[:, :, 2], -1e-9)
    ttab = -hit_from[:, :, 2] / dz
    X = hit_from[:, :, 0] + ttab * d3[:, :, 0]
    Y = hit_from[:, :, 1] + ttab * d3[:, :, 1]
    sel = alive & (ttab > 0) & (np.abs(X) < EXT) & (np.abs(Y) < EXT)
    return X[sel], Y[sel], int(sel.sum()), int(on_wall.sum()), int(escaped.sum())


def to_grid(X, Y):
    """Bin hits, row 0 = +Y to match the baked field's dump convention.

    Getting this backwards produced a clean 90-degree-free Y MIRROR between the
    two maps - identity correlation +0.19 against flip-y +0.91 - which looks
    exactly like a physics disagreement and is not one. The field is written with
    row 0 at +Y (see the exporter), so anything compared against it must be too.
    """
    g = np.zeros((N, N))
    ix = ((X + EXT) / (2 * EXT) * N).astype(int)
    iy = ((EXT - Y) / (2 * EXT) * N).astype(int)
    ok = (ix >= 0) & (ix < N) & (iy >= 0) & (iy < N)
    np.add.at(g, (iy[ok], ix[ok]), 1.0)
    return g


def load_field(path, shape):
    a = np.asarray(Image.open(path)).astype(np.float32)
    if a.ndim == 3:
        a = a[:, :, :3].mean(axis=2)
    a = a / 65535.0 * 16.0
    return np.asarray(Image.fromarray(a.astype(np.float32), mode="F")
                      .resize(shape[::-1], Image.BOX))


def tiles(a, k):
    h, w = a.shape
    bh, bw = h // k, w // k
    return a[: bh * k, : bw * k].reshape(k, bh, k, bw).mean(axis=(1, 3))


def centroid(f, k=32):
    t = tiles(f, k)
    t = np.clip(t - np.median(t), 0, None)
    tot = t.sum()
    rr, cc = np.mgrid[0:k, 0:k]
    x = ((cc * t).sum() / tot + 0.5) / k * 320.0 - 160.0
    y = 160.0 - ((rr * t).sum() / tot + 0.5) / k * 320.0
    return x, y


def main():
    print("=== independent brute-force trace (no parametrisation, no Jacobian) ===")
    X, Y, nhit, nwall, nesc = trace()
    print(f"  {nwall} of {900*900} rays entered the glass; {nesc} died on the far "
          f"wall before reaching the surface; {nhit} landed on the patch")
    brute = to_grid(X, Y)
    field = load_field(f"{OUT}/caustic_wavy.png", brute.shape)
    print(f"  brute-force map: {brute.sum():.0f} hits, "
          f"mean/flat-pixel {brute.mean():.2f}")
    med_b = np.median(brute)
    area_b = 100 * (brute > med_b + 0.02 * (brute.max() - med_b)).mean()
    med_f = np.median(field)
    area_f = 100 * (field > med_f + 0.02 * (field.max() - med_f)).mean()
    print(f"  caustic area (> median+3): brute force {area_b:.2f}%  "
          f"our field {area_f:.2f}%")
    for k in (8, 16, 32, 64):
        a = tiles(brute, k)
        b = tiles(field, k)
        a = a - a.mean()
        b = b - b.mean()
        d = np.sqrt((a * a).sum() * (b * b).sum())
        r = (a * b).sum() / d if d > 0 else 0.0
        print(f"    correlation at {k:>3}x{k:<3} k={k:>2}  r = {r:+.3f}")
    bx, by = centroid(brute)
    fx, fy = centroid(field)
    print(f"  caustic centroid: brute ({bx:+7.1f},{by:+7.1f}) mm   "
          f"ours ({fx:+7.1f},{fy:+7.1f}) mm   "
          f"offset {np.hypot(bx-fx, by-fy):.1f} mm on a 320 mm patch")


if __name__ == "__main__":
    main()
