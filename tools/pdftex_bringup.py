"""pdftex_bringup.py -- resolve the EG class's package dependencies for pdfLaTeX.

MiKTeX ships a basic set and fetches the rest, but it needs a repository passed
per command and it does not resolve a missing .sty itself in a non-interactive
shell: it stops with "File `X.sty' not found" and no PDF.

This runs pdfLaTeX, reads the missing package out of the log, installs it from the
repository, and repeats. Each round should clear at least one dependency.
"""
import os
import re
import subprocess
import sys

PAPER = "D:/ValueProjects/caustics/docs/paper"
LOG = "D:/ValueProjects/caustics/out/pdftex_try.log"
MKTEX = "D:/MiKTeX/miktex/bin/x64"
PDFLATEX = MKTEX + "/pdflatex.exe"        # Windows cannot resolve the bare name
MIKTEX = MKTEX + "/miktex.exe"
BIBTEX = MKTEX + "/bibtex.exe"
REPO = "https://mirror.niser.ac.in/ctan/systems/win32/miktex/tm/packages/"
# a .sty name is not always its MiKTeX package name
ALIAS = {"lastpage": "lastpage", "algorithmic": "algorithms",
         "algpseudocode": "algorithmicx", "ifpdf": "ifpdf",
         "amsthm": "amscls", "amsmath": "amsmath", "amssymb": "amsfonts",
         "amsfonts": "amsfonts"}


def run(cmd, cwd=None, timeout=900):
    env = dict(os.environ)
    env["PATH"] = MKTEX + os.pathsep + env.get("PATH", "")
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, env=env)


def install(pkg):
    r = run([MIKTEX, "packages", "install", "--repository", REPO, pkg])
    out = (r.stdout + r.stderr).strip().splitlines()
    return out[-1] if out else "?"


def main():
    for round_ in range(1, 41):
        r = run([PDFLATEX, "-interaction=nonstopmode", "main.tex"], cwd=PAPER)
        log = (r.stdout or "") + (r.stderr or "")
        open(LOG, "w", encoding="utf-8", errors="ignore").write(log)

        missing = re.findall(r"File `([^']+)' not found", log)
        if not missing:
            # a real run: bibtex, then two more passes
            run([BIBTEX, "main"], cwd=PAPER)
            run([PDFLATEX, "-interaction=nonstopmode", "main.tex"], cwd=PAPER)
            rr = run([PDFLATEX, "-interaction=nonstopmode", "main.tex"], cwd=PAPER)
            open(LOG, "w", encoding="utf-8", errors="ignore").write(
                (rr.stdout or "") + (rr.stderr or ""))
            ok = os.path.exists(f"{PAPER}/main.pdf")
            print(f"round {round_}: no missing files"
                  f"{'; PDF produced' if ok else '; but NO PDF'}")
            if not ok:
                for l in log.splitlines():
                    if l.startswith("!"):
                        print("   " + l[:120])
            return 0 if ok else 1

        pkg = missing[0]
        name = pkg[:-4] if pkg.endswith(".sty") else pkg
        name = ALIAS.get(name, name)
        print(f"round {round_}: missing {pkg} -> installing {name}")
        print(f"           {install(name)[:90]}")

    print("gave up after 40 rounds")
    return 1


if __name__ == "__main__":
    sys.exit(main())
