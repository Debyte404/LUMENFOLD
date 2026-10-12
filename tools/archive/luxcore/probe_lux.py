"""probe_lux.py — validate the LuxCore Python API headlessly.

LuxCore is the reference 'photon map caustic cache' implementation we want to
test against (PhotonGI). Before building the real scene, this checks that a
minimal scene renders and prints the API surface we need.

Run:  third_party/luxvenv/Scripts/python.exe tools/archive/luxcore/probe_lux.py
"""
import glob
import os
import sys
import time

import pyluxcore

OUT = "D:/ValueProjects/caustics/out"
os.makedirs(OUT, exist_ok=True)

print("PYLUXCORE", pyluxcore.LuxCoreVersion() if hasattr(pyluxcore, "LuxCoreVersion")
      else getattr(pyluxcore, "__version__", "unknown"))
print("dlls", [os.path.basename(p) for p in glob.glob(
    os.path.join(os.path.dirname(pyluxcore.__file__), "..", "pyluxcore.libs", "*.dll"))][:6])

# what render engines / film outputs exist
print("engines", sorted(a for a in dir(pyluxcore) if a.isupper() and "PATH" in a)[:8])
print("filmout", sorted(a for a in dir(pyluxcore) if "FilmOutputType" in a))


def run(scene_props, cfg_props, name):
    scene = pyluxcore.Scene()
    p = pyluxcore.Properties()
    p.SetFromString(scene_props)
    scene.Parse(p)
    cfg = pyluxcore.Properties()
    cfg.SetFromString(cfg_props)
    session = pyluxcore.RenderSession(scene, cfg)
    t0 = time.time()
    session.Start()
    while not session.HasDone():
        session.Update()
    session.Stop()
    dt = time.time() - t0
    film = session.GetFilm()
    path = f"{OUT}/{name}.png"
    film.SaveOutput(path, pyluxcore.FilmOutputType.RGB_IMAGEPIPELINE,
                    pyluxcore.Properties())
    print(f"RENDERED {name} in {dt:.2f}s -> {path} exists={os.path.exists(path)}")
    return path


# --- minimal scene: a lit quad in front of the camera -----------------------
scene = """
scene.camera.type = perspective
scene.camera.lookat.orig = 0 0 2
scene.camera.lookat.target = 0 0 0
scene.camera.up = 0 0 1
scene.camera.fieldofview = 45

scene.materials.mat.type = matte
scene.materials.mat.kd = 0.8 0.8 0.8

scene.objects.quad.type = mesh
scene.objects.quad.material = mat
scene.objects.quad.vertices = -1 -1 0  1 -1 0  1 1 0  -1 1 0
scene.objects.quad.faces = 0 1 2 3

scene.lights.l.type = point
scene.lights.l.position = 1 1 2
scene.lights.l.color = 20 20 20
scene.lights.l.radius = 0.001
"""
cfg = """
render.engine.type = PATHCPU
film.width = 240
film.height = 160
film.outputs.0.type = RGB_IMAGEPIPELINE
film.outputs.0.filename = probe.png
render.threads.count = 4
"""
try:
    run(scene, cfg, "probe_lux")
except Exception as e:
    print("MINIMAL_SCENE_FAILED", type(e).__name__, e)
    sys.exit(1)

# --- the properties we will actually use for the caustic comparison --------
print()
print("PhotonGI properties to exercise (set in the render config):")
for k in ("photongi.enabled", "photongi.caustic.enabled",
          "photongi.caustic.maxsize", "photongi.caustic.lookupradius",
          "photongi.caustic.searchradius", "photongi.maxsize",
          "photongi.indirect.enabled", "lightstrategy.type"):
    print("   ", k)
print("PROBE_OK")
