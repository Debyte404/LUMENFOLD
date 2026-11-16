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

from . import bvh as _bvh_mod


def _first_hit_bvh(bv, o, d, skip=-1):
    """BVH-backed nearest hit, returning the same (face, (p, n)) shape."""
    res = _bvh_mod.nearest(bv, np.asarray(o, float), np.asarray(d, float),
                           skip=skip)
    if res is None:
        return None, None
    fi, dist = res
    pos = int(bv.pos_of[fi])
    p = np.asarray(o, float) + dist * np.asarray(d, float)
    n = np.cross(bv.E1[pos], bv.E2[pos])
    nrm = np.linalg.norm(n)
    if nrm > 0:
        n = n / nrm
    return int(fi), (p, n)


def estimate_seconds(n_tris, n_side, nchan=1, accel="numpy"):
    """Wall-time estimate for trace_mesh at this budget.

    Calibrated on the dragon referee (90k rays x 35k tris = 145 s):
    t = rays * tris * 5e-8 per channel for the numpy tracer. The BVHTree
    backend does not scale with tris; its constant is calibrated from the
    addon bake (see EVIDENCE section 32).
    """
    rays = float(n_side) * float(n_side)
    if accel == "bvhtree":
        # measured 9.7-29 us/ray/channel on the i7-14650HX (EVIDENCE 32);
        # 20 us is the conservative middle for the UI hint
        return rays * 2e-5 * max(int(nchan), 1)
    return rays * float(n_tris) * 5e-8 * max(int(nchan), 1)


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
    """Snell refraction; returns None on TIR."""
    cosi = -float(d @ n)
    if cosi < 0.0:
        n, cosi = -n, -cosi
    k = 1.0 - eta * eta * (1.0 - cosi * cosi)
    if k < 0.0:
        return None
    return eta * d + (eta * cosi - math.sqrt(k)) * n


def _fresnel_T(cosi, eta):
    """Unpolarized Fresnel transmittance. cosi >= 0 is the incident cosine,
    eta = n1/n2 the relative index (same convention as _refract).
    Exact (Born & Wolf), clamped to [0, 1]; returns 0.0 past the TIR angle
    instead of raising, so callers that already drop TIR rays stay correct."""
    import math
    cosi = min(max(float(cosi), 0.0), 1.0)
    eta = float(eta)
    if eta <= 0.0:
        return 0.0
    s2 = eta * eta * (1.0 - cosi * cosi)
    if s2 >= 1.0:
        return 0.0
    cost = math.sqrt(max(1.0 - s2, 0.0))
    inv = 1.0 / eta
    ds, dp = cosi + cost * inv, cost + cosi * inv
    if ds <= 0.0 or dp <= 0.0:
        return 0.0
    rs = (cosi - cost * inv) / ds
    rp = (cost - cosi * inv) / dp
    return min(max(1.0 - 0.5 * (rs * rs + rp * rp), 0.0), 1.0)


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


def frame_patch(hits, recv, margin, min_half=0.05, density=0.10, bins=64):
    """Fan-framed square receiver patch from probe hits, world metres.

    The tracer launches rays over the mesh bounding sphere, so the receiver
    patch only filters and bins hits: re-binning the SAME hits into a smaller
    patch buys texel resolution and hits-per-texel for free. This returns the
    (cx, cy, half) of the square patch that hugs the DENSE caustic support
    with `margin`, at least `min_half`, clamped inside the receiver.

    density: keep only probe bins (a `bins` x `bins` grid over the receiver)
    holding at least this fraction of the peak bin's hit count. The faint
    spray around the fan would stretch the frame to the receiver's full
    extent and give back the texels the framing exists to buy; hits outside
    the frame are simply not binned, and the injected image's EXTEND
    continues the edge texel outward, so nothing is cut to black.

    hits: (M, 2) world xy. recv: dict(cx, cy, half). Raises ValueError with
    the named refusal when the probe found nothing.
    """
    hits = np.asarray(hits, dtype=np.float64)
    if hits.size == 0:
        raise ValueError("no receiver hits: probe found nothing on the "
                         "receiver, so there is nothing to frame")
    rcx, rcy, rhalf = (float(recv["cx"]), float(recv["cy"]),
                       float(recv["half"]))
    H, xe, ye = np.histogram2d(
        hits[:, 0], hits[:, 1], bins=int(bins),
        range=[[rcx - rhalf, rcx + rhalf], [rcy - rhalf, rcy + rhalf]])
    peak = float(H.max())
    if peak <= 0.0:
        raise ValueError("no receiver hits: probe found nothing on the "
                         "receiver, so there is nothing to frame")
    keep = H > 0.0 if density <= 0.0 else H >= float(density) * peak
    if not keep.any():
        raise ValueError("no receiver hits: dense support empty at density "
                         f"{density}")
    ix, iy = np.nonzero(keep)
    x0, x1 = float(xe[ix.min()]), float(xe[ix.max() + 1])
    y0, y1 = float(ye[iy.min()]), float(ye[iy.max() + 1])
    half = max(max(x1 - x0, y1 - y0) / 2.0 + float(margin), float(min_half))
    if half > rhalf:
        half = rhalf
    cx = float(np.clip((x0 + x1) / 2.0, rcx - (rhalf - half),
                       rcx + (rhalf - half)))
    cy = float(np.clip((y0 + y1) / 2.0, rcy - (rhalf - half),
                       rcy + (rhalf - half)))
    return cx, cy, half


