"""test_addon.py — headless proof that the Blender add-on works end to end.

Runs inside Blender:
  blender --background --factory-startup --python tools/test_addon.py

Checks, in order:
  1. the add-on registers
  2. bake runs the solver and produces a real image
  3. inject builds the node graph (image -> x16 -> gain -> emission -> add)
  4. a render WITH the injection differs measurably from one without
  5. remove takes the graph back out
Prints PASS/FAIL lines and exits non-zero on failure.
"""
import importlib.util
import os
import sys

import bpy

ADDON = "D:/ValueProjects/caustics/blender_addon/caustic_injector.py"
OUT = "D:/ValueProjects/caustics/out"
FAILS = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name} {detail}")
    if not ok:
        FAILS.append(name)


# ---- 1. register ----------------------------------------------------------
spec = importlib.util.spec_from_file_location("caustic_injector", ADDON)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.register()
check("register", hasattr(bpy.types.Scene, "caustic"))

# ---- scene: a table plane that will receive the caustic --------------------
# --factory-startup ships a default 2 m cube that ENCLOSES this whole scene:
# nothing inside gets any light and every render comes out black. Start empty.
bpy.ops.wm.read_factory_settings(use_empty=True)

bpy.ops.mesh.primitive_plane_add(size=0.32, location=(0.0, 0.0, 0.0))
plane = bpy.context.active_object
plane.name = "table"
if not plane.data.uv_layers:
    plane.data.uv_layers.new()

sun_data = bpy.data.lights.new("sun", type="SUN")
sun_data.energy = 8.0
sun_data.angle = 0.042
sun = bpy.data.objects.new("sun", sun_data)
bpy.context.collection.objects.link(sun)
import mathutils  # noqa: E402

sun.rotation_mode = "QUATERNION"
sun.rotation_quaternion = mathutils.Vector((0.80, 0.42, -0.43)).to_track_quat("-Z", "Y")

cam_data = bpy.data.cameras.new("cam")
cam_data.lens = 60.0
cam = bpy.data.objects.new("cam", cam_data)
bpy.context.collection.objects.link(cam)
cam.location = (0.24, 0.19, 0.16)
cam.rotation_mode = "QUATERNION"
d = mathutils.Vector((0.0, 0.0, 0.02)) - mathutils.Vector(cam.location)
cam.rotation_quaternion = d.to_track_quat("-Z", "Y")
bpy.context.scene.camera = cam

sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.samples = 32
sc.cycles.caustics_refractive = True
sc.cycles.caustics_reflective = True
sc.render.resolution_x = 480
sc.render.resolution_y = 300
sc.render.image_settings.file_format = "PNG"
sc.view_settings.view_transform = "AgX"

p = sc.caustic
p.target = plane
p.resolution = 256          # small for a fast test
p.gain = 0.5
p.wave_amp = 0.65

# ---- 2. bake --------------------------------------------------------------
res = bpy.ops.caustic.bake()
img = bpy.data.images.get("CAUSTIC_bake")
check("bake", res == {"FINISHED"} and img is not None,
      f"({p.last_ms:.0f} ms, {img.size[0] if img else 0}px)")
if img:
    px = list(img.pixels[:400])
    check("bake_nonzero", max(px) > 0.0, f"max={max(px):.3f}")

# ---- render BEFORE injection ---------------------------------------------
sc.render.filepath = os.path.join(OUT, "addon_before.png")
bpy.ops.render.render(write_still=True)
import numpy as np  # noqa: E402


def load_rgb(path):
    """Blender's bundled Python has no PIL; use Blender's own loader."""
    im = bpy.data.images.load(path, check_existing=False)
    w, h = im.size
    a = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)[:, :, :3]
    bpy.data.images.remove(im)
    return a


before = load_rgb(sc.render.filepath)

# ---- 3. inject ------------------------------------------------------------
res = bpy.ops.caustic.inject()
mat = plane.data.materials[0]
names = [n.name for n in mat.node_tree.nodes]
check("inject", res == {"FINISHED"} and any(n.startswith("CAUSTIC_") for n in names),
      f"({len(names)} nodes)")
check("cycles_caustics_off", sc.cycles.caustics_refractive is False)

# ---- 4. render AFTER injection -------------------------------------------
sc.render.filepath = os.path.join(OUT, "addon_after.png")
bpy.ops.render.render(write_still=True)
after = load_rgb(sc.render.filepath)

diff = np.abs(after - before)
frac = float((diff.max(axis=2) > 0.016).mean())   # Blender pixels are 0..1
check("injection_changes_image", frac > 0.002,
      f"{100*frac:.3f}% of pixels moved, mean |d| = {255*diff.mean():.2f} levels, "
      f"mean luma {255*before.mean():.1f} -> {255*after.mean():.1f}")

# ---- 5. remove ------------------------------------------------------------
res = bpy.ops.caustic.remove()
left = [n.name for n in mat.node_tree.nodes if n.name.startswith("CAUSTIC_")]
check("remove", res == {"FINISHED"} and not left, f"({len(left)} left)")

# ---- write the proof render out for inspection ---------------------------
sc.render.filepath = os.path.join(OUT, "addon_after.png")
print(f"PROOF_DIR {OUT}")
print("FAILS", len(FAILS), FAILS)
sys.exit(1 if FAILS else 0)
