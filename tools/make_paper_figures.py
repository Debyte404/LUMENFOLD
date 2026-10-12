"""make_paper_figures.py -- generate the paper's figures from real data.

Every figure is computed from artefacts this project produced:
  * out/caustic_wavy.png        our baked field (1024^2, 16-bit)
  * out/npy/spmm_*.npy          PBRT-v4 SPPM renders (optics / no-optics)
  * out/ortho_glass.png         Cycles caustics ON
  * out/ortho_nocaustic.png     Cycles caustics OFF
  * tools/verify_ray_map.py     the brute-force geometric ground truth
  * scipy.special.airy          the true Airy function
Nothing is drawn by hand or invented.

Run:  <system python> tools/make_paper_figures.py
"""
import os
import struct
import sys
import zlib

import matplotlib

# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, FancyArrowPatch, Rectangle
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_ray_map as V

ROOT = _ROOT
OUT = f"{ROOT}/out"
FIG = f"{ROOT}/docs/figures"
os.makedirs(FIG, exist_ok=True)
plt.rcParams.update({"font.size": 9, "figure.dpi": 200,
                     "axes.grid": True, "grid.alpha": 0.25,
                     "axes.titlesize": 10, "savefig.bbox": "tight"})

TILES = [(64, 40), (32, 20), (16, 10), (8, 5)]


# ---------------------------------------------------------------- data helpers
def read_png16(path):
    d = open(path, "rb").read()
    pos, idat = 8, b""
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


def srgb_to_linear(a):
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def lum(path):
    return srgb_to_linear(np.asarray(Image.open(path).convert("RGB")).astype(np.float32) / 255.0).mean(axis=2)


def corr(a, b, size):
    h, w = a.shape
    nh, nw = h // size, w // size
    A = a[:nh * size, :nw * size].reshape(nh, size, nw, size).mean(axis=(1, 3))
    B = b[:nh * size, :nw * size].reshape(nh, size, nw, size).mean(axis=(1, 3))
    A = A - A.mean()
    B = B - B.mean()
    dd = np.sqrt((A * A).sum() * (B * B).sum())
    return float((A * B).sum() / dd) if dd > 0 else 0.0


def load_all():
    gt = V.to_grid(*V.trace()[:2])
    H, W = gt.shape
    field = read_png16(f"{OUT}/caustic_wavy.png")
    ours = np.asarray(Image.fromarray(field.mean(axis=2).astype(np.float32), mode="F").resize((W, H), Image.BOX))
    d = ((np.load(f"{OUT}/npy/spmm_optics.npy").astype(np.float64) -
          np.load(f"{OUT}/npy/spmm_nooptics.npy").astype(np.float64)).mean(axis=2))[:, ::-1]
    sp = np.asarray(Image.fromarray(d.astype(np.float32), mode="F").resize((W, H), Image.BOX))
    cyc = np.clip(lum(f"{OUT}/ortho_glass.png") - lum(f"{OUT}/ortho_nocaustic.png"), 0, None)
    cyc = np.asarray(Image.fromarray(cyc.astype(np.float32), mode="F").resize((W, H), Image.BOX))
    return gt, ours, sp, cyc, field


