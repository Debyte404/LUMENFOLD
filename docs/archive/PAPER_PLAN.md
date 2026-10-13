# Paper Plan — Wave-Corrected Caustics: A Comparative Evaluation

Status: plan / pre-submission. **Scope revised 2026-10-12:** this is an
evaluation paper (speed and quality of wave-corrected caustics against PBRT-v4
SPPM, Cycles and Mitsuba 3), not a physical-validation paper. Laboratory
apparatus validation is out of scope and is not proposed as future work; the
apparatus protocol is retained only as an optional appendix in
`docs/PHYSICAL_TEST.md`. The plan below predates sections 14-20 of EVIDENCE and
is retained for its related-work survey and venue analysis; the claim inventory
in section 2 has been updated where measurements have since landed.

Grounding rule: every quantity cited below is either quoted verbatim from
`docs/EVIDENCE.md` or explicitly marked **NEEDS MEASUREMENT**. No number in
this document is inferred, extrapolated, or invented.

---

## 1. Working title and abstract

**Working title:** *Wave-Corrected Caustics over Photon Splatting: A Comparative
Evaluation against Photon Mapping and Path Tracing.*

**Abstract.** Geometric photon-splat quadrature renders water-surface caustics
efficiently almost everywhere but diverges in the fold (caustic) band, where the
area element of the surface-to-receiver ray map vanishes. We present a hybrid in
which the geometric quadrature is the backbone and a wave correction is applied
only inside a narrowly detected fold band: the band's geometric energy is
redistributed according to the Airy fold profile `|Ai(-s/w)|^2`, with a
per-channel fringe width `w` scaling as `lambda^(2/3)`, which yields finite
fringes and chromatic dispersion as a consequence of the profile rather than as
an added effect. Three methodological decisions were forced by measurement rather
than assumed. First, the fold locus is taken as the analytic zero of the
determinant of the Jacobian of the ray map, not as an intensity percentile: the
percentile detector plateaus at RMSE 0.08534 while the analytic locus converges
to 0.03914 against a converged higher-resolution reference of the same model.
Second, flux is conserved locally within the band rather than by a post-clamp
global rescale, which otherwise pushes the peak past its own display ceiling
(measured peak 11.58 against a ceiling of 8.10). Third, ray hits that land
outside the receiver are discarded rather than clamped to the border, removing a
measured 38x border artifact (geometric peak 350.78 clamped versus 9.28
discarded). Against the wave-corrected reference, a stochastic geometric
estimator stalls at an error floor of 0.06013, while the corrected field reaches
0.03914 using 16x fewer samples; at small budgets, however, stochastic
estimation is more accurate, and we report this limitation explicitly. The
contribution is a fold-local wave correction whose physical claim is one of form
(finite fringes, chromatic ordering, no divergence), demonstrated on a single
documented scene and pending laboratory validation.

---

## 2. Claims, each tagged with its supporting measurement

Each claim states (a) the exact measured quantity from `docs/EVIDENCE.md` that
supports it and (b) whether it is ready or requires a new experiment.

### C1 — Analytic fold locus converges; the intensity percentile does not. `[SUPPORTED BY CURRENT DATA]`
RMSE against a converged 2048^2 reference (evaluated at 256^2), percentile versus
analytic `|det J|`: at 128, 0.20598 vs 0.20188; at 256, 0.12795 vs 0.13738; at
512, 0.09296 vs 0.10455; at 1024, 0.08534 (stalls) vs 0.03914 (converges). The
analytic locus is 2.2x more accurate at 1024^2. Source: EVIDENCE §1. The claim is
about convergence behaviour, not pointwise accuracy: at 256^2 and 512^2 the
percentile detector is slightly better (up to 12%).

### C2 — Band-local flux conservation holds the display ceiling; a post-clamp global rescale violates it. `[SUPPORTED BY CURRENT DATA]`
At 256^2 the global variant reaches peak 11.58 against a ceiling of 8.10
(violated) with RMSE 0.14363, while band-local holds peak 7.55 with RMSE 0.13738.
At 512^2, global peak 12.17 (violated), band-local 7.71 (ok). At 1024^2, global
7.85 and band-local 7.69, both ok, both RMSE 0.03914. Source: EVIDENCE §2. It
also fixes `airy_caustic.py`'s flux ratio to 1.0000.

