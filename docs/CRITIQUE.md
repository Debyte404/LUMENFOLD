# CRITIQUE — an adversarial audit of this project's claims

Written as an attack on our own work, because a claim that has not been attacked
is a claim that has not been tested. Every verdict below is tied to a measurement
in `docs/EVIDENCE.md` or to a verification in `tools/`.

## Verdict in one paragraph

The **geometric core is sound and now independently verified** by two unrelated
methods (a brute-force tracer and a path tracer), and the **wave correction is
real physics** — its profile matches the true Airy function, its fold peak lands
where Ai² says, its λ^(2/3) fringe scaling is confirmed numerically, and its
chromatic ordering is correct. But three claims in our own write-ups do not
survive contact: the headline "17-18x less noise" is measured against each
method's *own* noisy reference and is therefore inflated; "both caustics peak at
the same level" is vacuous because both are clipped; and "flux conserved to
1.0000" is a property of our construction, not evidence about the world. The
field also **over-smooths by 2x against a brute-force trace and ~20x against
Cycles**, so our detail is partly blur. Net: a verified method, wrapped in two
inflated claims and one vacuous one, with an honest but unflattering limit on
detail.

## Claim by claim

### C1. "17-18x less caustic noise than Cycles" — INFLATED. Downgrade.

(Note: the *accuracy* half of this story is now independently supported — see C6.
It is specifically the noise ratio that remains unproven.)

Each method is scored against **its own** 4096-sample render. Cycles' reference is
not clean: with indirect clamping disabled — which is *required* to let caustics
through at all — its residual is firefly-dominated, so part of the "error" we
charge Cycles is its own reference's noise. Ours has no such floor: a
deterministic caustic plus a converged base.

That asymmetry flatters us by an unmeasured amount. A fair test needs a **common
ground truth** (an analytic caustic, or a converged render produced by a third
method), not two self-references. Until that exists the defensible statement is
"our caustic contributes no variance at any sample count, while Cycles' caustic
error does not fall between 256 and 1024 spp" — which is what the data actually
shows — not "17x better".

### C2. "Both converged renders agree on the caustic peak (+46.7 over median)" — VACUOUS.

