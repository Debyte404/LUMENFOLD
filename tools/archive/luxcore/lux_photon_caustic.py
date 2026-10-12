"""lux_photon_caustic.py — render the caustic with LuxCore's PhotonGI caustic
cache (a production photon-map implementation) from a top-down orthographic
camera covering exactly the patch our solver bakes.

Why: every comparison so far used Cycles, which brute-forces caustics. Photon
mapping is the technique this project structurally replaces, and LuxCore's
PhotonGI is the reference implementation of it. An orthographic camera over the
same 0.32 m square means the rendered image and our baked field are the same
thing pixel for pixel, so they can be compared directly.

Run:  third_party/luxvenv/Scripts/python.exe tools/archive/luxcore/lux_photon_caustic.py \
        --photons 1000000 --spp 64 --out out/lux_photon.png
"""
import argparse
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pyluxcore
from PIL import Image

from probe_lux2 import Mesh, cylinder_side, disc

OUT = "D:/ValueProjects/caustics/out"
PATCH = 0.16          # our solver's field spans [-0.16, +0.16] m
R_OUT, R_IN, H, BOT = 0.035, 0.0315, 0.090, 0.0035
WATER_Z = 0.0594


def build():
    glass = Mesh()
    glass.add(*cylinder_side(R_OUT, BOT, H))
    glass.add(*cylinder_side(R_IN, BOT, H))
    glass.add(*disc(R_OUT, BOT, flip=True))
    glass.add(*disc(R_IN, BOT))
    glass.add(*disc(R_OUT, H))
    glass.add(*disc(R_IN, H, flip=True))
    water = Mesh()
    water.add(*cylinder_side(0.0314, BOT, WATER_Z))
    water.add(*disc(0.0314, WATER_Z))
    water.add(*disc(0.0314, BOT, flip=True))
    table = Mesh()
    s = PATCH
    table.add([-s, -s, 0, s, -s, 0, s, s, 0, -s, s, 0], [0, 1, 2, 0, 2, 3])
    return glass, water, table


def scene_string(photons, photongi_on, light_r, light_dist, opaque=False,
                 light_type="sphere"):
    glass, water, table = build()
    # the light travels along our solver's sun direction (0.80, 0.42, -0.43)
    d = np.array([0.80, 0.42, -0.43])
    d = d / np.linalg.norm(d)
    lpos = -d * light_dist          # back along the ray, so light travels down d
    sc = f"""
scene.materials.mat_table.type = matte
scene.materials.mat_table.kd = 0.82 0.82 0.82

scene.materials.mat_glass.type = {'matte' if opaque else 'glass'}
scene.materials.mat_glass.kd = 0.05 0.05 0.05
scene.materials.mat_glass.kr = 1.0 1.0 1.0
scene.materials.mat_glass.kt = 1.0 1.0 1.0
scene.materials.mat_glass.ior = 1.5

scene.materials.mat_water.type = {'matte' if opaque else 'glass'}
scene.materials.mat_water.kr = 1.0 1.0 1.0
scene.materials.mat_water.kt = 1.0 1.0 1.0
scene.materials.mat_water.ior = 1.333

scene.world.type = constantinfinite
scene.world.color = 0.0 0.0 0.0
"""
    sc += table.props("table", "mat_table")
    sc += glass.props("glass", "mat_glass")
    sc += water.props("water", "mat_water")
    # a small, distant sphere light: PhotonGI builds its caustic cache from it,
    # and at 1.2 m with a 3 mm radius it is effectively our directional sun
    if light_type == "sun":
        sc += f"""
scene.lights.key.type = sun
scene.lights.key.dir = {d[0]:.6f} {d[1]:.6f} {d[2]:.6f}
scene.lights.key.angle = {light_r * 180.0 / 3.141592653589793}
scene.lights.key.gain = 50.0 50.0 50.0
scene.lights.key.turbidity = 2.0
"""
    else:
        sc += f"""
scene.lights.key.type = sphere
scene.lights.key.position = {lpos[0]:.6f} {lpos[1]:.6f} {lpos[2]:.6f}
scene.lights.key.radius = {light_r}
scene.lights.key.color = 1.0 1.0 1.0
scene.lights.key.gain = 3000.0 3000.0 3000.0
"""
    return sc


