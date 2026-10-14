r"""check_layout.py -- find text that runs past the margins.

Tectonic does not write a .log file, so the usual `grep Overfull main.log` finds
nothing and it is tempting to conclude the layout is clean. The warnings are in
the compiler's stdout; this captures them and reports the worst offenders.

An "Overfull \hbox" is a line wider than its measure, which is exactly what a
reader sees as text running into the margin or into the neighbouring column. It
is the defect class that produced the reproduction table's overlapping columns,
so checking it is the difference between "the build succeeded" and "the page is
readable".
"""
import os
import re
import subprocess
import sys


# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

ROOT = _ROOT
PAPER = f"{ROOT}/docs/paper"
TEC = os.path.expandvars(r"%LOCALAPPDATA%\Temp\tectonic_bin\tectonic.exe")


def main():
    if not os.path.exists(TEC):
        print(f"tectonic not found at {TEC}")
        return 2
    r = subprocess.run([TEC, "-X", "compile", "main.tex", "--outdir", ".",
                        "--keep-intermediates"],
                       cwd=PAPER, capture_output=True, text=True, timeout=3600)
    log = r.stdout + r.stderr

    over = re.findall(r"Overfull \\hbox \(([0-9.]+)pt too wide\)", log)
    ovbox = re.findall(r"Overfull \\vbox \(([0-9.]+)pt too high\)", log)
    under = re.findall(r"Underfull \\hbox \(badness ([0-9]+)\)", log)
    latex_warn = [l for l in log.splitlines() if l.startswith("LaTeX Warning")]
    pkg_warn = [l for l in log.splitlines()
                if re.match(r"Package .* Warning", l)]

    # each overfull box, with the source lines it came from, when given
    details = re.findall(
        r"Overfull \\hbox \(([0-9.]+)pt too wide\)(?:[^\n]*?at lines ([0-9]+)--([0-9]+))?",
        log)

    print(f"Overfull  \\hbox : {len(over)}")
    if over:
        worst = sorted(details, key=lambda t: -float(t[0]))[:15]
        for w, la, lb in worst:
            where = f"  lines {la}--{lb}" if la else ""
            print(f"   {float(w):7.2f} pt too wide{where}")
        total = sum(float(w) for w in over)
        print(f"   total overflow {total:.1f} pt across {len(over)} boxes")
    print(f"Overfull  \\vbox : {len(ovbox)}")
    print(f"Underfull \\hbox : {len(under)}")
    print(f"LaTeX warnings  : {len(latex_warn)}")
    for l in latex_warn[:8]:
        print(f"   {l[:100]}")
    print(f"Package warnings: {len(pkg_warn)}")
    for l in pkg_warn[:6]:
        print(f"   {l[:100]}")

    bad = bool(over or ovbox or latex_warn)
    print()
    print("LAYOUT HAS OVERFLOW" if bad else "LAYOUT CLEAN")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
