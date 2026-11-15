"""make_presentation_figure.py -- presentation sheets, honestly labelled.

Emits two files in out/presentation/:

  comparison.png  A/C  Cycles    -- sunlit dragon | designed fringe rig
                  B/D  ours      -- same two scenes
    The dragon row is the realistic comparison (same camera, 16 rays/texel
    bake). The fringe row is the rig built to make fringes visible: operational
    0.123 mm width, 18x the canonical 6.8 um (EVIDENCE 14.5f), labelled as such.

  airy_profile.png  the canonical Airy band (d = 6.77 um, first zero 15.84 um)
    against the geometric divergence, with the solar wash-out stated. This is
    the quantitative claim: bounded at the fold, fringes where resolvable.

Run:  python tools/make_presentation_figure.py
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec
from PIL import Image
from scipy.special import airy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DS = os.path.join(ROOT, "out", "dragon_suite")
OUT = os.path.join(ROOT, "out", "presentation")

CYCLES = os.path.join(DS, "cycles_fresh.png")      # fresh render, MNEE, 4096 spp, no denoise
OURS = os.path.join(DS, "addon_ours_2560_mult4.png")  # fresh bake, 16 rays/texel
if not os.path.exists(CYCLES):
    CYCLES = os.path.join(DS, "cycles_native_2560.png")
if not os.path.exists(OURS):
    OURS = os.path.join(DS, "addon_ours_2560_physical.png")
HERO_C = os.path.join(ROOT, "out", "hero_cycles.png")
HERO_O = os.path.join(ROOT, "out", "hero_ours.png")

D_UM = 6.77            # canonical fringe width scale, Eq. 14 at 550 nm
FIRST_ZERO_UM = 15.84  # 2.3381 * D_UM


def caustic_box(path, size=760):
    """Crop box centred on the brightest table region (same box for both engines)."""
    im = Image.open(path).convert("RGB")
    a = np.asarray(im, dtype=np.float32).mean(2)
    a[: int(a.shape[0] * 0.30)] = 0.0          # skip the glass/rim highlights
    k = 24
    h, w = a.shape[0] // k * k, a.shape[1] // k * k
    t = a[:h, :w].reshape(h // k, k, w // k, k).mean(axis=(1, 3))
    r, c = np.unravel_index(int(np.argmax(t)), t.shape)
    cy, cx = (r + 0.5) * k, (c + 0.5) * k
    half = size // 2
    x0 = int(min(max(cx - half, 0), im.width - size))
    y0 = int(min(max(cy - half, 0), im.height - size))
    return (x0, y0, x0 + size, y0 + size)


def sheet_comparison(path):
    box = caustic_box(HERO_O)
    fig = plt.figure(figsize=(15, 12.6), dpi=150)
    gs = GridSpec(2, 2, hspace=0.16, wspace=0.04,
                  left=0.02, right=0.98, top=0.94, bottom=0.09)
    panels = [
        (gs[0, 0], CYCLES, "Cycles  —  sunlit dragon scene"),
        (gs[0, 1], OURS, "Ours  —  baked wave-corrected field, 16 rays/texel"),
        (gs[1, 0], HERO_C, "Cycles  —  designed fringe rig"),
        (gs[1, 1], HERO_O, "Ours  —  same rig, wave-corrected"),
    ]
    for spec, src, title in panels:
        ax = fig.add_subplot(spec)
        im = Image.open(src).convert("RGB")
        ax.imshow(im.crop(box) if "hero" in src else im)
        ax.axis("off")
        ax.set_title(title, loc="left", fontsize=13, pad=6)

    fig.text(0.02, 0.035,
             "Top row — the same scene and camera. No fringe pattern is shown or claimed: "
             "at 550 nm the spacing is 6.77 µm and a 0.53° sun blurs 925 µm (136x).\n"
             "Bottom row — a rig designed for visibility: operational 0.123 mm width, "
             "18x the canonical 6.8 µm, so the fringe count is not physical (EVIDENCE 14.5f).",
             fontsize=10.5, color="0.25", va="bottom")
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    print("WROTE", path)


def sheet_profile(path):
    x = np.linspace(-2.0, 26.0, 4000)
    wave = np.abs(airy(-x / D_UM)[0]) ** 2
    wave /= wave.max()
    geom = np.zeros_like(x)
    pos = x > 0
    geom[pos] = 1.0 / np.sqrt(x[pos])
    band = (x > 0) & (x < 26)
    geom *= wave[band].sum() / max(geom[band].sum(), 1e-12)

    fig, ax = plt.subplots(figsize=(11, 5), dpi=150)
    ax.plot(x, geom, color="#b03030", lw=1.6, ls="--",
            label="geometric optics (path tracer): divergent at the fold")
    ax.plot(x, wave, color="#1f4e9c", lw=2.6,
            label="wave-corrected: $|\\mathrm{Ai}(-x/d)|^2$, bounded, $d$ = 6.77 µm")
    ax.axvline(0, color="0.6", lw=0.8)
    for k, lab in ((D_UM, "$d$ = 6.77 µm"), (FIRST_ZERO_UM, "first zero 15.84 µm")):
        ax.axvline(k, color="0.75", lw=0.8, ls=":")
        ax.text(k + 0.3, 0.88, lab, rotation=90, va="top", fontsize=9, color="0.45")
    ax.set_xlim(-2, 26)
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("distance from the fold (µm)")
    ax.set_ylabel("normalised irradiance")
    ax.set_title("Canonical Airy band at 550 nm: bounded at the fold, "
                 "fringes only where the source is coherent enough", loc="left", fontsize=12)
    ax.legend(loc="upper right", frameon=False)
    ax.grid(alpha=0.15)
    fig.text(0.5, -0.02,
             "Flux-matched over the plotted band. Under a 0.53° sun this structure is "
             "washed out (925 µm blur, 136x the spacing); it is shown at micro-scale.",
             ha="center", fontsize=9, color="0.3")
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    print("WROTE", path)


def main():
    os.makedirs(OUT, exist_ok=True)
    for p in (CYCLES, OURS, HERO_C, HERO_O):
        if not os.path.exists(p):
            raise SystemExit(f"missing panel: {p}")
    sheet_comparison(os.path.join(OUT, "comparison.png"))
    sheet_profile(os.path.join(OUT, "airy_profile.png"))


if __name__ == "__main__":
    main()