### C3 — Discarding out-of-receiver ray hits removes a border artifact. `[SUPPORTED BY CURRENT DATA]`
Geometric peak 350.78 with border-clamping versus 9.28 with discarding — a 38x
artifact. Source: EVIDENCE §3.

### C4 — The corrected estimator reaches an accuracy the stochastic geometric estimator cannot reach at any sample count. `[SUPPORTED BY CURRENT DATA]`
Against the converged wave-corrected reference, Monte-Carlo geometric shrinks
from 0.12294 (65 k splats) to 0.06013 at its floor (16.8 M splats), while the
corrected field reaches 0.03914 at 1.0 M splats — 35% below the MC asymptote,
using 16x fewer splats than MC's M=256 run. Source: EVIDENCE §4. The defensible
statement is that geometric sampling is *unreachable* for the wave-corrected
target, **not** that our method is uniformly faster.

### C5 — At small budgets, stochastic MC is more accurate than our method. `[SUPPORTED BY CURRENT DATA]`
At ≤262 k splats plain geometric MC is better in RMSE (0.12294 and 0.07838 for
MC versus 0.13738 and 0.10455 for ours at 65 k and 262 k). Source: EVIDENCE §4.
This is a stated limitation, not a result to be hidden.

### C6 — The geometric fold tail decays slowly; the corrected field is bounded and slightly conservative against truth. `[SUPPORTED BY CURRENT DATA]`
With a 6x display cap: MC geometric M=1 max 8.71, M=256 max 7.25 (a slow decay
across 256x more samples); ours (512^2, det J) max 7.71 with 0.06% of pixels
above cap; converged wave truth max 7.73 with 0.35% above cap. Source: EVIDENCE
§4 (tail table).

### C7 — Fusion and parallelism reduce bake time, reported as separate wins. `[SUPPORTED BY CURRENT DATA]`
Serial/algorithmic: 231.58 ms to 78.49 ms at 512^2 (2.95x) by fusing surface +
refraction + splat into one pass and deleting the post-clamp global rescale pass,
single thread. Parallel: 78.49 ms to 36.22 ms at 8 threads (2.17x). Combined at
512^2: 231.58 ms to 36.22 ms = 6.4x, with the peak artifact removed at the same
time. Source: EVIDENCE §5. Scope: single machine, single compiler.

### C8 — The known fringe resolution floor. `[SUPPORTED BY CURRENT DATA]`
The Airy band is meaningless if the fringe width `w` spans fewer than ~3 pixels;
with `w = 0.02 m` over a 6 m patch this requires `N >= ~900`, so a 512^2
real-time bake is under-resolved for the fringe structure it claims to draw.
Source: EVIDENCE §1 (design rule).

### C9 — The result is one of form: finite fringes and absence of divergence. `[SUPPORTED BY CURRENT DATA]`
EVIDENCE §7.3 states the honest physics claim is about FORM (finite Airy
fringes, chromatic ordering, no 1/sqrt divergence), not absolute fringe width.

### C10 — Chromatic dispersion ordering is correct. `[SUPPORTED BY CURRENT DATA]`
Ordering is now VERIFIED three ways on measured indices (Daimon & Masumura
water, Rubin glass): Mitsuba 3 spectral with measured BK7/water data gives red
farther than blue by +1.6 mm (+1.74%%, EVIDENCE 18); PBRT-v4 SPPM per-channel
renders give monotonic R > G > B, R-B +1.37 mm; the ceiling-immune edge
estimator gives ours R 107 / G 105 / B 102 mm vs SPPM R 56 / G 54 / B 51 mm,
both R-B +5.0 mm (EVIDENCE 20.3). The brightest-percentile estimator previously
quoted is RETIRED (reads flat on measured indices -- capped-core artefact).
What REMAINS open is fringe SPACING per channel vs the lambda^(2/3) prediction
as photographed quantities -- absolute fringe width under sunlight is
non-physical (C12), so a spacing measurement needs the laser/cylinder
apparatus (S4).

### C11 — C++ and Python ports agree; parallel and serial agree. `[SUPPORTED BY CURRENT DATA]`
512^2, t = 1.7, airy_scale = 1.0: geometric peaks 9.281 vs 9.280 (max abs diff
5.6e-04, 0.006%); wave R/G/B peaks agree to 0.3%; parallel versus serial output
agrees to 3.8e-06 (relative 1.1e-08). Source: EVIDENCE §6.

