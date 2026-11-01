# Dragon Glass Caustic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove a glass dragon throws a comparable caustic across ours, Cycles, PBRT-SPPM and Mitsuba at locked sun/camera and physical fringe scale.

**Architecture:** Spike first in Blender 5.2 (glass conversion + 720p Cycles-native smoke test via MCP and background renders); only on visible-fan go-ahead, export one shared OBJ and score all engines against an independent mesh tracer with paper tile metrics.

**Tech Stack:** Blender 5.2.3 LTS (Steam), MCP for Blender, Python 3.12 + numpy/scipy/matplotlib/Pillow, PBRT-v4 SPPM, Mitsuba 3, C++17 showcase only if needed.

**Spec:** `docs/superpowers/specs/2026-11-01-dragon-glass-caustic-design.md`

## Global Constraints

- One change per commit; EVIDENCE before paper before summaries.
- No paper text edits in this work; paper gate only after numbers exist with `check_dual_format.py` DUAL-FORMAT OK.
- Physical scale for proofs: canonical 6.77 um, first zero 15.84 um; `airy_scale = 1.5 mm` is 220x display exaggeration; 0.123 mm clips are 18x operational never physical.
- One locked sun + one locked camera for every engine; no per-engine sun/exposure retuning.
- Cycles caustic comparison must set Filter Glossy 0, clamp-indirect 0, max bounces 12 pattern from `tools/blender_scene.py`.
- A miss is recorded in EVIDENCE, never tuned to pass.
- Blender 5.2.3 via `E:\SteamLibrary\steamapps\common\Blender\blender.exe`; addon at `...\Blender\5.2\scripts\addons\blender_mcp.py`; 4.2 copy stays removed.

## Review Focus

- Dragon mesh not watertight so glass refraction leaks and no fan forms; expect closed manifold report with open-edge count 0.
- Single-sided dragon surface without Solidify so transmission path is wrong; expect two-sided closed volume method recorded.
- Plane receiver too small or tilted so fan falls off patch; expect receiver bounds covering the fan in world units.
- Cycles Filter Glossy left on blurring the caustic away; expect settings dump showing blur_glossy 0.0.
- PBRT/Mitsuba geometry mismatch from re-derived instead of exported mesh; expect byte-identical exported OBJ used by every engine.

---

### Task 1: MCP link test

**Files:**
- Modify: none (uses live Blender + installed addon)
- Test: `execute` calls `tools.blender.get_addon_status`, `get_scene_info`, `execute_blender_code`

**Interfaces:**
- Consumes: Steam Blender 5.2 open with MCP server started from sidebar (user action), `models/dragon.blend`.
- Produces: addon version string, scene object list matching background dump (6 objects, dragon 43457 verts) for Task 2 to trust.

- [ ] **Step 1: Start Blender server and query status via MCP**

Run in conversation via `execute`: `tools.blender.get_addon_status({})`
Expected: PASS with Blender 5.2.3, addon version, no connection-refused; on refused, stop and ask user to press Start in the MCP for Blender tab.

- [ ] **Step 2: Query scene info via MCP**

Run: `tools.blender.get_scene_info({limit: 20})`
Expected: PASS listing `dragon` mesh ~43457 verts, `Plane`, `Camera`, 3 lights, 2 materials.

- [ ] **Step 3: Commit nothing (verification only)**

No commit; record outputs in task log for Task 2.

### Task 2: Glass conversion script

**Files:**
- Create: `tools/dragon_glass_setup.py`
- Create: `models/dragon_glass.blend` (generated)
- Test: `C:\Users\Lenovo\AppData\Local\Temp\opencode\dragon_check.py` (inline, not committed)

**Interfaces:**
- Consumes: `models/dragon.blend`, paper defaults `SUN_DIR (0.80, 0.42, -0.43)`, sun angle 2.4 deg, glass IOR 1.525.
- Produces: `models/dragon_glass.blend` with `dragon` = closed glass volume + `SUN` light + `CAM_beauty` (existing framing) + `CAM_measure` (top-down ortho over receiver); `tools/dragon_glass_setup.py --check` prints `MANIFOLD_OK open_edges=0` and receiver bounds.

- [ ] **Step 1: Write failing check**

