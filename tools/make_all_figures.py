"""make_all_figures.py -- regenerate every paper figure, in dependency order.

Three tools write the figures and two of them own exactly one file each, because
their predecessors were wrong in ways that were easier to fix in a dedicated
script than to patch in place:

  tools/make_paper_figures_pdf.py   figs 2, 4, 5, 6, 7, 8, 9, 10
  tools/make_fig1_scene.py          fig 1  (scene: section, geometry, light path)
  tools/fix_fig3_airy.py            fig 3  (the Airy profile and its divergence)

The superseded copies of fig 1 and fig 3 inside make_paper_figures_pdf.py were
deleted, and this driver exists so the set is never rebuilt out of order: when
two tools write the same file, whichever runs last is what gets published, and
that is not a property anyone should have to remember.

Run:  python tools/make_all_figures.py
"""
import subprocess
import sys
import time

PY = sys.executable
STEPS = [
    ("tools/make_paper_figures_pdf.py", "figures 2, 4-10"),
    ("tools/make_fig1_scene.py",        "figure 1 (scene)"),
    ("tools/fix_fig3_airy.py",          "figure 3 (Airy)"),
]

ROOT = "D:/ValueProjects/caustics"


def main():
    for tool, what in STEPS:
        t0 = time.time()
        r = subprocess.run([PY, f"{ROOT}/{tool}"], cwd=ROOT,
                           capture_output=True, text=True, timeout=3600)
        dt = time.time() - t0
        ok = r.returncode == 0
        print(f"  {'ok  ' if ok else 'FAIL'} {tool:<34} {what:<22} {dt:5.1f}s")
        if not ok:
            print(r.stdout[-1500:])
            print(r.stderr[-1500:])
            return 1

    # every figure the paper \\includegraphics must exist and be a PDF
    import os
    import re
    tex = ""
    for f in ("main.tex",):
        tex += open(f"{ROOT}/docs/paper/{f}", encoding="utf-8").read()
    import glob
    for f in glob.glob(f"{ROOT}/docs/paper/sections/*.tex"):
        tex += open(f, encoding="utf-8").read()
    want = sorted(set(re.findall(r"includegraphics\[[^\]]*\]\{figures/([^}]+)\}", tex)))
    print(f"\n  {len(want)} figures referenced by the paper:")
    missing = []
    for w in want:
        p = f"{ROOT}/docs/paper/figures/{w}"
        exists = os.path.exists(p)
        if not exists:
            missing.append(w)
        print(f"    {'ok  ' if exists else 'MISSING'} {w}")
    if missing:
        print(f"\n  MISSING: {missing}")
        return 1
    print("\nall figures present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
