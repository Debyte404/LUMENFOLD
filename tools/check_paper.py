"""check_paper.py -- verify the paper's references, labels and source integrity.

Checks four things a submitted paper must not have:
  1. \\ref/\\eqref/\\autoref targets that are never \\label-ed;
  2. \\cite keys with no matching entry in refs.bib;
  3. bibliography entries that are never cited;
  4. labels that exist in the source but never make it into the compiled .aux.

Check 4 exists because of a real failure. A prose-editing script replaced a
multi-line anchor by first flattening all newlines to spaces, which collapsed
one section file to a single line. Because that line began with a '%' comment
rule, LaTeX treated the ENTIRE section as a comment: the section silently
disappeared from the PDF and every reference into it printed as "??". Checks
1-3 all passed, because the labels were present in the source. A source-only
check cannot see this class of bug, so this one also inspects the .aux.
"""
import glob
import io
import os
import re
import sys


# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

ROOT = _ROOT
PAPER = f"{ROOT}/docs/paper"
REPO = ROOT
SRC = [f"{PAPER}/main.tex"] + sorted(glob.glob(f"{PAPER}/sections/*.tex"))


def read(f):
    return io.open(f, encoding="utf-8").read()


def main():
    text = "\n".join(read(f) for f in SRC)
    problems = []

    # ---- 1. references have labels -------------------------------------
    labels = set(re.findall(r"\\label\{([^}]+)\}", text))
    refs = set()
    for m in re.finditer(r"\\(?:ref|eqref|autoref|Cref|cref)\{([^}]+)\}", text):
        refs |= {k.strip() for k in m.group(1).split(",") if k.strip()}
    missing_refs = sorted(refs - labels)

    # ---- 2 and 3. citations --------------------------------------------
    used = set()
    for m in re.finditer(r"\\cite\{([^}]+)\}", text):
        used |= {k.strip() for k in m.group(1).split(",") if k.strip()}
    bib = set(re.findall(r"@\w+\s*\{\s*([^,\s]+)\s*,", read(f"{PAPER}/refs.bib")))
    missing_cites = sorted(used - bib)
    uncited = sorted(bib - used)

    # ---- 4a. source files are not collapsed ----------------------------
    for f in SRC:
        lines = read(f).splitlines()
        longest = max((len(l) for l in lines), default=0)
        if len(lines) < 12 or longest > 3000:
            problems.append(
                f"COLLAPSED SOURCE: {os.path.basename(f)} has {len(lines)} lines, "
                f"longest {longest} chars (a flattened file starting with '%' "
                f"comments out the whole section)")

    # ---- 4b. every label reached the compiled .aux ---------------------
    aux = f"{PAPER}/main.aux"
    if os.path.exists(aux):
        aux_text = read(aux)
        in_aux = set(re.findall(r"\\newlabel\{([^}]+)\}", aux_text))
        not_compiled = sorted(labels - in_aux)
        if not_compiled:
            problems.append(
                f"{len(not_compiled)} labels never reached main.aux (the section "
                f"may be commented out or excluded): {not_compiled[:12]}")
    else:
        print("note: main.aux absent, skipping the compiled-label check")

    # ---- 4c. every tool the paper names actually exists ---------------
    flat = text.replace("\\_", "_")
    named = sorted(set(re.findall(r"(?:tools|out)/([A-Za-z0-9_]+\.py)", flat)))
    absent = [n for n in named if not os.path.exists(f"{REPO}/tools/{n}")
              and not os.path.exists(f"{REPO}/out/{n}")]
    if absent:
        problems.append(
            f"{len(absent)} scripts named in the paper do not exist: {absent}")

    # ---- 4d. the title and author actually reached page 1 ----------------
    # \maketitle is not automatic: the class typesets the title block only when it
    # is called. Omitting it compiles cleanly, keeps every reference valid and
    # produces a full-length PDF whose first page has no title at all -- which is
    # how it survived every other check in this file, including the layout and
    # page-count ones. So the title is checked against the rendered page.
    try:
        import pymupdf
        pdf = f"{PAPER}/main.pdf"
        if os.path.exists(pdf):
            page1 = pymupdf.open(pdf)[0].get_text()
            m = re.search(r"\\title(?:\[[^\]]*\])?[%\s]*\{(.*?)\}", text, re.S)
            if m:
                raw = re.sub(r"\\\\|\[|\]|\{|\}", " ", m.group(1))
                tw = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z-]{4,}", raw)}
                pw = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z-]{4,}", page1)}
                missing = sorted(tw - pw)
                # Word SETS, not a contiguous probe: the rendered title carries
                # commas and line breaks between the words, so a substring test
                # fails on a correct page. A tolerance of two words absorbs
                # hyphenation and ligature differences.
                if tw and len(missing) > 2:
                    problems.append(
                        f"the title is missing from page 1 of the PDF ({len(missing)} "
                        f"of {len(tw)} title words absent: {missing[:6]}); "
                        f"is \\maketitle called?")
            # Same separator trap as \title: the class's template wraps, so the
            # brace does not follow the optional short form directly.
            au = re.search(r"\\author(?:\[[^\]]*\])?[%\s]*\{", text)
            if au and "\\maketitle" not in text:
                problems.append("\\maketitle is never called: the title page has "
                                "no title and no author block")
    except ImportError:
        print("note: pymupdf absent, skipping the title-page check")

    print(f"sources checked      : {len(SRC)}")
    print(f"labels defined       : {len(labels)}")
    print(f"reference targets    : {len(refs)}")
    print(f"citations used       : {len(used)}")
    print(f"bibliography entries : {len(bib)}")
    print(f"scripts named        : {len(named)}")
    print()
    print(f"references with no label : {len(missing_refs)}  {missing_refs}")
    print(f"citations not in refs.bib: {len(missing_cites)}  {missing_cites}")
    print(f"bib entries never cited  : {len(uncited)}  {uncited}")
    print()
    for p in problems:
        print("  PROBLEM: " + p)
    ok = not (missing_refs or missing_cites or problems)
    print("PAPER REFS OK" if ok else "PAPER REFERENCES HAVE PROBLEMS")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
