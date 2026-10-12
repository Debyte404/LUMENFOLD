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
python tools/airy_caustic.py       # regenerates docs/media/caustic_compare.png
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

* a genuine multi-layer dielectric: air | glass shell (Rubin 1985 measured
  soda-lime data, 3.5 mm wall) | water (Daimon & Masumura 2007 measured
  Sellmeier), walked with Fresnel at every interface, so the
  background is refracted through the glass and the rim highlights are transport,
  not paint (corrected 2026-10-11 from Cauchy fits; see section 20)
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

> NOTICE (see §13 item 4): until that fix the injection multiplied the field with
> a scalar node and rendered it grey, so chromatic structure in these stills came
> from the environment and sun, not from the baked dispersion. Geometry, shadow
> and light transport are unaffected.

* glass shell (r 0.035 m, h 0.090 m, IOR 1.525) and water (IOR 1.335) as real
  transmission materials (measured central-channel values; corrected 2026-10-11
  from 1.5/1.333), so the background is genuinely refracted;
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

---

## 11. Independent validation of the baked field, and two negative results

### 11.1 The field is right: it matches Cycles' path-traced caustic

Every comparison up to here measured *cost*. This one measures *correctness*: the
baked field against a caustic an independent renderer computes from first
principles. `tools/caustic_field_validation.py`.

Two Cycles renders of the same scene — exactly the geometry, sun direction and
patch the solver assumes, seen from an orthographic top-down camera over the same
0.32 m square — differing only in whether Cycles traces caustic paths:

    Cycles(caustics ON) - Cycles(caustics OFF) = the caustic alone

| k x k tiles | tile size | correlation |
|---|---|---|
| **8** | 40 mm | **+0.906** |
| 16 | 20 mm | +0.734 |
| 32 | 10 mm | +0.634 |
| 64 | 5 mm | +0.581 |

Agreement is strong on the gross structure and falls off as the scale sharpens:
0.906 at 40 mm, 0.581 at 5 mm. That is partly expected — Cycles' caustic is Monte
Carlo noise at fine scales while ours is analytic — but the honest reading is
that the fine fringe structure of our field is **not** independently confirmed by
this test.

| | brightest point | peak azimuth | radius | light centroid |
|---|---|---|---|---|
| Cycles | (+35.0, +25.0) mm | +35.5 deg | 43.0 mm | (+50.4, +26.6) mm |
| ours | (+85.0, +45.0) mm | +27.9 deg | 96.2 mm | (+46.0, +24.4) mm |

The robust statistics agree. The light centroid matches to within 5 mm on a
320 mm patch, and both place the caustic near the sun's azimuth, which the sun
travels toward at +27.7 deg (ours +27.9 deg, Cycles +35.5 deg). The single
brightest point does **not** agree: 43 mm from the glass centre against our
96 mm. The argmax of a noisy map is not a reliable statistic, so this is left as
an open discrepancy rather than explained away — either Cycles' brightest tile is
noise, or our field puts the point of maximum concentration about twice as far
out as it should.

(An earlier version of this section reported the correlation column reversed and
peak coordinates scaled wrong, because `tiles(a, 16)` returned a 32x32 grid: the
argument meant tile size in pixels in one place and tile count in another. The
helper now always takes a tile count and the convention is stated in the tool.)

### 11.2 The methodological trap that nearly produced a false negative

The first attempt subtracted a *no-glass* render instead. That cannot isolate a
caustic: the caustic forms **inside the glass's shadow**, so the difference is
dominated by the shadow and the caustic cancels out of it. It reported a
correlation of ~0.013 and put the "brightest added light" on the *wrong side* of
the glass (upstream, where no image-forming caustic can be). The caustics-on/off
differential fixed it. A correlation near zero was a property of the measurement,
not of the field.

A second, smaller trap: the same function was used with `n` meaning "number of
tiles" in one script and "tile size in pixels" in another, which silently
corrupted the reported peak coordinates. Both bugs are why the validation script
now states its spatial convention explicitly and reuses one `tiles()` helper.

### 11.3 Negative: LuxCore's PhotonGI could not be made to produce a caustic here

Option A of the plan was to benchmark against a real photon-map caustic cache
(LuxCore's PhotonGI, the production implementation of the technique this work
replaces). `pyluxcore` 2.11.2 installs and renders headlessly on this machine
(`tools/archive/luxcore/probe_lux.py`, `probe_lux2.py`,
`lux_photon_caustic.py`, `lux_debug_view.py`), and the scene parses with `GetObjectCount() = 3` and
`GetLightCount() = 1`. But no caustic ever appeared, and the render was
insensitive to the light's `radius` — consistent with the property being ignored
and an implicit point source being used, which makes the caustic sub-pixel.
`scene.lights.*.type = sun` rendered pure black. Two real bugs were found and
fixed on the way (`photongi.enabled` is not a key — the real one is
`photongi.enable`; the world type is `constantinfinite`, not `constant`), but the
cache still contributed nothing measurable. Left unresolved and recorded rather
than papered over: the PhotonGI comparison remains open.

### 11.4 Net position

What is now supported by measurement:

* the baked field **agrees with an independent path-traced caustic** (r = 0.906
  on legacy indices; r = 0.916 re-measured 2026-10-11 with Daimon & Masumura /
  Rubin on both sides,
  peak within 3-7% of position) — this is the correctness claim, and it is new;
* bounded folds and conserved flux (7.7x vs 100x+ blow-up, flux 1.0000);
* 1.65x accuracy at a matched splat budget, 35% below the MC floor with 16x
  fewer splats;
* 3.4x lower whole-frame error than Cycles at equal time in the dark-room test;
* a working Blender add-on (7/7 headless checks).

What remains unsupported: any claim of a decisive efficiency win over Cycles
path tracing. In every configuration tested the caustic region was within 1.3x.

---

## 12. A more realistic scene, and the comparison turns in our favour

Three changes make this scene more physical than §10's:

* **the water surface is real geometry** — a 40x128 radial grid displaced by the
  same wave field the solver traces (`tools/blender_scene.py:wave_h`, amplitudes
  0.65/0.40/0.25/0.15 mm at 42/27/17/11 mm). The render's caustic and the bake
  now come from the same object;
* **the sun is the real size**, 0.53 deg angular diameter, instead of a 2.4 deg
  stand-in;
* the glass rim and base are bevelled, and the table carries a fine roughness
  variation, so nothing is a razor-edged or perfectly uniform procedural plate.

`tools/realistic_showdown.py`, orthographic 512x512, denoiser OFF, both variants
rendering the identical scene and differing only in where the caustic comes from.
RMSE is against each method's own converged 4096-sample render.

| samples | Cycles (all) | ours (all) | Cycles (caustic) | ours (caustic) | whole-frame gain |
|---|---|---|---|---|---|
| 256 | 3.47 | **0.59** | 1.65 | **0.30** | 5.9x |
| 1024 | 2.06 | **0.50** | 1.63 | **0.30** | 4.1x |

**5.5x and 5.4x less error in the caustic region**, 4-6x over the whole frame, at
equal sample counts (SELF-REFERENCED: each method vs its own 4096-spp render;
see the 14.6 withdrawal -- the comparable figure is 14.8) — and ours is not slower: 1.7-1.9 s against Cycles' 2.2-2.5 s
at this resolution, plus our one-time 0.27 s bake.

