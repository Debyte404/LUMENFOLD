# Launch-Plane Offset Fix

> **For agentic workers:** Use superpowers:executing-plans (inline execution).

**Goal:** Start every sun ray outside the mesh. The sun branch launches from a
plane `centre - 0.5*d`, but the dragon's bounding half-extent is ~0.66 m, so
rays whose (x, y) fall inside the mesh silhouette begin *inside* the glass.
The first hit is then an exit wall refracted as an entry (wrong eta direction),
landing the ray in the wrong texel with the right energy -- conserved totals,
distorted shape, which is exactly the measured signature (0.9995 energy match,
0.6-0.8 shape parity).

**Fix (one line + comment):** offset the launch plane by `-(radius + 0.05)*d`
using the already-computed bounding-sphere radius, in the sun branch of
`trace_mesh` (covers both numpy and BVHTree backends, since both share the loop).

## Constraints

- No behaviour change for scenes where the mesh already clears the plane
  (offset only moves origins further up-sun; parallel rays, same directions).
- Parity tests must stay green; the change is backend-agnostic by construction.
- Measure shape parity before/after on the smooth dragon; record plainly either
  way. Do NOT tune anything else in the same change.

---

### Task 1: Move the launch plane outside the bounding sphere

**Files:** `tools/mesh_caustic/trace.py` (one line), `tools/test_addon_mesh.py`
(regression check: all sun-ray origins lie outside the mesh bounding sphere... or
a cheaper invariant -- see step 1).

- [x] **Step 1: Write the failing test.** `launch_offset_outside_sphere` /
  `launch_offset_covers_dragon` pin the `_launch_origin` contract (offset =
  radius + 0.05, laterals untouched); they fail until the helper exists.
- [x] **Step 2: Implement** the offset + helper (shared sun loop: both backends).
- [x] **Step 3: Run the suite** (`FAILURES: 0 []`, incl. numpy/BVHTree parity).
- [x] **Step 4: Commit** (tracer + test only) (done: 7d283a3).

### Task 2: Re-bake smooth + measure shape parity

**Files:** none. **Output:** `out/dragon_suite/addon_ours_2560_smooth_offset.png`
(ignored by git).

- [x] **Step 1: Bake + render** at the shipped smooth settings. (done:
  ours_smooth_offset.exr, 2,091,120 tris, linear EXR)
- [x] **Step 2: Measure** band parity vs `_arb_cycles_4096` (same mask as
  EVIDENCE 41/45). Bands saturate at 1.0000 on shared direct; the valid readout
  is the isolated caustic (EVIDENCE 46): 3.9x concentrated in fold spikes, 0.06%
  of fan energy.
- [x] **Step 3: Record in EVIDENCE + commit.** (done: EVIDENCE 46)
