"""dragon_suite.py -- high-res four-engine suite for the glass dragon (GO-gated).

Physical scale only. Exaggerated panels are out of scope until this CSV exists.

Usage:
  python tools/dragon_suite.py --check                 # metric unit test
  python tools/dragon_suite.py --engines referee        # independent trace
  python tools/dragon_suite.py --engines ours           # proto correction + score
  python tools/dragon_suite.py --engines cycles_native  # high-res Cycles render
  python tools/dragon_suite.py --engines pbrt           # PBRT-v4 SPPM
  python tools/dragon_suite.py --engines mitsuba        # Mitsuba 3 qualitative
"""
import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
OUT = ROOT / "out" / "dragon_suite"
GEO = ROOT / "out" / "dragon_geo"
CSV = ROOT / "docs" / "data" / "dragon_suite.csv"


def corr(a, b, n_tiles):
    """Tiled Pearson correlation, paper tile convention (tile count -> size)."""
    assert a.shape == b.shape and a.shape[0] % n_tiles == 0
    bs = a.shape[0] // n_tiles
    A1 = a.reshape(n_tiles, bs, n_tiles, bs).mean(axis=(1, 3))
    B1 = b.reshape(n_tiles, bs, n_tiles, bs).mean(axis=(1, 3))
    A1 = A1 - A1.mean()
    B1 = B1 - B1.mean()
    d = float(np.sqrt((A1 * A1).sum() * (B1 * B1).sum()))
    return float((A1 * B1).sum() / d) if d > 0 else 0.0


def _recv():
    return json.loads((GEO / "receiver.json").read_text())


def _append_row(row):
    CSV.parent.mkdir(parents=True, exist_ok=True)
    new = not CSV.exists()
    with CSV.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)


def run_referee(n_side=300, n_grid=256):
    import dragon_trace as T
    r = _recv()
    rx = r["receiver"]
    patch_half = max(rx["x1"] - rx["x0"], rx["y1"] - rx["y0"]) / 2 * 0.52
    mesh = T.load_obj(GEO / "dragon.obj")
    t0 = time.time()
    hits = T.trace(mesh, n_side=n_side, eta=1.5251,
                   receiver_z=rx["z"], patch_half=patch_half)
    dt = time.time() - t0
    g = T.to_grid(hits, n=n_grid, patch_half=patch_half)
    OUT.mkdir(parents=True, exist_ok=True)
    np.save(OUT / f"referee_{n_grid}.npy", g)
    try:
        from PIL import Image
        Image.fromarray((65535 * g / g.max()).astype(np.uint16)).save(
            OUT / f"referee_{n_grid}.png")
    except Exception as e:
        print("PNG_SKIP", e)
    row = {"engine": "referee", "res": n_grid, "budget": f"{n_side}^2 rays",
           "render_s": round(dt, 1), "r_8tile": "", "r_32tile": "",
           "note": f"receiver_z={rx['z']:.3f} patch_half={patch_half:.2f}m"}
    _append_row(row)
    print(f"REFEREE_OK hits={len(hits)} max={g.max():.1f} {dt:.1f}s")
    return g


def run_ours(n_side=150, n_grid=128):
    import dragon_trace as T
    from scipy.ndimage import distance_transform_edt
    from scipy.special import airy
    r = _recv()
    rx = r["receiver"]
    patch_half = max(rx["x1"] - rx["x0"], rx["y1"] - rx["y0"]) / 2 * 0.52
    mesh = T.load_obj(GEO / "dragon.obj")
    t0 = time.time()
    hits = T.trace(mesh, n_side=n_side, eta=1.5251,
                   receiver_z=rx["z"], patch_half=patch_half)
    low = T.to_grid(hits, n=n_grid, patch_half=patch_half)
    ridge = low > np.percentile(low[low > 0], 95)
    m_per_px = 2 * patch_half / n_grid
    d = distance_transform_edt(~ridge) * m_per_px
    band = d <= 0.004
    out = low.copy()
    if band.any() and float(low[band].sum()) > 0:
        s = np.clip((d[band] - d[ridge].mean()) / 6.77e-6, -8.0, 8.0)
        ai, _, _, _ = airy(-s)
        w = (ai * ai)
        w = w / w.sum()
        out[band] = float(low[band].sum()) * w
    ref = np.load(OUT / "referee_256.npy")
    bs = 256 // n_grid
    ref128 = ref.reshape(n_grid, bs, n_grid, bs).mean(axis=(1, 3))
    r8, r32 = corr(ref128, out, 8), corr(ref128, out, 32)
    dt = time.time() - t0
    np.save(OUT / "ours_128.npy", out)
    row = {"engine": "ours-proto", "res": n_grid, "budget": f"{n_side}^2 rays",
           "render_s": round(dt, 1), "r_8tile": round(r8, 3),
           "r_32tile": round(r32, 3),
           "note": "EDT-ridge band + Airy 6.77um vs referee-256 block-averaged"}
    _append_row(row)
    print(f"OURS_OK r8={r8:.3f} r32={r32:.3f} {dt:.1f}s")


