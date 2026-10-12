"""make_no_exaggeration_figure.py -- show our solution at the physical fringe
width next to the exaggerated version, for the README.

The repository's showcase stills were baked at airy_scale = 1.5 mm, which is
12.2x the physical fringe width for this geometry (0.123 mm), and the real-time
baker's own default is 0.02 m, 163x. Those numbers were chosen so the fringes
are visible on screen, and they are exactly the exaggeration this paper removes.
The ripple GIFs already use the physical width; this produces a still pair so the
difference is visible side by side, with the exaggerated one labelled as not
used for any result.

Run:  <system python> tools/make_no_exaggeration_figure.py
"""
import os
import subprocess
import sys
import time

import numpy as np
from PIL import Image


# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

ROOT = _ROOT
OUT = f"{ROOT}/out"
EXE = f"{ROOT}/build/src/app/Release/showcase.exe"
BLENDER = "C:/Program Files/Blender Foundation/Blender 4.2/blender.exe"
SCENE = f"{ROOT}/tools/blender_scene.py"

PHYS = 0.000123    # physical fringe width for this geometry
EXAG = 0.001500    # the visibility-chosen value used by the old stills

RIG = ["--sun", "8", "--sun-color", "0.98,0.98,1.00",
       "--world", "0.34", "--world-color", "0.45,0.55,0.80",
       "--gain", "0.25", "--exposure", "-0.05", "--sun-angle", "0.53",
       "--w", "760", "--h", "760", "--ortho"]


def bake(airy, path, res=1024):
    cmd = [EXE, "--res", str(res), "--n", "400", "--ssaa", "1",
           "--airy", f"{airy:.6f}", "--wave-t", "0.0",
           "--out", f"{OUT}/_throw.png", "--dump-caustic", path]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if not os.path.exists(path):
        raise RuntimeError(f"bake failed: {p.stderr[-400:]}")
    return time.time() - t0


def render(caustic, path, samples=1024):
    cmd = [BLENDER, "--background", "--factory-startup", "--python", SCENE, "--",
           "--caustic", caustic, "--out", path, "--samples", str(samples)]
    cmd += RIG + ["--no-denoise", "--clamp-indirect", "0", "--no-adaptive"]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if not os.path.exists(path):
        raise RuntimeError(f"render failed: {p.stderr[-500:]}")
    return time.time() - t0


def main():
    jobs = [("phys", PHYS, f"{OUT}/caustic_phys.png", f"{OUT}/readme_ours_physical.png"),
            ("exag", EXAG, f"{OUT}/caustic_exag.png", f"{OUT}/readme_ours_exaggerated.png")]
    meta = {}
    for name, airy, cpath, rpath in jobs:
        tb = bake(airy, cpath)
        tr = render(cpath, rpath)
        a = np.asarray(Image.open(rpath).convert("RGB")).astype(np.float32)
        meta[name] = dict(airy=airy, bake=tb, render=tr, mean=float(a.mean()))
        print(f"  {name}: airy {airy:.6f} m  bake {tb:.2f}s  render {tr:.1f}s  mean {a.mean():.1f}")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "serif",
                         "font.serif": ["Times New Roman", "DejaVu Serif"],
                         "font.size": 9, "figure.dpi": 200})

    a = np.asarray(Image.open(jobs[0][3]).convert("RGB"))
    b = np.asarray(Image.open(jobs[1][3]).convert("RGB"))
    fig, axes = plt.subplots(1, 3, figsize=(11.0, 4.0))
    axes[0].imshow(a); axes[0].set_title(
        f"(a) physical fringe width\n{PHYS*1e3:.3f} mm  (no exaggeration)", fontsize=9)
    axes[1].imshow(b); axes[1].set_title(
        f"(b) exaggerated {EXAG/PHYS:.1f}x\n{EXAG*1e3:.1f} mm  (old stills; not used)", fontsize=9)
    d = np.abs(a.astype(np.int16) - b.astype(np.int16)).sum(axis=2)
    im = axes[2].imshow(d, cmap="inferno")
    axes[2].set_title("(c) absolute difference\n(sum over channels, 8-bit)", fontsize=9)
    fig.colorbar(im, ax=axes[2], fraction=0.046, pad=0.02)
    for ax in axes:
        ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
    fig.suptitle("Our solution: the fold band at the physical fringe width, and the "
                 "same band stretched 12.2x for visibility", fontsize=10)
    fig.tight_layout()
    p = f"{ROOT}/docs/media/no_exaggeration.png"
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {p}")

    # byte-length-preserving alpha flatten, same rule as the paper figures
    import re

    def flatten(path):
        def repl(m):
            key, val = m.group(1), m.group(2).decode()
            new = ("1." + "0" * (len(val) - 2)) if "." in val else "1"
            return b"/" + key + b" " + new.encode()
        d0 = open(path, "rb").read()
        d1 = re.sub(rb"/(ca|CA) ([0-9]*\.?[0-9]+)", repl, d0)
        if len(d1) == len(d0) and d1 != d0:
            open(path, "wb").write(d1)
    flatten(p)
    print("alpha flattened")


if __name__ == "__main__":
    sys.exit(main())
