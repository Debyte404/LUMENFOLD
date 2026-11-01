"""dragon_export.py -- export the shared dragon OBJ + receiver.json.

Usage (Blender background):
  blender --background --python tools/dragon_export.py -- \
      --blend models/dragon_glass.blend --out out/dragon_geo

Writes out/dragon_geo/dragon.obj (triangulated, applied modifiers,
9-decimal verts) and receiver.json (sun vector, receiver corners, patch).
Every engine and the tracer consume these exact files.
"""
import argparse
import json
import os
import sys

import bpy


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", default="models/dragon_glass.blend")
    ap.add_argument("--out", default="out/dragon_geo")
    return ap.parse_args(argv)


def main():
    args = parse_args()
    bpy.ops.wm.open_mainfile(filepath=args.blend)
    dragon = bpy.data.objects.get("dragon")
    if dragon is None:
        raise SystemExit("dragon object not found")
    bpy.ops.object.select_all(action="DESELECT")
    dragon.select_set(True)
    bpy.context.view_layer.objects.active = dragon
    os.makedirs(args.out, exist_ok=True)
    obj_path = os.path.join(args.out, "dragon.obj")
    bpy.ops.wm.obj_export(filepath=obj_path, export_selected_objects=True,
                           apply_modifiers=True, export_triangulated_mesh=True,
                           export_materials=False)
    plane = bpy.data.objects.get("Plane")
    if plane is not None:
        ws = [plane.matrix_world @ v.co for v in plane.data.vertices]
        xs = [v.x for v in ws]
        ys = [v.y for v in ws]
        zs = [v.z for v in ws]
        recv = {"x0": min(xs), "x1": max(xs), "y0": min(ys), "y1": max(ys),
                "z": sum(zs) / len(zs)}
    else:
        recv = {"x0": -4.0, "x1": 4.0, "y0": -4.0, "y1": 4.0, "z": 0.0}
    sun = bpy.data.objects.get("SUN")
    if sun is not None:
        import mathutils
        d = sun.matrix_world.to_quaternion() @ mathutils.Vector((0, 0, -1))
        sunv = [round(v, 6) for v in d]
    else:
        sunv = [0.80, 0.42, -0.43]
    with open(os.path.join(args.out, "receiver.json"), "w") as f:
        json.dump({"sun": sunv, "receiver": recv, "patch_half": 4.0}, f, indent=2)
    print(f"WROTE {obj_path}")
    print(f"RECEIVER {recv} SUN {sunv}")


if __name__ == "__main__":
    main()