def run_cycles_native(w=2560, h=1440, samples=1024):
    blender = r"E:\SteamLibrary\steamapps\common\Blender\blender.exe"
    out = OUT / "cycles_native_2560.png"
    t0 = time.time()
    cmd = [blender, "--background", "--python",
           str(ROOT / "tools" / "dragon_spike_render.py"), "--",
           "--blend", str(ROOT / "models" / "dragon_glass.blend"),
           "--out", str(out), "--w", str(w), "--h", str(h),
           "--samples", str(samples), "--clamp-indirect", "0"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    dt = time.time() - t0
    print((r.stdout[-600:] or "") + (r.stderr[-600:] or ""))
    if r.returncode != 0:
        raise SystemExit(f"cycles render failed: {r.returncode}")
    row = {"engine": "cycles-native", "res": f"{w}x{h}",
           "budget": f"{samples}spp", "render_s": round(dt, 1),
           "r_8tile": "", "r_32tile": "", "note": "Filter Glossy 0, clamp 0, mb12"}
    _append_row(row)
    print(f"CYCLES_OK {dt:.1f}s")


def run_pbrt(res=256, spp=256, photons=500000, radius=0.05):
    import struct
    pbrt = ROOT / "third_party" / "pbrt-v4" / "build" / "Release" / "pbrt.exe"
    if not pbrt.exists():
        raise SystemExit(f"pbrt not built at {pbrt}")
    outd = ROOT / "out" / "dragon_pbrt"
    outd.mkdir(parents=True, exist_ok=True)
    def convert(src, dst):
        verts, faces = [], []
        for line in Path(src).read_text().splitlines():
            if line.startswith("v "):
                verts.append(tuple(map(float, line.split()[1:4])))
            elif line.startswith("f "):
                idx = [int(t.split("/")[0]) - 1 for t in line.split()[1:]]
                for i in range(1, len(idx) - 1):
                    faces.append((idx[0], idx[i], idx[i + 1]))
        with open(dst, "w") as f:
            f.write("ply\nformat ascii 1.0\n")
            f.write(f"element vertex {len(verts)}\nproperty float x\nproperty float y\nproperty float z\n")
            f.write(f"element face {len(faces)}\nproperty list uchar int vertex_indices\nend_header\n")
            for v in verts:
                f.write(f"{v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
            for a, b, c in faces:
                f.write(f"3 {a} {b} {c}\n")
    convert(GEO / "dragon.obj", outd / "dragon.ply")
    r = _recv()
    rx = r["receiver"]
    cx, cy = (rx["x0"] + rx["x1"]) / 2, (rx["y0"] + rx["y1"]) / 2
    hw = max(rx["x1"] - rx["x0"], rx["y1"] - rx["y0"]) / 2
    fpath = (outd / "pbrt_dragon.exr").as_posix()
    dply = (outd / "dragon.ply").as_posix()
    tply = (outd / "table.ply").as_posix()
    scene = f"""LookAt {cx} {cy} 5   {cx} {cy} {rx['z']}   0 1 0
Camera "orthographic" "float screenwindow" [{-hw} {hw} {-hw} {hw}]
       "float frameaspectratio" [1.0]
Film "rgb" "string filename" "{fpath}"
     "integer xresolution" [{res}] "integer yresolution" [{res}]
Sampler "halton" "integer pixelsamples" [{spp}]
Integrator "sppm" "integer maxdepth" [8]
           "integer photonsperiteration" [{photons}]
           "float radius" [{radius}]
WorldBegin
LightSource "distant" "point3 from" [-1.6 -0.84 0.86] "point3 to" [0 0 0] "rgb L" [8.0 8.0 8.0]
LightSource "infinite" "rgb L" [0.7 0.7 0.7]
MakeNamedMaterial "glass" "string type" "dielectric" "float eta" [1.52514]
MakeNamedMaterial "table" "string type" "diffuse" "rgb reflectance" [0.8 0.8 0.8]
AttributeBegin
  NamedMaterial "table"
  Shape "plymesh" "string filename" "{tply}"
AttributeEnd
AttributeBegin
  NamedMaterial "glass"
  Shape "plymesh" "string filename" "{dply}"
AttributeEnd
"""
    # flat receiver quad for pbrt (two triangles)
    with open(outd / "table.ply", "w") as f:
        f.write("ply\nformat ascii 1.0\nelement vertex 4\nproperty float x\nproperty float y\nproperty float z\nelement face 2\nproperty list uchar int vertex_indices\nend_header\n")
        f.write(f"{rx['x0']} {rx['y0']} {rx['z']}\n{rx['x1']} {rx['y0']} {rx['z']}\n{rx['x1']} {rx['y1']} {rx['z']}\n{rx['x0']} {rx['y1']} {rx['z']}\n3 0 1 2\n3 0 2 3\n")
    sp = outd / "dragon.pbrt"
    sp.write_text(scene)
    t0 = time.time()
    p = subprocess.run([str(pbrt), "--nthreads", "20", str(sp)],
                       capture_output=True, text=True, timeout=7200)
    dt = time.time() - t0
    print((p.stdout[-800:] or "") + (p.stderr[-800:] or ""))
    luxpy = ROOT / "third_party" / "luxvenv" / "Scripts" / "python.exe"
    q = subprocess.run(
        [str(luxpy), "-c",
         "import mitsuba as mi; mi.set_variant('scalar_rgb');"
         "import numpy as np; from PIL import Image;"
         f"a = np.array(mi.Bitmap(r'{fpath}')); lum = a[..., :3].mean(axis=-1).astype(np.float64);"
         f"np.save(r'{(OUT / 'pbrt_lum.npy').as_posix()}', lum);"
         f"Image.fromarray((255 * lum / lum.max()).astype(np.uint8)).save(r'{(OUT / 'pbrt_vis.png').as_posix()}');"
         "print('PBRT_EXR_DUMP_OK', a.shape, float(lum.max()))"],
        capture_output=True, text=True, timeout=600)
    print((q.stdout[-400:] or "") + (q.stderr[-400:] or ""))
    row = {"engine": "pbrt-sppm", "res": res, "budget": f"{spp}spp/{photons}ph",
           "render_s": round(dt, 1), "r_8tile": "", "r_32tile": "",
           "note": "ortho over receiver; scored vs referee in EVIDENCE step"}
    _append_row(row)
    print(f"PBRT_OK {dt:.1f}s")


def run_mitsuba(res=256, spp=64):
    luxpy = ROOT / "third_party" / "luxvenv" / "Scripts" / "python.exe"
    if not luxpy.exists():
        raise SystemExit("luxvenv python missing")
    script = OUT / "mitsu_dragon.py"
    obj = (GEO / "dragon.obj").as_posix()
    exr = (OUT / "mitsuba_dragon.exr").as_posix()
    lines = [
        "import mitsuba as mi",
        "mi.set_variant('scalar_spectral')",
        "T = mi.ScalarTransform4f",
        "scene = mi.load_dict({",
        "    'type': 'scene',",
        "    'integrator': {'type': 'path'},",
        "    'sensor': {'type': 'perspective', 'fov': 40,",
        "               'to_world': T.look_at(origin=[1.47, 2.03, 1.29], target=[0, 0, 0.1], up=[0, 0, 1]),",
        f"               'film': {{'type': 'hdrfilm', 'width': {res}, 'height': {res}}}}},",
        f"    'dragon': {{'type': 'obj', 'filename': '{obj}', 'material': {{'type': 'dielectric', 'int_ior': 1.525}}}},",
        "    'sun': {'type': 'sphere', 'center': [-4.8, -2.52, 2.58], 'radius': 0.3, 'emitter': {'type': 'area', 'radiance': 200.0}},",
        "    'ground': {'type': 'rectangle', 'to_world': T.translate([0, 0, -0.28]).scale([8, 7, 1]), 'material': {'type': 'diffuse'}}",
        "})",
        f"img = mi.render(scene, spp={spp})",
        f"mi.Bitmap(img).write('{exr}')",
        "print('MITSUBA_DONE')",
        "import numpy as _np",
        "from PIL import Image as _Image",
        f"_lum = _np.array(img)[..., :3].mean(axis=-1).astype(_np.float64)",
        f"_Image.fromarray((255 * _lum / _lum.max()).astype(_np.uint8)).save(r'{(OUT / 'mitsuba_vis.png').as_posix()}')",
        "",
    ]
    script.write_text("\n".join(lines))
    t0 = time.time()
    p = subprocess.run([str(luxpy), str(script)], capture_output=True,
                       text=True, timeout=3600)
    dt = time.time() - t0
    print((p.stdout[-800:] or "") + (p.stderr[-800:] or ""))
    if "MITSUBA_DONE" not in p.stdout:
        raise SystemExit("mitsuba render failed")
    row = {"engine": "mitsuba-path", "res": res, "budget": f"{spp}spp",
           "render_s": round(dt, 1), "r_8tile": "", "r_32tile": "",
           "note": "qualitative only (no SPPM in 3.9); beauty framing"}
    _append_row(row)
    print(f"MITSUBA_OK {dt:.1f}s")


def run_score():
    """Resample the PBRT ortho render onto the referee grid and correlate.

    PBRT ortho covers the full receiver; the referee covers [-2.17,2.17]^2.
    Bilinear resample then paper tile convention. Appends a pbrt-scored row.
    """
    from scipy.ndimage import map_coordinates
    lum = np.load(OUT / "pbrt_lum.npy")
    ref = np.load(OUT / "referee_256.npy")
    r = _recv()
    rx = r["receiver"]
    x0, x1, y0, y1 = rx["x0"], rx["x1"], rx["y0"], rx["y1"]
    ph = 2.17
    gx = np.linspace(-ph, ph, 256)
    GY, GX = np.meshgrid(gx, gx)
    px = (GX - x0) / (x1 - x0) * 255.0
    py = (GY - y0) / (y1 - y0) * 255.0
    res = map_coordinates(lum, [py.ravel(), px.ravel()], order=1).reshape(256, 256)
    r8, r32 = corr(res, ref, 8), corr(res, ref, 32)
    row = {"engine": "pbrt-scored", "res": 256,
           "budget": "resample-to-referee", "render_s": "",
           "r_8tile": round(r8, 3), "r_32tile": round(r32, 3),
           "note": "bilinear PBRT ortho onto referee grid; orientation per pipeline"}
    _append_row(row)
    print(f"SCORE_OK pbrt_vs_referee r8={r8:.3f} r32={r32:.3f}")


EYE = (1.47, 2.03, 1.29)
LOOK = (0.0, 0.0, 0.1)
BEAUTY_FOV = 39.6  # Blender 50mm default lens


def _write_table_ply(outd, rx):
    with open(outd / "table.ply", "w") as f:
        f.write("ply\nformat ascii 1.0\nelement vertex 4\nproperty float x\nproperty float y\nproperty float z\nelement face 2\nproperty list uchar int vertex_indices\nend_header\n")
        f.write(f"{rx['x0']} {rx['y0']} {rx['z']}\n{rx['x1']} {rx['y0']} {rx['z']}\n{rx['x1']} {rx['y1']} {rx['z']}\n{rx['x0']} {rx['y1']} {rx['z']}\n3 0 1 2\n3 0 2 3\n")


def run_pbrt_beauty(w=2560, h=1440, spp=128, photons=500000, radius=0.05):
    """Perspective beauty through the same eye/target/fov as CAM_beauty."""
    import struct
    pbrt = ROOT / "third_party" / "pbrt-v4" / "build" / "Release" / "pbrt.exe"
    if not pbrt.exists():
        raise SystemExit(f"pbrt not built at {pbrt}")
    outd = ROOT / "out" / "dragon_pbrt"
    outd.mkdir(parents=True, exist_ok=True)
    fpath = (outd / "pbrt_beauty.exr").as_posix()
    dply = (outd / "dragon.ply").as_posix()
    tply = (outd / "table.ply").as_posix()
    r = _recv()
    rx = r["receiver"]
    _write_table_ply(outd, rx)
    ex, ey, ez = EYE
    tx, ty, tz = LOOK
    scene = f"""LookAt {ex} {ey} {ez}   {tx} {ty} {tz}   0 0 1
Camera "perspective" "float fov" [{BEAUTY_FOV}]
       "float frameaspectratio" [{w / h:.6f}]
Film "rgb" "string filename" "{fpath}"
     "integer xresolution" [{w}] "integer yresolution" [{h}]
Sampler "halton" "integer pixelsamples" [{spp}]
Integrator "sppm" "integer maxdepth" [8]
           "integer photonsperiteration" [{photons}]
           "float radius" [{radius}]
WorldBegin
LightSource "distant" "point3 from" [-1.6 -0.84 0.86] "point3 to" [0 0 0] "rgb L" [8.0 8.0 8.0]
LightSource "infinite" "rgb L" [0.7 0.7 0.7]
MakeNamedMaterial "glass" "string type" "dielectric" "float eta" [1.52514]
MakeNamedMaterial "table" "string type" "diffuse" "rgb reflectance" [0.8 0.8 0.8]
AttributeBegin
  NamedMaterial "table"
  Shape "plymesh" "string filename" "{tply}"
AttributeEnd
AttributeBegin
  NamedMaterial "glass"
  Shape "plymesh" "string filename" "{dply}"
AttributeEnd
"""
    sp = outd / "dragon_beauty.pbrt"
    sp.write_text(scene)
    t0 = time.time()
    p = subprocess.run([str(pbrt), "--nthreads", "20", str(sp)],
                       capture_output=True, text=True, timeout=7200)
    dt = time.time() - t0
    print((p.stdout[-600:] or "") + (p.stderr[-600:] or ""))
    if p.returncode != 0:
        raise SystemExit("pbrt beauty render failed")
    luxpy = ROOT / "third_party" / "luxvenv" / "Scripts" / "python.exe"
    q = subprocess.run(
        [str(luxpy), "-c", "import mitsuba as mi; mi.set_variant('scalar_rgb');"
         "import numpy as np; from PIL import Image;"
         f"a = np.array(mi.Bitmap(r'{fpath}')); lum = a[..., :3].mean(axis=-1).astype(np.float64);"
         f"np.save(r'{(OUT / 'pbrt_beauty_lum.npy').as_posix()}', lum);"
         "p1, p999 = float(np.quantile(lum, 0.01)), float(np.quantile(lum, 0.999));"
         "m = np.clip((lum - p1) / max(p999 - p1, 1e-9), 0, 1);"
         f"Image.fromarray((255 * m).astype(np.uint8)).save(r'{(OUT / 'pbrt_beauty_vis.png').as_posix()}');"
         "print('PBRT_BEAUTY_DUMP_OK', a.shape, 'p999', float(p999))"],
        capture_output=True, text=True, timeout=600)
    print((q.stdout[-400:] or "") + (q.stderr[-400:] or ""))
    row = {"engine": "pbrt-beauty", "res": f"{w}x{h}",
           "budget": f"{spp}spp/{photons}ph", "render_s": round(dt, 1),
           "r_8tile": "", "r_32tile": "",
           "note": "perspective 39.6deg, same eye/target as CAM_beauty"}
    _append_row(row)
    print(f"PBRT_BEAUTY_OK {dt:.1f}s")


def _mitsu_scene(obj, radiance, res, spp, exr):
    return "\n".join([
        "import mitsuba as mi",
        "mi.set_variant('scalar_spectral')",
        "T = mi.ScalarTransform4f",
        "scene = mi.load_dict({",
        "    'type': 'scene',",
        "    'integrator': {'type': 'path'},",
        "    'sensor': {'type': 'perspective', 'fov': 40,",
        "               'to_world': T.look_at(origin=[1.47, 2.03, 1.29], target=[0, 0, 0.1], up=[0, 0, 1]),",
        f"               'film': {{'type': 'hdrfilm', 'width': {res}, 'height': {res}}}}},",
        f"    'dragon': {{'type': 'obj', 'filename': '{obj}', 'material': {{'type': 'dielectric', 'int_ior': 1.525}}}},",
        "    'sun': {'type': 'sphere', 'center': [-4.8, -2.52, 2.58], 'radius': 0.126,"
        f" 'emitter': {{'type': 'area', 'radiance': {radiance}}}}},",
        "    'ground': {'type': 'rectangle', 'to_world': T.translate([0, 0, -0.28]).scale([8, 7, 1]), 'material': {'type': 'diffuse'}},",
        "    'world': {'type': 'constant', 'radiance': 0.7},",
        "})",
        f"img = mi.render(scene, spp={spp})",
        f"mi.Bitmap(img).write('{exr}')",
        "print('MITSUBA_DONE')",
        "",
    ])


def run_mitsuba_beauty(res=256, spp=64, radiance=6000.0):
    """Perspective beauty, 2.4deg disk sun. Calibrates radiance once at 128px
    against the Cycles beauty ground level, then renders full res."""
    import numpy as np
    luxpy = ROOT / "third_party" / "luxvenv" / "Scripts" / "python.exe"
    if not luxpy.exists():
        raise SystemExit("luxvenv python missing")
    obj = (GEO / "dragon.obj").as_posix()
    script = OUT / "mitsu_dragon.py"
    # calibrate on the Cycles beauty ground level (display-mean of lower half)
    from PIL import Image
    cyc = np.array(Image.open(ROOT / "out/dragon_suite/cycles_native_2560.png").convert("L"),
                   dtype=float) / 255.0
    lin = cyc ** 2.2  # Cycles PNG is gamma-encoded; match in linear light
    tgt = float(np.median(np.sort(lin)[:len(lin) // 2]))
    rad = float(radiance)
    for attempt in range(2):
        exr = (OUT / "mitsuba_calib.exr").as_posix()
        script.write_text(_mitsu_scene(obj, rad, 128, 32, exr))
        p = subprocess.run([str(luxpy), str(script)], capture_output=True,
                           text=True, timeout=1800)
        if "MITSUBA_DONE" not in p.stdout:
            print((p.stdout[-600:] or "") + (p.stderr[-600:] or ""))
            raise SystemExit("mitsuba calibration render failed")
        q = subprocess.run(
            [str(luxpy), "-c", "import mitsuba as mi; mi.set_variant('scalar_rgb');"
             "import numpy as np;"
             f"a = np.array(mi.Bitmap(r'{exr}'))[..., :3].mean(axis=-1).ravel();"
             "print(float(np.median(np.sort(a)[:len(a)//2])))"],
            capture_output=True, text=True, timeout=600)
        got = float(q.stdout.strip().split()[-1])
        print(f"CALIB attempt {attempt}: radiance {rad:.0f} -> ground {got:.3f} (target {tgt:.3f} linear)")
        if got <= 0:
            rad *= 4.0
            continue
        rad *= tgt / got
    exr = (OUT / "mitsuba_beauty.exr").as_posix()
    script.write_text(_mitsu_scene(obj, rad, res, spp, exr))
    t0 = time.time()
    p = subprocess.run([str(luxpy), str(script)], capture_output=True,
                       text=True, timeout=3600)
    dt = time.time() - t0
    print((p.stdout[-600:] or "") + (p.stderr[-600:] or ""))
    if "MITSUBA_DONE" not in p.stdout:
        raise SystemExit("mitsuba beauty render failed")
    q = subprocess.run(
        [str(luxpy), "-c", "import mitsuba as mi; mi.set_variant('scalar_rgb');"
         "import numpy as np; from PIL import Image;"
         f"a = np.array(mi.Bitmap(r'{exr}'))[..., :3].mean(axis=-1);"
         "m = a / max(a.max(), 1e-9);"
         f"Image.fromarray((255 * m).astype(np.uint8)).save(r'{(OUT / 'mitsuba_beauty_vis.png').as_posix()}');"
         "print('MITSUBA_VIS_OK', float(a.max()))"],
        capture_output=True, text=True, timeout=600)
    print((q.stdout[-400:] or "") + (q.stderr[-400:] or ""))
    row = {"engine": "mitsuba-beauty", "res": res,
           "budget": f"{spp}spp/rad~{rad:.0f}", "render_s": round(dt, 1),
           "r_8tile": "", "r_32tile": "",
           "note": "perspective 40deg, 2.4deg disk sun, ground-matched to Cycles beauty"}
    _append_row(row)
    print(f"MITSUBA_BEAUTY_OK {dt:.1f}s")


def _check():
    rng = np.random.default_rng(0)
    a = rng.random((128, 128))
    assert abs(corr(a, a, 8) - 1.0) < 1e-9, "identical grids must correlate 1.0"
    b = rng.random((128, 128))
    assert corr(a, b, 8) < 0.5, "independent grids must not correlate"
    print("DRAGON_SUITE_CHECK_OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--engines", default="referee")
    args = ap.parse_args()
    if args.check:
        _check()
    else:
        for e in args.engines.split(","):
            e = e.strip()
            {"referee": run_referee, "ours": run_ours,
             "cycles_native": run_cycles_native, "pbrt": run_pbrt,
             "mitsuba": run_mitsuba, "score": run_score,
             "pbrt_beauty": run_pbrt_beauty,
             "mitsuba_beauty": lambda: run_mitsuba_beauty(res=640, spp=256)}[e]()
