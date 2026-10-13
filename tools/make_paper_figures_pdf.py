"""make_paper_figures_pdf.py -- the paper's figures as vector PDF.

Replaces the earlier PNG figures. Differences that matter for a submission to
Computer Graphics Forum:

  * vector PDF out, not raster PNG;
  * sized for the EG two-column grid (column 84 mm, full width 174 mm);
  * Figure 1 is a to-scale technical drawing -- dimension lines with arrowheads,
    a scale bar, the light path TRACED through the real geometry rather than
    drawn as decoration, and a marked fold band -- not a sketch with floating
    annotations;
  * every data axis carries units and states its normalisation explicitly, since
    "intensity" without a normalisation is the single easiest way to publish a
    meaningless comparison;
  * no alpha/transparency anywhere: the EG author guidelines warn that
    transparent pixels break PDF display and print.

Run:  <system python> tools/make_paper_figures_pdf.py
"""
import io
import json
import os
import sys

import matplotlib

# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle, FancyArrow

ROOT = _ROOT
OUT = f"{ROOT}/out"
FIG = f"{ROOT}/docs/paper/figures"
os.makedirs(FIG, exist_ok=True)
sys.path.insert(0, f"{ROOT}/tools")

MM = 1.0 / 25.4
COL = 84 * MM      # single column width (inches)
FULL = 174 * MM    # full text width (inches)

from paper_figs import palette, style

MM = style.MM
COL = style.COL_MM * MM      # single column width, inches
FULL = style.FULL_MM * MM    # full text width, inches

# The house style. No local rcParams: four producers each had their own copy and
# they had drifted apart. Grid stays on for this file because these are data plots
# whose values are read off the axis.
style.apply()
plt.rcParams.update({"axes.grid": True, "grid.color": "#d9d9d9",
                     "grid.linewidth": 0.35, "axes.axisbelow": True})

# scene constants -- identical to tools/verify_ray_map.py and the solver
R_OUT, R_IN, H_GLASS = 0.035, 0.0315, 0.090
WATER = 0.0594
SUN = np.array([0.80, 0.42, -0.43]); SUN /= np.linalg.norm(SUN)
N_WATER = 1.33468      # central channel, Daimon & Masumura 2007
N_GLASS = 1.52514      # central channel, Rubin 1985


# The three render channels. Chosen to separate on hue AND luminance AND dash, so
# the figures survive greyscale printing and the common red-green confusion: R and G
# differ in luminance, B is the darkest, and every series carries its own linestyle.
CH_COLOUR = {0: palette.CHANNEL[650], 1: palette.CHANNEL[550],
             2: palette.CHANNEL[450]}
CH_STYLE = {0: palette.CHANNEL_DASH[650], 1: palette.CHANNEL_DASH[550],
            2: palette.CHANNEL_DASH[450]}
CH_NAME = {0: "R 650 nm", 1: "G 550 nm", 2: "B 450 nm"}


def save(fig, name, note=""):
    """Fit inside the canvas, then assert the page is exactly the authored width.

    Figures used to be saved with a tight bounding box, which CROPPED them: a
    figure asked for at 174 mm came out at 142 mm and LaTeX then scaled it back,
    changing its type size and raster dpi. Authored size is now the contract.
    """
    p = f"{FIG}/{name}.pdf"
    want_mm = fig.get_size_inches()[0] * 25.4
    style.fit(fig)
    style.save(fig, p, width_mm=want_mm)
    print(f"  {name}.pdf  {note}")


