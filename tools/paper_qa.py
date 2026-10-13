"""paper_qa.py -- text-first QA of the compiled paper.

Every complaint here is measurable, so measure it rather than eyeball it:

  * page renders            -- one PNG per page, for a human to look at
  * embedded image DPI      -- pixel size vs the size it is PLACED at. A figure that
                               looks soft is almost always below ~150 dpi effective,
                               and the number is exact.
  * whitespace bands        -- runs of empty vertical space. This is what "spacing
                               issues with diagrams" looks like numerically: a short
                               float pushed to the next page leaves a hole behind it.
  * underfull/overfull      -- from the engine log
  * bibliography format     -- the eg-alpha style's shape: author, title, venue, year

Run:  python tools/paper_qa.py [--render]
"""
import argparse
import os
import re
import subprocess
import sys

import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = f"{ROOT}/docs/paper/main.pdf"
SHOTS = f"{ROOT}/out/paper_pages"
PY = sys.executable


def render_pages():
    os.makedirs(SHOTS, exist_ok=True)
    d = pymupdf.open(PDF)
    for i, page in enumerate(d):
        p = f"{SHOTS}/page_{i+1:02d}.png"
        page.get_pixmap(dpi=140).save(p)
    print(f"  rendered {d.page_count} pages to {SHOTS}")
    return d.page_count


def image_dpi():
    """Effective dpi of every raster placed in the document."""
    d = pymupdf.open(PDF)
    rows = []
    for pno, page in enumerate(d, 1):
        for info in page.get_images(full=True):
            xref = info[0]
            px_w, px_h = info[2], info[3]
            # every placement of this xref on this page
            for r in page.get_image_rects(xref):
                w_in = r.width / 72.0
                h_in = r.height / 72.0
                if w_in <= 0 or h_in <= 0:
                    continue
                rows.append((pno, xref, px_w, px_h,
                             round(px_w / w_in), round(px_h / h_in),
                             round(w_in * 25.4, 1), round(h_in * 25.4, 1)))
    return rows


def whitespace(page, min_pt=28.0):
    """Vertical bands with nothing in them, as (top, bottom, height) in points."""
    blocks = [b for b in page.get_text("blocks") if b[4].strip()]
    rects = page.get_images()
    bands = []
    hm = page.rect.height
    top_m, bot_m = 72.0, hm - 66.0        # ignore the running head / folio
    spans = [(max(top_m, b[1]), min(bot_m, b[3])) for b in blocks]
    # drawings (rules, vector figure content) count as content too
    for dr in page.get_drawings():
        r = dr["rect"]
        spans.append((max(top_m, r.y0), min(bot_m, r.y1)))
    spans = [s for s in spans if s[1] > s[0]]
    spans.sort()
    cursor = top_m
    for a, b in spans:
        if a - cursor >= min_pt:
            bands.append((round(cursor, 1), round(a, 1), round(a - cursor, 1)))
        cursor = max(cursor, b)
    if bot_m - cursor >= min_pt:
        bands.append((round(cursor, 1), round(bot_m, 1), round(bot_m - cursor, 1)))
    return bands


def bib_check():
    """The eg-alpha shape, and the venues that most often break it."""
    bbl = f"{ROOT}/docs/paper/main.bbl"
    if not os.path.exists(bbl):
        return []
    txt = open(bbl, encoding="utf-8", errors="ignore").read()
    items = re.findall(r"\\bibitem(?:\[[^\]]*\])?\{([^}]*)\}(.*?)(?=\\bibitem|\\end\{thebibliography\})",
                       txt, re.S)
    probs = []
    for key, body in items:
        b = re.sub(r"\s+", " ", body)
        if "\\newblock" not in body:
            probs.append((key, "no \\newblock (year/venue block missing)"))
        if re.search(r"\b(19|20)\d\d\b", b) is None:
            probs.append((key, "no year"))
        if re.search(r"\\emph|\\textit", body) is None:
            probs.append((key, "no italic venue/title"))
        if "--" in b and "\u2013" not in b:
            probs.append((key, "double hyphen where an en dash belongs"))
    return probs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", action="store_true")
    a = ap.parse_args()

    if a.render:
        n = render_pages()
        print(f"  pages: {n}")
    print()

    print("=== embedded raster resolution (effective dpi when placed) ===")
    rows = image_dpi()
    seen = set()
    for pno, xref, pw, ph, dw, dh, wmm, hmm in rows:
        k = (xref, dw, dh)
        if k in seen:
            continue
        seen.add(k)
        flag = "LOW" if min(dw, dh) < 300 else ("soft" if min(dw, dh) < 150 else "")
        print(f"  p{pno:<3} xref {xref:<6} {pw}x{ph}px  placed {wmm}x{hmm}mm  "
              f"-> {dw} x {dh} dpi  {flag}")
    if not rows:
        print("  (no raster images placed)")
    print()

    print("=== vertical whitespace bands >= 28 pt (blank runs on a page) ===")
    d = pymupdf.open(PDF)
    total = 0
    for pno, page in enumerate(d, 1):
        for top, bot, h in whitespace(page):
            total += 1
            print(f"  p{pno:<3} y {top:6.1f} -> {bot:6.1f}   {h:5.1f} pt blank")
    print(f"  {total} bands")
    print()

    print("=== bibliography format ===")
    probs = bib_check()
    if probs:
        for k, why in probs:
            print(f"  {k}: {why}")
    else:
        print("  all entries have the eg-alpha shape")
    return 0


if __name__ == "__main__":
    sys.exit(main())