Create background script that loads `models/dragon_glass.blend`, counts open edges on `dragon`, asserts 0 and glass node `Transmission Weight == 1.0` and one `SUN` light present.
Run: `blender --background models/dragon_glass.blend --python check.py`
Expected: FAIL with file-not-found before the setup script exists.

- [ ] **Step 2: Implement `tools/dragon_glass_setup.py`**

Signature: `python tools/dragon_glass_setup.py --in models/dragon.blend --out models/dragon_glass.blend [--sun 0.80,0.42,-0.43] [--sun-angle 2.4]`
Behavior: load input, report open edges; if open, Solidify 0.0035 m + weld, recalc normals outside; set Principled `Base Color (1,1,1)`, `Roughness 0`, `IOR 1.525`, `Transmission Weight 1.0`; delete 3 Point lights, add one `SUN` with angle; keep `Camera` as `CAM_beauty`, add `CAM_measure` ortho over receiver bounds; save output; print `MANIFOLD_OK open_edges=N verts=43457 receiver=x0,x1,y0,y1`.

- [ ] **Step 3: Run setup and check**

Run: `python tools/dragon_glass_setup.py --in models/dragon.blend --out models/dragon_glass.blend`
Expected: `MANIFOLD_OK open_edges=0` and `models/dragon_glass.blend` exists; then background check from Step 1 PASSES.

- [ ] **Step 4: Commit**

```bash
git add tools/dragon_glass_setup.py models/dragon_glass.blend
git commit -m "Add glass-converted dragon scene with locked sun and cameras"
```

### Task 3: Spike render (go/no-go)

**Files:**
- Create: `out/dragon_spike/cycles_native_720p.png` (generated)
- Create: `out/dragon_spike/settings.txt` (generated, `--dump-settings` pattern)
- Test: visual `look` + settings grep

**Interfaces:**
- Consumes: `models/dragon_glass.blend` from Task 2, Cycles device GPU with CPU fallback.
- Produces: spike PNG plus go/no-go string for Task 5 gate.

- [ ] **Step 1: Render 720p Cycles-native smoke test**

Run: `blender --background models/dragon_glass.blend --python tools/dragon_spike_render.py -- --out out/dragon_spike/cycles_native_720p.png --w 1280 --h 720 --samples 128 --cycles-caustics --no-adaptive --clamp-indirect 0`
Expected: exit 0, PNG exists, render log contains `RENDER_DONE`; script sets `blur_glossy 0.0`, `caustics_reflective True`, `caustics_refractive True`, `max_bounces 12`.

- [ ] **Step 2: Verify settings and visibility**

Run: settings dump to `out/dragon_spike/settings.txt`; grep `blur_glossy 0.0` and `caustics_refractive True`.
Expected: PASS both present; MCP `look` or PNG inspection shows a bright fan on the plane (qualitative; no metric yet).

- [ ] **Step 3: Record go/no-go and commit**

Write `out/dragon_spike/decision.txt` with `GO` plus fan bounds or `NO-GO` plus cause (non-manifold, off-patch, no focus).
Run:
```bash
git add tools/dragon_spike_render.py out/dragon_spike/cycles_native_720p.png out/dragon_spike/settings.txt out/dragon_spike/decision.txt
git commit -m "Add dragon spike render and go-no-go decision"
```
On `NO-GO`, stop; do not start Task 4.

### Task 4: Shared export plus independent tracer

**Files:**
- Create: `tools/dragon_export.py`
- Create: `tools/dragon_trace.py`
- Create: `out/dragon_geo/dragon.obj` (generated)
- Test: `python tools/dragon_trace.py --self-test`

**Interfaces:**
- Consumes: `models/dragon_glass.blend` receiver bounds + sun vector from Task 2.
- Produces: `dragon_trace.load_obj(path) -> (verts, faces)`, `dragon_trace.trace(mesh, n_side, eta) -> hits (N,2)`, `dragon_trace.to_grid(hits, n) -> grid`; `dragon_export.py --out out/dragon_geo` writes `dragon.obj` + `receiver.json` (sun, bounds, patch) used byte-identical by PBRT/Mitsuba/suite.

- [ ] **Step 1: Write failing self-test**

