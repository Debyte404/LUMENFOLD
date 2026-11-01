# Any-Mesh, Any-Light Caustic Injector — Design (full envelope)

Date: 2026-11-01, revised to full envelope at user request. Supersedes the
static-only scope; Phase 1 is static, Phase 2 is animation. Uriel project
memory consulted 2026-11-01 (no directly reusable addon context; reviewer
note retained: rough-surface cases attack the fold-only limitation, kept as
an explicit limit below, not a claim).

## Intent and why

The Wave Caustic Injector bakes only the tumbler scene today. This makes it
work, inside Blender as a genuine addon, with any mesh, any light source,
colors, moving surfaces, and Blender materials — as far as the method's
physics honestly stretches, with named errors everywhere else.

## Phase 1 — static (v1)

### Supported envelope

- **Meshes:** any closed manifold mesh (evaluated: modifiers applied).
  Open meshes, non-manifold edges, and missing UVs on the receiver are
  refused with named reasons, not baked as garbage.
- **Light sources:** directional SUN plus point, spot, and area lights. The
  tracer builds rays per source type: parallel grid for SUN, divergent cone
  (shadow-ray sampled origin set) for point/spot, jittered area samples for
  area lamps. One bake per enabled light, summed with per-light gain.
- **Color:** per-channel bake. Colored sources work by construction (three
  channel ray maps through measured index laws); white sources stay exact.
- **Materials (bake side):** clear dielectric and absorbing dielectric
  (Beer-Lambert per-metre RGB entered in the panel; per-ray path length
  through the mesh weights each ray, replacing the tumbler-only absorb
  flags for mesh mode). Principled settings on the Blender material that the
  bake reads: IOR and absorption; everything else ignored and stated.
- **Materials (render side):** existing tint/injection machinery unchanged.
- **Receiver:** any object with a full 0–1 UV map; patch = its world bbox,
  field image maps UV directly. Validated up front.
- **Explicitly unsupported in v1, refused by name:** rough/transmission-rough
  glass (no sharp fold exists to correct; the band assumption fails — this is
  the reviewer's rough-surface case, recorded as a limit), volumetrics inside
  the body, nested dielectrics (one closed surface per object), motion blur.

### Preserved

- `Solver scene` mode byte-identical: same flags, same output, existing
  tests unchanged.
- Airy scale stays the documented visibility parameter, never physical.
- Absolute paths only; Blender 5.x; Steam 5.2 headless tests.

## Phase 2 — animation (v2, gated on Phase 1 tests green)

- Per-frame mesh Bake over a frame range (re-trace per frame; topology must
  be constant —8829 shape keys okay, remesh-off), PNG sequence, injection as
  an image sequence with Auto Refresh, one Bake-all button with progress and
  cancel.
- Deforming meshes (armature sims) supported if the vertex count is stable;
  fluid-remeshes are refused by name.

## Non-goals

- No C++ port (Python tracer, minutes per frame at 300^2, stated in-panel).
- No paper text edits in this work.

## Anti-goals

- No silent wrong-place caustics: contract validation first, named refusal.
- No threshold tuning after seeing results; misses recorded.
- No claiming rough-glass support.

## What the human decided

- Full envelope per this doc, phased static-then-animation. Uriel consulted.

## Left to the builder

- Panel layout (Source enum, per-light list UI, absorb RGB inputs, frame-range
  box for Phase 2).
- LUT export format for Airy without scipy; numpy-only distance transform.
- Receiver contract generalization details and validation messages.
- Fixture .blend for headless tests (small closed mesh + plane + sun).
- Default resolutions vs measured time estimates (dragon numbers as reference).

## Verification

- Existing `test_addon.py` unchanged-green on Steam 5.2.
- New `test_addon_mesh.py`: sphere bake nonzero + bounded; point-light bake
  runs; open mesh / missing UVs cancel with named errors; inject/remove
  round-trip; absorb coefficients change channel ratios.
- Phase 2: 3-frame sequence bake, frames differ, injection node uses sequence.
- `check_paper.py` green; no paper edits.

## Research notes (books + latest docs, 2026-11-01)

Context7 MCP is not wired into this session (no context7 server configured),
so latest-docs duty fell to the official Blender 5.x API reference and
published rendering literature; key points verified, not assumed:

- Blender 5.0 API (docs.blender.org/api/current + 5.0 review): Grease Pencil
  renamed to Annotation (irrelevant — addon touches none of it); `bpy.props`
  dict-style storage access removed (addon uses attribute access: safe);
  `Material.use_nodes` deprecation announced for 6.0 (we set it; fine on 5.x,
  revisit at 6.0); `wm.obj_export(apply_modifiers, export_selected_objects)`
  confirmed current. mathutils moved to float32 (perf); our tracer keeps
  float64 deliberately — refraction discriminants need it.
- PBRT 4th-ed photon-mapping chapters + SPPM literature: radius schedules
  shrink per iteration; absolute radius must scale with scene extent. This is
  exactly the dragon lesson (0.008 m @ 0.32 m paper scene vs 0.05 m @ 8 m
  dragon scene, still unconverged at 256 iters). Implication for mesh Bake:
  presets must scale with receiver size, and the panel states the time cost
  before baking.
- Mitsuba 3 usage (via repo): spectral emitter conventions differ per plugin
  type (sphere+area with float radiance, not directional+vector) — mesh Bake
  stays with Blender SUN + point/spot/area lamps only, no HDRI sampling (out
  of scope, stated).

Optimizations adopted from this reading (good practice, in this build):

1. BBox pre-cull: rays generated only over the mesh's projected extent
   (already in dragon tracer; a hard requirement for mesh Bake).
2. Batch-vectorized Moller-Trumbore stays O(rays x tris); the scale escape is
   a uniform grid or BVH — explicit future work, NOT silently promised.
3. Panel shows predicted bake time from tri count x ray budget before running
   (cost honesty, same spirit as the paper's cost tables).
4. No scipy in-Blender: Airy from the shipped LUT, distance transform as
   two-pass chamfer — one less hosted dependency to rot.
