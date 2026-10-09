"""audit_cycles_settings.py — dump the Cycles settings that decide whether
caustics render well, next to Blender's own defaults.

The claim "Cycles under-resolves our caustic" is only interesting if Cycles was
configured correctly. This prints every relevant value so a bad setting is
visible instead of assumed. Particular suspects:

  sample_clamp_indirect  clamps bright indirect samples -> suppresses caustics
                         and biases them low. Default 10.0, i.e. non-zero.
  sample_clamp_direct    same for direct light.
  filter_glossy          blurs glossy paths, which blurs caustics away.
  caustics_reflective/refractive   whether caustic paths are traced at all.
  transmission_bounces   needs >= 4 here: glass wall, water, glass floor, exit.
  use_adaptive_sampling  can stop sampling noisy regions early.
  max_bounces / light_tree / transparent_max_bounces

Run:  blender --background --factory-startup --python tools/audit_cycles_settings.py
"""
import bpy

# Blender's own defaults for these, for comparison
DEFAULTS = {
    "max_bounces": 12,
    "diffuse_bounces": 4,
    "glossy_bounces": 4,
    "transmission_bounces": 12,
    "transparent_max_bounces": 8,
    "volume_bounces": 0,
    "caustics_reflective": True,
    "caustics_refractive": True,
    "filter_glossy": 0.0,
    "sample_clamp_direct": 0.0,
    "sample_clamp_indirect": 10.0,
    "use_adaptive_sampling": True,
    "adaptive_threshold": 0.01,
    "samples": 4096,
    "use_denoising": True,
    "use_light_tree": True,
    "blur_glossy": 0.0,
    "sample_all_lights_directly": True,
    "light_sampling_threshold": 0.05,
}


def report():
    c = bpy.context.scene.cycles
    print(f"{'setting':>30} {'value':>14} {'default':>10}  note")
    print("-" * 78)
    changed = []
    for k, dflt in DEFAULTS.items():
        if not hasattr(c, k):
            print(f"{k:>30} {'ABSENT':>14} {str(dflt):>10}")
            continue
        v = getattr(c, k)
        note = ""
        if isinstance(v, float):
            same = abs(v - dflt) < 1e-9
            vs = f"{v:.4f}"
        else:
            same = v == dflt
            vs = str(v)
        if not same:
            note = "<-- NOT DEFAULT"
            changed.append(k)
        print(f"{k:>30} {vs:>14} {str(dflt):>10}  {note}")
    print()
    print("non-default settings:", changed if changed else "none")
    # scene-level render settings that also matter
    sc = bpy.context.scene
    print()
    print("render.engine               ", sc.render.engine)
    print("view_transform              ", sc.view_settings.view_transform)
    print("use_preview_denoising       ", getattr(sc.render, "use_preview_denoising", "?"))
    print("film_transparent            ", sc.render.film_transparent)
    print("cycles.device               ", c.device)
    print("film.filter_type/width      ", sc.render.filter_type, sc.render.filter_size)
    print("use_fast_gi (world/light)   ", getattr(sc, "cycles", None) and c.use_fast_gi)
    if hasattr(c, "fast_gi_method"):
        print("fast_gi_method              ", c.fast_gi_method)


if __name__ == "__main__":
    report()
