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

**Method (pre-registered here, amended 2026-11-17 before any run):** brute-force
Möller–Trumbore over all triangles is 8.4 Tflop for the subdivided mesh (measured),
so the referee shares ONLY the geometry index (`mathutils.bvhtree`, a library
call, not project code) while every element of the transport is written
independently in `audit/`: own Snell refraction, own unpolarized Fresnel, own
stratified sun-disk sampling, own binning. Target geometry is the **authored
87,130-tri mesh** (`out/dragon_clean.blend`) at **512² over the same fan frame**
— texel 2.9 mm, enough to test the 9/18/37 mm bands that carry the accuracy
argument; 4 mm is below the referee's resolution and is NOT claimed by the
referee (stating this before the run, not after). Rays: 512² × 16 sun-disk
subsamples = 4.19M.

**Pass criterion (pre-registered):** band-resolved correlation r >= 0.80 at
9 mm, r >= 0.85 at 18/37 mm, AND integrated caustic energy ratio within
[0.85, 1.18]. A miss is recorded as a finding, not tuned away. If the referee
disagrees with *both* the bake and Cycles in the same direction, that is
evidence about the scene setup (normals/serialization), reported as such.

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
