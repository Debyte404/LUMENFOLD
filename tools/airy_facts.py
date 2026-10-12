"""airy_facts.py -- the numerical Airy constants quoted in the paper.

The paper asserts several numbers about the Airy function and its intensity, and
the reproduction list names this tool as their source. Computing them here rather
than quoting a printed table means every constant in the text and in
Table (Airy quantities) has a command behind it.

What it establishes:

  * the position and height of the peak of |Ai(-u)|^2, which is the normaliser
    used by the band profile;
  * that |Ai(-u)|^2 is NOT integrable on the real line: its tail falls off as
    u^-1/2, so the integral over a truncated band grows like pi^-1 sqrt(L). This
    is the lemma that rules out a constant normalisation and forces the
    correction to be a discrete band ratio;
  * the convergent half-line integral, for contrast.

Run:  python tools/airy_facts.py
"""
import numpy as np
from scipy.integrate import quad
from scipy.optimize import minimize_scalar
from scipy.special import airy


def peak():
    r = minimize_scalar(lambda t: -airy(-t)[0] ** 2, bracket=(0.8, 1.0, 1.2))
    return float(r.x), float(-r.fun)


def truncated(L, hi=80.0):
    """Integral of Ai(x)^2 from -L to hi, by cumulative trapezoid on a fine grid.

    Load-bearing detail: calling quad() separately for each L on a slowly
    decaying oscillatory integrand makes each call hit its subdivision limit and
    contribute its own error, and the resulting curve is visibly jagged. One
    integration on a fine grid, read off cumulatively, is smooth by construction.
    """
    x = np.arange(-float(L), hi, 0.005)
    a = airy(x)[0] ** 2
    return float(np.sum(0.5 * (a[1:] + a[:-1]) * np.diff(x)))


def main():
    pu, ph = peak()
    half = quad(lambda x: airy(x)[0] ** 2, 0, 80, limit=400)[0]

    print("Airy quantities used by the implementation")
    print("-" * 52)
    print(f"  argmax_u |Ai(-u)|^2          {pu:.8f}")
    print(f"  max_u    |Ai(-u)|^2          {ph:.6f}   <- the profile normaliser")
    print(f"  int_0^inf Ai(u)^2 du         {half:.7f}  (convergent)")
    print()
    print("Non-integrability of |Ai(-u)|^2  (the tail decays as u^-1/2, so")
    print("the integral over a truncated band grows like pi^-1 sqrt(L))")
    print("-" * 52)
    print(f"  {'L':>8} {'computed':>10} {'pi^-1 sqrt(L)':>14} {'ratio':>8}")
    for L in (100, 500, 1000, 2000, 5000):
        c = truncated(L)
        p = np.sqrt(L) / np.pi
        print(f"  {L:>8} {c:>10.4f} {p:>14.4f} {c/p:>8.3f}")
    print()
    print("  the ratio tends to a constant, so the exponent is 1/2 and the")
    print("  integral diverges: no constant Z makes Z^-1|Ai|^2 a density.")


if __name__ == "__main__":
    main()
