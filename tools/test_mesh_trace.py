"""Task 2 RED: generalized tracer with light types and named refusals."""
import numpy as np

from mesh_caustic.trace import trace_mesh


def _sphere(r=0.035, n_lat=12, n_lon=24):
    verts = [(0.0, 0.0, r)]
    for i in range(1, n_lat):
        th = np.pi * i / n_lat
        for j in range(n_lon):
            ph = 2 * np.pi * j / n_lon
            verts.append((r * np.sin(th) * np.cos(ph),
                          r * np.sin(th) * np.sin(ph), r * np.cos(th)))
    verts.append((0.0, 0.0, -r))
    faces = []
    for j in range(n_lon):
        faces.append((0, 1 + j, 1 + (j + 1) % n_lon))
    for i in range(n_lat - 2):
        r0, r1 = 1 + i * n_lon, 1 + (i + 1) * n_lon
        for j in range(n_lon):
            a, b = r0 + j, r0 + (j + 1) % n_lon
            c, d = r1 + j, r1 + (j + 1) % n_lon
            faces += [(a, b, d), (a, d, c)]
    last = 1 + (n_lat - 2) * n_lon
    for j in range(n_lon):
        faces.append((len(verts) - 1, last + (j + 1) % n_lon, last + j))
    return np.array(verts), np.array(faces, dtype=np.int64)


def _recv():
    return {"z": -0.10, "patch_half": 0.16}


def test_sphere_focuses():
    v, f = _sphere()
    out = trace_mesh(v, f, [{"type": "sun", "direction": (0.8, 0.42, -0.43)}],
                     _recv(), {"n_side": 60})
    assert len(out["hits"]) > 100, f"only {len(out['hits'])} hits"


def test_open_cube_refused():
    v = np.array([[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0]], float)
    f = np.array([[0, 1, 2]], np.int64)  # single triangle: open edges
    try:
        trace_mesh(v, f, [{"type": "sun", "direction": (0, 0, -1)}], _recv(), {"n_side": 8})
    except ValueError as e:
        assert "not watertight" in str(e), e
    else:
        raise AssertionError("open mesh did not raise")


def test_inside_point_light_refused():
    v, f = _sphere()
    try:
        trace_mesh(v, f, [{"type": "point", "position": (0, 0, 0)}], _recv(), {"n_side": 8})
    except ValueError as e:
        assert "inside" in str(e), e
    else:
        raise AssertionError("inside light did not raise")


def test_per_channel_ior_separates_folds():
    import numpy as np
    from mesh_caustic.trace import ior_rgb
    v, f = _sphere()
    sun = [{"type": "sun", "direction": (0.8, 0.42, -0.43)}]
    kw = {"n_side": 60}
    a = trace_mesh(v, f, sun, _recv(), dict(kw, eta=1.5251))
    assert len(a["hits"]) > 100
    # BK7-anchored dispersion must order R < G < B in index (red bends least)
    r_ior, g_ior, b_ior = ior_rgb(1.525)
    assert r_ior < g_ior < b_ior, (r_ior, g_ior, b_ior)
    # ...and distinct per-channel etas must land hits in different bins
    b = trace_mesh(v, f, sun, _recv(), dict(kw, eta=(1.00, 1.5251, 2.00)))
    assert len(b["hits"]) > 100
    hr, _, _ = np.histogram2d(*b["hits"][b["chan"] == 0].T, bins=16)
    hb, _, _ = np.histogram2d(*b["hits"][b["chan"] == 2].T, bins=16)
    assert not np.allclose(hr, hb)


def test_estimate_scales_with_channels():
    from mesh_caustic.trace import estimate_seconds
    assert estimate_seconds(1000, 48, 3) > 2.5 * estimate_seconds(1000, 48, 1)


# ---- BVH build and traversal -------------------------------------------------

def test_bvh_partitions_every_triangle_once():
    from mesh_caustic import bvh
    v, f = _sphere()
    bb = bvh.build(v, f)
    assert len(bb.order) == len(f)
    assert sorted(bb.orig.tolist()) == list(range(len(f)))
    assert len(bb.bounds) <= 2 * len(f) + 1, "a build bug doubles node count"
    root = bb.bounds[0]
    assert (root[:3] <= v.min(axis=0) + 1e-9).all()
    assert (root[3:] >= v.max(axis=0) - 1e-9).all()


def test_bvh_tie_breaks_to_lowest_index():
    from mesh_caustic import bvh
    v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]] * 2, float)
    f = np.array([[0, 1, 2], [3, 4, 5]])
    b = bvh.build(v, f, leaf_size=1)
    hit = bvh.nearest(b, np.array([0.2, 0.2, 1.0]), np.array([0.0, 0.0, -1.0]))
    assert hit is not None and hit[0] == 0 and abs(hit[1] - 1.0) < 1e-12