Both images are clipped at 255 in that region (p75 = 255 for ours, p99 = 208.7
for Cycles' background). "Both peak at 255" says both exceed the display range
after AgX. It carries no information about matching brightness. To compare
brightness we would need linear, unclipped values or a deliberately
under-exposed pair. §12's earlier claim that the config fix "settled" brightness
agreement is withdrawn.

### C3. "The caustic centroid agrees within 5 mm" — HOLDS.

Robust, threshold-relative, reproduced by three independent renders (Cycles
native, Cycles via the caustics-on/off differential, and the brute-force tracer:
brute (+51.9, +27.3) mm, ours (+47.3, +24.7) mm, offset **5.2 mm** on a 320 mm
patch). This is one of the few claims that survives everything we threw at it.

### C4. "The field is validated at r = 0.906" — HOLDS, and stronger than before.

Originally this rested on one comparison (Cycles, caustics-on minus caustics-off,
r = +0.906 at 40 mm tiles). It now has a second, methodologically unrelated
witness: `tools/verify_ray_map.py` launches 810 000 rays, intersects them
explicitly with the wall, the cavity wall, the rippling surface and the table,
and simply counts where they land — no parametrisation, no Jacobian, no flux
renormalisation. Correlation with our field:

| tiles | tile size | brute force | Cycles (from §11) |
|---|---|---|---|
| 8 | 40 mm | **+0.906** | **+0.906** |
| 16 | 20 mm | +0.858 | +0.734 |
| 32 | 10 mm | +0.787 | +0.634 |
| 64 | 5 mm | +0.718 | +0.581 |

Two independent implementations agreeing with us at the same strength is real
evidence about the ray map. Caveat: agreement is coarse-scale; at 5 mm our field
correlates with the brute force at +0.72, so fine structure is only partly
confirmed.

### C5. "Flux conserved to 1.0000" — CIRCULAR.

The band-local step *renormalises* the flux to the target by construction
(`kk = want/got`). Measuring 1.0000 afterwards tests that the division worked,
not that the physics conserves energy. It should never have been listed beside
independent results. The non-circular version — does the total energy leaving the
glass equal the energy entering it? — has **not** been measured.

### C6. Accuracy — NOW INDEPENDENTLY GROUNDED (upgraded after the audit).

The original "1.65x more accurate than Monte Carlo" was self-referenced, same
structure as C1. That has now been replaced by a comparison against a reference
neither method produced: the brute-force geometric trace
(`tools/accuracy_vs_ground_truth.py`).

| tiles | tile | OUR FIELD | CYCLES |
|---|---|---|---|
| 8 | 40 mm | **0.907** | 0.825 |
| 16 | 20 mm | **0.858** | 0.602 |
| 32 | 10 mm | **0.787** | 0.475 |
| 64 | 5 mm | **0.718** | 0.400 |

Of the ground truth's caustic core, **our field covers 99.9%** and Cycles'
caustic covers **54.7%** — it misses about half of it. Our field is closer to the
independent reference at every scale, and the margin widens as the scale
sharpens. That is a real accuracy result and it supersedes the self-referenced
one.

### C7. "Wave correction" — VERIFIED. This is the real result.

Previously asserted from theory. Now checked three ways
(`tools/verify_wave_correction.py`):

* the solver's 2048-entry profile table equals the true Airy function to
  **8.1e-03 of peak**, with the first sign change at u = 2.2915 in both;
* the fold diffraction integral, computed from scratch (a cubic-phase wavefront
  integrated over the pupil), peaks at X = **-1.00** where Ai² peaks at
  **-1.0188**;
* the fringe scale's wavelength dependence, fitted from the same integral at 450,
  550 and 650 nm, is **0.698** against the analytic **0.667** — a 3% agreement
  with the exponent the code assumes for dispersion.

That last one is the load-bearing number for the whole dispersion story.

### C8. "Dispersion is correct" — VERIFIED (ordering, not just magnitude).

We previously reported only that the channels *differ* (|R-B| = 37.6% of field
mean). Differing is not correct — the ordering must match the physics. Measured
on the bake: mean radius of the brightest 1% per channel is **R 54.4 mm,
G 53.4 mm, B 52.9 mm**. Water's index falls with wavelength (R 1.33311,
G 1.33799, B 1.34648), so red refracts least and must land farthest. It does.
The ordering is right.

### C12. "Wave-corrected fringes" — THE FRINGES WE DRAW ARE NOT PHYSICAL. Major correction.

Prompted by the question "how do we verify this is what an actual caustic will
look like". The answer exposed a claim we have been implying for the whole
project without ever testing it.

`tools/fringe_scale.py` computes the fold's physical diffraction width from the
ray map's cubic term:

| quantity | value |
|---|---|
| physical diffraction width at the fold | **123 um** |
| width the renderer uses (`airy_scale`) | 1500 um |
| ratio | **12.2x too wide** |

And then the reason it does not matter, which is worse:

| quantity | value |
|---|---|
| sun's angular size | 0.53 deg |
| blur that imposes at ~100 mm to the fold | **925 um** |
| ratio to the fringe spacing | **7.5x** |

**Under a real sun this caustic has no visible fringes at all.** The source's
angular size washes them out. That matches everyday experience — nobody sees
fringes in a glass of water's caustic in sunlight; they see a smooth bright ridge
with colour fringing from dispersion.

So the fringe structure in every render we have produced is a **visibility
choice**, not a depiction of reality, and no photograph can confirm it. Any
statement implying the fringe pattern has been or could be experimentally
validated must be removed.

**What survives is boundedness.** The physical content of the wave model is not
"there are fringes", it is "the intensity stays finite at the fold instead of
diverging". That is testable with an HDR photograph of a real caustic, and it is
the claim to take to an experiment. The protocol and the falsifiable numbers are
in `docs/PHYSICAL_TEST.md`; `tools/verify_against_photo.py` measures them.

