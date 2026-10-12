"""bisect_parity.py — find WHERE cpp and python diverge: geometric vs wave."""
import subprocess, os, sys
import numpy as np


# Repo root, derived rather than hardcoded.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
MSVC = "C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Tools/MSVC/14.41.34120/bin/Hostx64/x64"
SDK = "C:/Program Files (x86)/Windows Kits/10"
VC = MSVC
MSVCROOT = "C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools"
env = dict(os.environ)
env["PATH"] = VC + ";" + env.get("PATH", "")
env["INCLUDE"] = (SDK + "/Include/10.0.22621.0/ucrt;" +
                  MSVCROOT + "/VC/Tools/MSVC/14.41.34120/include;" + env.get("INCLUDE", ""))
env["LIB"] = (SDK + "/Lib/10.0.22621.0/ucrt/x64;" +
              MSVCROOT + "/VC/Tools/MSVC/14.41.34120/lib/x64;" + env.get("LIB", ""))

# Build via cmake (proven to find libs).
subprocess.run(["cmake", "--build", _ROOT + "/build", "--config", "Release",
                "--target", "dump"], capture_output=True, text=True)

N, T, AS = 256, 1.7, 0.02
subprocess.run([_ROOT + "/build/src/app/Release/dump.exe",
                str(N), str(T), str(AS),
                _ROOT + "/build/g_cpp.bin",
                _ROOT + "/build/w_cpp.bin"], check=True)
gc = np.fromfile(_ROOT + "/build/g_cpp.bin", np.float32).reshape(N, N)
wc = np.fromfile(_ROOT + "/build/w_cpp.bin", np.float32).reshape(N, N, 3)

sys.path.insert(0, _ROOT + "/tools")
import importlib.util
spec = importlib.util.spec_from_file_location("ac", _ROOT + "/tools/airy_caustic.py")
ac = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ac)
ac.N = N
gp = ac.bake(T)
rp, _ = ac.wave_correct(gp, AS)

print("GEOMETRIC corr:", float(np.corrcoef(gc.ravel(), gp.ravel())[0, 1]),
      " maxerr:", float(np.max(np.abs(gc - gp))))
for c in range(3):
    a, b = wc[..., c].ravel(), rp[..., c].ravel()
    print(f"WAVE ch{c} corr:", float(np.corrcoef(a, b)[0, 1]),
          " mae:", float(np.abs(a - b).mean()),
          " cpp_peak:", float(a.max()), " py_peak:", float(b.max()))
