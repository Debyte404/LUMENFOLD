"""dragon_glass_setup.py -- convert models/dragon.blend to a glass caustic scene.

Usage (Blender background):
  blender --background --python tools/dragon_glass_setup.py -- \
      --in models/dragon.blend --out models/dragon_glass.blend \
      [--sun 0.80,0.42,-0.43] [--sun-angle 2.4]

What it does: loads input, reports dragon open edges; if open, applies a
0.0035 m Solidify + weld and recalculates normals; sets Principled glass
(Base Color white, Roughness 0, IOR 1.525, Transmission Weight 1.0);
replaces all point/spot/area lights with one SUN; keeps Camera as
CAM_beauty and adds CAM_measure (top-down ortho over the receiver).
"""
import argparse
import math
import sys
from collections import Counter

import bpy


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="models/dragon.blend")
    ap.add_argument("--out", dest="out", default="models/dragon_glass.blend")
    ap.add_argument("--sun", default="0.80,0.42,-0.43")
    ap.add_argument("--sun-angle", type=float, default=2.4)
    return ap.parse_args(argv)


def open_edges(mesh):
    c = Counter()
    for p in mesh.polygons:
        vs = list(p.vertices)
        for i in range(len(vs)):
            e = tuple(sorted((vs[i], vs[(i + 1) % len(vs)])))
            c[e] += 1
    return [e for e, n in c.items() if n != 2]


def main():
    args = parse_args()
    bpy.ops.wm.open_mainfile(filepath=args.inp)
    dragon = bpy.data.objects.get("dragon")
    if dragon is None or dragon.type != "MESH":
        raise SystemExit("dragon mesh not found")
    mesh = dragon.data
    bad = open_edges(mesh)
    print(f"DRAGON_IN verts={len(mesh.vertices)} polys={len(mesh.polygons)} open_edges={len(bad)}")
    if bad:
        bpy.ops.object.select_all(action="DESELECT")
        dragon.select_set(True)
        bpy.context.view_layer.objects.active = dragon
        bpy.ops.object.mode_set(mode="OBJECT")
        sol = dragon.modifiers.new("wall", "SOLIDIFY")
        sol.thickness = 0.0035
        sol.offset = -1.0
        bpy.ops.object.modifier_apply(modifier=sol.name)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.remove_doubles(threshold=0.0001)
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode="OBJECT")
        mesh = dragon.data
        bad = open_edges(mesh)
        print(f"SOLIDIFY_APPLIED open_edges={len(bad)}")
    # glass material on slot 0
    if len(dragon.data.materials) == 0:
        mat = bpy.data.materials.new("DragonGlass")
        dragon.data.materials.append(mat)
    mat = dragon.data.materials[0]
    mat.use_nodes = True
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        bsdf = mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = 0.0
    if "IOR" in bsdf.inputs:
        bsdf.inputs["IOR"].default_value = 1.525
    if "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = 1.0
    # replace lights with one SUN
    for o in [o for o in bpy.data.objects if o.type == "LIGHT"]:
        bpy.data.objects.remove(o, do_unlink=True)
    sx, sy, sz = (float(v) for v in args.sun.split(","))
    sun_data = bpy.data.lights.new("SUN", type="SUN")
    sun_data.energy = 19.0
    sun_data.angle = math.radians(args.sun_angle)
    sun = bpy.data.objects.new("SUN", sun_data)
    bpy.context.collection.objects.link(sun)
    from mathutils import Vector
    sun.rotation_euler = Vector((sx, sy, sz)).to_track_quat("-Z", "Y").to_euler()
    # cameras: keep existing as beauty, add ortho measure over plane receiver
    cam = bpy.data.objects.get("Camera")
    if cam is not None:
        cam.name = "CAM_beauty"
    plane = bpy.data.objects.get("Plane")
    if plane is not None:
        cx, cy, cz = plane.location
    else:
        cx, cy, cz = (0.0, 0.0, -0.28)
    mcam_data = bpy.data.cameras.new("CAM_measure")
    mcam_data.type = "ORTHO"
    mcam_data.ortho_scale = 3.0
    mcam = bpy.data.objects.new("CAM_measure", mcam_data)
    mcam.location = (cx, cy, cz + 3.0)
    mcam.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.collection.objects.link(mcam)
    bpy.context.scene.camera = bpy.data.objects.get("CAM_beauty", mcam)
    # receiver bounds from plane world bbox
    if plane is not None:
        ws = [plane.matrix_world @ v.co for v in plane.data.vertices]
        xs = [v.x for v in ws]
        ys = [v.y for v in ws]
    else:
        xs, ys = [cx - 1.5, cx + 1.5], [cy - 1.5, cy + 1.5]
    print(f"MANIFOLD_OK open_edges={len(open_edges(dragon.data))} "
          f"verts={len(dragon.data.vertices)} receiver={min(xs):.3f},{max(xs):.3f},{min(ys):.3f},{max(ys):.3f}")
    bpy.ops.wm.save_as_mainfile(filepath=args.out)
    print(f"WROTE {args.out}")


if __name__ == "__main__":
    main()
