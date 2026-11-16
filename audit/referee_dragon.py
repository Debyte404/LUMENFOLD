"""referee_dragon.py -- independent two-interface referee for the dragon caustic.

Independence contract (see docs/superpowers/plans/2026-11-17-referee-dragon.md):
  * shares ONLY the geometry index (mathutils.bvhtree, a library call);
  * ALL transport is written here from scratch: refraction via the vector Snell
    form with explicit n1/n2, Fresnel via amplitude (s/p) coefficients,
    stratified sun-disk sampling, own binning;
  * reads the exported npz (a different serialization than the bake consumes);
  * imports nothing from tools/mesh_caustic, blender_addon or src.

Run inside Blender (uses mathutils only):
  python tools/run_blender.py --background --factory-startup \\
      --python audit/referee_dragon.py -- [--res 512] [--sub 4]
Output: out/referee/referee_field.npy and referee_stats.json
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NPZ = os.path.join(ROOT, "out", "referee", "dragon_referee_87k.npz")
OUTDIR = os.path.join(ROOT, "out", "referee")

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
RES = int(argv[argv.index("--res") + 1]) if "--res" in argv else 512
SUB = int(argv[argv.index("--sub") + 1]) if "--sub" in argv else 4

d = np.load(NPZ)
verts = d["verts"]
tris = d["tris"]
cnorm = d["corner_normals"]          # (M,3,3) per-corner shading normals
sun_dir = d["sun_dir"].astype(float)  # unit, direction of travel
E_SUN = float(d["sun_energy"])
HALF_ANGLE = math.radians(float(d["sun_angle_deg"])) / 2.0
RZ = float(d["receiver_z"])
CX, CY, HALF = [float(x) for x in d["frame_rect"]]
ALBEDO = d["albedo"].astype(float)
IOR = float(d["ior"])

print("REFEREE tris", len(tris), "res", RES, "sun-sub", SUB,
      "frame", (round(CX, 3), round(CY, 3), round(HALF, 3)))

bvh = BVHTree.FromPolygons([tuple(v) for v in verts],
                           [tuple(int(x) for x in t) for t in tris],
                           all_triangles=True, epsilon=0.0)

# ---- independent transport -------------------------------------------------
def refract_vec(dvec, nvec, n1, n2):
    """Vector Snell form with explicit indices; None on TIR."""
    cosi = -(dvec @ nvec)
    if cosi < 0.0:
        nvec = -nvec
        cosi = -cosi
        n1, n2 = n2, n1
    eta = n1 / n2
    sin2t = eta * eta * (1.0 - cosi * cosi)
    if sin2t > 1.0:
        return None, cosi
    cost = math.sqrt(1.0 - sin2t)
    return eta * dvec + (eta * cosi - cost) * nvec, cosi


def fresnel_T_amplitudes(cosi, n1, n2):
    """Unpolarized transmittance via s/p amplitude coefficients.
    Independent derivation: solve the Fresnel equations directly."""
    cosi = min(max(abs(cosi), 0.0), 1.0)
    sint2 = (n1 / n2) ** 2 * (1.0 - cosi * cosi)
    if sint2 >= 1.0:
        return 0.0
    cost = math.sqrt(1.0 - sint2)
    a, b = n1 * cosi, n2 * cost
    rs = (a - b) / (a + b)
    c, e = n1 * cost, n2 * cosi
    rp = (c - e) / (c + e)
    R = 0.5 * (rs * rs + rp * rp)
    return max(0.0, min(1.0, 1.0 - R))


def shade_normal(hit_index, loc, fallback):
    """Interpolate the exported per-corner normal at the hit point."""
    tri = tris[hit_index]
    p0, p1, p2 = (verts[tri[0]], verts[tri[1]], verts[tri[2]])
    v0, v1, v2 = p1 - p0, p2 - p0, np.asarray(loc, float) - p0
    d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
    d20, d21 = v2 @ v0, v2 @ v1
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-20:
        return np.asarray(fallback, float)
    u = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    s = 1.0 - u - w
    nrm = s * cnorm[hit_index][0] + u * cnorm[hit_index][1] + w * cnorm[hit_index][2]
    ln = np.linalg.norm(nrm)
    return nrm / ln if ln > 1e-12 else np.asarray(fallback, float)


def trace_one(origin, direction):
    """Return (x, y, T) or None."""
    loc, nor, idx, dist = bvh.ray_cast(Vector(origin), Vector(direction))
    if loc is None:
        return None
    n = shade_normal(int(idx), loc, nor)
    t, cosi = refract_vec(np.asarray(direction, float), n, 1.0, IOR)
    if t is None:
        return None
    T1 = fresnel_T_amplitudes(cosi, 1.0, IOR)
    p = np.asarray(loc, float) + t * 1e-6
    loc2, nor2, idx2, _ = bvh.ray_cast(Vector(p), Vector(t))
    tries = 0
    while loc2 is not None and int(idx2) == int(idx) and tries < 3:
        p = p + t * 1e-5
        loc2, nor2, idx2, _ = bvh.ray_cast(Vector(p), Vector(t))
        tries += 1
    if loc2 is None or int(idx2) == int(idx):
        return None
    n2 = shade_normal(int(idx2), loc2, nor2)
    t2, cosi2 = refract_vec(t, n2, IOR, 1.0)
    if t2 is None or abs(t2[2]) < 1e-9:
        return None
    T2 = fresnel_T_amplitudes(cosi2, IOR, 1.0)
    q0 = np.asarray(loc2, float)
    s = (RZ - q0[2]) / t2[2]
    if s <= 0.0:
        return None
    q = q0 + s * t2
    if abs(q[0] - CX) > HALF or abs(q[1] - CY) > HALF:
        return None
    return (float(q[0]), float(q[1]), T1 * T2)


# ---- stratified sun-disk sampling -----------------------------------------
right = np.cross(sun_dir, [0.0, 0.0, 1.0])
if np.linalg.norm(right) < 1e-6:
    right = np.cross(sun_dir, [0.0, 1.0, 0.0])
right /= np.linalg.norm(right)
up = np.cross(right, sun_dir)
up /= np.linalg.norm(up)
tan_half = math.tan(HALF_ANGLE)

lo = verts.min(axis=0)
hi = verts.max(axis=0)
ctr = 0.5 * (lo + hi)
rad = 0.5 * float(np.linalg.norm(hi - lo)) + 0.05
plane_ctr = ctr - sun_dir * (rad + 0.05)
grid = np.linspace(-rad, rad, RES)
cell = 2.0 * rad / (RES - 1)

rng = np.random.default_rng(20261117)
hits = []
total = 0
for gx in grid:
    for gy in grid:
        for si in range(SUB):
            for sj in range(SUB):
                total += 1
                ox = gx + (si + 0.5) / SUB * cell - 0.5 * cell
                oy = gy + (sj + 0.5) / SUB * cell - 0.5 * cell
                o = plane_ctr + ox * right + oy * up
                # stratified disk sample (sqrt radius for uniform area)
                rr = tan_half * math.sqrt((si + rng.random()) / SUB)
                aa = 2.0 * math.pi * ((sj + rng.random()) / SUB)
                dd = sun_dir + rr * (math.cos(aa) * right + math.sin(aa) * up)
                dd /= np.linalg.norm(dd)
                r = trace_one(o, dd)
                if r is not None:
                    hits.append(r)

print("REFEREE rays", total, "hits", len(hits))
h = np.asarray(hits, float) if hits else np.zeros((0, 3))

field = np.zeros((RES, RES), dtype=np.float64)
if len(h):
    field, _, _ = np.histogram2d(h[:, 0], h[:, 1], bins=RES,
                                 weights=h[:, 2],
                                 range=[[CX - HALF, CX + HALF],
                                        [CY - HALF, CY + HALF]])
os.makedirs(OUTDIR, exist_ok=True)
np.save(os.path.join(OUTDIR, "referee_field.npy"), field)
stats = {"res": RES, "sub": SUB, "rays": total, "hits": int(len(h)),
         "frame": [CX, CY, HALF], "sum": float(field.sum()),
         "max": float(field.max()) if field.size else 0.0}
with open(os.path.join(OUTDIR, "referee_stats.json"), "w") as f:
    json.dump(stats, f, indent=2)
print("REFEREE_STATS", json.dumps(stats))
