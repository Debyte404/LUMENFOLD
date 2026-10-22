"""check_dual_format.py -- prove the CGF and IEEE editions carry the same paper.

Checks three things:
  1. The ordered body-section list is identical after removing the format-
     specific frontmatter.
  2. The two abstracts are identical after whitespace normalisation.
  3. Every canonical value in docs/CLAIMS.md appears in both source trees.

Prints DUAL-FORMAT OK on success and exits 1 on the first failure.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CGF = ROOT / "docs" / "paper"
IEEE = ROOT / "docs" / "paper-ieee"
CLAIMS = ROOT / "docs" / "CLAIMS.md"


def body_list(main_tex, prefix):
    text = main_tex.read_text(encoding="utf-8")
    out = []
    for item in re.findall(r"\\input\{([^}]+)\}", text):
        item = item.replace("\\", "/")
        if not item.startswith(prefix):
            continue
        item = item[len(prefix):]
        if item in ("frontmatter", "sections/frontmatter"):
            continue
        out.append(item)
    return out


def abstract(frontmatter):
    text = frontmatter.read_text(encoding="utf-8")
    m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", text, re.S)
    if not m:
        raise SystemExit(f"no abstract in {frontmatter}")
    return " ".join(m.group(1).split())


def source_text(root):
    chunks = []
    for path in sorted(root.rglob("*.tex")):
        chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def main():
    for p in (CGF / "main.tex", IEEE / "main.tex", CLAIMS):
        if not p.exists():
            print(f"MISSING: {p}")
            return 1

    a = body_list(CGF / "main.tex", "sections/")
    b = body_list(IEEE / "main.tex", "../paper/sections/")
    if a != b:
        print("BODY MISMATCH")
        print("  CGF :", a)
        print("  IEEE:", b)
        return 1

    aa = abstract(CGF / "sections" / "frontmatter.tex")
    bb = abstract(IEEE / "sections" / "frontmatter.tex")
    if aa != bb:
        print("ABSTRACT MISMATCH")
        print("  CGF :", aa[:500])
        print("  IEEE:", bb[:500])
        return 1

    claims = []
    for line in CLAIMS.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(C\d\d)\s*\|.*?\|\s*([^|]+?)\s*\|", line)
        if m:
            claims.append((m.group(1), m.group(2).strip()))
    if not claims:
        print("NO CLAIMS PARSED from", CLAIMS)
        return 1

    shared = "\n".join(
        p.read_text(encoding="utf-8")
        for p in sorted((CGF / "sections").glob("*.tex")))
    cgf_text = source_text(CGF)
    ieee_text = source_text(IEEE) + "\n" + shared
    missing = []
    for cid, value in claims:
        for token in re.findall(r"-?\d+(?:\.\d+)?", value):
            for name, text in (("CGF", cgf_text), ("IEEE", ieee_text)):
                if not re.search(r"(?<![\d.])" + re.escape(token)
                                 + r"(?![\d.])", text):
                    missing.append(f"{cid} {token!r} absent from {name}")
    if missing:
        print("CLAIM VALUE MISSING")
        for line in missing:
            print("  " + line)
        return 1

    print(f"sections: {len(a)} shared")
    print(f"claims:   {len(claims)} checked in both editions")
    print("DUAL-FORMAT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
