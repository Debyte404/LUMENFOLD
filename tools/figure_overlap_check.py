"""figure_overlap_check.py -- find colliding text inside every figure PDF.

The paper-level overlap check found nothing because figure text lives in the figure
PDFs, not in the paper's own text stream. A reader sees the collision all the same:
fig2(b) had its y-axis label "ray counts (unnormalised)" printed through the rotated
annotation "counts: gamma = 0.4 for display".

Geometry, not substrings: extract each text span with its box and intersect. Also
flags text that runs outside the figure's own canvas, which is how a label gets
clipped at the trim.
"""
import glob
import os

import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIGDIR = f"{ROOT}/docs/paper/figures"

OVERLAP_X = 1.0     # pt of horizontal overlap before it counts
OVERLAP_Y = 4.0     # pt of vertical overlap (text leading is ~7pt, so 4pt is real)


def main():
    total = 0
    for f in sorted(glob.glob(f"{FIGDIR}/*.pdf")):
        d = pymupdf.open(f)
        found = []
        for page in d:
            words = page.get_text("words")     # x0,y0,x1,y1,word,...
            for i in range(len(words)):
                for j in range(i + 1, len(words)):
                    a, b = words[i], words[j]
                    if a[4] == b[4]:
                        continue
                    ox = min(a[2], b[2]) - max(a[0], b[0])
                    oy = min(a[3], b[3]) - max(a[1], b[1])
                    if ox > OVERLAP_X and oy > OVERLAP_Y:
                        found.append((round(ox, 1), round(oy, 1), a[4], b[4]))
        # text pushed off the canvas
        clipped = []
        for page in d:
            r = page.rect
            for w in page.get_text("words"):
                if w[0] < -1 or w[2] > r.width + 1 or w[1] < -1 or w[3] > r.height + 1:
                    clipped.append(w[4])
        if found or clipped:
            print("  %s" % os.path.basename(f))
            for ox, oy, a, b in found[:8]:
                print("     OVERLAP  %-24r x %-24r  (%.1f x %.1f pt)" % (a, b, ox, oy))
                total += 1
            if clipped:
                print("     CLIPPED  %s" % ", ".join(repr(c) for c in clipped[:8]))
                total += 1
    print("  ---")
    print("  %d figure text problems" % total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
