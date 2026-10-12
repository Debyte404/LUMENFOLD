"""frame_test2.py -- pick camera azimuth/distance/elevation for the ripple GIFs.

tools/archive/frame_test.py used a brightness percentile as the caustic mask and that caught
the sunlit table as well, so its bbox was meaningless. This isolates the caustic
properly: render the same frame WITH and WITHOUT the injected field and take the
difference -- the same differential method EVIDENCE uses for the Cycles
comparison. Then report the caustic's margin from the frame edges.

Also tests viewing the fan broadside rather than down its length: the sun's
azimuth is ~+27.7 deg, so a camera near that looks along the fan and foreshortens
it, while a camera roughly perpendicular sees the whole spread.
"""
import os
import subprocess

import numpy as np
from PIL import Image

ROOT = "D:/ValueProjects/caustics"
BLENDER = "C:/Program Files/Blender Foundation/Blender 4.2/blender.exe"
SCENE = f"{ROOT}/tools/blender_scene.py"
OUT = f"{ROOT}/out"
CAUSTIC = f"{OUT}/caustic_phys.png"

W, H = 960, 540
STUDIO = ["--studio", "--sun", "6.5", "--world", "0.55", "--gain", "0.25",
          "--sun-angle", "0.53", "--clamp-indirect", "0"]
SAMPLES = 192


def lum(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32).mean(axis=2)


def render(out, az, elev, dist, lens, caustic=True):
    cmd = [BLENDER, "--background", "--factory-startup", "--python", SCENE, "--",
           "--caustic", CAUSTIC, "--out", out, "--samples", str(SAMPLES),
           "--w", str(W), "--h", str(H),
           "--az", str(az), "--elev", str(elev), "--dist", str(dist),
           "--lens", str(lens)]
    if not caustic:
        cmd.append("--no-caustic")
    r = subprocess.run(cmd + STUDIO, capture_output=True, text=True, timeout=2400)
    return os.path.exists(out)


def main():
    if not os.path.exists(CAUSTIC):
        print("baking physical-width field ...")
        subprocess.run([f"{ROOT}/build/src/app/Release/showcase.exe",
                        "--res", "1024", "--airy", "0.000123",
                        "--n", "400", "--ssaa", "1", "--wave-t", "0.0",
                        "--out", f"{OUT}/_ft.png", "--dump-caustic", CAUSTIC],
                       capture_output=True, text=True, timeout=900)

    print("=== differential framing test (caustic = with - without) ===")
    results = []
    for az in (75, 110, 145):
        for dist in (0.62, 0.78, 0.92):
            on = f"{OUT}/_fo.png"
            off = f"{OUT}/_ff.png"
            ok1 = render(on, az, 38, dist, 50, True)
            ok2 = render(off, az, 38, dist, 50, False)
            if not (ok1 and ok2):
                print(f"  az {az} dist {dist}: render failed")
                continue
            d = np.clip(lum(on) - lum(off), 0, None)
            # the caustic is the added light; threshold relative to its own peak
            # 10% of peak isolates the bright caustic CORE; the faint skirt
            # legitimately spreads over the whole table and would fill any frame
            m = d > 0.10 * d.max()
            if m.sum() < 200:
                print(f"  az {az:>3} dist {dist}: only {m.sum()} caustic px")
                continue
            ys, xs = np.nonzero(m)
            mg = {"top": ys.min() / H, "bot": (H - 1 - ys.max()) / H,
                  "left": xs.min() / W, "right": (W - 1 - xs.max()) / W}
            tight = min(mg.values())
            print(f"  az {az:>3} dist {dist}: bbox x[{xs.min():>3}..{xs.max():>3}] "
                  f"y[{ys.min():>3}..{ys.max():>3}]  margins "
                  + " ".join(f"{k}={100*v:4.1f}%" for k, v in mg.items())
                  + f"   tightest {100*tight:4.1f}%")
            results.append((az, dist, tight, m.sum()))
            for p in (on, off):
                os.remove(p)

    print()
    good = [r for r in results if r[2] > 0.04]
    if good:
        # prefer the tightest framing that still clears the edges comfortably
        best = min(good, key=lambda r: r[2])
        print(f"chosen: az {best[0]}, dist {best[1]} "
              f"(tightest margin {100*best[2]:.1f}%, {best[3]} caustic px)")
    else:
        print("no configuration cleared the edges; widening needed")
        for r in results:
            print(f"   az {r[0]} dist {r[1]} margin {100*r[2]:.1f}%")


if __name__ == "__main__":
    main()
