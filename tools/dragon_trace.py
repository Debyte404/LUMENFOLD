"""dragon_trace.py -- independent triangle-mesh tracer for the dragon suite.

No Jacobian, no parametrisation, no call into src/: this is the ground truth.
A sun ray is traced from the source plane through the mesh to the receiver
plane; hits are binned on the shared receiver patch from receiver.json.
"""
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
GEO = ROOT / "out" / "dragon_geo"
SUN = np.array([0.80, 0.42, -0.43])
SUN = SUN / np.linalg.norm(SUN)


def load_obj(path):
    verts, faces = [], []
    for line in Path(path).read_text(encoding="ascii").splitlines():
        if line.startswith("v "):
            verts.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("f "):
            idx = [int(x.split("/")[0]) - 1 for x in line.split()[1:]]
            for i in range(1, len(idx) - 1):
                faces.append((idx[0], idx[i], idx[i + 1]))
    return np.asarray(verts, dtype=np.float64), np.asarray(faces, dtype=np.int64)


def refract(d, n, eta):
    cosi = -float(d @ n)
    if cosi < 0.0:
        n, cosi = -n, -cosi
    k = 1.0 - eta * eta * (1.0 - cosi * cosi)
    if k < 0.0:
        return None
    return eta * d + (eta * cosi - math.sqrt(k)) * n


def trace(mesh, sun=SUN, n_side=300, eta=1.5251, receiver_z=0.0,
          patch_half=4.0, mesh_offset=None):
    verts, faces = mesh
    if mesh_offset is not None:
        verts = verts + np.asarray(mesh_offset, dtype=np.float64)
    A = verts[faces[:, 0]]
    E1 = verts[faces[:, 1]] - A
    E2 = verts[faces[:, 2]] - A
    pvec = np.cross(sun, E2)
    det = np.einsum("ij,ij->i", E1, pvec)
    good = np.abs(det) > 1e-14
    inv = np.zeros_like(det)
    inv[good] = 1.0 / det[good]
    lo, hi = verts.min(axis=0) - 0.05, verts.max(axis=0) + 0.05
    centre = 0.5 * (lo + hi)
    up = np.array([0.0, 0.0, 1.0])
    right = np.cross(sun, up)
    right /= np.linalg.norm(right)
    up = np.cross(right, sun)
    half = 0.5 * float(np.linalg.norm(hi - lo)) + 0.02
    xs = np.linspace(-half, half, n_side)
    hits = []
    for x in xs:
        for y in xs:
            o = centre + x * right + y * up - 0.5 * sun
            tvec = o - A
            qvec = np.cross(tvec, E1)
            u = np.einsum("ij,ij->i", tvec, pvec) * inv
            v = (qvec @ sun) * inv
            dist = np.einsum("ij,ij->i", qvec, E2) * inv
            ok = (good & (u >= 0.0) & (u <= 1.0) & (v >= 0.0)
                  & (u + v <= 1.0) & (dist > 1e-9))
            if not ok.any():
                continue
            i = int(np.argmin(np.where(ok, dist, np.inf)))
            p = o + dist[i] * sun
            n = np.cross(E1[i], E2[i])
            n /= np.linalg.norm(n)
            if n @ sun > 0.0:
                n = -n
            t = refract(sun, n, 1.0 / eta)
            if t is None or abs(t[2]) < 1e-9:
                continue
            s = (receiver_z - p[2]) / t[2]
            if s <= 0.0:
                continue
            q = p + s * t
            if abs(q[0]) <= patch_half and abs(q[1]) <= patch_half:
                hits.append((q[0], q[1]))
    return np.asarray(hits, dtype=np.float64)


def to_grid(hits, n=512, patch_half=4.0):
    g, _, _ = np.histogram2d(
        hits[:, 0], hits[:, 1], bins=n,
        range=[[-patch_half, patch_half], [-patch_half, patch_half]])
    return g.T


def _self_test():
    # dragon.obj must exist and be substantial
    dp = GEO / "dragon.obj"
    assert dp.exists(), f"missing exported {dp} -- run dragon_export.py first"
    verts, faces = load_obj(dp)
    assert len(faces) > 10000, f"dragon too coarse: {len(faces)} tris"
    print(f"dragon: {len(verts)} verts {len(faces)} tris OK")
    print("DRAGON_TRACE_SELF_TEST_OK")


if __name__ == "__main__":
    _self_test()
