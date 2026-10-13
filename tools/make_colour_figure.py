"""make_colour_figure.py -- the colour figure: caustic colour, fringe colour, and
where each comes from.

Reads docs/data/colour_results.json, which tools/colour_study.py writes, so the
figure and the report can never disagree about a number.

Follows the same submission rules as the paper's other figures: vector PDF, sized
for the EG grid (full width 174 mm), units on every axis, and no alpha/transparency
anywhere (the EG guidelines warn transparent content breaks PDF display and print).
The colour strips are drawn as runs of thin vector rectangles rather than an
imshow, which would rasterise.
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                        # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
OUT = _os.path.join(_ROOT, "docs", "paper", "figures")

MM = 1.0 / 25.4

# Match the paper's other figures. Micro is written as the literal character rather
# than $\mu$: mathtext draws it but emits a glyph that does not round-trip as text
# in the PDF, so the axis label extracts as "distance ... ( m)" and a reader cannot
# tell what the unit is.
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Nimbus Roman", "DejaVu Serif"],
    "font.size": 8,
    "axes.labelsize": 8,
    "axes.titlesize": 8,
    "legend.fontsize": 7,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "axes.linewidth": 0.6,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "pdf.fonttype": 42,
})

STRIP_N = 260          # vector segments per colour band; 640 made a 112 KiB PDF


def srgb(x):
    """Linear -> display, so a strip is not drawn from linear values."""
    x = np.clip(np.asarray(x, float), 0.0, None)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * x ** (1 / 2.4) - 0.055)


def strip(ax, y, h, x, rgb, xlim, nseg=260):
    """One horizontal colour band, drawn as vector rectangles."""
    # Resample onto a coarse grid: every source sample as its own rectangle made a
    # 112 KiB PDF, since the band is smooth and most rectangles are the same colour.
    idx = np.linspace(0, len(x) - 1, min(nseg, len(x))).astype(int)
    x = x[idx]
    rgb = rgb[:, idx]
    n = len(x)
    for i in range(n - 1):
        c = rgb[:, i]
        m = c.max()
        c = c / m if m > 0 else c
        ax.add_patch(Rectangle((x[i], y), x[i + 1] - x[i], h, linewidth=0,
                               facecolor=tuple(np.clip(srgb(c), 0, 1)),
                               edgecolor="none"))
    ax.plot([xlim[0], xlim[1]], [y, y], color="none")


def main():
    with open(_os.path.join(_ROOT, "docs", "data", "colour_results.json"),
              encoding="utf-8") as fh:
        R = json.load(fh)

    fig = plt.figure(figsize=(174 * MM / 1.0, 118 * MM))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.15],
                          hspace=0.55, wspace=0.28,
                          left=0.075, right=0.985, top=0.93, bottom=0.10)

    # ---- (a) the mechanism: channel peaks at different positions ----------
    ax = fig.add_subplot(gs[0, 0])
    f = R["fringes"]["clear|flat"]
    x = np.array(f["x_um"])
    rgb = np.array(f["rgb"])
    for i, (c, name) in enumerate(zip(("#d62728", "#2ca02c", "#1f77b4"),
                                      ("650 nm", "550 nm", "450 nm"))):
        v = rgb[i] / rgb[i].max()
        ax.plot(x, v, color=c, lw=1.1, label=name)
        k = int(np.argmax(v))
        ax.plot([x[k]], [v[k]], "o", color=c, ms=3.5)
    ax.set_xlim(x.min(), x.max())
    ax.set_ylim(0, 1.08)
    ax.set_xlabel("distance across the fold ($\\mu$m)", fontsize=7)
    ax.set_ylabel("$|\\mathrm{Ai}|^2$ / peak", fontsize=7)
    ax.set_title("(a) the three channels peak in different places",
                 fontsize=7.5)
    ax.legend(fontsize=6, frameon=False, ncol=3, loc="upper right")
    ax.tick_params(labelsize=6.5)
    sc = [R["airy_scales_um"][i] for i in (0, 1, 2)]
    ax.text(0.02, 0.62,
            "Airy scale:  %.2f / %.2f / %.2f $\\mu$m\n"
            "ratio $(\\lambda/550)^{2/3}$:  %.3f / 1.000 / %.3f"
            % (sc[0], sc[1], sc[2],
               (650 / 550) ** (2 / 3), (450 / 550) ** (2 / 3)),
            transform=ax.transAxes, fontsize=6.2, va="top")

    # ---- (b) caustic colour swatches --------------------------------------
    ax = fig.add_subplot(gs[0, 1])
    combos = [("clear", "clear"), ("cobalt", "clear"), ("amber", "clear"),
              ("clear", "copper"), ("clear", "tea")]
    ills = ["flat", "solar", "warm", "cool"]
    ax.set_xlim(0, len(ills))
    ax.set_ylim(0, len(combos))
    for r, (g, w) in enumerate(combos):
        for c, ill in enumerate(ills):
            e = R["caustic"].get(f"{g}|{w}|{ill}")
            if not e:
                continue
            v = srgb(np.array(e["norm"]) / max(max(e["norm"]), 1e-9))
            ax.add_patch(Rectangle((c, len(combos) - 1 - r), 1, 1, linewidth=0.4,
                                   edgecolor="white", facecolor=tuple(np.clip(v, 0, 1))))
    ax.set_xticks(np.arange(len(ills)) + 0.5)
    ax.set_xticklabels(["equal\nenergy", "solar\n5778 K", "warm\n3400 K", "cool\n10 000 K"],
                       fontsize=6)
    ax.set_yticks(np.arange(len(combos)) + 0.5)
    ax.set_yticklabels([f"{g} glass\n{w} water" for g, w in combos][::-1], fontsize=5.6)
    ax.set_title("(b) colour of the caustic core", fontsize=7.5)
    ax.tick_params(length=0)

    # ---- (c) colour across the band, per medium and source ----------------
    ax = fig.add_subplot(gs[1, :])
    rows = [("clear|flat", "clear, equal energy"),
            ("clear|solar", "clear, solar"),
            ("clear|warm", "clear, warm sun"),
            ("cobalt|flat", "cobalt glass"),
            ("clear|copper", "copper water"),
            ("clear|tea", "tea water")]
    xlim = None
    h = 1.0
    for i, (k, label) in enumerate(rows):
        e = R["fringes"].get(k)
        if not e:
            continue
        xx = np.array(e["x_um"])
        rr = np.array(e["rgb"])
        m = rr.max()
        rr = rr / m if m > 0 else rr
        y = len(rows) - 1 - i
        strip(ax, y, h * 0.72, xx, rr, (xx.min(), xx.max()))
        xlim = (xx.min(), xx.max())
        ax.text(xx.min() + 0.01 * (xx.max() - xx.min()), y + h * 0.40,
                label, fontsize=6.4, va="center", ha="left", color="white")
    ax.set_xlim(*xlim)
    ax.set_ylim(-0.2, len(rows))
    ax.set_yticks([])
    ax.set_xlabel("distance across the fold band ($\\mu$m)", fontsize=7)
    ax.set_title("(c) colour down the band: the fringes themselves are coloured, "
                 "and the medium decides which survive", fontsize=7.5)
    ax.tick_params(labelsize=6.5)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)

    p = _os.path.join(OUT, "fig11_colour.pdf")
    fig.savefig(p, format="pdf")
    plt.close(fig)
    print(f"wrote {p}  ({os.path.getsize(p)/1024:.1f} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