### C13. Nothing in this project has touched reality.

Every check is simulation against simulation — Cycles, the brute-force tracer,
the closed-form cylinder. They establish that the maths is implemented correctly
and that the ray map is right for the modelled geometry. None of them can say
whether a real glass of water produces the pattern we draw. The existing reference
photograph cannot close that gap either: four parameters are unknown (glass
dimensions, water level, light direction, camera scale) and its caustic core is
clipped across 2,919 pixels. Two measurable features fitted with four free
parameters is not a test.

As a weak consistency check the photograph does carry one real signal, and it is
the one that survives a bad calibration: measured per-colour radii on the real
caustic give **red 4.969, green 4.959, blue 4.892** glass radii — red lands
farthest, blue closest, matching the index ordering, with an R-B separation of
1.6% against our predicted 2.9%. The ordering is a genuine physical consistency
check; the absolute radii are worthless because the calibration was guessed.

### C9. "The method is more efficient" — TRUE ONLY INSIDE A NARROW SCOPE.

The 0.27 s bake is for **one fixed geometry** the solver was written for: a
cylinder of radius 0.035 m and height 0.090 m with a specific ripple field. Change
the glass and the solver needs new work. Cycles has no such contract. Any
efficiency statement must carry that scope, and it does not survive comparison
against "a general renderer on an arbitrary scene".

### C10. "The Blender plug-in is a deliverable" — TRUE, WITH A CONTRACT.

`tools/test_addon.py` passes 7/7 headless. But it requires the Blender scene to
match the solver's geometry to the millimetre (table at z = 0, patch exactly
0.32 m, glass radius and height fixed, sun direction fixed). It is a demonstrator
for one scene family, not a general caustic solver. That is a legitimate
deliverable; it is not what "plug-in" usually implies.

### C11. "Photorealistic" — NOT SUPPORTED as a claim.

There is no image-understanding model in this environment, so photorealism has
never been *seen* by the author of these renders, only measured as eight summary
statistics against one stock photograph. 5/6 of those statistics match. That is
a necessary-not-sufficient test. Calling the output photoreal is a claim about
perception made by something that cannot perceive. It should be called "matches
the reference on 5 of 6 measured statistics".

## The limit that actually matters

Against a brute-force trace the caustic covers **8.95%** of the patch; the brute
force says **4.16%**; Cycles says **0.20%**. Our field is 2.1x broader than an
independent geometric trace and ~20x broader than a path tracer. Both peaks are
clipped so the peak height tells us nothing. The smoothing — the Airy treatment
plus the 5x5 band mean — spreads energy over ~1.5 mm, while the true bright cores
are sub-millimetre.

So the honest characterisation of our caustic is: **correctly placed, correctly
ordered, noise-free, and too smooth.** It is a blur of the right thing. Pushing
the Airy scale lower breaks the >=3 px-per-fringe visibility rule at the bake
resolution, so this is a genuine resolution trade-off, not a bug we simply have
not fixed yet.

## What would falsify the remaining claims

1. **A common ground truth** (analytic caustic or a third renderer) to re-score
   noise without self-referencing — this is the only way C1 and C6 become real.
2. **An energy audit**: total flux leaving the glass versus entering it, with no
   renormalisation anywhere. This is the non-circular replacement for C5.
3. **A ridge/cusp test**: our method has only ever been validated on one fold
   geometry (a cylinder). A spherical lens, where the caustic has a cusp and a
   focal line, would test whether the Airy machinery generalises or is tuned to
   this case.
4. **A resolution study**: bake at 4096² with a proportionally smaller Airy scale
   and check whether the 2.1x breadth against the brute force closes. If it does
   not, the breadth is not a resolution artefact and the smoothing model is
   simply wrong in shape.

> NOTICE (2026-10-11): C9 (dispersion/chromatic separation) is WITHDRAWN. Our
> per-channel ray map inverts the sign of the chromatic split relative to both
> Mitsuba and PBRT SPPM on measured indices. See docs/EVIDENCE.md section 20.