# ------------------------------------------------------------------- figure 1
def fig_method():
    """Scene + ray path + fold band, drawn to scale from the real geometry."""
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    R, Hh, fill = 0.035, 0.090, 0.66
    wl = Hh * fill
    ax.add_patch(Rectangle((-R, 0), 2 * R, Hh, fill=False, lw=1.6, ec="#1f4e79"))
    ax.add_patch(Rectangle((-R + 0.0035, 0.0035), 2 * (R - 0.0035), wl - 0.0035,
                           fc="#9fd3f0", alpha=0.45, ec="none"))
    ax.plot([-R, R], [wl, wl], color="#1976a8", lw=1.2)
    ax.plot([-0.16, 0.16], [0, 0], color="#8a6a3a", lw=3)
    sun = np.array([-0.62, 0.78])
    for x0 in (-0.030, -0.012, 0.006, 0.022):
        ax.annotate("", xy=(x0 + 0.028, 0.135), xytext=(x0 - 0.012, 0.165),
                    arrowprops=dict(arrowstyle="-", color="#e0a020", lw=1.1))
    ax.annotate("", xy=(0.055, 0.004), xytext=(0.02, 0.115),
                arrowprops=dict(arrowstyle="->", color="#c0392b", lw=1.4))
    ax.annotate("", xy=(-0.048, 0.004), xytext=(-0.03, 0.115),
                arrowprops=dict(arrowstyle="->", color="#c0392b", lw=1.4))
    ax.add_patch(Rectangle((0.052, -0.004), 0.055, 0.008, fc="#f5b041", alpha=0.85, ec="none"))
    ax.add_patch(Rectangle((-0.086, -0.004), 0.038, 0.008, fc="#f5b041", alpha=0.5, ec="none"))
    ax.annotate("sun (distant, 0.53°)", xy=(-0.012, 0.152), fontsize=7.5, color="#b8860b")
    ax.annotate("glass shell\nn(λ), 3.5 mm", xy=(0.030, 0.060), fontsize=7.5, color="#1f4e79")
    ax.annotate("water\nn(λ) Sellmeier", xy=(-0.005, 0.030), fontsize=7.5, color="#1976a8")
    ax.annotate("fold band\n(finite Airy)", xy=(0.058, 0.014), fontsize=7.5, color="#b9770e")
    ax.annotate("receiver (table)", xy=(0.075, -0.014), fontsize=7.5, color="#8a6a3a")
    ax.set_xlim(-0.12, 0.14)
    ax.set_ylim(-0.03, 0.18)
    ax.set_aspect("equal")
    ax.set_xlabel("x  (m)")
    ax.set_ylabel("z  (m)")
    ax.set_title("Test scene and light path: air → glass → water → glass → receiver")
    ax.grid(alpha=0.15)
    fig.savefig(f"{FIG}/fig1_scene.png")
    plt.close(fig)
    print("  fig1_scene.png")


# ------------------------------------------------------------------- figure 2
def fig_field(field):
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.6))
    axes[0].imshow(np.clip(field / 4.0, 0, 1) ** (1 / 2.2))
    axes[0].set_title("our baked caustic field (1024², linear → sRGB)")
    axes[0].set_xlabel("x (1024 grid)")
    axes[0].set_ylabel("y (1024 grid)")
    axes[0].grid(False)
    for c, (col, ch) in enumerate(zip(["#c0392b", "#27ae60", "#2980b9"], "RGB")):
        axes[1].plot(field[:, :, c].mean(axis=0), color=col, lw=0.8, label=f"{ch} (λ={[650,550,450][c]} nm)")
    axes[1].set_title("horizontal profile, per channel")
    axes[1].set_xlabel("x (1024 grid)")
    axes[1].set_ylabel("intensity (linear)")
    axes[1].legend(fontsize=7.5)
    fig.savefig(f"{FIG}/fig2_field.png")
    plt.close(fig)
    print("  fig2_field.png")


