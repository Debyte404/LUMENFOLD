# IEEE Edition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second, peer-reviewable edition of the manuscript under `docs/paper-ieee/` that uses IEEEtran's two-column journal layout and numbered citations, while sharing every body section with the CGF edition so the two cannot disagree on a claim.

**Architecture:** The CGF edition stays the canonical build. `docs/paper-ieee/main.tex` supplies only an IEEE preamble and an IEEE frontmatter, then inputs `../paper/sections/*.tex` for the body, appendix, and references. A parity script checks that the ordered body-section list is identical and that both abstracts carry the same words; the build wrapper refuses to publish a PDF with overfull boxes or engine errors.

**Tech Stack:** pdfLaTeX (MiKTeX), IEEEtran, BibTeX, Python 3.12, pypdf (already available for page counting), the existing `tools/` harness.

---

## File Structure

**Create**
- `docs/paper-ieee/main.tex` — IEEEtran preamble and the shared-body input list.
- `docs/paper-ieee/sections/frontmatter.tex` — IEEE title, author block, abstract, keywords.
- `docs/paper-ieee/README.md` — what the edition is, how it is built, and the shared-body rule.
- `docs/CLAIMS.md` — the canonical quantitative claims and their evidence sections.
- `tools/build_paper_ieee.py` — build wrapper: pdflatex, bibtex, page count, overfull/error gate.
- `tools/check_dual_format.py` — parity gate for the two editions.

**Modify**
- `README.md` — add the IEEE edition link next to the CGF paper link.
- `docs/README.md` — add the IEEE edition to the document index.
- `tools/README.md` — add the two new tools.
- `AGENTS.md` — already contains the hard dual-format rule; update it only if the command names change.
- `docs/EVIDENCE.md` — append a short entry recording that the IEEE edition was built and what was checked (do not rewrite prior sections).

**Do not create**
- A second copy of `docs/paper/sections/*.tex`. Duplicating the body is the failure mode this plan exists to prevent.
- A second `refs.bib`. The IEEE build reads `../paper/refs.bib`.

---

## Task 1: Install and verify the IEEEtran class

**Files:**
- No repository files changed.
- Toolchain: MiKTeX at `D:\MiKTeX\miktex\bin\x64\`.

- [ ] **Step 1: Update the MiKTeX package database**

Run:
```bat
mpm --update-db
```
Expected: `mpm` exits 0 and prints no error. The earlier `kpsewhich` warning about an unchecked update disappears.

- [ ] **Step 2: Install the IEEEtran package**

Run:
```bat
mpm --install=IEEEtran
```
Expected: `mpm` exits 0. If it reports "already installed", continue.

- [ ] **Step 3: Verify both class and bibliography style resolve**

Run:
```bat
kpsewhich IEEEtran.cls
kpsewhich IEEEtran.bst
```
Expected: two absolute paths under `D:\MiKTeX\...`, one ending in `IEEEtran.cls`, one in `IEEEtran.bst`. An empty line means the install failed; stop and record the exact `mpm` output.

- [ ] **Step 4: Commit the toolchain note only if a tracked file changed**

No commit is expected in this task. If `docs/EVIDENCE.md` needs a note about a non-default package version, append it in Task 9, not here.

---

## Task 2: Write the canonical claims register

**Files:**
- Create: `docs/CLAIMS.md`

- [ ] **Step 1: Write the register**

Create `docs/CLAIMS.md` with exactly this content:

```markdown
# Canonical claims

This is the list the dual-format check reads. A claim may be reworded, but its
canonical value must not appear in one edition and be absent from the other.
Every value below is measured in `docs/EVIDENCE.md`; the evidence section is the
authority, not this table.

