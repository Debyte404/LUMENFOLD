"""check_control_chars.py -- catch LaTeX written through a non-raw Python string.

A string like "\\footnotesize" is fine, but "\\footnotesize" typed with a single
backslash in Python becomes FORM FEED + "ootnotesize". TeX sees the form feed as
whitespace and prints "ootnotesize" as ordinary text. Nothing complains: no LaTeX
error, no overfull box, no undefined reference. It is only visible by reading the
rendered page -- and it silently deletes the command, so the table also loses its
font size.

Same trap for \\v (vertical tab), \\b (backspace), \\a (bell), \\r (return), \\0 (NUL).

Scan every source file for control bytes that are not tab/newline/return and report
the line and the reconstructed text. --fix rewrites them to the intended escape.
"""
import argparse
import glob
import io
import os

# byte -> the two characters it was meant to be
REPAIRS = {
    "\x0c": "\\f", "\x0b": "\\v", "\x08": "\\b", "\x07": "\\a",
    "\x00": "\\0", "\x0d": "\\r",
}
# \x0d (CR) is only a problem when not followed by LF
ALLOWED = {"\t", "\n"}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GLOBS = ["docs/paper/**/*.tex", "docs/paper/*.tex", "docs/paper/*.cls",
         "docs/paper/*.sty", "docs/paper/*.bib"]
TEXT_EXT = (".tex", ".cls", ".sty", ".bib", ".py", ".md")


def scan(paths):
    findings = []
    for p in sorted(set(paths)):
        try:
            raw = io.open(p, "rb").read().decode("utf-8")
        except Exception:
            continue
        for n, line in enumerate(raw.split("\n"), 1):
            for ch, fix in REPAIRS.items():
                if ch in line:
                    if ch == "\r":
                        continue
                    idx = line.find(ch)
                    findings.append((p, n, repr(ch), fix, line[max(0, idx - 30):idx + 30]))
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--all", action="store_true", help="scan the whole repo, not just the paper")
    a = ap.parse_args()

    paths = []
    for g in (GLOBS if not a.all else ["**/*"]):
        paths += glob.glob(f"{ROOT}/{g}", recursive=True)
    paths = [p for p in paths if p.endswith(TEXT_EXT) and "_pp." not in p]

    found = scan(paths)
    if not found:
        print("  no stray control characters in %d files" % len(set(paths)))
        return 0

    print("  %d stray control character(s):" % len(found))
    for p, n, ch, fix, ctx in found:
        print("    %s:%d  %s should be %r" % (os.path.relpath(p, ROOT), n, ch, fix))
        print("       context: %r" % ctx)

    if a.fix:
        changed = 0
        for p in sorted(set(f[0] for f in found)):
            t = io.open(p, "rb").read().decode("utf-8")
            for ch, fix in REPAIRS.items():
                if ch in t:
                    t = t.replace(ch, fix)
            io.open(p, "wb").write(t.encode("utf-8"))
            changed += 1
        print("  repaired %d file(s)" % changed)
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
