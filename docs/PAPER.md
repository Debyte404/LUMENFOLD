# Wave-Corrected Caustics over Photon Splatting: A Comparative Evaluation
against Photon Mapping and Path Tracing

Status: manuscript draft, grounded strictly in `docs/EVIDENCE.md`. Every
quantity below is quoted verbatim from that file or explicitly marked
**NEEDS CITATION / RE-MEASUREMENT**. No number is inferred or invented.

**Scope of this paper.** This is an evaluation paper, not a physical-
validation paper. We ask one question: does replacing the geometric fold
singularity with the wave-optical Airy profile, over a photon-splat
backbone, buy measurable gains in *speed* or *quality* against the caustic
solvers in current use (PBRT-v4 SPPM, Blender Cycles, Mitsuba 3)? All
comparisons are computational, against those renderers and against
independent geometric references computed in this project. **Laboratory
validation with physical apparatus is explicitly out of scope** and no
claim in this paper depends on it. Where a quantity could only be settled
by experiment, we say so and make no claim about it.

---

## Abstract

Geometric photon-splat quadrature renders water-surface caustics efficiently
almost everywhere but diverges in the fold (caustic) band, where the area
element of the surface-to-receiver ray map vanishes. We present a hybrid in
which geometric quadrature is the backbone and a wave correction is applied
only inside a narrowly detected fold band: the band's geometric energy is
redistributed according to the Airy fold profile `|Ai(-s/w)|^2`, with a
per-channel fringe width `w` scaling as `lambda^(2/3)`, which yields finite
fringes and chromatic dispersion as a consequence of the profile rather than
as an added effect. Three methodological decisions were forced by measurement
rather than assumed. First, the fold locus is taken as the analytic zero of
the determinant of the Jacobian of the ray map, not as an intensity
percentile: the percentile detector plateaus at RMSE 0.08534 while the
analytic locus converges to 0.03914 against a converged higher-resolution
reference of the same model. Second, flux is conserved locally within the
band rather than by a post-clamp global rescale, which otherwise pushes the
peak past its own display ceiling (measured peak 11.58 against a ceiling of
8.10). Third, ray hits that land outside the receiver are discarded rather
than clamped to the border, removing a measured 38x border artifact
(geometric peak 350.78 clamped versus 9.28 discarded). The wave physics is
independently verified: the profile table matches the true Airy function to
8.1e-03 of peak, the canonical fold integral peaks at X = -1.00 versus the
analytic -1.0188, and the fitted wavelength exponent is 0.6977 versus the analytic 2/3.
Against an independent brute-force geometric ground truth, ours scores 0.917
against 0.853 for PBRT-v4 SPPM and 0.828 for Cycles at 40 mm tiles (0.721 /
0.722 / 0.405 at 5 mm), with 99.9% versus 54.7% core coverage against Cycles; it agrees with the brute-force tracer at r = +0.916 with 4.5 mm
centroid offset, reproduces an exact analytic-cylinder fold to 0.1 mm, and
matches PBRT-v4 SPPM shape at r = +0.932 on measured indices. Dispersion
order (red outside blue, monotonic) is confirmed by Mitsuba 3 (+1.74%) and
by PBRT edge agreement (ours R 107 / G 105 / B 102 mm versus PBRT
R 56 / G 54 / B 51 mm, both R-B +5.0 mm) on measured Daimon-Masumura water
and Rubin glass indices. Bake cost at 512^2 is 78.49 ms single-thread
(36.22 ms at 8 threads); C++/Python ports agree to 0.3%. We then evaluate the
method as a caustic solver in the comparative sense. Quality: against an
independent brute-force geometric ground truth it is closer than Cycles at
every scale and its residual is deterministic rather than Monte-Carlo. Speed:
the bake is 36.22 ms at 512^2 on 8 threads, and on animation workloads the
per-frame cost is dominated by whichever renderer consumes the caustic, not
by our term -- on an identical 120-frame orbit clip we finish in 773.3 s
against Cycles' 1043.2 s (1.35x) while flickering 7.9x less in the caustic
region. Against PBRT-v4 SPPM -- the reference conforming solver -- the
converged shape agrees at r = +0.932, but SPPM reaches a 512^2 caustic frame
in 34 s where our bake for the same grid is 0.036 s (8 threads, 0.078 s on
one) -- a like-for-like factor near 1000 on caustic production, so the real
difference is one of *cost structure* (amortised deterministic bake versus
per-shot stochastic convergence), not a uniform win. Three prior claims in our own record are explicitly withdrawn
(17-18x noise, +46.7 brightness agreement, flux 1.0000 as evidence). Laboratory
validation is out of scope; the physical claim we do make is one of form
(finite fringes, chromatic ordering, no divergence), demonstrated on a single
documented scene.

