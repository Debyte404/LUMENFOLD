"""Load the add-on into Blender and actually exercise it.

Compiling proves nothing: the failure this guards against is a material that
silently does nothing because Cycles never integrates the volume. So the test
asserts the three things that have to be true together -- the operator runs, the
volume node is built and LINKED, and volume_bounces is raised off its default 0.
"""
import sys
import os

import bpy

ADDON = r"D:/ValueProjects/caustics/blender_addon/caustic_injector.py"
fails = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        fails.append(msg)


# --- a scene with a glass-like object
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cylinder_add(radius=0.035, depth=0.09)
obj = bpy.context.object
obj.name = "glass"
mat = bpy.data.materials.new("glass")
mat.use_nodes = True
obj.data.materials.append(mat)

sc = bpy.context.scene
sc.render.engine = "CYCLES"
print("  volume_bounces default =", sc.cycles.volume_bounces)
check(sc.cycles.volume_bounces == 0,
      "Cycles really does default volume_bounces to 0 (the silent trap)")

# --- register the add-on the way Blender would
import importlib.util
spec = importlib.util.spec_from_file_location("caustic_injector", ADDON)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.register()
check(hasattr(bpy.types.Scene, "caustic"), "add-on registered; Scene.caustic exists")

p = sc.caustic
check(all(abs(a-b) < 1e-3 for a, b in zip(p.glass_absorb, (30.0, 344.0, 721.0))),
      "glass_absorb defaults present")
check(all(abs(a-b) < 1e-3 for a, b in zip(p.water_absorb, (1.17, 21.0, 38.9))),
      "water_absorb defaults present")

# --- exercise the tint operator
p.medium_objects = obj
bpy.context.view_layer.objects.active = obj
res = bpy.ops.caustic.tint_medium()
check(res == {"FINISHED"}, "tint_medium ran")

nt = mat.node_tree
vnodes = [n for n in nt.nodes if n.name.startswith("MEDIUM_")]
check(len(vnodes) == 1, "exactly one MEDIUM_ volume node created")

out = nt.nodes.get("Material Output")
check(out is not None and out.inputs["Volume"].is_linked,
      "volume node is LINKED to the output (a built-but-unlinked node is the bug)")

if vnodes:
    va = vnodes[0]
    dens = va.inputs["Density"].default_value
    col = tuple(va.inputs["Color"].default_value)[:3]
    check(abs(dens - 721.0) < 1e-6, f"Density == max(mu) (got {dens})")
    mu = [dens * (1.0 - c) for c in col]
    # float32 UI storage: 1e-6 is tighter than a FloatVectorProperty can hold
    check(all(abs(a - b) < 1e-3 for a, b in zip(mu, (30.0, 344.0, 721.0))),
          f"recovered mu round-trips: {['%.1f' % v for v in mu]}")

check(sc.cycles.volume_bounces >= 1,
      f"volume_bounces raised off 0 (now {sc.cycles.volume_bounces})")

# --- idempotence and removal
bpy.ops.caustic.tint_medium()
check(len([n for n in mat.node_tree.nodes if n.name.startswith("MEDIUM_")]) == 1,
      "re-running replaces rather than stacking")
bpy.ops.caustic.untint_medium()
check(len([n for n in mat.node_tree.nodes if n.name.startswith("MEDIUM_")]) == 0,
      "untint removes the volume node")

print()
print("  FAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
