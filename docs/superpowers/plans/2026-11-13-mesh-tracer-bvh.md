# Mesh Tracer BVH Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the addon's any-mesh bake 5-50x faster with a numpy-only BVH inside the tracer, with hit sets identical to the brute-force path.

**Architecture:** A flat-array binned-SAH BVH (`tools/mesh_caustic/bvh.py`) built once per `trace_mesh` call; `_shoot` asks it for the nearest hit instead of testing all triangles. The brute-force path stays behind `opts["accel"]=False` as the reference and rollback. No API change, no new dependency, no build step.

**Tech Stack:** Python 3.12, numpy only (must run in Blender's bundled Python), the existing `tools/mesh_caustic` package and `tools/test_mesh_trace.py` harness.

**Spec:** this plan; it implements the rejected-alternatives analysis in `docs/superpowers/plans/2026-11-13-dragon-caustic-appearance.md` and EVIDENCE §28's "supersampling above grid resolution" thread (the bake cost is the reason that fix is expensive).

## Global Constraints

- numpy only. No new dependency, no compiled extension, no build step: the module is imported by the addon inside Blender's bundled Python and by `tools/test_mesh_trace.py` in plain Python.
- Public API unchanged: `trace_mesh(verts, faces, lights, receiver, opts) -> {"hits","chan","weights","extent_m"}` and the four light dict types. All existing tests must pass without edits.
- Numerical semantics identical to `_first_hit`: hit iff `|det| > 1e-14`, barycentric `u,v >= 0`, `u+v <= 1`, `dist > 1e-9`; `skip` excludes one ORIGINAL face index; the reported face is the nearest by distance, and on an exact distance tie the LOWEST original index (matching `np.argmin` on the brute-force array).
- One change per commit. EVIDENCE before summaries. A miss against a pre-registered criterion is recorded, never tuned to pass.

## Review Focus

- **Grazing hits at leaf boundaries.** A slab test that is 1 ulp too tight drops a real hit that brute force finds. Expected: identical hit sets on rays aimed at triangle edges; AABBs padded by 1e-9 m at build.
- **Exact distance ties.** Brute-force `np.argmin` returns the lowest index; a front-to-back traversal can return the higher one. Expected: the tie-break rule above, pinned by a constructed two-triangle test.
- **`skip`.** The second interface traversal must not re-hit the entry triangle. Expected: same hit with and without acceleration at `skip=ie`.
- **Degenerate triangles** (`|det| <= 1e-14`). Never hit, exactly as brute force. Expected: a zero-area triangle in the mesh changes nothing.
- **Rays starting inside the mesh / on the surface.** No origin-side culling; slab bounds admit `t >= 0` with the same epsilon.
- **Build cost.** One build per `trace_mesh` call; a 35k-tri build must be a small fraction of the trace. Expected: build <= 2 s on the dragon and node count <= 2 x triangles.

---

### Task 1: Parity harness and RED test

**Files:**
- Modify: `tools/test_mesh_trace.py`
- Test: `tools/test_mesh_trace.py::test_bvh_matches_bruteforce_on_random_rays`

**Interfaces:**
- Consumes: `mesh_caustic.trace._prep`, `_first_hit` (existing), `_sphere` fixture (existing).
- Produces: `_random_rays(verts, n, seed)` helper in the test file (returns `(origins, dirs)` in a mesh-bbox-covering box).

- [ ] **Step 1: Write the failing test**

```python
def test_bvh_matches_bruteforce_on_random_rays():
    from mesh_caustic import bvh
    from mesh_caustic.trace import _prep, _first_hit
    v, f = _sphere()
    A, E1, E2 = _prep(v, f)
    b = bvh.build(v, f)
    rng = np.random.default_rng(7)
    lo, hi = v.min(axis=0) - 0.1, v.max(axis=0) + 0.1
    for _ in range(2000):
        o = rng.uniform(lo, hi)
        d = rng.normal(size=3)
        d /= np.linalg.norm(d)
        # _shoot builds these per ray; the parity test must too
        pvec = np.cross(d, E2)
        det = np.einsum("ij,ij->i", E1, pvec)
        inv = np.zeros_like(det)
        good = np.abs(det) > 1e-14
        inv[good] = 1.0 / det[good]
        bf = _first_hit(o, d, A, E1, E2, pvec, det, inv)
        ac = bvh.nearest(b, o, d)
        assert (ac is None) == (bf[0] is None)
        if ac is not None:
            assert ac[0] == bf[0], "nearest face must match brute force"
            assert np.allclose(o + ac[1] * d, bf[1][0], atol=1e-9)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python tools/test_mesh_trace.py`
Expected: `ModuleNotFoundError: No module named 'mesh_caustic.bvh'`.

- [ ] **Step 3: Commit the RED test only**

```bash
git add tools/test_mesh_trace.py
git commit -m "Pin BVH parity against the brute-force tracer"
```

### Task 2: Build the BVH

**Files:**
- Create: `tools/mesh_caustic/bvh.py`
- Test: `tools/test_mesh_trace.py::test_bvh_partitions_every_triangle_once`

**Interfaces:**
- Produces: `build(verts, faces, leaf_size=8) -> BVH` with flat arrays `bounds (N,6)`, `left (N,)`, `right (N,)`, `start (N,)`, `count (N,)`, `order (T,)`, `orig (T,)`, and reordered `A, E1, E2`.

- [ ] **Step 1: Write the failing test**

```python
def test_bvh_partitions_every_triangle_once():
    from mesh_caustic import bvh
    v, f = _sphere()
    b = bvh.build(v, f)
    assert len(b.order) == len(f)
    assert sorted(b.orig.tolist()) == list(range(len(f)))
    root = b.bounds[0]
    assert (root[:3] <= v.min(axis=0) + 1e-9).all()
    assert (root[3:] >= v.max(axis=0) - 1e-9).all()
    assert len(b.bounds) <= 2 * len(f) + 1, "a build bug doubles node count"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python tools/test_mesh_trace.py`
Expected: FAIL with `AttributeError`/`ImportError` on `bvh.build`.

- [ ] **Step 3: Implement the binned-SAH build**

12 bins on the longest centroid axis per node, split at the SAH minimum; leaves at `count <= leaf_size`; AABBs padded by `1e-9`; recursed with an explicit stack (no recursion limit risk). `orig` maps leaf order to the input face index.

- [ ] **Step 4: Run the test**

Run: `python tools/test_mesh_trace.py`
Expected: `test_bvh_partitions_every_triangle_once` PASS; the Task 1 parity test still FAILs on the missing `nearest`.

- [ ] **Step 5: Commit**

```bash
git add tools/mesh_caustic/bvh.py tools/test_mesh_trace.py
git commit -m "Add flat-array SAH BVH for the mesh tracer"
```

### Task 3: Nearest-hit traversal and parity

**Files:**
- Modify: `tools/mesh_caustic/bvh.py`
- Test: `tools/test_mesh_trace.py`

**Interfaces:**
- Produces: `nearest(bvh, o, d, eps=1e-9, skip=-1) -> (face_index, distance) | None`. Returns the ORIGINAL face index.

- [ ] **Step 1: Write the failing edge tests**

```python
def test_bvh_tie_breaks_to_lowest_index():
    # two coincident triangles at z=0, indices 0 and 1; the nearest hit must be 0
    v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]] * 2, float)
    f = np.array([[0, 1, 2], [3, 4, 5]])
    from mesh_caustic import bvh
    b = bvh.build(v, f, leaf_size=1)
    hit = bvh.nearest(b, np.array([0.2, 0.2, 1.0]), np.array([0.0, 0.0, -1.0]))
    assert hit is not None and hit[0] == 0 and abs(hit[1] - 1.0) < 1e-12

def test_bvh_skip_and_degenerate():
    from mesh_caustic import bvh
    v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 0]], float)
    f = np.array([[0, 1, 2], [0, 1, 3]])  # second triangle is degenerate
    b = bvh.build(v, f, leaf_size=1)
    o, d = np.array([0.2, 0.2, 1.0]), np.array([0.0, 0.0, -1.0])
    hit = bvh.nearest(b, o, d)
    assert hit is not None and hit[0] == 0 and abs(hit[1] - 1.0) < 1e-12
    assert bvh.nearest(b, o, d, skip=0) is None

def test_bvh_hits_on_a_shared_edge():
    # aim exactly at the edge shared by both triangles: brute force must be
    # reproduced, whichever face it reports
    from mesh_caustic import bvh
    v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], float)
    f = np.array([[0, 1, 2], [1, 3, 2]])
    b = bvh.build(v, f, leaf_size=1)
    o, d = np.array([0.5, 0.5, 1.0]), np.array([0.0, 0.0, -1.0])
    hit = bvh.nearest(b, o, d)
    assert hit is not None and abs(hit[1] - 1.0) < 1e-12

def test_bvh_origin_inside_mesh():
    from mesh_caustic import bvh
    v, f = _sphere()
    b = bvh.build(v, f)
    hit = bvh.nearest(b, np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]))
    assert hit is not None and hit[1] > 0.0
```

- [ ] **Step 2: Run to verify they fail**

Run: `python tools/test_mesh_trace.py`
Expected: FAIL with `AttributeError: nearest`.

- [ ] **Step 3: Implement traversal**

Slab test per node (`t0 = max((lo-o)/d)`, `t1 = min((hi-o)/d)`, admit if `t0 <= t1` and `t1 >= 0`); guard near-zero `d` components with `np.errstate` so the division yields +/-inf instead of raising; push children, visit the nearer child first by entry distance; at leaves run the exact Möller-Trumbore mask from `_first_hit` on the leaf's reordered triangles; keep `best` if `dist < best` or (`dist == best` and `orig < best_orig`). No recursion.

- [ ] **Step 4: Run the full test file**

Run: `python tools/test_mesh_trace.py`
Expected: all tests PASS including `test_bvh_matches_bruteforce_on_random_rays` (2000 rays, 1e-9 tolerance).

- [ ] **Step 5: Commit**

```bash
git add tools/mesh_caustic/bvh.py tools/test_mesh_trace.py
git commit -m "Traverse the BVH with brute-force-identical nearest hits"
```

### Task 4: Wire the accelerator into `trace_mesh`

**Files:**
- Modify: `tools/mesh_caustic/trace.py`
- Test: `tools/test_mesh_trace.py` (existing tests must pass unchanged)

**Interfaces:**
- Consumes: `bvh.build`, `bvh.nearest`.
- Produces: `accel` opt (default True); the result dict gains `"accel": bool` so callers and tests can see which path ran; `estimate_seconds` recalibrated from the benchmark.

- [ ] **Step 1: Add a failing integration test**

```python
def test_accel_opt_matches_bruteforce_hits():
    v, f = _sphere()
    sun = [{"type": "sun", "direction": (0.8, 0.42, -0.43)}]
    a = trace_mesh(v, f, sun, _recv(), {"n_side": 40, "eta": 1.5251})
    b = trace_mesh(v, f, sun, _recv(), {"n_side": 40, "eta": 1.5251,
                                       "accel": False})
    assert a["accel"] is True and b["accel"] is False   # RED: key absent
    assert len(a["hits"]) == len(b["hits"])
    assert np.allclose(np.sort(a["hits"], axis=0), np.sort(b["hits"], axis=0),
                       atol=1e-12)
    assert np.allclose(np.sort(a["weights"]), np.sort(b["weights"]), atol=1e-12)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python tools/test_mesh_trace.py`
Expected: FAIL with `KeyError: 'accel'` - the path choice is not observable yet.

- [ ] **Step 3: Wire it**

In `trace_mesh`: build `bv = bvh.build(verts, faces)` once when `opts.get("accel", True)`; thread `bv` (or `None`) into `_shoot`; `_shoot` calls `bvh.nearest(bv, o, d, skip=ie)` for the exit interface and the plain call for the entry. Keep the brute-force branch for `accel=False`.

- [ ] **Step 4: Run the whole file**

Run: `python tools/test_mesh_trace.py`
Expected: all PASS; existing sphere/TIR/dispersion tests unchanged.

- [ ] **Step 5: Commit**

```bash
git add tools/mesh_caustic/trace.py tools/test_mesh_trace.py
git commit -m "Use the BVH in the mesh tracer with a brute-force fallback"
```

### Task 5: Dragon A/B benchmark

**Files:**
- Create: `tools/bench_mesh_trace.py`
- Test: its own assertions, run manually

**Interfaces:**
- Consumes: `trace_mesh` with `accel` on/off; `out/dragon_geo/dragon.obj`.
- Produces: printed table + exit code; asserts hit-set equality and the pre-registered speedup.

- [ ] **Step 1: Write the benchmark**

```python
# tools/bench_mesh_trace.py
# load out/dragon_geo/dragon.obj, sun (0.799481, 0.419727, -0.429721),
# receiver z=-0.2763 patch_half=4.18 center=(-2.95,-2.53)
# t_fast = trace_mesh(..., {"n_side": 256, "accel": True})
# t_slow = trace_mesh(..., {"n_side": 256, "accel": False})
# assert same hit count, same sorted hits (1e-12), same weights (1e-12)
# print build_s, fast_s, slow_s, speedup
# assert speedup >= 5.0
```

- [ ] **Step 2: Run it**

Run: `python tools/bench_mesh_trace.py`
Expected: hit sets identical; `speedup >= 5.0` (pre-registered). If < 5, record the miss and tune once (leaf size / bins), then record the final measured value.

- [ ] **Step 3: Recalibrate `estimate_seconds`**

Replace the `5e-8` model with the measured per-ray cost plus the build term, in `trace.py`, with the calibration run named in the docstring. Re-run `python tools/dragon_suite.py --check` (unchanged) and the addon tests.

- [ ] **Step 4: Commit**

```bash
git add tools/bench_mesh_trace.py tools/mesh_caustic/trace.py
git commit -m "Measure the BVH speedup and recalibrate the bake estimate"
```

### Task 6: Addon, EVIDENCE, docs, commit

**Files:**
- Modify: `blender_addon/caustic_injector.py` (only if the estimate call needs the accel default; no UI change otherwise)
- Modify: `docs/EVIDENCE.md` (append a dated section)
- Modify: `tools/README.md`

- [ ] **Step 1: Run the addon suite**

Run: `python tools/run_blender.py --background --factory-startup --python tools/test_addon_mesh.py`
Expected: `FAILURES: 0 []` (the 16+ checks, including the framed-bake ones, must be unaffected).

- [ ] **Step 2: Record EVIDENCE**

Append a dated section: parity method (2000 random rays, 1e-9), the dragon A/B table (hits, centroid, weights, build_s, fast_s, slow_s, speedup), the new estimate model, and the rejected alternatives (GPU unavailable in Blender's Python; C++ needs a build step and breaks the numpy-only contract). State any criterion miss plainly.

- [ ] **Step 3: Update tools/README.md**

Add `bench_mesh_trace.py` and one sentence: the tracer uses a numpy BVH by default, `accel=False` is the brute-force reference.

- [ ] **Step 4: Commit**

```bash
git add tools/README.md docs/EVIDENCE.md blender_addon/caustic_injector.py
git commit -m "Record the BVH parity and speedup, document the fallback"
```

## Definition of Done

1. `python tools/test_mesh_trace.py` passes, including parity and the tie/skip/degenerate tests.
2. `python tools/bench_mesh_trace.py` prints identical hit sets and `speedup >= 5.0` on the dragon at res 256 (or the achieved value with the miss recorded).
3. `python tools/run_blender.py --background --factory-startup --python tools/test_addon_mesh.py` prints `FAILURES: 0 []`.
4. `estimate_seconds` reflects the measured model; the addon status is honest.
5. EVIDENCE has the dated section; tools/README updated; one commit per task.