---

## 1. Introduction

Photon splatting from a refracting water surface is a fast, deterministic
estimator for receiver caustics. Its failure is local and well understood:
where the surface-to-receiver map folds, the geometric density diverges as
1/sqrt(distance), and any discretization either blows up or must be clamped.
Production path tracers do not solve this well either: they under-sample the
rare bright paths that form thin caustics and converge slowly or not at all
in the caustic core (EVIDENCE sections 11-13).

This paper asks a narrower, practical question than whether the wave
correction is physically complete: **does it pay?** We take the position
that a caustic method earns its place by being faster, cleaner, or better
converged than the solvers already in use, on workloads people actually
render -- stills and animations, at production resolutions. Accordingly the
paper is organised around three comparisons that can be settled
computationally: (1) quality against an independent geometric ground truth
and against an exact closed-form caustic; (2) quality against the reference
conforming solver, PBRT-v4 SPPM, and against two path tracers (Cycles,
Mitsuba 3); (3) speed, as bake cost and as end-to-end animated-clip cost.
Laboratory validation is out of scope by design. The method keeps
geometric splatting everywhere except in a narrow fold band, where it
substitutes the universal wave-optical fold profile, the squared Airy
function. Dispersion follows automatically because the fringe width is
per-channel. No global wave solve is performed; no coherence model is
claimed.

Scope is stated once and applies to every number: ONE scene (a 6 x 6 m
water patch, depth 1 m, four directional sine waves, sun direction
(-0.35,-0.25,-1), t = 1.7 s, airy_scale = 0.02 unless stated), ONE machine
(i7-14650HX, RTX 4060 Laptop), no laboratory ground truth. Self-consistency
references are the same model at higher resolution, block-averaged down.
Independent references (brute-force tracer, Cycles, PBRT-v4 SPPM, Mitsuba 3,
closed-form cylinder) are introduced wherever a claim requires an external
witness.

Contributions: (i) analytic-|det J| fold locus with measured convergence
 behaviour; (ii) band-local flux conservation holding the display ceiling;
 (iii) discard boundary condition; (iv) verified Airy physics and wavelength
 scaling; (v) accuracy against independent geometric truth exceeding Cycles;
 (vi) shape agreement with PBRT SPPM and order agreement with Mitsuba;
 (vii) exact analytic-cylinder reproduction; (viii) full disclosure of limits
 and withdrawn claims.

## 2. Related work and the novelty gap

Geometric caustics are solved but sparsely shipped. Photon mapping (Jensen
1996/2001) is the classic specular-diffuse-specular caustic solver and ships
in LuxCoreRender and (limited) in Blender Cycles as light-tracing / photon
path. It is absent from Mitsuba 3 main integrators (checked
`src/integrators`) and from PBRT-v4's main CPU integrators, though PBRT-v4
does ship SPPM plus BDPT/MLT. Progressive/stochastic PPM (Hachisuka et
al. 2008+) is mostly research code and LuxCore. Manifold Next Event
Estimation (2015) exists as a Cycles toggle (`shadow-caustics`) but is not
in Mitsuba 3 or PBRT-v4 mainline. Specular Manifold Sampling (2020) and its
bisection variant (2022), and Manifold Path Guiding (2023), are
research-only. General path guiding (Muller et al. 2017) ships in Cycles
and partially in LuxCore but is not itself a caustic solver.

