"""check_paper.py -- verify no dangling references or citations.

Checks three things a submitted paper must not have:
  1. \\ref/\\eqref/\\autoref targets that are never \\label-ed;
  2. \\cite keys with no matching entry in refs.bib;
  3. bibliography entries that are never cited.
Reads the LaTeX sources directly, so it works whether or not an intermediate
.log was kept.
"""
import glob
import io
import os
import re

PAPER = "D:/ValueProjects/caustics/docs/paper"
SRC = glob.glob(f"{PAPER}/main.tex") + sorted(glob.glob(f"{PAPER}/sections/*.tex"))


def read(f):
    return io.open(f, encoding="utf-8").read()


def main():
    text = "\n".join(read(f) for f in SRC)

    # 1. references
    labels = set(re.findall(r"\\label\{([^}]+)\}", text))
    refs = set()
    for m in re.finditer(r"\\(?:ref|eqref|autoref|Cref|cref)\{([^}]+)\}", text):
        refs |= {k.strip() for k in m.group(1).split(",") if k.strip()}
    missing_refs = sorted(refs - labels)

    # 2. and 3. citations
    used = set()
    for m in re.finditer(r"\\cite\{([^}]+)\}", text):
        used |= {k.strip() for k in m.group(1).split(",") if k.strip()}
    bibtext = read(f"{PAPER}/refs.bib")
    bib = set(re.findall(r"@\w+\s*\{\s*([^,\s]+)\s*,", bibtext))
    missing_cites = sorted(used - bib)
    uncited = sorted(bib - used)

    print(f"sources checked      : {len(SRC)}")
    print(f"labels defined       : {len(labels)}")
    print(f"reference targets    : {len(refs)}")
    print(f"citations used       : {len(used)}")
    print(f"bibliography entries : {len(bib)}")
    print()
    print(f"references with no label : {len(missing_refs)}  {missing_refs}")
    print(f"citations not in refs.bib: {len(missing_cites)}  {missing_cites}")
    print(f"bib entries never cited  : {len(uncited)}  {uncited}")
    ok = not (missing_refs or missing_cites)
    print()
    print("PAPER REFS OK" if ok else "PAPER REFS HAVE PROBLEMS")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
