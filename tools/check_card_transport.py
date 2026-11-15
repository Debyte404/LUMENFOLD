"""check_card_transport.py — prove the light card transports a field correctly.

Runs inside Blender:
  python tools/run_blender.py --background --factory-startup \\
      --python tools/check_card_transport.py

Builds a minimal rig instead of the dragon: a 2 x 2 diffuse plate (albedo 0.5)
at z = 0, the addon's CAUSTIC_card 0.5 mm above it, an orthographic camera
looking down, no other light, black world.

The baked field is a plate radiance (irradiance x albedo / pi). For a plate of
albedo a lit by a coplanar card of radiance L, the plate's radiance is L * a,
so the card must emit L = field / a for the plate to reproduce the field. This
script measures that, and checks the card is invisible to camera rays.

Expected, with a field of 0.25 on the left half and 0.05 on the right:
  * plate left  ~ 0.25, plate right ~ 0.05  (within 5% relative)
  * a camera render with the plate hidden is black (no visible card)
Exits non-zero on failure.
"""
import importlib.util
import os
import sys

import bpy
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")
FAILS = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name} {detail}")
    if not ok:
        FAILS.append(name)


def measure(path, win):
    im = bpy.data.images.load(path)
    a = np.array(im.pixels[:], dtype=np.float32).reshape(im.size[1], im.size[0], 4)
    y0, y1, x0, x1 = win
    return float(a[y0:y1, x0:x1, :3].mean())


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    os.makedirs(OUT, exist_ok=True)

    # receiver: 2 x 2 plate, diffuse, albedo 0.5
    me = bpy.data.meshes.new("Plate")
    me.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
    me.update()
    plate = bpy.data.objects.new("Plate", me)
    sc.collection.objects.link(plate)
    mat = bpy.data.materials.new("plate")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.5, 0.5, 0.5, 1.0)
    bsdf.inputs["Roughness"].default_value = 1.0
    bsdf.inputs["Specular IOR Level"].default_value = 0.0
    nt.links.new(nt.nodes["Material Output"].inputs["Surface"], bsdf.outputs["BSDF"])
    plate.data.materials.append(mat)

    # synthetic field: left half 0.25, right half 0.05 of plate radiance.
    # The bake stores the field divided by 64 and the card multiplies it back,
    # so the image carries field/64. Float buffer: 0.05/64 does not survive
    # 8-bit quantisation.
    N = 64
    img = bpy.data.images.new("CAUSTIC_bake", N, N, alpha=True, float_buffer=True)
    px = np.zeros((N, N, 4), dtype=np.float32)
    px[:, : N // 2, :3] = 0.25 / 64.0
    px[:, N // 2:, :3] = 0.05 / 64.0
    px[..., 3] = 1.0
    img.pixels = px.ravel()
    img.pack()

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 2.0
    cam = bpy.data.objects.new("cam", cam_data)
    cam.location = (0, 0, 1)
    sc.collection.objects.link(cam)
    sc.camera = cam

    world = bpy.data.worlds.new("w")
    sc.world = world
    world.use_nodes = True
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Strength"].default_value = 0.0

    spec = importlib.util.spec_from_file_location(
        "caustic_injector", os.path.join(ROOT, "blender_addon", "caustic_injector.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["caustic_injector"] = mod
    spec.loader.exec_module(mod)
    mod.register()

    p = sc.caustic
    p.target = plate
    p.inject_mode = "LIGHT_CARD"
    p.gain = 1.0
    p.mesh_physical_exposure = True
    p.frame_rect = (0.0, 0.0, 1.0)
    res = bpy.ops.caustic.inject()
    card = bpy.data.objects.get("CAUSTIC_card")
    check("card_built", res == {"FINISHED"} and card is not None, str(res))

    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 128
    sc.cycles.use_denoising = False
    sc.render.resolution_x = 128
    sc.render.resolution_y = 128
    sc.render.filter_size = 0.01
    sc.render.image_settings.file_format = "OPEN_EXR"
    sc.render.image_settings.color_depth = "32"
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.gamma = 1.0

    lit = os.path.join(OUT, "_card_transport_lit.exr")
    sc.render.filepath = lit
    bpy.ops.render.render(write_still=True)
    left = measure(lit, (48, 80, 16, 48))
    right = measure(lit, (48, 80, 80, 112))
    check("transports_left_half", abs(left - 0.25) < 0.0125,
          f"measured {left:.4f} expected 0.2500")
    check("transports_right_half", abs(right - 0.05) < 0.0025,
          f"measured {right:.4f} expected 0.0500")

    # camera visibility: with the plate hidden, only the card could show
    plate.hide_render = True
    black = os.path.join(OUT, "_card_transport_black.exr")
    sc.render.filepath = black
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(black)
    a = np.array(im.pixels[:], dtype=np.float32).reshape(128, 128, 4)
    check("card_invisible_to_camera", float(a[..., :3].max()) < 1e-3,
          f"max pixel {float(a[..., :3].max()):.2e}")

    print("FAILURES:", FAILS)
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
