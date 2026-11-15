# Caustic Directional Response Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans (inline execution). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Give the injected caustic a correct directional response on glossy receivers, so the caustic appears at the right reflection angles instead of glowing view-independently. For a Lambertian receiver the result must be bit-identical to today's surface injection.

**Physics:** The baked field F is a receiver-space plate radiance `F = E_c * a / pi` (E_c = caustic irradiance, a = receiver albedo). For a general BRDF the outgoing radiance toward V is `L(V) = E_c * (a/pi + f_s(V, L_sun)) = F * (1 + (pi/a) * f_s)`. f_s is the specular part (GGX D * Fresnel-Schlick F * Smith G / (4 (N.V)(N.L))). The sun direction L_sun comes from the scene SUN lamp, falling back to `p.sun_dir`. This is a closed-form evaluation of the rendering equation for a small angular source, not a fitted gain — exact and noise-free.

**Scope:** SURFACE injection path only (`_emit_into_material`). LIGHT_CARD untouched. New bool prop `directional` (default False); driver flag `--directional`. OFF = today's graph, unchanged.

## Global Constraints

- OFF path is byte-identical in node graph to today (same node names/labels/counts) so all existing checks pass unchanged.
- ON path with a Lambertian receiver (Specular IOR Level = 0, or Roughness = 1 with F0 = 0) must reproduce the OFF plate value within render tolerance (proves reduction to surface injection).
- ON path reads the receiver's Base Color, Roughness, Specular IOR Level from its first Principled BSDF; textured inputs use the socket default and the limit is documented.
- No new third-party dependency. Pure Blender shader nodes + existing numpy tooling.
- EVIDENCE before summaries; no paper claim until measured.

## Review Focus

- **Double counting:** renderer caustics must stay disabled for injected frames (existing `disable_cycles_caustics` path). The directional term does not re-enable them.
- **Division by zero:** albedo floor 0.02 (as in the card gain), NdotV/NdotL clamped >= 1e-3, roughness floored (alpha = max(r^2, 1e-3)) so GGX stays finite.
- **Vector spaces:** Geometry Normal/Incoming are world-space; sun direction converted once on CPU to a constant vector input.
- **Node removal:** every new node is named/labelled `CAUSTIC_*`; `caustic.remove` and re-inject stay idempotent.

---

### Task 1: `directional` prop + sun-direction helper + GGX term builder (no behaviour change when OFF)

**Files:**
- Modify: `blender_addon/caustic_injector.py`
- Test: `tools/test_addon_mesh.py`

**Interfaces:**
- Consumes: receiver Principled inputs, scene SUN lamp or `p.sun_dir`, baked-field socket.
- Produces: `_sun_light_dir(scene, fallback)` and `_directional_factor(nt, ...)` returning a scalar socket; `_emit_into_material(..., directional=False)`.

- [x] **Step 1: Write the failing test** — `directional_off_graph_unchanged` (OFF build has exactly today's CAUSTIC node set) and `directional_lambertian_reduces` (ON build on a Lambertian receiver carries a unity factor path). Run suite, verify they FAIL with missing prop/helper. (Done: failed as specified.)
- [x] **Step 2: Implement** — `directional` BoolProperty, `_sun_light_dir()`, GGX chain (H = normalize(L+V), NdotX clamps, D/F/G math, factor = 1 + (pi/a)*f_s per channel via separate-XYZ/combine or three scalar chains), wire factor into the emission colour (field * gain * factor) when ON.
- [x] **Step 3: Run the suite** — `python tools/run_blender.py --background --factory-startup --python tools/test_addon_mesh.py`, expect `FAILURES: 0 []` plus the two new PASS lines. (Done: green.)
- [x] **Step 4: Commit** — injector + test only. (Done: b564448.)

### Task 2: Isolated render proof (Lambertian unchanged, glossy responds)

**Files:**
- Modify: `tools/check_card_transport.py` (or new `tools/check_directional.py` if cleaner)
- Output: `out/_directional_*.exr` (ignored by git)

- [x] **Step 1: Lambertian parity render** — same 0.25/0.05 plate, Principled specular 0, directional ON: measures 0.2500/0.0500 within 5%. (Done: exact.)
- [x] **Step 2: Glossy response render** — polished plate (roughness ~0.05): peak/far 7345x at the mirror direction (analytic ~9000); specular-0 control 1.008. (Done: peak/max replaced the planned halves-contrast once the maps showed a narrow lobe.)
- [x] **Step 3: Commit** — check script + EVIDENCE section. (Done: 8c0c4d6; EVIDENCE section lands with Task 3.)

### Task 3: Glossy-table dragon comparison vs Cycles

**Files:**
- Modify: `tools/dragon_addon_beauty.py` (`--directional`)
- Output: `out/dragon_suite/addon_ours_2560_directional.png` (ignored by git)

- [ ] **Step 1: Render** — polished-table rig (separate .blend or same scene with lowered table roughness, labelled as such), directional ON, same bake settings.
- [ ] **Step 2: Measure vs Cycles** — caustic core RGB/centroid + glass response; record win/loss plainly.
- [ ] **Step 3: Record in EVIDENCE**, update `docs/paper/sections/ourway.tex` coupling sentence + both frontmatters if any claim changes, run `check_dual_format.py`, `check_paper.py`, `build_paper_pdf`.
- [ ] **Step 4: Commit** — driver + EVIDENCE (+ paper if touched).
