"""frame_test.py -- choose the camera distance for the ripple GIFs by measuring
how much margin the caustic has from the frame edges.

"No exaggerated fringes" also means no cropped subject: the earlier ripple clip
used dist 0.32 and cropped the fan. This renders one frame per candidate
distance (with the physical Airy width) and reports the bounding box of the
bright caustic pixels as a fraction of the frame, so the choice is measured
rather than guessed.
"""
import os
import struct
import subprocess
import zlib

import numpy as np

ROOT = "D:/ValueProjects/caustics"
BLENDER = "C:/Program Files/Blender Foundation/Blender 4.2/blender.exe"
SCENE = f"{ROOT}/tools/blender_scene.py"
OUT = f"{ROOT}/out"
CAUSTIC = f"{OUT}/caustic_phys.png"

W, H = 960, 540
AIRY_PHYSICAL = 0.000123

# the calibrated studio rig the clip passes use
STUDIO = ["--studio", "--sun", "6.5", "--world", "0.55", "--gain", "0.25",
          "--sun-angle", "0.53", "--clamp-indirect", "0"]


def read_rgb(path):
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32)


def margin_report(path, tag):
    a = read_rgb(path)
    lum = a.mean(axis=2)
    # caustic = the bright, warm part of the frame (above the table's base level)
    thr = np.percentile(lum, 99.0)
    m = lum >= thr
    if m.sum() < 50:
        print(f"  {tag}: only {m.sum()} bright px -- cannot judge")
        return None
    ys, xs = np.nonzero(m)
    top, bot = ys.min(), ys.max()
    left, right = xs.min(), xs.max()
    margins = {
        "top": top / H, "bottom": (H - 1 - bot) / H,
        "left": left / W, "right": (W - 1 - right) / W,
    }
    tightest = min(margins, key=margins.get)
    print(f"  {tag}: caustic bbox x[{left:>3}..{right:>3}] y[{top:>3}..{bot:>3}]  "
          f"margins " + " ".join(f"{k}={100*v:4.1f}%" for k, v in margins.items())
          + f"   tightest={tightest} {100*margins[tightest]:.1f}%")
    return min(margins.values())


def main():
    print("=== framing test: dist -> caustic margin (physical Airy width) ===")
    if not os.path.exists(CAUSTIC):
        print("  baking physical-width field ...")
        subprocess.run([f"{ROOT}/build/src/app/Release/showcase.exe",
                        "--res", "1024", "--airy", f"{AIRY_PHYSICAL:.6f}",
                        "--n", "400", "--ssaa", "1", "--wave-t", "0.0",
                        "--out", f"{OUT}/_ft.png", "--dump-caustic", CAUSTIC],
                       capture_output=True, text=True, timeout=900)
    best = None
    for dist in (0.36, 0.42, 0.48, 0.54):
        path = f"{OUT}/_ft_{dist}.png"
        cmd = [BLENDER, "--background", "--factory-startup", "--python", SCENE, "--",
               "--caustic", CAUSTIC, "--out", path, "--samples", "192",
               "--w", str(W), "--h", str(H),
               "--az", "35", "--elev", "19", "--dist", str(dist), "--lens", "50"] + STUDIO
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if not os.path.exists(path):
            print(f"  dist {dist}: render failed {r.stderr[-200:]}")
            continue
        m = margin_report(path, f"dist {dist}")
        if m is not None:
            # want the subject to fill the frame but clear of the edges
            if best is None or abs(m - 0.08) < abs(best[1] - 0.08):
                best = (dist, m)
        os.remove(path)
    print()
    print(f"chosen: dist = {best[0]}  (tightest margin {100*best[1]:.1f}%)" if best
          else "no usable distance found")
    return best[0] if best else 0.48


if __name__ == "__main__":
    main()
