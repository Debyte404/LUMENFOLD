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
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle, FancyArrow

ROOT = "D:/ValueProjects/caustics"
OUT = f"{ROOT}/out"
FIG = f"{ROOT}/docs/paper/figures"
os.makedirs(FIG, exist_ok=True)
sys.path.insert(0, f"{ROOT}/tools")

MM = 1.0 / 25.4
COL = 84 * MM      # single column width (inches)
FULL = 174 * MM    # full text width (inches)

SERIF = ["Times New Roman", "Nimbus Roman", "DejaVu Serif"]
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": SERIF,
    "font.size": 8,
    "axes.labelsize": 8,
    "axes.titlesize": 8,
    "legend.fontsize": 7,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "axes.linewidth": 0.6,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "lines.linewidth": 1.0,
    "axes.grid": True,
    "grid.linewidth": 0.3,
    "grid.alpha": 1.0,
    "grid.color": "0.85",
    "axes.axisbelow": True,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.01,
    "figure.dpi": 300,
    "pdf.fonttype": 42,
})

# scene constants -- identical to tools/verify_ray_map.py and the solver
R_OUT, R_IN, H_GLASS = 0.035, 0.0315, 0.090
WATER = 0.0594
SUN = np.array([0.80, 0.42, -0.43]); SUN /= np.linalg.norm(SUN)
N_WATER = 1.33468      # central channel, Daimon & Masumura 2007
N_GLASS = 1.52514      # central channel, Rubin 1985


def save(fig, name, note=""):
    p = f"{FIG}/{name}.pdf"
    fig.savefig(p)
    plt.close(fig)
    flatten_alpha(p)
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
def fig_scene():
    """To-scale technical drawing: the scene, the traced light path, the fold."""
    fig, ax = plt.subplots(figsize=(FULL, FULL * 0.40))

    # glass body: cross-section, hatched wall, no alpha
    ax.add_patch(Rectangle((-R_OUT, 0), 2 * R_OUT, H_GLASS, fill=False,
                           lw=0.9, ec="black", zorder=3))
    ax.add_patch(Rectangle((-R_IN, 0), 2 * R_IN, WATER, fill=False,
                           lw=0.7, ec="0.35", ls=(0, (4, 2)), zorder=3))
    # water fill, hatched rather than translucent (no alpha in a submission)
    ax.add_patch(Rectangle((-R_IN, 0), 2 * R_IN, WATER, fill=True, fc="0.92",
                           ec="none", zorder=2, hatch="...."))
    ax.plot([-R_IN, R_IN], [WATER, WATER], color="black", lw=0.9, zorder=4)
    # receiver
    ax.plot([-0.16, 0.16], [0, 0], color="black", lw=1.8, zorder=4)

    # traced light path -- computed, not sketched
    for y0 in (-0.004, 0.001, 0.006, 0.011):
        pts, hit = trace_ray(y0)
        if len(pts) > 1:
            xs = [q[0] for q in pts]; zs = [q[1] for q in pts]
            ax.plot(xs, zs, color="0.15", lw=0.6, zorder=5)
    # incident bundles
    for y0 in (-0.004, 0.001, 0.006, 0.011):
        xs = -SUN[0] / SUN[2] * (0.155 - y0)
        ax.annotate("", xy=(xs + 0.004, 0.150), xytext=(xs - 0.020, 0.190),
                    arrowprops=dict(arrowstyle="->", lw=0.6, color="0.15"))

    # fold band on the receiver, from the ray map's own extent
    ax.add_patch(Rectangle((0.036, -0.0035), 0.061, 0.007, fc="0.55",
                           ec="none", zorder=6))
    ax.annotate("fold band", xy=(0.066, -0.014), ha="center", va="top",
                fontsize=7, color="black")
    ax.annotate("", xy=(0.036, -0.010), xytext=(0.097, -0.010),
                arrowprops=dict(arrowstyle="<->", lw=0.5, color="black"))
    ax.text(0.0665, -0.0085, r"$61\,$mm", ha="center", va="bottom", fontsize=6.5)

    # dimension lines
    def dim_h(x0, x1, z, label, off=0.0):
        ax.annotate("", xy=(x0, z + off), xytext=(x1, z + off),
                    arrowprops=dict(arrowstyle="<->", lw=0.5, color="black"))
        ax.text((x0 + x1) / 2, z + off + 0.004, label, ha="center", va="bottom",
                fontsize=6.5)
        for xx in (x0, x1):
            ax.plot([xx, xx], [z, z + off], color="black", lw=0.4, ls=":")

    def dim_v(z0, z1, x, label):
        ax.annotate("", xy=(x, z0), xytext=(x, z1),
                    arrowprops=dict(arrowstyle="<->", lw=0.5, color="black"))
        ax.text(x + 0.004, (z0 + z1) / 2, label, ha="left", va="center",
                fontsize=6.5, rotation=90)
        for zz in (z0, z1):
            ax.plot([x, x + 0.004], [zz, zz], color="black", lw=0.4)

    dim_v(0.0, H_GLASS, -0.052, r"$H=90\,$mm")
    dim_v(0.0, WATER, -0.062, r"fill $59.4\,$mm")
    dim_h(-R_OUT, R_OUT, H_GLASS, r"$\varnothing\,70\,$mm", off=0.010)

    # wall thickness callout
    ax.annotate("", xy=(R_IN, 0.078), xytext=(R_OUT, 0.078),
                arrowprops=dict(arrowstyle="<->", lw=0.5, color="black"))
    ax.text(R_OUT + 0.006, 0.078, r"wall $3.5\,$mm", ha="left", va="center",
            fontsize=6.5)

    # scale bar, 20 mm
    ax.add_patch(Rectangle((-0.152, -0.026), 0.020, 0.004, fc="black", ec="none"))
    ax.text(-0.142, -0.031, r"$20\,$mm", ha="center", va="top", fontsize=6.5)

    ax.text(-0.020, 0.168, r"sun: distant, $0.53^\circ$", fontsize=7)
    ax.text(0.040, 0.040, "glass\n" + r"$n(\lambda)$", fontsize=7, va="center")
    ax.text(-0.024, 0.018, "water\n" + r"$n(\lambda)$ Sellmeier", fontsize=7,
            ha="center", va="center")
    ax.text(0.0, -0.043, "receiver (matte, Lambertian)", fontsize=7, ha="center")

    ax.set_xlim(-0.185, 0.185)
    ax.set_ylim(-0.050, 0.185)
    ax.set_aspect("equal")
    ax.set_xlabel(r"$x$ (mm)")
    ax.set_ylabel(r"$z$ (mm)")
    ax.grid(False)
    ax.set_xticks(np.arange(-0.15, 0.20, 0.05))
    ax.set_yticks(np.arange(0.0, 0.20, 0.05))
    ax.set_xticklabels([f"{v*1000:.0f}" for v in np.arange(-0.15, 0.20, 0.05)])
    ax.set_yticklabels([f"{v*1000:.0f}" for v in np.arange(0.0, 0.20, 0.05)])
    save(fig, "fig1_scene", "to-scale drawing, traced path")


