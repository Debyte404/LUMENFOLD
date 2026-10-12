"""airy_scale_sweep.py — is the caustic's breadth caused by our smoothing scale?

With the corrected Cycles configuration, the two caustics sit in the same place
(centroids agree within 4 mm) but ours is 8-11x broader and dimmer at the core:
Cycles puts ~520 saturated pixels, ours spreads ~8300 dimmer ones. The obvious
suspect is airy_scale, which is the fold-softening length our field uses. It is
documented as a visibility parameter (it needs >= 3 px per fringe to be legible)
and its default of 0.006 m is 6 mm — orders of magnitude above the physical
fringe scale at a 0.53 deg source.

Here each candidate scale is baked, rendered, and scored against Cycles'
converged render of the same scene: caustic area at three thresholds, centroid
offset, and the correlation of each image's deviation from its own median over
the shared caustic region.

Run:  python tools/airy_scale_sweep.py
"""
import os
import subprocess

import numpy as np
from PIL import Image


# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

ROOT = _ROOT
BLENDER = "C:/Program Files/Blender Foundation/Blender 4.2/blender.exe"
SCENE = f"{ROOT}/tools/blender_scene.py"
OUT = f"{ROOT}/out"
EXE = f"{ROOT}/build/src/app/Release/showcase.exe"

SCALES = [0.006, 0.0015, 0.0006]
COMMON = ["--sun", "8", "--sun-color", "0.98,0.98,1.00",
          "--world", "0.34", "--world-color", "0.45,0.55,0.80",
          "--gain", "0.25", "--exposure", "-0.05", "--sun-angle", "0.53",
          "--no-denoise", "--clamp-indirect", "0", "--no-adaptive",
          "--w", "512", "--h", "512", "--ortho"]


def lum(p):
    return np.asarray(Image.open(p).convert("RGB")).astype(np.float32).mean(axis=2)


def bake(airy, path):
    cmd = [EXE, "--res", "1024", "--airy", str(airy), "--n", "400", "--ssaa", "1",
           "--out", f"{OUT}/_throwaway.png", "--dump-caustic", path]
    subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    return os.path.exists(path)


def render(caustic, path):
    cmd = [BLENDER, "--background", "--factory-startup", "--python", SCENE, "--",
           "--caustic", caustic, "--out", path, "--samples", "4096"] + COMMON
    subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    return os.path.exists(path)


def main():
    c = lum(f"{OUT}/rn_cycles_ref.png")          # Cycles converged, same scene
    med = float(np.median(c))
    print(f"Cycles converged reference: median {med:.1f}")

    print(f"{'airy_scale':>11} {'area med+10':>12} {'med+20':>8} {'med+30':>8} "
          f"{'centroid':>18} {'offset':>8} {'corr':>7}")
    rows = []
    for a in SCALES:
        field = f"{OUT}/caustic_a{a}.png"
        if not bake(a, field):
            print(f"{a:>11} bake failed")
            continue
        img = f"{OUT}/rn_ours_a{a}.png"
        if not render(field, img):
            print(f"{a:>11} render failed")
            continue
        o = lum(img)
        m10 = o > med + 10
        m20 = o > med + 20
        m30 = o > med + 30
        ys, xs = np.where(m10)
        H, W = o.shape
        cx = (xs.mean() / (W - 1) - 0.5) * 320 if len(xs) else float("nan")
        cy = (0.5 - ys.mean() / (H - 1)) * 320 if len(ys) else float("nan")
        # Cycles caustic centroid for the same threshold
        cc = np.where(c > med + 10)
        ccx = (cc[1].mean() / (W - 1) - 0.5) * 320
        ccy = (0.5 - cc[0].mean() / (H - 1)) * 320
        off = float(np.hypot(cx - ccx, cy - ccy))
        mask = m10 | (c > med + 10)
        do = (o - med)[mask]
        dc = (c - med)[mask]
        corr = float(((do - do.mean()) * (dc - dc.mean())).sum() /
                     max(np.sqrt(((do - do.mean()) ** 2).sum() *
                                 ((dc - dc.mean()) ** 2).sum()), 1e-9))
        rows.append((a, 100 * m10.mean(), off, corr))
        print(f"{a:>11} {100*m10.mean():>11.2f}% {100*m20.mean():>7.2f}% "
              f"{100*m30.mean():>7.2f}% ({cx:+7.1f},{cy:+7.1f}) {off:>7.1f}mm "
              f"{corr:>+7.3f}")
    print(f"{'Cycles':>11} {100*(c>med+10).mean():>11.2f}% "
          f"{100*(c>med+20).mean():>7.2f}% {100*(c>med+30).mean():>7.2f}% "
          f"({ccx:+7.1f},{ccy:+7.1f})")
    print()
    if rows:
        best = max(rows, key=lambda r: r[3])
        print(f"highest correlation at airy_scale = {best[0]} (r = {best[3]:+.3f}, "
              f"area {best[1]:.2f}%, centroid offset {best[2]:.1f} mm)")


if __name__ == "__main__":
    main()