def flatten_alpha(path):
    """Force every constant-alpha entry in the PDF to fully opaque.

    The EG author guidelines require that no figure contain transparent pixels,
    because transparent content breaks PDF display and print. Matplotlib emits an
    ExtGState with ca/CA values regardless of styling -- even a bare plot.pdf
    contains `/CA 0` -- and a legend frame or a default patch edge can leave
    fractional alpha behind. Nothing in these figures uses transparency for
    meaning (fills are hatched or greyscale instead), so every such value is
    rewritten to 1.

    The rewrite MUST be byte-length preserving. A PDF's cross-reference table
    stores absolute byte offsets, so substituting a shorter token silently
    corrupts every offset after it and the file stops loading in any viewer that
    honours the xref -- which is exactly what happened on the first attempt
    (the engine reported "Unable to load picture or PDF file" for a file that
    was 52 KiB and superficially well formed).
    """
    import re

    def repl(m):
        key, val = m.group(1), m.group(2).decode()
        new = ("1." + "0" * (len(val) - 2)) if "." in val else "1"
        assert len(new) == len(val), (val, new)
        return b"/" + key + b" " + new.encode()

    d = open(path, "rb").read()
    d2 = re.sub(rb"/(ca|CA) ([0-9]*\.?[0-9]+)", repl, d)
    if d2 != d:
        assert len(d2) == len(d), "alpha flatten changed file length"
        open(path, "wb").write(d2)
    after = sorted({float(m.group(2)) for m in
                    re.finditer(rb"/(ca|CA) ([0-9.]+)", open(path, "rb").read())})
    if after and after != [1.0]:
        print(f"    NOTE {os.path.basename(path)}: alpha values {after}")


def refract(d, n, eta):
    """Vector Snell. d is the incident unit direction, n the interface normal
    facing into the incident medium, eta = n1/n2."""
    ci = -float(np.dot(d, n))
    k = 1.0 - eta * eta * (1.0 - ci * ci)
    if k < 0:
        return None
    return eta * d + (eta * ci - np.sqrt(k)) * n


def trace_ray(y0):
    """Trace one ray down through air -> glass -> water -> glass -> receiver.

    y0 is the height of the ray's entry point on the outer wall. Returns the
    polyline and the landing x on the receiver, so the light path in Figure 1 is
    computed from the scene rather than sketched.
    """
    pts = []
    # start well above, travelling along SUN toward the cylinder
    ys = 0.30
    p = np.array([-SUN[0] / SUN[2] * (ys - y0), y0])
    pts.append((p[0], p[1]))
    d = np.array([SUN[0], SUN[2]])   # work in the x-z plane, y offset fixes the slab
    d = d / np.linalg.norm(d)

    def hit_cyl(p, d, r):
        # solve |p + t d| = r on the x axis
        a = float(np.dot(d, d)); b = 2 * float(np.dot(p, d)); c = float(np.dot(p, p)) - r * r
        disc = b * b - 4 * a * c
        if disc < 0:
            return None
        t = (-b - np.sqrt(disc)) / (2 * a)
        return t if t > 1e-6 else None

    def hit_z(p, d, z):
        return (z - p[1]) / d[1] if abs(d[1]) > 1e-12 else None

    # air -> glass (outer wall)
    t = hit_cyl(p, d, R_OUT)
    if t is None:
        return pts, None
    p = p + t * d
    pts.append(tuple(p))
    nrm = np.array([p[0], p[1]]) / np.linalg.norm(p)
    d = refract(d, nrm, 1.0 / N_GLASS)
    if d is None:
        return pts, None
    # glass -> water (inner wall)
    t = hit_cyl(p, d, R_IN)
    if t is None:
        return pts, None
    p = p + t * d
    pts.append(tuple(p))
    nrm = -np.array([p[0], p[1]]) / np.linalg.norm(p)
    d = refract(d, nrm, N_GLASS / N_WATER)
    if d is None:
        return pts, None
    # water surface (flat, at z = WATER)
    t = hit_z(p, d, WATER)
    if t is not None and t > 0:
        p = p + t * d
        pts.append(tuple(p))
        nrm = np.array([0.0, 1.0])
        d = refract(d, nrm, N_WATER / 1.0)
        if d is None:
            return pts, None
    # -> receiver
    t = hit_z(p, d, 0.0)
    if t is None:
        return pts, None
    p = p + t * d
    pts.append(tuple(p))
    return pts, p[0]


