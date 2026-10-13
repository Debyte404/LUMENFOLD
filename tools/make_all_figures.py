"""make_all_figures.py -- regenerate every paper figure, then lint them.

FIVE producers write the figures. Several of them exist as separate scripts only
because their predecessors were wrong in ways that were easier to fix in a dedicated
script than to patch in place:

  tools/make_paper_figures_pdf.py   figs 2, 4, 5, 6, 7, 8, 9, 10
  tools/make_fig1_scene.py          fig 1  (scene: section, geometry, light path)
  tools/fix_fig3_airy.py            fig 3  (the Airy profile and its divergence)
  tools/make_colour_figure.py       fig 11 (colour: channels, medium, sun)
  tools/make_red_media_figure.py    fig 12 (tinted-medium renders)

This driver owns the order, so the set is never rebuilt out of order: when two tools
write the same file, whichever runs last is what gets published, and that is not a
property anyone should have to remember.

It ends by running figure_lint.py, and fails if any figure fails. That is the point:
a figure that violates the design spec -- wrong width, non-serif font, tiny text,
colliding labels, clipped text, low dpi, transparency -- stops the build rather than
reaching a reader. Every figure defect in this paper so far was found by a human eye
after the fact; this is what replaces that.

Run:  python tools/make_all_figures.py [--skip-lint]
"""
import glob
import os as _os
import re
import subprocess
import sys
import time

_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
ROOT = _ROOT
PY = sys.executable

STEPS = [
    ("tools/make_paper_figures_pdf.py", "figures 2, 4-10"),
    ("tools/make_fig1_scene.py",        "figure 1 (scene)"),
    ("tools/fix_fig3_airy.py",          "figure 3 (Airy)"),
    ("tools/make_colour_figure.py",     "figure 11 (colour)"),
    ("tools/make_red_media_figure.py",  "figure 12 (tinted media)"),
]


def main():
    skip_lint = "--skip-lint" in sys.argv

    for tool, what in STEPS:
        t0 = time.time()
        r = subprocess.run([PY, f"{ROOT}/{tool}"], cwd=ROOT,
                           capture_output=True, text=True, timeout=7200)
        dt = time.time() - t0
        ok = r.returncode == 0
        print(f"  {'ok  ' if ok else 'FAIL'} {tool:<34} {what:<24} {dt:5.1f}s")
        if not ok:
            print(r.stdout[-1500:])
            print(r.stderr[-1500:])
            return 1

    # every figure the paper \includegraphics must exist
    tex = open(f"{ROOT}/docs/paper/main.tex", encoding="utf-8").read()
    for f in glob.glob(f"{ROOT}/docs/paper/sections/*.tex"):
        tex += open(f, encoding="utf-8").read()
    want = sorted(set(re.findall(r"includegraphics\[[^\]]*\]\{figures/([^}]+)\}", tex)))
    missing = [w for w in want if not _os.path.exists(f"{ROOT}/docs/paper/figures/{w}")]
    print(f"\n  {len(want)} figures referenced by the paper, "
          f"{len(want) - len(missing)} present")
    if missing:
        print(f"  MISSING: {missing}")
        return 1

    if skip_lint:
        print("\n  lint skipped (--skip-lint)")
        return 0

    print()
    r = subprocess.run([PY, f"{ROOT}/tools/figure_lint.py"], cwd=ROOT,
                       capture_output=True, text=True, timeout=900)
    print(r.stdout)
    if r.returncode != 0:
        print("  FIGURE LINT FAILED -- a figure does not meet the spec, not shipping it")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