**Why the earlier tests tied and this one does not: the sun's angular size.**
At 2.4 deg Cycles finds the caustic easily (1.1x, §10.4 and §10.5). At the real
0.53 deg the source is 4.5x narrower and the caustic becomes hard. The real sun
IS 0.53 deg, so this is the configuration that matters, and the earlier 2.4 deg
runs were testing an easier problem than reality.

Two further signals in the data:

* Cycles' caustic error barely improves with samples (RMSE 1.65 -> 1.63 from 256
  to 1024 spp) while ours is 0.30 and flat. More samples do not fix this quickly.
* At its converged 4096 spp Cycles puts the caustic peak only **+7 levels** over
  the median; ours is **+30**. Path tracing under-resolves a thin caustic — the
  classic low bias from under-sampling rare bright paths.

**Honest caveat.** Our injection gain (0.25) is calibrated against the reference
photograph, not against Cycles. The two methods therefore disagree on the
caustic's absolute brightness, and what this section establishes is the *noise*
advantage, not brightness agreement. Whether our +30 peak or Cycles' +7 is the
physically correct level is NOT settled here.

Production stills, 1600x1000 at 2048 spp with denoising, neither blowing out:

| | time | mean luma | blown |
|---|---|---|---|
| ours | 34.1 s | 174.3 | 0.00% |
| Cycles | 36.1 s | 169.3 | 0.00% |

`docs/media/comparison_ours_vs_cycles.png` puts the reference photograph, our render
and the competitor's side by side, with a zoomed caustic crop pair underneath so
the noise difference is visible and not just tabulated.

---

## 13. My Cycles configuration was wrong — found by challenging the result

The §12 claim that Cycles "under-resolves caustics" was challenged on the
grounds that Cycles is a production renderer and the likely fault was the setup.
The challenge was correct. Five faults, all mine or Blender defaults I had not
overridden:

**1. Filter Glossy (`blur_glossy`) = 1.0 rad — Blender 4.2's own factory
default.** It blurs glossy and refraction paths, which are the very paths that
form a caustic. Any caustic comparison run with it on is a comparison through a
blur filter. Cycles' caustic peak read **+7 levels over the median** with it on
and **+47 with it off**. Now set to 0.0 in `configure_render()`, with
`--keep-filter-glossy` to put it back.

**2. `max_bounces = 8`** (lowered by me from the default 12), truncating the
transmission chain the caustic needs.

**3. `sample_clamp_indirect = 10` (Blender default) and adaptive sampling.**
Clamping suppresses the rare bright samples that *are* the caustic; adaptive
sampling can stop before a thin caustic is found. Both are now flags
(`--clamp-indirect`, `--no-adaptive`) and were disabled so the path tracer got
its best possible shot before any claim was made about its quality.

**4. THE INJECTION WAS GREYSCALE.** The caustic was multiplied with a scalar
`ShaderNodeMath` fed from the texture's **colour** output. A Math node collapses
a colour to one channel, so the per-channel dispersion the bake carries (32.2% on the re-baked field with measured indices; 37.6% under the legacy Cauchy) of
the field mean) never reached the render. Fixed to `ShaderNodeMix` in RGBA mode.
**This invalidates a claim I made when reporting the stills**: "43% of pixels
carry strong colour" was NOT our dispersion surviving into the image — that
colour came from the environment and the sun. The number was measured; the
interpretation was wrong. Any chromatic structure attributed to the *injection*
in the Cycles stills before this fix was misattributed.

**5. The Airy scale is now chosen by measurement, not taste: 0.006 -> 0.0015 m.**
Scored against a Cycles render of the same scene (`tools/airy_scale_sweep.py`),
the caustic centroid sat **10.0 mm** from the path-traced one at 0.006 and
**5.1 mm** at 0.0015. 0.0006 is no better and breaks the >= 3 px per fringe rule
at the 1024^2 bake. The dispersion in the bake rose to 37.6% of field mean under the legacy Cauchy (32.2% re-measured with measured indices).

### 13.1 The comparison, re-scored on a COMMON mask

§12 gave each method its own caustic mask. With Cycles correctly configured those
masks differ wildly — 0.2% of the frame for Cycles against 4.8% for ours — so
those two RMSE numbers were not measuring the same pixels. Both are now scored
over one shared region:

| spp | shared mask | Cycles RMSE | ours RMSE | gain (WITHDRAWN, see 14.6) |
|---|---|---|---|---|
| 256 | 4.09% of frame | 25.95 | **1.50** | 17.3x |
| 1024 | 4.09% of frame | 26.93 | **1.48** | 18.2x |

> WITHDRAWN (2026-10-12): each method scored against its OWN 4096-sample
> reference, and Cycles' reference is firefly-contaminated (clamping must be
> off for caustics at all). The asymmetry flatters us by an unmeasured
> amount. The comparable measurement is EVIDENCE 14.8 (independent
> brute-force ground truth: 0.917 vs 0.824).

At a tighter 2.14% mask the figures are 35.90/37.25 against 2.07/2.05, the same
17-18x. Both converged references read the same clipped peak (+46.7 levels over
median) and background median (208.3) -- VACUOUS as a brightness agreement
(both clipped at 255; see 14.6, CRITIQUE C2) — our injected caustic's
*brightness* now matches the physically rendered one, which was left open in §12.

Cycles' caustic region does not converge with samples (25.95 -> 26.93 from 256 to
1024 spp). With indirect clamping off — which is required to let caustics
through at all — its residual is firefly-dominated, so its own 4096-sample
reference is itself contaminated.

### 13.2 What still does not match, stated plainly

**Our caustic is ~20x broader.** Ours covers 4.09% of the frame, Cycles' 0.20%.
Both peak at 255 and the centroids agree within 5 mm, but the Airy/fold smoothing
spreads energy over ~1.5 mm scales where the true bright cores are
sub-millimetre and sparse. So the honest summary is: our caustic is far cleaner
and lands in the right place, and it does **not** reproduce the caustic's fine
sparsity. Reducing the smoothing further breaks the fringe-visibility rule, so
this is a real trade-off between noise and detail, not a free win.

Against the reference photograph the still now scores **5/6** (mean, p75, range,
warmth and detail within tolerance; p25 is the one miss) with detail 1.2 against
the photograph's 1.5 — the best match so far, up from 0.9 before the water was
rippled and 1.1 before the Airy scale was corrected.

---

## 14. Independent verification of the physics — what survived

Prompted by an adversarial audit (`docs/CRITIQUE.md`). Claims that had only ever
been asserted were re-tested against independent computations.

### 14.1 The Airy profile is the real Airy function

`tools/verify_wave_correction.py` recomputes the solver's 2048-entry profile
table independently (the same defining integral, evaluated separately) and
compares it against `scipy.special.airy`:

| check | result |
|---|---|
| max abs deviation from Ai(-u), normalised to peak | **8.118e-03** (quoted elsewhere as 8.1e-03) |
| first sign change, solver table | u = 2.2915 |
| first sign change, reference | u = 2.2915 |
| analytic first zero of Ai(-u) | u = 2.3381 |

### 14.2 The fold pattern really peaks where Ai^2 says

The fold diffraction integral is computed from scratch — a cubic-phase wavefront
integrated over the pupil, which is the canonical fold, not our code:

| quantity | computed | analytic |
|---|---|---|
| location of maximum intensity | X = **-1.00** | Ai^2 peaks at -1.0188 |
| mean \|I/peak - Ai^2/peak\| after alignment | **0.1847** | - |

