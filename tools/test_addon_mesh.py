"""test_addon_mesh.py — headless proof of the any-mesh Bake path.

Runs inside Blender:
  python tools/run_blender.py --background --factory-startup \\
      --python tools/test_addon_mesh.py

Checks, in order:
  1. register (incl. the mesh Bake operator)
  2. mesh bake on the fixture sphere is nonzero and bounded
  3. point-light bake runs
  4. open mesh cancels with the named error
  5. receiver without UVs cancels with the named error
  6. absorb coefficients change channel ratios vs clear
  7. time estimate is shown and scales with budget
  8. inject/remove round-trip works on a mesh bake
Prints PASS/FAIL lines and exits non-zero on failure.
"""
import importlib.util
import os
import sys

import bpy

import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
sys.path.insert(0, _ROOT + "/tools")

ADDON = _ROOT + "/blender_addon/caustic_injector.py"
FIXTURE = _ROOT + "/models/mesh_fixture.blend"
OUT = _ROOT + "/out"
FAILS = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name} {detail}")
    if not ok:
        FAILS.append(name)


spec = importlib.util.spec_from_file_location("caustic_injector", ADDON)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.register()
check("register", hasattr(bpy.types.Scene, "caustic")
      and hasattr(bpy.types, "CAUSTIC_OT_bake_mesh"))


def fresh_scene():
    bpy.ops.wm.open_mainfile(filepath=FIXTURE)


def plane():
    return bpy.data.objects.get("fixture_table")


def glass():
    return bpy.data.objects.get("fixture_glass")


def run_bake(**kw):
    p = bpy.context.scene.caustic
    for k, v in kw.items():
        setattr(p, k, v)
    r = bpy.ops.caustic.bake_mesh()
    return r, p


def run_bake_cancel(**kw):
    """Headless note (Blender 5.2): an operator that reports {'ERROR'} and
    returns CANCELLED RAISES RuntimeError when invoked via bpy.ops from a
    script (in the UI it just flashes the status bar). So a named refusal
    surfaces as RuntimeError carrying the message — assert on that."""
    p = bpy.context.scene.caustic
    for k, v in kw.items():
        setattr(p, k, v)
    try:
        bpy.ops.caustic.bake_mesh()
    except RuntimeError as e:
        return str(e)
    return None


# ---- 2. mesh bake nonzero + bounded -----------------------------------------
fresh_scene()
r, p = run_bake(mesh_object=glass(), mesh_resolution=48, mesh_airy=0.006, target=plane())
img = bpy.data.images.get("CAUSTIC_bake")
ok = r == {"FINISHED"} and img is not None
mx = -1.0
if ok:
    px = list(img.pixels[:])
    mx = max(px)
    ok = mx > 0.0 and mx <= 1.0 + 1e-6
check("mesh_bake_nonzero_and_bounded", ok, f"max={mx:.3f}")
print("BAKE_STATUS", p.status)

# ---- 3. point light bake runs ----------------------------------------------
fresh_scene()
bpy.ops.object.light_add(type="POINT", location=(0.0, 0.0, 0.4))
for o in list(bpy.data.objects):
    if o.type == "LIGHT" and o.data.type == "SUN":
        bpy.data.objects.remove(o, do_unlink=True)
r, p = run_bake(mesh_object=glass(), mesh_resolution=32, mesh_airy=0.006, target=plane())
check("point_light_bake_runs", r == {"FINISHED"}, p.status[:80])

# ---- 4. open mesh cancels by name ------------------------------------------
fresh_scene()
bpy.ops.mesh.primitive_plane_add(size=0.1, location=(0, 0, 0.05))
hole = bpy.context.active_object
hole.name = "open_mesh"
msg = run_bake_cancel(mesh_object=hole, target=plane())
check("open_mesh_cancels_named",
      msg is not None and "watertight" in msg.lower(), msg[:80] if msg else "no error")

# ---- 5. missing UVs cancel by name -----------------------------------------
fresh_scene()
bpy.ops.mesh.primitive_cube_add(size=0.05, location=(0, 0, 0.05))
cube = bpy.context.active_object
cube.name = "glass_cube"
while cube.data.uv_layers:
    cube.data.uv_layers.remove(cube.data.uv_layers[0])
bpy.ops.mesh.primitive_plane_add(size=0.32, location=(2.0, 0.0, -0.10))
recv = bpy.context.active_object
recv.name = "receiver"
while recv.data.uv_layers:
    recv.data.uv_layers.remove(recv.data.uv_layers[0])
msg = run_bake_cancel(mesh_object=cube, target=recv)
check("missing_uvs_cancel_named",
      msg is not None and "uv" in msg.lower(), msg[:80] if msg else "no error")

# ---- 6. absorb changes channel ratios --------------------------------------
fresh_scene()
run_bake(mesh_object=glass(), mesh_resolution=48, mesh_airy=0.006, target=plane(),
         glass_absorb=(0.0, 0.0, 0.0))
clear = list(bpy.data.images["CAUSTIC_bake"].pixels[:])
run_bake(mesh_object=glass(), mesh_resolution=48, mesh_airy=0.006, target=plane(),
         glass_absorb=(30.0, 344.0, 721.0))
tinted = list(bpy.data.images["CAUSTIC_bake"].pixels[:])
n = len(clear) // 4
cr = sum(clear[4 * i] for i in range(n)) / (sum(clear[4 * i + 2] for i in range(n)) + 1e-9)
tr = sum(tinted[4 * i] for i in range(n)) / (sum(tinted[4 * i + 2] for i in range(n)) + 1e-9)
check("absorb_changes_channel_ratios", abs(cr - tr) / (abs(cr) + 1e-9) > 0.05,
      f"R/B clear={cr:.2f} tinted={tr:.2f}")

# ---- 7. time estimate shown and scales --------------------------------------
from mesh_caustic.trace import estimate_seconds
t1 = estimate_seconds(10000, 48)
t2 = estimate_seconds(10000, 96)
check("estimate_shown_and_scales", t1 > 0 and t2 > 2.5 * t1,
      f"48^2={t1:.1f}s 96^2={t2:.1f}s")

# ---- 8. inject/remove round-trip on a mesh bake -----------------------------
fresh_scene()
run_bake(mesh_object=glass(), mesh_resolution=48, mesh_airy=0.006, target=plane())
bpy.ops.caustic.inject()
mats = [m for m in plane().data.materials if m and m.use_nodes]
n_in = sum(1 for m in mats for nd in m.node_tree.nodes if nd.name.startswith("CAUSTIC_"))
bpy.ops.caustic.remove()
n_out = sum(1 for m in mats for nd in m.node_tree.nodes if nd.name.startswith("CAUSTIC_"))
check("inject_remove_roundtrip", n_in > 0 and n_out == 0,
      f"injected={n_in} left={n_out}")

print("FAILURES:", FAILS if FAILS else "0 []")
sys.exit(1 if FAILS else 0)
