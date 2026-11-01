"""make_dragon_beauty_figure.py -- matched four-engine beauty comparison.

Same eye/target (CAM_beauty), same 2.4deg sun direction, matched ground
levels. Reads working artefacts in out/ (gitignored) and writes
docs/media/dragon_beauty_compare.png (committed). Physical scale throughout.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "dragon_suite"
MEDIA = ROOT / "docs" / "media"


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image
    import numpy as np

    def load(name, size=(640, 360)):
        im = Image.open(OUT / name).convert("RGB").resize(size)
        return np.array(im)

    panels = [
        ("cycles_native_2560.png", "Cycles native 2560x1440/1024spp (66 s)"),
        ("addon_ours_2560_r1024.png", "ours injected 2560, 1024^2 bake (71 min + 4 min)"),
        ("pbrt_beauty_vis.png", "PBRT-SPPM perspective 2560x1440/256spp (155 s)"),
        ("mitsuba_beauty_vis.png", "Mitsuba path 1024spp, ground-matched (106 s)"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(12.8, 7.6))
    for ax, (fn, title) in zip(axes.ravel(), panels):
        ax.imshow(load(fn))
        ax.set_title(title, fontsize=9)
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle("Glass dragon, one sun + one camera for all four — matched rig, physical scale",
                 fontsize=10)
    fig.tight_layout()
    MEDIA.mkdir(parents=True, exist_ok=True)
    out = MEDIA / "dragon_beauty_compare.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"WROTE {out}")


if __name__ == "__main__":
    main()