def config_string(spp, photons, photongi_on, size, budget_s, engine="PATHCPU"):
    pg = f"""
photongi.enable = 1
photongi.caustic.enabled = 1
photongi.caustic.maxsize = {photons}
photongi.caustic.lookup.radius = 0.012
photongi.indirect.enabled = 1
photongi.indirect.maxsize = {photons}
photongi.photon.maxcount = {max(photons * 4, 1000000)}
photongi.photon.maxdepth = 8
lightstrategy.type = LOG_POWER
""" if photongi_on else "photongi.enable = 0\n"
    return f"""
render.engine.type = {engine}
render.threads.count = 4
film.width = {size}
film.height = {size}
film.filter.type = BOX
film.outputs.0.type = RGB_IMAGEPIPELINE
film.outputs.0.filename = lux_tmp.png
batch.haltspp = {spp}
batch.halttime = {budget_s}
{pg}
"""


def render(spp, photons, photongi_on, size, out_path, budget_s=600,
           light_r=0.003, light_dist=1.2, opaque=False, engine="PATHCPU", light_type="sphere"):
    sc = pyluxcore.Scene()
    p = pyluxcore.Properties()
    # orthographic camera straight down over the patch, so the render IS the
    # same field our solver bakes
    p.SetFromString(f"""
scene.camera.type = orthographic
scene.camera.lookat.orig = 0 0 1
scene.camera.lookat.target = 0 0 0
scene.camera.up = 0 1 0
scene.camera.screenwindow = -{PATCH} {PATCH} -{PATCH} {PATCH}
""" + scene_string(photons, photongi_on, light_r, light_dist, opaque, light_type))
    sc.Parse(p)
    c = pyluxcore.Properties()
    c.SetFromString(config_string(spp, photons, photongi_on, size, budget_s, engine))
    cfg = pyluxcore.RenderConfig(c, sc)
    session = pyluxcore.RenderSession(cfg)
    t0 = time.time()
    session.Start()
    while time.time() - t0 < budget_s:
        if session.HasDone():
            break
        time.sleep(0.25)
    session.Stop()
    dt = time.time() - t0
    film = session.GetFilm()
    film.SaveOutput(out_path, pyluxcore.FilmOutputType.RGB_IMAGEPIPELINE,
                    pyluxcore.Properties())
    a = np.asarray(Image.open(out_path).convert("RGB")).astype(np.float32)
    return a, dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--photons", type=int, default=1_000_000)
    ap.add_argument("--spp", type=int, default=64)
    ap.add_argument("--size", type=int, default=256)
    ap.add_argument("--budget", type=float, default=600)
    ap.add_argument("--out", default=f"{OUT}/lux_photon.png")
    ap.add_argument("--no-photongi", action="store_true")
    ap.add_argument("--engine", default="PATHCPU")
    ap.add_argument("--light-r", type=float, default=0.003)
    ap.add_argument("--light-type", default="sphere")
    ap.add_argument("--opaque", action="store_true",
                    help="make glass/water matte: proves the objects are in the scene")
    args = ap.parse_args()

    a, dt = render(args.spp, args.photons, not args.no_photongi, args.size,
                   args.out, args.budget, opaque=args.opaque, engine=args.engine,
                   light_r=args.light_r, light_type=args.light_type)
    lum = a.mean(axis=2)
    print(f"LUX {args.size}x{args.size} photons={args.photons} spp={args.spp} "
          f"photongi={'off' if args.no_photongi else 'on'} in {dt:.1f}s")
    print(f"  luma mean {lum.mean():.3f} max {lum.max():.3f} "
          f"p50 {np.percentile(lum,50):.3f} p99 {np.percentile(lum,99):.3f}")
    print(f"  brightest 2% of the patch is {lum.max()/max(np.median(lum),1e-9):.1f}x the median")


if __name__ == "__main__":
    main()
