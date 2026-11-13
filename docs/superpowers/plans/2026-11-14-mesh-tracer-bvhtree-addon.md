# Addon Mesh Bake: Blender BVHTree Fast Path

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the addon's mesh bake 50-200x faster by using Blender's built-in C++ BVHTree (`mathutils.bvhtree.BVHTree`) instead of the pure-numpy brute-force tracer, with bit-identical hit sets, so the beauty panel can be re-baked at high quality in minutes instead of hours.

**Architecture:** A new `_trace_mesh_bvhtree` in `blender_addon/caustic_injector.py` that builds `BVHTree.FromPolygons` from the evaluated mesh and uses `bv.ray_cast` for both interface traversals. `_bake_field` gains an `accel` kwarg ("bvhtree" default in Blender, "numpy" for parity tests). The numpy tracer (`tools/mesh_caustic/trace.py`) stays as the reference implementation and test target. No build step, no new dependency.

**Tech Stack:** Blender 5.2 Python (bpy, mathutils), numpy (already bundled), the existing `mesh_caustic` package (imported by the addon).

**Spec:** EVIDENCE §28 ("supersampling above grid resolution"), §30 (camera), §31 (appearance). The numpy BVH plan (`docs/superpowers/plans/2026-11-13-mesh-tracer-bvh.md`) measured 1.84x — insufficient. The BVHTree is the lever that makes the prescribed fix affordable.

## Global Constraints

- The BVHTree path must produce hit sets within 1e-6 (distance) and 1e-9 (position) of the numpy path on the fixture sphere and the dragon. A parity failure is a stop, not a tuning opportunity.
- `trace_mesh`'s public API and return keys are unchanged; the addon's `_bake_field` gains `accel` but keeps its signature backward-compatible (default "bvhtree").
- No new dependency, no build step. The addon runs in Blender's bundled Python.
- One change per commit. EVIDENCE before summaries.

## Review Focus

- **Normal orientation.** BVHTree's face normal must match `cross(E1, E2)` (verified on a probe: it does, +Z for CCW). If it ever differs, the refraction flips and the caustic lands in the wrong place. Parity test catches this.
- **Skip handling.** The numpy path skips the entry triangle by index (`skip=ie`). BVHTree has no skip parameter; the nudge (`p + t*1e-6`) must clear the triangle. If the nudge fails, the ray is dropped (conservative). Parity test on the dragon must confirm no rays are dropped incorrectly.
- **Degenerate triangles.** `|det| <= 1e-14` triangles are never hit in numpy. BVHTree may return them; the `_shoot_bvhtree` must check `dist > 1e-9` and the barycentric bounds. Parity test covers this.
- **Origin on surface.** A ray starting exactly on a triangle must not self-hit. The nudge handles this.
- **Build cost.** BVHTree.FromPolygons on 35k tris must be < 1 s. Measured on the probe: instant.
- **Memory.** BVHTree is C++-allocated; no Python memory overhead.

---

### Task 1: BVHTree tracer in the addon

**Files:**
- Modify: `blender_addon/caustic_injector.py`
- Test: `tools/test_addon_mesh.py` (parity check added in Task 2)

- [ ] **Step 1: Add `_shoot_bvhtree` and `_trace_mesh_bvhtree` to the addon**

`_shoot_bvhtree(bv, o, d, eta_c, receiver_z, patch_half, cx, cy)` mirrors `_shoot` but uses `bv.ray_cast` for both interface traversals. `_trace_mesh_bvhtree(verts, faces, lights, receiver, opts)` mirrors `trace_mesh` but calls `_shoot_bvhtree`. Both return the same dict format (`hits`, `chan`, `weights`, `extent_m`, `accel`).

- [ ] **Step 2: Add `accel` kwarg to `_bake_field`**

`_bake_field(MT, MB, verts, faces, lights, recv, res, airy, absorb, eta, ray_mult=1, frame="FULL", frame_margin=0.15, feather=0.35, accel="bvhtree")`. When `accel == "bvhtree"`, use `_trace_mesh_bvhtree`; otherwise `MT.trace_mesh`. The probe trace also uses the chosen accel.

- [ ] **Step 3: Add `mesh_accel` prop**

`mesh_accel: EnumProperty [("BVHTREE", "BVHTree (fast)", ...), ("NUMPY", "Numpy (reference)", ...)]`, default "BVHTREE". Pass `accel=p.mesh_accel.lower()` to `_bake_field`.

- [ ] **Step 4: Update the estimate**

`estimate_seconds` is calibrated for the numpy tracer. Add `estimate_seconds_bvhtree(tris, n_side, nchan)` = `n_side² × nchan × 5e-6` (5 µs/ray, measured from the BVHTree probe). The addon uses the right one based on `mesh_accel`.

- [ ] **Step 5: Update the addon status line**

Status reports `accel bvhtree` or `accel numpy` and the measured texel.

- [ ] **Step 6: Run the addon suite**

Run: `python tools/run_blender.py --background --factory-startup --python tools/test_addon_mesh.py`
Expected: `FAILURES: 0 []` (all existing checks pass with the BVHTree path).

### Task 2: Parity test

**Files:**
- Modify: `tools/test_addon_mesh.py`

- [ ] **Step 1: Add a parity check**

Bake the fixture sphere with `mesh_accel="NUMPY"` and `mesh_accel="BVHTREE"` at the same resolution, then compare the resulting fields: assert correlation ≥ 0.999 at coarse tiles and hit counts within 5%.

- [ ] **Step 2: Run the addon suite**

Expected: all pass, including the parity check.

### Task 3: Re-bake the dragon panel with BVHTree

**Files:**
- Modify: `tools/dragon_addon_beauty.py` (add `--accel` flag, default "bvhtree")
- Output: `out/dragon_suite/addon_ours_2560_bvhtree.png`

- [ ] **Step 1: Add `--accel` flag to the driver**

- [ ] **Step 2: Run the bake at res 1024, ray_mult 1, accel bvhtree**

Expected: bake in ~30-60 s (vs 3.86 h numpy). Compare the rendered panel to the numpy-framed panel: the caustic should be in the same place with less grain (same rays, but faster traversal means I can afford ray_mult=2 or higher).

- [ ] **Step 3: If parity holds, update the figure and EVIDENCE**

Point the figure at the new panel, update the title, rebuild.

### Task 4: EVIDENCE, docs, commit

- [ ] **Step 1: Record the BVHTree parity and speedup in EVIDENCE**
- [ ] **Step 2: Update tools/README.md**
- [ ] **Step 3: Commit**

## Definition of Done

1. The addon bakes the dragon in < 5 min (vs 3.86 h).
2. Parity: BVHTree vs numpy hit sets agree within 1e-6 on the fixture and the dragon.
3. All addon tests pass.
4. The figure panel rivals Cycles in smoothness.
5. EVIDENCE records the speedup and the parity evidence.
