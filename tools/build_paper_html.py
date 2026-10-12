"""build_paper_html.py -- render docs/PAPER.md as a self-contained, printable
research paper (docs/PAPER.html): markdown -> HTML, LaTeX math left for
MathJax, figures inlined as base64 so the file is portable.

No LaTeX distribution is installed on this machine, so HTML+MathJax is the
publishable artefact; the browser's print-to-PDF produces a paper-shaped PDF
with the maths typeset.

Run:  <system python> tools/build_paper_html.py
"""
import base64
import io
import os
import re

from markdown_it import MarkdownIt

ROOT = "D:/ValueProjects/caustics"
SRC = f"{ROOT}/docs/PAPER.md"
DST = f"{ROOT}/docs/PAPER.html"
FIGDIR = f"{ROOT}/docs/figures"


def inline_figures(html):
    """Replace <img src="figures/x.png"> with a base64 data URI."""
    def repl(m):
        src = m.group(1)
        path = os.path.join(FIGDIR, os.path.basename(src))
        if not os.path.exists(path):
            print(f"  WARNING missing figure {path}")
            return m.group(0)
        b64 = base64.b64encode(open(path, "rb").read()).decode()
        return f'src="data:image/png;base64,{b64}"'
    return re.sub(r'src="figures/([^"]+)"', repl, html)


def protect_math(md_text):
    """Pull $...$ / $$...$$ out before markdown parsing so markdown cannot
    mangle underscores and asterisks inside equations, then restore after."""
    store = []

    def stash(m):
        store.append(m.group(0))
        return f"@@MATH{len(store) - 1}@@"

    # display first, then inline
    md_text = re.sub(r"\$\$(.+?)\$\$", stash, md_text, flags=re.S)
    md_text = re.sub(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)", stash, md_text, flags=re.S)
    return md_text, store


def restore_math(html, store):
    for i, raw in enumerate(store):
        # $$..$$ -> \[ .. \] ; $..$ -> \( .. \)
        if raw.startswith("$$"):
            body = raw[2:-2].strip()
            out = "\\[" + body + "\\]"
        else:
            body = raw[1:-1].strip()
            out = "\\(" + body + "\\)"
        html = html.replace(f"@@MATH{i}@@", out)
    return html


CSS = """
:root { --ink:#111; --mut:#555; --rule:#ddd; --acc:#c0392b; }
html { -webkit-text-size-adjust:100%; }
body { margin:0 auto; max-width:46rem; padding:3.2rem 1.6rem 6rem;
  font:16px/1.62 "Charter","Georgia","Times New Roman",serif; color:var(--ink);
  background:#fff; text-align:left; }
h1 { font-size:1.72rem; line-height:1.24; margin:0 0 .5rem; letter-spacing:-.01em; }
h2 { font-size:1.22rem; margin:2.6rem 0 .7rem; padding-bottom:.28rem;
  border-bottom:1px solid var(--rule); }
h3 { font-size:1.03rem; margin:1.7rem 0 .5rem; }
h4 { font-size:.97rem; margin:1.3rem 0 .4rem; font-style:italic; font-weight:600; }
p { margin:.72rem 0; }
a { color:var(--acc); text-decoration:none; }
strong { font-weight:600; }
em { font-style:italic; }
hr { border:0; border-top:1px solid var(--rule); margin:2.4rem 0; }
blockquote { margin:1.1rem 0; padding:.7rem 1rem; background:#faf7f2;
  border-left:3px solid var(--acc); font-size:.94rem; }
code { font:13px/1.5 "Cascadia Mono","Consolas",monospace; background:#f4f4f4;
  padding:.1rem .3rem; border-radius:3px; }
pre { background:#f7f7f8; border:1px solid var(--rule); border-radius:5px;
  padding:.8rem 1rem; overflow-x:auto; font-size:12.5px; line-height:1.5; }
pre code { background:none; padding:0; }
img { max-width:100%; height:auto; display:block; margin:1.1rem auto .4rem;
  border:1px solid var(--rule); border-radius:4px; }
figure { margin:1.4rem 0; }
table { border-collapse:collapse; width:100%; margin:1.1rem 0; font-size:.9rem; }
th,td { border:1px solid var(--rule); padding:.36rem .55rem; text-align:left; }
th { background:#f7f7f8; font-weight:600; }
td:first-child { white-space:nowrap; }
ul,ol { margin:.7rem 0 .7rem 1.3rem; padding:0; }
li { margin:.28rem 0; }
.meta { color:var(--mut); font-size:.9rem; margin:.2rem 0 1.8rem; }
mjx-container { overflow-x:auto; overflow-y:hidden; }
@media print {
  body { max-width:none; padding:0; font-size:10.5pt; }
  h2 { page-break-after:avoid; }
  img,table,pre,figure { page-break-inside:avoid; }
  a { color:var(--ink); }
}
"""

HEAD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wave-Corrected Caustics: A Comparative Evaluation</title>
<script>
window.MathJax = {
  tex: { inlineMath: [['\\\\(','\\\\)']], displayMath: [['\\\\[','\\\\]']],
         tags: 'ams' },
  options: { skipHtmlTags: ['script','noscript','style','textarea','pre','code'] }
};
</script>
<script id="MathJax-script" async
  src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
<style>%s</style>
</head><body>
""" % CSS

FOOT = """
</body></html>
"""


def main():
    md_text = io.open(SRC, encoding="utf-8").read()
    md_text, store = protect_math(md_text)
    md = MarkdownIt("gfm-like").enable("table")
    html = md.render(md_text)
    html = restore_math(html, store)
    html = inline_figures(html)
    io.open(DST, "w", encoding="utf-8", newline="\n").write(HEAD + html + FOOT)
    n_fig = len(re.findall(r"data:image/png;base64", html))
    print(f"wrote {DST}")
    print(f"  math spans: {len(store)}   inlined figures: {n_fig}")
    print(f"  bytes: {os.path.getsize(DST):,}")


if __name__ == "__main__":
    main()