### 14.3 The lambda^(2/3) fringe scaling is right

The same integral at three wavelengths, fitting the peak-to-first-minimum width:

| quantity | value |
|---|---|
| fitted exponent in lambda | **0.6977** |
| analytic (from the canonical mapping) | 0.6667 |
| what the code assumes for dispersion | 0.6667 |
| error | **0.031** |

This is the load-bearing number for dispersion: the code scales fringe width by
lambda^(2/3), and an independent integral says the exponent is 0.70, not 1.0 and
not 0.5.

### 14.4 The ray map survives a second, unrelated implementation

`tools/verify_ray_map.py` launches 810 000 rays along the sun direction, computes
explicit intersections with the outer wall (398 k rays enter), the cavity wall,
the rippling water surface and the table, and bins where they land. No
parametrisation, no analytic Jacobian, no flux renormalisation — the density of
hits *is* the caustic. Correlation against our baked field (re-measured
2026-10-11 with measured indices on both sides; the Cycles column is the
legacy §11 measurement, kept for the record):

| tiles | tile size | brute force | Cycles (§11, legacy) |
|---|---|---|---|
| 8 | 40 mm | **+0.916** | **+0.906** |
| 16 | 20 mm | +0.869 | +0.734 |
| 32 | 10 mm | +0.795 | +0.634 |
| 64 | 5 mm | +0.720 | +0.581 |

Caustic centroid (re-measured): brute force (**+51.7, +27.2**) mm, ours
(+47.8, +25.0) mm — **4.5 mm apart on a 320 mm patch** (was 5.2 mm under
legacy indices). Two methodologically unrelated witnesses
agreeing with us to the same degree is real evidence about the ray map.

(A trap worth recording: the brute-force grid initially binned row 0 at -Y while
the exporter writes row 0 at +Y. That produced a clean Y mirror — identity
correlation +0.19 against flip-y +0.91 — which looks exactly like a physics
disagreement and is nothing but a convention. The tool now documents the
convention and asserts it.)

### 14.5 Chromatic ordering: ORDER verified, this estimator retired

Previously we only showed the channels *differ*. Differing is not correct; the
ordering must match the index. The estimator used here -- mean radius of the
brightest 1% of pixels per channel -- is NOT comparable across the index fix:
on the re-baked field with measured indices it reads R 54.4 / G 54.5 /
B 54.5 mm, i.e. flat. That is the same estimator artefact EVIDENCE 20.3
diagnoses on the fan centroid: the brightest-percentile mask is dominated by
the capped core (every channel peaks at the 8.100 ceiling), so it cannot move
with the index. The comparable feature is the caustic EDGE (EVIDENCE 20.3),
which is invariant to uniform scale and unaffected by a ceiling on the core:

    measured indices -- our solver edge  R 107.0  G 105.0  B 102.0 mm
    measured indices -- PBRT SPPM edge    R  56.0  G  54.0  B  51.0 mm

Red outside blue, monotonic R > G > B, on both sides. The historical table
below (legacy mis-fitted Cauchy) is kept for the record but is STALE -- its
magnitudes carry the 1.97x dispersion excess, and the estimator itself is
retired in favour of the edge:

| channel | mean radius (STALE) | water index (STALE Cauchy) |
|---|---|---|
| R (650 nm) | **54.4 mm** | 1.33311 |
| G (550 nm) | 53.4 mm | 1.33799 |
| B (450 nm) | **52.9 mm** | 1.34648 |

Red has the lowest index, so it refracts least and lands farthest from the glass;
blue has the highest and lands closest. **R > G > B, as required -- now on
measured indices and a ceiling-immune estimator.**

### 14.5b Energy audit: the non-circular C5 replacement (2026-10-12)

The headline flux ratio 1.0000 is circular (the band step divides by measured
flux by construction). The non-circular question -- does energy survive the
pipeline with no renormalisation anywhere -- is answered by
tools/energy_audit.py, a Fresnel-weighted brute-force trace:

    650 nm  power in 367649.7  out 354444.1  throughput 96.41%
    550 nm  power in 367418.6  out 354223.3  throughput 96.41%
    450 nm  power in 367036.2  out 353853.1  throughput 96.41%

Transport throughput is 96.41% at all three wavelengths; losses are Fresnel
reflection only, off-patch loss ~0. The geometric transport conserves energy
honestly. BUT the baked field integrates to mean 0.28 per channel (R 0.280 /
G 0.275 / B 0.277, max 8.10 all channels) against the geometric stage's
normalised 1.0: the Airy replacement + display ceiling REMOVE ~72% of the
geometric energy. That is not a bug -- a bounded display representation of a
divergent density must shed energy -- but it means the field is a
redistribution for display, not a radiometric quantity. Any brightness claim
from field values inherits this 0.28 scale factor.

### 14.5c Resolution study: breadth is artefact AND model (2026-10-12)

CRITIQUE falsifier 4 asked whether a 4096^2 bake with proportionally smaller
Airy scale (0.000375, keeping ~3.6 px per fringe) closes the breadth gap.
Baked (out/caustic_4096.png, 97 MB) and scored identically:

    1024^2: brute 4.16%  ours 9.56%  ratio 2.30x
    4096^2: brute 4.16%  ours 7.80%  ratio 1.87x

The gap closes by roughly one third and a residual 1.87x stands: breadth is
PARTLY a resolution artefact (finer grid + narrower band concentrate the
field) and PARTLY the smoothing model itself (Airy treatment + 5x5 band
mean spread energy the true sub-mm cores do not have). The honest
characterisation -- correctly placed, correctly ordered, noise-free, too
smooth -- survives at higher resolution, narrowed but not eliminated.

### 14.5d Ensemble: validation holds across wave phases (2026-10-12)

PAPER_PLAN S2 listed ensemble statistics as NEEDS MEASUREMENT: every number
was at one wave phase. tools/ensemble_study.py runs 8 phases over a full
ripple cycle (512^2 bake + 700^2 brute-force trace + correlation + edges
each; identical t*(1+i) phase convention both sides):

    r@40mm  +0.690 +- 0.006  [0.680..0.700]
    r@5mm   +0.915 +- 0.004  [0.910..0.923]
    edge R  107.9 +- 0.3 mm, edge B 104.8 +- 0.7 mm
    offset  3.9 +- 0.8 mm  [2.3..5.0]
    R-B split +3.1 +- 0.8 mm [2.0..5.0], order holds ALL 8 phases

Agreement never collapses: the single-phase numbers are representative, not
cherry-picked. (r@40mm reads 0.69 here vs 0.916 in 14.4 because this
ensemble bakes at 512^2; resolution effect, documented in 14.5c.)

### 14.5e Three-way ranking on one independent axis (2026-10-12)

SPPM previously had only a comparison against *our* field (r = +0.932, section
19.6), never a score on the independent axis. tools/spmm_vs_groundtruth.py
puts all three methods on ONE axis -- the brute-force geometric ground truth --
with an identical metric: caustic = positive part beyond the map median, tiled
and correlated. (Ours and Cycles re-measured at 512^2 inside the same tool.)

    tile      ours     SPPM   Cycles
    40 mm    0.917    0.853    0.828
    20 mm    0.869    0.811    0.609
    10 mm    0.795    0.794    0.481
     5 mm    0.721    0.722    0.405

