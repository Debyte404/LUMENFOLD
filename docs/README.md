# docs/ — the written record

The paper, the measurement record behind it, and the presentation media. Nothing here
is asserted without a measurement; currency is stated per file.

## Current

| File | What it is |
|---|---|
| [`paper/main.pdf`](paper/main.pdf) | **The paper.** Typeset in Computer Graphics Forum's own class (`egpubl.cls`, Eurographics): kinematics, how computer graphics builds caustics, the current solvers, the method, results, verification, limits, discussion, appendices. Source in `paper/`. Compile with `tools/build_paper_pdf.py`. |
| [`EVIDENCE.md`](EVIDENCE.md) | **The measurement record.** Every number in the paper with its provenance, including the negative results, the estimator traps that manufactured false conclusions, and the defects found after publication-grade checks had passed. Sections `14.5a`–`14.5r` are the colour, colour-rendering and add-on findings. |
| [`CRITIQUE.md`](CRITIQUE.md) | Adversarial audit of our own claims: which survived, which were inflated, which were vacuous. Carries the active falsifier list. |
| [`BLENDER_PLUGIN.md`](BLENDER_PLUGIN.md) | The Blender caustic-injector add-on: install, every control, both node graphs, the silent-failure traps, the scene contract, and troubleshooting. |
| [`PHYSICAL_TEST.md`](PHYSICAL_TEST.md) | How the physical questions *would* be settled with apparatus: protocol, falsifiable predictions, what a photograph cannot settle. **Optional appendix — out of scope for this work**, not cited as evidence. |

## Directories

| Path | Contents |
|---|---|
| `paper/` | The CGF LaTeX source: `main.tex`, `sections/`, `refs.bib` (every entry verified against Crossref), `egpubl.cls` and the vector figures in `paper/figures/`. |
| `media/` | Presentation media. The ripple animation three ways — **`ripple_{ours,cycles,spmm}.gif`**, one verified camera, physical fringe width, exposure-matched subject (EVIDENCE 14.5f) — plus **`hero_comparison.gif`/`.png`**, **`no_exaggeration.png`**, and the colour set: **`colour_media_grid.png`** (20 rendered caustics, 4 glass × 5 water), **`colour_sun_orbit.gif`** (camera fixed, sun rotated a full turn), **`colour_sun_sweep.gif`** (source 2000–12000 K, a palindrome so the loop does not flash), and **`ripple_{water,glass,both}_red.gif`** (one medium variable at a time). |
| `data/` | Machine-readable artefacts: the baked caustic field (`caustic_wave.npy`), the efficiency study results, **`colour_results.json`** (the full 4×5×4 glass × water × source factorial — 80 caustic cases, 15 fringe cases), **`figure_data.json`** (the numbers `tools/make_paper_figures_pdf.py` plots), **`control_corpus.json`** (156 pre-2020 human control abstracts for stylometry and overlap baselines), and **`detector_results.json`** (chunked AI detector evaluations). |
| `archive/` | Superseded material, kept for the record rather than deleted: `PAPER.md` and `PAPER_PLAN.md` (the markdown draft of the manuscript, and its planning document — both replaced by `paper/main.tex`) and `figures/` (the earlier raster figures, replaced by the vector PDFs in `paper/figures/`). |

The generated `docs/PAPER.html` was removed rather than archived: it was a 2.1 MB
by-product of `PAPER.md`, rebuildable from the archived source by
`tools/archive/build_paper_html.py`.

## Where the numbers come from

Nothing in the paper is asserted without a measurement behind it. The independent
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
conclusion before being caught (EVIDENCE §14.5e): the sign convention for a
differential caustic, and the tile-size-vs-tile-count naming collision.
