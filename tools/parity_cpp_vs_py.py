"""parity_cpp_vs_py.py — C++ baker vs the Python model, matched parameters.

Guards the port: the C++ path may only be trusted if it reproduces the Python
reference at the same t / airy_scale / grid. Also checks the intensity ceiling
and reports the fold-band fraction.
"""
import sys

import numpy as np


# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

sys.path.insert(0, _ROOT + "/tools")
import fold_diag as fd          # noqa: E402
import band_flux_test as bft    # noqa: E402

N, T, SCALE = 512, 1.7, 1.0
CEIL = 8.10

g, Hx, Hy = fd.geom_field(T, N)
det = fd.jacobian_det(Hx, Hy, N)
fold = np.abs(det) < np.percentile(np.abs(det), 2.0)
pyrgb = bft.correct_bandlocal(g, SCALE, fold)

base = _ROOT + "/out"
cpp = np.fromfile(f"{base}/w_s.bin", dtype=np.float32, count=N * N * 3).reshape(N, N, 3)
cppg = np.fromfile(f"{base}/g_s.bin", dtype=np.float32, count=N * N).reshape(N, N)

print(f"grid {N}^2  t={T}  airy_scale={SCALE}")
print(f"geometric : C++ max={cppg.max():9.3f}  py max={g.max():9.3f}  "
      f"maxdiff={np.abs(cppg - g).max():.3e}")
for c, nm in enumerate("RGB"):
    a, b = cpp[..., c], pyrgb[..., c]
    print(f"wave {nm}    : C++ max={a.max():9.3f}  py max={b.max():9.3f}  "
          f"maxdiff={np.abs(a - b).max():.3e}  mean|d|={np.abs(a - b).mean():.3e}")

rel = np.abs(cpp - pyrgb).max() / max(pyrgb.max(), 1e-9)
print(f"\npeak-relative C++/py disagreement: {rel:.4f} ({rel*100:.2f}%)")
print(f"fold band: {fold.mean()*100:.2f}% of grid (both implementations use the 2nd "
      f"percentile of |det J|)")
print(f"ceiling   : C++ {cpp.max():.3f}  py {pyrgb.max():.3f}  ceiling {CEIL}  "
      f"C++ ok={cpp.max() <= CEIL}  py ok={pyrgb.max() <= CEIL}")
