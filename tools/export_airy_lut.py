"""export_airy_lut.py -- Airy profile -> Blender-readable JSON (numpy-only runtime).

Run:  python tools/export_airy_lut.py
Writes tools/mesh_caustic/airy_lut.json: {"u_min": -4.0, "u_max": 8.0,
"values": [...3072...]} of peak-normalized |Ai(-u)|^2 sampled uniformly.
u >= 0 matches src/render/airy_lut.hpp (same scipy source); u < 0 is the
physical exponential shadow-side decay, which the [0, 8] C++ table cannot
represent. Export needs scipy; Blender runtime needs only numpy.
"""
import json

import numpy as np

import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

from scipy.special import airy

STEP = 8.0 / 2047.0
N = 3072  # u = -4 .. +8 at the hpp step
u = -4.0 + np.arange(N) * STEP
ai = airy(-u)[0]
vals = (ai * ai)
vals = (vals / vals.max()).tolist()
assert len(vals) == N and abs(max(vals) - 1.0) < 1e-12
peak_u = float(u[int(np.argmax(vals))])
assert 0.9 < peak_u < 1.15, peak_u  # analytic +1.0188 on the lit side
out = _ROOT + "/tools/mesh_caustic/airy_lut.json"
with open(out, "w", encoding="ascii") as f:
    json.dump({"u_min": -4.0, "u_max": 8.0, "values": vals}, f)
print(f"wrote {out} peak=1.0 at u={peak_u:.4f} n={N}")
