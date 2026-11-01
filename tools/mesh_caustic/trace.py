"""trace.py -- generalized two-interface mesh tracer (numpy-only).

trace_mesh(verts, faces, lights, receiver, opts) -> dict with hits (N,2),
weights (N,3 rgb transmission), grid (G,G irradiance), extent_m.

Lights: {"type":"sun","direction":(x,y,z)} | {"type":"point","position":...}
| {"type":"spot","position":...,"direction":...,"angle_deg":...}
| {"type":"area","position":...,"normal":...,"size":...,"samples":3}.
Absorption: opts["absorb_rgb"] per-metre Beer-Lambert, applied per ray as
exp(-mu * entry->exit path length). Rays that TIR at exit are dropped.
Refusals are ValueError with stable message fragments (tests pin them).
"""
import math
from collections import Counter

import numpy as np


def _check_watertight(faces):
    c = Counter()
    for a, b, cc in faces:
        for u, v in ((a, b), (b, cc), (cc, a)):
            c[tuple(sorted((int(u), int(v))))] += 1
    return [e for e, n in c.items() if n != 2]


def _point_in_mesh(p, verts, faces):
    d = np.array([0.37, 0.48, 0.80])
    d /= np.linalg.norm(d)
    A = verts[faces[:, 0]]
    E1 = verts[faces[:, 1]] - A
    E2 = verts[faces[:, 2]] - A
    pvec = np.cross(d, E2)
    det = np.einsum("ij,ij->i", E1, pvec)
    good = np.abs(det) > 1e-14
    inv = np.zeros_like(det)
    inv[good] = 1.0 / det[good]
    tvec = np.asarray(p, float) - A
    qvec = np.cross(tvec, E1)
    u = np.einsum("ij,ij->i", tvec, pvec) * inv
    v = (qvec @ d) * inv
    dist = np.einsum("ij,ij->i", qvec, E2) * inv
    ok = good & (u >= 0) & (u <= 1) & (v >= 0) & (u + v <= 1) & (dist > 1e-9)
    return bool(ok.sum() % 2 == 1)


def _refract(d, n, eta):
    cosi = -float(d @ n)
    if cosi < 0.0:
        n, cosi = -n, -cosi
    k = 1.0 - eta * eta * (1.0 - cosi * cosi)
    if k < 0.0:
        return None
    return eta * d + (eta * cosi - math.sqrt(k)) * n


def _first_hit(o, d, A, E1, E2, pvec, det, inv, skip=-1):
    tvec = o - A
    qvec = np.cross(tvec, E1)
    u = np.einsum("ij,ij->i", tvec, pvec) * inv
    v = (qvec @ d) * inv
    dist = np.einsum("ij,ij->i", qvec, E2) * inv
    ok = ((np.abs(det) > 1e-14) & (u >= 0.0) & (u <= 1.0) & (v >= 0.0)
          & (u + v <= 1.0) & (dist > 1e-9))
    if skip >= 0:
        ok = ok & (np.arange(A.shape[0]) != skip)
    if not ok.any():
        return None, None
    i = int(np.argmin(np.where(ok, dist, np.inf)))
    p = o + dist[i] * d
    n = np.cross(E1[i], E2[i])
    n /= np.linalg.norm(n)
    return i, (p, n)


def _prep(verts, faces):
    A = verts[faces[:, 0]]
    E1 = verts[faces[:, 1]] - A
    E2 = verts[faces[:, 2]] - A
    return A, E1, E2


def _basis_toward(n):
    n = np.asarray(n, float)
    n /= np.linalg.norm(n)
    up = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 else np.array([0.0, 1.0, 0.0])
    right = np.cross(n, up)
    right /= np.linalg.norm(right)
    return right, np.cross(right, n), n


def _shoot(o, d, geo, eta, absorb, receiver_z, patch_half, cx, cy):
    A, E1, E2 = geo
    pvec = np.cross(d, E2)
    det = np.einsum("ij,ij->i", E1, pvec)
    inv = np.zeros_like(det)
    g = np.abs(det) > 1e-14
    inv[g] = 1.0 / det[g]
    ie, hp = _first_hit(o, d, A, E1, E2, pvec, det, inv)
    if ie is None:
        return None
    p, n = hp
    if n @ d > 0.0:
        n = -n
    t = _refract(d, n, 1.0 / eta)
    if t is None:
        return None
    p2 = p + t * 1e-6
    pvec2 = np.cross(t, E2)
    det2 = np.einsum("ij,ij->i", E1, pvec2)
    inv2 = np.zeros_like(det2)
    g2 = np.abs(det2) > 1e-14
    inv2[g2] = 1.0 / det2[g2]
    ix, hx = _first_hit(p2, t, A, E1, E2, pvec2, det2, inv2, skip=ie)
    if ix is None:
        return None
    q0, n2 = hx
    if n2 @ t > 0.0:
        n2 = -n2
    t2 = _refract(t, n2, eta)
    if t2 is None or abs(t2[2]) < 1e-9:
        return None
    L = float(np.linalg.norm(q0 - p))
    w = np.exp(-np.asarray(absorb, float) * L)
    s = (receiver_z - q0[2]) / t2[2]
    if s <= 0.0:
        return None
    q = q0 + s * t2
    if abs(q[0] - cx) > patch_half or abs(q[1] - cy) > patch_half:
        return None
    return (q[0], q[1], w)


