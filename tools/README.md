# tools/ — measurement, verification, references, production

Every number in the paper comes from one of these. Nothing here is a build step; the
C++ binaries are built by CMake (see the root README).

Two Python interpreters are in play, because the dependencies differ:

| Interpreter | Has | Used for |
|---|---|---|
| system Python 3.12 | `matplotlib`, `scipy`, `numpy`, `Pillow`, `markdown_it` | figures, Airy verification, everything that plots |
| `third_party/luxvenv` | `mitsuba` (EXR reading), `pyluxcore` | PBRT/Mitsuba EXR handling, the archived LuxCore probes |

## Independent instruments — the ground truths

These share no code with the estimator, which is the point.

| Tool | Purpose |
|---|---|
| `verify_ray_map.py` | **Primary ground truth.** 810 k explicit rays, no parametrisation, no Jacobian, no renormalisation — the hit density *is* the caustic. Also the importable module the other comparison tools build on. |
| `analytic_caustic.py` | Closed-form caustic of a solid refracting cylinder: every step exact Snell, fold found by bisection. Reproduced to 0.1 mm. |
| `verify_wave_correction.py` | Airy profile vs `scipy.special.airy`; the canonical cubic-phase fold integral; the λ^(2/3) exponent. Needs scipy. |
| `energy_audit.py` | Fresnel-weighted power entering vs landing — the non-circular replacement for the withdrawn flux claim. |
| `ensemble_study.py` | Agreement across 8 wave phases, to show the single-phase numbers are representative. |

## Comparisons against the estimator

| Tool | Purpose |
|---|---|
| `accuracy_vs_ground_truth.py` | Three-way accuracy: ours vs Cycles vs the brute-force truth, tiled. |
| `spmm_vs_groundtruth.py` | SPPM scored on the same axis, with the sign convention stated. |
| `metric_parity_check.py` | Scores all methods under both estimator conventions and reports where the ordering flips — this is what caught the false `r = 0.40` for SPPM. |
| `fold_diag.py` | Fold-locus convergence: analytic `\|det J\|` vs the intensity percentile. |
| `band_flux_test.py` | Flux ablation: post-clamp global rescale vs band-local. |
| `tail_study.py` | Tail/boundedness statistics of the fold against a display cap. |
| `parity_cpp_vs_py.py`, `parity_cpp.py` | C++/Python port agreement, and parallel-vs-serial agreement. |
| `fringe_scale.py` | Physical fringe width at the fold versus the width the renderer draws. |
| `dispersion_scale.py` | How wide the Airy band must be before dispersion is visible at all. |
| `physical_predictions.py` | Prints the falsifiable predictions from a bake, in camera-independent units. |
| `verify_against_photo.py` | Measures those same quantities from a photograph. **Appendix only** — see `docs/PHYSICAL_TEST.md`. |
| `clip_flicker.py` | Temporal flicker of the clips, caustic region vs control region. |

## Reference renderers

| Tool | Purpose |
|---|---|
| `pbrt_reference.py` | Generate and run the PBRT-v4 SPPM scene (measured etas by default). |
| `dispersion_pbrt.py` | Per-channel SPPM dispersion, centroids and edges. |
| `compare_pbrt.py` | PBRT vs our field, tiled correlation, with the documented X-mirror correction. |
| `pbrt_comparison_figure.py` | The PBRT / ours / overlay figure. |
| `mitsuba_reference.py` | Mitsuba 3 spectral render, using its own measured index data. |
| `blender_scene.py` | The Blender/Cycles scene that imports the baked field as an emission texture. |
| `studio.py` | The studio lighting rig and surface detail for that scene. |
| `audit_cycles_settings.py` | Dump the live Cycles configuration (imported by `blender_scene.py`). |
| `realistic_showdown.py` | Our injection vs Cycles' own caustics: RMSE table plus the hero stills. |
| `caustic_vs_cycles.py`, `hard_caustic_ab.py` | Caustic-noise A/B, including the hard small-source regime. |
| `caustic_field_validation.py` | The baked field vs Cycles' caustics-on-minus-off differential. |
| `compare_to_reference.py` | Photograph statistics (mean, percentiles, warmth, detail) for a render. |
| `export_scene_obj.py` | Export the scene geometry for Mitsuba and PBRT (identical vertices). |
| `airy_scale_sweep.py` | Choose `airy_scale` by measurement against a path-traced caustic. |
| `test_addon.py` | Headless test of the Blender caustic-injector add-on. |

## Production, figures, paper

| Tool | Purpose |
|---|---|
| `production_renders.py` | The deliverable stills and clips (`--combined-only`, `--cycles-clips`). |
| `make_paper_figures.py` | Regenerates all 9 figures in `docs/figures/` from real artefacts. |
| `build_paper_html.py` | `docs/PAPER.md` → `docs/PAPER.html` (MathJax, figures inlined). |
| `make_comparison_figure.py` | The photograph / ours / Cycles comparison figure. |
| `airy_caustic.py` | Python reference baker for the pool scene, and its comparison image. |
| `efficiency_study.py` | Accuracy vs splat budget: Monte-Carlo against the deterministic pass. |
| `gen_lut.py` | Regenerate the Airy LUT header from its `.npz` source. |

## archive/

Superseded harnesses, kept because they produced documented findings and because two of
them are cited in `docs/EVIDENCE.md`. Nothing live imports them.

| Tool | Why it is here |
|---|---|
| `luxcore/{probe_lux,probe_lux2,lux_photon_caustic,lux_debug_view}.py` | The LuxCore PhotonGI attempt — never produced a caustic here. Documented as a **negative result** in EVIDENCE §11.3. |
| `repro_3452.py`, `two_medium_demo.py` | The MuJoCo air/water physics demos from this repo's earlier stage (see the History section of the root README). |
| `dispersion_analytic.py` | Superseded by the dispersion work in EVIDENCE §20. |
| `edt_debug.py`, `probe_blender.py`, `where_diff.py`, `mid_diff.py`, `bisect_parity.py`, `compare_caustic_maps.py`, `showdown_common_mask.py`, `validate_field_vs_cycles.py` | One-off diagnostic inquests, each superseded once its question was answered. |

## Note on layout

Tools are deliberately **flat** rather than grouped into subpackages: several import
their siblings by inserting their own directory on `sys.path`, so moving a module would
silently break the harnesses that reproduce the paper's numbers. The only exception is
`archive/`, whose members were verified first — they either import nothing local, or
hardcode the tools path, or move as a self-contained cluster.