# ------------------------------------------------------------------- figure 1
# Figure 1 lives in tools/make_fig1_scene.py. Its earlier version here traced rays
# in the x-z plane rather than along the sun's azimuth, intersected the wall as a
# circle instead of a rectangle, and drew the fold band at a hardcoded 36-97 mm.
# Keeping a second renderer for the same file invited the bad one back, so it was
# deleted rather than left uncalled.


def decade_ticks(ax, which="x", values=None):
    """Label only the intended ticks on a log axis.

    Matplotlib labels the log MINOR ticks too, in scientific notation, so a
    frequency panel came out reading "5, 6 x 10^0, 10, 20, 3 x 10^1, 40". The
    minor ticks are ticks, not labels.
    """
    from matplotlib.ticker import FuncFormatter, NullFormatter, NullLocator
    axis = ax.xaxis if which == "x" else ax.yaxis
    axis.set_minor_locator(NullLocator())
    axis.set_minor_formatter(NullFormatter())
    # Matplotlib labels decades as $10^{n}$; mathtext draws the exponent at 0.7x,
    # so a 7pt axis produced 4.9pt superscripts. Plain decimals keep every glyph
    # at the axis size, and read better besides.
    axis.set_major_formatter(FuncFormatter(lambda v, _p: "%g" % v))
    if values is not None:
        axis.set_major_locator(plt.FixedLocator(values))
        axis.set_major_formatter(plt.FixedFormatter([f"{v:g}" for v in values]))


