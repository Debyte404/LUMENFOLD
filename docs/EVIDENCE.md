# EVIDENCE — measured results for the wave-corrected caustic module

Every number here was produced by a script in `tools/` or by the `bench` binary
in this repo, on this machine (i7-14650HX, 16C/24T, RTX 4060 Laptop), on the one
documented test scene: a 6 x 6 m water patch, depth 1 m, 4 directional sine
waves, sun direction (-0.35,-0.25,-1), t = 1.7 s, airy_scale = 0.02 unless
stated.

Reproduce:
```
python tools/fold_diag.py          # fold-locus convergence
python tools/band_flux_test.py     # flux-conservation variants
python tools/tail_study.py         # blowout / tail behaviour
python tools/efficiency_study.py   # stochastic vs deterministic, RMSE vs cost
python tools/parity_cpp_vs_py.py   # C++ vs Python port agreement
python tools/airy_caustic.py       # regenerates docs/caustic_compare.png
./build/src/app/Release/bench.exe 5    # timing (set CAUSTIC_THREADS)
```

Honest scope, stated once and applying to every table: ONE scene, ONE machine,
ONE sun angle, no laboratory ground truth. The "truth" below is the same model
evaluated at higher resolution, block-averaged down to 256^2. `airy_scale`
exaggerates the physical fringe width for visibility (real pool-scale fringes
are sub-millimetre); it is the identical parameter in every path compared.

--------------------------------------------------------------------------------
## 1. Fold detection: intensity percentile vs analytic |det J|
--------------------------------------------------------------------------------

The fold (caustic) locus is where the surface -> floor ray map has zero area
element. The original code detected it as "intensity above the 98th percentile".
That always flags exactly 2% of pixels regardless of how much of the image is
actually inside the fold band, so it cannot converge under refinement.

RMSE against a converged 2048^2 reference of the same model, evaluated at 256^2
(lower is better):

| grid | percentile (old)      | analytic \|det J\| (new) |
|------|-----------------------|--------------------------|
|  128 | 0.20598               | 0.20188                  |
|  256 | **0.12795**           | 0.13738                  |
|  512 | **0.09296**           | 0.10455                  |
| 1024 | **0.08534 (stalls)**  | **0.03914 (converges)**  |

Read honestly: at 256^2 and 512^2 the percentile detector is slightly BETTER
(up to 12%). Its defect is not accuracy, it is that it stops improving - it
plateaus near 0.085 no matter how fine the grid gets, because the flagged set
never becomes the true fold set. The analytic locus converges and is 2.2x more
accurate at 1024^2. Below 1024^2 the two are within noise, which is exactly why
the defect was invisible in the original implementation: it only manifests as a
failure to converge, not as an obviously wrong picture.

**Design rule that falls out of this:** the Airy band is meaningless if the
fringe width `w` spans fewer than ~3 pixels. With `w = 0.02 m` over a 6 m patch
that means `N >= ~900`. A 512^2 real-time bake is *under-resolved* for the
fringe structure it claims to draw. The offline showcase render uses 2048^2.

--------------------------------------------------------------------------------
## 2. Flux conservation: global rescale vs band-local
--------------------------------------------------------------------------------

Replacing the fold band with the Airy profile changes the band's total energy, so
it must be renormalized. The original code rescaled the WHOLE channel - after the
intensity clamp - which pushes the peak back over the ceiling it just enforced.

| grid | variant    | peak  | ceiling 8.10 | RMSE vs truth |
|------|------------|-------|--------------|---------------|
|  256 | global     | 11.58 | **violated** | 0.14363       |
|  256 | band-local |  7.55 | ok           | 0.13738       |
|  512 | global     | 12.17 | **violated** | 0.10467       |
|  512 | band-local |  7.71 | ok           | 0.10455       |
| 1024 | global     |  7.85 | ok           | 0.03914       |
| 1024 | band-local |  7.69 | ok           | 0.03914       |

Band-local = the Airy profile redistributes the band's OWN energy, so no global
rescale is needed. The ceiling then holds at every resolution, with equal or
better accuracy, and it also fixes `airy_caustic.py`'s flux ratio to 1.0000.

--------------------------------------------------------------------------------
## 3. Splat boundary: clamping vs discarding
--------------------------------------------------------------------------------

