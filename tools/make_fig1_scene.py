"""make_fig1_scene.py -- Figure 1 as a to-scale technical drawing.

What was wrong with the first version, all of it visible in the render:

  1. rays were traced in the x-z plane from the sun vector's x and z components.
     The sun's azimuth is 27.7 deg, so light also moves in y; the section has to
     be taken along the sun's azimuth for the 2-D refraction to be exact.
  2. the fold band was drawn at a HARDCODED 36-97 mm. A drawn band that does not
     correspond to the measured caustic is exactly the kind of decoration this
     work is meant to avoid.
  3. the air gap inside the glass was labelled "glass", and both material labels
     sat inside the water region.

Two modelling errors were made and fixed while rebuilding, both of which made the
figure silently wrong rather than visibly broken:

  * the light path was taken as glass -> water at the inner wall. Per
    tools/verify_ray_map.py it is
        air -> outer wall -> inner wall -> AIR CAVITY -> rippling surface
            -> water -> receiver:
    light enters high on the side wall and crosses the empty cavity before it
    reaches the water at all;
  * the wall was intersected as a CIRCLE of radius R_OUT. That is the cylinder's
    cross-section, but an axial section of a finite cylinder is a RECTANGLE, so
    the wall is the vertical pair x = +/-R_OUT over z in [0, H_GLASS]. The circle
    only spans z = +/-35 mm and rejected every ray for entering too low.

The 2-D section does NOT reproduce the 3-D caustic (its landing map stays
monotonic even with the scene's ripple present, because the in-plane ripple is a
single 1-D sinusoid while the real fold comes from the full 2-D surface). So the
figure does not invent a band from it: the band drawn on the receiver is the
MEASURED extent of the caustic taken from the ray map, projected onto the section
direction, and the caption says so.

Run:  <system python> tools/make_fig1_scene.py
"""
import os
import sys

import matplotlib

# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fig1_geometry as G

ROOT = _ROOT
FIG = f"{ROOT}/docs/paper/figures"
MM = 1.0 / 25.4
import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)
from paper_figs import palette, style
FULL = style.FULL_MM * style.MM   # measured text width

style.apply()

R_OUT, R_IN, H_GLASS, WATER = G.R_OUT, G.R_IN, G.H_GLASS, G.WATER


def measured_caustic_span():
    """Measured extent of the caustic, from the independent trace, projected onto
    the section direction. Nothing hardcoded: this is the same brute-force trace
    (tools/verify_ray_map.py) the paper's ground truth uses."""
    import verify_ray_map as V
    from scipy.ndimage import gaussian_filter
    X, Y = V.trace(n_side=1200)[:2]
    g = gaussian_filter(V.to_grid(X, Y).astype(float), 2.0)
    n = g.shape[0]
    xs = np.linspace(-0.16, 0.16, n)
    ys = np.linspace(0.16, -0.16, n)
    m = g > 0.25 * g.max()
    yy, xx = np.where(m)
    # project onto the in-plane sun azimuth
    r = xs[xx] * G.D[0] + ys[yy] * G.D[1]
    return float(r.min()), float(r.max()), float(g.max())


