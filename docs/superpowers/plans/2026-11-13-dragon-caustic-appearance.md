# Dragon Caustic Appearance Fix Plan

> **For agentic workers:** execute inline with TDD. Pre-registered criteria are
> binding: a miss is recorded, never tuned to pass.

**Goal:** make the ours-injected dragon panel comparable to the Cycles panel in
appearance (no visible texel blocks, no dominant speckle) without changing the
method, the placement, or the measurement claims.

**Spec:** `docs/EVIDENCE.md` §28 prescribes exactly this work: "supersampling
rays above grid resolution (decouple n_side from n_grid) plus a feathered band
edge — recorded here as prescribed work, not done." Commit `570c3f2` landed the
supersample half (ray_mult=2) after the shipped panel was baked; the feather
and the resolution half are missing, and no post-supersample bake was ever
measured into the figure.

## Why the panel looks bad (measured)

- The bake bins 1024x1024 texels over the receiver patch, which
  `_resolve_target` sizes as `max(xext, yext)/2` = 4.18 m on the dragon plane
  (8.36 x 7.30 m): **8.2 mm per texel**, ~13 image px at the subject's
  0.62 mm/px. That is the blockiness.
- 258k hits land in ~15k fan texels: the Airy band correction smooths the band
  interior but the out-of-band hits and the hard band edge remain.
- The tracer launches rays over the **mesh bounding sphere**, not the receiver
  (trace.py L200-236): the patch only filters and bins hits. So re-binning the
  same hits into a smaller, fan-framed patch is **free** — same rays, same
  hits, finer texels, more hits per texel.

## Pre-registered criteria (before any bake)

1. **Texel:** bake texel over the fan <= 1.6 mm (<= ~2.5 image px at
   0.62 mm/px). Expected: fan ~1.5 m square framed patch at res=1024 ->
   ~1.5 mm.
2. **Placement unchanged:** the injected panel's bright-region centroid stays
   within 3% of frame of the Cycles-native panel's. Baseline measured
   2026-11-13: cycles (0.445, 0.756), ours (0.431, 0.778) — the fix must not
   move it beyond that tolerance.
3. **Cost:** bake wall time <= 2.5 h at res=1024, ray_mult=1 (the §28 71-min
   class; the probe adds ~1.5 min).
4. A miss on any criterion is recorded in EVIDENCE, not re-tuned.

## Design

- `tools/mesh_caustic/trace.py` gains `frame_patch(hits_xy, recv, margin,
  min_half)`: square framed patch from the probe hit bbox, clamped inside the
  receiver. Pure numpy, unit-tested outside Blender.
- `tools/mesh_caustic/band.py` gains `correct(..., feather=0.0)`: cross-fade
  the outer `feather` fraction of the band to the raw field. `feather=0` is
  bit-identical to today. The measurement path (`dragon_suite.py` proto) keeps
  strict conservation; the addon display path documents the feather.
- `blender_addon/caustic_injector.py`:
  - props: `mesh_frame` (FULL/AUTO, default AUTO), `mesh_frame_margin`
    (0.15 m), `mesh_ray_mult` (default 2, preserving current behaviour),
    internal `frame_uv` (u0, v0, du, dv).
  - `_bake_field`: AUTO runs a cheap scalar-eta probe (n_side=128, ~1.5 min on
    the dragon) over the full receiver, frames the patch, then traces and bins
    `res` texels over the framed rect. FULL keeps today's behaviour.
  - The inject maps the framed image onto the target through the target's
    **actual world->UV affine fit** (lstsq over loop vertices), not an assumed
    0-1 stretch: a `CAUSTIC_map` Mapping node with Scale=1/(du,dv),
    Location=-(u0,v0)/(du,dv). Identity for FULL. This also removes the
    latent square-patch-vs-plane-extent anisotropy by construction.
  - `bake_seq` stays FULL (one shared UV mapping across frames).
- `tools/test_mesh_trace.py`: unit tests for `frame_patch` and the feather.
- `tools/test_addon_mesh.py`: AUTO bake finishes and reports the frame; the
  framed field re-binned into the full grid correlates >= 0.9 at coarse tiles
  with a FULL bake of the same scene (same caustic, same place); frame_uv is
  the affine fit; FULL is identity.
- `tools/dragon_addon_beauty.py`: reproducible driver — neutral medium, bake,
  inject, render CAM_beauty with the spike settings; writes a JSON sidecar
  (bake s, hits, frame rect, texel mm, render s). The §28 panel had no
  committed driver; this fixes that too.

## Order

1. Baseline dry run of the CURRENT code at res=128 through the new driver —
   measures placement and the fan bbox before any change.
2. TDD: frame_patch, feather, addon wiring, tests.
3. Dry run of the framed code at res=128; compare to baseline (criterion 2).
4. Full bake res=1024 ray_mult=1 + render 2560x1440/1024spp; check criteria.
5. Figure, EVIDENCE §31, tools/README, commit.

## Amendment: measured before the final bake (2026-11-13)

Dry run (res 128, ray_mult 2, AUTO, 949 s): placement END-TO-END verified -
the framed panel's bright centroid is (0.443, 0.764) vs Cycles (0.445, 0.756),
closer to Cycles than the shipped panel (0.431, 0.778). Criterion 2 met.
Found and fixed en route: a relative `render.filepath` silently resolves
against the .blend's directory, so the driver wrote nothing; the driver now
uses absolute paths.

Probe support on the dragon mesh (5034 probe hits, 64x64 bins, peak bin 333):

| keep fraction of peak bin | frame side | texel at res 1024 |
|---|---|---|
| any hit | 2.78 m | 2.72 mm |
| 1% | 2.65 m | 2.59 mm |
| 2% | 2.26 m | 2.21 mm |
| 5% | 1.74 m | 1.70 mm |
| 10% | 1.61 m | 1.57 mm |

Pre-registered choice BEFORE the final bake: **density = 0.10 of the peak
probe bin** (margin 0.15 m). Expected frame ~1.6 m, texel at res 1024 ~1.57
mm, meeting criterion 1. Hits in bins below the threshold are not binned;
the injected image's EXTEND continues the edge texel outward, so the spray
fades at the frame edge rather than cutting to black.

Machine rate: 13.5 ms/ray measured in both dry runs vs 4.06 ms/ray in the
section 28 bake (3.3x slower machine state). At res 1024 / ray_mult 1 the
bake is ~3.9 h - over the pre-registered 2.5 h; at res 768 it is ~2.2 h with
texel 2.10 mm, a criterion-1 miss. Neither satisfies both; the budget choice
was put to the repository owner and the outcome, either way, is recorded in
EVIDENCE as measured.
