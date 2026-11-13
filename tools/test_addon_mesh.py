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
  8e. fan-framed bake: finishes, reports the frame, finer texels, the bright
      centroid stays at the same world place as a FULL bake, and the inject
      places it through the target's affine UV fit (identity for FULL)
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

# ---- 8b. rough glass refused by name -----------------------------------------
fresh_scene()
gm = glass().data.materials[0]
bsdf = next(n for n in gm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
bsdf.inputs["Roughness"].default_value = 0.5
p = bpy.context.scene.caustic
p.mesh_object = glass()
p.target = plane()
try:
    bpy.ops.caustic.bake_mesh()
    check("rough_glass_refused", False, "no error raised")
except RuntimeError as e:
    check("rough_glass_refused", "rough" in str(e).lower(), str(e)[:90])

# ---- 8c. material IOR moves the fold ---------------------------------------
fresh_scene()
gm = glass().data.materials[0]
bsdf = next(n for n in gm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
bsdf.inputs["IOR"].default_value = 1.4
run_bake(mesh_object=glass(), mesh_resolution=32, mesh_airy=0.006, target=plane())
lo = [round(v, 4) for v in bpy.data.images["CAUSTIC_bake"].pixels[:]]
bsdf.inputs["IOR"].default_value = 1.6
run_bake(mesh_object=glass(), mesh_resolution=32, mesh_airy=0.006, target=plane())
hi = [round(v, 4) for v in bpy.data.images["CAUSTIC_bake"].pixels[:]]
check("material_ior_moves_fold", lo != hi, f"same={lo == hi}")

# ---- 8d. volume node on the material tints the bake -----------------------
fresh_scene()
gm = glass().data.materials[0]
nt = gm.node_tree
va = nt.nodes.new("ShaderNodeVolumeAbsorption")
va.inputs["Color"].default_value = (1.0, 0.0, 0.0, 1.0)  # absorb G+B
va.inputs["Density"].default_value = 30.0
out = nt.nodes.get("Material Output")
nt.links.new(va.outputs["Volume"], out.inputs["Volume"])
run_bake(mesh_object=glass(), mesh_resolution=32, mesh_airy=0.006, target=plane())
img = list(bpy.data.images["CAUSTIC_bake"].pixels[:])
n = len(img) // 4
rr = sum(img[4 * i] for i in range(n))
bb = sum(img[4 * i + 2] for i in range(n))
check("volume_node_tints_bake", rr > 2.0 * max(bb, 1e-9),
      f"R/B={rr / max(bb, 1e-9):.1f} (material volume node, no panel absorb)")

# ---- 8c2. supersampled rays keep grid shape, raise hit count ---------------
fresh_scene()
import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "caustic_injector",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "blender_addon", "caustic_injector.py"))
_mod = _ilu.module_from_spec(_spec)
_sys.modules["caustic_injector"] = _mod
_spec.loader.exec_module(_mod)
from mesh_caustic import trace as _MT, band as _MB
from caustic_injector import _mesh_tris as _mesh_tris_fn, _resolve_target as _resolve_tgt, _collect_lights as _collect_l, _bake_field as _bake_field_fn
dg = bpy.context.evaluated_depsgraph_get()
_vv, _ff, _nn = _mesh_tris_fn(glass(), dg)
_rr = _resolve_tgt(plane())
_ll = _collect_l(bpy.context.scene.objects, (0.80, 0.42, -0.43))
_f1, _r1, _rect1 = _bake_field_fn(_MT, _MB, _vv, _ff, _ll, _rr, 32, 0.006, (0.0, 0.0, 0.0), 1.5251, ray_mult=1, tri_normals=_nn)
_f2, _r2, _rect2 = _bake_field_fn(_MT, _MB, _vv, _ff, _ll, _rr, 32, 0.006, (0.0, 0.0, 0.0), 1.5251, ray_mult=2, tri_normals=_nn)
check("supersample_keeps_grid", _f1.shape == (32, 32, 3) and _f2.shape == (32, 32, 3),
      f"{_f1.shape} vs {_f2.shape}")
check("supersample_adds_hits", len(_r2["hits"]) > len(_r1["hits"]),
      f"{len(_r1['hits'])} -> {len(_r2['hits'])}")
check("supersample_full_has_no_frame", _rect1 is None and _rect2 is None,
      f"rects={_rect1},{_rect2}")

# ---- 8e. fan-framed bake: same caustic, finer texels, placed by UV fit ------
fresh_scene()
import numpy as _np

# A receiver LARGER than the caustic: the fixture sphere's fan fills the
# fixture table (framing clamps to FULL there, which is correct but proves
# nothing), so these checks bake onto a 1 m plane placed at the table's z.
_tbl = plane()
bpy.ops.mesh.primitive_plane_add(size=1.0, location=_tbl.location)
_big = bpy.context.active_object
_big.name = "big_receiver"