def test_bvh_skip_and_degenerate():
    from mesh_caustic import bvh
    v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 0]], float)
    f = np.array([[0, 1, 2], [0, 1, 3]])  # second triangle is degenerate
    b = bvh.build(v, f, leaf_size=1)
    o, d = np.array([0.2, 0.2, 1.0]), np.array([0.0, 0.0, -1.0])
    hit = bvh.nearest(b, o, d)
    assert hit is not None and hit[0] == 0 and abs(hit[1] - 1.0) < 1e-12
    assert bvh.nearest(b, o, d, skip=0) is None


def test_bvh_hits_on_a_shared_edge():
    from mesh_caustic import bvh
    v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], float)
    f = np.array([[0, 1, 2], [1, 3, 2]])
    b = bvh.build(v, f, leaf_size=1)
    o, d = np.array([0.5, 0.5, 1.0]), np.array([0.0, 0.0, -1.0])
    hit = bvh.nearest(b, o, d)
    assert hit is not None and abs(hit[1] - 1.0) < 1e-12


def test_smooth_normal_interpolates_corner_normals():
    from mesh_caustic.trace import _smooth_normal
    A = np.array([[0.0, 0.0, 0.0]])
    E1 = np.array([[1.0, 0.0, 0.0]])
    E2 = np.array([[0.0, 1.0, 0.0]])
    tri = np.array([[[0.0, 0.0, 1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]])
    n = _smooth_normal(np.array([1.0 / 3.0, 1.0 / 3.0, 0.0]), 0, A, E1, E2, tri)
    exp = (np.array([0.0, 0.0, 1.0]) + np.array([1.0, 0.0, 0.0])
           + np.array([0.0, 1.0, 0.0])) / 3.0
    exp /= np.linalg.norm(exp)
    assert np.allclose(n, exp), (n, exp)


def test_bvh_origin_inside_mesh():
    from mesh_caustic import bvh
    v, f = _sphere()
    b = bvh.build(v, f)
    hit = bvh.nearest(b, np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]))
    assert hit is not None and hit[1] > 0.0

def test_bvh_matches_bruteforce_on_random_rays():
    from mesh_caustic import bvh
    from mesh_caustic.trace import _prep, _first_hit
    v, f = _sphere()
    A, E1, E2 = _prep(v, f)
    bb = bvh.build(v, f)
    rng = np.random.default_rng(7)
    lo, hi = v.min(axis=0) - 0.1, v.max(axis=0) + 0.1
    for _ in range(2000):
        o = rng.uniform(lo, hi)
        d = rng.normal(size=3)
        d /= np.linalg.norm(d)
        pvec = np.cross(d, E2)
        det = np.einsum("ij,ij->i", E1, pvec)
        inv = np.zeros_like(det)
        good = np.abs(det) > 1e-14
        inv[good] = 1.0 / det[good]
        bf = _first_hit(o, d, A, E1, E2, pvec, det, inv)
        ac = bvh.nearest(bb, o, d)
        assert (ac is None) == (bf[0] is None)
        if ac is not None:
            assert ac[0] == bf[0], "nearest face must match brute force"
            assert np.allclose(o + ac[1] * d, bf[1][0], atol=1e-9)


# ---- frame_patch: the fan-framed receiver patch ------------------------------

def _bw(recv, bins=64):
    return 2.0 * recv["half"] / bins


def test_frame_patch_hugs_hits_with_margin():
    from mesh_caustic.trace import frame_patch
    hits = np.array([[0.0, 0.0], [0.4, -0.3], [0.1, 0.2]])
    recv = {"cx": 0.0, "cy": 0.0, "half": 4.18, "z": -0.28}
    cx, cy, half = frame_patch(hits, recv, margin=0.15)
    # square patch around the dense support: x spans 0.4, y spans 0.5
    # -> side 0.5 (+ bin quantisation: the bbox is read off bin edges)
    tol = 1.5 * _bw(recv)
    assert abs(half - (0.25 + 0.15)) < tol, half
    assert abs(cx - 0.2) < tol and abs(cy - (-0.05)) < tol, (cx, cy)


def test_frame_patch_drops_sparse_spray():
    from mesh_caustic.trace import frame_patch
    recv = {"cx": 0.0, "cy": 0.0, "half": 4.18, "z": -0.28}
    # one tight cluster, deterministically inside a single probe bin
    # (bin width 8.36/64 = 0.13 m; the cluster spans 4 mm), plus one stray
    # hit 4.2 m out
    dense = 0.05 + np.linspace(-0.002, 0.002, 20)[:, None] * np.ones((1, 2))
    hits = np.vstack([dense, [[3.0, 3.0]]])
    cx, cy, half = frame_patch(hits, recv, margin=0.15)
    # one stray hit 4.2 m out must not stretch the frame to it
    assert half < 1.0, half
    _, _, half_all = frame_patch(hits, recv, margin=0.15, density=0.0)
    assert half_all > 1.5 and half_all > 5 * half, \
        f"density 0 must keep the spray: {half_all:.2f} vs {half:.2f}"


