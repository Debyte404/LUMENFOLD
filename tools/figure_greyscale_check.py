"""Does each figure separate its series in greyscale by SOMETHING?

Relative luminance alone is the wrong test for a per-channel figure: R, G and B
cannot all be far apart in luminance while still reading as red, green and blue --
which is exactly why accessible practice combines hue with a pattern. So the real
question is: for the series in a figure, is there either a luminance gap of >= 0.10
OR a non-colour pattern (dash, or a hatch fill)?

A hatch is many short parallel strokes rather than a "dashes" entry, so it is
detected by counting short line segments; an earlier version of this check missed it
and reported a figure as collapsing when it separates perfectly well.

Figures whose DATA is a colour ramp (a spectrum, a set of colour swatches) are
reported as such and not judged: greyscale collapse there is inherent to showing
colour, and hiding it would be the wrong fix.
"""
import glob
import os
from collections import Counter

import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIGDIR = f"{ROOT}/docs/paper/figures"


def lum(rgb):
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def analyse(path):
    d = pymupdf.open(path)
    hue = Counter()
    dashes = set()
    short = 0
    rects = 0
    for page in d:
        for dr in page.get_drawings():
            c = dr.get("color")
            if c is not None:
                rgb = tuple(int(round(v * 255)) for v in c)
                if max(rgb) - min(rgb) > 60:
                    hue[rgb] += 1
            dash = dr.get("dashes")
            if dash and dash not in ("[] 0", "[]0"):
                dashes.add(dash)
            r = dr["rect"]
            if r.width * r.height < 6:
                short += 1
            else:
                rects += 1
    return hue, dashes, short, rects


def main():
    print("  %-22s %-4s %-7s %-7s %-8s %s"
          % ("figure", "hue", "minlum", "dashes", "hatch", "verdict"))
    for f in sorted(glob.glob(f"{FIGDIR}/*.pdf")):
        hue, dashes, short, rects = analyse(f)
        if len(hue) < 2:
            continue
        keys = [k for k, _ in hue.most_common(6)]
        lums = sorted(round(lum([c / 255 for c in k]), 3) for k in keys)
        gap = min((lums[i + 1] - lums[i]) for i in range(len(lums) - 1))
        # a hatch shows up as many short strokes relative to solid shapes
        hatched = short > 40
        if gap >= 0.10 or dashes or hatched:
            v = "separates"
        else:
            v = "colour-ramp data" if len(hue) > 20 else "COLLAPSES"
        print("  %-22s %-4d %-7.3f %-7d %-8s %s"
              % (os.path.basename(f), len(hue), gap, len(dashes),
                 "yes" if hatched else "no", v))


if __name__ == "__main__":
    main()