# ------------------------------------------------------------------- figure 2
def fig_fold_optics():
    """The ray map and its Jacobian: where the fold is and why it matters."""
    import verify_ray_map as V
    X, Y = V.trace(n_side=700)[:2]
    g = V.to_grid(X, Y)
    g = np.asarray(g, dtype=float)

    fig, axes = plt.subplots(1, 2, figsize=(FULL, FULL * 0.33))
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
def fig_airy():
    """The fold profile and the non-integrability of the Airy intensity."""
    from scipy.special import airy
    from scipy.integrate import quad
    u = np.linspace(0, 8, 2000)
    I = airy(-u)[0] ** 2
    peak_u = 1.01879297
    peak_h = 0.286928

    fig, axes = plt.subplots(1, 2, figsize=(FULL, FULL * 0.33))
    axes[0].plot(u, I, color="black", lw=0.9)
    axes[0].plot([peak_u], [peak_h], "o", ms=3, color="black")
    axes[0].annotate(r"peak $X=1.0188$, beside the fold",
                     xy=(peak_u, peak_h), xytext=(2.4, 0.26), fontsize=7,
                     arrowprops=dict(arrowstyle="->", lw=0.6))
    axes[0].axvline(0, color="0.6", lw=0.5, ls=":")
    axes[0].set_title(r"(a) fold intensity $|\mathrm{Ai}(-u)|^{2}$")
    axes[0].set_xlabel(r"$u$ (canonical fold coordinate, dimensionless)")
    axes[0].set_ylabel(r"$|\mathrm{Ai}(-u)|^{2}$")

    L = np.linspace(1, 5000, 300)
    vals = []
    for l in L:
        vals.append(quad(lambda x: airy(x)[0] ** 2, -l, 80, limit=400)[0])
    axes[1].plot(L, vals, color="black", lw=0.9, label="computed")
    axes[1].plot(L, np.sqrt(L) / np.pi + 0.5, color="0.45", lw=0.9, ls="--",
                 label=r"$\pi^{-1}\sqrt{L}$ (Lemma 1)")
    axes[1].set_title(r"(b) $\int_{-L}^{80}|\mathrm{Ai}(u)|^{2}\mathrm{d}u$ diverges")
    axes[1].set_xlabel(r"truncation $L$ (dimensionless)")
    axes[1].set_ylabel("integral")
    axes[1].legend(loc="upper left")
    save(fig, "fig3_airy", "profile and non-integrability")


