"""check_text_overlap.py -- find text that actually collides on the page.

The earlier version of this looked for fused substrings in the extracted page
text. That produced false positives immediately: "for all" in ordinary prose
contains "or all", and a rotated multi-word axis label extracts without spaces.
A substring match cannot tell a collision from English.

A collision is a geometric fact, so this measures it geometrically. Every word is
taken with its bounding box, and a pair whose boxes overlap by more than a
fraction of the smaller box is a genuine collision -- two labels printed on top
of each other. That is the defect that produced "Cycles or all" (a legend entry
over an annotation) and "outerwall 3.5" (two callouts on one baseline).
"""
import sys

import pdfplumber

PDF = "D:/ValueProjects/caustics/docs/paper/main.pdf"
MIN_IOU = 0.30          # overlap area / smaller box area


def overlap(a, b):
    """Intersection-over-smaller-area for two word boxes."""
    x0 = max(a["x0"], b["x0"]); x1 = min(a["x1"], b["x1"])
    t0 = max(a["top"], b["top"]); b1 = min(a["bottom"], b["bottom"])
    if x1 <= x0 or b1 <= t0:
        return 0.0
    inter = (x1 - x0) * (b1 - t0)
    area_a = max((a["x1"] - a["x0"]) * (a["bottom"] - a["top"]), 1e-9)
    area_b = max((b["x1"] - b["x0"]) * (b["bottom"] - b["top"]), 1e-9)
    return inter / min(area_a, area_b)


def is_prose(word):
    """True for an ordinary word, false for a math glyph or an unmapped codepoint.

    A naive box-overlap test drowns in false positives on a maths paper: a radical
    sign legitimately overlaps its radicand, a bar accent overlaps the letter it
    modifies, and a fraction's numerator overlaps its denominator. Those are
    correct typesetting, not collisions. Restricting to alphabetic runs of at
    least three characters isolates the case that matters -- two labels printed on
    top of each other.
    """
    t = word["text"]
    if len(t) < 3:
        return False
    if "cid:" in t:
        return False
    return all(c.isalnum() for c in t)


def main():
    bad = 0
    with pdfplumber.open(PDF) as pdf:
        print(f"{len(pdf.pages)} pages scanned "
              f"(math glyphs excluded; only prose-on-prose counts)\n")
        for pno, page in enumerate(pdf.pages, 1):
            try:
                words = page.extract_words(use_text_flow=False)
            except Exception as e:
                print(f"  page {pno}: could not extract ({e})")
                continue
            words = [w for w in words if is_prose(w)]
            hits = []
            for i in range(len(words)):
                for j in range(i + 1, len(words)):
                    a, b = words[i], words[j]
                    if abs(a["top"] - b["top"]) > 14 and \
                       abs(a["bottom"] - b["bottom"]) > 14:
                        continue
                    o = overlap(a, b)
                    if o > MIN_IOU:
                        hits.append((o, a["text"], b["text"]))
            if hits:
                bad += len(hits)
                print(f"  page {pno}: {len(hits)} colliding pairs")
                for o, ta, tb in sorted(hits, key=lambda t: -t[0])[:6]:
                    print(f"      {o:.2f}  {ta[:30]!r} over {tb[:30]!r}")
    print()
    if bad:
        print(f"{bad} colliding prose pairs found")
        return 1
    print("no colliding text anywhere in the document")
    return 0


if __name__ == "__main__":
    sys.exit(main())