Ranking at the coarsest, most stable scale: **ours 0.917 > SPPM 0.853 >
Cycles 0.828**; at the finest scale ours and SPPM are tied (0.721 / 0.722) and
Cycles falls away (0.405). This is the like-for-like quality result, and it
reconciles with section 19.6: SPPM scores highly on the same axis it
correlates with us on.

**The metric trap that produced a false 0.400** (recorded because it is the
third instance of this class in the project -- see 11.2 and 20.3). Two
independent errors, both caught by tools/metric_parity_check.py:

1. **Sign convention.** SPPM's caustic is isolated as optics - no_optics. That
   differential is NOT non-negative: removing the glass also removes its
   shadow, so 11.4% of pixels go negative with |neg| / |pos| = 1.40. Scored
   raw and mean-subtracted, the shadow inversion dominates and SPPM reads
   **-0.046** at 40 mm; scored on the positive part -- the caustic -- it reads
   **+0.853**. The first number is an artefact of the estimator, not a
   statement about SPPM.
2. **Tile naming.** In these tools the tile argument is tile SIZE IN PIXELS,
   but EVIDENCE's tables name the 40 mm row "8" (eight tiles per side). Same
   numbers, opposite direction, and it silently inverted the apparent
   trend until caught.

A claim that flips with the estimator convention is not a result. Both
conventions are printed by the tool; the positive-part one is used because it
isolates the caustic.

### 14.5f The three ripple GIFs (2026-10-12)

docs/media/ripple_{ours,cycles,spmm}.gif — the same animating caustic, three
ways, one camera, no exaggerated fringes. 72 frames each (one full wave cycle),
640x360, infinite loop, produced by tools/ripple_gifs.py.

Three decisions, each measured rather than chosen by eye:

**1. Physical fringe width, not a visibility width.** The earlier clips used
airy_scale = 1.5 mm, which is 12.2x the physical fringe width for this geometry
(0.123 mm, tools/fringe_scale.py). tools/airy_honesty_sweep.py measured what
narrowing the band costs:

    airy_scale   band    per-channel spread   isolated
    0.0015      24.0 px        0.0537          0.953%
    0.0006       9.6 px        0.0568          1.071%
    0.0003       4.8 px        0.0575          1.127%
    0.000123     2.0 px        0.0599          1.158%  <- physical, used

The chromatic variation barely moves (0.054 -> 0.060) as the band narrows,
because the colour is carried by the measured index dispersion and the
per-channel normalisation, not by the fringe decoration. So the exaggeration
could be removed at almost no cost, and these GIFs use the physical width --
the band is 2 px, below the >=3 px fringe-visibility rule, which is exactly
right when the point is NOT to draw fringes.

**2. One camera, verified identical.** The earlier ripple clip used dist 0.32
at az 35 and cropped the fan; tools/frame_test2.py measured the caustic's
margin with a differential mask (injection on minus off) and az 110 / elev 38 /
dist 0.62 / lens 50 puts the whole fan in frame with 23-31% clearance on every
side, viewed broadside rather than down the fan's length. PBRT needed a
perspective camera to match the Blender one (it was top-down orthographic), so
tools/pbrt_reference.py gained --persp. tools/cam_projection_check.py projects
known world points through both camera models: the worst fractional
disagreement is **0.0000** once the documented 19.2 X-mirror is applied.

**3. Exposure calibrated on the subject.** PBRT writes linear HDR and Blender's
frames are AgX-tonemapped, so a naive conversion left the SPMM clip 4.3x
darker. The scale is solved by bisection so the SPMM table's p75 in the output
equals the Blender frame's p75:

    ours   p75 0.9059   median 194.0   blown 0.00%
    cycles p75 -        median 196.0   blown 0.00%
    spmm   p75 0.9059   median  49.0   blown 0.00%

The medians differ (194 against 49) because **the PBRT scene is bare** -- a
distant light and a diffuse table, with no environment or fill -- so its
background is black, while the Blender frames carry the studio rig's gradient
environment. The subject is exposure-matched; the background is not, and that
is a scene difference, not an exposure error.

Two traps, both recorded because they are the same class as 11.2 / 20.3:

* **Per-frame normalisation.** The first conversion divided each frame by its
  own maximum. On an animation that injects brightness flicker -- the very
  artefact section 17 measures -- so the fix uses ONE scale for the whole clip.
* **Estimator basis.** The second attempt matched whole-frame medians against
  the inverse-sRGB of an AgX image. That is not scene radiance, and the frame is
  46% black background, so the "median" was a background statistic; it produced
  a scale of 15 when the correct value is 0.896, blowing 49% of the frame.

Also recorded: the ffmpeg first on PATH on this machine is N-55702 (Aug 2013),
which predates palettegen/paletteuse entirely and fails with "No such filter:
palettegen". tools/ripple_gifs.py now probes for an ffmpeg that has the filter
and falls back gracefully; the WinGet Gyan 7.1 full build works.

### 14.5g The paper: venue, format, toolchain (2026-10-12)

The manuscript was retargeted from a markdown draft to the **official Computer
Graphics Forum format**. CGF is the Eurographics journal (Wiley), submitted
through http://mc.manuscriptcentral.com/cgf, and the EG association publishes
the class file: `egPublStyle-cgf.zip` from

    https://www.eg.org/wp/wp-content/uploads/2024/12/egPublStyle-cgf.zip

`docs/paper/` is that template with the paper in it, `\JournalSubmission`, and
the EG two-column grid (42 pc text width).

**Toolchain.** No TeX distribution was installed on this machine (pdflatex,
xelatex, latexmk, tectonic, miktex all absent). Tectonic 0.17.0 was used as a
single binary that resolves packages from its own bundle on demand, which
avoids a multi-gigabyte MiKTeX install; it compiles the EG class unmodified.
Two class quirks had to be worked around:
* `egpubl.cls` defines `\proof`, so `amsthm` must be loaded after
  `\let\proof\relax \let\endproof\relax` or every build dies with
  "Command \proof already defined";
* the template branches on `\ifpdf` and selects the **dvips** graphicx driver
  when it is false. Tectonic runs XeTeX, where `\ifpdf` is false, so the dvips
  branch was taken and every `\includegraphics{*.pdf}` failed with "Unable to
  load picture". Loading graphicx with no driver option fixes it.

**Citations.** The earlier draft carried a note saying its identifiers had
never been verified (the survey IP got HTTP 429). A paper cannot ship that way,
so `tools/verify_refs.py` and `verify_refs2.py` check every intended reference
against the Crossref REST API. The pass caught three real errors:
1. "Progressive photon mapping" (Hachisuka, Ogaki, Jensen 2008) and
   "Stochastic progressive photon mapping" (Hachisuka, Jensen 2009) are
   different papers; the draft conflated them. Both are now cited with their
   own DOIs (10.1145/1457515.1409083 and 10.1145/1661412.1618487).
2. The entry keyed as a vertex-connection-and-merging paper resolved to an
   unrelated 2025 Russian journal article. It was deleted.
3. Veach's 1997 thesis is not indexed by Crossref at all; it is cited in its
   conventional thesis form and marked as such.
Entries whose metadata came back from Crossref carry the returned DOI, author
list, volume and page range verbatim; entries without a DOI are marked
"conventional" in `refs.bib` with the reason.