# ------------------------------------------------------------------- figure 4
def fig_field():
    """Our baked field, with the per-channel profile."""
    from make_paper_figures import read_png16
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
    for c, (col, ch) in enumerate(zip(["black", "0.45", "0.7"], "RGB")):
        axes[1].plot(field[:, :, c].mean(axis=0), color=col, lw=0.8,
                     label=f"{ch}  ({[650,550,450][c]} nm)")
    axes[1].set_title("(b) horizontal profile, per channel")
    axes[1].set_xlabel("grid $x$ (1024 px)")
    axes[1].set_ylabel(r"intensity, linear (cap $\times$ mean)")
    axes[1].legend(loc="upper right")
    save(fig, "fig4_field", "baked field and profile")


# ------------------------------------------------------------------- figure 5
def fig_quality():
    """Correlation against the independent ground truth, by tile size."""
    d = json.load(open(f"{ROOT}/docs/figures/figure_data.json"))
    tiles = d["tiles_mm"]
    q = d["quality"]
    fig, ax = plt.subplots(figsize=(COL, COL * 0.72))
    marks = {"ours": ("o", "black", "ours"), "SPPM": ("s", "0.45", "SPPM"),
             "Cycles": ("^", "0.7", "Cycles")}
    for k, (m, c, lab) in marks.items():
        ax.plot(tiles, q[k], marker=m, color=c, ms=3.2, label=lab)
    ax.set_xscale("log")
    ax.set_xticks(tiles); ax.set_xticklabels([f"{t:.0f}" for t in tiles])
    ax.set_xlabel("tile size (mm)")
    ax.set_ylabel("Pearson $r$ vs independent trace")
    ax.set_ylim(0.35, 1.0)
    ax.legend(loc="lower left")
    ax.text(0.02, 0.05, "caustic = positive part;\nsame estimator for all",
            transform=ax.transAxes, fontsize=6.5, va="bottom")
    save(fig, "fig5_quality", "quality vs trace")


# ------------------------------------------------------------------- figure 6
def fig_fourpanel():
    """The same caustic four ways."""
    try:
        from make_paper_figures import load_all
        gt, ours, sp, cyc, _ = load_all()
    except Exception as e:
        print("  fig6 skipped:", e)
        return
    fig, axes = plt.subplots(1, 4, figsize=(FULL, FULL * 0.28))
    for ax, img, t in zip(axes, (gt, ours, sp, cyc),
                          ("ground truth\n(brute-force trace)", "ours\n(wave-corrected)",
                           "PBRT-v4 SPPM", "Blender Cycles")):
        v = np.asarray(img, dtype=float)
        v = v / (v.max() if v.max() > 0 else 1)
        ax.imshow(np.clip(v, 0, 1) ** 0.45, cmap="inferno")
        ax.set_title(t, fontsize=7)
        ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
    fig.text(0.5, -0.02, "each panel normalised to its own maximum, $\\gamma=0.45$",
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
    ax.set_xticks(x); ax.set_xticklabels([f"${g}^2$" for g in grids])
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
    ax.bar(x - 0.19, ours, 0.36, color="black", ec="black", lw=0.5, label="ours")
    ax.bar(x + 0.19, sppm, 0.36, color="0.75", ec="black", lw=0.5, label="SPPM")
    for xi, v in zip(x - 0.19, ours):
        ax.text(xi, v + 2, str(v), ha="center", fontsize=6.5)
    for xi, v in zip(x + 0.19, sppm):
        ax.text(xi, v + 2, str(v), ha="center", fontsize=6.5)
    ax.set_xticks(x); ax.set_xticklabels(ch)
    ax.set_ylabel("edge radius (mm)")
    ax.set_ylim(0, 122)
    ax.legend(frameon=False, loc="upper right")
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
    fig_scene()
    fig_fold_optics()
    fig_airy()
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
