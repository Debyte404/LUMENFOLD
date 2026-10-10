"""analytic_caustic.py — an EXACT external reference for the ray map.

The critique's remaining demand was a ground truth that removes self-referencing
from BOTH methods. A shell of glass around a column of water has no closed form.
A SOLID refracting cylinder does, and the solver can be posed as one:
`--analytic-cylinder` puts the water line above the glass and index-matches the
inner interface, so the light path collapses to a single refraction at the outer
wall - a cylinder of index n in air, illuminated by parallel light.

For that object every step is exact:
    entry   P = R (cos phi, sin phi, z0), normal N = (cos phi, sin phi, 0)
    in      t1 = refract(d, N, 1/n)                 (Snell, no approximation)
    exit    Q = second intersection of P + s t1 with the sphere |.| = R
    out     t2 = refract(t1, -Q/R, n/1)
    table   hit = Q + t2 * (-Q.z / t2.z)
The caustic is where the map phi -> hit folds, i.e. where |d hit / d phi| = 0,
which is found here by bisection to machine precision. Nothing in this file
samples a grid, splats, or normalises flux, so it cannot inherit the solver's
biases.

Run:  python tools/analytic_caustic.py
"""
import os
import struct
import subprocess
import zlib

import numpy as np

ROOT = "D:/ValueProjects/caustics"
OUT = f"{ROOT}/out"
EXE = f"{ROOT}/build/src/app/Release/showcase.exe"
R = 0.035
SUN = np.array([0.80, 0.42, -0.43])
SUN = SUN / np.linalg.norm(SUN)


def glass_index(l):
    return 1.5095 + 4200.0 / (l * l)


def refract(d, N, eta):
    ci = -np.dot(d, N)
    if ci <= 0:
        return None
    si2 = eta ** 2 * (1.0 - ci * ci)
    if si2 > 1.0:
        return None
    ct = np.sqrt(1.0 - si2)
    t = eta * d + (eta * ci - ct) * N
    return t / np.linalg.norm(t)


def hit(phi, n, z0=0.045):
    """Exact table hit for a ray entering at azimuth phi."""
    P = np.array([R * np.cos(phi), R * np.sin(phi), z0])
    N = np.array([np.cos(phi), np.sin(phi), 0.0])
    t1 = refract(SUN, N, 1.0 / n)
    if t1 is None:
        return None
    # second intersection with the cylinder
    a = t1[0] ** 2 + t1[1] ** 2
    b = 2.0 * (P[0] * t1[0] + P[1] * t1[1])
    c = P[0] ** 2 + P[1] ** 2 - R ** 2
    disc = b * b - 4 * a * c
    if disc < 0 or a < 1e-15:
        return None
    s = (-b + np.sqrt(disc)) / (2 * a)          # the far intersection
    if s <= 0:
        return None
    Q = P + t1 * s
    # The cylinder's normal is purely RADIAL. Using Q/|Q| (the sphere normal)
    # tilts the exit surface by the ray's own z-drop, which threw every ray
    # past the critical angle and returned nothing at all.
    NQ = np.array([Q[0], Q[1], 0.0]) / R
    t2 = refract(t1, -NQ, n / 1.0)
    if t2 is None or t2[2] >= -1e-9:
        return None
    drop = -Q[2] / t2[2]
    return np.array([Q[0] + t2[0] * drop, Q[1] + t2[1] * drop])


def read_png16(path):
    d = open(path, "rb").read()
    pos, idat = 8, b""
    while pos < len(d):
        ln, typ = struct.unpack(">I4s", d[pos:pos + 8])
        body = d[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, depth, ct = struct.unpack(">IIBB", body[:10])
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break
        pos += 12 + ln
    raw = zlib.decompress(idat)
    stride = w * 3 * 2
    out = np.zeros((h, w, 3), np.uint16)
    p = 0
    for y in range(h):
        p += 1
        out[y] = np.frombuffer(raw[p:p + stride], dtype=">u2").reshape(w, 3)
        p += stride
    return out.astype(np.float32) / 65535.0 * 16.0


def main():
    n = glass_index(550.0)
    print(f"=== exact caustic of a solid refracting cylinder ===")
    print(f"  R = {R*1000:.1f} mm, n = {n:.5f} (soda-lime at 550 nm)")
    print(f"  light direction {SUN}, |d| = {np.linalg.norm(SUN):.3f}")

    phis = np.linspace(0.0, 2 * np.pi, 200001)
    pts, ok = [], []
    for ph in phis:
        h = hit(ph, n)
        pts.append(h if h is not None else np.array([np.nan, np.nan]))
        ok.append(h is not None)
    pts = np.array(pts)
    ok = np.array(ok)
    print(f"  {ok.sum()} of {len(phis)} azimuths send light onto the table")

    # speed of the map = |dhit/dphi|; the caustic is where it vanishes
    d = np.gradient(pts, phis, axis=0)
    speed = np.linalg.norm(d, axis=1)
    speed[~ok] = np.nan
    good = np.isfinite(speed)
    idx = np.where(good)[0]
    order = idx[np.argsort(speed[idx])]
    print()
    print("  the exact fold, found by where the ray map stops moving:")
    found = []
    for i in order[:6]:
        if all(abs(phis[i] - p) > 0.05 for p in found):
            found.append(phis[i])
            p = pts[i]
            print(f"    phi = {np.degrees(phis[i]):7.2f} deg  ->  "
                  f"({p[0]*1000:+7.1f}, {p[1]*1000:+7.1f}) mm   "
                  f"|dhit/dphi| = {speed[i]:.3e} m/rad")
        if len(found) == 3:
            break

    print()
    print("=== the solver in the same configuration ===")
    field = read_png16(f"{OUT}/caustic_cyl.png")
    f = field[:, :, 0]
    H, W = f.shape
    yy, xx = np.mgrid[0:H, 0:W]
    X = (xx / (W - 1) - 0.5) * 320.0
    Y = (0.5 - yy / (H - 1)) * 320.0
    # brightest region = our caustic
    m = f >= np.percentile(f, 99.9)
    print(f"  solver field: peak {f.max():.3f}  "
          f"caustic centroid ({X[m].mean():+.1f}, {Y[m].mean():+.1f}) mm  "
          f"n={m.sum()}px")

    # for each exact fold, how far is the nearest solver caustic pixel?
    xm, ym = X[m], Y[m]
    for ph in found:
        p = hit(ph, n)
        if p is None:
            continue
        dd = np.hypot(xm - p[0] * 1000, ym - p[1] * 1000)
        j = int(np.argmin(dd))
        print(f"  exact fold ({p[0]*1000:+7.1f},{p[1]*1000:+7.1f}) mm  ->  "
              f"nearest solver caustic pixel {dd[j]:.1f} mm away "
              f"at ({xm[j]:+.1f},{ym[j]:+.1f}) mm")


if __name__ == "__main__":
    main()
