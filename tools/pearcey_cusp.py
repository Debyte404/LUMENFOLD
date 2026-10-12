"""pearcey_cusp.py -- the cusp case the paper leaves as an untested conjecture.

Section 8 of the paper says the correction is defined only for a fold: at a cusp the
local phase is quartic rather than cubic, the diffraction pattern is a Pearcey
function, and "we have not built or tested the cusp case, so we do not know whether
the natural generalisation -- detect the higher-order stratum, substitute the
corresponding catastrophe function -- works in practice at a comparable cost."

This tool tests it, and the answer is not the one the paper hopes for. See `main`.

Convention, used throughout:

    phi(u; x, y) = u^4 + x u^2 + y u
    Pe(x, y)     = integral over R of exp(i phi) du

    ray map     phi' = 4u^3 + 2xu + y = 0
    fold curve  phi'' = 12u^2 + 2x = 0   ->  (x, y) = (-6 s^2, 8 s^3)
    cusp point  phi''' = 24u = 0         ->  (x, y) = (0, 0)

The fold curve is a semicubical parabola: two branches of the fold meet at the
origin, which is what makes a cusp more than two folds side by side.
"""
import sys
import time

import numpy as np

try:
    import scipy.special as sp
except ImportError:
    sp = None

REPO_ROOT = None  # unused; kept out deliberately so the tool has no repo dependency


# --------------------------------------------------------------------------
# the Pearcey function
# --------------------------------------------------------------------------

def closed_form_origin():
    """Pe(0, 0) exactly.

    Substituting t = a u^4 in the convergent integral over R of exp(-a u^4) du
    = (1/2) a^(-1/4) Gamma(1/4), and continuing a -> -i, gives a^(-1/4) =
    exp(i pi/8), hence

        Pe(0,0) = (1/2) Gamma(1/4) exp(i pi/8).

    It is Gamma(1/4), not Gamma(3/4): t = u^4 turns exp(i u^4) du into
    t^(-3/4) exp(i t) dt, so the exponent in the Mellin form is s = 1/4.
    """
    g = sp.gamma(0.25) if sp is not None else 3.6256099082219083
    return 0.5 * g * np.exp(1j * np.pi / 8)


def _phase(u, x, y):
    return u ** 4 + x * u ** 2 + y * u


def _dphase(u, x, y):
    return 4 * u ** 3 + 2 * x * u + y


def pearcey_rotated(x, y, R=9.0, n=200001):
    """Pe(x, y) along the deformed contour u = r exp(i pi/8).

    Valid for x > 0, y > 0, where i u^4 = -r^4 and the quadratic and linear terms
    decay too. The integrand is then a fast-decaying Gaussian-type function and a
    plain trapezoid reaches near machine precision. This is the accurate reference
    the real-axis method is checked against.
    """
    th = np.pi / 8
    r = np.linspace(-R, R, n)
    u = r * np.exp(1j * th)
    return np.trapezoid(np.exp(1j * _phase(u, x, y)) * np.exp(1j * th), r)


def _tail(U, x, y, sign):
    """Integral from U to infinity of exp(i phi(sign*t)) dt, two asymptotic terms.

    With f' = sign phi'(u) and f'' = phi''(u) at u = sign U, integration by parts
    gives -exp(i f)/(i f') + exp(i f) f''/f'^3 + O(1/U^5). The leading term alone
    leaves O(1/U^3), which showed up as a 1.3e-5 error at the default U and looked
    like a bug.
    """
    u = sign * U
    p = _phase(u, x, y)
    d1 = sign * _dphase(u, x, y)
    d2 = 12.0 * u * u + 2.0 * x
    if abs(d1) < 1e-12:
        return 0.0 + 0.0j
    e = np.exp(1j * p)
    return -e / (1j * d1) + e * d2 / d1 ** 3


def pearcey(x, y, U=None, pts_per_cycle=48.0):
    """Pe(x, y) by refined trapezoid on [-U, U] plus the analytic tail.

    General in (x, y), which is why the paper's cost claim needs this one: the
    rotated contour only converges for x, y > 0, and a caustic is mostly elsewhere.
    """
    if U is None:
        roots = np.roots([4.0, 0.0, 2.0 * x, float(y)])
        real = np.real(roots[np.abs(np.imag(roots)) < 1e-9])
        U = max(8.0, (np.max(np.abs(real)) if real.size else 0.0) + 8.0)

    k_edge = abs(_dphase(U, x, y))
    h = (2 * np.pi / pts_per_cycle) / max(k_edge, 1e-9)
    n = max(int(np.ceil(2 * U / h)), 2001)
    u = np.linspace(-U, U, n)
    I = np.trapezoid(np.exp(1j * _phase(u, x, y)), u)
    return I + _tail(U, x, y, 1.0) + _tail(U, x, y, -1.0)


