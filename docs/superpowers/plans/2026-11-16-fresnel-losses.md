# Missing Fresnel Losses Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> (inline execution). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Apply exact unpolarized Fresnel transmittance at both refractive
interfaces in the tracer. The exposure arbiter (EVIDENCE 43 + smooth-scene
re-runs) shows Cycles' fan integral flat across 4x spp while our injected fan
is +13% brighter post-free; the tracer transmits weight 1.0 at every
non-TIR interface, but real glass (and Cycles) loses ~4% per interface. The
paper already records 96.4% interface throughput, so the bake contradicts the
paper's own number.

**Physics:** Per ray, weight *= T1 * T2 with T = 1 - R, R the unpolarized
Fresnel reflectance (Born & Wolf) from the same cosi/eta the Snell step uses.
TIR already drops the ray (T = 0 implicitly). No tuning scalar; the factor is
exact for unpolarized light at dielectric interfaces.

## Global Constraints

- Both refract paths change together: numpy `_shoot` (reference) and the
  addon's `_make_bvh_shooter` (production). The numpy/BVHTree parity check must
  stay green.
- Return contract change `(x, y, L)` -> `(x, y, L, T)` is contained: the only
  consumer is `shoot_all` inside `trace_mesh`. Verify by grep before and after.
- No behaviour change when T == 1 (vacuum eta 1.0 both sides): existing tests
  must pass unmodified.
- EVIDENCE before summaries; no paper claim changes (the paper already states
  96.4% throughput -- the bake is being brought into agreement with it).

---

### Task 1: Fresnel factor in both shooters + unit test

**Files:**
- Modify: `tools/mesh_caustic/trace.py` (`_fresnel_T`, `_shoot`, `shoot_all`),
  `blender_addon/caustic_injector.py` (`_make_bvh_shooter.shoot`),
  `tools/test_addon_mesh.py` (unit check).
- Test: `python tools/run_blender.py --background --factory-startup --python tools/test_addon_mesh.py`

- [ ] **Step 1: Write the failing test** -- `fresnel_normal_incidence`
  (T = 0.9568 at eta 1.5251) and `fresnel_brewster` (Rp = 0 at tan = eta).
  Run suite, verify they FAIL with missing helper.
- [ ] **Step 2: Implement** -- `_fresnel_T(cosi, eta)` clamped [0,1] with an
  explicit TIR guard; thread T1*T2 into both shooters' weights.
- [ ] **Step 3: Run the suite** -- expect `FAILURES: 0 []` plus the new PASS
  lines, including the numpy/BVHTree parity check.
- [ ] **Step 4: Commit** -- tracer + addon + test only.

### Task 2: Re-bake the dragon and measure against Cycles

**Files:** none (driver unchanged).
**Output:** `out/dragon_suite/addon_ours_2560_fresnel.png` (ignored by git).

- [ ] **Step 1: Bake + render at the shipped settings** (1024^2 x4,
  achromatic, physical, 2048 spp, post-free to match `cycles_fresh`).
- [ ] **Step 2: Measure the fan** (same window as section 43). Expect the fan
  mean to drop ~8-10% toward Cycles' 0.634. If it lands within a few percent,
  the exposure question is closed; if not, record the residual plainly and do
  NOT tune -- the origin-offset (`-0.5*d`) inside-mesh starts are the named
  next suspect, as a separate change.
- [ ] **Step 3: Record in EVIDENCE** (new section), update the presentation
  sheet only if the gap closes.
- [ ] **Step 4: Commit** -- EVIDENCE (+ media only if regenerated).