### C12 — Absolute fringe width is predictive. `[NEEDS NEW EXPERIMENT]`
`airy_scale` is a visibility parameter, not a prediction (EVIDENCE §7.3). No
claim of absolute fringe width will be made without apparatus measurement —
**NEEDS MEASUREMENT**.

---

## 3. Related work and the novelty gap

Source: `WAVE_VIABILITY.md` (prior-art study, cross-checked via OpenAlex and
GitHub repository trees).

### 3.1 Geometric caustics — solved but sparsely shipped
Photon mapping (Jensen 1996/2001) is the classic specular-diffuse-specular
caustic solver and ships in LuxCoreRender and (limited) in Blender Cycles as
light-tracing / photon path. It is absent from Mitsuba 3 main integrators
(checked `src/integrators`) and from PBRT-v4's main CPU integrators, though
PBRT-v4 does ship SPPM plus BDPT/MLT. Progressive/stochastic PPM (Hachisuka et
al. 2008+) is mostly research code and LuxCore. Manifold Next Event Estimation
(MNEE, 2015) exists as a Cycles toggle (`shadow-caustics`) but is not in Mitsuba
3 or PBRT-v4 mainline. Specular Manifold Sampling (SMS, 2020) and its bisection
variant (2022), and Manifold Path Guiding (2023), are research-only. General path
guiding (Müller et al. 2017) ships in Cycles and partially in LuxCore but is not
itself a caustic solver. Net: geometric caustics are well understood and only
partially shipped.

### 3.2 Wave optics in graphics — largely unshipped
Yan et al. 2018 ("Rendering specular microgeometry with wave optics", TOG/
SIGGRAPH) models scratches as phase gratings for stable glints; no shipping
renderer implements it. The closest shipping features are analytic thin-film
interference (Cycles thin-film toggle; Mitsuba 3 `principledthin` BSDF), which
are not general diffraction. Bar et al. 2019 (Monte-Carlo speckle in scattering
media) and a 2023 generalized ray formulation for wave-optics rendering are
research-only. UTD/PTD edge diffraction (Kouyoumjian-Pathak) is standard in
acoustics and RF planning but absent from major graphics path tracers. Frosted
and Airy-fringe caustics remain research-only.

### 3.3 The physics root and the exact gap
Berry & Upstill 1980 is the physics root for catastrophe/Airy fold optics. A
title search for wave-optics caustic rendering returns only physics papers
(optical rogue waves, etc.); **no production or research renderer ships Airy
(fold) or Pearcey (cusp) regularized caustics.**

**Stated gap (verbatim intent):** detect fold/cusp geometry near focus and
replace the geometric spike with an Airy/Pearcey fringe profile parameterized by
wavelength and wavefront curvature.

### 3.4 The specific novelty of this work
Prior viability study verifies the gap; this work occupies it by *construction*:
the correction is not a global wave solve but a **band-local replacement of the
geometric singularity**, gated by the analytic fold locus and flux-conserved
inside the band. The three measured methodological rules (C1–C3) are, to our
knowledge, not previously documented as a design discipline for wave-corrected
caustics, and they are the paper's methodological core rather than incidental
engineering.

**Caveat carried forward:** `WAVE_VIABILITY.md` records that arXiv and Semantic
Scholar were HTTP 429 from the survey IP on 2026-09-29, and that versioned IDs
must be re-verified from a keyed connection before citing. Any citation list must
be re-run before submission.

---

## 4. Method section outline

### 4.1 Geometry and the geometric backbone (Section 3 of the paper)
- Scene: a 6 x 6 m water patch, depth 1 m, four directional sine waves, sun
  direction `(-0.35, -0.25, -1)`, `t = 1.7 s`, with `airy_scale = 0.02` unless
  stated. Surface height and analytic gradient from the sine superposition.
- Per-surface-cell: compute the surface normal, refracted ray (Snell's law with
  the air/water index ratio as implemented in `src/render/caustic.cpp`), and the
  receiver hit by ray-marching to the floor plane.
- Splat the photon energy into the receiver with bilinear taps; **discard** taps
  that fall outside the receiver (C3).
- Normalize the geometric field by its own mean.

### 4.2 Fold locus (Section 4)
- Define the surface-to-receiver ray map and compute the determinant of its
  Jacobian `det J` by finite differences of the receiver-hit coordinates `Hx`,
  `Hy` with respect to surface position.
- The fold band is the region of small `|det J|`; the current threshold is the
  2nd percentile of `|det J|`.
