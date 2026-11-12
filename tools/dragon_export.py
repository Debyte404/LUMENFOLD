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
    ap.add_argument("--dump-camera", action="store_true",
                    help="write cam_beauty.json for check_dragon_framing.py")
    ap.add_argument("--beauty-resolution", default="2560x1440",
                    help="comparison render size; sets the sensor fit aspect")
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
    # forward=Y, up=Z writes Blender world coordinates unchanged. The OBJ
    # exporter defaults convert Z-up to Y-up, which left the dragon lying on
    # its side in PBRT/Mitsuba while Cycles rendered the transformed object.
    bpy.ops.wm.obj_export(filepath=obj_path, export_selected_objects=True,
                           apply_modifiers=True, export_triangulated_mesh=True,
                           export_materials=False,
                           forward_axis="Y", up_axis="Z")
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
    if args.dump_camera:
        cam = bpy.data.objects.get("CAM_beauty")
        if cam is None:
            raise SystemExit("CAM_beauty not found")
        m = cam.matrix_world
        try:
            rw, rh = (int(v) for v in args.beauty_resolution.lower().split("x"))
        except ValueError:
            raise SystemExit("--beauty-resolution must look like 2560x1440")
        deps = bpy.context.evaluated_depsgraph_get()
        ev = dragon.evaluated_get(deps)
        me = ev.to_mesh()
        vs = [ev.matrix_world @ v.co for v in me.vertices]
        lo = [min(v[i] for v in vs) for i in range(3)]
        hi = [max(v[i] for v in vs) for i in range(3)]
        ev.to_mesh_clear()
        dump = {"matrix": [[m[r][c] for c in range(4)] for r in range(4)],
                "lens": cam.data.lens,
                "sensor_width": cam.data.sensor_width,
                "sensor_height": cam.data.sensor_height,
                "sensor_fit": cam.data.sensor_fit,
                "resolution": [rw, rh],
                "dragon_bbox": [lo, hi]}
        with open(os.path.join(args.out, "cam_beauty.json"), "w") as f:
            json.dump(dump, f, indent=2)
        print(f"CAMERA {dump['lens']}mm {dump['sensor_fit']} {dump['resolution']}")


if __name__ == "__main__":
    main()
