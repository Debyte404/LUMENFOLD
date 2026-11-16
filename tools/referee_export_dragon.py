"""referee_export_dragon.py -- export the dragon for the independent referee.

Writes a DIFFERENT serialization than the bake consumes: world-space triangles,
per-corner shading normals, the sun direction and the receiver frame. The
referee reads this and never touches the addon or mesh_caustic.

Run inside Blender:
  python tools/run_blender.py --background --factory-startup \\
      --python tools/referee_export_dragon.py
Output: out/referee/dragon_referee.npz
"""
import os

import bpy
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND = os.path.join(ROOT, "out", "dragon_clean.blend")
OUT = os.path.join(ROOT, "out", "referee", "dragon_referee_87k.npz")

bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene
obj = bpy.data.objects["dragon"]
dg = bpy.context.evaluated_depsgraph_get()
ev = obj.evaluated_get(dg)
me = ev.to_mesh()
mw = obj.matrix_world

# world-space vertices
v = np.empty(len(me.vertices) * 3)
me.vertices.foreach_get("co", v)
v = v.reshape(-1, 3)
M = np.array(mw)
v_world = v @ M[:3, :3].T + M[:3, 3]

# triangles + per-corner shading normals (object space -> world)
tris = []
cn = me.corner_normals
for poly in me.polygons:
    vs = list(poly.vertices)
    ls = poly.loop_start
    for i in range(1, len(vs) - 1):
        tri = (vs[0], vs[i], vs[i + 1])
        nn = []
        for k in (0, i, i + 1):
            c = cn[ls + k]
            nn.append([c.vector.x, c.vector.y, c.vector.z])
        tris.append((tri, nn))
tri_idx = np.array([t[0] for t in tris], dtype=np.int64)
tri_nrm = np.array([t[1] for t in tris], dtype=np.float64)
tri_nrm = tri_nrm @ M[:3, :3].T          # normals rotate, no translation
n = np.linalg.norm(tri_nrm, axis=2, keepdims=True)
tri_nrm = tri_nrm / np.where(n > 0, n, 1.0)

# sun direction (world)
sun = next(o for o in sc.objects if o.type == "LIGHT" and o.data.type == "SUN")
q = sun.matrix_world.to_quaternion()
from mathutils import Vector
d = q @ Vector((0.0, 0.0, -1.0))
sun_dir = np.array([d.x, d.y, d.z], dtype=np.float64)
sun_dir /= np.linalg.norm(sun_dir)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
np.savez_compressed(
    OUT,
    verts=v_world.astype(np.float64),
    tris=tri_idx,
    corner_normals=tri_nrm.astype(np.float64),
    sun_dir=sun_dir,
    sun_energy=np.float64(sun.data.energy),
    sun_angle_deg=np.float64(np.degrees(sun.data.angle)),
    receiver_z=np.float64(-0.276),
    # AUTO frame the bake produced for this mesh (from its metrics sidecar)
    frame_rect=np.array([0.4907739460468292, 0.3444439172744751,
                         0.7378125190734863], dtype=np.float64),
    albedo=np.array([0.328, 0.53, 0.8], dtype=np.float64),
    ior=np.float64(1.52514),
)
print("EXPORTED tris", len(tri_idx), "verts", len(v_world))
print("SAVED", OUT)