def big():
    return bpy.data.objects["big_receiver"]


r, p = run_bake(mesh_object=glass(), mesh_resolution=48, mesh_airy=0.006,
                target=big(), mesh_frame="FULL")
_fvrect = _resolve_tgt(big())
r, p = run_bake(mesh_object=glass(), mesh_resolution=48, mesh_airy=0.006,
                target=big(), mesh_frame="AUTO", mesh_frame_margin=0.05)
img = bpy.data.images.get("CAUSTIC_bake")
check("frame_auto_bakes", r == {"FINISHED"} and img is not None
      and "frame" in p.status, p.status[:90])
u0, v0, du, dv = tuple(p.frame_uv)
check("frame_uv_is_subrect",
      -1e-6 <= u0 and u0 + du <= 1.0 + 1e-6
      and -1e-6 <= v0 and v0 + dv <= 1.0 + 1e-6
      and 0.02 < du < 1.0 and 0.02 < dv < 1.0,
      f"uv=({u0:.3f},{v0:.3f},{du:.3f},{dv:.3f})")
check("frame_rect_recorded", p.frame_rect[2] > 0.0,
      f"rect=({p.frame_rect[0]:.3f},{p.frame_rect[1]:.3f},{p.frame_rect[2]:.3f})")
texel_full = 2 * _fvrect["half"] / 48
telem_auto = 2 * p.frame_rect[2] / 48
check("frame_never_coarser_than_full",
      telem_auto <= texel_full + 1e-9 and p.frame_rect[2] < _fvrect["half"],
      f"auto {1000 * telem_auto:.1f} mm vs full {1000 * texel_full:.1f} mm")

# Same caustic in the same world place. The framed trace carries the SAME
# ray set (n_side is unchanged; the patch only filters hits), so AUTO's raw
# hits must be exactly FULL's hits inside the framed rect. The corrected
# IMAGE centroid is not comparable across bin sizes: the ridge percentile
# and band width are texel-size dependent, which is why this is asserted on
# the hits and not on the corrected field.
_dg2 = bpy.context.evaluated_depsgraph_get()
_vv2, _ff2, _nn2 = _mesh_tris_fn(glass(), _dg2)
_ll2 = _collect_l(bpy.context.scene.objects, (0.80, 0.42, -0.43))
_fF, rF, _ = _bake_field_fn(_MT, _MB, _vv2, _ff2, _ll2, _fvrect, 48, 0.006,
                            (0.0, 0.0, 0.0), 1.5251, ray_mult=2, frame="FULL",
                            tri_normals=_nn2)
_fA, rA, rectA = _bake_field_fn(_MT, _MB, _vv2, _ff2, _ll2, _fvrect, 48,
                                0.006, (0.0, 0.0, 0.0), 1.5251, ray_mult=2,
                                frame="AUTO", frame_margin=0.05,
                                tri_normals=_nn2)
hF = _np.asarray(rF["hits"])
hA = _np.asarray(rA["hits"])
inside = ((abs(hF[:, 0] - rectA[0]) <= rectA[2])
          & (abs(hF[:, 1] - rectA[1]) <= rectA[2]))
cF = hF[inside].mean(axis=0)
cA = hA.mean(axis=0)
d_hits = float(_np.hypot(*(cA - cF)))
check("frame_auto_same_world_place",
      d_hits < 1e-6 and len(hA) == int(inside.sum()),
      f"hit centroid moved {d_hits * 1e6:.1f} um; "
      f"hits {len(hA)} vs full-inside {int(inside.sum())}")

run_bake(mesh_object=glass(), mesh_resolution=48, mesh_airy=0.006,
         target=big(), mesh_frame="FULL")
check("frame_full_is_identity",
      tuple(p.frame_uv) == (0.0, 0.0, 1.0, 1.0) and p.frame_rect[2] == 0.0,
      f"uv={tuple(round(v, 3) for v in p.frame_uv)}")

# inject a framed bake: the placement nodes must exist and carry the fit
run_bake(mesh_object=glass(), mesh_resolution=48, mesh_airy=0.006,
         target=big(), mesh_frame="AUTO", mesh_frame_margin=0.05)
bpy.ops.caustic.inject()
nt = next(m for m in big().data.materials if m and m.use_nodes).node_tree
mul = nt.nodes.get("CAUSTIC_map_mul")
add = nt.nodes.get("CAUSTIC_map_add")
u0, v0, du, dv = tuple(bpy.context.scene.caustic.frame_uv)
ok = (mul is not None and add is not None
      and _np.allclose(mul.inputs[1].default_value[:2], (1 / du, 1 / dv), atol=1e-6)
      and _np.allclose(add.inputs[1].default_value[:2], (-u0 / du, -v0 / dv), atol=1e-6))