Test asserts ball-lens style focus: trace 300^2 rays through a 35 mm sphere OBJ at paraxial focus concentrates with mean radius < 0.2*f; and `dragon.obj` loads with > 10000 tris.
Run: `python tools/dragon_trace.py --self-test`
Expected: FAIL with files not defined.

- [ ] **Step 2: Implement exporter**

Signature: `python tools/dragon_export.py --blend models/dragon_glass.blend --out out/dragon_geo`
Behavior: background Blender exports `dragon` mesh (applied modifiers, triangulated) to `dragon.obj` with `v` 9-decimal; writes `receiver.json` with sun vector, receiver corners, patch size; prints `dragon.obj verts tris receiver`.

- [ ] **Step 3: Implement tracer**

Moller-Trumbore first-hit, Snell `eta = 1/1.5251`, sun-perpendicular source grid, receiver binning on shared patch; no import from `src/`, no Jacobian.
Run: `python tools/dragon_export.py --blend models/dragon_glass.blend --out out/dragon_geo` then `python tools/dragon_trace.py --self-test`
Expected: PASS self-test plus `dragon.obj` exists.

- [ ] **Step 4: Commit**

```bash
git add tools/dragon_export.py tools/dragon_trace.py
git commit -m "Add shared dragon export and independent mesh tracer"
```

### Task 5: High-res suite (gated on GO)

**Files:**
- Create: `tools/dragon_suite.py`
- Create: `docs/data/dragon_suite.csv` (generated)
- Create: `docs/media/dragon_suite.png` (generated)
- Test: CSV has 4 engine rows plus referee column; figure exists.

**Interfaces:**
- Consumes: `out/dragon_geo/dragon.obj + receiver.json` (Task 4), `models/dragon_glass.blend` cams (Task 2).
- Produces: per-engine PNGs at 2560x1440 beauty (fallback 1920x1080 if > 3 min/frame) + 1024^2 measurement grids; `corr(a, b, n_tiles)` tile-size convention (320/k mm equivalent scaled to receiver); rows `r_40mm, r_5mm, edge_R_G_B, ms_or_s`.

- [ ] **Step 1: Write failing metric check**

Test: `corr` on identical grids returns 1.0; on shifted grids drops; CSV writer writes header `engine,r_40mm,r_5mm,edge_R,edge_G,edge_B,render_s`.
Run: `python tools/dragon_suite.py --check`
Expected: FAIL before implementation.

- [ ] **Step 2: Implement suite runners**

`python tools/dragon_suite.py --engines ours,cycles,pbrt,mitsuba --beauty 2560x1440 --measure 1024` behavior: ours = bake + inject (caustics off); cycles = native (Task 3 settings at high spp 1024, fallback 2048); pbrt = PLY convert + `--sppm` 500k photons radius 0.008; mitsuba = spectral path tracer qualitative; each logs wall time; referee = `dragon_trace` at >= 700^2 (target 1400^2); physical scale only (exaggerated panels are out of scope until this CSV exists).

- [ ] **Step 3: Run suite and inspect**

Run: `python tools/dragon_suite.py --engines ours,cycles,pbrt,mitsuba`
Expected: exit 0, `docs/data/dragon_suite.csv` has 4 rows, `docs/media/dragon_suite.png` exists, no traceback.

- [ ] **Step 4: Commit**

```bash
git add tools/dragon_suite.py docs/data/dragon_suite.csv docs/media/dragon_suite.png
git commit -m "Add dragon high-res suite table and figure at physical scale"
```

### Task 6: EVIDENCE entry and verification

**Files:**
- Modify: `docs/EVIDENCE.md` (append dated section)
- Test: `python tools/check_paper.py`, `python tools/figure_lint.py` on new figure if applicable.

**Interfaces:**
- Consumes: CSV + PNGs + settings + wall times from Tasks 3-5.
- Produces: dated EVIDENCE section with table, commands, go/no-go, negative results; no paper edits.

- [ ] **Step 1: Append EVIDENCE section**

Content: date, sun/cam lock values, res/spp/photon budgets, CSV table verbatim, spike decision, failed engines if any with likely cause and distinguishing experiment.
Run: `python tools/check_paper.py`
Expected: exit 0 (no dangling refs introduced).

- [ ] **Step 2: Commit**

```bash
git add docs/EVIDENCE.md
git commit -m "Record dragon glass-caustic measurements and negative results"
```
