"""Do the RENDERED caustics agree with the COMPUTED ones, tile by tile?

Before the light-path transmission fix the rendered grid was near-neutral for every
water (the camera ray reaches the exterior fan through air, so the renderer never
charged the water) while the computed table was strongly coloured. That gap is the
defect the fix closes, so it is the thing to measure.
"""
import json
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GLASS = ["clear", "cobalt", "amber", "green"]
WATER = ["clear", "faint", "copper", "tea", "ink"]
TW, TH, LAB, PAD, OFF = 340, 212, 20, 6, 130


def rendered():
    sh = np.asarray(Image.open(os.path.join(ROOT, "docs/media/colour_media_grid.png"))
                    .convert("RGB"), dtype=np.float32)
    out = {}
    for i, g in enumerate(GLASS):
        for j, w in enumerate(WATER):
            y = 30 + i * (TH + LAB + PAD)
            x = OFF + j * (TW + PAD)
            t = sh[y:y + TH, x:x + TW]
            lum = t.mean(axis=2)
            m = lum >= np.percentile(lum, 98)
            rgb = t[m].mean(axis=0)
            out[(g, w)] = rgb / max(rgb.max(), 1e-9)
    return out


def computed():
    with open(os.path.join(ROOT, "docs/data/colour_results.json"), encoding="utf-8") as fh:
        R = json.load(fh)
    out = {}
    for k, v in R["caustic"].items():
        g, w, ill = k.split("|")
        # The renderer's own sun is {19.0, 17.6, 15.8}, i.e. R/G 1.0795 and
        # B/G 0.8977 -- closest of the four named sources to EQUAL ENERGY, not to
        # solar. Comparing against the solar column was comparing two different
        # illuminants and inflated the disagreement.
        if ill != "flat":
            continue
        n = np.array(v["norm"], dtype=float)
        out[(g, w)] = n / max(n.max(), 1e-9)
    return out


def main():
    r, c = rendered(), computed()
    print("  %-7s %-7s | %-24s | %-24s | %s" % ("glass", "water", "RENDERED (norm)", "COMPUTED (norm)", "spread"))
    print("  " + "-" * 92)
    rv, cv = [], []
    for g in GLASS:
        for w in WATER:
            if (g, w) not in r or (g, w) not in c:
                continue
            a, b = r[(g, w)], c[(g, w)]
            sp_r = (a.max() - a.min()) / a.max()
            sp_c = (b.max() - b.min()) / b.max()
            rv.append(sp_r)
            cv.append(sp_c)
            print("  %-7s %-7s | %5.3f %5.3f %5.3f      | %5.3f %5.3f %5.3f      | %.3f vs %.3f"
                  % (g, w, a[0], a[1], a[2], b[0], b[1], b[2], sp_r, sp_c))
        print()
    rv, cv = np.array(rv), np.array(cv)
    print("  mean chroma  rendered %.3f   computed %.3f" % (rv.mean(), cv.mean()))
    # were they correlated before? measure now, as the regression guard
    corr = np.corrcoef(rv, cv)[0, 1]
    print("  correlation of per-tile chroma: %.3f" % corr)
    ok = rv.mean() > 0.05 and cv.mean() > 0.05 and corr > 0.3
    print("  VERDICT: %s" % ("rendered grid now tracks the computed colours"
                             if ok else "STILL DIVERGENT"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
