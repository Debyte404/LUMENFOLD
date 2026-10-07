"""hard_caustic_ab.py — the test that decides whether this method is worth anything.

The earlier A/B (caustic_vs_cycles.py) used a physical 2.4-degree sun in a bright
room. There, most light reaches the table straight through the glass, Cycles
samples that easily, and the caustic carries too little energy to matter - so the
two methods tied. That is a fair result but it tests the easy case.

This script sets up the HARD case, which is also the case in the reference
photograph: a small source and a dark room, so the caustic is nearly the only
light on the table and it is the subject of the image.

  mode = cycles : Cycles path-traces the caustics itself
  mode = ours   : our baked caustic is injected, Cycles' caustics off

For each mode we render 16/64/256 samples and compare against that mode's own
converged 2048-sample render, so the RMSE is that mode's Monte-Carlo error. We
also record how long each render took, so the comparison is "error per second",
not "error per sample".

Run:  python tools/hard_caustic_ab.py
"""
import json
import os
import subprocess
import time

import numpy as np
from PIL import Image

ROOT = "D:/ValueProjects/caustics"
BLENDER = "C:/Program Files/Blender Foundation/Blender 4.2/blender.exe"
SCENE = f"{ROOT}/tools/blender_scene.py"
CAUSTIC = f"{ROOT}/out/caustic_wavy.png"
OUT = f"{ROOT}/out"
W, H = 480, 300
SAMPLES = [16, 64, 256]
REF_SAMPLES = 2048

# dark room + small source: the caustic is the picture
BASE = ["--w", str(W), "--h", str(H),
        "--sun", "8", "--sun-angle", "0.05",
        "--world", "0.015", "--world-color", "0.30,0.38,0.55",
        "--sun-color", "1.00,0.98,0.95",
        "--gain", "1.0", "--exposure", "0.0", "--no-denoise"]


def render(mode, samples, path):
    cmd = [BLENDER, "--background", "--factory-startup", "--python", SCENE, "--",
           "--caustic", CAUSTIC, "--out", path, "--samples", str(samples), *BASE]
    if mode == "cycles":
        cmd.append("--cycles-caustics")
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    dt = time.time() - t0
    if not os.path.exists(path):
        raise RuntimeError(f"render failed ({mode}, {samples}): {p.stderr[-500:]}")
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32), dt


def rmse(a, b, mask=None):
    d = (a - b)
    if mask is not None:
        d = d[mask]
    return float(np.sqrt((d ** 2).mean()))


def main():
    out = {}
    for mode in ("cycles", "ours"):
        ref, t_ref = render(mode, REF_SAMPLES, f"{OUT}/hard_{mode}_ref.png")
        lum = ref.mean(axis=2)
        # the caustic: the brightest part of the converged image
        mask = lum > np.percentile(lum, 96)
        rows = []
        print(f"[{mode}] reference {REF_SAMPLES}s in {t_ref:.1f}s, "
              f"caustic = {100*mask.mean():.1f}% of frame, "
              f"brightest +{lum.max()-np.median(lum):.0f} levels over median")
        for s in SAMPLES:
            img, dt = render(mode, s, f"{OUT}/hard_{mode}_s{s}.png")
            rows.append({"samples": s, "time_s": dt,
                         "rmse_all": rmse(img, ref),
                         "rmse_caustic": rmse(img, ref, mask)})
            print(f"    {s:5d} samples  {dt:6.1f}s   RMSE all {rows[-1]['rmse_all']:7.2f}"
                  f"   RMSE caustic {rows[-1]['rmse_caustic']:7.2f}")
        out[mode] = {"rows": rows, "ref_time_s": t_ref,
                     "caustic_px_pct": 100 * float(mask.mean())}

    print()
    c, o = out["cycles"], out["ours"]
    print("=" * 78)
    print("DARK ROOM, 0.05 deg SOURCE - the caustic is the subject")
    print(f"{'samples':>8} {'Cycles RMSE':>12} {'ours RMSE':>10} "
          f"{'Cycles time':>12} {'ours time':>10} {'advantage':>10}")
    for rc, ro in zip(c["rows"], o["rows"]):
        adv = rc["rmse_caustic"] / max(ro["rmse_caustic"], 1e-6)
        print(f"{rc['samples']:>8} {rc['rmse_caustic']:>12.2f} "
              f"{ro['rmse_caustic']:>10.2f} {rc['time_s']:>11.1f}s "
              f"{ro['time_s']:>9.1f}s {adv:>9.1f}x")
    print(f"{'':>8} (RMSE measured in the caustic region, vs each mode's own "
          f"{REF_SAMPLES}-sample reference)")
    with open(f"{ROOT}/out/hard_caustic_ab.json", "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
