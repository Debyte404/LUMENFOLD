"""trace.py -- generalized two-interface mesh tracer (numpy-only).

trace_mesh(verts, faces, lights, receiver, opts) -> {"hits": (M,2),
"chan": (M,) int 0/1/2 (R/G/B), "weights": (M,) Beer-Lambert transmission,
"extent_m"}. eta may be scalar (one shared path, per-channel absorption
weights) or an (R,G,B) triple (three dispersed paths).

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


def estimate_seconds(n_tris, n_side, nchan=1):
    """Wall-time estimate for trace_mesh at this budget.

    Calibrated on the dragon referee (90k rays x 35k tris = 145 s):
    t = rays * tris * 5e-8 per channel. Conservative on small meshes,
    honest on big ones.
    """
    return float(n_side * n_side) * float(n_tris) * 5e-8 * max(int(nchan), 1)


def _check_watertight(faces):
    c = Counter()
    for a, b, cc in faces:
        for u, v in ((a, b), (b, cc), (cc, a)):
            c[tuple(sorted((int(u), int(v))))] += 1
    return [e for e, n in c.items() if n != 2]


def check_closed(faces):
    """Raise ValueError naming open edges unless the mesh is watertight.

    Public pre-flight used by hosts (e.g. the Blender addon) that must
    report topology problems before spending time on lights and materials.
    Same message as the in-trace guard: never two sources of truth.
    """
    bad = _check_watertight(faces)
    if bad:
        raise ValueError(f"mesh not watertight: {len(bad)} open edges")


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


def bk7_n(wl_um):
    """BK7 crown-glass index at wavelength um (Sellmeier). Shape only: callers
    anchor the curve at the artist's IOR, so the studio value is preserved
    while the physical R>G>B ordering comes from measured dispersion."""
    B = (1.03961212, 0.231792344, 1.01046945)
    C = (0.00600069867, 0.0200179144, 103.560653)
    l2 = wl_um * wl_um
    return float((1.0 + sum(b * l2 / (l2 - c) for b, c in zip(B, C))) ** 0.5)


def ior_rgb(ior_550, lambdas=(0.65, 0.55, 0.45)):
    """Per-channel IOR anchored at the material's IOR (taken at 550 nm)."""
    base = bk7_n(0.55)
    return tuple(float(ior_550) + (bk7_n(l) - base) for l in lambdas)


def _shoot(o, d, geo, eta_c, receiver_z, patch_half, cx, cy):
    """Single interface-pair traversal at one channel index. Returns
    (x, y, path_length_mm_inside) or None (miss / TIR / off-receiver). The
    caller applies Beer-Lambert from the path length."""
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
    t = _refract(d, n, 1.0 / eta_c)
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
    t2 = _refract(t, n2, eta_c)
    if t2 is None or abs(t2[2]) < 1e-9:
        return None
    L = float(np.linalg.norm(q0 - p))
    s = (receiver_z - q0[2]) / t2[2]
    if s <= 0.0:
        return None
    q = q0 + s * t2
    if abs(q[0] - cx) > patch_half or abs(q[1] - cy) > patch_half:
        return None
    return (q[0], q[1], L)


def trace_mesh(verts, faces, lights, receiver, opts):
    """Two-interface transport per channel. eta may be scalar or (R,G,B).

    Returns {"hits": (M,2), "chan": (M,) int 0/1/2, "weights": (M,) float,
    "extent_m"}. A scalar eta traces one shared path with per-channel
    absorption weights; a triple traces three dispersed paths.
    Raises ValueError on open meshes / inside lights."""
    verts = np.asarray(verts, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    check_closed(faces)
    eta_opt = opts.get("eta", 1.5251)
    try:
        etas = (float(eta_opt),) * 3
        nchan = 1
    except TypeError:
        etas = (float(eta_opt[0]), float(eta_opt[1]), float(eta_opt[2]))
        nchan = 3 if len({round(e, 9) for e in etas}) > 1 else 1
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

    outs = []  # (x, y, channel, weight)

    def shoot_all(o, d):
        if nchan == 1:
            r = _shoot(o, d, geo, etas[0], rz, ph, cx, cy)
            if r is None:
                return
            _, _, L = r
            for c in range(3):
                outs.append((r[0], r[1], c, float(np.exp(-absorb[c] * L))))
        else:
            for c in range(3):
                r = _shoot(o, d, geo, etas[c], rz, ph, cx, cy)
                if r is None:
                    continue
                _, _, L = r
                outs.append((r[0], r[1], c, float(np.exp(-absorb[c] * L))))

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
                    shoot_all(o, d)
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
                    shoot_all(pos, dd)
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
                            shoot_all(src, dd)
        else:
            raise ValueError(f"unknown light type: {t}")
    if outs:
        a = np.array(outs, float)
        hits = a[:, :2].reshape(-1, 2)
        chan = a[:, 2].astype(np.int64)
        wght = a[:, 3]
    else:
        hits = np.zeros((0, 2))
        chan = np.zeros((0,), dtype=np.int64)
        wght = np.zeros((0,))
    return {"hits": hits, "chan": chan, "weights": wght,
            "extent_m": (2 * ph, 2 * ph)}
