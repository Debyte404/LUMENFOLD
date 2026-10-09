"""realistic_showdown.py — our injected caustic vs Cycles' own path-traced
caustics, on a more realistic scene.

What makes this scene more realistic than the earlier ones:

  * the water surface is REAL GEOMETRY, a 40x128 radial grid displaced by the
    same wave field the solver traces (tools/blender_scene.py:wave_h), so the
    caustic in the render arises from the same physics that produced the bake;
  * the sun has the real solar angular diameter, 0.53 deg, not the 2.4 deg
    stand-in. A small source is what makes caustics hard for path tracing, so
    this is both more physical and a fairer test;
  * the glass rim and base are bevelled (no razor edges) and the table carries a
    fine roughness variation instead of being a uniform procedural plate.

Both variants render the identical scene and differ only in where the caustic
comes from:

  ours     our baked field injected as light, Cycles' own caustics OFF
  cycles   no injection, Cycles traces caustics itself

Both are measured against their own converged 4096-sample render, so the RMSE is
that method's Monte-Carlo error. Denoising is OFF for these measurements: it
removes exactly the noise being measured.

Run:  python tools/realistic_showdown.py
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

COMMON = ["--sun", "8", "--sun-color", "0.98,0.98,1.00",
          "--world", "0.34", "--world-color", "0.45,0.55,0.80",
          "--gain", "0.25", "--exposure", "-0.05", "--sun-angle", "0.53",
          "--no-denoise",
          # give the path tracer its best shot: no Filter Glossy blur, no
          # indirect clamping, no adaptive early-out (see blender_scene.py)
          "--clamp-indirect", "0", "--no-adaptive"]
ORTHO = ["--w", "512", "--h", "512", "--ortho"]


def render(mode, samples, path, extra=None, denoise=False):
    cmd = [BLENDER, "--background", "--factory-startup", "--python", SCENE, "--",
           "--caustic", CAUSTIC, "--out", path, "--samples", str(samples)]
    cmd += (extra if extra is not None else ORTHO)
    cmd += COMMON
    if denoise:
        cmd = [c for c in cmd if c != "--no-denoise"]
    if mode == "cycles":
        cmd.append("--cycles-caustics")
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    dt = time.time() - t0
    if not os.path.exists(path):
        raise RuntimeError(f"{mode}/{samples} failed:\n{p.stderr[-700:]}")
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
    return a, dt


def rmse(a, b, mask=None):
    d = a - b
    if mask is not None:
        d = d[mask]
    return float(np.sqrt((d ** 2).mean()))


def main():
    res = {}
    print("=== orthographic 512x512, denoise off, real 0.53 deg sun ===")
    for mode in ("cycles", "ours"):
        ref, t_ref = render(mode, 4096, f"{OUT}/rn_{mode}_ref.png")
        lum = ref.mean(axis=2)
        mask = lum > np.percentile(lum, 92)          # the caustic region
        rows = []
        print(f"[{mode}] reference 4096 spp in {t_ref:5.1f}s  "
              f"caustic = {100*mask.mean():.1f}% of frame  "
              f"peak {lum.max()-np.median(lum):+.0f} levels over median")
        for s in (256, 1024):
            img, dt = render(mode, s, f"{OUT}/rn_{mode}_s{s}.png")
            r_all, r_cau = rmse(img, ref), rmse(img, ref, mask)
            rows.append({"samples": s, "time_s": dt, "rmse_all": r_all,
                         "rmse_caustic": r_cau})
            print(f"    {s:5d} spp  {dt:6.1f}s   RMSE all {r_all:7.2f}   "
                  f"RMSE caustic {r_cau:7.2f}")
        res[mode] = {"rows": rows, "ref_time_s": t_ref,
                     "caustic_pct": 100 * float(mask.mean())}

    c, o = res["cycles"], res["ours"]
    print()
    print("=" * 78)
    print(f"{'samples':>8} {'Cycles(all)':>12} {'ours(all)':>10} "
          f"{'Cycles(caust)':>14} {'ours(caust)':>12} {'whole-frame gain':>17}")
    for rc, ro in zip(c["rows"], o["rows"]):
        print(f"{rc['samples']:>8} {rc['rmse_all']:>12.2f} {ro['rmse_all']:>10.2f} "
              f"{rc['rmse_caustic']:>14.2f} {ro['rmse_caustic']:>12.2f} "
              f"{rc['rmse_all']/max(ro['rmse_all'],1e-9):>16.1f}x")
    print(f"{'':>8} (RMSE vs each method's own 4096-sample reference; "
          f"caustic = brightest 8% of the frame)")

    print()
    print("=== production stills: 1600x1000, 2048 spp, denoised ===")
    for mode, path in (("ours", f"{OUT}/hero_ours.png"),
                       ("cycles", f"{OUT}/hero_cycles.png")):
        _, dt = render(mode, 2048, path, extra=["--w", "1600", "--h", "1000"],
                       denoise=True)
        a = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
        lum = a.mean(axis=2)
        print(f"  {mode:7s} {dt:5.1f}s  mean {lum.mean():6.1f}  "
              f"p99 {np.percentile(lum,99):6.1f}  blown "
              f"{100*(a.max(axis=2)>=254).mean():.2f}%  -> {path}")
        res.setdefault("stills", {})[mode] = {"time_s": dt,
                                             "mean": float(lum.mean())}

    with open(f"{OUT}/realistic_showdown.json", "w") as f:
        json.dump(res, f, indent=2)


if __name__ == "__main__":
    main()