def _bary(p, a, b, c):
    """Barycentric weights (w0, w1, w2) of point p in triangle (a, b, c)."""
    v0 = b - a
    v1 = c - a
    v2 = p - a
    d00 = float(v0 @ v0)
    d01 = float(v0 @ v1)
    d11 = float(v1 @ v1)
    d20 = float(v2 @ v0)
    d21 = float(v2 @ v1)
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-30:
        return (1.0, 0.0, 0.0)
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    return (1.0 - v - w, v, w)


def _smooth_normal(p, ie, A, E1, E2, tri_normals):
    """Barycentric interpolation of the mesh's shading normals at a hit.

    tri_normals[ie] is the (3, 3) corner-normal triple for triangle ie, so a
    smooth-shaded mesh refracts continuously instead of per facet. Falls back
    to the geometric face normal if the interpolated normal is degenerate.
    """
    a = A[ie]
    b = a + E1[ie]
    c = a + E2[ie]
    w0, w1, w2 = _bary(p, a, b, c)
    ns = tri_normals[ie]
    n = w0 * ns[0] + w1 * ns[1] + w2 * ns[2]
    nrm = float(np.linalg.norm(n))
    if nrm > 0.0:
        return n / nrm
    n = np.cross(E1[ie], E2[ie])
    nrm = float(np.linalg.norm(n))
    return n / nrm if nrm > 0.0 else n


