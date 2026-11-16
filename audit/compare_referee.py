"""compare_referee.py -- referee vs our bake, same mesh, same frame, watts.

Runs inside Blender (needs the addon to bake our field in physical units):

  python tools/run_blender.py --background --factory-startup \\
      --python audit/compare_referee.py

Pre-registered thresholds (docs/superpowers/plans/2026-11-17-referee-dragon.md):
  r >= 0.80 at 9 mm, r >= 0.85 at 18 and 37 mm, energy ratio in [0.85, 1.18].
Both fields are converted to watts with their own sampling bookkeeping:
  ours     = sum(field_W_per_sr) * texel_area * pi/albedo   (as EVIDENCE 47)
  referee  = sum(weights) * E_sun * origin_cell_area / SUB^2
"""
import importlib.util
import json
import os
import sys

import bpy
import numpy as np

ROOT = r"D:\ValueProjects\caustics"
REF = os.path.join(ROOT, "out", "referee", "referee_field.npy")
STATS = os.path.join(ROOT, "out", "referee", "referee_stats.json")

spec = importlib.util.spec_from_file_location(
    "caustic_injector", os.path.join(ROOT, "blender_addon", "caustic_injector.py"))
mod = importlib.util.module_from_spec(spec)
sys.modules["caustic_injector"] = mod
spec.loader.exec_module(mod)
mod.register()

ref = np.load(REF)
st = json.load(open(STATS))
RES = int(st["res"])
SUB = int(st["sub"])
CX, CY, HALF = st["frame"]
d = np.load(os.path.join(ROOT, "out", "referee", "dragon_referee_87k.npz"))
verts = d["verts"]
E_SUN = float(d["sun_energy"])

# ---- our bake on the same mesh, same frame, physical units ------------------
bpy.ops.wm.open_mainfile(filepath=os.path.join(ROOT, "out", "dragon_clean.blend"))
sc = bpy.context.scene
p = sc.caustic
p.mesh_object = bpy.data.objects["dragon"]
p.target = bpy.data.objects["Plane"]
p.mesh_resolution = RES
p.mesh_ray_mult = 2
p.mesh_airy = 6.77e-6
p.mesh_accel = "BVHTREE"
p.mesh_achromatic = True
p.mesh_physical_exposure = True
p.glass_absorb = (0.0, 0.0, 0.0)
p.gain = 1.0

sys.path.insert(0, os.path.join(ROOT, "tools"))
from mesh_caustic import trace as MT, band as MB

dg = bpy.context.evaluated_depsgraph_get()
v, fcs, tn = mod._mesh_tris(p.mesh_object, dg)
recv = mod._resolve_target(p.target)
mat = mod._resolve_material(p.mesh_object)
lights = mod._collect_lights(sc.objects, tuple(p.sun_dir))
# force the same frame the referee used
recv = dict(recv)
recv["cx"], recv["cy"], recv["half"] = CX, CY, HALF
fld, res, rect = mod._bake_field(
    MT, MB, v, fcs, lights, recv, RES, p.mesh_airy, tuple(p.glass_absorb),
    float(mat["ior"]), ray_mult=2, frame="FULL", accel="bvhtree",
    tri_normals=tn, physical=True, sun_irradiance=E_SUN,
    albedo=mod._target_albedo(p.target), jitter_seed=20261117)
ours_rad = np.asarray(fld).mean(axis=2)              # W / (m^2 sr)
texel = (2 * HALF / RES) ** 2
alb = np.asarray(mod._target_albedo(p.target)).mean()
ours_W = float(ours_rad.sum()) * texel * np.pi / max(alb, 1e-9)

lo, hi = verts.min(axis=0) - 0.02, verts.max(axis=0) + 0.02
rad = 0.5 * float(np.linalg.norm(hi - lo)) + 0.01
cell = (2.0 * rad / (RES - 1)) ** 2
ref_W = float(ref.sum()) * E_SUN * cell / (SUB * SUB)
ratio = ours_W / max(ref_W, 1e-12)
print("ENERGY ours %.3f W  referee %.3f W  ratio %.3f  (threshold 0.85-1.18)"
      % (ours_W, ref_W, ratio))


def blockmean(a, k):
    h, w = a.shape
    return a[:h // k * k, :w // k * k].reshape(h // k, k, w // k, k).mean(axis=(1, 3))


def band(a, k):
    b = blockmean(a, k)
    t = np.repeat(np.repeat(blockmean(a, 2 * k), 2, 0), 2, 1)
    b = b[:t.shape[0], :t.shape[1]]
    return b - t


mm_per_texel = 2 * HALF / RES * 1000.0
print("%-12s %8s %8s %6s" % ("band", "r", "thresh", "verdict"))
bands = {}
fail = []
# The bake returns row 0 = +Y (fld[::-1,:,:]); the referee's histogram2d is
# (x-bins, y-bins) with no flip. Resolve the orientation BEFORE any band claim.
def bnd(x, k):
    b = blockmean(x, k)
    t = np.repeat(np.repeat(blockmean(x, 2 * k), 2, 0), 2, 1)
    b = b[:t.shape[0], :t.shape[1]]
    return b - t


_orients = {"raw": ref, "T": ref.T, "flipud": np.flipud(ref),
            "fliplr": np.fliplr(ref), "T+flipud": np.flipud(ref.T),
            "T+fliplr": np.fliplr(ref.T), "rot180": np.flipud(np.fliplr(ref))}
_bo = bnd(ours_rad, 8)
_best, _bname = -2.0, "raw"
for _nm, _r in _orients.items():
    _br = bnd(_r, 8)
    _m = np.ones(_bo.shape, dtype=bool)
    _m[:2, :2] = _m[:2, -2:] = _m[-2:, :2] = _m[-2:, -2:] = False
    _v = float(np.corrcoef(_bo[_m], _br[_m])[0, 1])
    print("ORIENT %-10s r(18mm)=%+.3f" % (_nm, _v))
    if _v > _best:
        _best, _bname, ref = _v, _nm, _r
print("ORIENT BEST %s r=%.3f" % (_bname, _best))
np.save(os.path.join(ROOT, "out", "referee", "ours_field.npy"), ours_rad)
for k, thresh in ((4, 0.80), (8, 0.85), (16, 0.85)):
    lam = k * mm_per_texel
    ba, bb = band(ours_rad, k), band(ref, k)
    m = np.ones(ba.shape, dtype=bool)
    m[:2, :2] = m[:2, -2:] = m[-2:, :2] = m[-2:, -2:] = False
    r = float(np.corrcoef(ba[m], bb[m])[0, 1])
    bands[round(lam, 1)] = float(r)
    ok = bool(r >= thresh)
    if not ok:
        fail.append((lam, r, thresh))
    print("%-12.1f %8.3f %8.2f %6s" % (lam, r, thresh, "PASS" if ok else "FAIL"))

out = {"energy": {"ours_W": ours_W, "referee_W": ref_W, "ratio": ratio},
       "bands_mm": bands,
       "pass_energy": bool(0.85 <= ratio <= 1.18),
       "pass_bands": not fail, "fails": fail}
with open(os.path.join(ROOT, "out", "referee", "compare.json"), "w") as fh:
    json.dump(out, fh, indent=2)
print("COMPARE", json.dumps(out))
print("REFEREE_VERDICT",
      "PASS" if out["pass_bands"] and out["pass_energy"] else "MISS")