def main():
    lo, hi, _ = measured_caustic_span()
    print(f"measured caustic span along the section direction: "
          f"{lo*1000:.1f} .. {hi*1000:.1f} mm")

    fig, ax = plt.subplots(figsize=(FULL, FULL * 0.46))

    # ---- geometry, true scale
    ax.add_patch(Rectangle((-R_OUT, 0), 2 * R_OUT, H_GLASS, fill=False,
                           lw=1.0, ec="black", zorder=4))
    ax.add_patch(Rectangle((-R_IN, 0), 2 * R_IN, H_GLASS, fill=False,
                           lw=0.7, ec="black", zorder=4))
    ax.add_patch(Rectangle((-R_IN, 0), 2 * R_IN, WATER, fc="0.90", ec="none",
                           zorder=2))
    ax.plot([-R_IN, R_IN], [WATER, WATER], color="black", lw=1.0, zorder=5)
    ax.plot([-0.16, 0.16], [0, 0], color="black", lw=2.0, zorder=5)

    # ---- traced light path (real rays through the real interfaces)
    bw = (WATER - G.Z_AT_B0) / G.DZ_DB
    bt = (H_GLASS - G.Z_AT_B0) / G.DZ_DB
    bs_dense = np.linspace(bw, bt, 5000)
    ray_candidates = [(b, G.path(b)) for b in bs_dense]
    ray_candidates = [(b, pts, r) for b, (pts, r) in ray_candidates if r is not None]
    # Select 5 rays spanning the measured caustic fold on the receiver
    chosen_rays = [min(ray_candidates, key=lambda x: abs(x[2] - tr))
                   for tr in [0.025, 0.036, 0.048, 0.060, 0.072]]

    for b, pts, r in chosen_rays:
        xs = [p[0] for p in pts]; zs = [p[1] for p in pts]
        ax.plot(xs, zs, color="0.15", lw=0.55, zorder=6)
        # incoming sun ray arrow head along the trajectory
        if len(pts) >= 2:
            p_hit = np.array(pts[1])
            p_arr = p_hit - 0.055 * G.D
            ax.annotate("", xy=p_arr + 0.008 * G.D, xytext=p_arr - 0.008 * G.D,
                        arrowprops=dict(arrowstyle="->", lw=0.5, color="0.35"))

    # ---- the measured caustic, drawn where it was measured
    ax.add_patch(Rectangle((lo, -0.0030), hi - lo, 0.0060, fc="0.35",
                           ec="none", zorder=7))
    ax.annotate("", xy=(lo, -0.0135), xytext=(hi, -0.0135),
                arrowprops=dict(arrowstyle="<->", lw=0.5, color="black", zorder=8))
    ax.text((lo + hi) / 2, -0.0175, f"caustic fold  {abs(hi-lo)*1000:.0f} mm  (measured)",
            ha="center", va="top", fontsize=7, zorder=8)

    # ---- dimension lines, kept clear of the geometry and rays
    def dim_v(z0, z1, x, label, side="left"):
        ax.annotate("", xy=(x, z0), xytext=(x, z1),
                    arrowprops=dict(arrowstyle="<->", lw=0.5, color="black"))
        ax.text(x + (-0.004 if side == "left" else 0.004), (z0 + z1) / 2, label,
                ha="right" if side == "left" else "left", va="center",
                fontsize=6.5, rotation=90)
        for zz in (z0, z1):
            ax.plot([x, x + (0.003 if side == "left" else -0.003)], [zz, zz],
                    color="black", lw=0.4)

    # Left: water fill height (all incoming rays enter above 61 mm, so no collision)
    dim_v(0.0, WATER, -0.046, r"water fill $59.4$", "left")
    ax.plot([-R_OUT, -0.046 - 0.003], [WATER, WATER], color="black", lw=0.35, ls="--")

    # Right: total glass height (all caustic rays land by x = 72 mm, so x = 92 mm is clear)
    dim_v(0.0, H_GLASS, 0.092, r"glass height $90$", "right")
    ax.plot([R_OUT, 0.092 + 0.003], [H_GLASS, H_GLASS], color="black", lw=0.35, ls="--")

    # outer diameter, above cylinder with extension witness lines
    z_dim_d = H_GLASS + 0.007
    for xx in (-R_OUT, R_OUT):
        ax.plot([xx, xx], [H_GLASS, z_dim_d + 0.003], color="black", lw=0.4)
    ax.annotate("", xy=(R_OUT, z_dim_d), xytext=(-R_OUT, z_dim_d),
                arrowprops=dict(arrowstyle="<->", lw=0.5, color="black"))
    ax.text(0.0, z_dim_d + 0.002, r"$\varnothing\,70$",
            ha="center", va="bottom", fontsize=6.5)

    # ---- material labels, each with a leader to its own region
    ax.text(0.0, WATER * 0.55, "water", ha="center", va="center", fontsize=7.5,
            color="black", zorder=9)
    ax.text(0.0, (WATER + H_GLASS) / 2, "air", ha="center", va="center",
            fontsize=7.5, color="black", zorder=9)

    # Glass and wall thickness called out cleanly on upper right wall (zero rays)
    ax.text(R_OUT + 0.024, 0.075, "glass\n(wall $3.5$)", ha="left", va="center",
            fontsize=7.0, color="black")
    ax.annotate("", xy=((R_OUT + R_IN) / 2, 0.075),
                xytext=(R_OUT + 0.022, 0.075),
                arrowprops=dict(arrowstyle="->", lw=0.45, color="black"))

    ax.text(-0.055, 0.152, "sun: distant, 0.53\u00b0 (solar), elevation 25.4\u00b0",
            fontsize=7.5, ha="left")

    # ---- scale bar
    ax.add_patch(Rectangle((-0.152, -0.030), 0.020, 0.004, fc="black", ec="none"))
    ax.text(-0.142, -0.034, r"$20$ mm", ha="center", va="top", fontsize=6.5)

    ax.text(0.0, -0.041, "receiver: matte, Lambertian, 320 mm square",
            ha="center", va="top", fontsize=7)

    ax.set_xlim(-0.180, 0.180)
    ax.set_ylim(-0.050, 0.190)
    ax.set_aspect("equal")
    ax.grid(False)
    ax.set_xlabel(r"$x$ (mm)")
    ax.set_ylabel(r"$z$ (mm)")
    xt = np.arange(-0.15, 0.20, 0.05)
    yt = np.arange(0.0, 0.20, 0.05)
    ax.set_xticks(xt); ax.set_yticks(yt)
    ax.set_xticklabels([f"{v*1000:.0f}" for v in xt])
    ax.set_yticklabels([f"{v*1000:.0f}" for v in yt])

    p = f"{FIG}/fig1_scene.pdf"
    style.fit(fig)
    style.save(fig, p, width_mm=style.FULL_MM)
    plt.close(fig)

    import re
    d0 = open(p, "rb").read()
    d1 = re.sub(rb"/(ca|CA) ([0-9]*\.?[0-9]+)",
                lambda m: b"/" + m.group(1) + b" " +
                          (("1." + "0" * (len(m.group(2).decode()) - 2))
                           if "." in m.group(2).decode() else "1").encode(),
                d0)
    if len(d1) == len(d0):
        open(p, "wb").write(d1)
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