def _shoot(o, d, geo, eta_c, receiver_z, patch_half, cx, cy, bv=None,
           tri_normals=None):
    """Single interface-pair traversal at one channel index. Returns
    (x, y, path_length_mm_inside, fresnel_weight) or None (miss / TIR /
    off-receiver). The caller applies Beer-Lambert from the path length and
    multiplies the Fresnel transmittance product. bv, when given, is a
    mesh_caustic.bvh.BVH used for the nearest-hit tests (bit-identical to
    the brute-force path)."""
    A, E1, E2 = geo
    if bv is None:
        pvec = np.cross(d, E2)
        det = np.einsum("ij,ij->i", E1, pvec)
        inv = np.zeros_like(det)
        g = np.abs(det) > 1e-14
        inv[g] = 1.0 / det[g]
        ie, hp = _first_hit(o, d, A, E1, E2, pvec, det, inv)
    else:
        ie, hp = _first_hit_bvh(bv, o, d)
    if ie is None:
        return None
    p, n = hp
    if tri_normals is not None:
        n = _smooth_normal(p, ie, A, E1, E2, tri_normals)
    if n @ d > 0.0:
        n = -n
    t = _refract(d, n, 1.0 / eta_c)
    if t is None:
        return None
    T1 = _fresnel_T(-float(d @ n), 1.0 / eta_c)
    p2 = p + t * 1e-6
    if bv is None:
        pvec2 = np.cross(t, E2)
        det2 = np.einsum("ij,ij->i", E1, pvec2)
        inv2 = np.zeros_like(det2)
        g2 = np.abs(det2) > 1e-14
        inv2[g2] = 1.0 / det2[g2]
        ix, hx = _first_hit(p2, t, A, E1, E2, pvec2, det2, inv2, skip=ie)
    else:
        ix, hx = _first_hit_bvh(bv, p2, t, skip=ie)
    if ix is None:
        return None
    q0, n2 = hx
    if tri_normals is not None:
        n2 = _smooth_normal(q0, ix, A, E1, E2, tri_normals)
    if n2 @ t > 0.0:
        n2 = -n2
    t2 = _refract(t, n2, eta_c)
    if t2 is None or abs(t2[2]) < 1e-9:
        return None
    T2 = _fresnel_T(-float(t @ n2), eta_c)
    L = float(np.linalg.norm(q0 - p))
    s = (receiver_z - q0[2]) / t2[2]
    if s <= 0.0:
        return None
    q = q0 + s * t2
    if abs(q[0] - cx) > patch_half or abs(q[1] - cy) > patch_half:
        return None
    return (q[0], q[1], L, T1 * T2)


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
    shoot = opts.get("shoot")
    tri_normals = opts.get("tri_normals")
    accel = bool(opts.get("accel", True)) and shoot is None
    rz = float(receiver["z"])
    ph = float(receiver["patch_half"])
    cxy = receiver.get("center", (0.0, 0.0))
    cx, cy = float(cxy[0]), float(cxy[1])
    geo = _prep(verts, faces)
    bv = _bvh_mod.build(verts, faces) if accel else None
    lo, hi = verts.min(axis=0) - 0.02, verts.max(axis=0) + 0.02
    centre = 0.5 * (lo + hi)
    radius = 0.5 * float(np.linalg.norm(hi - lo)) + 0.01

    for L in lights:
        pos = L.get("position")
        if pos is not None and _point_in_mesh(pos, verts, faces):
            raise ValueError("light inside mesh: move it outside the glass")

    outs = []  # (x, y, channel, weight)

    if shoot is None:
        def shoot(o, d, eta_c):
            return _shoot(o, d, geo, eta_c, rz, ph, cx, cy, bv, tri_normals)

    def shoot_all(o, d):
        if nchan == 1:
            r = shoot(o, d, etas[0])
            if r is None:
                return
            _, _, L, T = r
            for c in range(3):
                outs.append((r[0], r[1], c, float(np.exp(-absorb[c] * L)) * T))
        else:
            for c in range(3):
                r = shoot(o, d, etas[c])
                if r is None:
                    continue
                _, _, L, T = r
                outs.append((r[0], r[1], c, float(np.exp(-absorb[c] * L)) * T))

    for L in lights:
        t = L["type"]
        if t == "sun":
            d = np.asarray(L["direction"], float)
            d /= np.linalg.norm(d)
            right, up, _ = _basis_toward(-d)
            xs = np.linspace(-radius, radius, n_side)
            # Jitter each ray origin inside its grid cell. Without this a
            # regular lattice aliases against the facet lattice: the pattern
            # is deterministic, so it reproduces across ray counts and looks
            # like signal, but two independent renderers do not show it.
            jit = opts.get("jitter")
            rng = np.random.default_rng(int(jit)) if jit else None
            cell = (xs[1] - xs[0]) if n_side > 1 else 0.0
            # Direction jitter samples the sun's disk: every ray then leaves
            # from a different solar point, so the receiver integrates the
            # convolved field directly. A delta-sun (all rays parallel) bins
            # sub-texel caustic structure that no post-convolution can recover.
            half_deg = 0.5 * float(L.get("angle_deg", 0.0))
            sun_jit = bool(opts.get("sun_jitter")) and half_deg > 0.0
            tan_half = np.tan(np.radians(half_deg)) if sun_jit else 0.0
            if sun_jit and rng is None:
                rng = np.random.default_rng(0)
            for x in xs:
                for y in xs:
                    ox, oy = x, y
                    if rng is not None:
                        ox = x + (rng.random() - 0.5) * cell
                        oy = y + (rng.random() - 0.5) * cell
                    o = centre + ox * right + oy * up - 0.5 * d
                    dj = d
                    if sun_jit:
                        a = rng.random() * 2 * np.pi
                        rr = np.sqrt(rng.random()) * tan_half
                        dj = d + rr * (np.cos(a) * right + np.sin(a) * up)
                        dj /= np.linalg.norm(dj)
                    shoot_all(o, dj)
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
            "extent_m": (2 * ph, 2 * ph), "accel": accel}