- Manuscript must state the convergence argument (C1) and the open problem that
  this remains a threshold (EVIDENCE §7.5; a scale-space or sign-change
  formulation would be threshold-free — proposed as future work).

### 4.3 Airy fold profile (Section 5)
- Inside the band, replace the geometric value by the Airy fold intensity
  profile `|Ai(-s/w)|^2`, where `s` is the signed distance to the fold locus
  (Euclidean distance transform, `d2`, times the cell spacing) and `w` is the
  per-channel fringe width.
- `w` is proportional to `lambda_c^(2/3)` (the `lambda^(2/3)` law given for this
  work), evaluated per channel relative to a reference wavelength taken from
  `src/render/caustic.cpp`; the profile itself is evaluated through a precomputed
  LUT with linear interpolation.
- Blend with the smoothed geometric strength (`min(smooth, cap)`) so the band's
  amplitude, not the profile, carries the energy.

### 4.4 Band-local flux conservation (Section 6)
- Inside the band, compute the band's own target energy `want` and the profile's
  produced energy `got`, and renormalize only within the band by
  `k = want / got` — no global rescale after the clamp (C2).
- State the ceiling argument explicitly: the display ceiling of 8.10 is violated
  at 256^2 and 512^2 by the global variant (peaks 11.58 and 12.17) and held by
  the band-local variant (7.55 and 7.71).

### 4.5 Dispersion and chromatic ordering (Section 7)
- Per-channel `w` implies red fringes wider than blue; present the measured
  per-channel parity (C11) as an implementation check and defer the validated
  chromatic-ordering claim to the apparatus experiment (C10, C12).

---

## 5. Experiment plan

Legend: **[EXISTING]** = artifact already in the repo and cited in EVIDENCE.md;
**[TO ADD]** = a new script or harness the paper requires.

### 5.1 Result figures/tables, each with its producing artifact

| # | Figure / table | Content | Artifact |
|---|----------------|---------|----------|
| F1 | Fold-locus convergence (RMSE vs grid, 128–1024) | C1 | `tools/fold_diag.py` **[EXISTING]** |
| F2 | Flux / ceiling ablation table | C2 | `tools/band_flux_test.py` **[EXISTING]** |
| F3 | Splat boundary ablation (clamp vs discard) | C3 | dedicated harness **[TO ADD]** (currently a path inside `src/render/caustic.cpp`; must be scripted to be citable) |
| F4 | Efficiency: RMSE vs splat budget, MC vs corrected | C4, C5 | `tools/efficiency_study.py` → `docs/data/efficiency_study.json`, `docs/media/efficiency_plot.png` **[EXISTING]** |
| F5 | Tail behaviour (max / p99.9 / %>cap) at 6x cap | C6 | `tools/tail_study.py` **[EXISTING]** |
| F6 | Serial fusion + thread scaling + combined speedup | C7 | `bench.exe` **[EXISTING]**, thread count via `CAUSTIC_THREADS` |
| F7 | C++/Python parity table (peaks, max abs diff) | C11 | `tools/parity_cpp_vs_py.py` **[EXISTING]** |
| F8 | Showcase render (visual) | method overview | `tools/airy_caustic.py` → `docs/media/caustic_compare.png` **[EXISTING]** |

### 5.2 Ablations for the three methodological fixes

**Ablation A — Fold locus (percentile vs analytic `|det J|`).** Re-run
`tools/fold_diag.py` at 128, 256, 512, 1024 and report both detectors against the
2048^2 reference at 256^2. Expected reproduction of §1: percentile stalls at
0.08534, analytic converges at 0.03914. Artifact: `tools/fold_diag.py`
**[EXISTING]**.

**Ablation B — Flux conservation (global vs band-local).** Re-run
`tools/band_flux_test.py` at 256, 512, 1024; report peak and ceiling status and
RMSE for both variants. Expected reproduction of §2. Artifact:
`tools/band_flux_test.py` **[EXISTING]**.

**Ablation C — Splat boundary (clamp vs discard).** Re-run the splat pass with
border clamping and with discarding, and report the geometric peak for each.
Expected reproduction of §3 (350.78 vs 9.28). Artifact: harness **[TO ADD]** so
the ablation is script-citable, not merely described.

### 5.3 Real-validation experiment (physical apparatus) — OUT OF SCOPE (2026-10-12)

