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

- [ ] **Step 1: Write the failing test.** A small closed mesh (fixture sphere)
  baked through `trace_mesh` with a directly introspectable hook, OR assert on
  `_launch_offset` helper if the offset is factored out (preferred: factor
  `offset = radius + 0.05` into a named helper and unit-test
  `offset >= bounding half-extent`).
- [ ] **Step 2: Implement** the offset + helper.
- [ ] **Step 3: Run the suite** (`FAILURES: 0 []`).
- [ ] **Step 4: Commit** (tracer + test only).

### Task 2: Re-bake smooth + measure shape parity

**Files:** none. **Output:** `out/dragon_suite/addon_ours_2560_smooth_offset.png`
(ignored by git).

- [ ] **Step 1: Bake + render** at the shipped smooth settings.
- [ ] **Step 2: Measure** band parity vs `_arb_cycles_4096` (same mask as
  EVIDENCE 41/45). Expect the 4-9 mm bands to rise toward the ceiling; if they
  do not move, record that plainly -- the suspect is eliminated, not confirmed.
- [ ] **Step 3: Record in EVIDENCE + commit.**
