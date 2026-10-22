# AGENTS.md — working rules for LUMENFOLD

## What this repository is

A research codebase and manuscript for **Wave-Corrected Caustics over Photon
Splatting**: a geometric caustic solver with a band-local Airy correction. The
production path is C++ (`src/`), the measurement harness is Python (`tools/`),
and the manuscript exists in two formats:

* `docs/paper/` — Computer Graphics Forum / Eurographics (`egpubl`, the canonical edition).
* `docs/paper-ieee/` — IEEEtran, two-column, numbered citations (the IEEE edition).
  Built by `tools/build_paper_ieee.py`; parity checked by `tools/check_dual_format.py`.

## Source of truth, in order

1. `docs/EVIDENCE.md` — measured numbers and how they were obtained. Start at **§0**.
2. `docs/paper/sections/*.tex` — the claims and their wording.
3. `README.md`, `docs/README.md`, `docs/CRITIQUE.md`, `tools/README.md` — summaries.

Never change a number in a summary first. Change the measurement record, then
both papers, then the summaries, in that order.

## The dual-format rule (hard)

Any change to a **claim, number, figure, caption, table, abstract, title, author,
or reference** must land in **both** editions in the **same commit**:

* `docs/paper/` (CGF)
* `docs/paper-ieee/` (IEEEtran)

The body sections are shared: the IEEE `main.tex` inputs
`../paper/sections/*.tex`, so a body edit is automatically in both editions.
Only the class preamble and `frontmatter.tex` are format-specific. If a change
cannot be shared, duplicate it in both frontmatters and let
`tools/check_dual_format.py` prove the two copies still carry the same claims.

If `docs/paper-ieee/` does not exist yet, a paper change is **blocked** until the
IEEE edition is created. Do not land a CGF-only paper change.

In the same commit, also update every document that repeats the claim:

* `README.md`
* `docs/README.md`
* `docs/EVIDENCE.md` (append a dated section; do not rewrite history)
* `docs/CRITIQUE.md` (if a criticism is answered or a new one is exposed)
* `tools/README.md` (if a tool, figure, or command changed)
* `docs/PHYSICAL_TEST.md` (if the change affects the apparatus protocol)

## Claim rules

* Every quantitative claim names its evidence section (`EVIDENCE §x`) and the
  tool that produced it.
* Withdrawn claims stay withdrawn. The register is `docs/EVIDENCE.md §0.2`.
* **Fringe scale.** Canonical physical fringe width is **6.77 µm** (Eq. 14);
  first Airy zero **15.84 µm**. `airy_scale = 1.5 mm` is a **220× display
  exaggeration**. The shipped ripple clips at `0.123 mm` are **18× the canonical
  scale** and are labelled *operational*, never *physical*. Sun blur at ~100 mm is
  **925 µm**, i.e. **136×** the fringe spacing: solar fringes are not visible.
* **Benchmark scope.** One scene family, one machine, one sun angle. The headline
  is a production-cost result for that family, not a general speed-up. State the
  ties and losses (5 mm tiles, static-camera ripple clip, Monte Carlo below
  ~262 k splats).
* **No apparatus validation.** Every check is simulation against simulation.
  Do not imply a photograph has confirmed the model; `docs/PHYSICAL_TEST.md` is a
  protocol, not a result.
* A negative result is a result. Record it in EVIDENCE rather than deleting the
  experiment.

## Build and verification

Run from the repository root:

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

Both editions exist. Every command above must exit 0; each build must report `0`
overfull boxes; the page count is printed for both editions; and
`tools/check_dual_format.py` must print `DUAL-FORMAT OK`. Both builds currently
report 27 pages with pdfLaTeX in this environment; do not hardcode a page count
in prose without rebuilding.

`python tools/verify_refs.py` needs network access. HTTP 429 is rate limiting,
not a bibliography failure; rerun later and record any DOI that still does not
resolve. `tools/refs_verified.json` is a cache, not a source of truth.

## Figures and media

* `tools/make_all_figures.py` is the only supported way to regenerate paper
  figures. It runs the figure lint; all 12 must pass.
* Never hand-edit a generated PDF or PNG. Edit the generator and rebuild.
* README media: `python tools/make_no_exaggeration_figure.py --force` and
  `python tools/ripple_gifs.py`. The left panel of `no_exaggeration.png` is the
  canonical 6.77 µm scale; the right panel is the labelled 220× comparison.
* Plot labels use `\SI`/`\num` and the same units as the paper.

## Code and prose conventions

* Python: standard library + numpy/scipy/matplotlib/Pillow; keep scripts runnable
  as `python tools/<name>.py`. Prefer measured output over assertions in prose.
* C++: C++17, warnings clean, no new third-party dependency without a plan.
* LaTeX: `\SI` for units, `\num` for numbers, `\cref`/`\ref` for cross-references.
  Do not introduce a claim in a caption that is absent from the body.
* Commits: imperative, one sentence, no Conventional Commits prefix unless the
  existing history uses one. Include the verification status when all gates pass.

## Scope discipline

* One change per commit. A paper change and its evidence are one change.
* Do not tune a method per scene and then report the tuned number as a method
  result. Pre-register the criterion in the plan or EVIDENCE before running.
* Do not add a dependency, a figure, or a section without a plan in
  `docs/superpowers/plans/`.