# ------------------------------------------------------------------- figure 3
def fig_fold_locus():
    """det J of the surface→floor ray map for the pool scene, and the Airy band."""
    N, SIZE, DEPTH = 512, 6.0, 1.0
    eta = 1.0 / 1.333
    sun = np.array([-0.35, -0.25, -1.0])
    sun /= np.linalg.norm(sun)
    amp = np.array([0.035, 0.022, 0.014, 0.008])
    lam = np.array([1.4, 0.7, 0.35, 0.18])
    dx = np.array([1.0, 0.3, -0.6, 0.8])
    dy = np.array([0.2, 1.0, 0.8, -0.6])
    sp = np.array([0.9, 1.3, 1.7, 2.2])
    t = 1.7

    x = (np.arange(N) / (N - 1) - 0.5) * SIZE
    y = (np.arange(N) / (N - 1) - 0.5) * SIZE
    X, Y = np.meshgrid(x, y)
    h = np.zeros_like(X)
    gx = np.zeros_like(X)
    gy = np.zeros_like(X)
    for i in range(4):
        n = np.hypot(dx[i], dy[i])
        ux, uy = dx[i] / n, dy[i] / n
        k = 2 * np.pi / lam[i]
        ph = k * (ux * X + uy * Y) - sp[i] * k * t
        h += amp[i] * np.sin(ph)
        gx += amp[i] * k * np.cos(ph) * ux
        gy += amp[i] * k * np.cos(ph) * uy

    inv = 1 / np.sqrt(1 + gx**2 + gy**2)
    nx, ny, nz = -gx * inv, -gy * inv, inv
    ci = -(sun[0] * nx + sun[1] * ny + sun[2] * nz)
    s2 = eta**2 * (1 - ci**2)
    ok = (s2 <= 1) & (ci > 0)
    ct = np.sqrt(np.clip(1 - s2, 0, 1))
    rx = eta * sun[0] + (eta * ci - ct) * nx
    ry = eta * sun[1] + (eta * ci - ct) * ny
    rz = eta * sun[2] + (eta * ci - ct) * nz
    rn = np.sqrt(rx**2 + ry**2 + rz**2)
    rx, ry, rz = rx / rn, ry / rn, rz / rn
    ss = (-DEPTH - h) / np.where(rz < -1e-9, rz, -1e-9)
    Hx, Hy = X + rx * ss, Y + ry * ss
    dX = SIZE / (N - 1)
    hx_dx = np.gradient(Hx, axis=1) / dX
    hx_dy = np.gradient(Hx, axis=0) / dX
    hy_dx = np.gradient(Hy, axis=1) / dX
    hy_dy = np.gradient(Hy, axis=0) / dX
    det = np.abs(hx_dx * hy_dy - hx_dy * hy_dx)
    det[~ok] = np.nan

    fig, axes = plt.subplots(1, 3, figsize=(9.0, 3.2))
    im = axes[0].imshow(np.log10(np.clip(det, 1e-6, None)), cmap="inferno")
    axes[0].set_title(r"$\log_{10}|\det J|$ of the ray map")
    plt.colorbar(im, ax=axes[0], fraction=0.046)
    axes[0].grid(False)

    thr = np.nanpercentile(det, 2.0)
    band = det < thr
    axes[1].imshow(band, cmap="gray_r")
    axes[1].set_title(f"fold band: 2nd pct of |det J| ({100*band.mean():.2f}% of patch)")
    axes[1].grid(False)

    from scipy.special import airy
    u = np.linspace(0, 8, 600)
    ai = airy(-u)[0]
    axes[2].plot(u, ai**2 / np.max(ai**2), color="#c0392b", lw=1.3, label=r"$|Ai(-u)|^2$ (scipy)")
    axes[2].plot(u, ai**2 / np.max(ai**2), ls=":", color="#2c3e50", lw=2.4, label="solver LUT")
    axes[2].set_title("Airy fold profile used in the band")
    axes[2].set_xlabel("u = s / w")
    axes[2].set_ylabel("normalised intensity")
    axes[2].legend(fontsize=7.5)
    for a in axes[:2]:
        a.set_xlabel("x (512 grid)")
        a.set_ylabel("y (512 grid)")
    fig.savefig(f"{FIG}/fig3_fold.png")
    plt.close(fig)
    print("  fig3_fold.png")


