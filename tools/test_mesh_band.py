"""Task 1 RED: band correction + LUT export must exist and conserve flux."""
import numpy as np

from mesh_caustic.band import correct, ridge_distance, load_lut


def test_flux_conserved():
    field = np.ones((64, 64))
    d = np.linspace(-0.01, 0.01, 64)[None, :].repeat(64, axis=0)
    out = correct(field, d, 0.002, 6.77e-6, load_lut())
    band = np.abs(d) <= 0.002
    assert abs(out[band].sum() / field[band].sum() - 1.0) < 1e-9


def test_ridge_distance_metres():
    field = np.ones((64, 64))
    field[30:34, :] = 5.0
    d = ridge_distance(field, m_per_px=0.001)
    assert d.shape == (64, 64)
    assert abs(d[32, 32]) < 1e-12
    assert d[0, 0] > 0.02


if __name__ == "__main__":
    test_flux_conserved()
    test_ridge_distance_metres()
    print("MESH_BAND_TESTS_OK")
