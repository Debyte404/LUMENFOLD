"""dragon_addon_beauty.py -- reproducible ours-injected dragon panel.

Drives the addon's any-mesh Bake end to end on models/dragon_glass.blend:
bake the dragon, inject into the receiver plane (Cycles caustics off), render
CAM_beauty with the paper-grade settings from tools/dragon_spike_render.py.
Writes a JSON sidecar with the measured numbers so EVIDENCE can quote them.

Usage (Steam Blender 5.2):
  blender --background --factory-startup --python tools/dragon_addon_beauty.py -- \
      --res 1024 --ray-mult 1 --frame AUTO --w 2560 --h 1440 --samples 1024 \
      --out out/dragon_suite/addon_ours_2560_framed.png
"""
import argparse
import importlib.util
import json
import os
import sys
import time

import bpy

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "tools"))

ADDON = os.path.join(_ROOT, "blender_addon", "caustic_injector.py")
BLEND = os.path.join(_ROOT, "models", "dragon_glass.blend")


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", default=BLEND)
    ap.add_argument("--res", type=int, default=1024)
    ap.add_argument("--ray-mult", type=int, default=1)
    ap.add_argument("--frame", default="AUTO", choices=["AUTO", "FULL"])
    ap.add_argument("--accel", default="BVHTREE", choices=["BVHTREE", "NUMPY"])
    ap.add_argument("--margin", type=float, default=0.15)
    ap.add_argument("--airy", type=float, default=0.006)
    ap.add_argument("--gain", type=float, default=0.25)
    ap.add_argument("--w", type=int, default=2560)
    ap.add_argument("--h", type=int, default=1440)
    ap.add_argument("--samples", type=int, default=1024)
    ap.add_argument("--out", default=os.path.join(
        _ROOT, "out", "dragon_suite", "addon_ours_2560_framed.png"))
    return ap.parse_args(argv)


def load_addon():
    spec = importlib.util.spec_from_file_location("caustic_injector", ADDON)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.register()
    return mod


def main():
    a = parse_args()
    a.out = os.path.abspath(a.out)  # Blender resolves relative render paths
    # against the .blend's directory, not the process CWD
    bpy.ops.wm.open_mainfile(filepath=a.blend)
    mod = load_addon()
    p = bpy.context.scene.caustic
    p.bake_source = "MESH"
    p.mesh_object = bpy.data.objects["dragon"]
    p.target = bpy.data.objects["Plane"]
    p.mesh_resolution = a.res
    p.mesh_airy = a.airy
    p.gain = a.gain
    p.glass_absorb = (0.0, 0.0, 0.0)  # neutral medium, per EVIDENCE 25
    if hasattr(p, "mesh_ray_mult"):
        p.mesh_ray_mult = a.ray_mult
    if hasattr(p, "mesh_frame"):
        p.mesh_frame = a.frame
        p.mesh_frame_margin = a.margin
    if hasattr(p, "mesh_accel"):
        p.mesh_accel = a.accel

    t0 = time.time()
    r = bpy.ops.caustic.bake_mesh()
    if r != {"FINISHED"}:
        raise SystemExit(f"bake failed: {p.status}")
    bake_s = time.time() - t0
    print("BAKE_STATUS", p.status)

    t1 = time.time()
    if bpy.ops.caustic.inject() != {"FINISHED"}:
        raise SystemExit("inject failed")
    inject_s = time.time() - t1

    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.render.resolution_x = a.w
    sc.render.resolution_y = a.h
    sc.cycles.samples = a.samples
    try:
        sc.cycles.use_denoising = True
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception as e:
        print("DENOISE_FALLBACK", e)
    sc.cycles.blur_glossy = 0.0
    sc.cycles.max_bounces = 12
    sc.cycles.diffuse_bounces = 4
    sc.cycles.glossy_bounces = 4
    sc.cycles.transmission_bounces = 12
    sc.cycles.sample_clamp_indirect = 0.0
    sc.cycles.use_adaptive_sampling = False
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.refresh_devices()
        prefs.compute_device_type = "OPTIX"
        for d in prefs.devices:
            d.use = True
        sc.cycles.device = "GPU"
    except Exception as e:
        print("DEVICE_FALLBACK", e)
    sc.camera = bpy.data.objects["CAM_beauty"]
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    sc.render.filepath = a.out
    t2 = time.time()
    bpy.ops.render.render(write_still=True)
    render_s = time.time() - t2

    sidecar = os.path.splitext(a.out)[0] + "_metrics.json"
    metrics = {
        "res": a.res, "ray_mult": a.ray_mult, "frame": a.frame,
        "airy": a.airy, "gain": a.gain, "samples": a.samples,
        "out_size": [a.w, a.h], "bake_s": round(bake_s, 1),
        "inject_s": round(inject_s, 1), "render_s": round(render_s, 1),
        "status": p.status,
        "frame_uv": list(p.frame_uv) if hasattr(p, "frame_uv") else None,
        "frame_rect": list(p.frame_rect) if hasattr(p, "frame_rect") else None,
    }
    with open(sidecar, "w") as f:
        json.dump(metrics, f, indent=2)
    print("DRIVER_OK", json.dumps(metrics))


if __name__ == "__main__":
    main()
