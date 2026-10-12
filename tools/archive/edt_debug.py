"""edt_debug.py — test our CDT vs scipy exact EDT (standalone, via cmake-built .exe)."""
import subprocess
import numpy as np
from scipy.ndimage import distance_transform_edt


# Repo root, derived rather than hardcoded.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
EDTSRC_PATH = _ROOT + "/src/app/edt.cpp"
BUILD = _ROOT + "/build"

# Build via cmake (already proven to find libs).
subprocess.run(["cmake", "--build", BUILD, "--config", "Release", "--target", "edt"],
               check=True, capture_output=True)

W, H = 256, 256
rng = np.random.default_rng(0)
feat = (rng.random((H, W)) < 0.02).astype(np.uint8)
feat.tofile(f"{BUILD}/feat.bin")
subprocess.run([f"{BUILD}/src/app/Release/edt.exe", str(W), str(H),
                f"{BUILD}/feat.bin", f"{BUILD}/d2.bin"], check=True)
d2 = np.fromfile(f"{BUILD}/d2.bin", np.float32).reshape(H, W)
ref = distance_transform_edt(~feat.astype(bool)) ** 2
print("max abs error vs scipy edt^2:", float(np.max(np.abs(d2 - ref))))
print("d2[128,128]=", d2[128, 128], " scipy=", ref[128, 128])
