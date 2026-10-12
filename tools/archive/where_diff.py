"""where_diff.py — inspect the geometric field diff pattern."""
import subprocess, sys
import numpy as np


# Repo root, derived rather than hardcoded.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
N, T, AS = 256, 1.7, 0.02
subprocess.run(["cmake", "--build", _ROOT + "/build", "--config", "Release",
                "--target", "dump"], capture_output=True, text=True)
subprocess.run([_ROOT + "/build/src/app/Release/dump.exe",
                str(N), str(T), str(AS),
                _ROOT + "/build/g_cpp.bin",
                _ROOT + "/build/w_cpp.bin"], check=True)
gc = np.fromfile(_ROOT + "/build/g_cpp.bin", np.float32).reshape(N, N)

sys.path.insert(0, _ROOT + "/tools")
import importlib.util
spec = importlib.util.spec_from_file_location("ac", _ROOT + "/tools/airy_caustic.py")
ac = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ac)
ac.N = N
gp = ac.bake(T)

d = np.abs(gc - gp)
i = int(np.argmax(d))
yy, xx = divmod(i, N)
print("max diff at (y,x)=", yy, xx)
print("  cpp=", gc[yy, xx], " py=", gp[yy, xx], " diff=", d[yy, xx])
print("diff percentiles:", {p: float(np.percentile(d, p)) for p in [50, 90, 99, 99.9, 100]})
print("corr:", float(np.corrcoef(gc.ravel(), gp.ravel())[0, 1]))
print("corr on log1p:", float(np.corrcoef(np.log1p(gc).ravel(), np.log1p(gp).ravel())[0, 1]))
# Where is error concentrated: near ridges (high geom) or flat (geom~1)?
flat = gp < 2
print("mean diff on flat(geom<2) pixels:", float(d[flat].mean()), " n=", int(flat.sum()))
print("mean diff on ridge(geom>=2) pixels:", float(d[~flat].mean()), " n=", int((~flat).sum()))
thr = np.percentile(gp, 98)
foldp = gp > thr
print("fold pixels (py 98th pct):", int(foldp.sum()))
print("mean diff among fold:", float(d[foldp].mean()), "max:", float(d[foldp].max()))
# fraction of fold-mask disagreement at same threshold on cpp
foldc = gc > thr
disagree = int((foldp ^ foldc).sum())
print("fold-mask disagreement at same thr:", disagree, "/", int(foldp.sum()))
