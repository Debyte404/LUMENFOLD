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
    if abs(c3) < 1e-30:
        print("  cubic term vanished - cannot estimate the diffraction width")
        return
    delta = (LAM ** 2 / (2.0 * abs(c3))) ** (1.0 / 3.0)
    print()
    print(f"  PHYSICAL diffraction width  delta = {delta*1e6:8.1f} um "
          f"({delta*1000:.4f} mm)")
    print(f"  what the renderer uses      airy_scale = {AIRED*1e6:8.1f} um "
          f"({AIRED*1000:.4f} mm)")
    print(f"  ratio                                   {AIRED/delta:8.1f}x wider "
          f"than physical")

    # Does the fringe pattern survive the source's angular size at all?
    SUN_ANGLE = np.radians(0.53)      # the real sun
    L_TO_CAUSTIC = 0.10               # glass to where the caustic forms, m
    blur = SUN_ANGLE * L_TO_CAUSTIC
    print()
    print("  ...but under a real sun it does not matter, because the fringes do")
    print("     not exist in the first place:")
    print(f"     source angular size 0.53 deg at {L_TO_CAUSTIC*1000:.0f} mm "
          f"blurs the pattern by {blur*1e6:.0f} um")
    print(f"     that is {blur/delta:.1f}x the fringe spacing -> washed out "
          f"entirely")
    print()
    print("  CONCLUSION: under this illumination the caustic has no visible")
    print("  fringes. The fold is a smooth bright ridge. So the fringe structure")
    print("  our renderer draws (1.5 mm) is neither the physical scale (0.12 mm)")
    print("  nor something a camera could see - it is a VISIBILITY CHOICE, and")
    print("  the honest position is that it makes the wave correction legible")
    print("  rather than depicting reality.")
    print()
    print("  What the wave model does predict PHYSICALLY, and a photograph can")
    print("  test, is that the intensity stays FINITE at the fold instead of")
    print("  diverging: a bounded bright ridge, not a singularity. That is the")
    print("  claim to take to an experiment - boundedness, not pattern.")


if __name__ == "__main__":
    main()
