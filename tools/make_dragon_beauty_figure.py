"""make_dragon_beauty_figure.py -- matched four-engine beauty comparison.

Same eye/target (CAM_beauty), same 2.4deg sun direction, matched ground
levels. Reads working artefacts in out/ (gitignored) and writes
docs/media/dragon_beauty_compare.png (committed). Physical scale throughout.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "dragon_suite"
MEDIA = ROOT / "docs" / "media"


def _check_aspect(w, h, name, target=16 / 9, tol=0.01):
    if abs(w / h - target) > tol:
        raise SystemExit(f"{name}: {w}x{h} is not 16:9; refusing to squash")


def _last_rows():
    import csv
    rows = {}
    with open(ROOT / "docs" / "data" / "dragon_suite.csv", newline="") as f:
        for row in csv.DictReader(f):
            rows[row["engine"]] = row
    return rows


def _self_test():
    rows = _last_rows()
    assert rows["mitsuba-beauty"]["engine"] == "mitsuba-beauty"
    _check_aspect(1600, 900, "ok")
    try:
        _check_aspect(640, 640, "square")
    except SystemExit:
        pass
    else:
        raise AssertionError("a square panel must be refused")
    print("FIGURE_SELF_TEST_OK")


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image
    import numpy as np

    def load(name, size=(640, 360)):
        im = Image.open(OUT / name).convert("RGB")
        _check_aspect(im.width, im.height, name)
        return np.array(im.resize(size))

    rows = _last_rows()

    def title(engine, label):
        r = rows[engine]
        text = f"{label} {r['res']}/{r['budget']}"
        if r["render_s"]:
            text += f" ({r['render_s']} s)"
        return text

    panels = [
        ("cycles_native_2560.png", title("cycles-native", "Cycles native")),
        ("addon_ours_2560_physical.png",
         "ours injected 2560x1440, 1024^2 x2 + 5.6 mm sun blur (9 min + 2 min)"),
        ("pbrt_beauty_vis.png", title("pbrt-beauty", "PBRT-SPPM")),
        ("mitsuba_beauty_vis.png", title("mitsuba-beauty", "Mitsuba path")),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(12.8, 7.6))
    for ax, (fn, title) in zip(axes.ravel(), panels):
        ax.imshow(load(fn))
        ax.set_title(title, fontsize=9)
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle("Glass dragon - same eye, target and 39.6 deg horizontal FOV; "
                 "one sun direction; physical scale", fontsize=10)
    fig.tight_layout()
    MEDIA.mkdir(parents=True, exist_ok=True)
    out = MEDIA / "dragon_beauty_compare.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"WROTE {out}")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        _self_test()
    else:
        main()
