"""probe_blender.py — verify headless Cycles + GPU before building the scene."""
import bpy
import sys

print("BLENDER", bpy.app.version_string)
print("CYCLES_AVAILABLE", "cycles" in bpy.context.preferences.addons)

prefs = bpy.context.preferences.addons.get("cycles")
if prefs:
    try:
        cprefs = prefs.preferences
        cprefs.refresh_devices()
        names = []
        for d in cprefs.devices:
            names.append(f"{d.name}:{d.type}:use={d.use}")
        print("CYCLES_DEVICES", names)
        print("COMPUTE_DEVICE", cprefs.compute_device_type)
    except Exception as e:  # noqa: BLE001
        print("DEVICE_QUERY_FAILED", e)

# tiny render to prove the pipeline works end to end
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 8
scene.cycles.use_denoising = True
scene.render.resolution_x = 160
scene.render.resolution_y = 120
scene.render.filepath = "D:/ValueProjects/caustics/out/blender_probe.png"
scene.render.image_settings.file_format = "PNG"
try:
    scene.cycles.device = "GPU"
except Exception as e:  # noqa: BLE001
    print("GPU_SET_FAILED", e)

bpy.ops.mesh.primitive_uv_sphere_add(location=(0, 0, 1))
bpy.ops.object.light_add(type="SUN", location=(2, -2, 4))
bpy.ops.object.camera_add(location=(4, -4, 3), rotation=(1.1, 0, 0.78))
scene.camera = bpy.context.object
bpy.ops.render.render(write_still=True)
print("PROBE_RENDER_DONE")
sys.stdout.flush()
