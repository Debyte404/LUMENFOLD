"""Extract a clean plain-text sample of the paper for AI-detector submission.

Detectors cap input (commonly 5k-15k characters), so submit the part that carries the
argument: title, abstract, introduction and the opening of the method. Strip LaTeX so a
detector is not scoring markup.
"""
import glob
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from scan_ai_tells import prose                    # noqa: E402

ORDER = ["intro.tex", "kinematics.tex", "cgcaustics.tex", "current.tex"]
FILES = {os.path.basename(p): p for p in
         glob.glob(os.path.join(ROOT, "docs", "paper", "sections", "*.tex"))}

chunks = []

# Frontmatter is title/author/affiliation markup and scores as neither prose nor AI.
# Take the abstract from it, starting at the word "abstract", then the body sections.
fm = FILES.get("frontmatter.tex")
if fm:
    t = prose(fm)
    m = re.search(r"\babstract\b(.*)", t, re.S)
    if m:
        chunks.append("Abstract. " + m.group(1).strip())

for name in ORDER:
    p = FILES.get(name)
    if not p:
        continue
    t = prose(p)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{2,}", "\n\n", t).strip()
    chunks.append(t)

text = "\n\n".join(chunks)
# a detector wants readable paragraphs, not one line per LaTeX line
text = re.sub(r"\n(?!\n)", " ", text)
text = re.sub(r"\s{2,}", " ", text)
# residual markup that survived the LaTeX strip: [..] option lists, \\ breaks, ^1
text = re.sub(r"\[\s*[^\]]{0,60}\]", "", text)
text = re.sub(r"\\\\", " ", text)
text = re.sub(r"\^\{?\d+\}?", "", text)
text = re.sub(r"%\s*\S*", " ", text)
text = re.sub(r"\s{2,}", " ", text).strip()

out = os.path.join(ROOT, "out", "paper_sample.txt")
os.makedirs(os.path.dirname(out), exist_ok=True)
io.open(out, "w", encoding="utf-8").write(text)

words = len(re.findall(r"[A-Za-z][A-Za-z'\-]+", text))
print("  wrote %s" % os.path.relpath(out, ROOT))
print("  %d words, %d characters" % (words, len(text)))
print()
print("  first 480 characters:")
print("  " + text[:480].replace("\n", "\n  "))