def test_frame_patch_clamps_inside_receiver():
    from mesh_caustic.trace import frame_patch
    hits = np.array([[3.9, -3.9], [3.95, -3.95]])
    recv = {"cx": 0.0, "cy": 0.0, "half": 4.18, "z": -0.28}
    cx, cy, half = frame_patch(hits, recv, margin=0.5, min_half=0.05)
    assert half <= 4.18 + 1e-12
    assert abs(cx) + half <= 4.18 + 1e-9, "frame must stay inside the receiver"
    assert abs(cy) + half <= 4.18 + 1e-9


def test_frame_patch_enforces_min_half():
    from mesh_caustic.trace import frame_patch
    hits = np.array([[0.0, 0.0]])
    recv = {"cx": 0.0, "cy": 0.0, "half": 4.18, "z": -0.28}
    _, _, half = frame_patch(hits, recv, margin=0.01, min_half=0.3)
    assert half >= 0.3 - 1e-12


def test_frame_patch_empty_hits_raise():
    from mesh_caustic.trace import frame_patch
    try:
        frame_patch(np.zeros((0, 2)), {"cx": 0, "cy": 0, "half": 4.18}, 0.15)
    except ValueError as e:
        assert "no receiver hits" in str(e)
    else:
        raise AssertionError("empty probe hits must raise the named refusal")


# ---- band.correct feather ----------------------------------------------------

def _grid_with_exact_distance():
    """Ridge field with an EXACT distance map (metres, 1 m/px) so the feather
    alpha can be asserted at exact distances."""
    yy, xx = np.mgrid[0:32, 0:32]
    field = np.exp(-((yy - 16) ** 2) / 2.0)
    d = np.abs(yy - 16.0)
    return field, d


def test_feather_zero_is_bit_identical():
    from mesh_caustic.band import correct
    field, d = _grid_with_exact_distance()
    ref = correct(field, d, 4.0, 0.5, feather=0.0)
    old = correct(field, d, 4.0, 0.5)
    assert np.array_equal(ref, old), "feather=0 must not change the operator"


def test_feather_edge_returns_to_raw_inner_keeps_profile():
    from mesh_caustic.band import correct
    field, d = _grid_with_exact_distance()
    bw, airy = 4.0, 0.5
    strict = correct(field, d, bw, airy, feather=0.0)
    feath = correct(field, d, bw, airy, feather=0.5)
    inner = d <= bw * 0.5                     # alpha == 1 zone
    outer = d == bw                           # alpha == 0 zone
    edge = (d > bw * 0.5) & (d <= bw)         # the blend
    assert np.allclose(feath[inner], strict[inner]), \
        "the inner band keeps the strict profile"
    assert np.allclose(feath[outer], field[outer]), \
        "the band edge returns to the raw field"
    lo = np.minimum(strict[edge], field[edge])
    hi = np.maximum(strict[edge], field[edge])
    assert (feath[edge] >= lo - 1e-12).all() and (feath[edge] <= hi + 1e-12).all(), \
        "the blend must stay between the profile and the raw field"


def test_feather_leaves_outside_band_alone():
    from mesh_caustic.band import correct
    field, d = _grid_with_exact_distance()
    feath = correct(field, d, 4.0, 0.5, feather=0.5)
    outside = d > 4.0
    assert np.array_equal(feath[outside], field[outside])


if __name__ == "__main__":
    test_sphere_focuses()
    test_open_cube_refused()
    test_inside_point_light_refused()
    test_per_channel_ior_separates_folds()
    test_estimate_scales_with_channels()
    test_frame_patch_hugs_hits_with_margin()
    test_frame_patch_drops_sparse_spray()
    test_frame_patch_clamps_inside_receiver()
    test_frame_patch_enforces_min_half()
    test_frame_patch_empty_hits_raise()
    test_feather_zero_is_bit_identical()
    test_feather_edge_returns_to_raw_inner_keeps_profile()
    test_feather_leaves_outside_band_alone()
    test_bvh_matches_bruteforce_on_random_rays()
    test_bvh_partitions_every_triangle_once()
    test_bvh_tie_breaks_to_lowest_index()
    test_bvh_skip_and_degenerate()
    test_bvh_hits_on_a_shared_edge()
    test_bvh_origin_inside_mesh()
    print("MESH_TRACE_TESTS_OK")
