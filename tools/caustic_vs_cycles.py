"""caustic_vs_cycles.py — does injecting our caustic beat letting Cycles find it?

For each mode we render at S and at 4S samples. The 4S render is that mode's own
converged reference, so the RMSE between them is that mode's Monte-Carlo noise.
Then we compare how much render time each mode needs to reach the same noise
level in the caustic region.

  mode = cycles : Cycles path-traces the caustics itself (refractive/reflective
                  caustics on), the default way anyone renders a glass.
  mode = ours   : our baked caustic is injected as light and Cycles' own
                  caustics are switched off.

Run:  python tools/caustic_vs_cycles.py
"""
import json
import os
import subprocess
import time

import numpy as np
from PIL import Image


# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

ROOT = _ROOT
BLENDER = "C:/Program Files/Blender Foundation/Blender 4.2/blender.exe"
SCENE = f"{ROOT}/tools/blender_scene.py"
CAUSTIC = f"{ROOT}/out/caustic_wavy.png"
OUT = f"{ROOT}/out"
W, H = 640, 400
BASE = ["--w", str(W), "--h", str(H), "--sun", "8", "--world", "0.34",
        "--world-color", "0.45,0.55,0.80", "--sun-color", "0.98,0.98,1.00",
        "--gain", "0.25", "--exposure", "-0.05", "--no-denoise",
        "--sun-angle", "2.4"]


def render(mode, samples, path):
    cmd = [BLENDER, "--background", "--factory-startup", "--python", SCENE, "--",
           "--caustic", CAUSTIC, "--out", path, "--samples", str(samples), *BASE]
    if mode == "cycles":
        cmd.append("--cycles-caustics")
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    dt = time.time() - t0
    if not os.path.exists(path):
        raise RuntimeError(f"render failed ({mode}, {samples}): {p.stderr[-400:]}")
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
    return a, dt


def rmse(a, b, mask=None):
    d = a - b
    if mask is not None:
        d = d[mask]
    return float(np.sqrt((d ** 2).mean()))


def main():
    res = {}
    for mode in ("cycles", "ours"):
        lo, tlo = render(mode, 64, f"{OUT}/ab_{mode}_s64.png")
        hi, thi = render(mode, 256, f"{OUT}/ab_{mode}_s256.png")
        # the caustic region: where the converged render is brighter than the
        # scene's median (i.e. the light the glass threw onto the table)
        lum = hi.mean(axis=2)
        mask = lum > np.percentile(lum, 92)
        res[mode] = {
            "rmse_all": rmse(lo, hi),
            "rmse_caustic": rmse(lo, hi, mask),
            "caustic_px_pct": 100.0 * mask.mean(),
            "t_64": tlo, "t_256": thi,
            "caustic_gain": float(lum[mask].mean() - np.median(lum)),
        }
        print(f"[{mode}] 64s: {tlo:5.1f}s  256s: {thi:5.1f}s  "
              f"RMSE all {res[mode]['rmse_all']:6.2f}  "
              f"RMSE caustic {res[mode]['rmse_caustic']:6.2f}  "
              f"caustic {res[mode]['caustic_px_pct']:.1f}% of frame")

    print()
    c, o = res["cycles"], res["ours"]
    print(f"caustic region noise at equal samples: Cycles {c['rmse_caustic']:.2f} "
          f"vs ours {o['rmse_caustic']:.2f}  ->  "
          f"{c['rmse_caustic'] / max(o['rmse_caustic'], 1e-6):.1f}x quieter")
    print(f"caustic brightening: Cycles +{c['caustic_gain']:.1f} levels, "
          f"ours +{o['caustic_gain']:.1f} levels")
    print(f"render time at 256 samples: Cycles {c['t_256']:.1f}s, "
          f"ours {o['t_256']:.1f}s")
    with open(f"{ROOT}/out/caustic_vs_cycles.json", "w") as f:
        json.dump(res, f, indent=2)


if __name__ == "__main__":
    main()