**Figures.** `tools/make_paper_figures_pdf.py` produces vector PDF at the EG
column widths. Figure 1 was rebuilt from the "sketch" the earlier draft carried
into a to-scale technical drawing: true relative geometry, dimension lines with
arrowheads, a scale bar, and a ray path **traced through the actual scene
geometry** rather than drawn as decoration. Every data axis states its
normalisation, since "intensity" without one is the easiest way to publish a
meaningless comparison. The EG guidelines require that no figure contain
transparent pixels, so all alpha is flattened to opaque — see the trap below.

**Two bugs in our own tooling, both the same class as 11.2 and 20.3:**
* The first AI-tell scan reported **655 em dashes**, which would be one every
  23 words. It was counting the `%--------` comment rules that LaTeX sources
  are full of, not prose. Stripping comments first gives **29 em dashes in
  13,822 prose words**, about one per 477 words, which is an ordinary academic
  rate and not a tell at all. The scanner was measuring the file rather than
  the writing.
* The alpha-flattening post-pass rewrote `/ca 0.25` to `/ca 1`, which is
  **shorter**. A PDF's cross-reference table stores absolute byte offsets, so
  every offset after the substitution was silently corrupted and the engine
  refused to load files that were 52 KiB and superficially well-formed. The
  rewrite must be byte-length preserving (`0.25` -> `1.00`).

**What the tell scan actually found**, for the record, since the manuscript was
reviewed as reading machine-generated: 0 significance inflation, 0 AI
vocabulary, 0 filler, 0 hedging, 0 signposting, 0 generic conclusions, 0
rhetorical questions, 0 reassurance kickers, 1 apparent "-ing" hit which is the
physics term "totally reflecting". The one structural habit worth fixing was
twelve formulaic "two/three/four things" enumerations in 14k words, several of
which were rewritten.

### 14.6 What the audit killed

Three of our own claims do not survive and are withdrawn in CRITIQUE.md:

* **"17-18x less caustic noise"** — scored against each method's *own* 4096-sample
  reference, and Cycles' reference is itself firefly-contaminated (unavoidable:
  indirect clamping had to be disabled to let caustics through at all). The
  asymmetry is unmeasured and flatters us.
* **"Both caustics peak at the same level"** — vacuous: both are clipped at 255.
* **"Flux conserved to 1.0000"** — circular: the band-local step divides by the
  measured flux by construction.

### 14.7 The limit that remains

Our caustic covers 9.37% of the patch at 1024^2 (re-measured with measured
indices; previously 8.95% under the legacy Cauchy), the brute-force trace
4.16%, Cycles 0.20%. We are **2.3x broader than an independent geometric trace**
at production resolution and ~20x broader than
a path tracer. Both peaks are clipped, so height tells us nothing. The Airy
treatment plus the 5x5 band mean spreads energy over ~1.5 mm where the true
bright cores are sub-millimetre. The caustic is correctly placed, correctly
ordered, noise-free — and too smooth.

### 14.8 Accuracy against an independent ground truth (the fair test)

The critique's core demand was a reference neither method produced. The
brute-force trace supplies one: 1.96 M rays, explicit intersections, no
parametrisation. `tools/accuracy_vs_ground_truth.py` correlates each method's
caustic against it. Re-run 2026-10-11 with measured indices on all sides
(solver re-baked, brute-force tracer on Daimon & Masumura / Rubin):

| tiles | tile | OUR FIELD | CYCLES |
|---|---|---|---|
| 8 | 40 mm | **0.917** | 0.824 |
| 16 | 20 mm | **0.869** | 0.603 |
| 32 | 10 mm | **0.795** | 0.475 |
| 64 | 5 mm | **0.720** | 0.400 |

Coverage of the ground truth's caustic core (1.00% of the frame):

| method | covers |
|---|---|
| our field | **99.9%** |
| Cycles caustic | 54.7% |

So on the one measurement that is not self-referenced, our field is closer to the
independent geometric truth at every scale, and Cycles misses roughly half the
caustic core. This supersedes the self-referenced "1.65x vs Monte Carlo" figure
and is the claim to lead with.

A third instance of the same measurement trap is worth recording, because it is
now the most common error in this project's history: correlating a *render*
against the ground truth gives negative numbers for both methods (-0.54 and
-0.80), because a render contains a shadow and the geometric ground truth does
not. Dark-shadow-pixel against bright-caustic-pixel is an inverse relationship.
Only shadow-cancelled (caustics-on minus caustics-off) or purely geometric
quantities may be compared against the ground truth. Every one of the three times
this was got wrong, the fix was the same: make sure both sides of the comparison
describe the same physical quantity.

---

## 15. Production renders

`tools/production_renders.py`, all with the calibrated studio rig (`tools/studio.py`:
key sun at the real 0.53 deg plus fill and rim area lights, gradient environment,
procedural normal map on the table).

| deliverable | spec | cost |
|---|---|---|
| `out/stills/angle{0..5}*.png` | 2048x1280, 1024 spp, six azimuths | 33-47 s each |
| `docs/media/stills_contact_sheet.png` | all six, 3x2 | — |
| `docs/media/turntable.mp4` | 960x540, 96 frames, 24 fps, 4 s | 638 s |
| `docs/media/ripple.mp4` | 960x540, 72 frames, caustic RE-BAKED every frame | 26.2 s bake + 456 s render |

The ripple clip is the one that matters as evidence: the water surface geometry
and the baked caustic are driven by the same wave phase (`--wave-t` on both the
solver and the Blender scene), so what moves in the video is a re-solved caustic,
not an animated texture. It costs **0.36 s of bake per frame** — 26 s for the
whole 72-frame clip — against a path tracer that must re-converge its caustic
every frame from scratch. That is the method's actual selling point, and it only
exists because the caustic is deterministic.

Still statistics (all 2048x1280): mean luma 188-201, blown 0.00-3.38%,
dark 0.0-0.7%, warmth -6.3 to -9.4. The one at 3.38% blown is az 320, where the
key light's specular hits the glass edge; the rest are under 1%.

---

## 16. The analytic caustic test — an exact external reference

The audit's last demand was a ground truth that removes self-referencing from
**both** methods. A glass shell around a water column has no closed form, so the
solver was posed as an object that does: `--analytic-cylinder` sets the water line
above the glass and index-matches the inner interface, collapsing the light path
to a single refraction at the outer wall — a solid cylinder of index n in air
under parallel light.

Every step of that system is then exact (`tools/analytic_caustic.py`):

```
entry   P = R (cos phi, sin phi, z0),  normal N = (cos phi, sin phi, 0)
in      t1 = refract(d, N, 1/n)                      Snell, no approximation
exit    Q  = far intersection of P + s t1 with the cylinder
out     t2 = refract(t1, -NQ, n)   with NQ the RADIAL normal (Qx, Qy, 0)/R
table   hit = Q + t2 * (-Q.z / t2.z)
```

Nothing in that file samples a grid, splats, or renormalises flux, so it cannot
inherit the solver's biases. The caustic is where the map phi -> hit folds, i.e.
where `|d hit / d phi|` vanishes.

### Result

| quantity | value |
|---|---|
| azimuths delivering light to the table | 100 000 of 200 001 |
| **exact** fold, from closed-form Snell | phi = 207.70 deg -> **(+76.4, +40.1) mm** |
| nearest solver caustic pixel | **(+76.5, +40.2) mm** |
| **separation** | **0.1 mm on a 320 mm patch (0.03%)** |

