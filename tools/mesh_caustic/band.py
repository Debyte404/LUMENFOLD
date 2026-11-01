"""band.py -- numpy-only band-local Airy correction (no scipy).

The Airy profile comes from the repo's 2048-entry LUT
(`tools/export_airy_lut.py` writes it to JSON); the fold-distance field is a
two-pass chamfer distance transform, also numpy-only, so this runs inside
Blender's bundled Python.
"""
import json
from pathlib import Path

import numpy as np

_LUT = None


def load_lut(path=None):
    """Peak-normalized |Ai(-u)|^2 on u in [-4, 8], uniform grid."""
    global _LUT_META, _LUT
    if _LUT is not None:
        return _LUT
    p = Path(path) if path else Path(__file__).resolve().parent / "airy_lut.json"
    d = json.loads(p.read_text(encoding="ascii"))
    _LUT_META = (float(d["u_min"]), float(d["u_max"]))
    _LUT = np.asarray(d["values"], dtype=np.float64)
    return _LUT


_LUT_META = (-4.0, 8.0)


def _airy(s, lut):
    """s signed in Airy units; linear interpolation on the [-4, 8] table."""
    u_min, u_max = _LUT_META
    n = len(lut)
    x = (np.clip(np.asarray(s, dtype=np.float64), u_min, u_max) - u_min) / (u_max - u_min) * (n - 1)
    lo = np.floor(x).astype(np.int64)
    hi = np.minimum(lo + 1, n - 1)
    f = x - lo
    return (1.0 - f) * lut[lo] + f * lut[hi]


def ridge_distance(field, m_per_px):
    """Distance (metres) from each pixel to the bright ridge.

    Ridge = pixels above the 95th percentile of positive values. Two-pass
    chamfer (3-4) distance transform, numpy-only.
    """
    pos = field[field > 0]
    if pos.size == 0:
        return np.full_like(field, np.inf, dtype=np.float64)
    # >= : a flat-topped bright band sits exactly ON its own percentile.
    ridge = field >= np.percentile(pos, 95)
    if not ridge.any() or ridge.all():
        return np.zeros_like(field, dtype=np.float64)
    # cost: 0 on ridge, large elsewhere; forward/backward chamfer passes
    INF = 1e9
    d = np.where(ridge, 0.0, INF)
    r, c = d.shape
    for i in range(r):
        for j in range(c):
            if i > 0:
                d[i, j] = min(d[i, j], d[i - 1, j] + 3.0)
            if j > 0:
                d[i, j] = min(d[i, j], d[i, j - 1] + 3.0)
            if i > 0 and j > 0:
                d[i, j] = min(d[i, j], d[i - 1, j - 1] + 4.0)
            if i > 0 and j < c - 1:
                d[i, j] = min(d[i, j], d[i - 1, j + 1] + 4.0)
    for i in range(r - 1, -1, -1):
        for j in range(c - 1, -1, -1):
            if i < r - 1:
                d[i, j] = min(d[i, j], d[i + 1, j] + 3.0)
            if j < c - 1:
                d[i, j] = min(d[i, j], d[i, j + 1] + 3.0)
            if i < r - 1 and j < c - 1:
                d[i, j] = min(d[i, j], d[i + 1, j + 1] + 4.0)
            if i < r - 1 and j > 0:
                d[i, j] = min(d[i, j], d[i + 1, j - 1] + 4.0)
    return d / 3.0 * m_per_px


def correct(field, signed_distance, band_width, airy_scale, lut=None):
    """Redistribute the band's own geometric energy by the Airy profile.

    field: geometric irradiance (H, W); signed_distance: metres, same shape;
    band_width: half-width of detected band, metres; airy_scale: display
    width w, metres. Band flux strictly conserved by construction.
    """
    lut = load_lut() if lut is None else np.asarray(lut, dtype=np.float64)
    out = field.copy()
    band = np.abs(signed_distance) <= band_width
    if not band.any():
        return out
    energy = float(field[band].sum())
    if energy <= 0.0:
        return out
    s = np.clip(signed_distance[band] / airy_scale, -4.0, 8.0)
    w = _airy(s, lut)
    w = w / w.sum()
    out[band] = energy * w
    return out
