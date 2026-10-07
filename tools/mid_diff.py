"""mid_diff.py — dump h/gx/gy/flux intermediates from C++ vs Python."""
import subprocess, sys
import numpy as np

N, T = 256, 1.7
BUILD = "D:/ValueProjects/caustics/build"

# C++ side: bake with geometric_only but also dump intermediates — quick hack:
# recompute h/gx/gy in pure python (same formulas) and compare to cpp FIELD only.
# Actually simplest: compare the geometric field pixel-by-pixel structure.

subprocess.run(["cmake", "--build", BUILD, "--config", "Release", "--target", "dump"],
               capture_output=True, text=True)
subprocess.run([f"{BUILD}/src/app/Release/dump.exe", str(N), str(T), "0.02",
                f"{BUILD}/g_cpp.bin", f"{BUILD}/w_cpp.bin"], check=True)
gc = np.fromfile(f"{BUILD}/g_cpp.bin", np.float32).reshape(N, N)

sys.path.insert(0, "D:/ValueProjects/caustics/tools")
import importlib.util
spec = importlib.util.spec_from_file_location("ac", "D:/ValueProjects/caustics/tools/airy_caustic.py")
ac = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ac)
ac.N = N
gp = ac.bake(T)

d = gc - gp
# row/col error profile
rowerr = np.abs(d).mean(axis=1)
colerr = np.abs(d).mean(axis=0)
print("worst rows:", np.argsort(rowerr)[-5:][::-1], rowerr.max())
print("worst cols:", np.argsort(colerr)[-5:][::-1], colerr.max())
print("error at corners:", [float(np.abs(d[a, b])) for a, b in
                            [(0, 0), (0, N - 1), (N - 1, 0), (N - 1, N - 1)]])
# Is error multiplicative? diff/geom on flat
flat = gp < 1.5
ratio = gc[flat] / np.maximum(gp[flat], 1e-6)
print("ratio on flat: mean=%.4f median=%.4f std=%.4f" % (ratio.mean(), np.median(ratio), ratio.std()))
# check edge columns specifically
print("col0 mean abs err:", float(np.abs(d[:, 0]).mean()),
      " col128:", float(np.abs(d[:, 128]).mean()),
      " col255:", float(np.abs(d[:, 255]).mean()))
