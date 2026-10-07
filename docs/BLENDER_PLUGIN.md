# Blender plug-in: Wave Caustic Injector

`blender_addon/caustic_injector.py` — installs into Blender as an add-on, bakes
the wave-corrected caustic with this repo's solver, and injects it into a Cycles
material as light.

## Install

1. Blender → `Edit > Preferences > Add-ons > Install from Disk…`
2. Pick `D:/ValueProjects/caustics/blender_addon/caustic_injector.py`
3. Enable **Wave Caustic Injector** (Render category).

## Use

Open the 3D View sidebar (`N`) → **Caustic** tab:

| control | meaning |
|---|---|
| Solver | path to `showcase.exe` (defaults to `build/src/app/Release/showcase.exe`) |
| Resolution | caustic bake grid, 1024 is the calibrated default |
| Airy scale | fringe width near the fold. Documented *visibility* parameter (needs ≥3 px per fringe), not a physical prediction |
| Ripple amplitude | water-surface ripple in mm; 0 reproduces the smooth cylindrical fan |
| Target | the object that receives the caustic (the table). Its UVs must span the solver's patch |
| Injection gain | brightness of the injected caustic |
| Disable Cycles caustics | switches off Cycles' own refractive/reflective caustics so ours is the only one |

Buttons: **Bake caustic** → **Inject into material** → render. **Remove injection**
takes the node graph back out; **Toggle Cycles caustics** flips the toggles by hand.

The node graph it builds:

```
UV Map ─▶ Image Texture (Non-Color) ─▶ ×16 ─▶ ×gain ─▶ Emission ─┐
                                                                 ├─▶ Add Shader ─▶ Output
Principled BSDF ─────────────────────────────────────────────────┘
```

The `×16` undoes the 16-bit export scaling (the baked field is linear with a
display cap of 8.1, written as `value/16` in a 16-bit PNG).

## Verification

`tools/test_addon.py` proves the add-on works, headless:

```
"C:/Program Files/Blender Foundation/Blender 4.2/blender.exe" \
  --background --factory-startup --python tools/test_addon.py
```

```
PASS register
PASS bake (272 ms, 256px)
PASS bake_nonzero max=1.000
PASS inject (8 nodes)
PASS cycles_caustics_off
PASS injection_changes_image 65.512% of pixels moved, mean |d| = 18.65 levels,
                              mean luma 144.9 -> 163.6
PASS remove (0 left)
FAILS 0 []
```

## Measured: our injection vs Cycles' own caustics

`tools/caustic_vs_cycles.py` renders the same scene twice — once letting Cycles
path-trace the caustics, once with our caustic injected and Cycles' caustics off —
at 64 and 256 samples with the denoiser **off** (the denoiser otherwise hides
exactly the noise being measured). Each mode's 256-sample render is its own
converged reference, so the RMSE between them is that mode's Monte-Carlo noise.

Physical 2.4° sun, 640×400:

| | Cycles native | ours injected |
|---|---|---|
| RMSE, whole frame | 7.67 | **2.29** (3.3× quieter) |
| RMSE, caustic region | 1.50 | **1.42** (1.1× quieter) |
| render time @256 | 2.2 s | 2.1 s |
| bake cost | — | **0.27 s, once** |

**Read this honestly.** The whole-frame noise drops 3.3×, because the injected
caustic is deterministic and adds zero variance. But in the *caustic region* the
two are nearly tied (1.1×). At a physical sun size, light reaching the table
through the glass is dominated by direct transmission, which Cycles samples
easily; the concentrated caustic carries only a small share of the energy here.
The advantage should grow as the caustic carries more of the image and the source
gets smaller (laser, small lamp), and it is unlimited in *accuracy* — see below —
but at these settings this is a modest win, not an order-of-magnitude one.
Testing the hard regime (small source, caustic-dominated frame) is listed as an
open experiment, not a claim.

## Where the real advantage is (already measured elsewhere)

* **Accuracy at the fold.** Geometric caustics diverge where `det J → 0`
  (100×+ spikes, clamped to a 350× artefact before the fix); the wave-corrected
  field stays bounded (peak 7.7×, cap 8.10) with flux conserved to 1.0000.
* **Dispersion for free.** Per-channel ray maps give real chromatic splitting
  (31% of the field mean in the wavy model), where geometric splatting needs
  separate runs.
* **Deterministic.** Same input → same caustic, every time, at any sample count.

## Scene contract

The injected texture is only correct if the Blender scene matches the solver's
geometry, because the caustic is *precomputed*, not solved in-scene:

* table at `z = 0`, patch spanning `[-0.16, +0.16] m` in x and y
* glass: outer radius 0.035 m, height 0.090 m, centred on the origin
* sun direction `(0.80, 0.42, -0.43)` (direction light travels), index-matched
* target UVs spanning 0…1 across that patch

`tools/blender_scene.py` builds a scene satisfying this contract and is the
reference for what "matching" means.
