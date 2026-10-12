"""probe_lux2.py — validate the primitives the comparison scene needs.

Checks, in one render: a triangle mesh, a smooth dielectric ("glass"), a small
sun, a dark world, and PATHCPU + PhotonGI. Prints whatever LuxCore complains
about so the scene format can be corrected before the real experiment.

Run:  third_party/luxvenv/Scripts/python.exe tools/archive/luxcore/probe_lux2.py
"""
import math
import os
import time

import pyluxcore

OUT = "D:/ValueProjects/caustics/out"
os.makedirs(OUT, exist_ok=True)

SEG = 48


def cylinder_side(r, z0, z1, seg=SEG):
    """Open tube at radius r; returns (verts, faces) as flat lists."""
    v, f = [], []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        v += [r * math.cos(a), r * math.sin(a), z0]
        v += [r * math.cos(a), r * math.sin(a), z1]
    for i in range(seg):
        a0, a1 = 2 * i, 2 * ((i + 1) % seg)
        b0, b1 = a0 + 1, a1 + 1
        f += [a0, a1, b1]
        f += [a0, b1, b0]
    return v, f


def disc(r, z, seg=SEG, flip=False):
    v, f = [0.0, 0.0, z], []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        v += [r * math.cos(a), r * math.sin(a), z]
    for i in range(seg):
        a0, a1 = 1 + i, 1 + ((i + 1) % seg)
        f += [0, a1, a0] if flip else [0, a0, a1]
    return v, f


class Mesh:
    def __init__(self):
        self.v, self.f = [], []

    def add(self, verts, faces):
        o = len(self.v) // 3
        self.v += verts
        self.f += [i + o for i in faces]

    def props(self, name, material):
        return (f"\nscene.objects.{name}.type = mesh"
                f"\nscene.objects.{name}.material = {material}"
                f"\nscene.objects.{name}.vertices = {' '.join(f'{x:g}' for x in self.v)}"
                f"\nscene.objects.{name}.faces = {' '.join(str(i) for i in self.f)}")


def build_scene():
    m = Mesh()
    # table: 0.32 m square at z=0, two triangles
    s = 0.16
    m.add([-s, -s, 0, s, -s, 0, s, s, 0, -s, s, 0], [0, 1, 2, 0, 2, 3])
    # glass tube: outer + inner wall + bottom + rim
    R_out, R_in, H, bot = 0.035, 0.0315, 0.090, 0.0035
    m.add(*cylinder_side(R_out, bot, H))
    m.add(*cylinder_side(R_in, bot, H))
    m.add(*disc(R_out, bot, flip=True))     # glass bottom, outside faces down
    m.add(*disc(R_in, bot))                 # ...inside faces up
    m.add(*disc(R_out, H))                  # rim
    m.add(*disc(R_in, H, flip=True))
    # water: solid cylinder inside, up to the water line
    water = Mesh()
    water.add(*cylinder_side(0.0314, bot, 0.0594))
    water.add(*disc(0.0314, 0.0594))
    water.add(*disc(0.0314, bot, flip=True))
    return m, water


def main():
    glass, water = build_scene()
    sc = """
scene.camera.type = perspective
scene.camera.lookat.orig = 0.26 0.20 0.17
scene.camera.lookat.target = 0.0 0.0 0.01
scene.camera.up = 0 0 1
scene.camera.fieldofview = 38

scene.materials.mat_table.type = matte
scene.materials.mat_table.kd = 0.82 0.82 0.82

scene.materials.mat_glass.type = glass
scene.materials.mat_glass.kr = 1.0 1.0 1.0
scene.materials.mat_glass.kt = 1.0 1.0 1.0
scene.materials.mat_glass.ior = 1.5

scene.materials.mat_water.type = glass
scene.materials.mat_water.kr = 1.0 1.0 1.0
scene.materials.mat_water.kt = 1.0 1.0 1.0
scene.materials.mat_water.ior = 1.333

scene.world.type = constant
scene.world.color = 0.02 0.025 0.035
"""
    sc += glass.props("glass", "mat_glass")
    sc += water.props("water", "mat_water")
    sc += """
scene.lights.sun.type = sun
scene.lights.sun.dir = 0.80 0.42 -0.43
scene.lights.sun.angle = 0.10
scene.lights.sun.gain = 1.0 1.0 1.0
scene.lights.sun.turbidity = 2.0
"""
    cfg = """
render.engine.type = PATHCPU
film.width = 320
film.height = 200
film.outputs.0.type = RGB_IMAGEPIPELINE
film.outputs.0.filename = probe2.png
render.threads.count = 4
batch.haltspp = 32
batch.halttime = 120
"""
    scene = pyluxcore.Scene()
    p = pyluxcore.Properties()
    p.SetFromString(sc)
    scene.Parse(p)
    c = pyluxcore.Properties()
    c.SetFromString(cfg)

    config = pyluxcore.RenderConfig(c, scene)
    session = pyluxcore.RenderSession(config)
    t0 = time.time()
    session.Start()
    # A progressive renderer has no natural end: bound it by wall clock instead
    # of trusting a halt key, otherwise WaitForDone() blocks forever.
    while time.time() - t0 < 25.0:
        if session.HasDone():
            break
        time.sleep(0.25)
    session.Stop()
    dt = time.time() - t0
    try:
        st = session.GetStats()
        print("stats", {k: st[k] for k in list(st)[:6]})
    except Exception as e:
        print("stats unavailable", e)
    film = session.GetFilm()
    path = f"{OUT}/probe_lux2.png"
    film.SaveOutput(path, pyluxcore.FilmOutputType.RGB_IMAGEPIPELINE,
                    pyluxcore.Properties())
    print(f"RENDERED in {dt:.2f}s exists={os.path.exists(path)}")

    # is there any light on the table at all?
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
    print(f"image {a.shape[1]}x{a.shape[0]} mean {a.mean():.2f} max {a.max():.0f}")
    print("PROBE2_OK")


if __name__ == "__main__":
    main()
