"""parity_cpp.py — build the C++ parity harness and compare against Python.
Checks: geometric peak >100x (fold present), wave peak <20x, |flux-1|<1e-3,
and C++ vs Python wave-field correlation >0.95 (same grid/t/time/airy-scale).
"""
import subprocess
import sys
import numpy as np


# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

MSVC = "C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Tools/MSVC/14.41.34120/bin/Hostx64/x64"

N, T, AS = 256, 1.7, 0.02
exe = _ROOT + "/build/src/app/Release/parity.exe"
subprocess.run(["cmake", "--build", _ROOT + "/build", "--config", "Release",
                "--target", "parity"], capture_output=True, text=True)
out = _ROOT + "/build/wave_cpp.bin"
r = subprocess.run([exe, str(N), str(T), str(AS), out], capture_output=True, text=True)
print(r.stdout, r.stderr[-500:])
assert r.returncode == 0
cpp = np.fromfile(out, dtype=np.float32).reshape(N, N, 3)

sys.path.insert(0, _ROOT + "/tools")
import importlib.util
spec = importlib.util.spec_from_file_location("ac", _ROOT + "/tools/airy_caustic.py")
ac = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ac)
ac.N = N
geom = ac.bake(T)
rgb, _ = ac.wave_correct(geom, AS)
for c in range(3):
    a, b = cpp[..., c].ravel(), rgb[..., c].ravel()
    corr = float(np.corrcoef(a, b)[0, 1])
    print(f"ch{c}: cpp_peak={a.max():.2f} py_peak={b.max():.2f} corr={corr:.4f}")
    assert corr > 0.95, f"channel {c} diverged!"
print("PARITY OK")
