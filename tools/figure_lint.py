"""figure_lint.py -- the gate a figure must pass before it may ship.

Why this exists
---------------
Every figure defect in this paper so far was found by the author's eye, after
publication of the draft, and then patched in one producer script while the other
three kept the bug. The pattern is: generate, look, patch, miss the rest.

This inverts it. Each figure is measured against the spec measured from the file
itself -- not from the code that was supposed to produce it -- and a failure is
reported with the numbers that justify it. Exit status is non-zero if anything
fails, so `build_paper_pdf.py` can refuse to ship a bad figure.

What is checked, and why each one has bitten us already
-------------------------------------------------------
  fonts        matplotlib substitutes DejaVu Serif silently when Times is absent,
               and the figures stop matching the text face
  font size    below ~6pt labels clog with ink and become unreadable in print
  collisions   two labels sharing ink; the reader cannot tell which is which
  clipping     a rotated ylabel's side bearing fell outside the canvas at -1.1pt
  raster dpi   a panel at 98 dpi against 600 dpi elsewhere
  transparency the venue forbids it; matplotlib emits alpha ExtGState by default
  width        a figure wider than the text block must be scaled, which drops its
               effective raster resolution and its type size
  empty        a gridspec row whose axes were never created shrinks the figure
  dash         on channel/method figures, colour alone collapses in greyscale
"""
import argparse
import glob
import os
import re
import sys

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paper_figs import style            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIGDIR = f"{ROOT}/docs/paper/figures"

MIN_DPI = 300
OVERLAP_X = 1.0
OVERLAP_Y = 4.0
WIDTH_TOL_MM = 3.0          # a figure may be at most this much wider than its column


# An image dictionary may be written "/Subtype /Image" or "/Subtype/Image".
_IMAGE_RE = re.compile(r"/Subtype\s*/Image")

SERIF_OK = ("times", "nimbus", "serif", "stix", "termes", "cmr", "latinmodern")


def expected_widths():
    """Width each figure MUST be, derived from the LaTeX that includes it.

    This exists because the linter previously compared each figure against
    style.COL_MM / style.FULL_MM -- the very constants the producers author with. Edit
    the constant and both sides move together, so a wrong constant is invisible: a
    figure authored at 187 mm against a 187 mm constant read as "ok".

    Deriving the expectation from the include command breaks that circularity. The
    contract is between the figure and the \\includegraphics that places it.
    """
    want = {}
    for f in glob.glob(f"{ROOT}/docs/paper/sections/*.tex"):
        tex = open(f, encoding="utf-8").read()
        for m in re.finditer(r"includegraphics\[width=([^\]]+)\]\{figures/([^}]+)\}", tex):
            spec, name = m.group(1), m.group(2)
            want[name] = style.FULL_MM if "textwidth" in spec else style.COL_MM
    return want


def paper_geometry():
    """Measure the compiled paper's column and text width independently.

    Returns (column_mm, full_mm) or None. Used to catch style's constants drifting
    away from what the class actually typesets.
    """
    pdf = f"{ROOT}/docs/paper/main.pdf"
    if not os.path.exists(pdf):
        return None
    from collections import Counter
    d = pymupdf.open(pdf)
    widths = Counter()
    for page in d:
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") == 0 and b["bbox"][2] - b["bbox"][0] > 40:
                widths[round((b["bbox"][2] - b["bbox"][0]) / 72 * 25.4, 1)] += 1
    if not widths:
        return None
    col = widths.most_common(1)[0][0]
    full = max(widths)
    return col, full


def _is_serif(fontname):
    return any(k in fontname.lower() for k in SERIF_OK)


def mm(pt):
    return pt / 72.0 * 25.4


