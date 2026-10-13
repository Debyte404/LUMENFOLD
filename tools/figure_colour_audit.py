"""Audit the colour usage in the paper's figures.

Two things a print/publisher cares about, both measurable:

  * greyscale separation -- if two series differ only in hue and not in luminance,
    they collapse into the same grey when printed or read by a colourblind reader.
    Rule of thumb: adjacent series should differ by >= 10% in relative luminance.
  * pure-channel primaries -- #ff0000 / #00ff00 / #0000ff are the classic
    red-green pair that ~8% of men cannot separate at all.

Scans the vector figure PDFs in docs/paper/figures/.
"""
import glob
import os
import re
from collections import Counter

import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIGDIR = f"{ROOT}/docs/paper/figures"


def lum(rgb):
    """Rec.709 relative luminance, 0..1."""
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def main():
    files = sorted(glob.glob(f"{FIGDIR}/*.pdf"))
    print("  %-22s %-6s %-34s %s" % ("figure", "cols", "top colours (hex, share)", "notes"))
    for f in files:
        d = pymupdf.open(f)
        cnt = Counter()
        for page in d:
            for dr in page.get_drawings():
                for key in ("fill", "color"):
                    c = dr.get(key)
                    if c is None:
                        continue
                    r, g, b = [int(round(v * 255)) for v in c]
                    if (r, g, b) in ((255, 255, 255), (0, 0, 0)):
                        continue
                    cnt[(r, g, b)] += 1
        if not cnt:
            print("  %-22s %-6d %s" % (os.path.basename(f), 0, "(no colour fills)"))
            continue
        tot = sum(cnt.values())
        top = cnt.most_common(5)
        shown = " ".join(
            "%02x%02x%02x:%.0f%%" % (r, g, b, 100 * n / tot) for (r, g, b), n in top)
        notes = []
        # red-green pair under the classic confusion
        keys = [k for k, _ in cnt.most_common(8)]
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                a, b2 = keys[i], keys[j]
                da = max(a) - min(a)
                db = max(b2) - min(b2)
                if da > 120 and db > 120:
                    if a[0] > 180 and a[1] < 90 and b2[1] > 180 and b2[0] < 90:
                        notes.append("RED+GREEN pair")
        # greyscale collapse among the top series
        lums = sorted(round(lum([c / 255 for c in k]), 3) for k in keys)
        for i in range(len(lums) - 1):
            if lums[i + 1] - lums[i] < 0.10:
                notes.append("greys collapse %.2f/%.2f" % (lums[i], lums[i + 1]))
                break
        print("  %-22s %-6d %-34s %s" % (os.path.basename(f), len(cnt), shown,
                                         ", ".join(notes) or "ok"))


if __name__ == "__main__":
    main()