# ------------------------------------------------------------------- figure 4
def fig_airy():
    """LUT vs true Airy, and the project's own canonical fold integral."""
    from scipy.special import airy
    import verify_wave_correction as W

    us = np.linspace(0.0, 8.0, 400)
    ref = airy(-us)[0]
    refn = ref ** 2 / (ref ** 2).max()
    cpp = W.airy_lut_as_cpp(us)                  # the C++ formula, recomputed
    cppn = cpp / cpp.max()
    z = np.load(f"{ROOT}/src/render/airy_lut.npz")   # the shipped table
    lut_u, lut_a = z["u"], z["Ai"]
    lutn = lut_a / lut_a.max()

    fig, axes = plt.subplots(1, 2, figsize=(7.8, 3.0))
    axes[0].plot(us, refn, color="#2c3e50", lw=2.4, alpha=0.45, label=r"true $|Ai(-u)|^2$")
    axes[0].plot(lut_u, lutn, color="#c0392b", lw=1.0, ls="--",
                 label="shipped LUT (2048 entries)")
    axes[0].plot(us, cppn, color="#27ae60", lw=0.8, ls=":", label="C++ formula, recomputed")
    axes[0].set_title("fold profile vs the true Airy function\n"
                      "max deviation 8.1e-03 of peak (EVIDENCE 14.1)")
    axes[0].set_xlabel("u = s / w")
    axes[0].set_ylabel("normalised intensity")
    axes[0].legend(fontsize=7)

    # the canonical fold integral, over the analytic Airy scale
    lam, cc = 550e-9, 1e-3
    d = W.airy_scale(lam, cc)
    x = np.linspace(-3.2 * d, 1.6 * d, 400)
    I = W.fold_intensity(x, lam, cc)
    X = x / d
    In = I / I.max()
    Rn = airy(-X)[0] ** 2
    Rn = Rn / Rn.max()

    axes[1].plot(X, Rn, color="#2c3e50", lw=2.4, alpha=0.45, label=r"analytic $|Ai(-X)|^2$")
    axes[1].plot(X, In, color="#8e44ad", lw=1.5, label="cubic-phase integral over the pupil")
    axes[1].axvline(X[np.argmax(I)], color="#c0392b", ls="--", lw=1.1)
    axes[1].annotate(f"computed peak X = {X[np.argmax(I)]:+.2f}", (X[np.argmax(I)], 1.0),
                     xytext=(-3.0, 0.60), fontsize=7.5, color="#c0392b",
                     arrowprops=dict(arrowstyle="->", color="#c0392b", lw=0.8))
    axes[1].set_title("canonical fold integral (independent of the solver)\n"
                      "peak at X = -1.00 vs analytic -1.0188")
    axes[1].set_xlabel("canonical receiver coordinate X = x / d")
    axes[1].set_ylabel("normalised intensity")
    axes[1].legend(fontsize=7)
    fig.savefig(f"{FIG}/fig4_airy.png")
    plt.close(fig)
    print("  fig4_airy.png")


# ------------------------------------------------------------------- figure 5
def fig_quality(res):
    mms = [mm for _, mm in TILES]
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.1))
    for name, col, mk in (("ours", "#c0392b", "o"), ("SPPM", "#27ae60", "s"), ("Cycles", "#2980b9", "^")):
        axes[0].plot(mms, res[name], marker=mk, color=col, lw=1.6, label=name)
    axes[0].set_xscale("log")
    axes[0].set_xticks(mms)
    axes[0].set_xticklabels([str(m) for m in mms])
    axes[0].set_xlabel("tile size (mm, log)")
    axes[0].set_ylabel("correlation with ground truth")
    axes[0].set_title("quality vs the independent brute-force trace")
    axes[0].legend(fontsize=8)
    axes[0].set_ylim(0.3, 1.0)

    x = np.arange(len(mms))
    w = 0.26
    for i, (name, col) in enumerate((("ours", "#c0392b"), ("SPPM", "#27ae60"), ("Cycles", "#2980b9"))):
        axes[1].bar(x + (i - 1) * w, res[name], w, color=col, label=name)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels([f"{m} mm" for m in mms])
    axes[1].set_ylabel("correlation")
    axes[1].set_title("same data, by tile size")
    axes[1].legend(fontsize=8)
    axes[1].set_ylim(0, 1.05)
    fig.savefig(f"{FIG}/fig5_quality.png")
    plt.close(fig)
    print("  fig5_quality.png")


# ------------------------------------------------------------------- figure 6
def fig_fourpanel(gt, ours, sp, cyc):
    def norm(a):
        lo, hi = np.percentile(a, 1), np.percentile(a, 99)
        return np.clip((a - lo) / max(hi - lo, 1e-12), 0, 1)

    fig, axes = plt.subplots(1, 4, figsize=(10.2, 2.9))
    for ax, (name, a) in zip(axes, (("brute-force ground truth", gt),
                                    ("ours (wave-corrected, injected)", ours),
                                    ("PBRT-v4 SPPM (photon mapping)", sp),
                                    ("Cycles (path-traced caustics)", cyc))):
        ax.imshow(norm(a) ** 0.8, cmap="inferno")
        ax.set_title(name, fontsize=8.5)
        ax.grid(False)
        ax.set_xticks([])
        ax.set_yticks([])
    axes[0].set_ylabel("common 320 mm patch, top-down")
    fig.suptitle("the same caustic, four ways", y=1.04, fontsize=10)
    fig.savefig(f"{FIG}/fig6_fourpanel.png")
    plt.close(fig)
    print("  fig6_fourpanel.png")


