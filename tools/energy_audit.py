"""energy_audit.py -- the non-circular replacement for "flux conserved to 1.0000".

CRITIQUE C5 rules the headline flux ratio circular: the band-local step
divides by the measured flux by construction, so measuring 1.0000 afterwards
tests the division, not the physics. The non-circular question is: does the
total energy leaving the glass equal the energy entering it, with NO
renormalisation anywhere?

Method: extend the brute-force tracer (tools/verify_ray_map.py) so every ray
carries its Fresnel transmission product through each interface. Sum the
weights of rays entering the outer wall (power in) vs weights landing on the
receiver patch (power out). Separately, integrate our baked field over the
patch (its own-mean normalisation noted) and compare against the
Fresnel-weighted brute-force landing sum. A mismatch beyond Fresnel +
out-of-patch losses means the Airy replacement or the ceiling creates or
destroys energy.

Run:  luxvenv/Scripts/python tools/energy_audit.py
"""
import sys
import os

import numpy as np


# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_ray_map as V

EXT = V.EXT


def fresnel_T(ci, eta):
    """Unpolarized Fresnel power transmission. ci = cos(incidence) > 0."""
    ci = np.clip(ci, 1e-9, 1.0)
    si2 = eta ** 2 * (1.0 - ci * ci)
    tir = si2 >= 1.0
    ct = np.sqrt(np.clip(1.0 - si2, 0.0, 1.0))
    rs = (eta * ci - ct) / (eta * ci + ct)
    rp = (ci - eta * ct) / (ci + eta * ct)
    R = 0.5 * (rs * rs + rp * rp)
    T = np.where(tir, 0.0, 1.0 - R)
    return T


def audit(n_side=900, lam_nm=550.0):
    SUN = V.SUN
    up = np.array([0.0, 0.0, 1.0])
    ex = np.cross(SUN, up)
    ex /= np.linalg.norm(ex)
    ey = np.cross(ex, SUN)
    ey /= np.linalg.norm(ey)
    a = np.linspace(-0.045, 0.045, n_side)
    A, B = np.meshgrid(a, a)
    origin = (A[..., None] * ex + B[..., None] * ey) - SUN * 0.5
    d = np.broadcast_to(SUN, origin.shape).copy()

    nw, ng = V.water_index(lam_nm), V.glass_index(lam_nm)

    # --- outer wall
    oxy, dxy = origin[:, :, :2], d[:, :, :2]
    A2 = np.sum(dxy * dxy, axis=-1)
    B2 = 2 * np.sum(oxy * dxy, axis=-1)
    C2 = np.sum(oxy * oxy, axis=-1) - V.R_OUT ** 2
    disc = B2 ** 2 - 4 * A2 * C2
    hit_wall = disc > 0
    t = np.where(hit_wall, (-B2 - np.sqrt(np.maximum(disc, 0))) / (2 * A2), np.nan)
    z = origin[:, :, 2] + t * d[:, :, 2]
    on_wall = hit_wall & (t > 0) & (z > 0) & (z < V.H_GLASS)

    P = origin + t[..., None] * d
    nrm = np.zeros_like(P)
    with np.errstate(invalid="ignore"):
        nrm[:, :, 0] = P[:, :, 0] / V.R_OUT
        nrm[:, :, 1] = P[:, :, 1] / V.R_OUT
    ci1 = np.clip(-np.sum(d * nrm, axis=-1), 1e-9, 1.0)
    d2, ok2 = V.refract(d, nrm, 1.0 / ng)
    T1 = np.where(on_wall & ok2, fresnel_T(ci1, 1.0 / ng), 0.0)
    alive = on_wall & ok2
    power_in = float(T1[alive].sum())

    # --- inner wall
    oxy, dxy = P[:, :, :2], d2[:, :, :2]
    A2 = np.sum(dxy * dxy, axis=-1)
    B2 = 2 * np.sum(oxy * dxy, axis=-1)
    C2 = np.sum(oxy * oxy, axis=-1) - V.R_IN ** 2
    disc = B2 ** 2 - 4 * A2 * C2
    t = np.where(disc > 0, (-B2 - np.sqrt(np.maximum(disc, 0))) / (2 * A2), np.nan)
    with np.errstate(invalid="ignore"):
        P2 = P + t[..., None] * d2
    nrm2 = np.zeros_like(P2)
    with np.errstate(invalid="ignore"):
        nrm2[:, :, 0] = P2[:, :, 0] / V.R_IN
        nrm2[:, :, 1] = P2[:, :, 1] / V.R_IN
    below = alive & (P2[:, :, 2] < V.WATER)
    # Inner wall: the OUTWARD radial normal faces the incoming (inward-going)
    # ray, so dot < 0 for live rays and ci = -dot, matching V.refract's
    # convention. Using +dot clips to 1e-9 and zeroes every T2 -- the audit
    # then reads 0% throughput for 388k landed rays.
    ci2 = np.clip(-np.sum(d2 * nrm2, axis=-1), 1e-9, 1.0)
    d3w, okw = V.refract(d2, nrm2, ng / nw)
    d3a, oka = V.refract(d2, nrm2, ng / 1.0)
    T2w = fresnel_T(ci2, ng / nw)
    T2a = fresnel_T(ci2, ng / 1.0)
    d3 = np.where(below[..., None], d3w, d3a)
    survived = np.where(below, okw, oka)
    T = np.where(alive & survived, T1 * np.where(below, T2w, T2a), 0.0)
    alive = alive & survived

    # --- rippling surface for rays above the water line
    above = alive & ~below
    W = P2.copy()
    dd = d3.copy()
    for _ in range(3):
        if above.any():
            zs = V.WATER + V.wave_h(W[:, :, 0], W[:, :, 1])
            dt = (zs - W[:, :, 2]) / np.where(dd[:, :, 2] < 0, dd[:, :, 2], -1e-9)
            Wn = W + dt[..., None] * dd
            W = np.where(above[..., None], Wn, W)
    with np.errstate(invalid="ignore"):
        escaped = above & (np.hypot(W[:, :, 0], W[:, :, 1]) > V.R_IN)
    alive = alive & ~escaped
    above = above & ~escaped
    eps = 2e-5
    hx = (V.wave_h(W[:, :, 0] + eps, W[:, :, 1]) - V.wave_h(W[:, :, 0] - eps, W[:, :, 1])) / (2 * eps)
    hy = (V.wave_h(W[:, :, 0], W[:, :, 1] + eps) - V.wave_h(W[:, :, 0], W[:, :, 1] - eps)) / (2 * eps)
    nrm3 = np.stack([-hx, -hy, np.ones_like(hx)], axis=-1)
    nrm3 /= np.linalg.norm(nrm3, axis=-1, keepdims=True)
    ci3 = np.clip(-np.sum(dd * nrm3, axis=-1), 1e-9, 1.0)
    d4, ok4 = V.refract(dd, nrm3, 1.0 / nw)
    T3 = fresnel_T(ci3, 1.0 / nw)
    d3 = np.where(above[..., None], d4, d3)
    surf_survived = (~above) | ok4
    T = np.where(alive & surf_survived, T * np.where(above, T3, 1.0), 0.0)
    alive = alive & surf_survived
    hit_from = np.where(above[..., None], W, P2)

    # --- table
    dz = np.where(d3[:, :, 2] < 0, d3[:, :, 2], -1e-9)
    ttab = -hit_from[:, :, 2] / dz
    X = hit_from[:, :, 0] + ttab * d3[:, :, 0]
    Y = hit_from[:, :, 1] + ttab * d3[:, :, 1]
    on_patch = alive & (ttab > 0) & (np.abs(X) < EXT) & (np.abs(Y) < EXT)
    power_out = float(T[on_patch].sum())
    power_lost_off_patch = float(T[alive & (ttab > 0) & ~((np.abs(X) < EXT) & (np.abs(Y) < EXT))].sum())
    power_lost_absorb = float(T1[alive].sum() - T[alive].sum())

    return {
        "n_rays": n_side * n_side,
        "n_enter": int(on_wall.sum()),
        "n_land": int(on_patch.sum()),
        "power_in": power_in,
        "power_out": power_out,
        "power_off_patch": power_lost_off_patch,
        "throughput": power_out / power_in if power_in > 0 else float("nan"),
    }