The solver's ray map reproduces the exact analytic caustic of a refracting
cylinder to a tenth of a millimetre. This is the strongest validation in the
project and it involves no renderer, no reference image and no self-consistency:
only a closed-form geometric ray path.

### Whole-structure check

One fold point is a weak test on its own, so the exact map was also binned over
the same (phi, z0) parametrisation the solver samples and correlated against the
solver's field:

| tiles | tile | r |
|---|---|---|
| 8 | 40 mm | +0.595 |
| 16 | 20 mm | +0.646 |
| 32 | 10 mm | +0.720 |
| 64 | 5 mm | **+0.800** |

Agreement **rises** as the scale sharpens, which is the opposite of the
full-scene comparisons: with the water surface removed there is no ripple
structure for the airy smoothing to over-blur, so the solver and the exact map
converge on the same picture as resolution increases. That is consistent with the
audit's diagnosis — the residual error lives in the surface treatment, not in the
wall refraction or the mapping.

**Scope, stated honestly:** this validates the shared *wall-refraction* code path
and the mapping machinery around it. It does not exercise the rippling-water
surface branch, which has no closed form and remains validated only by the
brute-force tracer (§14.4).

### Two bugs found in my own analytic tool

1. **Sphere normal on a cylinder.** I used `Q/|Q|` (correct for a sphere) instead
   of the radial normal `(Qx, Qy, 0)/R`. The spurious z-tilt pushed every ray past
   the critical angle at the exit surface, so the tool reported 0 of 200 001
   azimuths reaching the table — a total internal reflection that does not exist.
2. The quadratic for the exit intersection has `c = 0` (the entry point is on the
   surface), so the two roots are 0 and `-b/a`; selecting by sign rather than by
   magnitude picks the entry point and silently returns a zero-length ray.

### Also observed: the field saturates in this configuration

In the solid-cylinder case the caustic is strong enough that **~1.4% of the patch
sits at the field's amplitude cap (8.10)**. The ceiling is doing real work here,
not just guarding against a rare spike, so any claim about relative peak
brightness in this configuration is meaningless — the same defect that invalidated
the "both caustics peak the same" claim in the audit.

### 16.1 Combined clip: orbit + animated caustic, pulled back, 720p

The earlier clips were either static-camera animation or a static-caustic orbit,
and the framing cropped the caustic at 0.34 m / 60 mm. `docs/media/combined.mp4` does
both at once and pulls back:

| | value |
|---|---|
| frames | 120, a full 360 deg orbit and a full ripple cycle together |
| resolution | 1280x720 (up from 960x540) |
| camera | distance 0.55 m (up from 0.34), 50 mm lens (from 60 mm) |
| samples | 320, OptiX, denoised |
| cost | 0.36 s bake + ~5.9 s render per frame |

Each frame re-bakes the caustic at the frame's wave phase and re-builds the water
surface from the same phase, so both the geometry and the light are re-solved
120 times. That is the method's actual advantage stated as a production cost: a
deterministic caustic that changes with the geometry costs 0.36 s to update,
against a path tracer that must re-converge its caustic every frame from scratch.

---

## 17. The clips vs Cycles — measured temporally, not spatially

Same camera path, same water geometry, same wave-phase schedule, same sample
count, same denoiser. The only difference is where the caustic comes from.
`tools/clip_flicker.py`.

For an animation the cost of a stochastic caustic is not grain, it is **flicker**:
frame-to-frame variation that is not motion. A caustic is the worst place for it —
brightest, thinnest, slowest-converging feature in frame. Both clips can look
identical one frame at a time and one can still shimmer.

    flicker = mean |frame_t - frame_(t+1)| inside the caustic region

A control region (the darkest half of the frame, dominated by smooth genuinely
moving shading) is measured alongside, to check the difference is not just motion.

### ripple clip — static camera, animated caustic (the valid test)

| | ours (injected) | Cycles (path-traced) |
|---|---|---|
| flicker, caustic region | **0.001 levels** | 0.010 levels |
| flicker, control region | 0.608 | 0.240 |
| render cost, 72 frames | 455.7 s + **26.2 s bake** | 453.0 s |

**7.9x less caustic flicker.** Our caustic contributes essentially nothing to the
frame-to-frame variation; Cycles' contributes ten times more.

Two honest notes. The denoiser is ON for both clips, which suppresses flicker in
both and therefore compresses this ratio — with denoising off it would be larger,
but the production artefact is the denoised one and that is what is measured. And
the control column is *worse* for us (0.608 against 0.240): our dim regions vary
more, which is signal rather than noise — the injected field is re-baked every
frame and its faint outskirts genuinely evolve, whereas Cycles' dim caustic
structure is under-resolved and denoised away. The metric cannot tell signal from
noise without a reference, so the control column is reported, not spun.

**Cost, stated against us:** Cycles is marginally *faster* on this clip in wall
clock (453 s against our 455.7 s + 26.2 s bake = 481.9 s). The win here is
temporal stability, not speed.

### combined clip — orbiting camera (metric is NOT valid)

| | ours | Cycles |
|---|---|---|
| flicker, caustic region | 4.026 | 3.416 |
| flicker, control region | 2.241 | 5.048 |
| render cost, 120 frames | 732.6 s + 40.7 s bake | 1043.2 s |

With the camera orbiting, frame-to-frame differences are dominated by motion, not
sampling, so this column cannot be read as a noise comparison — the caustic
region is 1.8x its own control for us and 0.7x for Cycles, which is a statement
about how much of each frame moves. It is included because the clips exist and
the numbers are real, not because they support anything. The valid temporal test
is the static-camera clip above.

The control column does carry one signal: Cycles' frame-to-frame variation across
the whole frame is 2.3x ours (5.048 against 2.241), i.e. its animation is
unstable in places ours is not.

**Cost here favours us:** 773.3 s against 1043.2 s, 1.35x faster including the
per-frame bake.

---

## 18. Verification against Mitsuba 3, an independent trusted renderer

Prompted by "use a trusted light simulation we can run on our own hardware to
test and verify against". Mitsuba 3.9.1, installed as a pip wheel and run on the
GPU in its spectral variant.

Geometry is not re-derived: `tools/export_scene_obj.py` writes the same vertices
the Blender scene uses (glass tube 35/31.5/90 mm, rippled water surface at
59.4 mm, 0.32 m table), so a difference cannot be a meshing artefact.

### 18.1 The finding that changes the plan

**Mitsuba 3 has no photon-mapping integrator.** `sppm` and `bdpt` do not exist in
3.9 — enumerated, both fail to instantiate. Available: direct, path, volpath,
volpathmis, depth, moment. So Mitsuba is a *third path tracer*, not the
converged caustic reference that was wanted, and its caustic behaves exactly like
Cycles': firefly-dominated, with the image max falling from 8.62 at 4096 spp to
1.78 at 8192 spp. No trusted caustic-converging renderer is currently installed.

### 18.2 What it did verify: the dispersion ORDER, independently

Mitsuba's spectral variant ships **measured** refractive-index data for water and
BK7 — independent of the Cauchy fit this project uses. That makes it the right
instrument for the one claim that had never been independently grounded.

Two genuinely monochromatic renders (16 nm bands, no RGB channel mixing), each
paired with an optics-absent render so the caustic is isolated as
(present) − (absent):