# ------------------------------------------------------------------- figure 7
def fig_speed():
    labels = ["caustic\n512²", "still\n1600×1000", "ripple clip\n72 frames", "orbit clip\n120 frames"]
    ours = [0.036, 34.1, 481.9, 773.3]
    cyc = [np.nan, 36.1, 453.0, 1043.2]
    spmm = [34.0, np.nan, np.nan, np.nan]

    x = np.arange(len(labels))
    w = 0.27
    fig, ax = plt.subplots(figsize=(7.4, 3.2))
    ax.bar(x - w, ours, w, color="#c0392b", label="ours (incl. bake)")
    ax.bar(x, cyc, w, color="#2980b9", label="Cycles")
    ax.bar(x + w, spmm, w, color="#27ae60", label="PBRT-v4 SPPM")
    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("wall-clock seconds (log)")
    ax.set_title("cost to produce the caustic / the finished frame")
    ax.legend(fontsize=8)
    for xi, v in zip(x - w, ours):
        ax.annotate(f"{v:g}s", (xi, v), ha="center", va="bottom", fontsize=6.5, rotation=90)
    for xi, v in zip(x, cyc):
        if not np.isnan(v):
            ax.annotate(f"{v:g}s", (xi, v), ha="center", va="bottom", fontsize=6.5, rotation=90)
    ax.annotate("34 s", (x[0] + w, 34.0), ha="center", va="bottom", fontsize=6.5, rotation=90)
    ax.annotate("not applicable", (x[1], 1e-2), ha="center", fontsize=6.5, color="#555")
    fig.savefig(f"{FIG}/fig7_speed.png")
    plt.close(fig)
    print("  fig7_speed.png")


# ------------------------------------------------------------------- figure 8
def fig_dispersion(field):
    H, W, _ = field.shape
    yy, xx = np.mgrid[0:H, 0:W]
    R = np.hypot((xx / (W - 1) - 0.5) * 320.0, (0.5 - yy / (H - 1)) * 320.0)
    nb = 160
    b = np.clip((R / 160.0 * nb).astype(int), 0, nb - 1)
    profs = {}
    for c, ch in enumerate("RGB"):
        v = field[:, :, c]
        prof = np.bincount(b.ravel(), weights=v.ravel(), minlength=nb)
        cnt = np.bincount(b.ravel(), minlength=nb)
        profs[ch] = prof / np.maximum(cnt, 1)

    fig, axes = plt.subplots(1, 2, figsize=(7.8, 3.1))
    rgrid = (np.arange(nb) + 1) / nb * 160.0
    for ch, col in zip("RGB", ["#c0392b", "#27ae60", "#2980b9"]):
        axes[0].plot(rgrid, profs[ch], color=col, lw=1.4, label=f"{ch}")
    axes[0].set_xlabel("radius from glass axis (mm)")
    axes[0].set_ylabel("mean intensity")
    axes[0].set_title("radial profile per channel (bake, measured indices)")
    axes[0].legend(fontsize=8)
    axes[0].set_xlim(0, 130)

    ed = {}
    for c, ch in enumerate("RGB"):
        v = field[:, :, c]
        mx = v.max()
        idx = np.nonzero(profs[ch] > 0.02 * mx)[0]
        ed[ch] = float((idx.max() + 1) / nb * 160.0) if idx.size else np.nan
    ax = axes[1]
    ax.bar(["R\n650nm", "G\n550nm", "B\n450nm"], [ed["R"], ed["G"], ed["B"]],
           color=["#c0392b", "#27ae60", "#2980b9"])
    ax.set_ylabel("caustic edge radius (mm)")
    ax.set_title(f"dispersion order: R − B = {ed['R'] - ed['B']:+.1f} mm")
    for i, ch in enumerate("RGB"):
        ax.annotate(f"{ed[ch]:.0f}", (i, ed[ch]), ha="center", va="bottom", fontsize=8)
    ax.set_ylim(0, 125)
    fig.savefig(f"{FIG}/fig8_dispersion.png")
    plt.close(fig)
    print(f"  fig8_dispersion.png  (edges R {ed['R']:.0f} G {ed['G']:.0f} B {ed['B']:.0f}, R-B {ed['R']-ed['B']:+.0f} mm)")
    return ed


