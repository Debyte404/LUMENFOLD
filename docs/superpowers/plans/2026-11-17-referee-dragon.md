# Independent Brute-Force Referee for the Dragon

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> (inline execution). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Verify the injected dragon caustic against a referee written from
scratch that shares **no code** with the bake path. The pool scene has this
(810k-ray independent tracer, EVIDENCE §24 pre-registered, r >= 0.80); the
dragon never did — every accuracy claim on it so far is ours-vs-Cycles, which
is renderer-vs-renderer, not truth-vs-claim.

**Role separation.** The referee is the *pre-registered independent estimator*.
It does not import from `tools/mesh_caustic`, `blender_addon`, or reuse any
existing verification code. It may read the scene geometry only through the
exported OBJ/PLY (a *different serialization* than the bake consumes).

**Method (pre-registered here):** brute-force Möller–Trumbore, two-interface
air→glass→air, TIR drop, exact unpolarized Fresnel at both interfaces, Beer-
Lambert absorption off (achromatic scene), **stratified-jitter ray grid over
the sun disk** (4×4 subsamples per sun point, 8 directions per jitter cell —
different sampling structure than the bake's regular grid, deliberately).
Resolution 1024² over the same fan frame the bake used. Budget ~3M rays
(runtime est. ~10–20 min pure Python with the numpy Möller–Trumbore inner
loop over triangles at once — acceptable; slow is fine, independent is the
point).

**Pass criterion (pre-registered):** band-resolved correlation r >= 0.80 at
4 mm and 9 mm, r >= 0.85 at 18/37 mm, AND integrated caustic energy ratio
within [0.85, 1.18]. A miss is recorded as a finding, not tuned away. If the
referee disagrees with *both* the bake and Cycles in the same direction, that
is evidence about the scene setup (normals/serialization), reported as such.

---

### Task 1: Export the dragon geometry for the referee

**Files:** new `tools/referee_export_dragon.py` (temp-or-committed: commit).
**Output:** `out/referee/dragon_tris.npz` (verts float64 (N,3), tris int64
(M,3), sun direction, receiver frame — all in world space).

- [ ] **Step 1: Export from the *authored* data mesh** (no modifier stack;
  the bake path now uses it too) with custom split normals written out per
  corner (the referee interpolates them itself, independently).
- [ ] **Step 2: Also export the receiver frame** (cx, cy, half, z) exactly as
  the bake's AUTO frame produced, so both estimate the same patch.
- [ ] **Step 3: Sanity-print** tri count vs the bake's BAKE_STATUS (must match
  87,130 → 87,130).

### Task 2: Write the referee

**Files:** new `audit/referee_dragon.py` (lives in audit/: independence is
structural, not nominal). Pure numpy, no project imports.

- [ ] **Step 1: Möller–Trumbore over all triangles per ray** (vectorized).
- [ ] **Step 2: Two-interface traversal** with Fresnel weights, TIR drop,
  Beer-Lambert zero.
- [ ] **Step 3: Stratified sun-disk sampling** (4×4 per cell, 8 jitter
  directions — NOT the bake's sampling).
- [ ] **Step 4: Bin to 1024², save EXR-free .npy + JSON stats.**

### Task 3: Compare and record

**Files:** modify `audit/run_audit.py` — add checker `C11 referee dragon`
that loads both fields, computes the band correlations + energy ratio, prints
PASS/FAIL against the pre-registered thresholds.

- [ ] **Step 1: Run the comparison; record the numbers.**
- [ ] **Step 2: EVIDENCE section** with the table, either outcome.
- [ ] **Step 3: Commit** referee + checker + EVIDENCE.
