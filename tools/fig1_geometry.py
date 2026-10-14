"""fig1_geometry.py -- decide Figure 1's geometry numerically before drawing it.

Figure 1 as first drawn had three problems, all visible in the render:

  1. it traced rays in the x-z plane using the sun vector's x and z components,
     which is not the plane the light travels in (the sun's azimuth is 27.7 deg,
     so the true path also moves in y). The section must be taken along the
     sun's azimuth, where the 2-D refraction is exact;
  2. it drew the fold band at a hardcoded 36-97 mm, while the measured ridge sits
     elsewhere -- a drawn band that does not correspond to the caustic;
  3. it labelled the air gap inside the glass as "glass", and put both material
     labels in the water region.

Two further errors were made and fixed while building this, both worth recording
because they made the figure silently wrong rather than visibly broken:

  * the light path was modelled as glass -> water at the inner wall. Per
    tools/verify_ray_map.py the path is
        air -> outer wall -> inner wall -> AIR CAVITY -> rippling surface
            -> water -> receiver,
    so light enters high on the side wall and crosses the empty cavity above the
    water before it ever meets the surface;
  * the wall was intersected as a CIRCLE of radius R_OUT. That is the cylinder's
    cross-section, but a finite cylinder cut axially section is a RECTANGLE: the
    wall is the vertical pair x = +/-R_OUT spanning z in [0, H_GLASS]. The circle
    only reaches z = +/-35 mm, so every ray was rejected for entering too low.

Rays are parametrised by the perpendicular impact parameter. This computes the
in-plane sun direction, the landing map, and the fold as the stationary points of
that map -- the definition of the fold used everywhere else in the paper.
"""
import numpy as np

R_OUT, R_IN, H_GLASS, WATER = 0.035, 0.0315, 0.090, 0.0594
SUN = np.array([0.80, 0.42, -0.43]); SUN /= np.linalg.norm(SUN)
N_WATER, N_GLASS = 1.33468, 1.52514
H = float(np.hypot(SUN[0], SUN[1]))
D = np.array([H, SUN[2]]); D /= np.linalg.norm(D)      # in-plane sun direction
NPERP = np.array([-D[1], D[0]])
SLOPE = D[1] / D[0]

# the wall is the vertical line x = -R_OUT; z_hit is affine in b, which is what
# the scan range must be derived from rather than guessed
Z_AT_B0 = -SLOPE * R_OUT                                # hit height for b = 0
DZ_DB = NPERP[1] - SLOPE * NPERP[0]


def refract(d, n, eta):
    ci = -float(np.dot(d, n))
    k = 1.0 - eta * eta * (1.0 - ci * ci)
    if k < 0:
        return None
    return eta * d + (eta * ci - np.sqrt(k)) * n


def z_hit(b):
    """Height at which the ray with impact parameter b crosses x = -R_OUT."""
    return Z_AT_B0 + DZ_DB * b


def path(b_par, ripple=0.0):
    """Polyline for the cavity-path ray with impact parameter b_par.

    ripple=0 draws the flat surface; ripple=s draws a schematic sinusoid of
    amplitude s and the scene's own 42 mm wavelength, which is what makes the
    caustic. Returns (points, landing_r) or (points, None).
    """
    p = -0.30 * D + b_par * NPERP
    d = D.copy()
    pts = [tuple(p)]
    if not (0.0 < z_hit(b_par) < H_GLASS):
        return pts, None
    # air -> glass at the outer wall (normal faces the incoming air)
    t = (-R_OUT - p[0]) / d[0]
    p = p + t * d
    pts.append(tuple(p))
    d = refract(d, np.array([-1.0, 0.0]), 1.0 / N_GLASS)
    if d is None:
        return pts, None
    # glass -> cavity or water at the inner wall
    t = (-R_IN - p[0]) / d[0]
    if t <= 0:
        return pts, None
    p = p + t * d
    pts.append(tuple(p))
    in_water = p[1] < WATER
    d = refract(d, np.array([-1.0, 0.0]),
                N_GLASS / (N_WATER if in_water else 1.0))
    if d is None:
        return pts, None
    # cross the water surface if the ray is still in the cavity
    if not in_water:
        if abs(d[1]) < 1e-12:
            return pts, None
        zs = WATER + (ripple * np.sin(2 * np.pi * p[0] / 0.042) if ripple else 0.0)
        t = (zs - p[1]) / d[1]
        if t <= 0:
            return pts, None
        p = p + t * d
        pts.append(tuple(p))
        d = refract(d, np.array([0.0, 1.0]), 1.0 / N_WATER)
        if d is None:
            return pts, None
    # -> receiver
    if abs(d[1]) < 1e-12:
        return pts, None
    t = -p[1] / d[1]
    if t <= 0:
        return pts, None
    p = p + t * d
    pts.append(tuple(p))
    return pts, float(p[0])


def main():
    print(f"sun {SUN}")
    print(f"  in-plane direction ({D[0]:.4f}, {D[1]:.4f}), "
          f"elevation {np.degrees(np.arctan2(-D[1], D[0])):.2f} deg")
    print(f"  wall-hit height z(b) = {Z_AT_B0*1000:.2f} + {DZ_DB:.4f}*b  (mm)")
    b_water = (WATER - Z_AT_B0) / DZ_DB
    b_top = (H_GLASS - Z_AT_B0) / DZ_DB
    print(f"  cavity-path range: b in [{b_water*1000:.2f}, {b_top*1000:.2f}] mm")
    print()

    b = np.linspace(b_water + 1e-5, b_top - 1e-5, 6000)
    r = np.array([path(bi)[1] for bi in b], dtype=float)
    ok = ~np.isnan(r)
    print(f"rays on the cavity path reaching the receiver: {ok.sum()} / {b.size}")
    rr, bb = r[ok], b[ok]
    print(f"landing range: {rr.min()*1000:.1f} .. {rr.max()*1000:.1f} mm")

    dr = np.gradient(rr, bb)
    idx = np.where(np.diff(np.sign(dr)) != 0)[0]
    print(f"\nstationary points of the landing map (fold, det J = 0): {idx.size}")
    for i in idx:
        print(f"   b = {bb[i]*1000:+7.3f} mm  ->  r = {rr[i]*1000:+7.2f} mm")
    print(f"\ncaustic extent (turning points of the landing map): "
          f"r in [{rr.min()*1000:.1f}, {rr.max()*1000:.1f}] mm")

    # the fold in the flat-surface case is the turning point of r(z_hit); report
    # the span between the two outermost turning points
    if idx.size >= 2:
        lo, hi = np.sort(rr[idx])[[0, -1]]
        print(f"FOLD BAND: r = {lo*1000:.1f} .. {hi*1000:.1f} mm "
              f"(width {abs(hi-lo)*1000:.1f} mm)")

    print("\nrays chosen for the drawing (b -> landing on the flat surface):")
    for bi in (b_water + 0.004, b_water + 0.012, b_water + 0.020,
               b_top - 0.008, b_top - 0.002):
        _, v = path(bi)
        print(f"   b {bi*1000:+7.3f} mm  z_hit {z_hit(bi)*1000:5.1f} mm -> r "
              f"{(v*1000 if v is not None else float('nan')):8.1f} mm")


if __name__ == "__main__":
    main()
