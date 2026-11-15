"""check_directional.py — prove the directional injection term is correct in isolation.

Runs inside Blender:
  python tools/run_blender.py --background --factory-startup \\
      --python tools/check_directional.py

Rig: a 2x2 diffuse plate (albedo 0.5) at z = 0 carrying a synthetic baked
field through the addon's SURFACE injection with directional=True, black
world, no other light.

  1. lambertian_parity: specular 0, ortho top-down, field 0.25/0.05 halves.
     The GGX term is F0 = 0, so the factor is exactly 1 and the plate must
     read 0.2500/0.0500 (within 5%) — directional ON reduces to OFF.
  2. glossy_responds: polished plate (roughness 0.05, F0 0.04), uniform field
     0.15, perspective camera, sun set so the mirror direction hits the plate
     centre. The analytic factor at the centre is ~3200 and ~1 far away, so
     the p99/p10 ratio over the plate must exceed 10.
  3. lambertian_control: same geometry with specular 0 gives p99/p10 < 1.5,
     proving the spike comes from the directional term, not the setup.

Exits non-zero on failure.
"""
import importlib.util
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")
FAILS = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name} {detail}")
    if not ok:
        FAILS.append(name)


def setup(addon):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    os.makedirs(OUT, exist_ok=True)
    spec = importlib.util.spec_from_file_location(
        "caustic_injector", os.path.join(ROOT, addon))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["caustic_injector"] = mod
    spec.loader.exec_module(mod)
    mod.register()
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Strength"].default_value = 0.0
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 64
    sc.cycles.use_denoising = False
    sc.render.filter_size = 0.01
    sc.render.image_settings.file_format = "OPEN_EXR"
    sc.render.image_settings.color_depth = "32"
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.gamma = 1.0
    return sc, mod


def plate(sc, roughness, spec):
    me = bpy.data.meshes.new("Plate")
    me.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [],
                   [(0, 1, 2, 3)])
    me.update()
    uvl = me.uv_layers.new(name="UVMap")
    for lp, uv in zip(me.loops, [(0, 0), (1, 0), (1, 1), (0, 1)]):
        uvl.data[lp.index].uv = uv
    ob = bpy.data.objects.new("Plate", me)
    sc.collection.objects.link(ob)
    m = bpy.data.materials.new("plate")
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (0.5, 0.5, 0.5, 1.0)
    b.inputs["Roughness"].default_value = roughness
    b.inputs["Specular IOR Level"].default_value = spec
    ob.data.materials.append(m)
    return ob


def bake_image(left, right=None):
    N = 64
    img = bpy.data.images.new("CAUSTIC_bake", N, N, alpha=True,
                              float_buffer=True)
    px = np.zeros((N, N, 4), dtype=np.float32)
    if right is None:
        px[:, :, :3] = left / 64.0
    else:
        px[:, : N // 2, :3] = left / 64.0
        px[:, N // 2:, :3] = right / 64.0
    px[..., 3] = 1.0
    img.pixels = px.ravel()
    img.pack()
    return img


def read(path):
    im = bpy.data.images.load(path)
    return np.array(im.pixels[:], dtype=np.float32).reshape(
        im.size[1], im.size[0], 4)[..., :3]


def main():
    sc, _mod = setup("blender_addon/caustic_injector.py")
    p = sc.caustic
    p.mesh_physical_exposure = True

    # --- 1. Lambertian parity ------------------------------------------------
    ob = plate(sc, 1.0, 0.0)
    bake_image(0.25, 0.05)
    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 2.0
    cam = bpy.data.objects.new("cam", cam_data)
    cam.location = (0, 0, 1)
    sc.collection.objects.link(cam)
    sc.camera = cam
    p.target = ob
    p.inject_mode = "SURFACE"
    p.directional = True
    p.gain = 1.0
    p.frame_uv = (0.0, 0.0, 1.0, 1.0)
    assert bpy.ops.caustic.inject() == {"FINISHED"}
    sc.render.resolution_x = 128
    sc.render.resolution_y = 128
    fp = os.path.join(OUT, "_dir_lambert.exr")
    sc.render.filepath = fp
    bpy.ops.render.render(write_still=True)
    a = read(fp)
    left = float(a[48:80, 16:48].mean())
    right = float(a[48:80, 80:112].mean())
    check("lambertian_parity_left", abs(left - 0.25) < 0.0125,
          f"measured {left:.4f} expected 0.2500")
    check("lambertian_parity_right", abs(right - 0.05) < 0.0025,
          f"measured {right:.4f} expected 0.0500")

    # --- 2/3. glossy spike vs Lambertian control -----------------------------
    # L toward the sun: mirror of the centre view ray about +Z.
    # Camera (0,-3,2) -> centre view V = (0, 0.832, 0.555) reversed:
    # V (surface->camera) = (0,-0.832,0.555); mirror needs L = (0,0.832,0.555).
    p.sun_dir = (0.0, -0.832050, -0.554700)  # travel dir; L = -travel
    results = {}
    for tag, rough, spec in (("glossy", 0.05, 0.5), ("control", 0.05, 0.0)):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        sc, _mod = setup("blender_addon/caustic_injector.py")
        ob = plate(sc, rough, spec)
        bake_image(0.15)
        cd = bpy.data.cameras.new("cam")
        c = bpy.data.objects.new("cam", cd)
        c.location = (0, -3, 2)
        d = Vector((0, 0, 0)) - c.location
        c.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        sc.collection.objects.link(c)
        sc.camera = c
        p = sc.caustic
        p.target = ob
        p.inject_mode = "SURFACE"
        p.directional = True
        p.gain = 1.0
        p.frame_uv = (0.0, 0.0, 1.0, 1.0)
        p.sun_dir = (0.0, -0.832050, -0.554700)
        assert bpy.ops.caustic.inject() == {"FINISHED"}
        sc.render.resolution_x = 256
        sc.render.resolution_y = 256
        fp = os.path.join(OUT, f"_dir_{tag}.exr")
        sc.render.filepath = fp
        bpy.ops.render.render(write_still=True)
        a = read(fp).mean(2)
        m0 = a > 0.02
        # 3-px binary erosion without scipy: a pixel survives only if its
        # whole 7x7 neighbourhood is plate (kills AA edge pixels).
        eroded = m0.copy()
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                eroded &= np.roll(np.roll(m0, dy, 0), dx, 1)
        vals = a[eroded]
        # the lobe is a few px wide (peak max ~1100, analytic ~1400); p99
        # dilutes it, so compare the peak against the far-field median.
        peak = float(vals.max())
        far = float(np.median(vals))
        r = peak / max(far, 1e-9)
        results[tag] = r
        print(f"DIR_{tag} peak {peak:.1f} far {far:.4f} ratio {r:.1f} n {len(vals)}")
    # analytic centre factor is ~9000 (D peak 50930, F 0.057, G 1); the pixel
    # footprint averages the lobe down, so >100 is the order-separation bar.
    check("glossy_responds", results["glossy"] > 100.0,
          f"peak/far {results['glossy']:.1f}")
    check("lambertian_control", results["control"] < 1.5,
          f"peak/far {results['control']:.3f}")

    print("FAILURES:", FAILS if FAILS else "0 []")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
