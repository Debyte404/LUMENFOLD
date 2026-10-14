"""Build a small text-only PDF of the paper's prose for detector submission.

Sapling accepts a PDF or Word file. Submitting the typeset paper would drag in figure
captions, tables and the bibliography, none of which is the prose being judged, so this
writes just the sample text as a paginated PDF with selectable text.

Uses PyMuPDF's built-in fonts, so there is no extra dependency.
"""
import os
import re
import textwrap

import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "out", "paper_sample.txt")
OUT = os.path.join(ROOT, "out", "paper_sample.pdf")

text = open(SRC, encoding="utf-8").read()
# keep the prose readable: wrap at a column width the font can hold
lines = []
for para in text.split("\n"):
    para = para.strip()
    if not para:
        continue
    lines.extend(textwrap.wrap(para, width=96) or [""])
    lines.append("")

doc = pymupdf.open()
fontsize, leading, margin, top = 9.0, 11.5, 52.0, 56.0
W, H = 595.0, 842.0            # A4
i = 0
while i < len(lines):
    page = doc.new_page(width=W, height=H)
    y = top
    while i < len(lines) and y < H - margin:
        if lines[i]:
            page.insert_text((margin, y), lines[i], fontsize=fontsize, fontname="helv")
        y += leading
        i += 1

doc.save(OUT)
doc.close()
print("  wrote %s" % os.path.relpath(OUT, ROOT))
print("  %d pages, %.1f KB" % (len(pymupdf.open(OUT)), os.path.getsize(OUT) / 1024))
