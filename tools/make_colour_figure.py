"""make_colour_figure.py -- the colour figure: caustic colour, fringe colour, the
full medium x source factorial, and the rotating-source experiment.

Reads docs/data/colour_results.json (written by tools/colour_study.py) and the
shipped orbit GIF, so the figure cannot disagree with the artefacts it shows.

Layout fixes over the first version, all of them things a reader trips over:

  * the annotation in (a) sat on top of the curves. It now goes in an opaque white
    box in the empty decaying tail, where no curve reaches.
  * the row labels in the swatch grid wrapped onto two lines and collided. The grid
    is now full width with the labels in their own gutter, and the media are
    labelled "glass/water" on one line.
  * the band labels in (c) were drawn ON the colour strips, so white text vanished
    on the bright end. They are now y-tick labels in a gutter, off the colour.
  * the source sweep GIF looped with a 20x jump; see tools/colour_experiments.py.

Submission rules as for the paper's other figures: vector where the content is
vector, sized for the EG grid, units on every axis, and no alpha/transparency
anywhere (the EG guidelines warn transparent content breaks PDF display and print).
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
MEDIA = _os.path.join(_ROOT, "docs", "media")

MM = 1.0 / 25.4
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Nimbus Roman", "DejaVu Serif"],
    "font.size": 7.5,
    "axes.labelsize": 7.5,
    "axes.titlesize": 7.5,
    "legend.fontsize": 6.5,
    "xtick.labelsize": 6.5,
    "ytick.labelsize": 6.5,
    "axes.linewidth": 0.6,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "pdf.fonttype": 42,
    # Raster panels need explicit resolution: the rcParam default is 100 dpi,
    # which is where the orbit strip embedded at 98 dpi came from.
    "figure.dpi": 400,
    "savefig.dpi": 400,
})

STRIP_N = 200          # vector segments per band; the bands are smooth


def srgb(x):
    x = np.clip(np.asarray(x, float), 0.0, None)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * x ** (1 / 2.4) - 0.055)


def strip(ax, y, h, x, rgb, nseg=STRIP_N):
    """One horizontal colour band, drawn as vector rectangles."""
    idx = np.linspace(0, len(x) - 1, min(nseg, len(x))).astype(int)
    x, rgb = x[idx], rgb[:, idx]
    for i in range(len(x) - 1):
        c = rgb[:, i]
        m = c.max()
        c = c / m if m > 0 else c
        ax.add_patch(Rectangle((x[i], y), x[i + 1] - x[i], h, linewidth=0,
                               facecolor=tuple(np.clip(srgb(c), 0, 1)),
                               edgecolor="none"))


def main():
    with open(_os.path.join(_ROOT, "docs", "data", "colour_results.json"),
              encoding="utf-8") as fh:
        R = json.load(fh)

    fig = plt.figure(figsize=(174 * MM, 196 * MM))
    gs = fig.add_gridspec(4, 2, height_ratios=[1.00, 0.55, 1.30, 0.66],
                          hspace=0.95, wspace=0.30,
                          left=0.115, right=0.985, top=0.955, bottom=0.055)

    # ---- (a) the mechanism ------------------------------------------------
    ax = fig.add_subplot(gs[0, 0])
    f = R["fringes"]["clear|flat"]
    x = np.array(f["x_um"])
    rgb = np.array(f["rgb"])
    # hue AND dash: R, G and B cannot all be far apart in luminance while still
    # reading as red, green and blue, so the pattern carries greyscale separation.
    for i, (c, name, lsty) in enumerate(zip(("#c62828", "#2e7d32", "#1565c0"),
                                            ("650 nm", "550 nm", "450 nm"),
                                            ("-", "--", ":"))):
        v = rgb[i] / rgb[i].max()
        ax.plot(x, v, color=c, lw=1.2, ls=lsty, label=name)
        k = int(np.argmax(v))
        ax.plot([x[k]], [v[k]], "o", color=c, ms=4, markeredgecolor="white",
                markeredgewidth=0.5)
    ax.set_xlim(x.min(), x.max())
    ax.set_ylim(0, 1.22)
    ax.set_xlabel("distance across the fold (µm)")
    ax.set_ylabel("$|\\mathrm{Ai}|^2$ / peak")
    ax.set_title("(a) the channels peak in different places", pad=4)
    ax.legend(frameon=False, ncol=3, loc="upper center",
              bbox_to_anchor=(0.5, 1.02), handlelength=1.2, columnspacing=1.0)
    ax.tick_params(labelsize=6.5)
    # Opaque white box in the decaying tail (x > 0), which no curve occupies --
    # the first version put this text straight across the fringes.
    ax.text(0.97, 0.44,
            "Airy scale  %.2f / %.2f / %.2f µm\n"
            "ratio $(\\lambda/550)^{2/3}$\n   %.3f / 1.000 / %.3f"
            % (R["airy_scales_um"][0], R["airy_scales_um"][1], R["airy_scales_um"][2],
               (650 / 550) ** (2 / 3), (450 / 550) ** (2 / 3)),
            transform=ax.transAxes, ha="right", va="center", fontsize=6.2,
            linespacing=1.5,
            bbox=dict(facecolor="white", edgecolor="0.75", linewidth=0.5,
                      boxstyle="round,pad=0.35"))

    # ---- (b) colour down the band, labels OFF the colour ------------------
    ax = fig.add_subplot(gs[0, 1])
    rows = [("clear|flat", "clear, equal energy"),
            ("clear|solar", "clear, solar"),
            ("clear|warm", "clear, warm sun"),
            ("cobalt|flat", "cobalt glass"),
            ("clear|copper", "copper water"),
            ("clear|tea", "tea water")]
    keep = [(k, lab) for k, lab in rows if k in R["fringes"]]
    for i, (k, lab) in enumerate(keep):
        e = R["fringes"][k]
        xx = np.array(e["x_um"])
        rr = np.array(e["rgb"])
        rr = rr / rr.max()
        strip(ax, len(keep) - 1 - i, 0.72, xx, rr)
    ax.set_xlim(xx.min(), xx.max())
    ax.set_ylim(-0.4, len(keep) - 0.2)
    ax.set_yticks([len(keep) - 1 - i + 0.36 for i in range(len(keep))])
    ax.set_yticklabels([lab for _, lab in keep], fontsize=6.3)
    ax.tick_params(axis="y", length=0)
    ax.set_xlabel("distance across the fold band (µm)")
    ax.set_title("(b) colour down the band", pad=4)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)

    # ---- (c) the full factorial ------------------------------------------
    ax = fig.add_subplot(gs[1:3, :])
    ions = ["flat", "solar", "warm", "cool"]
    labels = ["equal\nenergy", "solar\n5778 K", "warm\n3400 K", "cool\n10 000 K"]
    media = []
    for g in ("clear", "cobalt", "amber", "green"):
        for w in ("clear", "faint", "copper", "tea", "ink"):
            media.append((g, w))
    for r, (g, w) in enumerate(media):
        for c, ill in enumerate(ions):
            e = R["caustic"].get(f"{g}|{w}|{ill}")
            if not e:
                continue
            v = srgb(np.array(e["norm"]) / max(max(e["norm"]), 1e-9))
            y = len(media) - 1 - r
            ax.add_patch(Rectangle((c, y), 1, 0.92, linewidth=0.4,
                                   edgecolor="white", facecolor=tuple(np.clip(v, 0, 1))))
    ax.set_xlim(0, len(ions))
    ax.set_ylim(-0.6, len(media) - 0.1)
    ax.set_xticks(np.arange(len(ions)) + 0.5)
    ax.set_xticklabels(labels, fontsize=6.3)
    ax.set_yticks([len(media) - 1 - r + 0.46 for r in range(len(media))])
    ax.set_yticklabels([f"{g} / {w}" for g, w in media], fontsize=5.8)
    ax.tick_params(length=0)
    ax.set_title("(c) all %d combinations: %d glasses x %d waters x %d sources"
                 % (len(media) * len(ions), 4, 5, 4), pad=3)

    # ---- (d) fixed camera, rotating sun -----------------------------------
    ax = fig.add_subplot(gs[3, :])
    gif = _os.path.join(MEDIA, "colour_sun_orbit.gif")
    if _os.path.exists(gif):
        from PIL import Image
        im = Image.open(gif)
        n = im.n_frames
        picks = np.linspace(0, n - 1, 6).astype(int)
        for j, k in enumerate(picks):
            im.seek(int(k))
            # downscale in PIL, not matplotlib: imshow scaling would rasterise at
            # panel resolution anyway and this way the aspect is controlled here
            t = im.convert("RGB").resize((420, 262), Image.LANCZOS)
            ax.imshow(np.asarray(t), extent=[j, j + 1, 0, 1], aspect="auto",
                      interpolation="bilinear")
            ax.text(j + 0.5, -0.13, "%d°" % int(round(360.0 * k / n)),
                    ha="center", fontsize=6.2)
        ax.set_xlim(0, len(picks))
        ax.set_ylim(-0.28, 1)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title("(d) camera fixed, sun rotated about the glass: the caustic "
                     "orbits, the frame does not", pad=4)
        for s in ("top", "right", "left", "bottom"):
            ax.spines[s].set_visible(False)

    p = _os.path.join(OUT, "fig11_colour.pdf")
    fig.savefig(p, format="pdf")
    plt.close(fig)
    print(f"wrote {p}  ({os.path.getsize(p)/1024:.1f} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