| ID | Claim | Canonical value | Evidence |
|---|---|---|---|
| C01 | canonical physical fringe width at the fold | 6.8 | EVIDENCE 14.3 |
| C02 | first Airy zero | 15.84 | EVIDENCE 14.3 |
| C03 | renderer display exaggeration | 220 | EVIDENCE 14.5f |
| C05 | solar blur / fringe spacing | 136 | EVIDENCE 14.5f |
| C06 | 40 mm tile correlation, ours / SPPM / Cycles | 0.917 / 0.853 / 0.828 | EVIDENCE 14.8, 19.6 |
| C07 | 5 mm tile correlation, ours / SPPM | 0.721 / 0.722 | EVIDENCE 14.8, 19.6 |
| C08 | ground-truth core coverage, ours / Cycles | 99.9 / 54.7 | EVIDENCE 14.8 |
| C09 | 512^2 production cost, ours / SPPM | 36.2 / 34 | EVIDENCE 17 |
| C12 | interface transport throughput | 96.41 | EVIDENCE 14.5b |
| C13 | field broadening at 1024^2 / 4096^2 | 2.30 / 1.87 | EVIDENCE 14.5c, 14.7 |
| C14 | cusp / fold divergence exponents | -0.3333 / -0.2434 | EVIDENCE 14.5l |
| C15 | Monte Carlo crossover | 262000 | EVIDENCE 17 |
```

- [ ] **Step 2: Check the table is machine-readable**

Run:
```bat
python -c "import re,pathlib; t=pathlib.Path('docs/CLAIMS.md').read_text(); rows=[l for l in t.splitlines() if re.match(r'\|\s*C\d\d\s*\|',l)]; print(len(rows))"
```
Expected: `12`.

- [ ] **Step 3: Commit**

```bat
git add docs/CLAIMS.md
git commit -m "Add canonical claim register for dual-format checks"
```

---

## Task 3: Write the IEEE preamble and shared-body input list

**Files:**
- Create: `docs/paper-ieee/main.tex`

- [ ] **Step 1: Write the file**

Create `docs/paper-ieee/main.tex` with exactly this content:

```latex
%=======================================================================
% Wave-Corrected Caustics over Photon Splatting
% IEEEtran journal edition. The body is shared with docs/paper/.
% Compile: python tools/build_paper_ieee.py
%=======================================================================
\documentclass[journal]{IEEEtran}

\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{cite}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{amsthm}
\usepackage{booktabs}
\usepackage{multirow}
\usepackage{array}
\usepackage{siunitx}
\usepackage{algorithm}
\usepackage{algpseudocode}
\usepackage{xcolor}
\usepackage{url}
\usepackage{graphicx}
\graphicspath{{../paper/figures/}{../paper/}}

\setcounter{secnumdepth}{2}
\sisetup{detect-all,group-separator={,},group-minimum-digits=4,math-micro=\mu,text-micro=$\mu$}

\theoremstyle{plain}
\newtheorem{theoremcounter}{Theorem}
\newtheorem{lemma}[theoremcounter]{Lemma}
\newtheorem{corollary}[theoremcounter]{Corollary}
\newtheorem{proposition}[theoremcounter]{Proposition}
\theoremstyle{definition}
\newtheorem{definition}[theoremcounter]{Definition}
\theoremstyle{remark}
\newtheorem{remark}[theoremcounter]{Remark}
\newtheorem{assumption}[theoremcounter]{Assumption}