# ------------------------------------------------------------------- figure 2
def fig_fold_optics():
    """The ray map and its Jacobian: where the fold is and why it matters."""
    import verify_ray_map as V
    X, Y = V.trace(n_side=700)[:2]
    g = V.to_grid(X, Y)
    g = np.asarray(g, dtype=float)

    fig, axes = plt.subplots(1, 2, figsize=(FULL, FULL * 0.36),
                             gridspec_kw={"wspace": 0.40},
                             layout="constrained")
    im = axes[0].imshow(g ** 0.4, cmap="inferno",
                        extent=[-160, 160, -160, 160], origin="upper")
    axes[0].set_title("(a) brute-force ray density (independent trace)")
    axes[0].set_xlabel(r"$x$ (mm)"); axes[0].set_ylabel(r"$y$ (mm)")
    axes[0].grid(False)
    cb = fig.colorbar(im, ax=axes[0], fraction=0.046, pad=0.02)
    cb.set_label(r"counts, $\gamma=0.4$ for display", fontsize=7)

    prof = g[g.shape[0] // 2]
    axes[1].plot(np.linspace(-160, 160, prof.size), prof, color="black", lw=0.8)
    axes[1].set_title("(b) horizontal profile through the fold")
    axes[1].set_xlabel(r"$x$ (mm)")
    axes[1].set_ylabel("ray counts (unnormalised)")
    save(fig, "fig2_fold", "ray map and its profile")


# ------------------------------------------------------------------- figure 3
# Figure 3 lives in tools/fix_fig3_airy.py. Its version here carried a badly set
# integral in the panel title, a hardcoded "(Lemma 1)" inside a legend, and a
# computed curve made jagged by calling quad() once per abscissa on a slowly
# converging oscillatory integrand. Removed rather than left uncalled: two
# writers for one output file means the load order decides which is published.


# ---------------------------------------------------------------------------
# Local 16-bit PNG reader and artefact loader.
#
# These were imported from `make_paper_figures` until that tool was archived as
# superseded. A live tool must not depend on an archived one, so both are copied
# here along with the imports they need. Do not re-point these at the archive.
# ---------------------------------------------------------------------------
def read_png16(path):
    """Read a 16-bit RGB PNG as float, undoing the solver's /16 export scale."""
    import struct
    import zlib

    d = open(path, "rb").read()
    pos, idat = 8, b""
    w = h = 0
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


def _lum(path):
    from PIL import Image

    return np.asarray(Image.open(path).convert("L"), dtype=np.float32)


def load_all():
    """Ground truth, ours, SPPM and Cycles, all resampled onto one grid."""
    import sys as _sys
    from PIL import Image

    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import verify_ray_map as V

    gt = V.to_grid(*V.trace()[:2])
    H, W = gt.shape
    field = read_png16(f"{OUT}/caustic_wavy.png")
    ours = np.asarray(Image.fromarray(field.mean(axis=2).astype(np.float32),
                                     mode="F").resize((W, H), Image.BOX))
    d = ((np.load(f"{OUT}/npy/spmm_optics.npy").astype(np.float64) -
          np.load(f"{OUT}/npy/spmm_nooptics.npy").astype(np.float64)).mean(axis=2))[:, ::-1]
    sp = np.asarray(Image.fromarray(d.astype(np.float32), mode="F").resize((W, H), Image.BOX))
    cyc = np.clip(_lum(f"{OUT}/ortho_glass.png") - _lum(f"{OUT}/ortho_nocaustic.png"),
                  0, None)
    cyc = np.asarray(Image.fromarray(cyc.astype(np.float32), mode="F").resize((W, H), Image.BOX))
    return gt, ours, sp, cyc, field


# ------------------------------------------------------------------- figure 4
def fig_field():
    """Our baked field, with the per-channel profile."""
    try:
        field = read_png16(f"{OUT}/caustic_wavy.png")
    except Exception as e:
        print("  fig4 skipped:", e)
        return
    fig, axes = plt.subplots(1, 2, figsize=(FULL, FULL * 0.34))
    disp = np.clip(field / field.max(), 0, 1) ** (1 / 2.2)
    axes[0].imshow(disp, origin="upper")
    axes[0].set_title("(a) our baked field")
    axes[0].set_xlabel("grid $x$ (1024 px)"); axes[0].set_ylabel("grid $y$ (1024 px)")
    axes[0].grid(False)
    axes[0].text(0.02, 0.96, r"normalised to field max, $\gamma=2.2$",
                 transform=axes[0].transAxes, fontsize=6.5, va="top")
    for c, ch in enumerate("RGB"):
        axes[1].plot(field[:, :, c].mean(axis=0), color=CH_COLOUR[c], lw=0.9,
                     ls=CH_STYLE[c], label=CH_NAME[c])
    axes[1].set_title("(b) horizontal profile, per channel")
    axes[1].set_xlabel("grid $x$ (1024 px)")
    axes[1].set_ylabel(r"intensity, linear (cap $\times$ mean)")
    axes[1].legend(loc="upper right")
    save(fig, "fig4_field", "baked field and profile")


# ------------------------------------------------------------------- figure 5
def fig_quality():
    """Correlation against the independent ground truth, by tile size."""
    d = json.load(open(f"{ROOT}/docs/data/figure_data.json"))
    tiles = d["tiles_mm"]
    q = d["quality"]
    fig, ax = plt.subplots(figsize=(COL, COL * 0.72))
    marks = {"ours": ("o", "black", "ours"), "SPPM": ("s", "0.45", "SPPM"),
             "Cycles": ("^", "0.7", "Cycles")}
    for k, (m, c, lab) in marks.items():
        ax.plot(tiles, q[k], marker=m, color=c, ms=3.2, label=lab)
    ax.set_xscale("log")
    decade_ticks(ax, "x", tiles)
    ax.set_xlabel("tile size (mm)")
    ax.set_ylabel("Pearson $r$ vs independent trace")
    ax.set_ylim(0.35, 1.0)
    ax.legend(loc="lower right", frameon=False)
    ax.text(0.03, 0.94, "caustic = positive part;\nsame estimator for all",
            transform=ax.transAxes, fontsize=6.5, va="top", ha="left")
    save(fig, "fig5_quality", "quality vs trace")


# ------------------------------------------------------------------- figure 6
def fig_fourpanel():
    """The same caustic four ways."""
    try:
        gt, ours, sp, cyc, _ = load_all()
    except Exception as e:
        print("  fig6 skipped:", e)
        return
    fig, axes = plt.subplots(1, 4, figsize=(FULL, FULL * 0.35),
                             layout="constrained")
    for ax, img, t in zip(axes, (gt, ours, sp, cyc),
                          ("ground truth\n(brute-force trace)", "ours\n(wave-corrected)",
                           "PBRT-v4 SPPM", "Blender Cycles")):
        v = np.asarray(img, dtype=float)
        v = v / (v.max() if v.max() > 0 else 1)
        ax.imshow(np.clip(v, 0, 1) ** 0.45, cmap="inferno")
        ax.set_title(t, fontsize=7)
        ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
    fig.text(0.5, 0.05, "each panel normalised to its own maximum, $\\gamma=0.45$",
             ha="center", fontsize=6.5)
    save(fig, "fig6_fourpanel", "four-way comparison")


# ------------------------------------------------------------------- figure 7
def fig_cost():
    """Cost, log scale, with the wave term split out."""
    grids = [256, 512, 1024, 2048]
    geom = [7.00, 28.68, 108.25, 425.04]
    wave = [12.72, 49.81, 202.12, 781.75]
    t1 = [g + w for g, w in zip(geom, wave)]
    t8 = [16.46, 36.22, 117.82, 449.47]
    x = np.arange(len(grids))
    fig, ax = plt.subplots(figsize=(COL, COL * 0.72))
    ax.bar(x - 0.26, geom, 0.24, color="0.85", ec="black", lw=0.5, label="quadrature")
    ax.bar(x, wave, 0.24, color="0.45", ec="black", lw=0.5, label="Airy term")
    ax.bar(x + 0.26, t8, 0.24, color="black", ec="black", lw=0.5, label="total, 8 threads")
    ax.set_yscale("log")
    decade_ticks(ax, "y")
    ax.set_xticks(x); ax.set_xticklabels([f"{g}\u00b2" for g in grids])
    ax.set_xlabel("bake grid")
    ax.set_ylabel("time (ms), log scale")
    ax.legend(loc="upper left", frameon=False)
    save(fig, "fig7_cost", "bake cost, one thread + 8 threads")


# ------------------------------------------------------------------- figure 8
def fig_dispersion():
    """Edge radius per channel, both methods."""
    fig, ax = plt.subplots(figsize=(COL, COL * 0.72))
    ch = ["R\n650 nm", "G\n550 nm", "B\n450 nm"]
    ours = [107, 105, 102]
    sppm = [56, 54, 51]
    x = np.arange(3)
    # Channel identity is the x category, so colour the bars by channel and
    # separate the two methods by solid fill versus light hatch. Previously both
    # methods were grey and the channel only lived in the tick labels.
    from matplotlib.patches import Patch
    for i in x:
        ax.bar(i - 0.19, ours[i], 0.36, color=CH_COLOUR[i], ec="black", lw=0.5)
        # dashed edge rather than a hatch: a hatch is a pattern fill, which
        # disappears at small print sizes and is invisible to a stroke check.
        ax.bar(i + 0.19, sppm[i], 0.36, color="white", ec=CH_COLOUR[i], lw=1.0,
               ls="--")
    ax.legend(handles=[Patch(facecolor="0.55", edgecolor="black", label="ours, filled"),
                       Patch(facecolor="white", edgecolor="0.35", ls="--",
                             label="SPPM, dashed")],
              frameon=False, loc="lower center", ncol=2,
              bbox_to_anchor=(0.5, 1.005), columnspacing=1.8,
              handlelength=1.5, handletextpad=0.5, fontsize=7)
    for xi, v in zip(x - 0.19, ours):
        ax.text(xi, v + 2, str(v), ha="center", fontsize=6.5)
    for xi, v in zip(x + 0.19, sppm):
        ax.text(xi, v + 2, str(v), ha="center", fontsize=6.5)
    ax.set_xticks(x); ax.set_xticklabels(ch)
    ax.set_ylabel("edge radius (mm)")
    ax.set_ylim(0, 122)
    ax.text(0.02, 0.06, "red$-$blue split $+5.0$ mm in both",
            transform=ax.transAxes, fontsize=6.5)
    save(fig, "fig8_dispersion", "dispersion ordering")


# ------------------------------------------------------------------- figure 9
def fig_efficiency():
    """RMSE vs splat budget: the regime where we lose is visible."""
    splats = [65000, 262000, 1000000, 4200000, 16800000]
    mc = [0.12294, 0.07838, 0.06445, 0.06101, 0.06013]
    o_s = [65000, 262000, 1000000]
    o_r = [0.13738, 0.10455, 0.03914]
    fig, ax = plt.subplots(figsize=(COL, COL * 0.74))
    ax.plot(splats, mc, marker="s", color="0.45", ms=3.2,
            label="geometric MC (M samples/cell)")
    ax.plot(o_s, o_r, marker="o", color="black", ms=3.2, label="ours (1 pass)")
    ax.axhline(0.06013, color="0.6", lw=0.6, ls="--")
    ax.annotate("MC error floor $0.06013$", xy=(2e6, 0.06013), xytext=(2.2e5, 0.047),
                fontsize=6.5, arrowprops=dict(arrowstyle="->", lw=0.5))
    ax.annotate("we lose\nbelow here", xy=(262000, 0.07838), xytext=(4.2e4, 0.098),
                fontsize=6.5, arrowprops=dict(arrowstyle="->", lw=0.5))
    ax.set_xscale("log")
    decade_ticks(ax, "x")
    ax.set_xlabel("splats (log scale)")
    ax.set_ylabel("RMSE vs converged wave reference")
    ax.legend(frameon=False, loc="upper right")
    save(fig, "fig9_efficiency", "cost vs accuracy")


# ------------------------------------------------------------------- figure 10
def fig_ripple():
    """The animating caustic, three methods, three phases."""
    srcs = [("ours", "ours"), ("cycles", "Cycles"), ("spmm", "SPPM")]
    phases = [0, 24, 48]
    fig, axes = plt.subplots(3, 3, figsize=(FULL, FULL * 0.62))
    ok = True
    for i, (key, lab) in enumerate(srcs):
        for j, f in enumerate(phases):
            p = f"{OUT}/gif_src/{key}/f{f:04d}.png"
            ax = axes[i][j]
            if not os.path.exists(p):
                ok = False
                ax.text(0.5, 0.5, "missing", ha="center", fontsize=7)
                ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
                continue
            from PIL import Image
            a = np.asarray(Image.open(p).convert("RGB")).astype(float) / 255.0
            ax.imshow(a ** 1.0, vmin=0, vmax=1)
            ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
            if j == 0:
                ax.set_ylabel(lab, fontsize=7)
            if i == 0:
                ax.set_title(f"phase {f}/72", fontsize=7)
    if ok:
        fig.text(0.5, 0.005, "shared camera, physical fringe width, "
                             "subject exposure matched across rows",
                 ha="center", fontsize=6.5)
        save(fig, "fig10_ripple", "ripple, three methods")
    else:
        plt.close(fig)
        print("  fig10 skipped: ripple frames not found")


def main():
    print(f"writing vector PDFs to {FIG}")
    fig_fold_optics()
    fig_field()
    fig_quality()
    fig_fourpanel()
    fig_cost()
    fig_dispersion()
    fig_efficiency()
    fig_ripple()
    print("done")


if __name__ == "__main__":
    main()
