# Caustic Light Card (Transport Injection) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the injected caustic behave like light instead of a pasted texture: a receiver-sized emissive card that is invisible to camera rays but illuminates the scene, so the table's BSDF shades the caustic and the dragon receives it from below.

**Architecture:** New `inject_mode` (SURFACE / LIGHT_CARD). SURFACE is today's behaviour (emission added to the target's material). LIGHT_CARD creates a plane at the receiver carrying the baked field as an emission shader mixed with Transparent through `Light Path -> Is Camera Ray`, so the card is invisible to the camera but lights the table's diffuse BSDF and the dragon's underside. The table keeps a clean material.

**Tech Stack:** Blender 5.2 Cycles, the existing addon inject path, the baked field image (`CAUSTIC_bake`).

**Spec:** `docs/superpowers/specs/2026-11-14-tracer-optimization-research.md` point 5 (transport); EVIDENCE §31-33 establish that the SURFACE injection is matched in exposure and placement but is not transported light.

## Global Constraints

- The card must be invisible to camera rays (no visible rectangle) while still emitting to diffuse/glossy/transmission rays.
- The table's material must end with no `CAUSTIC_` nodes in LIGHT_CARD mode.
- The card's UVs map the framed bake 1:1 (the card IS the framed rect), so no `frame_uv` remap on the card.
- SURFACE mode is untouched; default `inject_mode` stays SURFACE until the comparison is recorded.
- EVIDENCE before summaries; the beauty comparison must label which panels use the card.

## Review Focus

- **Card visible as a rectangle.** If `Is Camera Ray` is wired backwards, the card shows as a glowing plane. Test: render and assert the card's pixel region matches the background, not the emission.
- **Card z-fighting the table.** At 0.5 mm above the receiver the card may still z-fight or shadow-flicker. Expected: no visible seam at grazing angles.
- **Double lighting.** The card illuminates the table; the table's own diffuse also reflects the world. If the SURFACE emission is left in place too, the caustic is counted twice. Expected: exactly one of the two paths active.
- **Energy scale.** The card's emission is radiance; the table's BSDF multiplies by albedo/pi again, so a physical field would be dimmed twice. Expected: the card path uses the irradiance (not radiance) form, or gain is adjusted and labelled.
- **Card outside the camera frustum.** Fine; Cycles culls it.

---

### Task 1: LIGHT_CARD injection mode

**Files:**
- Modify: `blender_addon/caustic_injector.py`
- Test: `tools/test_addon_mesh.py`

**Interfaces:**
- Consumes: `CAUSTIC_bake` image, `p.frame_rect` (world cx, cy, half), `p.frame_uv`.
- Produces: `mesh_inject_mode` prop ("SURFACE" default, "LIGHT_CARD"); `CAUSTIC_card` object; `caustic.remove` removes the card too.

- [ ] **Step 1: Write the failing test**

```python
def test_light_card_injection():
    # bake, then inject in LIGHT_CARD mode
    # assert: CAUSTIC_card exists, sized to frame_rect, at receiver z + 0.5 mm
    # assert: the table material has no CAUSTIC_ nodes
    # assert: the card material has a Light Path node and an Emission node
    # assert: caustic.remove() deletes the card
```

- [ ] **Step 2: Run to verify it fails**

Run: `python tools/run_blender.py --background --factory-startup --python tools/test_addon_mesh.py`
Expected: FAIL with `KeyError: 'mesh_inject_mode'`.

- [ ] **Step 3: Implement the card**

In `CAUSTIC_OT_inject`: if `p.inject_mode == "LIGHT_CARD"`, build the card from `p.frame_rect` (fallback: the target's bounds), assign an emission material (image x64 x gain) mixed with Transparent through Light Path `Is Camera Ray`, link it to the scene collection, and remove any `CAUSTIC_` nodes from the target's materials. `caustic.remove` deletes `CAUSTIC_card`.

- [ ] **Step 4: Run the suite**

Run: `python tools/run_blender.py --background --factory-startup --python tools/test_addon_mesh.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add blender_addon/caustic_injector.py tools/test_addon_mesh.py
git commit -m "Add a light-card injection mode that transports the caustic"
```

### Task 2: Render comparison

**Files:**
- Modify: `tools/dragon_addon_beauty.py` (`--inject-mode`)
- Output: `out/dragon_suite/addon_ours_2560_card.png`

- [ ] **Step 1: Render the card panel at the shipped settings**

Same bake (1024^2 x2, BVHTREE, achromatic, 6.77 um airy, sun blur), inject LIGHT_CARD, render 2560x1440/1024spp.

- [ ] **Step 2: Measure against Cycles**

Bright-region RGB and centroid in the fan window; the card must be invisible to the camera (no rectangle) and the caustic must shade the table (cosine falloff visible at the shadow edge).

- [ ] **Step 3: Record in EVIDENCE**

A dated section with the measured comparison and which mode the shipped figure uses.

- [ ] **Step 4: Commit**

```bash
git add tools/dragon_addon_beauty.py docs/EVIDENCE.md
git commit -m "Record the light-card transport comparison"
```
