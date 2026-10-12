"""build_paper_pdf.py -- compile the CGF paper with tectonic.

The official Eurographics / Computer Graphics Forum class (egpubl.cls) is what
this paper must be typeset in, and no TeX distribution was present on this
machine. Tectonic is used instead of MiKTeX/TeX Live: it is a single binary that
resolves packages from its own bundle on demand, so it compiles the EG class
without a multi-gigabyte install.

Run:  <system python> tools/build_paper_pdf.py [--keep]
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

ROOT = "D:/ValueProjects/caustics"
PAPER = f"{ROOT}/docs/paper"
TEC = os.path.expandvars(r"%LOCALAPPDATA%\Temp\tectonic_bin\tectonic.exe")


def find_tectonic():
    if os.path.exists(TEC):
        return TEC
    for c in ("tectonic", "tectonic.exe"):
        p = shutil.which(c)
        if p:
            return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="keep intermediate files")
    a = ap.parse_args()

    tec = find_tectonic()
    if not tec:
        print("tectonic not found. Download:")
        print("  https://github.com/tectonic-typesetting/tectonic/releases")
        return 2

    cmd = [tec, "-X", "compile", "main.tex", "--outdir", PAPER]
    if a.keep:
        cmd.append("--keep-intermediates")
    print("+", " ".join(cmd))
    r = subprocess.run(cmd, cwd=PAPER, capture_output=True, text=True, timeout=3600)

    log = r.stdout + r.stderr
    errs = [l for l in log.splitlines()
            if l.startswith("error") or "! " in l[:4] or "Undefined" in l]
    warns = [l for l in log.splitlines()
             if re.search(r"Warning|Overfull|Underfull", l)]

    print(f"exit {r.returncode}")
    if errs:
        print(f"--- {len(errs)} error lines ---")
        for l in errs[:40]:
            print("  " + l)
    if warns:
        print(f"--- {len(warns)} warnings (first 12) ---")
        for l in warns[:12]:
            print("  " + l)

    pdf = f"{PAPER}/main.pdf"
    if os.path.exists(pdf):
        size = os.path.getsize(pdf)
        # page count from the PDF's page tree
        pages = None
        try:
            from pypdf import PdfReader
            pages = len(PdfReader(pdf).pages)
        except Exception:
            data = open(pdf, "rb").read()
            counts = [int(m) for m in re.findall(rb"/Count\s+(\d+)", data)]
            pages = max(counts) if counts else None
        print(f"\nPDF: {pdf}  {size/1024:.0f} KiB  pages: {pages}")
        if r.returncode == 0 and pages:
            print(f"PAGE COUNT = {pages}")
    else:
        print("\nNO PDF PRODUCED")
        print(log[-3000:])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
