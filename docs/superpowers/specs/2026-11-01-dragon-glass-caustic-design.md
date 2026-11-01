# Dragon Glass Caustic — Design (C-first: spike then suite)

Date: 2026-11-01. Picked approach C from brainstorm 2026-11-01.

## Intent and why

Turn the in-repo `models/dragon.blend` (43k-vert dragon,
plane ground, 1 camera, 3 point lights, 2 materials, Blender 5.2.3) into a glass
caustic body in new scenery, then prove behaviour across the paper's engines
with no visual cheating. Success is a shared-rig comparison the paper can cite,
not a pretty render alone.

## Goals

- Glass dragon that actually focuses light: closed manifold volume, Principled
  transmission 1.0, roughness 0, IOR 1.525 (paper glass), on a ground receiver.
- One locked sun + one locked camera for every engine. New staging is fine;
  moving light/camera per engine is not.
- Spike first: 720p Cycles-native low-spp smoke test proving a visible caustic
  exists at this scale before anything expensive runs.
- Suite (only if spike passes): ours-injected vs Cycles-native vs PBRT-v4 SPPM
  vs Mitsuba 3, plus an independent mesh tracer as referee (no Jacobian, no
  solver import), scored at 40 mm and 5 mm tiles like Table 1 of the paper.
- Physical scale for all proof renders (fringe `d ~ 6.8 um`, subpixel).
  Exaggerated `w = 1.5 mm` (~220x operational) panels only after proofs exist,
  labelled as such.
- High-res beauty: 2560x1440 proposed (fallback 1920x1080 if dragon render
  exceeds ~3 min/frame on this machine). Measurement ortho pass at 1024^2 for
  tiling, separate from beauty.

## Non-goals

- No same-scene rebuild: the tumbler table rig stays as is; this is new scenery.
- No paper text edits in this work. EVIDENCE first, then paper only if
  thresholds pass and dual-format gate passes.
- No animation/flicker numbers in the spike; stills only until suite.

## Anti-goals

- Per-engine tuning to make one winner (different sun, exposure cheating,
  Filter Glossy left on for Cycles).
- Claiming exaggerated fringes as physical.
- Tuning thresholds after seeing results; misses are recorded as misses.

## Constraints (from AGENTS.md)

- One change per commit; EVIDENCE before paper before summaries.
- Any paper claim lands in both `docs/paper/` and `docs/paper-ieee/` in the
  same commit; `check_dual_format.py` must print DUAL-FORMAT OK.
- Fringe scale honesty: canonical 6.77 um (Eq. 14), first zero 15.84 um,
  `airy_scale = 1.5 mm` is 220x display exaggeration, shipped ripple clips at
  0.123 mm are 18x operational never physical. Sun blur ~925 um blurs fringes
  136x.
- Benchmark scope stays stated: one scene family, one machine, one sun angle.
- No apparatus validation; simulation vs simulation only.
- New tool/figure/section needs a plan in `docs/superpowers/plans/`.

## Approaches considered

- A. Adapt .blend in place (kept staging, swap points for sun, plane as
  receiver, ortho scoring cam, OBJ export). Fast, paper-comparable.
- B. Full new studio (HDRI + sun rig like `studio.py`, two cams, tuned
  exposure). Prettiest, 2-3x Blender work.
- C. Spike then suite (picked). Same as A but gated: 720p Cycles-native smoke
  test first; full four-engine high-res run only if the dragon focuses light.
  Reason: 43k-vert closure/scale is the unknown; everything expensive depends
  on it. B rejected unless spike shows current plane/camera cannot carry it.

## What the human decided

- Approach C-first.
- New scenery, not paper rig — confirmed.
- High-res for visible difference — confirmed (2560x1440 proposed).
- One sun + one camera locked across engines — confirmed yes.
- Physical scale for proofs, exaggerated showcase only after — confirmed.

## What's left to the builder

- Exact sun vector (default paper `SUN_DIR (0.80, 0.42, -0.43)`, angle 2.4 deg
  unless dragon staging forces a fit; record whatever is used).
- Manifold repair for the dragon (check open edges, normals, Solidify only if
  single-sided; record method).
- Exposure matching across engines (no per-clip renormalization that hides
  light loss; record gains).
- SPPM budget (paper: 500k photons, radius 0.008, spp = iterations) and
  Mitsuba integrator choice (3.9 has no SPPM; qualitative only per paper
  limitations §8).
- Mesh tracer resolution (plan says 1400^2; minimum reportable 700^2) and tile
  convention (paper: tile size in mm, not count).

## Spike definition of done

- `blender --background dragon.blend` opens clean in 5.2; MCP
  `get_addon_status` + `get_scene_info` + one `execute_blender_code` query
  succeed with Blender server started from the sidebar.
- Glass-converted dragon + single sun renders a visible bright fan on the
  plane at 720p low-spp Cycles-native. Screenshot via `look`.
- Go/no-go recorded; on no-go, stop and report geometry cause, do not proceed
  to suite.

## Suite pre-registration (gated, not yet run)

- Referee: independent triangle tracer, sun-perpendicular grid, first-hit
  Snell, receiver binning on shared patch. No solver Jacobian.
- Metrics: r@40mm (pass >= 0.80 proposed for dragon; paper tumbler is 0.917),
  r@5mm reported only, edge R>G>B ordering, coverage of caustic core,
  bake ms + render s per engine at stated res/spp.
- A miss is a negative result in EVIDENCE, not a retune.

## Verification

- Addon: MCP tools respond; `look` images in conversation.
- Spike: 720p PNGs + settings dump (`--dump-settings` pattern).
- Suite: CSV + figure + `EVIDENCE.md` dated section; paper gate only after:
  `build_paper_pdf.py`, `build_paper_ieee.py`, `check_dual_format.py` all exit 0.

Calls I made as defaults (check while reading): 2560x1440 beauty,
1024^2 measurement, IOR 1.525, paper sun vector, r >= 0.80 dragon threshold.
