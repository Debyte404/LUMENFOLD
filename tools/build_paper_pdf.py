"""build_paper_pdf.py -- compile the CGF paper.

Two engines work and are both supported, because they exercise the class
differently:

  tectonic   a single binary that resolves packages from its own bundle. No
             installation, so this is the default and the one the committed PDF
             is built with.
  pdflatex   MiKTeX, the engine the EG class is written for. The template
             branches on \\ifpdf, so under pdfLaTeX it takes its intended pdftex
             graphics path rather than the XeTeX workaround tectonic needs.
             Requires MiKTeX plus the class's dependencies (see
             tools/pdftex_bringup.py, which resolves them automatically).

Both produce 23 pages with no unresolved references and no overfull boxes, so
the choice is operational rather than editorial.

Run:  <system python> tools/build_paper_pdf.py [--engine tectonic|pdflatex] [--keep]
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

ROOT = "D:/ValueProjects/caustics"
PAPER = f"{ROOT}/docs/paper"
TECTONIC = os.path.expandvars(r"%LOCALAPPDATA%\Temp\tectonic_bin\tectonic.exe")
MIKTEX_BIN = "D:/MiKTeX/miktex/bin/x64"
PDFLATEX = f"{MIKTEX_BIN}/pdflatex.exe"
BIBTEX = f"{MIKTEX_BIN}/bibtex.exe"


def find_tectonic():
    if os.path.exists(TECTONIC):
        return TECTONIC
    for c in ("tectonic", "tectonic.exe"):
        p = shutil.which(c)
        if p:
            return p
    return None


def pages_of(pdf):
    try:
        from pypdf import PdfReader
        return len(PdfReader(pdf).pages)
    except Exception:
        data = open(pdf, "rb").read()
        counts = [int(m) for m in re.findall(rb"/Count\s+(\d+)", data)]
        return max(counts) if counts else None


def build_tectonic(keep):
    tec = find_tectonic()
    if not tec:
        print("tectonic not found. Download:")
        print("  https://github.com/tectonic-typesetting/tectonic/releases")
        return None, 2
    # Always keep intermediates: check_paper.py verifies every \label reached
    # main.aux, and tectonic only writes the .aux to disk when they are kept.
    cmd = [tec, "-X", "compile", "main.tex", "--outdir", PAPER,
           "--keep-intermediates"]
    print("+", " ".join(cmd))
    r = subprocess.run(cmd, cwd=PAPER, capture_output=True, text=True,
                       timeout=3600)
    return r.stdout + r.stderr, r.returncode


def build_pdflatex():
    if not os.path.exists(PDFLATEX):
        print(f"pdflatex not found at {PDFLATEX}")
        print("Install MiKTeX (see tools/pdftex_bringup.py for the dependencies).")
        return None, 2
    env = dict(os.environ)
    env["PATH"] = MIKTEX_BIN + os.pathsep + env.get("PATH", "")
    log = ""
    steps = [(PDFLATEX, "-interaction=nonstopmode", "main.tex"),
             (BIBTEX, "main"),
             (PDFLATEX, "-interaction=nonstopmode", "main.tex"),
             (PDFLATEX, "-interaction=nonstopmode", "main.tex")]
    rc = 0
    for cmd in steps:
        print("+", os.path.basename(cmd[0]), " ".join(cmd[1:]))
        r = subprocess.run(cmd, cwd=PAPER, capture_output=True, text=True,
                           timeout=1800, env=env)
        log += (r.stdout or "") + (r.stderr or "")
        rc = r.returncode
    return log, rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=("tectonic", "pdflatex"),
                    default="tectonic")
    ap.add_argument("--keep", action="store_true",
                    help="(tectonic only; intermediates are kept regardless)")
    a = ap.parse_args()

    log, rc = (build_tectonic(a.keep) if a.engine == "tectonic"
               else build_pdflatex())
    if log is None:
        return rc

    errs = [l for l in log.splitlines()
            if l.startswith("error:") or l.startswith("! ")]
    warns = [l for l in log.splitlines()
             if re.search(r"Overfull|LaTeX Warning|Package .* Warning", l)]
    print(f"engine {a.engine} exit {rc}")
    if errs:
        print(f"--- {len(errs)} error lines ---")
        for l in errs[:25]:
            print("  " + l[:140])
    ov = [l for l in warns if "Overfull" in l]
    print(f"overfull boxes: {len(ov)}")
    for l in ov[:8]:
        print("  " + l[:140])

    pdf = f"{PAPER}/main.pdf"
    if os.path.exists(pdf):
        n = pages_of(pdf)
        print(f"\nPDF: {pdf}  {os.path.getsize(pdf)/1024:.0f} KiB  pages: {n}")
        if n:
            print(f"PAGE COUNT = {n}")
        return 0
    print("\nNO PDF PRODUCED")
    print(log[-2500:])
    return 1


if __name__ == "__main__":
    sys.exit(main())
