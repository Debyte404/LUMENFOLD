import numpy as np

class BVH:
    __slots__ = ("bounds", "left", "right", "start", "count", "order", "orig",
                 "pos_of", "A", "E1", "E2")

    def __init__(self, bounds, left, right, start, count, order, orig, pos_of, A, E1, E2):
        self.bounds = np.asarray(bounds, dtype=np.float64).reshape(-1, 6)
        self.left = np.asarray(left, dtype=np.int64)
        self.right = np.asarray(right, dtype=np.int64)
        self.start = np.asarray(start, dtype=np.int64)
        self.count = np.asarray(count, dtype=np.int64)
        self.order = np.asarray(order, dtype=np.int64)
        self.orig = np.asarray(orig, dtype=np.int64)
        self.pos_of = np.asarray(pos_of, dtype=np.int64)
        self.A = np.asarray(A, dtype=np.float64)
        self.E1 = np.asarray(E1, dtype=np.float64)
        self.E2 = np.asarray(E2, dtype=np.float64)


def build(verts, faces, leaf_size=8):
    """Build a BVH over the triangles of (verts, faces)."""
    verts = np.asarray(verts, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    n_tri = len(faces)
    A = verts[faces[:, 0]]
    E1 = verts[faces[:, 1]] - A
    E2 = verts[faces[:, 2]] - A
    centers = (verts[faces[:, 0]] + verts[faces[:, 1]] + verts[faces[:, 2]]) / 3.0
    tmin = np.min(np.stack([verts[faces[:, 0]], verts[faces[:, 1]],
                            verts[faces[:, 2]]], axis=1), axis=1)
    tmax = np.max(np.stack([verts[faces[:, 0]], verts[faces[:, 1]],
                            verts[faces[:, 2]]], axis=1), axis=1)

    PAD = 1e-9
    bounds = []
    left = []
    right = []
    start = []
    count = []
    order = []

    def new_node(tmin_n, tmax_n):
        idx = len(bounds)
        bounds.append(np.concatenate([tmin_n - PAD, tmax_n + PAD]))
        left.append(-1)
        right.append(-1)
        start.append(-1)
        count.append(0)
        return idx

    def build_recursive(face_idx):
        face_idx = np.asarray(face_idx, dtype=np.int64)
        n = len(face_idx)
        tmin_n = tmin[face_idx].min(axis=0)
        tmax_n = tmax[face_idx].max(axis=0)
        ni = new_node(tmin_n, tmax_n)
        if n <= leaf_size or n <= 1:
            start[ni] = len(order)
            count[ni] = n
            order.extend(face_idx.tolist())
            return ni
        ctrs = centers[face_idx]
        span = ctrs.max(axis=0) - ctrs.min(axis=0)
        ax = int(np.argmax(span))
        if not np.isfinite(span[ax]) or span[ax] < 1e-18:
            ax = 0
            key = np.arange(n)
        else:
            key = ctrs[:, ax]
        order_local = np.argsort(key, kind="stable")
        mid = n // 2
        if mid < 1:
            mid = 1
        if mid >= n:
            mid = n - 1
        left_faces = face_idx[order_local[:mid]]
        right_faces = face_idx[order_local[mid:]]
        if len(left_faces) == 0 or len(right_faces) == 0:
            start[ni] = len(order)
            count[ni] = n
            order.extend(face_idx.tolist())
            return ni
        li = build_recursive(left_faces)
        ri = build_recursive(right_faces)
        left[ni] = li
        right[ni] = ri
        return ni

    if n_tri == 0:
        ni = new_node(np.zeros(3), np.zeros(3))
        start[ni] = 0
        count[ni] = 0
    else:
        build_recursive(np.arange(n_tri, dtype=np.int64))

    bounds = np.asarray(bounds, dtype=np.float64)
    left = np.asarray(left, dtype=np.int64)
    right = np.asarray(right, dtype=np.int64)
    start = np.asarray(start, dtype=np.int64)
    count = np.asarray(count, dtype=np.int64)
    order = np.asarray(order, dtype=np.int64)
    orig = order.copy()
    pos_of = np.empty(n_tri, dtype=np.int64)
    if n_tri > 0:
        pos_of[order] = np.arange(n_tri, dtype=np.int64)
    A_o = A[order]
    E1_o = E1[order]
    E2_o = E2[order]
    return BVH(bounds, left, right, start, count, order, orig, pos_of, A_o, E1_o, E2_o)


def _slab(o, d, lo, hi):
    with np.errstate(divide="ignore", invalid="ignore"):
        t1 = (lo - o) / d
        t2 = (hi - o) / d
    tmin_axis = np.minimum(t1, t2)
    tmax_axis = np.maximum(t1, t2)
    # d ~ 0 on an axis where o is outside the slab -> no overlap
    zero = np.abs(d) < 1e-30
    if np.any(zero & ((o < lo) | (o > hi))):
        return None
    if zero.any():
        tmin_axis = np.where(zero, -np.inf, tmin_axis)
        tmax_axis = np.where(zero, np.inf, tmax_axis)
    t0 = float(np.max(tmin_axis))
    t1v = float(np.min(tmax_axis))
    if not np.isfinite(t0) or not np.isfinite(t1v) or t1v < t0:
        return None
    return t0, t1v


def nearest(bvh, o, d, eps=1e-9, skip=-1):
    """Nearest hit face index and distance, or None. Matches _first_hit semantics."""
    o = np.asarray(o, dtype=np.float64).reshape(3)
    d = np.asarray(d, dtype=np.float64).reshape(3)
    nrm = float(np.linalg.norm(d))
    if nrm < 1e-30:
        return None
    d = d / nrm

    best_dist = np.inf
    best_face = -1
    pending = [(0, 0.0)]

    while pending:
        i = int(np.argmin([e for _, e in pending]))
        ni, entry_t = pending.pop(i)
        if entry_t > best_dist + 1e-15:
            continue
        lo = bvh.bounds[ni, :3]
        hi = bvh.bounds[ni, 3:]
        slab = _slab(o, d, lo, hi)
        if slab is None:
            continue
        t0, t1 = slab
        if t1 < max(t0, 0.0) - 1e-15:
            continue
        if t0 > best_dist + 1e-15:
            continue
        if bvh.count[ni] > 0:
            s = int(bvh.start[ni])
            c = int(bvh.count[ni])
            A = bvh.A[s:s + c]
            E1 = bvh.E1[s:s + c]
            E2 = bvh.E2[s:s + c]
            orig = bvh.orig[s:s + c]
            pvec = np.cross(d, E2)
            det = np.einsum("ij,ij->i", E1, pvec)
            inv = np.zeros_like(det)
            good = np.abs(det) > 1e-14
            inv[good] = 1.0 / det[good]
            tvec = o - A
            qvec = np.cross(tvec, E1)
            u = np.einsum("ij,ij->i", tvec, pvec) * inv
            v = np.einsum("ij,j->i", qvec, d) * inv
            dist = np.einsum("ij,ij->i", qvec, E2) * inv
            ok = (good & (u >= 0.0) & (u <= 1.0) & (v >= 0.0)
                  & (u + v <= 1.0) & (dist > 1e-9))
            for k in range(c):
                if not ok[k]:
                    continue
                of = int(orig[k])
                if of == skip:
                    continue
                dd = float(dist[k])
                if best_face < 0 or dd < best_dist or (dd == best_dist and of < best_face):
                    best_dist = dd
                    best_face = of
        else:
            li, ri = int(bvh.left[ni]), int(bvh.right[ni])
            children = []
            for ci in (li, ri):
                if ci < 0:
                    continue
                clo = bvh.bounds[ci, :3]
                chi = bvh.bounds[ci, 3:]
                cslab = _slab(o, d, clo, chi)
                if cslab is None:
                    continue
                ct0, ct1 = cslab
                if ct1 < max(ct0, 0.0) - 1e-15:
                    continue
                if ct0 > best_dist + 1e-15:
                    continue
                children.append((ci, max(ct0, 0.0)))
            children.sort(key=lambda x: -x[1])
            for ci, et in children:
                pending.append((ci, et))

    if best_face < 0:
        return None
    return int(best_face), float(best_dist)