def trace_mesh(verts, faces, lights, receiver, opts):
    """See module docstring. Raises ValueError on open meshes / inside lights."""
    verts = np.asarray(verts, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    bad = _check_watertight(faces)
    if bad:
        raise ValueError(f"mesh not watertight: {len(bad)} open edges")
    eta = float(opts.get("eta", 1.5251))
    absorb = tuple(opts.get("absorb_rgb", (0.0, 0.0, 0.0)))
    n_side = int(opts.get("n_side", 150))
    rz = float(receiver["z"])
    ph = float(receiver["patch_half"])
    cxy = receiver.get("center", (0.0, 0.0))
    cx, cy = float(cxy[0]), float(cxy[1])
    geo = _prep(verts, faces)
    lo, hi = verts.min(axis=0) - 0.02, verts.max(axis=0) + 0.02
    centre = 0.5 * (lo + hi)
    radius = 0.5 * float(np.linalg.norm(hi - lo)) + 0.01

    for L in lights:
        pos = L.get("position")
        if pos is not None and _point_in_mesh(pos, verts, faces):
            raise ValueError("light inside mesh: move it outside the glass")

    outs = []
    for L in lights:
        t = L["type"]
        if t == "sun":
            d = np.asarray(L["direction"], float)
            d /= np.linalg.norm(d)
            right, up, _ = _basis_toward(-d)
            xs = np.linspace(-radius, radius, n_side)
            for x in xs:
                for y in xs:
                    o = centre + x * right + y * up - 0.5 * d
                    r = _shoot(o, d, geo, eta, absorb, rz, ph, cx, cy)
                    if r is not None:
                        outs.append(r)
        elif t in ("point", "spot"):
            pos = np.asarray(L["position"], float)
            tgt = np.asarray(L.get("direction", centre - pos), float)
            tgt /= np.linalg.norm(tgt)
            right, up, _ = _basis_toward(tgt)
            xs = np.linspace(-radius, radius, n_side)
            for x in xs:
                for y in xs:
                    aim = centre + x * right + y * up
                    dd = aim - pos
                    nrm = float(np.linalg.norm(dd))
                    if nrm < 1e-9:
                        continue
                    dd /= nrm
                    if t == "spot":
                        co = np.asarray(L.get("direction", tgt), float)
                        co /= np.linalg.norm(co)
                        ang = math.radians(float(L.get("angle_deg", 30.0)))
                        if float(dd @ co) < math.cos(ang):
                            continue
                    r = _shoot(pos, dd, geo, eta, absorb, rz, ph, cx, cy)
                    if r is not None:
                        outs.append(r)
        elif t == "area":
            pos = np.asarray(L["position"], float)
            n = np.asarray(L.get("normal", (0, 0, -1)), float)
            right, up, _ = _basis_toward(n)
            s = int(L.get("samples", 3))
            half = float(L.get("size", 0.5)) / 2
            grid = np.linspace(-half, half, s)
            xs = np.linspace(-radius, radius, max(n_side // s, 4))
            for ax in grid:
                for ay in grid:
                    src = pos + ax * right + ay * up
                    for x in xs:
                        for y in xs:
                            aim = centre + x * right + y * up
                            dd = aim - src
                            dd /= float(np.linalg.norm(dd))
                            r = _shoot(src, dd, geo, eta, absorb, rz, ph, cx, cy)
                            if r is not None:
                                outs.append(r)
        else:
            raise ValueError(f"unknown light type: {t}")
    hits = np.array([(h[0], h[1]) for h in outs], float) if outs else np.zeros((0, 2))
    wght = np.array([h[2] for h in outs], float) if outs else np.zeros((0, 3))
    return {"hits": hits, "weights": wght, "extent_m": (2 * ph, 2 * ph)}