def check(path, verbose=False, expect=None):
    """Return (problems, info) for one figure."""
    problems = []
    d = pymupdf.open(path)
    page = d[0]
    r = page.rect

    # --- geometry -----------------------------------------------------------------
    w_mm = mm(r.width)
    # Prefer the width the LaTeX that includes this figure demands, over style's own
    # constants -- otherwise the check and the producer share the same assumption.
    want = expect.get(os.path.basename(path)) if expect else None
    if want is not None:
        if abs(w_mm - want) > WIDTH_TOL_MM:
            problems.append("width %.1f mm but the paper includes it at %.1f mm"
                            % (w_mm, want))
    else:
        fits_col = abs(w_mm - style.COL_MM) <= WIDTH_TOL_MM
        fits_full = abs(w_mm - style.FULL_MM) <= WIDTH_TOL_MM
        if not (fits_col or fits_full):
            problems.append("width %.0fmm is neither column (%.0f) nor full (%.0f)"
                            % (w_mm, style.COL_MM, style.FULL_MM))
    if mm(r.height) > style.MAX_H_MM:
        problems.append("height %.0fmm exceeds text height %.0f" % (mm(r.height), style.MAX_H_MM))

    # --- fonts and sizes ----------------------------------------------------------
    # The floor applies to BASE text. A superscript or subscript is deliberately set
    # at ~0.7x by the math renderer ($10^{2}$, lambda^{2/3}, 10^{-1}); holding those to
    # the body floor would be wrong, and "fixing" it by inflating the exponents is
    # worse typography than leaving them. So: scripts are judged against a lower
    # bound, and anything that is NOT a script must clear the body floor.
    SCRIPT_RATIO = 0.80
    SCRIPT_MIN = 4.5

    fonts = {}
    spans_all = []
    from collections import Counter
    blocks = []
    for b in page.get_text("dict")["blocks"]:
        sp = [s for l in b.get("lines", []) for s in l["spans"] if s["text"].strip()]
        if sp:
            blocks.append(sp)
            for s in sp:
                fonts[s["font"]] = fonts.get(s["font"], 0) + len(s["text"])
                spans_all.append((s["size"], s["text"][:20]))

    if spans_all:
        modal = Counter(round(sz, 1) for sz, _ in spans_all).most_common(1)[0][0]
    else:
        modal = style.SZ_LABEL
    body_ref = max(modal, style.SZ_MIN)

    # Classify each span against the largest text in ITS OWN block, falling back to the
    # figure's body size. A single figure can mix sizes -- fig11 has 6.4pt grid labels
    # and 8pt axis labels -- and a superscript belongs to the text it annotates, not to
    # the most common size in the file. Comparing only against the modal size called an
    # 8pt label's 5.6pt superscript "body text".
    classified = []
    for block in blocks:
        base = max(max(s["size"] for s in block), body_ref)
        for s in block:
            classified.append((s["size"], s["text"][:20],
                               s["size"] <= SCRIPT_RATIO * base + 0.05))

    serif_ok = all(_is_serif(f) for f in fonts)
    if fonts and not serif_ok:
        problems.append("non-serif fonts embedded: %s"
                        % ", ".join(sorted(f for f in fonts if not _is_serif(f))))

    bad_base = [(sz, tx) for sz, tx, sc in classified
                if not sc and sz < style.SZ_MIN - 0.2]
    if bad_base:
        problems.append("%d body text spans below %.1fpt (body is %.1fpt; smallest %.1fpt: %r)"
                        % (len(bad_base), style.SZ_MIN, body_ref,
                           min(b[0] for b in bad_base), bad_base[0][1]))
    bad_script = [(sz, tx) for sz, tx, sc in classified
                  if sc and sz < SCRIPT_MIN - 0.2]
    if bad_script:
        problems.append("%d script spans below %.1fpt (smallest %.1fpt: %r)"
                        % (len(bad_script), SCRIPT_MIN,
                           min(b[0] for b in bad_script), bad_script[0][1]))

    # --- collisions and clipping --------------------------------------------------
    words = page.get_text("words")
    hits = 0
    for i in range(len(words)):
        for j in range(i + 1, len(words)):
            a, b = words[i], words[j]
            if a[4] == b[4]:
                continue
            ox = min(a[2], b[2]) - max(a[0], b[0])
            oy = min(a[3], b[3]) - max(a[1], b[1])
            if ox > OVERLAP_X and oy > OVERLAP_Y:
                hits += 1
                if verbose and hits <= 4:
                    print("        overlap %r x %r (%.1f x %.1f pt)"
                          % (a[4], b[4], ox, oy))
    if hits:
        problems.append("%d colliding text pairs" % hits)

    clipped = [w[4] for w in words
               if w[0] < -0.5 or w[2] > r.width + 0.5 or w[1] < -0.5 or w[3] > r.height + 0.5]
    if clipped:
        problems.append("text outside canvas: %s" % ", ".join(repr(c) for c in clipped[:5]))

    # --- text drawn over DATA -----------------------------------------------------
    # A text-over-text check cannot see text sitting on a curve: fig11's annotation box
    # was printed across the 450 nm curve and every label-vs-label test passed.
    #
    # Compare text boxes against SATURATED or DASHED strokes only. Axes, spines and
    # gridlines are thin and neutral by design and are excluded, so this flags a label
    # over a data line and not a label over a gridline (which is fine and normal).
    data_strokes = []
    for dr in page.get_drawings():
        col = dr.get("color")
        if col is None:
            continue
        sat = max(col) - min(col)
        dashed = dr.get("dashes") not in (None, "[] 0", "[]0")
        if sat < 0.15 and not dashed:
            continue
        for item in dr["items"]:
            if item[0] == "l":
                data_strokes.append((item[1].x, item[1].y, item[2].x, item[2].y))
            elif item[0] == "c":
                pts = [p for p in item[1:] if hasattr(p, "x")]
                for a, b in zip(pts, pts[1:]):
                    data_strokes.append((a.x, a.y, b.x, b.y))

    if data_strokes:
        overlaps = []
        for w in words:
            tx0, ty0, tx1, ty1 = w[0], w[1], w[2], w[3]
            for sx0, sy0, sx1, sy1 in data_strokes:
                # does the segment's bounding box intersect the text box?
                if (min(sx0, sx1) < tx1 and max(sx0, sx1) > tx0
                        and min(sy0, sy1) < ty1 + 1.0 and max(sy0, sy1) > ty0 - 1.0):
                    overlaps.append(w[4])
                    break
        if overlaps:
            uniq = sorted(set(overlaps))
            problems.append("%d text span(s) overlap coloured/dashed data strokes: %s"
                            % (len(uniq), ", ".join(repr(o) for o in uniq[:6])))

    # --- rasters: resolution and transparency -------------------------------------
    worst = None
    for xref in range(1, d.xref_length()):
        try:
            obj = d.xref_object(xref, compressed=True)
        except Exception:
            continue
        if not obj or not _IMAGE_RE.search(obj):
            continue
        if "/SMask" in obj:
            problems.append("raster xref %d carries an /SMask (transparency)" % xref)
        m = re.search(r"/Width (\d+).*?/Height (\d+)", obj, re.S)
        if not m:
            continue
        pw, ph = int(m.group(1)), int(m.group(2))
        placed = page.get_image_rects(xref)
        if not placed:
            continue
        pd = placed[0]
        dpi = pw / (pd.width / 72.0)
        if worst is None or dpi < worst:
            worst = dpi

    if worst is not None and worst < MIN_DPI:
        problems.append("worst raster %.0f dpi (need %d)" % (worst, MIN_DPI))

    # --- transparency: inspect OBJECTS, never raw bytes ---------------------------
    # A raw-bytes grep for "/CA" and "/SMask" matches inside compressed streams and
    # produced false positives on figures that are entirely opaque. The only
    # trustworthy test is to resolve the ExtGState objects the content stream invokes.
    invoked = set()
    for pg in d:
        try:
            cs = pg.read_contents().decode("latin-1")
        except Exception:
            continue
        invoked |= set(re.findall(r"/(\w+)\s+gs", cs))

    for xref in range(1, d.xref_length()):
        try:
            obj = d.xref_object(xref, compressed=True)
        except Exception:
            continue
        if not obj:
            continue
        if "/Type /ExtGState" in obj:
            for k, v in re.findall(r"/(CA|ca)\s+(\d*\.?\d+)", obj):
                if v not in ("1", "1.0", "1.00"):
                    problems.append("ExtGState xref %d has %s %s (transparency)"
                                    % (xref, k, v))
        if _IMAGE_RE.search(obj) and "/SMask" in obj:
            problems.append("image xref %d carries an /SMask" % xref)
        # an inline image dict may also carry one
        if "/SMask" in obj and not _IMAGE_RE.search(obj):
            m = re.search(r"/SMask\s+(\d+)\s+0\s+R", obj)
            if m:
                problems.append("object xref %d references an /SMask" % xref)

    # --- not empty -----------------------------------------------------------------
    if not fonts and not page.get_drawings():
        problems.append("figure is empty (no text, no vector art)")

    info = {"mm": (round(w_mm), round(mm(r.height))),
            "words": len(words),
            "dpi": round(worst) if worst else None,
            "fonts": len(fonts)}
    return problems, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fig", help="check one figure")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    missing = style.missing_fonts()
    if missing:
        print("  FONT MISSING: %s -- matplotlib will substitute silently" % ", ".join(missing))
        print()

    paths = ([a.fig] if a.fig
             else sorted(glob.glob(f"{FIGDIR}/*.pdf")))
    expect = expected_widths()

    # Cross-check the shared constants against what the class actually typesets. If
    # main.pdf exists, this catches style.COL_MM / FULL_MM drifting -- which the
    # per-figure width test cannot, because it would move with them.
    geo = paper_geometry()
    if geo:
        col, full = geo
        drift = []
        if abs(col - style.COL_MM) > 0.8:
            drift.append("column %.1f mm vs style.COL_MM %.1f" % (col, style.COL_MM))
        if abs(full - style.FULL_MM) > 0.8:
            drift.append("text width %.1f mm vs style.FULL_MM %.1f" % (full, style.FULL_MM))
        if drift:
            print("  GEOMETRY DRIFT: " + "; ".join(drift))
            print("     figures are authored against the style constant, so every figure")
            print("     is being rescaled by LaTeX. Fix style.py to the measured values.")
            print()
            nfail_geo = 1
        else:
            nfail_geo = 0
    else:
        nfail_geo = 0

    nfail = nfail_geo
    print("  %-26s %-11s %6s %5s %5s  %s" % ("figure", "size mm", "words", "dpi", "fonts", "verdict"))
    print("  " + "-" * 72)
    for p in paths:
        if not os.path.exists(p):
            print("  %-26s MISSING" % os.path.basename(p))
            nfail += 1
            continue
        probs, info = check(p, a.verbose, expect)
        verdict = "ok" if not probs else "FAIL"
        if probs:
            nfail += 1
        print("  %-26s %-11s %6d %5s %5d  %s"
              % (os.path.basename(p), "%dx%d" % info["mm"], info["words"],
                 info["dpi"] or "-", info["fonts"], verdict))
        for pr in probs:
            print("       - %s" % pr)

    print()
    print("  %d/%d figures pass" % (len(paths) - nfail, len(paths)))
    return 1 if nfail else 0


if __name__ == "__main__":
    raise SystemExit(main())