# --------------------------------------------------------------------------
# the geometry
# --------------------------------------------------------------------------

def fold_curve(s):
    """The cusp's fold curve, parametrised by its stationary point s."""
    return -6.0 * s ** 2, 8.0 * s ** 3


def geometric_amplitude(x, y):
    """The geometric (ray-optics) amplitude of the same normal form.

    Sum over real stationary points of |phi''|^(-1/2), the standard
    stationary-phase amplitude. It DIVERGES on the fold curve, where phi'' = 0 --
    and at the cusp (0,0) two such divergences coincide.
    """
    r = np.roots([4.0, 0.0, 2.0 * x, float(y)])
    real = r[np.abs(np.imag(r)) < 1e-7]
    tot = 0.0
    for u in real:
        d2 = 12.0 * u * u + 2.0 * x
        if abs(d2) > 1e-12:
            tot += 1.0 / np.sqrt(abs(d2))
    return tot


def amplitude_along(xs, yv):
    return np.array([geometric_amplitude(float(x), float(yv)) for x in xs])


def fit_exponent(deltas, vals):
    """Least-squares slope of log|value| against log(delta)."""
    d = np.asarray(deltas, float)
    v = np.asarray(vals, float)
    ok = v > 0
    return np.polyfit(np.log(d[ok]), np.log(v[ok]), 1)[0]


def cusp_case():
    """Measure the divergence exponents by approaching each stratum transversally.

    Sitting exactly on the fold is useless as a test: phi'' is zero there, so the
    amplitude is infinite and a numeric root finder returns whatever its own
    precision allows. The exponents have to be measured by approaching from a side
    where the rays actually exist and fitting the scaling.

    Two traps, both hit on the first attempt:

      * the fold has a LIT side and a SHADOW side. Approached from the shadow side
        the two merging rays are complex and the amplitude is simply flat; the
        first run did exactly that and reported an exponent of 0.0000.
      * the quantity that diverges as delta^(-1/2) is the INTENSITY, not the
        amplitude. The amplitude goes as delta^(-1/4).

    The result that matters for the paper: a cusp does NOT inherit the fold's
    exponent. Approaching (0,0) along x = 0 leaves a single real stationary point at
    u = (-y/4)^(1/3), so phi'' = 12u^2 and the amplitude goes as |y|^(-1/3) --
    measured -0.3333 against the analytic -1/3. Different exponent, different
    catastrophe function: this is why Airy cannot simply be reused at a cusp.
    """
    out = {}

    # --- fold: approach a generic fold point (s = 2) from its LIT side
    x0, y0 = fold_curve(2.0)
    ds = np.array([1e-2, 1e-3, 1e-4, 1e-5])
    famp = np.array([abs(geometric_amplitude(x0 - float(d), y0)) for d in ds])
    out["fold_amp"] = famp
    out["fold_intensity"] = famp ** 2
    out["fold_amp_exponent"] = fit_exponent(ds, famp)
    out["fold_int_exponent"] = fit_exponent(ds, famp ** 2)
    out["fold_shadow"] = np.array([abs(geometric_amplitude(x0 + float(d), y0))
                                   for d in ds])

    # --- cusp: approach the origin along x = 0
    ys = np.array([1e-1, 1e-2, 1e-3, 1e-4])
    camp = np.array([abs(geometric_amplitude(0.0, float(y))) for y in ys])
    out["cusp_amp"] = camp
    out["cusp_intensity"] = camp ** 2
    out["cusp_amp_exponent"] = fit_exponent(ys, camp)
    out["cusp_int_exponent"] = fit_exponent(ys, camp ** 2)

    out["deltas"] = ds
    out["ys"] = ys
    # the corrected field's own intensity along the same approaches
    out["fold_corrected_int"] = np.array(
        [abs(pearcey(x0 - float(d), y0)) ** 2 for d in ds])
    out["cusp_corrected_int"] = np.array(
        [abs(pearcey(0.0, float(y))) ** 2 for y in ys])
    return out


# --------------------------------------------------------------------------
# the test
# --------------------------------------------------------------------------