Rays whose floor hit landed outside the 6 x 6 m receiver were clamped to the
border, piling every escaping ray into a bright rim.

| variant | geometric peak |
|---------|----------------|
| clamp   | 350.78         |
| discard | 9.28           |

A 38x artifact, removed. Energy that leaves the patch simply is not seen by the
receiver; the field is then normalized by its own mean. This is also what makes
the C++ and Python fields agree (section 6) - the Python reference always
discarded.

--------------------------------------------------------------------------------
## 4. Stochastic geometric vs deterministic wave-corrected
--------------------------------------------------------------------------------

Both estimators integrate the same model; they differ in how they estimate it.
`efficiency_study.py` runs M jittered samples per surface cell (a real
integrator's cost model) against the deterministic pass. Everything is compared
to the converged WAVE-CORRECTED reference (2048^2, block-averaged to 256^2).

| estimator                | splats   | RMSE vs wave truth |
|--------------------------|----------|--------------------|
| MC geometric, M=1        |    65 k  | 0.12294            |
| MC geometric, M=4        |   262 k  | 0.07838            |
| MC geometric, M=16       |    1.0 M | 0.06445            |
| MC geometric, M=64       |    4.2 M | 0.06101            |
| MC geometric, M=256      |   16.8 M | 0.06013 (floor)    |
| ours, 256^2, 1 pass      |    65 k  | 0.13738            |
| ours, 512^2, 1 pass      |   262 k  | 0.10455            |
| **ours, 1024^2, 1 pass** | **1.0 M**| **0.03914**        |

What this actually says:
* At small budgets (<= 262 k splats) plain geometric MC is BETTER in RMSE than
  our method. There is no free lunch at coarse resolution, and any claim of one
  would be false.
* At 1.0 M splats our method is 1.65x more accurate than MC at the same cost.
* MC's error STALLS at 0.06013 no matter how many samples are spent, because it
  converges to a different model: rays place no energy in the fringe skirt. Our
  1024^2 pass reaches 0.03914 - 35% below MC's asymptote - using 16x FEWER
  splats than MC's M=256 run.
* For the wave-corrected target, geometric sampling is therefore not merely
  slower; it is unreachable. That is the defensible claim, and it is narrower
  than "we are faster".

Tail behaviour (why folds are hard), `tail_study.py`, display cap = 6x:

| estimator            | max  | p99.9 | %>cap |
|----------------------|------|-------|-------|
| MC geometric M=1     | 8.71 | 6.77  | 0.24% |
| MC geometric M=256   | 7.25 | 6.19  | 0.15% |
| ours 512^2 (det J)   | 7.71 | 5.70  | 0.06% |
| converged wave truth | 7.73 | 6.87  | 0.35% |

The geometric tail decays slowly (8.71 -> 7.25 for 256x more samples). Our field
sits at 7.71 with 0.06% above cap, i.e. slightly conservative against a truth
that itself has 0.35% above cap - those are physically resolved bright fringes,
not noise. Our model is not "smoother by cheating"; it is bounded where the
geometric estimator is noisy and slowly converging.

--------------------------------------------------------------------------------
## 5. Cost and parallel scaling (`bench.exe`)
--------------------------------------------------------------------------------

Single bake, best of 5, thread count from `CAUSTIC_THREADS`:

| grid | geom ms | wave ms | total ms (1 thread) | total ms (8 threads) | speedup |
|------|---------|---------|---------------------|----------------------|---------|
|  256 |    7.00 |   12.72 |               19.72 |                16.46 |  1.20x  |
|  512 |   28.68 |   49.81 |               78.49 |                36.22 |  2.17x  |
| 1024 |  108.25 |  202.12 |              310.37 |               117.82 |  2.63x  |
| 2048 |  425.04 |  781.75 |             1206.79 |               449.47 |  2.68x  |

Thread scaling on the same 512^2 bake (measured on the pre-fix build, so the
serial baseline is the older 88.78 ms figure):

| threads | total ms | speedup | note              |
|---------|----------|---------|-------------------|
|       1 |    88.78 |   1.00x |                   |
|       4 |    37.00 |   2.40x |                   |
|       8 |    34.78 |   2.55x | best measured     |
|      16 |    43.29 |   2.05x | oversubscribed    |
|      24 |    54.24 |   1.64x | bandwidth bound   |

Two wins, deliberately kept separate:
* **Serial/algorithmic**: 231.58 ms -> 78.49 ms at 512^2 (2.95x) by fusing
  surface + refraction + splat into one pass and deleting the post-clamp global
  rescale pass. Same machine, same grid, single thread.
* **Parallel**: 78.49 ms -> 36.22 ms at 8 threads (2.17x). 8 threads is the
  optimum on a 16-core part; beyond that the per-thread splat buffers and memory
  traffic dominate, and 24 threads is actively worse than 1.
* Combined at 512^2: 231.58 ms -> 36.22 ms = **6.4x**, with the peak artifact
  gone at the same time.

Cost split: the Airy correction is ~2x the quadrature pass, so about two thirds
of a bake is the wave term. That is the obvious next optimization target - it is
embarrassingly parallel per channel and currently dominated by the exact EDT.

--------------------------------------------------------------------------------
## 6. Port agreement (C++ vs Python reference)
--------------------------------------------------------------------------------

`parity_cpp_vs_py.py`, 512^2, t = 1.7, airy_scale = 1.0:

| field     | C++ peak | Python peak | max abs diff     |
|-----------|----------|-------------|------------------|
| geometric |   9.281  |    9.280    | 5.6e-04 (0.006%) |
| wave R    |   4.754  |    4.731    | 6.1e-01          |
| wave G    |   4.762  |    4.749    | 6.1e-01          |
| wave B    |   4.774  |    4.772    | 6.1e-01          |

Peaks agree to 0.3%. The remaining localized differences sit on fold pixels and
come from the Airy LUT resolution in C++ versus exact `scipy.special.airy`, plus
EDT tie-breaking. Parallel vs serial output agrees to 3.8e-06 (relative
1.1e-08): floating-point reduction order only.

--------------------------------------------------------------------------------
## 7. What is NOT shown / open problems
--------------------------------------------------------------------------------

1. **No experimental ground truth.** Nothing here is validated against a
   photographed or measured caustic. The reference is the model itself at finer
   resolution. Real validation means fringe spacing against a laser and a known
   lens - that is the experiment a paper must add.
2. **One scene.** A sum of 4 sine waves, one time, one sun angle. No ensemble
   statistics over wave spectra, no wind, no moving bodies.
3. **`airy_scale` is a visibility parameter**, not a prediction. The honest
   physics claim is about FORM (finite Airy fringes, chromatic ordering, no
   1/sqrt divergence), not absolute fringe width.
4. **Coherence is not modelled.** Sunlight has a ~0.5 um coherence length; we
   apply the wave correction near folds unconditionally instead of gating it on
   path-length difference. The `coherence.hpp` gate from the viability study is
   still unimplemented.
5. **The fold threshold is still a threshold.** 2nd percentile of |det J| is
   better-behaved than an intensity percentile, but a scale-space or
   sign-change formulation would be threshold-free.
6. **Single machine, single compiler** (MSVC 14.41, /O2). No GPU port yet.
7. **Efficiency is not uniform.** Below ~262 k splats a stochastic estimator is
   competitive or better. The advantage only appears once the budget reaches the
   ~1 M splat range where fringes exist at all.

--------------------------------------------------------------------------------
## 8. Chromatic dispersion: how wide the band may be
--------------------------------------------------------------------------------

`tools/dispersion_scale.py`, 1024^2 grid, per-channel deviation from the field
mean (field mean is 1.0, so 0.05 = 5% colour):

| airy_scale | band width | mean spread | max spread | pixels with R-B > 5% | resolved fringes |
|------------|------------|-------------|------------|----------------------|------------------|
| 0.020      |   3.4 px   | 0.1008      | 2.9710     | 75.34%               | 38 |
| 0.040      |   6.8 px   | 0.0234      | 1.3467     | 43.10%               | 18 |
| 0.080      |  13.7 px   | 0.0060      | 0.1678     |  6.60%               | 15 |
| 0.160      |  27.3 px   | 0.0048      | 0.1208     |  4.16%               | 12 |
| 0.320      |  54.6 px   | 0.0031      | 0.0824     |  0.97%               |  9 |

Two rules that fall straight out of this, and they pull in opposite directions:
* the band must span **at least ~3 px** or the fringe structure cannot be
  resolved (at 1024^2 over a 6 m patch that is airy_scale >= 0.0176);
* colour **falls** as the band widens - ~10% mean spread at 0.02 down to 0.3% at
  0.32 - because at large w the Airy profile is nearly flat across the band, so
  the ~12% width difference between R and B stops changing any value much.
  Widening the band to make the *fringes* easier to see makes the *colour*
  disappear. 0.02 currently sits at the good end of both constraints.
* The library default was 1.0 (50 px wide on that grid): unresolvable band AND
  effectively monochrome. Corrected to 0.02.

--------------------------------------------------------------------------------
## 9. Showcase render (glass of water on a wood table)
--------------------------------------------------------------------------------

`showcase.exe` — an offline still on the geometry of the reference photograph,
rendered by a small physically-based renderer written in `src/app/showcase_main.cpp`:

* a genuine multi-layer dielectric: air | glass shell (n = 1.5095 + 4200/lambda^2,
  3.5 mm wall) | water (Cauchy), walked with Fresnel at every interface, so the
  background is refracted through the glass and the rim highlights are transport,
  not paint
* Beer-Lambert absorption in glass and water
* the sun as a 1.2 deg disk, so penumbrae are real (6 shadow-ray samples)
* a gradient environment for the reflected branches and ambient
* a rough-specular sheen on the table (jittered reflection picking up sky or glass)
* thin-lens depth of field, ACES-style filmic tonemapping, vignette
* the caustic fan itself from our wave model, evaluated per channel (dispersion)

1600x1000, 4x SSAA (25.6 M samples), 8 threads, 4.2 s.

### Is it photoreal? Measured against the photograph

There is no image-understanding tool in this environment, so "photoreal" cannot
be settled by looking here. Instead `tools/compare_to_reference.py` compares the
render to the reference photograph's measurable statistics. Matching these is
necessary but not sufficient; mismatching them would refute photorealism.

| statistic | reference | render | delta | tolerance | verdict |
|-----------|-----------|--------|-------|-----------|---------|
| mean          | 108.2 | 112.6 | +4.4  | 18.0 | ok |
| p25           |  79.3 | 107.0 | +27.7 | 25.0 | **OFF** |
| p75           | 129.0 | 126.7 | -2.3  | 25.0 | ok |
| range p5..p95 | 129.0 | 101.7 | -27.3 | 30.0 | ok |
| warmth (R-B)  |  18.5 |  18.7 | +0.2  |  8.0 | ok |
| detail (mean abs horizontal gradient) | 2.0 | 1.6 | -0.4 | 0.8 | ok |

5/6. The failure is informative: p25 is the 25th percentile, so the reference has
a quarter of its frame below 79 while ours stops at 107 — our scene lacks a large
dark region. The photograph's darkest quarter is the unlit part of the table plus
its shadow; our light is directional and the table is lit fairly evenly outside
the shadow, so we cannot reproduce that distribution without either a bigger
shadowed area in frame or a near-source falloff the sun does not physically have.

Honest limits that remain:
* no interreflection and a single indirect bounce; no path-traced caustic (the
  caustic is our model's, which is the point of the image)
* glass top/bottom caps are approximated as flat discs
* procedural wood; no measured BRDF
* the fan is 1.7% of samples and the blown glint is <0.1% of pixels, so a viewer
  comparing it to the photograph will notice the photograph's brighter, broader
  lit patch first — that is the p25 row above, not a physics error

### Three bugs the measurements caught (all real, all fixed)

1. **The entire table was being replaced by the ground colour.** My
   `next_crossing` rejected any crossing whose two sides are the same medium —
   which is *every* table hit outside the glass footprint, because a table has
   air on both sides. Symptom: max caustic sample 0.000, table samples 47 k
   against 1.2 M after the fix, no wood, no shadow. Fixed with an explicit
   surface-kind flag (0 = table, 1 = dielectric) and the medium guard applied
   only to dielectrics.
2. **Zero shadows.** Shadow rays were cast along `kSun` (the direction light
   travels) instead of toward the light. Symptom: shadow samples 0 of 1.2 M
   table samples. Fixed, now 7.2 M shadow samples at 1600x1000x4.
3. **Colour destroyed by clipping, then by the wrong curve.** The fan was ~30x
   overexposed and Reinhard-on-a-linear-add flattened every channel to white:
   6.65% field colour became 0.02% image colour. A correct exposure plus an
   ACES-style per-channel shoulder keeps it: 0.10% of pixels now carry strong
   colour and nothing clips (blown 0.00%, max 252).

Earlier corrections, kept for the record: the sun elevation is constrained (at
59 deg the refracted ray crosses the table inside the glass and the field comes
out empty — hence the low late-afternoon sun), and the caustic for a vertical
cylinder is a family of straight lines, so it needs the invariant 1-D model, not
a 2-D point splat (0.05% -> 1.7% of samples).

The chromatic separation is carried by the **per-channel ray map** (n varies with
lambda, so the fold positions shift), not by the Airy width: the field's |R-B| is
identical at airy_scale 0.0012 / 0.0025 / 0.006.

---

## 10. Cycles integration: the wavy model, photorealism, and the Blender plug-in

### 10.1 The smooth-cylinder caustic was missing the interesting half

The original showcase traced one refraction (the glass wall) and treated the
water as a plane, which produces a fan of straight lines. A real glass of water
is turbulent in its caustic because light also enters **above the water line**,
crosses the air gap inside the glass, and refracts off the **rippling water
surface** before reaching the table.

`trace_wavy()` in `src/app/showcase_main.cpp` now walks four interfaces
(air→glass wall, glass→water below the line or glass→air above it, then
air→water at the wavy surface). With ripples present the pattern is invariant
along no axis, so the ray map becomes 2-D over `(phi, z0)` and folds are the
locus where its Jacobian determinant vanishes — the same machinery as the pool
baker, applied to a new geometry.

| | flat model | wavy model |
|---|---|---|
| peak (cap 8.10) | 8.100 | 8.100 (still bounded) |
| field mean | 0.196 | 0.382 |
| mean \|R-B\| | 0.057 (too weak) | **0.1194 = 31.2% of field mean, dispersion VISIBLE** |
| caustic samples in the still | 20 274 | 26 474 |

Bug found on the way, worth recording: at the *inner* wall the ray is still
travelling inward, so the normal facing it is the **outward** one. Using the
inward normal made `snell()` reject every ray and the entire field came out 0.000.

### 10.2 Rendering it in Cycles instead of by hand

A hand-written renderer cannot reach Cycles-grade realism (no GI, no MIS, no
spectral colour management, no real BSDFs). `tools/blender_scene.py` builds the
scene in Blender 4.2 and injects the baked caustic:

* glass shell (r 0.035 m, h 0.090 m, IOR 1.5) and water (IOR 1.333) as real
  transmission materials, so the background is genuinely refracted;
* `AgX` view transform, sun with a physical angular size, gradient environment;
* the caustic from `--dump-caustic` (16-bit PNG, linear, row 0 = +Y) injected as
  an Emission shader added on top of the receiver's Principled BSDF;
* Cycles' own caustics switched off, so the injected caustic is the only one;
* OptiX GPU: 1800×1125 at 640 samples in **12.4 s**.

### 10.3 Realism, measured against the photograph

There is no image-understanding model in this environment, so "does it look
photoreal" is checked as statistics against the reference photograph, never by
eye. `tools/compare_to_reference.py`:

```
statistic  reference     render      delta     tol  verdict
      mean      183.2      174.6       -8.7    18.0  ok
       p25      155.0      122.7      -32.3    25.0  OFF
       p75      219.3      217.3       -2.0    25.0  ok
     range      138.0      115.0      -23.0    30.0  ok
    warmth      -19.3      -16.6       +2.8     8.0  ok
    detail        1.5        0.9       -0.6     0.8  ok
```

5/6. The one miss is `p25`: the photograph has a large, genuinely dark shadow
region and ours has no dark quarter, because the reference is lit by a dim room
while ours has a bright environment. Two measurement bugs were found and fixed
while doing this, both of which had been inflating or deflating the verdict:

* **resolution.** Gradient energy is resolution-dependent; a 1800×1125 render
  compared against an 800×457 photograph is not a like-for-like `detail`. The
  render is now resampled onto the reference's grid before measuring.
* **the blown pixels.** 9.4% of the frame was clipped and it did **not** move
  when the caustic gain changed — because it was not the caustic. It was the
  table's glossy reflection of the sun's disc (radiance ≈ E/Ω ≈ 5000). The
  reference surface is matte; lowering the specular level took blown from 9.40%
  to **0.00%**.

### 10.4 The plug-in, and an honest A/B against Cycles

`blender_addon/caustic_injector.py` installs as a Blender add-on (N-panel →
*Caustic*): bake with the solver (272 ms at 256², 0.27 s), inject the node graph,
toggle Cycles' caustics. `tools/test_addon.py` proves it headless — 7/7 PASS,
including that injection moves 65.5% of pixels and raises mean luma 144.9 → 163.6.

`tools/caustic_vs_cycles.py` renders the same scene with Cycles' native caustics
and with ours injected, at 64 and 256 samples, **denoiser off** (the denoiser
hides exactly the noise being measured — this was a real trap: with it on, both
modes looked noise-free and the A/B was meaningless).

| 2.4° sun, 640×400 | Cycles native | ours injected |
|---|---|---|
| RMSE whole frame | 7.67 | **2.29** (3.3× quieter) |
| RMSE caustic region | 1.50 | 1.42 (1.1× quieter) |
| bake cost | — | 0.27 s once |

The whole-frame noise improves 3.3× because the injected caustic is
deterministic. In the caustic region the two are **nearly tied**: at a physical
sun size most light reaching the table passes straight through the glass and is
easy to sample, so the concentrated caustic carries little of the energy. This is
a modest win in this configuration, not an order of magnitude, and it is recorded
as such. The unconditional advantages remain accuracy at the fold (bounded 7.7×
vs geometric blow-up, flux 1.0000) and per-channel dispersion, not speed.

### 10.5 The decisive test: dark room, tiny source (negative result)

§10.4 tested the easy case — a physical sun in a bright room, where most light
passes straight through the glass and the caustic carries little energy.
`tools/hard_caustic_ab.py` tests the hard case, which is also the case in the
reference photograph: a 0.05 deg source in a dark room (world 0.015), so the
caustic is nearly the only light on the table and it is the subject. RMSE is
measured against each mode's own converged 2048-sample render.

| samples | Cycles RMSE (caustic) | ours | Cycles time | ours | advantage |
|---|---|---|---|---|---|
| 16 | 0.87 | 1.08 | 1.6 s | 1.7 s | 0.8x |
| 64 | 0.51 | 0.53 | 1.8 s | 1.7 s | 1.0x |
| 256 | 0.46 | **0.34** | 2.0 s | 1.9 s | 1.3x |

Whole frame at 256 samples: Cycles 8.81 vs ours **2.56** (3.4x less error at
equal time, 2.0 s vs 1.9 s).

**Reading this honestly.** Making the source 48x smaller and the room 33x darker
did *not* open the gap the theory predicted. In the caustic region the two
methods are within 1.3x, and ours is actually *worse* at 16 samples. The
whole-frame 3.4x is real and comes from Cycles' fireflies spreading across the
frame while the injected caustic contributes no variance at all.

The reason the hard case stayed easy: this caustic is a **short specular chain**
(light -> glass wall -> water surface -> table). Cycles samples that chain with
BSDF sampling at high probability, because the surfaces are smooth and the
transmission dominates. Path tracing collapses on caustics that require a
*long* chain — light into a diffuse bounce and back through a specular surface
(SDS paths), or caustics off rough media. This solver models the direct
image-forming caustic only, so it cannot be tested against those cases without
new geometry in the solver. That is the open question, and it is solver work,
not a new measurement.

**What is therefore claimed, and what is not.** Claimed: bounded folds and flux
conservation (7.7x vs 100x+ blow-up, 1.0000), 1.65x accuracy at a matched splat
budget, 35% below the MC floor with 16x fewer splats, per-channel dispersion,
determinism, and a 3.4x whole-frame error reduction at equal time in this scene.
Not claimed: a decisive efficiency or quality win over Cycles path tracing in
any configuration tested so far.