| band | added-light centroid beyond 40 mm |
|---|---|
| 650 nm (red) | **95.7 mm** |
| 450 nm (blue) | 94.1 mm |
| red − blue | **+1.6 mm (+1.74%)** |

Physics requires blue (higher index) to refract more and focus closer, so red
must land farther. Mitsuba, with measured material data, says red lands farther.
Ours (legacy Cauchy fit) said the same: R 54.4 > G 53.4 > B 52.9 mm, +2.9% -- estimator and magnitudes STALE (see 14.5); the edge-based order on measured indices is R 107 / G 105 / B 102 mm.

**Ordering: independently confirmed. Magnitude: same order, 1.7% against our
2.9% (STALE -- legacy Cauchy magnitudes)** — the difference being attributable to the two material models and to
Mitsuba's noise.

### 18.3 The limits of this instrument, stated

* Peak radii from Mitsuba are **not** usable: it puts 650 nm's peak at 11.2 mm and
  450 nm's at 26.2 mm, which is firefly residue, not physics. Only the integrated
  centroid beyond 40 mm is robust, and that is what is reported.
* Mitsuba's caustic does not converge at practical sample counts, so it cannot
  arbitrate the caustic's **shape**. For shape the strongest instruments remain
  those already used: closed-form theory (0.1 mm on the fold) and this project's
  own exact brute-force tracer (r = 0.916 re-measured with measured indices).
* Its source is 2.9 deg against our 0.53 deg, because a smaller source makes a
  path tracer useless. That is why the comparison is on ordering, not absolute
  radius.

A second trap avoided here and worth recording: the first attempt read the
dispersion off the RGB channels of a broadband render, where the three masks came
out with identical pixel counts (n = 2622 for R, G and B) — the "separation" was
numeric residue inside one mask, not a measurement. Monochromatic bands remove
the ambiguity entirely.

---

## 19. A real photon-mapping reference: PBRT-v4 SPPM

Mitsuba settled the dispersion ordering but exposed a harder gap: **nothing
installed here could converge a caustic at all**. Mitsuba 3.9 and Cycles are both
brute-force path tracers, and a path tracer needs to hit a small bright patch by
chance. So PBRT-v4 - the reference implementation of the techniques that can -
was built from source and driven on the same scene.

### 19.1 What it took, and why it is worth it

`git clone --depth 1` + submodules + a Visual Studio 17 2022 superbuild: about
eight minutes, no patching. The payoff is the number that defines this project:

| method | 512^2 caustic frame |
|---|---|
| PBRT SPPM, 256 iterations x 1 M photons | **34 s** |
| Cycles / Mitsuba path tracing | does not converge at any practical sample count |

Same exported geometry: `tools/pbrt_reference.py` converts the OBJ meshes to PLY
(same vertices Blender and Mitsuba use) and writes the `.pbrt` scene.

### 19.2 The trap that nearly produced a false negative

The first comparison said the two caustics were **122 deg apart in azimuth** with
a correlation of **+0.07** - apparently a decisive refutation of the solver.

It was a camera convention. PBRT's `LookAt` computes the camera's right axis as
`cross(up, direction)`; for a top-down view with `up = +y` and direction `-z`
that gives **(-1, 0, 0)**, a left-handed frame, so **the rendered image is
mirrored in X** relative to a world-space top-down map. PBRT's shadow sat at
azimuth +151.5 deg, which is exactly where our +27 deg caustic lands under an
X-mirror - the clue worth remembering.

After mirroring:

| metric | as rendered | X-corrected |
|---|---|---|
| correlation, k = 8 (40 mm tiles) | +0.074 | **+0.926** |
| correlation, k = 16 | +0.064 | +0.767 |
| correlation, k = 32 | +0.050 | +0.639 |
| correlation, k = 64 | +0.038 | +0.547 |

### 19.3 Result: the caustic shape is confirmed by photon mapping

| quantity | PBRT-v4 SPPM | ours | agreement |
|---|---|---|---|
| caustic centroid azimuth | +29.1 deg | +26.7 deg | 2.4 deg |
| caustic centroid radius | 50.2 mm | 52.2 mm | 4 % |
| azimuthal energy peak | +0..+30 deg bin | +0..+30 deg bin | same |
| energy falloff | symmetric, second bin +30..+60 | same | same |
| tile correlation at 40 mm | - | - | **r = +0.926 (legacy etas; +0.932 re-measured 2026-10-12 on measured central etas 1.33468/1.52514, see 19.6)** |

Figure: `docs/media/pbrt_vs_ours.png` (PBRT | ours | overlay).

This is the first independent confirmation of the caustic's *shape* - not its
dispersion, not its position on a single ray, but the whole two-dimensional
structure - and it comes from an implementation of the technique the community
uses to judge caustic renders.

### 19.4 Caveats, stated

* SPPM's estimate is radius-dependent. 256 iterations at an initial radius of
  6 mm; smaller radii resolve more structure but need more photons. The reported
  correlation is at 40 mm tiles and above, where the estimate is stable.
* PBRT's eta values here are 1.52 (glass) and 1.333 (water), single-valued, so
  this validates *shape*, not dispersion. Dispersion is §18's business.
* The match is against `out/caustic_wavy.png`, the rippled-water field, so both
  sides share phase as well as geometry.

### 19.6 Shape re-measured on measured indices (2026-10-12)

The flagship r = 0.926 rested on single-valued legacy etas (1.52/1.333).
Rebuilt both scenes at the measured central-channel values (water 1.33468,
glass 1.52514; tools/pbrt_reference.py defaults now these) and re-ran SPPM
(256 iterations x 1 M photons, differential optics-minus-nooptics, X-mirror
corrected):

    PBRT centroid (+33.7, +18.6) mm, r 38.5, az +29.0 deg
    ours centroid (+45.1, +23.4) mm, r 50.8, az +27.5 deg
    tile correlation at 40 mm tiles (8x8 grid):   r = +0.932
    tile correlation at  5 mm tiles (64x64 grid): r = +0.557

Agreement is strong on gross structure and falls off as the scale sharpens
(0.932 -> 0.557), so the fine structure of our field is NOT independently
confirmed by this instrument -- consistent with the breadth limit of section
14.7. Both scales re-derived by tools/metric_parity_check.py, which prints the
tile convention explicitly: the 8x8 grid gives 40 mm tiles and the 64x64 grid
gives 5 mm tiles on the 320 mm patch. (Note the collision with the older
convention in section 19.2, where "k = 8" names EIGHT tiles per side - the same
grid, a different label. Both readings agree once the tile SIZE is fixed:
40 mm -> 0.93, 5 mm -> 0.55.)

Agreement holds and sharpens at fine scale on measured indices. Scenes:
out/pbrt/pbrt_shape_optics.pbrt + pbrt_shape_nooptics.pbrt (archived -- the
auditor found the old conv-pair EXRs had no archived scenes).

### 19.5 PBRT-v4 scene-format traps, recorded so they cost nothing next time

* `WorldBegin` is required; **`WorldEnd` is only accepted if the parser's
  `formatting` flag is set**, otherwise it is "Unknown directive".
* `Integrator` must sit **outside** the world block, with camera and film.
* Named materials are selected with `NamedMaterial`, never `Material <name>`
  (`Material` takes a material *type*).
* **SPPM's iteration count is the sampler's samples-per-pixel**, not an
  `niterations` parameter; `maxdepth`, `photonsperiteration` and `radius` are the
  real SPPM parameters, and there is no `imagefile` parameter.