EVIDENCE §7.1 states there is **no experimental ground truth** and that real
validation means fringe spacing against a laser and a known lens; §7.3 states the
honest claim is about form, not absolute fringe width. The paper therefore
requires at least one apparatus experiment.

**Apparatus.** A fold line caustic is naturally produced by a cylindrical
optical element (a cylindrical lens or a glass rod) illuminated by a laser and
projected onto a flat wall or screen — the cylindrical geometry yields a line
fold whose cross-section is exactly the Airy profile the method draws.

**Procedure.**
1. Illuminate the cylinder with a single-wavelength laser; photograph the
   projected caustic band on the screen.
2. Extract the intensity cross-section across the fold and measure the fringe
   spacing and the position of the first few fringes.
3. Repeat with two or more wavelengths (or a white-light source with a
   monochromator / colour separation) to test the chromatic ordering.
4. Compare measured fringe spacing and ordering against the model prediction.

**Predicted quantities.** The predicted fringe spacing and chromatic ordering
for the chosen apparatus geometry are not present in EVIDENCE.md and must be
computed from the Airy model and the apparatus parameters — **NEEDS
MEASUREMENT**. The measured-versus-predicted fringe-spacing error is also
**NEEDS MEASUREMENT**.

**Figures.** New Fig F9 (photograph overlaid with predicted fringe positions),
new Fig F10 (chromatic ordering: measured spacing per wavelength versus the
`lambda^(2/3)` prediction). Both artifacts **[TO ADD]**.

### 5.4 New experiments to close EVIDENCE's open problems

- **Ensemble statistics.** EVIDENCE §7.2: the result is one 4-sine-wave scene,
  one time, one sun angle; to generalize, run an ensemble over a range of wave
  spectra, amplitudes, wind conditions, and times. Ensemble error statistics are
  **NEEDS MEASUREMENT**. Artifact **[TO ADD]** (extend `tools/efficiency_study.py`
  to a scene ensemble).
- **Coherence gate.** EVIDENCE §7.4: the wave correction is applied near folds
  unconditionally and the `coherence.hpp` gate is unimplemented; sunlight has a
  ~0.5 µm coherence length. Add a path-length-difference gate and measure its
  effect on RMSE and cost. Effect **NEEDS MEASUREMENT**. Artifact **[TO ADD]**.
- **Threshold-free fold locus.** EVIDENCE §7.5: a scale-space or sign-change
  formulation would remove the 2nd-percentile threshold. Compare against the
  thresholded analytic locus. Improvement **NEEDS MEASUREMENT**. Artifact
  **[TO ADD]**.
- **GPU port.** EVIDENCE §7.6: no GPU port exists. Optional; would be required
  only for an HPG-class performance claim (see §6).

---

## 6. Target venues

| Venue | Type | One-line reason |
|-------|------|-----------------|
| ACM SIGGRAPH / ACM TOG | Archival, top-tier | The full form claim plus a physical-validation experiment and ensemble statistics would make it competitive; not ready without §5.3. |
| EGSR (Eurographics Symposium on Rendering) | Focused rendering conference | Best fit for a rendering method with a strong ablation table and an honest, bounded scope; expects exactly this kind of measured-methodology contribution. |
| HPG (High-Performance Graphics) | Performance-focused | Only appropriate if the paper leads with the parallel/G-flops story (2.95x fusion, 2.17x 8-thread, 6.4x combined); realistically needs a GPU port to qualify. |
| Journal of Computer Graphics Techniques (JCGT) | Reproducible, module-scale | Well matched to a self-contained analytical correction with shipped reference code and a reproducible benchmark; lowest barrier to a defensible, honest submission. |
| Optics Express / Applied Optics | Applied-optics journal | Appropriate if the work is reframed around wave-optics correctness and the apparatus validation; reviewers will demand coherence modelling (EVIDENCE §7.4) and real fringe measurement. |

---

## 7. Threats to validity and limitations

Reused from EVIDENCE §7 ("What is NOT shown / open problems") and extended.

1. **No experimental ground truth.** Every "truth" number is the same model
   evaluated at higher resolution (2048^2, block-averaged to 256^2) — a
   self-consistency reference, not physical truth. Addressed only by the §5.3
   apparatus experiment. `[NEEDS NEW EXPERIMENT]`
2. **One scene.** A sum of four sine waves, one time, one sun angle; no ensemble
   statistics over wave spectra, no wind, no moving bodies. `[NEEDS NEW EXPERIMENT]`
