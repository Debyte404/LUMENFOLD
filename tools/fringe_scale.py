"""fringe_scale.py — is the fringe structure we render physically real?

Our field softens the caustic near its folds with an Airy profile of width
`airy_scale`, currently 0.0015 m. That number was chosen for VISIBILITY (it keeps
at least 3 pixels per fringe at the bake resolution) and is documented as such.
But a fold has a physical diffraction width, and if the two differ by orders of
magnitude then the fringes in our renders are a drawing, not a prediction - and
no photograph could ever confirm them.

The physical scale comes from the wavefront's cubic term. Near a fold the ray map
behaves as x(phi) ~ x_f + (1/6) c3 (phi - phi_f)^3, and the diffraction integral
for that phase has a characteristic width

    delta = (lam^2 / (2 |c3|))^(1/3)

with c3 measured from the exact map (tools/analytic_caustic.py). This computes
both numbers and states the ratio.

Run:  python tools/fringe_scale.py
"""
import numpy as np

from analytic_caustic import R, SUN, glass_index, hit

LAM = 550e-9      # metres
AIRED = 0.0015    # what the renderer actually uses (metres)


def main():
    n = glass_index(550.0)
    print("=== the physical fringe width at the fold ===")
    print(f"  wavelength {LAM*1e9:.0f} nm, cylinder radius {R*1000:.1f} mm, "
          f"n = {n:.4f}")

    # find the fold azimuth on a fine grid, then fit the local cubic
    phis = np.linspace(np.radians(150), np.radians(260), 200001)
    _rows = []
    for p in phis:
        h = hit(p, n)
        _rows.append(h if h is not None else np.array([np.nan, np.nan]))
    pts = np.array(_rows)
    d = np.gradient(pts, phis, axis=0)
    speed = np.linalg.norm(d, axis=1)
    good = np.isfinite(speed)
    phf = phis[np.nanargmin(np.where(good, speed, np.nan))]

    # local expansion of the map along the fold direction
    w = np.radians(1.5)
    m = np.abs(phis - phf) < w
    t = phis[m] - phf
    # project onto the map's dominant direction so the fit is 1-D
    q = pts[m]
    q = q - q[len(q) // 2]
    u, s, vt = np.linalg.svd(q, full_matrices=False)
    along = q @ vt[0]
    # x(t) ~ a1 t + a3 t^3/6   (no quadratic term at a fold, by definition)
    A = np.vstack([t, t ** 3 / 6.0]).T
    coef, *_ = np.linalg.lstsq(A, along, rcond=None)
    a1, c3 = coef
    print()
    print(f"  fold at phi = {np.degrees(phf):.2f} deg")
    print(f"  local map: linear {a1:+.4e} m/rad, cubic c3 = {c3:+.4e} m/rad^3")
    # Eq. 14 normal-form diffraction width: d = (lambda^(2/3) * c^(1/3)) / (2 * pi^(2/3))
    # where c is the wavefront cubic curvature parameter in metres.
    c = abs(c3)
    d_eq14 = (LAM ** (2.0 / 3.0) * c ** (1.0 / 3.0)) / (2.0 * np.pi ** (2.0 / 3.0))
    # Transverse quadratic acceleration across the fold
    transverse = q @ vt[1]
    poly_trans = np.polyfit(t, transverse, 2)
    C_angle = abs(2.0 * poly_trans[0])
    d_trans = (LAM ** (2.0 / 3.0) * C_angle ** (1.0 / 3.0)) / (2.0 * np.pi ** (2.0 / 3.0))

    # The withdrawn heuristic formula from early drafts:
    delta_withdrawn = (LAM ** 2 / (2.0 * abs(c3))) ** (1.0 / 3.0)

    print()
    print(f"  PHYSICAL scale via Eq. 14 (c = {c:.5f} m):    d = {d_eq14*1e6:8.2f} um ({d_eq14*1000:.4f} mm)")
    print(f"  Transverse scale (C_angle = {C_angle:.5f} m):  d = {d_trans*1e6:8.2f} um ({d_trans*1000:.4f} mm)")
    print(f"  First Airy zero (|X| = 2.3381):                z1 = {2.3381*d_eq14*1e6:7.2f} um")
    print(f"  Withdrawn heuristic formula (early draft):    delta = {delta_withdrawn*1e6:8.1f} um")
    print(f"  What renderer uses for visibility:            airy_scale = {AIRED*1e6:8.1f} um")

    # Does the fringe pattern survive the source's angular size at all?
    SUN_ANGLE = np.radians(0.53)      # the real sun
    L_TO_CAUSTIC = 0.10               # glass to where the caustic forms, m
    blur = SUN_ANGLE * L_TO_CAUSTIC
    print()
    print("  ...under a real sun, fringes do not exist:")
    print(f"     source angular size 0.53 deg at {L_TO_CAUSTIC*1000:.0f} mm "
          f"blurs by {blur*1e6:.0f} um")
    print(f"     that is {blur/d_eq14:.1f}x the physical fringe spacing -> completely washed out")
    print()
    print("  CONCLUSION: under solar illumination, the caustic has no visible fringes;")
    print("  the fold is a smooth bounded ridge. The visible fringes (1.5 mm) are")
    print("  chosen for VISIBILITY, not to depict real sunlight.")
    print()
    print("  What the wave model does predict PHYSICALLY, and a photograph can")
    print("  test, is that the intensity stays FINITE at the fold instead of")
    print("  diverging: a bounded bright ridge, not a singularity. That is the")
    print("  claim to take to an experiment - boundedness, not pattern.")


if __name__ == "__main__":
    main()