def field_energy(path=_ROOT + "/out/caustic_wavy.png"):
    """Integrate the baked field. Its geometric stage normalises to mean 1.0,
    so any deficit below 1.0 is energy the Airy replacement + ceiling removed."""
    import struct
    import zlib
    d = open(path, 'rb').read()
    pos, idat = 8, b''
    while pos < len(d):
        ln, typ = struct.unpack('>I4s', d[pos:pos + 8])
        body = d[pos + 8:pos + 8 + ln]
        if typ == b'IHDR':
            w, h, depth, ct = struct.unpack('>IIBB', body[:10])
        elif typ == b'IDAT':
            idat += body
        elif typ == b'IEND':
            break
        pos += 12 + ln
    raw = zlib.decompress(idat)
    stride = w * 3 * 2
    out = np.zeros((h, w, 3), np.uint16)
    pp = 0
    for y in range(h):
        pp += 1
        out[y] = np.frombuffer(raw[pp:pp + stride], dtype='>u2').reshape(w, 3)
        pp += stride
    f = out.astype(np.float32) / 65535.0 * 16.0
    return f.mean(axis=(0, 1)), f.max(axis=(0, 1))


def main():
    print("=== energy audit: Fresnel-weighted power in vs power out ===")
    print("    no renormalisation anywhere; losses are Fresnel + off-patch only")
    for lam in (650.0, 550.0, 450.0):
        r = audit(lam_nm=lam)
        print(f"  {lam:.0f} nm  in {r['power_in']:9.1f}  out {r['power_out']:9.1f}  "
              f"off-patch {r['power_off_patch']:7.1f}  throughput {100*r['throughput']:.2f}%  "
              f"({r['n_enter']} entered, {r['n_land']} landed)")
    print()
    print("=== baked field energy (geometric stage normalised to mean 1.0) ===")
    means, mx = field_energy()
    for ch, m, x in zip("RGB", means, mx):
        print(f"  {ch}: mean {m:.3f} (deficit {100*(1-m):.1f}% removed by Airy+ceiling)  max {x:.2f}")


if __name__ == "__main__":
    main()