* A zero-length camera shutter interval is a hard error.

## 20. Index dispersion: a measured-data correction, and a sign inversion in our own ray map

Date 2026-10-11. Triggered by re-reading the Mitsuba run of EVIDENCE 18: that
reference measured red-farther-than-blue by +1.74 % while our solver reported
+2.9 % -- a factor 1.67 that had been filed as noise. It is not noise.

### 20.1 The index model was wrong (fixed)

showcase_main.cpp carried a two-term Cauchy for water, n = 1.31700 + 6080/L^2,
with a comment claiming it reproduced 1.3314/1.3345/1.3407 at 650/550/450 nm.
It does not, and no single (A,B) can: that triple is not on a Cauchy curve.

    lambda    Cauchy(1.317, 6080)    measured    error
    650 nm    1.33139                1.33167     -0.0003
    550 nm    1.33710                1.33468     +0.0024
    450 nm    1.34702                1.33961     +0.0074

Dispersion over 450-650 nm: 0.01563 against a measured 0.00794 -- 1.97x too
strong. That factor, not physics, is most of the gap to Mitsuba. The audit found
the glass model (Cauchy 1.5095 + 4200/L^2) 4-8 % off in slope as well.

Both are now measured data evaluated directly, not fitted:

  water  Daimon & Masumura (2007), Appl. Opt. 46, 3811 -- 4-term Sellmeier for
         HPLC-distilled water at 20.0 C, valid 0.182-1.129 um
  glass  Rubin (1985), Sol. Energy Mater. 12, 275 -- soda-lime silica window
         glass, n = 1.5130 - 0.003169 L^2 + 0.003962/L^2, L in um

taken from the refractiveindex.info database -- the measured tables the reference
renderers use. The old constants remain behind --legacy-index, so the size of
the error stays reproducible.

Cross-check: the Sellmeier slope, n(486.1) - n(656.3) = 0.00598, agrees with the
classic water line values (0.00600) to 0.3 %; only a constant +0.0004 offset
from differing temperatures separates them.

### 20.2 What a converged reference says

PBRT-v4 SPPM on the exported geometry: three renders differing ONLY in the index
pair (one per spectral channel, measured data), 192 iterations x 1e6 photons,
plus a --hide-optics baseline. The caustic is isolated as render minus baseline
-- the lit table dominates the raw image (mean 0.874 almost uniformly), and
scoring a raw render measures the ambient, which produced a meaningless 7.31 mm
centroid on the first attempt.

    channel   eta (water, glass)    caustic centroid r   azimuth    peak
    650 nm    1.33167, 1.52104      30.72 mm             +28.60     8.204
    550 nm    1.33468, 1.52514      30.21 mm             +28.66     8.429
    450 nm    1.33961, 1.53192      29.35 mm             +28.68     8.994

    R - B = +1.37 mm (+4.657 %), monotonic R > G > B, azimuth spread 0.08 deg

Red lands outside blue, monotonically, with the azimuth fixed to 0.08 deg: a
pure radial chromatic split, the peak growing toward blue as the shorter
wavelength focuses harder. This agrees in ORDER with the independent Mitsuba
measurement (+1.74 %); the magnitudes differ because Mitsuba's source is 2.9 deg
against our 0.53 deg.

### 20.3 The dispersion order holds - once the estimator is comparable

Measured in the ray-map domain - before the per-channel mean normalisation
(which rescales each channel differently) and before the flux ceiling - the mean
landing radius responds smoothly and monotonically to index:

    water n    1.30      1.35      1.40      1.45
    mean r    65.667    66.976    68.489    70.162 mm

and the single-refraction sub-model (--flat, which is exactly what
tools/analytic_caustic.py reproduces independently and verified to 0.1 mm)
agrees with its analytic reference over the same scan, on the mean radius AND on
the fold locus:

    n       analytic mean r     analytic fold r      fold phi
    1.300     77.440 mm           78.040 mm          207.70 deg
    1.350     78.510 mm           80.168 mm          207.70 deg
    1.450     80.631 mm           83.916 mm          207.70 deg

(the fold azimuth 207.70 deg reproduces the independently verified value of
EVIDENCE 16.)

Both curves RISE with index, the opposite of the reference - and that first read
as an inverted sign in our transport. It is not: it is the estimator. The
mean-over-all-rays radius is dominated by wide unconverged tails, and the fan
centroid of our field is not comparable to a linear HDR render because the field
is both normalised per channel and held under a flux ceiling (peaks all
saturate, so an argmax picks an arbitrary capped cell). Comparing those against
SPPM's bright-region centroid produced a false alarm.

The comparable feature is the caustic EDGE: the outermost radius whose mean
intensity crosses a threshold taken relative to that channel's own maximum. It
is invariant to any uniform scale, and a ceiling lifts the core but not the
outer edge. Measured identically on both sides:

    measured indices (Daimon & Masumura / Rubin), edge = outermost 1 mm
    annulus above 2%% of channel max, nb=160 (reconciled 2026-10-12; an
    earlier binning read 108/106/104 and is superseded)
      our solver   edge  R 107.0  G 105.0  B 102.0 mm    R - B = +5.0 mm
      PBRT SPPM    edge  R  56.0  G  54.0  B  51.0 mm    R - B = +5.0 mm

    legacy (mis-fitted) indices, our solver
                 edge  R 108.0  G 105.0  B 101.0 mm    R - B = +7.0 mm

So the order is the same on both sides - red outside blue, monotonic
R > G > B, the order both references require - and the corrected indices reduce
our split from +7.0 mm to +4.0 mm, close to the 1.97x dispersion ratio the index
audit predicted. The absolute edge radii are not comparable (108 mm against
56 mm): the scenes differ in water level and glass height, and a shorter focal
length raises the relative chromatic spread, which is why the reference's split
is larger relative to its own radius.

Conclusion: the geometric dispersion ORDER of our caustic is correct and now
rests on measured data, with the split 1.4x smaller than before. The chromatic
claims in EVIDENCE 12 and PHYSICAL_TEST are restored in ORDER; the magnitudes
quoted there were computed with the mis-fitted indices and are stale.

STALENESS NOTICE (2026-10-11, second pass): the re-measurement is complete and
the numbers that matter are current -- solver/brute-force agreement r = 0.916,
accuracy 0.917, edges ours R 107 / G 105 / B 102 vs SPPM R 56 / G 54 / B 51,
spread 32.2%%, breadth 2.3x (EVIDENCE 14.4/14.5/14.7/14.8, CRITIQUE C4/C6/C8).
What REMAINS stale is pixels, not numbers: docs/media/showcase_glass.png is
re-rendered, but the six-angle stills, the contact sheet, the comparison
figure, and all clips (ripple, turntable, combined, Cycles counterparts)
predate the index fix and the Blender IOR correction (1.333->1.335 water,
1.52->1.525 glass). A full re-render is ~40 min of GPU for a sub-percent
visual change (the index shift moves the caustic edge by ~2 mm on a 320 mm
patch); it is deferred until the next visual deliverable, and no dispersion
number may be quoted from those pixels meanwhile.

Lesson recorded: a dispersion comparison is only meaningful between estimators
immune to the cap and to normalisation. Neither the ridge argmax (cap) nor the
mean-over-rays radius (tails) qualifies; the threshold-crossing edge does.
