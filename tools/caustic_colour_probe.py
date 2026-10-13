"""Where does the caustic actually change colour, and by how much?

The previous measurement ranked pixels by LUMINANCE, which is self-defeating: a
strongly tinted caustic has LOWER luminance than a neutral one, so the brightest
pixels are exactly the ones the tint has moved least, and the reported colour is a
whitish glint. This selects the pixels that respond to the medium instead -- the
c austic itself -- and reports their colour under each medium.
"""
import os
import subprocess
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "build/src/app/Release/showcase.exe")


def render(tag, water):
    p = os.path.join(ROOT, "out", "_fan_%s.png" % tag)
    subprocess.run([EXE, "--n", "900", "--out", p,
                    "--water-abs", ",".join(map(str, water)),
                    "--glass-abs", "0.10,0.08,0.07"], capture_output=True)
    return np.asarray(Image.open(p).convert("RGB"), dtype=np.float32)


def norm(rgb):
    return rgb / max(rgb.max(), 1e-9)


clear = render("clear", (0.02, 0.02, 0.02))
copper = render("copper", (28.0, 3.0, 0.6))

# The caustic is what the medium moves. Take the pixels that respond most.
d = np.abs(clear - copper).mean(axis=2)
thr = np.percentile(d, 99.0)
m = d >= thr
print("  pixels most changed by the water: %d (%.2f%% of frame)" % (m.sum(), 100 * m.mean()))
print()
print("  %-10s | %-22s | %s" % ("medium", "caustic RGB (changed region)", "normalised"))
print("  " + "-" * 62)
for name, img in (("clear", clear), ("copper", copper)):
    rgb = img[m].mean(axis=0)
    print("  %-10s | %7.1f %7.1f %7.1f    | %.3f %.3f %.3f"
          % (name, rgb[0], rgb[1], rgb[2], *norm(rgb)))

# physical prediction for the same path
L = 0.0904
print()
print("  prediction, Beer-Lambert over the renderer's measured 90.4 mm water path:")
for name, w in (("clear", (0.02, 0.02, 0.02)), ("copper", (28.0, 3.0, 0.6))):
    T = np.exp(-np.array(w) * L)
    print("    %-7s predicted norm  %.3f %.3f %.3f" % (name, *(T / T.max())))

rel = d.max()
print()
print("  max pixel change: %.0f levels" % rel)