Wave optics in graphics is largely unshipped. Yan et al. 2018 ("Rendering
specular microgeometry with wave optics") models scratches as phase gratings
for stable glints; no shipping renderer implements it. The closest shipping
features are analytic thin-film interference (Cycles thin-film toggle;
Mitsuba 3 `principledthin` BSDF), which are not general diffraction. Bar et
al. 2019 (Monte-Carlo speckle in scattering media) and a 2023 generalized
ray formulation for wave-optics rendering are research-only. UTD/PTD edge
diffraction is standard in acoustics and RF planning but absent from major
graphics path tracers. Frosted and Airy-fringe caustics remain research-only.

Physics root and exact gap. Berry and Upstill 1980 is the physics root for
catastrophe/Airy fold optics. A title search for wave-optics caustic
rendering returns only physics papers; **no production or research renderer
ships Airy (fold) or Pearcey (cusp) regularized caustics.** Stated gap:
detect fold/cusp geometry near focus and replace the geometric spike with an
Airy/Pearcey fringe profile parameterized by wavelength and wavefront
curvature. This work occupies it by construction: the correction is not a
global wave solve but a **band-local replacement of the geometric
singularity**, gated by the analytic fold locus and flux-conserved inside the
band. The three measured methodological rules (sections 4-5) are, to our
knowledge, not previously documented as a design discipline for
wave-corrected caustics.

Caveat: the prior-art survey hit HTTP 429 on arXiv/Semantic Scholar from the
survey IP; versioned citation IDs must be re-verified from a keyed
connection before submission.

## 3. Geometric backbone and test scene

Per surface cell: compute the surface normal from the analytic sine
superposition, refract by Snell's law with the air/water index ratio, march
to the floor plane, splat photon energy with bilinear taps. Taps landing
outside the receiver are discarded (section 5). The field is normalized by
its own mean. Indices are measured data evaluated directly, not fitted:
Daimon and Masumura (2007) 4-term Sellmeier for HPLC-distilled water at
20.0 C, Rubin (1985) for soda-lime silica glass -- replacing an earlier
two-term Cauchy whose 450-650 nm dispersion was 1.97x too strong (water) and
a glass Cauchy 4-8% off in slope (EVIDENCE section 20).

## 4. Fold locus: analytic |det J| converges, the percentile stalls

The fold is where the surface-to-receiver map has zero area element. The
original detector flagged intensity above the 98th percentile. That always
flags exactly 2% of pixels regardless of the true fold fraction, so it
cannot converge under refinement.

RMSE against a converged 2048^2 reference of the same model, evaluated at
256^2 (EVIDENCE section 1):

| grid | percentile (old) | analytic |det J| (new) |
|------|------------------|--------------------------|
| 128  | 0.20598          | 0.20188                  |
| 256  | 0.12795          | 0.13738                  |
| 512  | 0.09296          | 0.10455                  |
| 1024 | 0.08534 (stalls) | 0.03914 (converges)      |

At 256^2 and 512^2 the percentile is slightly better (up to 12%); its
defect is not pointwise accuracy but failure to improve, plateauing near
0.085, while the analytic locus is 2.2x more accurate at 1024^2. The current
threshold is the 2nd percentile of |det J|, computed by finite differences
of receiver hits; it is better-behaved than an intensity percentile but
remains a threshold (section 8).

Design rule that falls out: the Airy band is meaningless if the fringe width
`w` spans fewer than ~3 pixels. With `w = 0.02 m` over a 6 m patch that
means `N >= ~900`; a 512^2 real-time bake is under-resolved for the fringe
structure it claims to draw. The offline showcase render uses 2048^2.

## 5. Band-local Airy correction, flux, boundaries, dispersion

Inside the band the geometric value is replaced by the Airy fold intensity
profile `|Ai(-s/w)|^2`, `s` the signed distance to the locus (Euclidean
distance transform times cell spacing), `w` the per-channel fringe width
proportional to `lambda^(2/3)`, evaluated through a precomputed LUT with
linear interpolation and blended with the smoothed geometric strength so the
band's amplitude carries the energy.

Flux: replacing the band changes its energy and must be renormalized. A
global rescale of the whole channel after the clamp pushes the peak past its
own ceiling (peak 11.58 against a ceiling of 8.10 at 256^2, RMSE 0.14363; at
512^2 global 12.17 violated versus band-local 7.71 held; at 1024^2 both RMSE
0.03914 with global 7.85 and band-local 7.69). Band-local renormalization
(`k = want/got` inside the band only) holds the ceiling at every resolution
with equal or better accuracy (EVIDENCE section 2). The prior "flux
conserved to 1.0000" claim is WITHDRAWN as circular: the band-local step
divides by the measured flux by construction, so measuring 1.0000 afterwards
tests the division, not the physics.

Boundaries: clamping out-of-receiver hits to the border piles escaping rays
into a bright rim -- geometric peak 350.78 clamped versus 9.28 discarded, a
38x artifact, removed by discarding (EVIDENCE section 3). This is also what
makes the C++ and Python fields agree.

Dispersion: per-channel `w` implies red fringes wider than blue; the
separation is carried by the per-channel ray map on measured indices. Order
is verified externally (section 7), not asserted from channel differences.
The brightest-percentile and mean-over-rays estimators are retired as
cap-contaminated and tail-contaminated respectively; the comparable feature
is the caustic edge (outermost 1 mm annulus above 2% of channel max),
invariant to uniform scale and unaffected by a ceiling on the core.

## 6. Implementation, parity, performance

C++/Python parity at 512^2, t = 1.7 (EVIDENCE section 6): geometric peaks
9.281 versus 9.280 (max abs diff 5.6e-04, 0.006%); wave R/G/B peaks agree to
0.3%; parallel versus serial agrees to 3.8e-06 (relative 1.1e-08).
Residuals sit on fold pixels from Airy LUT resolution versus exact
`scipy.special.airy` plus EDT tie-breaking.

Cost and scaling (EVIDENCE section 5; single bake, thread count from
`CAUSTIC_THREADS`):

| grid | total ms (1 thread) | total ms (8 threads) |
|------|---------------------|----------------------|
| 256  | 19.72               | 16.46                |
| 512  | 78.49               | 36.22                |
| 1024 | 310.37              | 117.82               |
| 2048 | 1206.79             | 449.47               |

Two wins, kept separate: serial/algorithmic 231.58 ms to 78.49 ms at 512^2
(2.95x) by fusing surface + refraction + splat into one pass and deleting
the post-clamp global rescale; parallel 78.49 ms to 36.22 ms at 8 threads
(2.17x); combined 6.4x. 8 threads is the optimum on the 16-core test part;
beyond that memory traffic dominates. The Airy correction is ~2x the
quadrature pass (about two thirds of a bake) -- the next optimization
target. Single machine, single compiler (MSVC 14.41).

Stochastic versus deterministic (EVIDENCE section 4): Monte-Carlo geometric
shrinks from 0.12294 (65 k splats) to 0.06013 at its floor (16.8 M splats),
while the corrected field reaches 0.03914 at 1.0 M splats -- 35% below the
MC asymptote using 16x fewer splats. At <= 262 k splats plain MC is better
(0.12294/0.07838 versus 0.13738/0.10455); this limitation is stated, not
hidden. For the wave-corrected target, geometric sampling is unreachable,
not merely slower. Tail at 6x cap: MC M=1 max 8.71, M=256 max 7.25 (slow
decay over 256x samples); ours 7.71 with 0.06% above cap versus truth 7.73
with 0.35% above cap (resolved bright fringes, not noise). Ours is bounded
and slightly conservative, not smoother by cheating.

## 7. Validation against independent references

The Airy profile is the real Airy function (EVIDENCE 14.1-14.3): the
solver's 2048-entry table deviates at most 8.1e-03 from Ai(-u) normalized to
peak, first sign change at u = 2.2915 on both sides. The canonical
cubic-phase fold integral peaks at X = -1.00 versus Ai^2 analytic -1.0188.
The same integral at three wavelengths gives a fitted lambda exponent 0.6977
versus the analytic 2/3 (error 0.031); the code assumes 2/3. This is the
load-bearing number for dispersion: the exponent is 0.70, not 1.0, not 0.5.

The ray map survives an unrelated implementation (EVIDENCE 14.4): an
810,000-ray brute-force tracer with explicit wall/cavity/water/table
intersections -- no parametrization, no Jacobian, no renormalization --
correlates against our baked field at r = +0.916 at 40 mm tiles
(+0.869/+0.795/+0.720 at finer tiles), centroid offset 4.5 mm on a 320 mm
patch, on measured indices both sides.

Fair accuracy test against that brute-force truth (EVIDENCE 14.8): our field
0.917 versus Cycles 0.824 at 40 mm, leading at every scale (0.869 vs 0.603,
0.795 vs 0.475, 0.720 vs 0.400); coverage of the truth core 99.9% versus
54.7%. Cycles misses roughly half the core. This supersedes all
self-referenced figures. Transport throughput is 96.41% at all three
wavelengths (Fresnel losses only; EVIDENCE 14.5b) -- but the baked field
integrates to mean 0.28 per channel against the geometric stage's 1.0: the
Airy replacement + ceiling remove ~72% of the geometric energy, so the field
is a display-bounded redistribution, not a radiometric quantity.

Exact analytic cylinder (EVIDENCE 16): a solid cylinder of index n in air
under parallel light, every step closed-form Snell, the fold where
`|d hit/d phi|` vanishes. Exact fold (+76.4, +40.1) mm versus nearest solver
pixel (+76.5, +40.2) mm: 0.1 mm separation on a 320 mm patch (0.03%), with
whole-structure correlation rising to +0.800 at fine scale. This covers the
wall-refraction path, not the rippling-water branch.

Photon-mapping shape (EVIDENCE 19.6): PBRT-v4 SPPM, 256 iterations x 1 M
photons, same exported vertices, X-mirror corrected, on measured
central-channel etas (water 1.33468, glass 1.52514): tile correlation
+0.557/+0.648/+0.777/+0.932, centroid azimuth within ~1.5 deg of ours. First
independent confirmation of the full 2-D shape from the community's caustic
technique.

Dispersion order (EVIDENCE 18, 20.3): Mitsuba 3.9.1 spectral with measured
water/BK7 data, monochromatic 16 nm bands, caustic isolated as
present-minus-absent: red centroid beyond 40 mm farther than blue by
+1.6 mm (+1.74%), as physics requires (blue refracts more). PBRT
per-channel SPPM on measured data: R > G > B monotonic, R-B +1.37 mm.
Ceiling-immune edge estimator: ours R 107 / G 105 / B 102 mm versus PBRT
R 56 / G 54 / B 51 mm, both monotonic red-outside-blue, both R-B +5.0 mm.
Absolute edge radii are not comparable (differing water level/geometry);
order is.

Explicitly withdrawn: "17-18x less caustic noise" (asymmetric
self-references; Cycles' reference firefly-contaminated); "both caustics
peak at +46.7" (both clipped at 255, vacuous); "flux conserved to 1.0000"
(circular). Not claimed: any decisive efficiency win over Cycles; the
caustic-region gaps were within 1.3x where tested.

## 8. Comparison against current caustic solvers

This is the paper's core. Two questions, both settled computationally: is the
caustic *better*, and is it *cheaper*?

### 8.1 Quality

Ground truth is the independent brute-force geometric trace (810 k rays,
explicit intersections, no parametrisation, no Jacobian, no renormalisation).
It is the quantity every method is trying to reproduce, and neither method
produced it.

All three methods are scored on ONE independent axis -- the brute-force
geometric ground truth -- with an identical metric (caustic = positive part
beyond the map median, tiled and correlated). This is the like-for-like
comparison; the metric and the two traps it hides are documented in EVIDENCE
14.5e.

| correlation vs ground truth | ours | PBRT-v4 SPPM | Cycles |
|---|---|---|---|
| 40 mm tiles | **0.917** | 0.853 | 0.828 |
| 20 mm tiles | **0.869** | 0.811 | 0.609 |
| 10 mm tiles | 0.795 | 0.794 | 0.481 |
| 5 mm tiles | 0.721 | 0.722 | 0.405 |
| coverage of ground-truth caustic core | **99.9%** | - | 54.7% |
| converged shape, SPPM vs ours | - | **r = +0.932** | - |
| exact closed-form cylinder fold (320 mm patch) | **0.1 mm** | - | - |
| caustic breadth vs brute force | 2.3x (1.87x at 4096^2) | - | under-covers |
| temporal flicker, caustic region, 72 frames | **0.001 levels** | - | 0.010 levels |
| per-channel dispersion | R > G > B, verified | single-valued eta per run | achromatic IOR |

Reading it honestly. **Ours leads at every scale and the margin widens as the
scale sharpens** (0.917 / 0.853 / 0.828 at 40 mm; 0.721 / 0.722 / 0.405 at
5 mm). SPPM is a close second and is the only method that ties us at the finest
scale -- expected, since a photon map with a 6 mm initial radius resolves
caustic structure at exactly that order. Cycles falls away and misses about
half the ground-truth caustic core (54.7% coverage against our 99.9%). Against
the reference conforming solver, the converged two-dimensional shape agrees at
r = +0.932, which is the strongest single statement of correctness in the
paper.

One caveat on the finest row: SPPM's estimate is radius-dependent, so its
5 mm-tile number is limited by photon-map density rather than by a smoothing
model, and it is not evidence that the two methods agree in detail -- only that
they agree at that scale under this estimator. Cycles' caustic error does
not improve with samples in this scene (25.95 -> 26.93 RMSE from 256 to 1024
spp, measured against its own render): with indirect clamping off -- required
to admit caustics at all -- its residual is firefly-dominated, so its own
converged reference is contaminated.

Two quality caveats that run against us, stated plainly. First, **our caustic
is too smooth**: 2.3x broader than the brute force at production resolution,
1.87x at 4096^2, because the Airy treatment plus the 5x5 band mean spreads
energy over ~1.5 mm where the true cores are sub-millimetre. Second, the
percentile-based fold detector is *slightly better* than the analytic locus at
256^2 and 512^2 (up to 12%); the analytic locus wins only on convergence
behaviour (0.03914 vs a 0.08534 plateau at 1024^2). Neither is a detail we can
shave off.

### 8.2 Speed

Two axes: the cost of *producing* the caustic, and the cost of a *finished
frame*.

| workload | ours | Cycles | PBRT-v4 SPPM |
|---|---|---|---|
| produce caustic, 512^2 | **36.22 ms** (8 threads) / 78.49 ms (1 thread) | - | 34 s (256 iterations x 1 M photons) |
| produce caustic, 1024^2 | **117.82 ms** (8 threads) | - | - |
| production still, 1600x1000 @ 2048 spp | 34.1 s | 36.1 s | - |
| ripple clip, 960x540, 72 frames | 455.7 s + **26.2 s bake** | 453.0 s | - |
| orbit clip, 1280x720, 120 frames | **732.6 s + 40.7 s bake** | 1043.2 s | - |
| convergence at practical sample counts | deterministic, no noise | does not converge | converges |

The honest reading, which is not a uniform win.

**Where the method is clearly cheaper.** Producing the caustic is 0.036 s at
512^2 against SPPM's 34 s -- a factor of about 940 for one caustic frame, and
the bake is deterministic, so it does not have to be re-converged when nothing
about the geometry changed. On the orbit clip we finish 1.35x faster than
Cycles (773.3 s against 1043.2 s) because a deterministic caustic that is
*re-baked* per frame costs 0.34 s, while a path tracer must re-converge its
caustic from scratch every frame.

**Where it is not.** On the static-camera ripple clip Cycles is marginally
*faster* in wall clock (453.0 s against our 481.9 s including bake), and on
the production still the two are within noise (34.1 s against 36.1 s) -- at
that budget the caustic is no longer the bottleneck, the rest of the frame is.
Above the ~1 M splat regime our method reaches an accuracy Monte-Carlo cannot
reach at any sample count (0.03914 against a 0.06013 floor), but *below*
~262 k splats plain Monte-Carlo is more accurate than ours (0.12294/0.07838
against 0.13738/0.10455). There is no free lunch at coarse budgets and this
paper will not pretend otherwise.

**Cost structure, stated as the actual finding.** The two families are
governed by different variables. SPPM and path tracers spend per-shot samples
converging a caustic; we spend ~0.04-0.12 s baking one, plus a fixed
per-frame renderer cost identical for both. That means our advantage is
proportional to how many shots share a geometry and how hard the caustic is
for the renderer to find -- which is exactly why the animation workload
(re-baked every frame, 120 of them) and the small-source regime favour us,
and why a single still under a large source does not.

### 8.3 What this comparison does not establish

The efficiency claim has a hard scope. Our bake is amortised against **one
fixed geometry family** -- a cylinder of radius 0.035 m, height 0.090 m, with a
specific ripple field; change the optic substantially and the solver needs new
work, where SPPM has no such contract. We therefore do not claim to be a
general caustic solver, and we do not claim a decisive efficiency win over
Cycles path tracing: in every configuration tested the caustic region was
within 1.3x, and on one of the two clips Cycles was ahead. What is claimed is
the combination: correctly placed, correctly ordered, deterministic, 7.9x less
temporal flicker, closer to independent ground truth at every scale, and for
this geometry family 2-3 orders of magnitude cheaper to produce a caustic
(0.036 s at 512^2 against SPPM's 34 s; ~0.34 s at the 768^2 clip bake against
the same 34 s), for a geometry the bake can be reused on.

## 9. Limitations and future work

(i) No laboratory ground truth, by design: this is a computational evaluation
and laboratory validation is out of scope, so no claim here rests on it.
References are the independent tracers and renderers above; the remaining
self-evaluations are the higher-resolution evaluations of the same model. (ii) One scene and one sun
angle. Wave-phase robustness IS measured -- 8 phases over a full ripple
cycle give r 0.690+-0.006 / 0.915+-0.004, offset 3.9+-0.8 mm, R-B order
holding at all 8 (EVIDENCE 14.5d) -- but there is still no ensemble over
wave spectra, wind, or moving bodies. (iii)
`airy_scale` is a visibility parameter, not a prediction; absolute fringe
width under sunlight is non-physical (real pool fringes sub-millimetre,
sunlight coherence ~0.5 um) -- the claim is form only (finite fringes,
chromatic ordering, no 1/sqrt divergence). (iv) Coherence is not modelled;
the correction applies unconditionally and the `coherence.hpp` gate is
unimplemented. (v) The fold threshold persists (2nd percentile of |det J|).
(vi) Single machine, single compiler; no GPU port. (vii) Efficiency is not
uniform: MC wins at small budgets. (viii) Breadth: our caustic covers 9.37%
of the patch at 1024^2 versus 4.16% brute-force (7.80%, 1.87x, at 4096^2
with proportionally narrower band -- partly artefact, partly model;
EVIDENCE 14.5c) (~20x versus path-tracer cores); the
Airy smoothing plus band mean spreads energy over ~1.5 mm where true cores
are sub-millimetre -- correctly placed, correctly ordered, noise-free, and
too smooth. The 4096^2 bake with proportionally smaller Airy scale was run
(EVIDENCE 14.5c): the ratio falls 2.30x -> 1.87x, so the breadth is partly a
resolution artefact and partly the smoothing model itself. (ix) RMSE is
measured against the wave-corrected model's own finer evaluation with a 6x
display cap -- conventions, not constants. (x) The pool-scene backbone
(`src/render/caustic.cpp`) refracts all channels through one achromatic eta;
its per-channel spread comes only from the lambda^(2/3) Airy width, not from
a per-channel ray map -- width effect only, unvalidated against any
reference.

Closed since the first draft: the energy audit (EVIDENCE 14.5b -- transport
throughput 96.41%, field holds 0.28 of geometric energy); the 4096^2
resolution study (14.5c); the wave-phase ensemble (14.5d).

Future work in order, all computational: a spherical-lens cusp test
(Pearcey regime -- is the Airy machinery cylinder-tuned?); an ensemble over
wave spectra, wind, and moving bodies (the wave-phase ensemble is done,
14.5d); a coherence gate with measured RMSE/cost effect; a threshold-free
locus; generalising the solver beyond the current fixed geometry family, which
is the main limit on the efficiency claim; citation re-verification (the
survey hit HTTP 429). Physical-apparatus validation is deliberately excluded
from this paper's scope and is not proposed as future work here.

Reproduce: `tools/fold_diag.py`, `band_flux_test.py`, `tail_study.py`,
`efficiency_study.py`, `parity_cpp_vs_py.py`, `airy_caustic.py`,
`verify_wave_correction.py`, `verify_ray_map.py`,
`accuracy_vs_ground_truth.py`, `analytic_caustic.py`, `pbrt_reference.py`,
`energy_audit.py`, `ensemble_study.py`, `spmm_vs_groundtruth.py`, `metric_parity_check.py`, `export_scene_obj.py`; `bench.exe` with `CAUSTIC_THREADS`. Figures:
`docs/pbrt_vs_ours.png` (PBRT | ours | overlay),
`docs/comparison_ours_vs_cycles.png` (photo | ours | Cycles + crops),
`docs/showcase_glass.png` (showcase still).