3. **`airy_scale` is a visibility parameter, not a prediction.** The physics
   claim is about form (finite Airy fringes, chromatic ordering, no 1/sqrt
   divergence), not absolute fringe width. `[SCOPE LIMIT]`
4. **Coherence is not modelled.** Sunlight's ~0.5 µm coherence length is not
   applied; the `coherence.hpp` gate is unimplemented and the correction is
   applied near folds unconditionally. `[NEEDS NEW EXPERIMENT]`
5. **The fold threshold is still a threshold.** The 2nd percentile of `|det J|`
   is better-behaved than an intensity percentile but remains resolution- and
   scene-dependent; a scale-space or sign-change formulation is future work.
   `[NEEDS NEW EXPERIMENT]`
6. **Single machine, single compiler** (MSVC 14.41, /O2; i7-14650HX, 16C/24T, RTX
   4060 Laptop). No GPU port. `[SCOPE LIMIT]`
7. **Efficiency is not uniform.** Below ~262 k splats a stochastic estimator is
   competitive or better (C5); the advantage appears only near the ~1 M splat
   range where fringes exist at all. `[SCOPE LIMIT]`
8. **Baseline inconsistency in the performance tables.** The fusion result
   (231.58 ms to 78.49 ms) and the thread-scaling table (serial baseline 88.78
   ms) do not share a baseline; the thread-scaling table was measured on the
   pre-fix build. The two factorizations must not be multiplied together
   naively, and the paper must state which baseline each speedup uses.
   `[SCOPE LIMIT]`
9. **The comparison metric is model-dependent.** RMSE is measured against the
   wave-corrected model's own finer evaluation, and the tail statistics use a 6x
   display cap; both choices shape the reported numbers and must be stated as
   conventions, not natural constants. `[SCOPE LIMIT]`
10. **Matched-budget "splat" comparison is a modelling choice.** The stochastic
    and deterministic estimators are compared at matched splat counts; the
    deterministic pass is grid-bound rather than sample-bound, so the equivalence
    is approximate. `[NEEDS NEW EXPERIMENT]` if the paper makes a cost-normalized
    claim.
11. **Parity residual is localized and physical.** C++/Python differences sit on
    fold pixels and come from Airy LUT resolution versus exact
    `scipy.special.airy`, plus EDT tie-breaking; peaks still agree to 0.3%.
    `[SCOPE LIMIT]`
12. **Prior-art recency.** The viability study's arXiv/Semantic Scholar lookups
    returned HTTP 429; the citation list must be re-run and re-verified before
    submission. `[TO VERIFY]`

---

## 8. Staged timeline

Durations are planning estimates, not measurements.

| Stage | Work | Depends on | Exit criterion |
|-------|------|-----------|----------------|
| S0 — Method + single-scene evidence | Fold locus, band-local flux, splat boundary, efficiency, parity, timing (already measured) | — | EVIDENCE.md tables reproduced and scripted |
| S1 — Script the missing ablation | Build the F3 splat-boundary harness **[TO ADD]** | S0 | C3 is reproducible from a single named script |
| S2 — Ensemble statistics | Multi-spectrum, multi-time, multi-sun-angle runs | S0 | Ensemble error statistics reported (currently **NEEDS MEASUREMENT**) |
| S3 — Coherence gate + threshold-free locus | Implement `coherence.hpp` gate; scale-space/sign-change fold locus | S2 | Measured RMSE/cost effect of each |
| S4 — ~~Physical validation~~ | **DESCoped (2026-10-12)**: laboratory apparatus validation is out of scope for this paper. Retained as an optional appendix protocol only. | — | — |
| S5 — Performance refactor (optional) | GPU port or Airy-term optimization (currently ~two thirds of a bake) | S0 | New timing broken out by term |
| S6 — Venue selection + writing | Choose venue from §6 based on S2–S4 outcomes | S2–S4 | Submission-ready manuscript |
| S7 — Citation re-verification | Re-run prior-art survey from a keyed connection | S6 | All citations verified against versioned IDs |

**Decision gate before S6 (RESOLVED 2026-10-12):** S4 was not run by design, so
the paper IS the methodology/comparative contribution (EGSR/JCGT scope). C10
(dispersion ordering) has since been verified against PBRT SPPM and Mitsuba on
measured indices and is no longer an open problem; C12 (absolute fringe width)
remains explicitly unclaimed, and every physical statement is bounded to the
form claim of C9 -- finite fringes, chromatic ordering, no divergence.
