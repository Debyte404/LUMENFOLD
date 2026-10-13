# Blender add-on: Wave Caustic Injector

`blender_addon/caustic_injector.py` installs as a Blender add-on, bakes the
wave-corrected caustic with this repository's solver, injects it into a Cycles
material as light, and can give the glass and water a coloured medium.

**Why it exists.** Cycles discovers caustics by random path tracing, so they are the
noisiest thing in a glass render, and they get worse as the source shrinks. This
bakes the caustic deterministically — fold locus, Airy profile, band-local flux
conservation, per channel — in a few hundred milliseconds, then injects it as light.
The result is noise-free at any sample count, stays finite at the fold where ray
tracing diverges, and carries per-channel dispersion.

---

## Install

1. `Edit > Preferences > Add-ons > Install from Disk…`
2. Pick `blender_addon/caustic_injector.py` from this repository.
3. Enable **Wave Caustic Injector** (category: Render).
4. Open the 3D View sidebar with `N` and find the **Caustic** tab.

Requires Blender 3.6+ and a built `showcase.exe` (`cmake --build build --config Release`).
The **Solver** field defaults to `build/src/app/Release/showcase.exe` relative to the
repository; point it elsewhere if you moved the build.

---

## Quick start

The everyday path is three buttons:

1. Set **Target** to the object that receives the caustic (the table).
2. **Bake caustic** — runs the solver, dumps the field, reports the bake time.
3. **Inject into material** — builds the emission chain on the target's material.
4. Render.

**Remove injection** takes the node graph back out. **Toggle Cycles caustics** flips
Cycles' own refractive/reflective caustics by hand.

The scene must satisfy the contract at the bottom of this page, or the injected
caustic will be in the wrong place. `tools/blender_scene.py` is a working reference.

---

## Controls

### Solver and bake

| control | meaning |
|---|---|
| Solver | path to `showcase.exe` |
| Resolution | caustic bake grid; 1024 is the calibrated default |
| Airy scale | fringe width near the fold. A documented *visibility* parameter that needs ≥3 px per fringe to resolve — **not** a physical prediction |
| Ripple amplitude | water-surface ripple in mm; 0 gives the smooth cylindrical fan |
| Ripple phase | phase of the ripple field; animate this for a moving caustic |
| Target | object that receives the caustic; its UVs must span the solver's patch |
| Injection gain | brightness of the injected caustic |
| Disable Cycles caustics | switches off Cycles' own refractive/reflective caustics so ours is the only one — that is the point of the add-on |

### Coloured medium

These are **experiment parameters, not measured materials.** Cobalt glass is
`(300, 30, 8)`; whether a tint "looks right" is a choice, not a datum.

| control | meaning |
|---|---|
| Glass absorb | Beer–Lambert per metre, R,G,B, through the ~3.5 mm glass wall |
| Water absorb | Beer–Lambert per metre, R,G,B, through the ~90 mm of water |
| Medium objects | whose materials get the volume tint — run once per object |

Buttons: **Tint this object's medium** and **Remove medium tint**.

The defaults give a visible red in each: `(30, 344, 721)` for glass, `(1.17, 21.0, 38.9)`
for water. Mind the path lengths — the glass path is only ~3.5 mm and the water
~90 mm, so a coefficient that seems small for water is large for glass. To transmit
`T` over a path `L`, use `mu = -ln(T)/L`.

---

## Colouring a scene: it has to be done twice

The pipeline is **bake → render**, and the two stages carry different halves of the
light. Setting only one gives a result that looks like the medium "barely works":

* **The bake tints the caustic.** `Glass absorb` / `Water absorb` are passed to the
  solver as `--glass-abs` / `--water-abs`. A caustic is a *light-side* quantity: its
  colour is set by what the sunlight crossed before landing, so this is the only
  stage that can tint it.
* **The volume tint colours the medium's own body.** **Tint this object's medium**
  adds a Volume Absorption node to that object's materials, so the glass and water
  look like glass and water rather than clear.

Set only the first and you get a red caustic inside a colourless glass. Set only the
second and you get a red glass with a neutral caustic. Set both, per medium.

### The setting that silently disables the whole thing

`scene.cycles.volume_bounces` **defaults to 0**, and at 0 Cycles *ignores a connected
volume shader entirely* — the absorption is built into the material, is never
integrated, and the medium renders colourless with **no warning anywhere in the log**.
Four isolation renders came back pixel-identical before this was tracked down; that
signature — a knob with no effect at all — is what to watch for.

**Tint this object's medium** raises it to 8 for you if it is below 1, and reports the
value it set. If you wire volumes yourself, set it yourself.

Two further traps worth knowing:

* A `NodeSocketShader` has **no** `default_value`. Assigning to one raises. To clear a
  volume, remove the *link*.
* Blender resolves a **relative** path against the drive root, not the working
  directory, so a relative `--out` lands in `C:\out\...`. Every path in the add-on and
  its harnesses is absolute.

---

## What the node graph looks like

Caustic injection, on the target's material:

```
UV Map ─▶ Image Texture (Non-Color) ─▶ ×16 ─▶ ×gain ─▶ Emission ─┐
                                                                 ├─▶ Add Shader ─▶ Output
Principled BSDF ─────────────────────────────────────────────────┘
```

