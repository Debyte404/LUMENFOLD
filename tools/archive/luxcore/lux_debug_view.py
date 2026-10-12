"""lux_debug_view.py — what is the orthographic camera actually looking at?

Flat environment light, opaque materials, no other lights: the image is then
just geometry. Prints an ASCII silhouette map plus the table's edges, so the
camera framing, the unit scale and the object placement can be checked directly
instead of inferred from summary statistics.

Run:  third_party/luxvenv/Scripts/python.exe tools/archive/luxcore/lux_debug_view.py
"""
import os
import sys
import time


# Repo root, derived rather than hardcoded.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pyluxcore
from PIL import Image

from lux_photon_caustic import build, PATCH

OUT = _ROOT + "/out"


def main():
    glass, water, table = build()
    sc = f"""
scene.camera.type = orthographic
scene.camera.lookat.orig = 0 0 1
scene.camera.lookat.target = 0 0 0
scene.camera.up = 0 1 0
scene.camera.screenwindow = -{PATCH} {PATCH} -{PATCH} {PATCH}

scene.materials.mat_table.type = matte
scene.materials.mat_table.kd = 0.85 0.85 0.85
scene.materials.mat_glass.type = matte
scene.materials.mat_glass.kd = 0.05 0.05 0.05
scene.materials.mat_water.type = matte
scene.materials.mat_water.kd = 0.35 0.35 0.35

scene.world.type = constantinfinite
scene.world.color = 0.5 0.5 0.5
"""
    sc += table.props("table", "mat_table")
    sc += glass.props("glass", "mat_glass")
    sc += water.props("water", "mat_water")

    scene = pyluxcore.Scene()
    p = pyluxcore.Properties()
    p.SetFromString(sc)
    scene.Parse(p)
    print("OBJECT_COUNT", scene.GetObjectCount(), "LIGHT_COUNT", scene.GetLightCount())

    c = pyluxcore.Properties()
    c.SetFromString("""
render.engine.type = PATHCPU
render.threads.count = 4
film.width = 160
film.height = 160
film.filter.type = BOX
film.outputs.0.type = RGB_IMAGEPIPELINE
film.outputs.0.filename = lux_dbg.png
batch.haltspp = 8
batch.halttime = 40
photongi.enable = 0
""")
    cfg = pyluxcore.RenderConfig(c, scene)
    session = pyluxcore.RenderSession(cfg)
    t0 = time.time()
    session.Start()
    while time.time() - t0 < 40:
        if session.HasDone():
            break
        time.sleep(0.2)
    session.Stop()
    path = f"{OUT}/lux_debug_view.png"
    session.GetFilm().SaveOutput(path, pyluxcore.FilmOutputType.RGB_IMAGEPIPELINE,
                                 pyluxcore.Properties())
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
    lum = a.mean(axis=2)
    H, W = lum.shape
    print(f"DEBUG {W}x{H} min {lum.min():.0f} max {lum.max():.0f} "
          f"corner {lum[3,3]:.0f} centre {lum[H//2,W//2]:.0f}")
    chars = " .:-=+*#%@"
    for r in range(20):
        print("   ", "".join(chars[min(9, int(lum[r*H//20:(r+1)*H//20,
                                                c*W//20:(c+1)*W//20].mean() / 25.6))]
                             for c in range(20)))
    # where are the table edges? a table of side 0.32 in a patch of side 0.32
    # fills the frame, so a dark border means the framing is wrong
    print(f"border means: top {lum[0:3,:].mean():.0f} bottom {lum[-3:,:].mean():.0f} "
          f"left {lum[:,0:3].mean():.0f} right {lum[:,-3:].mean():.0f}")
    print("DEBUG_DONE")


if __name__ == "__main__":
    main()
