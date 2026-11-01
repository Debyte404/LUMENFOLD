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


if __name__ == "__main__":
    test_sphere_focuses()
    test_open_cube_refused()
    test_inside_point_light_refused()
    test_per_channel_ior_separates_folds()
    test_estimate_scales_with_channels()
    print("MESH_TRACE_TESTS_OK")