check("frame_inject_maps_by_fit", ok,
      f"mul={tuple(round(v, 3) for v in mul.inputs[1].default_value[:2]) if mul else None}")

# ---- 8f. BVHTree backend matches the numpy reference ------------------------
run_bake(mesh_object=glass(), mesh_resolution=48, mesh_airy=0.006,
         target=big(), mesh_frame="FULL", mesh_accel="NUMPY")
_np_img = _np.array(bpy.data.images["CAUSTIC_bake"].pixels[:]).reshape(-1, 4)
_t0 = __import__("time").time()
run_bake(mesh_object=glass(), mesh_resolution=48, mesh_airy=0.006,
         target=big(), mesh_frame="FULL", mesh_accel="BVHTREE")
_bvh_img = _np.array(bpy.data.images["CAUSTIC_bake"].pixels[:]).reshape(-1, 4)
_a = _np_img[:, :3].mean(axis=1)
_b = _bvh_img[:, :3].mean(axis=1)
_r = float(_np.corrcoef(_a, _b)[0, 1]) if _a.std() > 0 and _b.std() > 0 else 0.0
check("bvhtree_matches_numpy", _r > 0.999,
      f"field correlation r={_r:.5f}, peak numpy {_a.max():.3f} bvh {_b.max():.3f}")

# ---- 8g. sun-disk blur: energy preserved, peak softened ----------------------
from caustic_injector import _disk_blur as _blur
_d = _np.zeros((128, 128))
_d[64, 64] = 1.0
_bl = _blur(_d, 3.0)
check("sun_blur_preserves_energy", abs(float(_bl.sum()) - 1.0) < 1e-9,
      f"sum={_bl.sum():.6f}")
check("sun_blur_drops_peak", float(_bl.max()) < 0.1, f"peak={_bl.max():.4f}")
_yy, _xx = _np.mgrid[0:128, 0:128]
_rr = _np.hypot(_yy - 64, _xx - 64)
check("sun_blur_support", float(_bl[_rr > 6.0].sum()) < 1e-3,
      f"outside={_bl[_rr > 6.0].sum():.2e}")

# ---- 8h. sub-texel Airy is skipped by design (geometric field) -------------
_r, _p = run_bake(mesh_object=glass(), mesh_resolution=48, mesh_airy=6.77e-6,
                  target=big(), mesh_frame="FULL", mesh_accel="BVHTREE")
check("sub_texel_airy_skips_correction",
      _r == {"FINISHED"} and "airy sub-texel" in _p.status, _p.status[:120])


sun = bpy.data.objects.get("sun")
sun.rotation_mode = "XYZ"
for f, ang in ((1, 0.0), (2, 0.1), (3, 0.2)):
    sun.rotation_euler = (ang, 0.0, 0.0)  # tilt about X: moves the -Z sun dir
    sun.keyframe_insert(data_path="rotation_euler", frame=f)
p = bpy.context.scene.caustic
p = bpy.context.scene.caustic
p.mesh_object = glass()
p.target = plane()
p.seq_start = 1
p.seq_end = 3
p.mesh_resolution = 32
p.mesh_airy = 0.006
r = bpy.ops.caustic.bake_seq()
check("seq_bake_runs", r == {"FINISHED"}, p.status[:80])
import glob as _glob
frames = sorted(_glob.glob(os.path.join(
    os.path.expanduser("~"), "AppData", "Local", "Temp",
    "blender_caustic", "seq", "caustic_*.png")))
check("seq_three_frames", len(frames) == 3, f"{len(frames)} files")
blobs = [open(f, "rb").read() for f in frames]
check("seq_frames_differ", len(set(blobs)) > 1,
      f"sizes={[len(b) for b in blobs]}")
img = bpy.data.images.get("CAUSTIC_bake")
check("seq_injection_uses_sequence",
      img is not None and img.source == "SEQUENCE", getattr(img, "source", "?"))
# the sequence must actually drive the render: CAUSTIC_bake is still the
# 3-frame sequence from the seq test above — inject it and render frames 1/3
bpy.ops.caustic.inject()
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.samples = 16
sc.render.resolution_x = 240
sc.render.resolution_y = 150
import tempfile as _tf
shots = []
for f in (1, 3):
    sc.frame_set(f)
    fp = os.path.join(_tf.gettempdir(), f"dragon_seq_proof_f{f}.png")
    sc.render.filepath = fp
    bpy.ops.render.render(write_still=True)
    shots.append(open(fp, "rb").read())
check("seq_drives_render",
      len(shots) == 2 and shots[0] != shots[1],
      f"sizes={[len(s) for s in shots]}")

print("FAILURES:", FAILS if FAILS else "0 []")
sys.exit(1 if FAILS else 0)