\newcommand{\Hm}{\mathbf{H}}
\newcommand{\Jm}{J_{\Hm}}
\newcommand{\fold}{\mathcal{F}}
\newcommand{\recv}{\Omega}
\newcommand{\dir}{\hat{\mathbf{s}}}
\newcommand{\nrm}{\mathbf{n}}
\newcommand{\trn}{\hat{\mathbf{t}}}
\newcommand{\Ai}{\operatorname{Ai}}
\newcommand{\detJ}{\det \Jm}
\newcommand{\dd}{\mathrm{d}}
\newcommand{\order}[1]{\mathcal{O}\!\left(#1\right)}
\DeclareMathOperator{\sinc}{sinc}

\renewcommand{\topfraction}{0.92}
\renewcommand{\bottomfraction}{0.5}
\renewcommand{\textfraction}{0.06}
\renewcommand{\floatpagefraction}{0.7}
\renewcommand{\dbltopfraction}{0.92}
\renewcommand{\dblfloatpagefraction}{0.7}
\setlength{\parskip}{0pt}

\begin{document}

\input{sections/frontmatter}

\input{../paper/sections/intro}
\input{../paper/sections/kinematics}
\input{../paper/sections/cgcaustics}
\input{../paper/sections/current}
\input{../paper/sections/ourway}
\input{../paper/sections/results}
\input{../paper/sections/verification}
\input{../paper/sections/limitations}
\input{../paper/sections/discussion}
\input{../paper/sections/conclusion}
\input{../paper/sections/appendix}

\bibliographystyle{IEEEtran}
\bibliography{../paper/refs}

\end{document}
```

- [ ] **Step 2: Confirm the body list matches the CGF build**

Run:
```bat
python -c "import re,pathlib; a=pathlib.Path('docs/paper/main.tex').read_text(); b=pathlib.Path('docs/paper-ieee/main.tex').read_text(); ca=[x for x in re.findall(r'\\input\{(sections/[^}]+)\}',a) if 'frontmatter' not in x]; cb=[x.replace('../paper/','') for x in re.findall(r'\\input\{(\.\./paper/sections/[^}]+)\}',b)]; print(ca==cb, ca, cb)"
```
Expected: `True` followed by the same 11-element list twice.

- [ ] **Step 3: Do not compile yet**

The frontmatter does not exist; a compile at this point must fail with "File `sections/frontmatter.tex' not found". That failure is expected and is the RED step for Task 4.

---

## Task 4: Write the IEEE frontmatter

**Files:**
- Create: `docs/paper-ieee/sections/frontmatter.tex`

- [ ] **Step 1: Write the IEEE frontmatter**

Create `docs/paper-ieee/sections/frontmatter.tex`:

```latex
%-----------------------------------------------------------------------
% IEEE title, author, abstract, keywords.
% The abstract is the CGF abstract verbatim; the parity check compares the
% whitespace-normalised text of the two abstracts and fails on any drift.
%-----------------------------------------------------------------------
\title{Wave-Corrected Caustics over Photon Splatting: Fold Kinematics,
a Band-Local Airy Correction, and a Comparative Evaluation Against
Production Solvers}

\author{\IEEEauthorblockN{A. Chetri}
\IEEEauthorblockA{Independent researcher\\
GitHub: Debyte404\\
ORCID: 0009-0004-2672-3503\\
Corresponding author}}

\maketitle

\begin{abstract}
Photon-splatting and path-traced caustics are the standard way to render the
light focused by a curved transparent body onto a diffuse receiver. Both
families evaluate a geometric push-forward whose Jacobian determinant vanishes
on the fold locus, so the estimator diverges there, and no amount of sampling
repairs it. We state that failure as a property of the model rather than of the
discretisation, then describe a hybrid estimator in which a geometric quadrature
carries the whole image and a wave-optical correction is applied only inside a
narrowly detected fold band: the band's own geometric energy is redistributed
according to the Airy fold profile $|\Ai(-s/w)|^2$, with a per-channel width
$w_c$ following the $\lambda^{2/3}$ scaling implied by the fold's canonical
form. We first derive the kinematics from scratch --- the ray map, the fold
condition, the normal form of the fold and the wavelength scaling that follows
from it --- and then use that derivation to explain where the standard computer
graphics constructions for caustics succeed and where they necessarily fail.

We evaluate against PBRT-v4 SPPM and Blender Cycles on an identical
scene with measured dispersive indices (water: Daimon \& Masumura 2007; glass:
Rubin 1985), using Mitsuba~3 for qualitative spectral verification.
Against an independent brute-force geometric ground truth of $810{,}000$ explicit
rays, our estimator scores $0.917$ correlation at 40\,mm tiles against $0.853$ (SPPM)
and $0.828$ (Cycles); at 5\,mm tiles the methods tie ($0.721$ vs $0.722$). An
equal-flux Gaussian control demonstrates that coarse-scale correlation is governed
by band-local flux regularisation and energy bounding, while the Airy profile
governs fine sub-pixel chromatic fringes. Internal convergence sweeps show
quadratic grid scaling against our own converged $2048^2$ wave-corrected pass,
while its interface transport throughput measures $\approx 96.4\%$ across internal
refractive interfaces (dominated by Fresnel exit reflection, noting that band-local
flux conservation redistributes the band's own measured energy by construction).
We also analyze chromatic dispersion under absorbing media and non-solar source
spectra: bulk absorption and emission spectra modulate channel throughput linearly,
while the $\lambda^{2/3}$ scaling displaces fringe peaks chromatically across the lit band.

We are explicit about what the method does \emph{not} establish. The correction
is defined for regular fold arcs, and we test the next stratum rather than assuming it:
a cusp requires a Pearcey function in place of the Airy one, and its divergence
exponent differs from the fold's (measured $-0.3333$ against analytic $-1/3$,
where a fold measures $-0.2434$ against $-1/4$). The substitution carries over and
bounds the field where the geometric estimator diverges; the cost does not, by
four orders of magnitude, so we report that measurement rather than a production method.
We also show that a continuous global normalisation of the fold is impossible ---
$|\Ai(-u)|^2$ is not integrable on $\mathbb{R}$ --- which is why the correction
is formulated as a band-local discrete flux ratio. Methodological limitations,
experimental controls (including an equal-flux Gaussian ablation and parameter
sensitivity sweeps), and solver failure modes are explicitly detailed. All solver
source code, verification harnesses, and the Blender integration add-on are
available under the MIT license at \url{https://github.com/Debyte404/LUMENFOLD}.
\end{abstract}

\begin{IEEEkeywords}
caustics, wave optics, photon splatting, photon mapping, SPPM, diffraction,
Airy function, grid-free rendering, comparative evaluation
\end{IEEEkeywords}
```

- [ ] **Step 2: Compile and verify the RED-to-GREEN transition**

Run:
```bat
cd docs\paper-ieee
set BIBINPUTS=..\paper
pdflatex -interaction=nonstopmode main.tex
bibtex main
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex
```
Expected: the first command now finds the frontmatter; the final exit code is 0. `main.pdf` exists. The page count is printed by the final run (for example `Output written on main.pdf (18 pages, ...)`); record it, do not assume it.

- [ ] **Step 3: Check for engine errors before layout**

Run:
```bat
Select-String -Path main.log -Pattern '^! '
```
Expected: no output. If there is an error, fix it before Task 5; an overfull box is not an engine error.

- [ ] **Step 4: Commit**

```bat
git add docs/paper-ieee/main.tex docs/paper-ieee/sections/frontmatter.tex
git commit -m "Add IEEEtran edition with a shared manuscript body"
```

---

## Task 5: Audit tables and figures in the narrower measure

**Files:**
- Modify: `docs/paper-ieee/main.tex` only if a global setting is needed.
- Modify: `docs/paper/sections/*.tex` only when a table is genuinely too wide for one IEEE column; a shared fix must also be checked in the CGF build.

- [ ] **Step 1: Build and list every overfull box**

Run:
```bat
cd docs\paper-ieee
pdflatex -interaction=nonstopmode main.tex > nul
Select-String -Path main.log -Pattern 'Overfull \\hbox' -Context 0,2
```
Expected: a list of `Overfull \hbox (...) in paragraph at lines A--B`. An empty list means the layout already fits.

- [ ] **Step 2: Map each overfull line to its source file**

The line numbers in the log refer to the file last opened. Search the `main.log` backwards from the overfull line for the nearest `(sections/...` or `(../paper/sections/...` marker:

```bat
Select-String -Path main.log -Pattern '\(\.\./paper/sections/|\(sections/' | Select-Object -Last 15
```
Expected: the section file that contains the overfull paragraph. Record the file and line pair in the commit message or a scratch note.

- [ ] **Step 3: Fix wide tables by promoting them to `table*`**

For a table whose natural width exceeds `\columnwidth`, change:
```latex
\begin{table}[tbp]
```
to:
```latex
\begin{table*}[tp]
```
and the matching `\end{table}` to `\end{table*}`. Keep the `\caption` and `\label` unchanged. Apply this only to tables that actually overflow; do not promote every table.

- [ ] **Step 4: Fix a wide figure by using its existing full-width form**

The shared sections already use `figure*` for the 177 mm figures and `figure` for the 84 mm ones. If a `figure` overflows, do not shrink the image below its generated size; change it to `figure*` in the shared section only if the CGF build still has 0 overfull boxes after the change.

- [ ] **Step 5: Rebuild and require zero overfull boxes**

Run:
```bat
pdflatex -interaction=nonstopmode main.tex > nul
Select-String -Path main.log -Pattern 'Overfull \\hbox'
```
Expected: no output. If a fix in a shared section changed the CGF layout, run `python tools/build_paper_pdf.py --engine pdflatex` from the repository root and require 0 overfull boxes there too.

- [ ] **Step 6: Commit**

```bat
git add docs/paper-ieee/main.tex docs/paper/sections
git commit -m "Fit the shared tables and figures to the IEEE measure"
```

---

## Task 6: Add the IEEE build wrapper

**Files:**
- Create: `tools/build_paper_ieee.py`

- [ ] **Step 1: Write the wrapper**

Create `tools/build_paper_ieee.py`:

```python
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
    env["TEXINPUTS"] = os.pathsep.join(
        [str(ROOT / "docs" / "paper"), str(DOC), ""])

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
    overfull = [l for l in log.splitlines() if l.startswith("Overfull \\hbox")]
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
```

- [ ] **Step 2: Run the wrapper**

Run:
```bat
python tools/build_paper_ieee.py
```
Expected: exit 0, `PAGE COUNT = <n>`, no overfull lines. If it fails, fix the exact reported line; do not relax the gate.

- [ ] **Step 3: Commit**

```bat
git add tools/build_paper_ieee.py
git commit -m "Add an IEEE build wrapper with a layout gate"
```

---

## Task 7: Add the dual-format parity check

**Files:**
- Create: `tools/check_dual_format.py`

- [ ] **Step 1: Write the checker**

Create `tools/check_dual_format.py`:

```python
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
```

- [ ] **Step 2: Run the checker**

Run:
```bat
python tools/check_dual_format.py
```
Expected: `DUAL-FORMAT OK`. If it fails, fix the missing section, abstract drift, or claim value; do not weaken the check.

- [ ] **Step 3: Prove the check fails on drift**

Temporarily change one number in `docs/paper-ieee/sections/frontmatter.tex` (for example `0.917` to `0.918`), run the checker, and confirm it exits 1 with `ABSTRACT MISMATCH`. Revert the change and re-run; expected `DUAL-FORMAT OK`.

- [ ] **Step 4: Commit**

```bat
git add tools/check_dual_format.py
git commit -m "Add a dual-format parity check"
```

---

## Task 8: Wire the IEEE edition into the documentation

**Files:**
- Create: `docs/paper-ieee/README.md`
- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `tools/README.md`

- [ ] **Step 1: Write the IEEE README**

Create `docs/paper-ieee/README.md`:

```markdown
# IEEEtran edition

This is the IEEE two-column, numbered-citation edition of
**Wave-Corrected Caustics over Photon Splatting**. It is not a second paper:
the body, appendix, figures, bibliography, and every quantitative claim are the
same as the CGF edition in `../paper/`.

* `main.tex` — IEEEtran preamble and the shared-body input list.
* `sections/frontmatter.tex` — IEEE title/author/abstract/keywords only.

Build from the repository root:

```bat
python tools/build_paper_ieee.py
python tools/check_dual_format.py
```

The build must exit 0 with 0 overfull boxes. The parity check must print
`DUAL-FORMAT OK`. If you change a claim, change it in `../paper/sections/` (shared)
or, for frontmatter, in both frontmatters in the same commit.
```

- [ ] **Step 2: Add the README link**

In `README.md`, immediately after the existing CGF paper link, add:

```markdown
- 📄 **[IEEEtran edition](docs/paper-ieee/main.pdf)** — two-column, numbered citations, same body and claims.
```

- [ ] **Step 3: Add the index rows**

In `docs/README.md`, add a row:

```markdown
| [`paper-ieee/`](paper-ieee/) | IEEEtran two-column edition. Shares every body section with `paper/`; only the preamble and frontmatter differ. Built by `tools/build_paper_ieee.py`. |
```

In `tools/README.md`, add rows:

```markdown
| `build_paper_ieee.py` | Compile the IEEEtran edition and fail on engine errors or overfull boxes. |
| `check_dual_format.py` | Prove the CGF and IEEE editions share the same body, abstract, and canonical claim values. |
```

- [ ] **Step 4: Check links and commands**

Run:
```bat
python tools/check_dual_format.py
python tools/build_paper_ieee.py
python tools/build_paper_pdf.py --engine pdflatex
```
Expected: `DUAL-FORMAT OK`; both builds exit 0 with 0 overfull; each prints its page count. The CGF count is 27 in this environment; do not copy that number into prose without rebuilding.

- [ ] **Step 5: Commit**

```bat
git add README.md docs/README.md docs/paper-ieee/README.md tools/README.md
git commit -m "Document the IEEEtran edition and its parity check"
```

---

## Task 9: Record the build in EVIDENCE

**Files:**
- Modify: `docs/EVIDENCE.md` (append a new dated section; never rewrite an earlier one)

- [ ] **Step 1: Append the section**

Add at the end of `docs/EVIDENCE.md`:

```markdown
### 25. IEEEtran edition build (2026-10-20)

`docs/paper-ieee/` is the IEEEtran journal edition. It shares the body sections
with `docs/paper/` and adds only an IEEE preamble and frontmatter. The abstract
is the CGF abstract verbatim.

* build: `pdflatex` + `bibtex`, 0 engine errors, 0 overfull boxes;
* page count: printed by `tools/build_paper_ieee.py` on every run;
* parity: `tools/check_dual_format.py` reports `DUAL-FORMAT OK`, 11 shared body
  sections and 12 canonical claims checked in both source trees.

No number in this section is a new measurement; it records a build and a parity
check, not a physical result.
```

- [ ] **Step 2: Run the full gate**

Run:
```bat
python tools/fringe_scale.py
python tools/make_all_figures.py
python tools/check_paper.py
python tools/verify_wave_correction.py
python tools/verify_ray_map.py
python tools/accuracy_vs_ground_truth.py
python tools/spmm_vs_groundtruth.py
python tools/build_paper_pdf.py --engine pdflatex
python tools/build_paper_ieee.py
python tools/check_dual_format.py
```
Expected: every command exits 0; both builds report 0 overfull; `DUAL-FORMAT OK`. `verify_refs.py` is network-dependent and not part of this gate; run it separately and record any 429.

- [ ] **Step 3: Commit**

```bat
git add docs/EVIDENCE.md
git commit -m "Record the IEEEtran build and parity check"
```

---

## Self-review

- **Spec coverage:** the plan creates the IEEE edition, shares the body, preserves
  numbered citations, adds a build gate and a parity gate, and updates every
  summary document. The dual-format rule in `AGENTS.md` is enforceable by
  `tools/check_dual_format.py`.
- **Placeholder scan:** no `TBD`, `TODO`, or sentinel text. The abstract is
  written out in full in Task 4, so the frontmatter can be created in one step.
- **Type consistency:** `tools/build_paper_ieee.py` reads `docs/paper-ieee/main.tex`;
  `tools/check_dual_format.py` reads the same path and `docs/CLAIMS.md`; both use
  the same `sections/frontmatter.tex` filename.
- **Known risk:** IEEEtran's narrower column will expose tables that fit the CGF
  measure. Task 5 promotes only the tables that actually overflow, and Step 5
  requires the CGF build to stay at 0 overfull.