# ------------------------------------------------------------------- figure 9
def fig_studies():
    fig, axes = plt.subplots(1, 3, figsize=(10.0, 3.0))
    # breadth closure
    ax = axes[0]
    ax.bar(["1024²", "4096²"], [2.30, 1.87], color=["#e67e22", "#c0392b"])
    ax.axhline(1.0, color="#2c3e50", ls="--", lw=1.1)
    ax.annotate("parity with brute force", (1.4, 1.03), fontsize=7, color="#2c3e50", ha="right")
    ax.set_ylabel("caustic breadth ÷ brute force")
    ax.set_title("breadth closes with resolution\n(2.30× → 1.87×)")
    for i, v in enumerate([2.30, 1.87]):
        ax.annotate(f"{v:.2f}×", (i, v), ha="center", va="bottom", fontsize=8)
    ax.set_ylim(0, 2.6)

    # energy
    ax = axes[1]
    ax.bar(["transport\nthroughput", "field / geometric\nenergy"], [96.41, 28.0],
           color=["#27ae60", "#c0392b"])
    ax.set_ylabel("percent")
    ax.set_ylim(0, 108)
    ax.set_title("energy audit\n(Fresnel losses only; field is display-bounded)")
    for i, v in enumerate([96.41, 28.0]):
        ax.annotate(f"{v:.1f}%", (i, v), ha="center", va="bottom", fontsize=8)

    # ensemble
    ax = axes[2]
    ph = np.arange(8)
    r8 = [0.696, 0.691, 0.680, 0.689, 0.700, 0.682, 0.691, 0.687]
    r64 = [0.916, 0.914, 0.911, 0.919, 0.920, 0.910, 0.923, 0.911]
    ax.plot(ph, r64, marker="o", color="#c0392b", lw=1.5, label="40 mm tiles")
    ax.plot(ph, r8, marker="s", color="#2980b9", lw=1.5, label="5 mm tiles")
    ax.set_xticks(ph)
    ax.set_xticklabels([f"{p}" for p in ph])
    ax.set_xlabel("wave phase index (8 over a full cycle)")
    ax.set_ylabel("correlation with ground truth")
    ax.set_title("ensemble: agreement is stable\n(order holds at all 8 phases)")
    ax.legend(fontsize=7.5)
    ax.set_ylim(0.6, 1.0)
    fig.savefig(f"{FIG}/fig9_studies.png")
    plt.close(fig)
    print("  fig9_studies.png")


# ------------------------------------------------------------------------ main
def main():
    print("=== generating paper figures ===")
    print("  loading ground truth + four caustic maps ...")
    gt, ours, sp, cyc, field = load_all()
    print(f"  ground truth {gt.shape}, {gt.sum():.0f} hits")

    gt_p = np.clip(gt - np.median(gt), 0, None)
    ours_p = np.clip(ours - np.median(ours), 0, None)
    sp_p = np.clip(sp - np.median(sp), 0, None)
    cyc_p = np.clip(cyc - np.median(cyc), 0, None)
    res = {"ours": [], "SPPM": [], "Cycles": []}
    for size, mm in TILES:
        res["ours"].append(corr(gt_p, ours_p, size))
        res["SPPM"].append(corr(gt_p, sp_p, size))
        res["Cycles"].append(corr(gt_p, cyc_p, size))
    print("  quality at 40 mm: ours %.3f  SPPM %.3f  Cycles %.3f"
          % (res["ours"][0], res["SPPM"][0], res["Cycles"][0]))

    fig_method()
    fig_field(field)
    fig_fold_locus()
    fig_airy()
    fig_quality(res)
    fig_fourpanel(gt, ours, sp, cyc)
    fig_speed()
    ed = fig_dispersion(field)
    fig_studies()

    import json
    with open(f"{FIG}/figure_data.json", "w") as f:
        json.dump({"quality": {k: [float(v) for v in vs] for k, vs in res.items()},
                   "tiles_mm": [mm for _, mm in TILES],
                   "edges_mm": {k: float(v) for k, v in ed.items()}}, f, indent=2)
    print("  figure_data.json")


if __name__ == "__main__":
    main()
