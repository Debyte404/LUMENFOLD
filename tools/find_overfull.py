r"""find_overfull.py -- identify WHAT is overflowing, not just how much.

check_layout.py reports magnitudes. That is not enough to fix anything: an
"Overfull hbox (62.81pt too wide)" with no context is a number, not a defect
report. This prints the source location and the words of the offending box.

Note on the format: tectonic prefixes every warning with

    warning: sections/<file>:<line>: Overfull \hbox (...) ...

so a regex anchored at the start of the line matches nothing and reports a clean
document. That is the same trap as reading a stale .aux: the check has to be
written against the actual output format, not the format one expects.
"""
import os
import re
import subprocess


# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

ROOT = _ROOT
PAPER = f"{ROOT}/docs/paper"
TEC = os.path.expandvars(r"%LOCALAPPDATA%\Temp\tectonic_bin\tectonic.exe")

OVER = re.compile(r"Overfull \\hbox \(([0-9.]+)pt too wide\)(?:\s*(.*))?")
LOC = re.compile(r"warning: ([^:]+:[0-9]+):")


def main():
    r = subprocess.run([TEC, "-X", "compile", "main.tex", "--outdir", ".",
                        "--keep-intermediates"],
                       cwd=PAPER, capture_output=True, text=True, timeout=3600)
    lines = (r.stdout + r.stderr).splitlines()

    hits = []
    for i, line in enumerate(lines):
        m = OVER.search(line)
        if not m:
            continue
        loc = LOC.search(line)
        # TeX prints the box contents over the following lines; strip control
        # sequences so the words are readable
        chunk = " ".join(lines[i:i + 6])
        chunk = re.sub(r"\\[a-zA-Z@]+\*?(\[[^\]]*\])?", " ", chunk)
        chunk = re.sub(r"Overfull.*?warning:", " ", chunk)
        chunk = re.sub(r"[{}]", " ", chunk)
        chunk = re.sub(r"\s+", " ", chunk).strip()
        hits.append((float(m.group(1)), loc.group(1) if loc else "?",
                     m.group(2) or "", chunk[:200]))

    # tectonic reports each once per pass, so de-duplicate
    seen, uniq = set(), []
    for w, loc, tail, text in hits:
        k = (round(w, 2), loc)
        if k in seen:
            continue
        seen.add(k)
        uniq.append((w, loc, tail, text))

    print(f"{len(uniq)} distinct overfull boxes "
          f"({len(hits)} warnings incl. repeat passes)\n")
    for w, loc, tail, text in sorted(uniq, key=lambda t: -t[0]):
        print(f"[{w:7.2f} pt too wide]  {loc}   {tail.strip()[:40]}")
        print(f"   {text[:190]}")
        print()
    if not uniq:
        print("no overfull boxes: every line fits its measure")
    return 0 if not uniq else 1


if __name__ == "__main__":
    raise SystemExit(main())