The `×16` undoes the 16-bit export scaling (the field is linear with a display cap of
8.1, written as `value/16` in a 16-bit PNG). The multiply is done with a `Mix` node in
RGBA mode: a `Math` node fed from a colour socket silently collapses to one channel,
which would throw away the per-channel dispersion the bake carries.

Medium tint, on the glass and water materials:

```
Volume Absorption (Color = 1 − mu/max(mu), Density = max(mu)) ─▶ Output.Volume
```

Blender attenuates as `exp(-Density*(1-Color)*L)`, so a per-channel `mu` is expressed
with `Density = max(mu)` and `Color = 1 - mu/max(mu)`. Both nodes are named with a
`MEDIUM_` prefix so **Remove medium tint** can find them.

---

## Verification

Two headless harnesses, both of which run without a GUI:

```bash
# the caustic injection end to end: register, bake, inject, remove
"C:/Program Files/Blender Foundation/Blender 4.2/blender.exe" \
  --background --factory-startup --python tools/test_addon.py

# the coloured-medium path: node built, node LINKED, volume_bounces raised
"C:/Program Files/Blender Foundation/Blender 4.2/blender.exe" \
  --background --factory-startup --python tools/addon_bringup.py
```

`test_addon.py` output:

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

`addon_bringup.py` output:

```
PASS  Cycles really does default volume_bounces to 0 (the silent trap)
PASS  add-on registered; Scene.caustic exists
PASS  glass_absorb defaults present
PASS  water_absorb defaults present
PASS  tint_medium ran
PASS  exactly one MEDIUM_ volume node created
PASS  volume node is LINKED to the output (a built-but-unlinked node is the bug)
PASS  Density == max(mu) (got 721.0)
PASS  recovered mu round-trips: ['30.0', '344.0', '721.0']
PASS  volume_bounces raised off 0 (now 8)
PASS  re-running replaces rather than stacking
PASS  untint removes the volume node
FAILURES: 0
```

The checks that matter are the *linked* one and the *bounces* one. A node that is
built but not linked, and a volume that is linked but never integrated, are both
invisible in the render and in the log — they are the two ways this feature fails
silently.

---

## Measured: our injection vs Cycles' own caustics

`tools/caustic_vs_cycles.py` renders the same scene twice — once letting Cycles
path-trace the caustics, once with our caustic injected and Cycles' caustics off — at
64 and 256 samples with the denoiser **off** (the denoiser otherwise hides exactly the
noise being measured). Each mode's 256-sample render is its own converged reference,
so the RMSE between them is that mode's Monte-Carlo noise.

Physical 2.4° sun, 640×400:

| | Cycles native | ours injected |
|---|---|---|
| RMSE, whole frame | 7.67 | **2.29** (3.3× quieter) |
| RMSE, caustic region | 1.50 | **1.42** (1.1× quieter) |
| render time @256 | 2.2 s | 2.1 s |
| bake cost | — | **0.27 s, once** |

**Read this honestly.** The whole-frame noise drops 3.3×, because the injected caustic
is deterministic and adds zero variance. But in the *caustic region* the two are nearly
tied (1.1×). At a physical sun size, light reaching the table through the glass is
dominated by direct transmission, which Cycles samples easily; the concentrated caustic
carries only a small share of the energy here. The advantage should grow as the caustic
carries more of the image and the source gets smaller (laser, small lamp), and it is
unlimited in *accuracy*, but at these settings this is a modest win, not an
order-of-magnitude one. The hard regime is an open experiment, not a claim.

## Where the real advantage is

* **Accuracy at the fold.** Geometric caustics diverge where `det J → 0` (100×+ spikes);
  the wave-corrected field stays bounded (peak 7.7×, cap 8.10). Note the band-local
  flux ratio is circular by construction — see CRITIQUE C5.
* **Dispersion for free.** Per-channel ray maps give real chromatic splitting, where
  geometric splatting needs separate runs.
* **Deterministic.** Same input → same caustic, at any sample count.

---

## Scene contract

The injected texture is only correct if the Blender scene matches the solver's
geometry, because the caustic is *precomputed*, not solved in-scene:

* table at `z = 0`, patch spanning `[-0.16, +0.16] m` in x and y
* glass: outer radius 0.035 m, height 0.090 m, centred on the origin
* water line at `z = 0.0594 m`
* sun direction `(0.80, 0.42, -0.43)` (direction light travels), index-matched
* target UVs spanning 0…1 across that patch

`tools/blender_scene.py` builds a scene satisfying this contract and is the reference
for what "matching" means.

---

## Troubleshooting

| symptom | cause |
|---|---|
| Caustic in the wrong place | scene does not match the contract above, or the target's UVs do not span the patch |
| Nothing appears after Inject | wrong Target object, or Injection gain is 0 |
| Medium has no colour at all | `volume_bounces` is 0 — Cycles is ignoring the volume shader. Use **Tint this object's medium**, which sets it |
| Medium thin/absent in one material only | the volume is on one object but not the other; run **Tint** once per object |
| Fringes invisible | Airy scale below ~3 px per fringe at the bake resolution |
| Solver not found | rebuild, or point **Solver** at the right `showcase.exe` |
| Bake fails | run `showcase.exe` by hand with the same flags; the add-on prints the solver's last lines on failure |
