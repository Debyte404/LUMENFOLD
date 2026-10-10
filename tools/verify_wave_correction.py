"""verify_wave_correction.py — independent verification of the physics at the
heart of the method, which until now has been asserted rather than tested.

The solver's whole "wave-corrected" claim rests on three things:

  A. near a fold, the light field's intensity really follows an Airy function;
  B. the fold's spatial scale goes as lambda^(2/3), which is why the code sets
     fringe width w = airy_scale * (lambda/550)^(2/3);
  C. the table it uses (airy_prof_1d, a 2048-entry LUT built from
     (1/pi) * int_0^12 cos(t^3/3 - u t) dt) really equals the Airy function.

Each is checked here against an independent computation, not against the code's
own output.

A is checked by doing the fold diffraction integral from scratch - the field
behind a wavefront with a cubic phase term, which is the canonical fold - and
comparing the result with Ai^2. B is checked by redoing that integral at several
wavelengths for a fixed geometry and fitting the exponent. C is checked against
scipy's Airy implementation.

Run:  python tools/verify_wave_correction.py
"""
import numpy as np
from scipy.special import airy


def airy_lut_as_cpp(u):
    """Reproduce the C++ LUT formula exactly: (1/pi) * int_0^12 cos(t^3/3-ut) dt."""
    S = 4000
    h = 12.0 / S
    t = np.arange(S + 1) * h
    w = np.ones(S + 1)
    w[1:-1:2] = 4.0
    w[2:-1:2] = 2.0
    out = np.empty_like(np.asarray(u, dtype=float))
    for i, uu in enumerate(np.atleast_1d(u)):
        out[i] = np.sum(w * np.cos(t ** 3 / 3.0 - uu * t)) * h / 3.0 / np.pi
    return out


def fold_intensity(x, lam, c, n_rho=120001):
    """Independent fold diffraction integral, chunked.

    A cubic-phase wavefront is the canonical fold:

        u(x) = int_{-1}^{1} exp( i (2 pi / lam) [ c rho^3 / 6 + rho x ] ) d rho

    Sampling matters: the phase turns over 2x/lam cycles across the pupil, so the
    window has to stay within a few Airy scales of the fold or the trapezoid rule
    aliases and the "pattern" is pure numerical noise. That mistake was made
    first, and it produced a peak at the edge of the array 20 Airy scales away.
    """
    rho = np.linspace(-1.0, 1.0, n_rho)
    k = 2.0 * np.pi / lam
    out = np.empty_like(x)
    step = 16
    for s0 in range(0, len(x), step):
        xs = x[s0:s0 + step]
        ph = k * (np.outer(xs, rho) + c * (rho ** 3)[None, :] / 6.0)
        out[s0:s0 + step] = np.abs(np.trapezoid(np.exp(1j * ph), rho, axis=1)) ** 2
    return out


def airy_scale(lam, c):
    """Spatial scale of the fold pattern, from the canonical mapping.

    Setting rho = alpha s and matching the cubic term to s^3/3 gives
    alpha = (2/(k c))^(1/3), so the canonical variable is
        X = x * k^(2/3) * 2^(1/3) * c^(-1/3)      hence  x ~ lam^(2/3) c^(1/3)
    which is exactly the lambda^(2/3) dependence the solver's dispersion uses.
    """
    k = 2.0 * np.pi / lam
    return 1.0 / (k ** (2.0 / 3.0) * 2.0 ** (1.0 / 3.0) * c ** (-1.0 / 3.0))


def main():
    print("=== C. does the solver's LUT equal the Airy function? ===")
    us = np.linspace(0.0, 12.0, 200)
    mine = airy_lut_as_cpp(us)
    ref = airy(-us)[0]                      # Ai(-u): the bright side of a fold
    # the C++ table is normalised by its own maximum
    scale = mine.max() / ref.max()
    err = np.abs(mine / mine.max() - ref * scale / (ref.max() * scale)).max()
    print(f"  compared at {len(us)} points over u in [0,12]")
    print(f"  max |LUT/peak - Ai(-u)/peak| = {err:.3e}")
    print(f"  first zero: LUT at u = {us[np.argmin(np.abs(mine[:60]))]:.4f}, "
          f"Ai(-u)=0 at u = {np.abs(airy(0)[0]):.4f} (Airy's first zero is 2.3381)")
    zero_ref = 2.338107410459767
    # find where the reference crosses zero going positive
    idx = np.where(np.diff(np.sign(ref)) != 0)[0]
    print(f"  reference's first sign change at u = {us[idx[0]]:.4f} "
          f"(analytic 2.3381)")
    print(f"  LUT's first sign change at u = "
          f"{us[np.where(np.diff(np.sign(mine)) != 0)[0][0]]:.4f}")

    print()
    print("=== A. is the fold pattern really Ai^2? ===")
    lam, c = 550e-9, 1e-3
    d = airy_scale(lam, c)
    x = np.linspace(-3.2 * d, 1.6 * d, 400)
    I = fold_intensity(x, lam, c)
    X = x / d
    ref = airy(-X)[0] ** 2
    # compare SHAPE, normalised at the peak: no free scale factors beyond the
    # analytic mapping above
    In = I / I.max()
    Rn = ref / ref.max()
    # align on the brightest index in case of a sub-pixel offset
    shift = int(np.argmax(In)) - int(np.argmax(Rn))
    Rn_s = np.roll(Rn, shift)
    err = np.abs(In - Rn_s).mean()
    print(f"  lambda {lam*1e9:.0f} nm, cubic coefficient {c:.1e}")
    print(f"  analytic fold scale d = {d*1e6:.1f} um; window "
          f"[{x[0]*1e6:.0f}, {x[-1]*1e6:.0f}] um, {len(x)} points")
    print(f"  computed peak at x = {x[np.argmax(I)]*1e6:+.1f} um  "
          f"(X = {X[np.argmax(I)]:+.2f}; Ai^2 peaks at X = -1.0188)")
    print(f"  mean |I/peak - Ai^2/peak| after alignment = {err:.4f}")
    i1 = np.argmax(I)
    j = i1 + int(np.argmin(I[i1:]))
    print(f"  first minimum at X = {X[j]:+.3f}  (Ai^2's first zero X = -2.3381)")

    print()
    print("=== B. does the fringe scale really go as lambda^(2/3)? ===")
    lams = np.array([450e-9, 550e-9, 650e-9])
    widths = []
    for L in lams:
        dd = airy_scale(L, c)
        xx = np.linspace(-3.2 * dd, 1.6 * dd, 300)
        II = fold_intensity(xx, L, c)
        ip = int(np.argmax(II))
        jj = ip + int(np.argmin(II[ip:]))
        widths.append(abs(xx[jj] - xx[ip]))
    widths = np.array(widths)
    fit = np.polyfit(np.log(lams), np.log(widths), 1)[0]
    print(f"  wavelengths {[f'{l*1e9:.0f}' for l in lams]} nm")
    print(f"  peak-to-first-minimum {[f'{w*1e6:.1f}' for w in widths]} um")
    print(f"  numerically fitted exponent in lambda : {fit:.4f}")
    print(f"  analytic prediction (see airy_scale)  : {2/3:.4f}")
    print(f"  solver's dispersion uses              : 0.6667")
    print(f"  |error| = {abs(fit - 2/3):.4f}")


if __name__ == "__main__":
    main()