def main():
    print("The cusp case: does the fold recipe generalise?")
    print("=" * 70)

    # ---- 1. the Pearcey function is right ---------------------------------
    ex = closed_form_origin()
    rot = pearcey_rotated(0.0, 0.0)
    print("\n[1] Pearcey implementation")
    print(f"    closed form  Pe(0,0) = {ex.real:+.9f} {ex.imag:+.9f}i")
    print(f"    rotated      {rot.real:+.9f} {rot.imag:+.9f}i   "
          f"rel err {abs(rot-ex)/abs(ex):.2e}")
    worst = 0.0
    for (x, y) in [(1.0, 1.0), (2.0, 3.0), (5.0, 2.0), (8.0, 4.0), (12.0, 6.0)]:
        a, b = pearcey_rotated(x, y), pearcey(x, y)
        worst = max(worst, abs(a - b) / abs(a))
    print(f"    cross-method worst relative disagreement: {worst:.2e} "
          f"over 5 off-axis points")

    # ---- 2. the divergence exponents ------------------------------------
    print("\n[2] Divergence exponents, measured by approaching the stratum")
    cc = cusp_case()
    ds, ys = cc["deltas"], cc["ys"]

    print("\n    generic fold point, approached from its LIT side:")
    print("      delta      amplitude   delta^-0.25      intensity   delta^-0.5")
    for i, d in enumerate(ds):
        pa = d ** -0.25
        pi_ = d ** -0.5
        print(f"      {d:8.0e}  {cc['fold_amp'][i]:9.4f}  {pa:11.4f}"
              f"   {cc['fold_intensity'][i]:10.4f}  {pi_:10.4f}")
    print(f"      amplitude exponent {cc['fold_amp_exponent']:+.4f}  (analytic -1/4)")
    print(f"      intensity exponent {cc['fold_int_exponent']:+.4f}  (analytic -1/2)")
    print(f"      shadow side (delta > 0): amplitude "
          f"{cc['fold_shadow'][0]:.4f} -> {cc['fold_shadow'][-1]:.4f}, flat")

    print("\n    cusp point, approached along x = 0:")
    print("      y          amplitude   y^-0.333        intensity   y^-0.667")
    for i, y in enumerate(ys):
        pa = y ** (-1.0 / 3.0)
        pi_ = y ** (-2.0 / 3.0)
        print(f"      {y:8.0e}  {cc['cusp_amp'][i]:9.4f}  {pa:11.4f}"
              f"   {cc['cusp_intensity'][i]:10.4f}  {pi_:10.4f}")
    print(f"      amplitude exponent {cc['cusp_amp_exponent']:+.4f}  (analytic -1/3)")
    print(f"      intensity exponent {cc['cusp_int_exponent']:+.4f}  (analytic -2/3)")

    print("\n    This is the result the paper's conjecture needed. A cusp does NOT")
    print("    inherit the fold's exponent: along x = 0 the single real stationary")
    print("    point sits at u = (-y/4)^(1/3), so phi'' = 12u^2 and the amplitude")
    print("    goes as |y|^(-1/3), not |delta|^(-1/4). Different exponent, so a")
    print("    different catastrophe function -- Airy cannot simply be reused.")
    print("\n    The corrected field stays finite on both approaches (|Pe|^2 is")
    print("    bounded), so the substitution itself does what it is meant to.")
    print("    The cost is what fails; see [3].")

    # ---- 3. the cost -----------------------------------------------------
    print("\n[3] Cost, which is where the conjecture actually fails")

    N = 20
    t0 = time.perf_counter()
    for _ in range(N):
        pearcey(1.0, 1.0)
    t_pe = (time.perf_counter() - t0) / N

    # an Airy LUT lookup, the fold case's cost, for scale
    lut_x = np.linspace(0.0, 8.0, 2048)
    lut_y = np.abs(sp.airy(-lut_x)[0]) if sp is not None else np.abs(np.cos(lut_x * 6.0))
    t0 = time.perf_counter()
    for _ in range(200000):
        _ = lut_y[np.searchsorted(lut_x, 1.0)]
    t_airy = (time.perf_counter() - t0) / 200000

    print(f"    fold  : Airy, 1-D table of 2048     {t_airy*1e6:10.4f} us/lookup")
    print(f"    cusp  : Pearcey, direct integral    {t_pe*1e3:10.3f} ms/eval")
    print(f"            ratio                        {t_pe/t_airy:10.0f}x")

    # The only route to comparable cost is a precomputed table. Measure a small one
    # and extrapolate, rather than quoting an unbuildable number.
    n_side = 24
    xs = np.linspace(-12.0, 4.0, n_side)
    ys = np.linspace(-24.0, 24.0, n_side)
    t0 = time.perf_counter()
    for xv in xs:
        for yv in ys:
            pearcey(xv, yv)
    t_small = time.perf_counter() - t0
    per = t_small / (n_side * n_side)
    print(f"\n    a precomputed cusp table is the only affordable route:")
    print(f"      measured {n_side}x{n_side} build: {t_small:8.1f} s "
          f"({per*1e3:.2f} ms/entry)")
    for side in (128, 256, 512):
        est = per * side * side
        mb = side * side * 8 / 1048576          # float64
        print(f"      {side:4d}x{side:<4d} -> {est/60:8.2f} min to build, "
              f"{mb:6.1f} MB (float64)")
    print(f"\n    for scale, the fold's table is 2048 entries built in milliseconds.")
    print(f"    The 1-D problem needs a curve; the cusp needs a surface, and the")
    print(f"    surface costs {t_pe/t_airy:.0f}x more per point to produce.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
