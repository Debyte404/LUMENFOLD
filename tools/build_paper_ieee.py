"""build_paper_ieee.py -- compile the IEEEtran edition and gate the result.

Runs pdflatex -> bibtex -> pdflatex -> pdflatex in docs/paper-ieee/, then fails
on an engine error or an overfull box. Prints the page count so a layout change
is visible even when the build is clean.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "paper-ieee"
PDFLATEX = shutil.which("pdflatex")
BIBTEX = shutil.which("bibtex")


def run(cmd, env):
    print("+", " ".join(cmd))
    p = subprocess.run(cmd, cwd=DOC, env=env, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if p.stdout:
        print(p.stdout, end="")
    return p.returncode


def main():
    if not PDFLATEX or not BIBTEX:
        print("pdflatex/bibtex not on PATH; install MiKTeX and IEEEtran")
        return 1
    env = os.environ.copy()
    env["BIBINPUTS"] = os.pathsep.join(
        [str(ROOT / "docs" / "paper"), str(DOC)])
    env["TEXINPUTS"] = os.pathsep.join([str(DOC), ""])

    rc = run([PDFLATEX, "-interaction=nonstopmode", "main.tex"], env)
    if rc != 0:
        print("BUILD FAILED: first pdflatex pass")
        return 1
    rc = run([BIBTEX, "main"], env)
    if rc != 0:
        print("BUILD FAILED: bibtex")
        return 1
    for _ in range(2):
        rc = run([PDFLATEX, "-interaction=nonstopmode", "main.tex"], env)
        if rc != 0:
            print("BUILD FAILED: pdflatex pass")
            return 1

    log = (DOC / "main.log").read_text(encoding="utf-8", errors="replace")
    errors = [l for l in log.splitlines() if l.startswith("! ")]
    overfull = [l for l in log.splitlines()
                if l.startswith("Overfull \\hbox") or l.startswith("Overfull \\vbox")]
    if errors:
        print(f"BUILD FAILED: {len(errors)} engine error line(s)")
        for l in errors[:5]:
            print("  " + l)
        return 1
    if overfull:
        print(f"BUILD FAILED: {len(overfull)} overfull box(es)")
        for l in overfull[:5]:
            print("  " + l)
        return 1

    m = re.search(r"Output written on main\.pdf \((\d+) pages", log)
    pages = int(m.group(1)) if m else "?"
    print(f"PDF: {DOC / 'main.pdf'}  pages: {pages}")
    print(f"PAGE COUNT = {pages}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
