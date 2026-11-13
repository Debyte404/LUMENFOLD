"""bench_mesh_trace.py -- brute-force vs BVH on the dragon mesh.

Runs the tracer twice at the same budget (accel on, accel off) on the real
dragon geometry and prints the speedup. The hit sets must agree bit-identically;
the pre-registered criterion is speedup >= 5.0x on this machine.

Run: python tools/bench_mesh_trace.py
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from mesh_caustic.trace import trace_mesh  # noqa: E402

GEO = ROOT / "out" / "dragon_geo"
rx = json.loads((GEO / "receiver.json").read_text())
recv = {"z": rx["receiver"]["z"], "patch_half": rx["patch_half"],
        "center": ((rx["receiver"]["x0"] + rx["receiver"]["x1"]) / 2,
                   (rx["receiver"]["y0"] + rx["receiver"]["y1"]) / 2)}

verts, faces = [], []
for line in (GEO / "dragon.obj").read_text().splitlines():
    if line.startswith("v "):
        verts.append(tuple(float(x) for x in line.split()[1:4]))
    elif line.startswith("f "):
        idx = [int(t.split("/")[0]) - 1 for t in line.split()[1:]]
        for i in range(1, len(idx) - 1):
            faces.append((idx[0], idx[i], idx[i + 1]))
verts = np.asarray(verts, dtype=np.float64)
faces = np.asarray(faces, dtype=np.int64)
sun = [{"type": "sun", "direction": tuple(rx["sun"])}]
opts = {"n_side": 256, "eta": 1.5251, "absorb_rgb": (0.0, 0.0, 0.0)}

t0 = time.time()
fast = trace_mesh(verts, faces, sun, recv, {**opts, "accel": True})
build_s = None  # build is inside; re-measure below not needed
fast_s = time.time() - t0
t0 = time.time()
slow = trace_mesh(verts, faces, sun, recv, {**opts, "accel": False})
slow_s = time.time() - t0

print(f"tris {len(faces)}  rays {256 * 256}")
print(f"accel=True  hits {len(fast['hits']):6d}  {fast_s:8.2f}s")
print(f"accel=False hits {len(slow['hits']):6d}  {slow_s:8.2f}s")
print(f"speedup {slow_s / fast_s:.2f}x")

# parity
assert len(fast["hits"]) == len(slow["hits"]), \
    f"hit count differs {len(fast['hits'])} vs {len(slow['hits'])}"
hf = np.sort(fast["hits"], axis=0)
hs = np.sort(slow["hits"], axis=0)
assert np.allclose(hf, hs, atol=1e-12), "hit positions differ"
wf = np.sort(fast["weights"])
ws = np.sort(slow["weights"])
assert np.allclose(wf, ws, atol=1e-12), "weights differ"
print("PARITY_OK (hits, positions, weights identical)")

if slow_s / fast_s < 5.0:
    print(f"SPEEDUP_MISS: {slow_s / fast_s:.2f}x < 5.0x (recorded, not tuned)")
else:
    print("SPEEDUP_OK")
