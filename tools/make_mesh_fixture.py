"""make_mesh_fixture.py -- build the small headless test scene.

Usage (needs bpy, i.e. run inside Blender):
  blender --background --python tools/make_mesh_fixture.py

Writes models/mesh_fixture.blend: a closed ~2k-tri UV sphere with a glass
material, a 0.32 m UV-mapped plane receiver at z=0, a SUN lamp along the
paper direction, and a camera. Small on purpose: Task 4 tests must run in
seconds, the dragon is the heavy manual check.
"""
import math
import os
import sys

import bpy

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "models", "mesh_fixture.blend")


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=0.035)
    ball = bpy.context.active_object
    ball.name = "fixture_glass"
    mat = bpy.data.materials.new("fixture_glass")
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (1, 1, 1, 1)
    b.inputs["Roughness"].default_value = 0.0
    b.inputs["IOR"].default_value = 1.525
    b.inputs["Transmission Weight"].default_value = 1.0
    ball.data.materials.append(mat)

    bpy.ops.mesh.primitive_plane_add(size=0.32, location=(0.0, 0.0, -0.10))
    plane = bpy.context.active_object
    plane.name = "fixture_table"
    if not plane.data.uv_layers:
        plane.data.uv_layers.new()

    sun_data = bpy.data.lights.new("sun", type="SUN")
    sun_data.energy = 8.0
    sun_data.angle = 0.042
    sun = bpy.data.objects.new("sun", sun_data)
    bpy.context.collection.objects.link(sun)
    from mathutils import Vector
    sun.rotation_euler = Vector((0.80, 0.42, -0.43)).to_track_quat("-Z", "Y").to_euler()

    cam_data = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = (0.24, 0.19, 0.06)
    cam.rotation_euler = (Vector((0, 0, 0)) - Vector(cam.location)).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam

    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    print(f"WROTE {OUT}")


if __name__ == "__main__":
    main()
