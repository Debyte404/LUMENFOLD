# docs/ — the written record

Reading order, and what each file is for. Currency is stated per file: the work went
through a scope change (from physical-validation to comparative-evaluation), so a few
documents carry dated scope notes.

| File | What it is | State |
|---|---|---|
| [`paper/main.pdf`](paper/main.pdf) | **The paper.** Typeset in the official Computer Graphics Forum class (`egpubl.cls`, Eurographics), 22 pages: kinematics with lemmas, theorems and proofs, how computer graphics builds caustics, the current solvers, the method, results, verification, limits, discussion, appendices. Source in `paper/`. | current, primary deliverable |
| [`PAPER.md`](PAPER.md) | Earlier markdown draft of the same manuscript. Superseded by `paper/main.tex`; kept for the record. | superseded |
| [`PAPER.html`](PAPER.html) | Printable web page generated from the markdown draft. The LaTeX build replaced it as the typeset artefact. | generated from PAPER.md |
| [`EVIDENCE.md`](EVIDENCE.md) | **The measurement record** — 1,400+ lines, every number in the paper with its provenance, including negative results, the estimator traps that produced false conclusions, and the index error that was caught. | current, canonical |
| [`CRITIQUE.md`](CRITIQUE.md) | Adversarial audit of our own claims: which survived, which were inflated, which were vacuous. Includes the active falsifier list. | current |
| [`PAPER_PLAN.md`](PAPER_PLAN.md) | Planning document: claim inventory, related-work survey (the novelty gap), figure list, staged timeline, target venues, threats to validity. | current where it has been updated (claim inventory, venue gate); the apparatus experiment is descoped |
| [`BLENDER_PLUGIN.md`](BLENDER_PLUGIN.md) | The Blender caustic-injector plug-in: scene contract, honest scope, install and use. | current |
| [`PHYSICAL_TEST.md`](PHYSICAL_TEST.md) | How the physical questions *would* be settled with apparatus: protocol, falsifiable predictions, what a photograph cannot settle. | **optional appendix — out of scope for this work**, not cited as evidence |

## Directories

| Path | Contents |
|---|---|
| `paper/` | The CGF LaTeX source: `main.tex`, `sections/`, `refs.bib` (every entry verified against Crossref), and `figures/` as vector PDF. Compile with `tools/build_paper_pdf.py`. |
| `figures/` | The earlier raster figures, generated from real artefacts by `tools/make_paper_figures.py`. `figure_data.json` carries the numbers they plot. The paper now uses the vector PDFs in `paper/figures/`. |
| `media/` | Presentation media: the four clips (ripple, turntable, combined, and Cycles' counterparts), **`ripple_{ours,cycles,spmm}.gif`** — the same ripple animation three ways, one verified camera, physical fringe width, exposure-matched subject (EVIDENCE 14.5f) — contact sheet, comparison figures, showcase stills. |
| `data/` | Machine-readable artefacts: the baked caustic field (`caustic_wave.npy`) and the efficiency study results. |

## Where the numbers come from

Nothing in `PAPER.md` is asserted without a measurement behind it. The independent
instruments, none of which share code with the estimator:

- **brute-force geometric trace** — 810 k explicit rays, no parametrisation, no
  Jacobian, no renormalisation (`tools/verify_ray_map.py`). The primary ground truth.
- **closed-form cylinder** — exact Snell, fold found by bisection to machine precision
  (`tools/analytic_caustic.py`).
- **PBRT-v4 SPPM** — the reference conforming caustic solver
  (`tools/pbrt_reference.py`, `tools/spmm_vs_groundtruth.py`).
- **Mitsuba 3 spectral** — independent measured index data for the dispersion order
  (`tools/mitsuba_reference.py`).
- **Blender Cycles** — path-traced comparison, with its configuration audited and
  corrected before any claim was made (`tools/blender_scene.py`).

Two estimator conventions are documented because each one manufactured a false
conclusion before being caught (`EVIDENCE.md` §6.8 of the paper, §14.5e of EVIDENCE):
the sign convention for a differential caustic, and the tile-size-vs-tile-count
naming collision.
