"""dragon_spike_render.py -- 720p Cycles-native smoke test for the glass dragon.

Usage:
  blender --background --python tools/dragon_spike_render.py -- \
      --blend models/dragon_glass.blend --out out/dragon_spike/cycles_native_720p.png \
      --w 1280 --h 720 --samples 128 --cycles-caustics --clamp-indirect 0

Sets paper-grade caustic paths (Filter Glossy 0, max bounces 12) and dumps
settings to <out>.settings.txt alongside the render.
"""
import argparse
import math
import os
import sys

import bpy


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", default="models/dragon_glass.blend")
    ap.add_argument("--out", default="out/dragon_spike/cycles_native_720p.png")
    ap.add_argument("--w", type=int, default=1280)
    ap.add_argument("--h", type=int, default=720)
    ap.add_argument("--samples", type=int, default=128)
    ap.add_argument("--cycles-caustics", action="store_true", default=True)
    ap.add_argument("--no-adaptive", action="store_true", default=True)
    ap.add_argument("--clamp-indirect", type=float, default=0.0)
    ap.add_argument("--camera", default="CAM_beauty")
    return ap.parse_args(argv)


def main():
    args = parse_args()
    bpy.ops.wm.open_mainfile(filepath=args.blend)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = args.samples
    try:
        sc.cycles.use_denoising = True
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception as e:
        print("DENOISE_FALLBACK", e)
    sc.cycles.caustics_reflective = True
    sc.cycles.caustics_refractive = True
    sc.cycles.blur_glossy = 0.0
    sc.cycles.max_bounces = 12
    sc.cycles.diffuse_bounces = 4
    sc.cycles.glossy_bounces = 4
    sc.cycles.transmission_bounces = 12
    sc.cycles.sample_clamp_indirect = args.clamp_indirect
    if args.no_adaptive:
        sc.cycles.use_adaptive_sampling = False
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.refresh_devices()
        prefs.compute_device_type = "OPTIX"
        for d in prefs.devices:
            d.use = (d.type == "OPTIX")
        sc.cycles.device = "GPU"
    except Exception as e:
        print("GPU_FALLBACK_CPU", e)
        sc.cycles.device = "CPU"
    cam = bpy.data.objects.get(args.camera, bpy.context.scene.camera)
    if cam is not None:
        bpy.context.scene.camera = cam
    sc.render.resolution_x = args.w
    sc.render.resolution_y = args.h
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = args.out
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    print(f"RENDER_START samples={args.samples} {args.w}x{args.h} camera={bpy.context.scene.camera.name if bpy.context.scene.camera else None}")
    sys.stdout.flush()
    bpy.ops.render.render(write_still=True)
    print(f"RENDER_DONE {args.out}")
    with open(args.out + ".settings.txt", "w") as f:
        f.write(f"blur_glossy {sc.cycles.blur_glossy}\n")
        f.write(f"caustics_reflective {sc.cycles.caustics_reflective}\n")
        f.write(f"caustics_refractive {sc.cycles.caustics_refractive}\n")
        f.write(f"max_bounces {sc.cycles.max_bounces}\n")
        f.write(f"samples {sc.cycles.samples}\n")
        f.write(f"device {sc.cycles.device}\n")
    print(f"WROTE {args.out}.settings.txt")


if __name__ == "__main__":
    main()
