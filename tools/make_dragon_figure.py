"""make_dragon_figure.py -- committed comparison figure for the dragon suite.

Reads working artefacts in out/ (gitignored) and writes
docs/media/dragon_suite.png (committed). All panels at physical scale.
"""
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "dragon_suite"
MEDIA = ROOT / "docs" / "media"


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image

    ref = np.load(OUT / "referee_256.npy")
    pbrt = np.array(Image.open(OUT / "pbrt_vis.png").convert("L"), dtype=float)
    mitsu = np.array(Image.open(OUT / "mitsuba_vis.png").convert("L"), dtype=float)
    cycles = np.array(Image.open(OUT / "cycles_native_2560.png").convert("L"), dtype=float)

    fig, axes = plt.subplots(2, 2, figsize=(9.6, 7.2))
    axes[0, 0].imshow(ref, cmap="inferno")
    axes[0, 0].set_title("referee: two-interface mesh trace (256)", fontsize=9)
    axes[0, 1].imshow(cycles, cmap="gray")
    axes[0, 1].set_title("Cycles-native 2560x1440/1024spp (66.1 s)", fontsize=9)
    axes[1, 0].imshow(pbrt, cmap="gray")
    axes[1, 0].set_title("PBRT-SPPM ortho 256 (7.7 s): fan unresolved", fontsize=9)
    axes[1, 1].imshow(mitsu, cmap="gray")
    axes[1, 1].set_title("Mitsuba path 64spp (1.4 s): fireflies", fontsize=9)
    for ax in axes.ravel():
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle("Glass dragon caustic suite — physical fringe scale, locked sun+camera",
                 fontsize=10)
    fig.tight_layout()
    MEDIA.mkdir(parents=True, exist_ok=True)
    fig.savefig(MEDIA / "dragon_suite.png", dpi=150)
    plt.close(fig)
    print(f"WROTE {MEDIA / 'dragon_suite.png'}")


if __name__ == "__main__":
    main()
