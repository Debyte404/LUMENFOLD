"""make_red_media_figure.py -- Figure 12: the tinted-medium renders.

The paper asserts that a caustic's colour is set by the path the LIGHT travelled,
and that the medium's own body needs a separate mechanism. Both claims are visual,
and the paper had no figure for either.

Four panels from the shipped clips, one medium variable changed at a time:

  clear  |  red water  |  red glass  |  both

Sources are docs/media/ripple_{ours,water_red,glass_red,both_red}.gif -- the same
animation, same camera, same physical Airy width, so the only variable is the
medium. Frames are read from the GIFs rather than re-rendered so the figure cannot
disagree with the artefacts it shows.

Raster resolution: the panels are placed small (about 42 mm), and the frames are
read at full 640x360 and written at savefig.dpi, so the effective resolution is set
here rather than inherited from an rcParam default. See tools/paper_qa.py, which
measures it.
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                        # noqa: E402
from PIL import Image                     # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

MEDIA = f"{_ROOT}/docs/media"
OUT = f"{_ROOT}/docs/paper/figures"

MM = 1.0 / 25.4
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Nimbus Roman", "DejaVu Serif"],
    "font.size": 7.5,
    "axes.titlesize": 7.5,
    "pdf.fonttype": 42,
    "figure.dpi": 400,
    "savefig.dpi": 400,
})

PANELS = [
    ("ripple_ours.gif", "clear medium"),
    ("ripple_water_red.gif", "red water"),
    ("ripple_glass_red.gif", "red glass"),
    ("ripple_both_red.gif", "red water + red glass"),
]


def frame(path, which=36):
    im = Image.open(path)
    n = im.n_frames
    im.seek(min(which, n - 1))
    return np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0


def main():
    fig, axes = plt.subplots(1, 4, figsize=(174 * MM, 62 * MM))
    for ax, (name, label) in zip(axes, PANELS):
        p = os.path.join(MEDIA, name)
        if not os.path.exists(p):
            ax.set_axis_off()
            ax.set_title(label + " (missing)")
            continue
        a = frame(p)
        ax.imshow(a, interpolation="bilinear")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(label, fontsize=7, pad=3)
        # a frame border so the panels read as separate images
        for s in ax.spines.values():
            s.set_linewidth(0.5)
            s.set_edgecolor("0.4")
    fig.subplots_adjust(left=0.004, right=0.996, top=0.90, bottom=0.008, wspace=0.03)
    p = f"{OUT}/fig12_red_media.pdf"
    fig.savefig(p)
    plt.close(fig)
    print(f"  wrote {p}  ({os.path.getsize(p)/1024:.0f} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
