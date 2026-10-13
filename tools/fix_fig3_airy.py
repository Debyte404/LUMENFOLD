"""fix_fig3_airy.py -- three defects in the Airy figure, all visible on the page.

  1. The panel (b) title carried `$\\int_{-L}^{80}$` and matplotlib's mathtext set
     the limits badly, so the integral sign printed with its bounds collapsed onto
     the glyph. The integral is moved to the axis label, where the same
     expression has room to set.
  2. The legend hardcoded "(Lemma 1)". LaTeX owns that number and it is not 1 --
     the figure was asserting a cross-reference it cannot know. The legend now
     says "predicted", which is true whatever the numbering is.
  3. The computed curve was jagged because `quad` was called 300 times on a
     slowly-converging oscillatory integrand, each call reaching its subdivision
     limit and contributing its own error. Integrating ONCE on a fine cumulative
     grid and reading the curve off it removes the artefact by construction
     instead of tuning an integrator until the noise looks small.
"""
import re
import sys

import numpy as np
from scipy.special import airy


# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

FIG = _ROOT + "/docs/paper/figures"


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from paper_figs import palette, style
    style.apply()

    MM = 1.0 / 25.4
    FULL = style.FULL_MM * style.MM

    u = np.linspace(0, 8, 2000)
    I = airy(-u)[0] ** 2
    peak_u, peak_h = 1.01879297, 0.286928

    # cumulative integral on a fine grid: one integration, no per-point solver error
    x = np.arange(-5000.0, 80.0, 0.005)
    ai2 = airy(x)[0] ** 2
    cum = np.concatenate([[0.0], np.cumsum(0.5 * (ai2[1:] + ai2[:-1]) * np.diff(x))])
    total = cum[-1]

    L = np.linspace(1, 5000, 400)
    idx = np.searchsorted(x, -L)
    vals = total - cum[idx]
    pred = np.sqrt(L) / np.pi

    # the asymptotic mean is (2 pi sqrt(u))^-1, so the integral carries a constant
    # offset; fit only the constant, never the exponent
    const = float(np.mean(vals - pred))
    print(f"fitted constant offset {const:.4f}  (exponent taken as 1/2, not fitted)")

    fig, axes = plt.subplots(1, 2, figsize=(FULL, FULL * 0.33))

    axes[0].plot(u, I, color="black", lw=0.9)
    axes[0].plot([peak_u], [peak_h], "o", ms=2.8, color="black", zorder=5)
    axes[0].annotate(r"peak at $X = 1.0188$, beside the fold",
                     xy=(peak_u, peak_h), xytext=(2.5, 0.255), fontsize=7,
                     arrowprops=dict(arrowstyle="->", lw=0.6, color="black"))
    axes[0].axvline(0, color="0.65", lw=0.5, ls=":")
    axes[0].set_title(r"(a) fold intensity $|\mathrm{Ai}(-u)|^{2}$")
    axes[0].set_xlabel(r"$u$ (canonical fold coordinate, dimensionless)")
    axes[0].set_ylabel(r"$|\mathrm{Ai}(-u)|^{2}$")

    # the integral lives in the axis label, where mathtext has room to set the bounds
    axes[1].plot(L, vals, color="black", lw=0.9, label="computed")
    axes[1].plot(L, pred + const, color="0.45", lw=0.9, ls="--",
                 label=r"$\pi^{-1}\sqrt{L}$  (predicted)")
    axes[1].set_title(r"(b) the normalising integral does not converge")
    axes[1].set_xlabel(r"truncation $L$:    "
                       r"$\int_{-L}^{\,80} |\mathrm{Ai}(x)|^{2}\,\mathrm{d}x$")
    axes[1].set_ylabel("integral (dimensionless)")
    axes[1].legend(loc="upper left", frameon=True, framealpha=1.0, edgecolor="black",
                   fancybox=False)

    p = f"{FIG}/fig3_airy.pdf"
    style.fit(fig)
    style.save(fig, p, width_mm=style.FULL_MM)
    plt.close(fig)

    # byte-length-preserving alpha flatten (a PDF xref stores absolute offsets)
    d0 = open(p, "rb").read()

    def repl(m):
        key, val = m.group(1), m.group(2).decode()
        new = ("1." + "0" * (len(val) - 2)) if "." in val else "1"
        return b"/" + key + b" " + new.encode()

    d1 = re.sub(rb"/(ca|CA) ([0-9]*\.?[0-9]+)", repl, d0)
    if len(d1) == len(d0):
        open(p, "wb").write(d1)
    print(f"wrote {p}")


if __name__ == "__main__":
    sys.exit(main())
