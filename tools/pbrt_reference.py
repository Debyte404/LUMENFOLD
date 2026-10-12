"""pbrt_reference.py — drive PBRT-v4 on the same scene, as the trusted
photon-mapping reference.

Why this exists: Mitsuba turned out to have no photon mapping (`sppm`/`bdpt` are
absent in 3.9), so every renderer installed here is a brute-force path tracer
that cannot converge this caustic. PBRT-v4 is the reference implementation of the
techniques that can - SPPM, BDPT, MLT - and it is the standard against which
caustic work is judged.

PBRT has no OBJ shape, so the exported meshes are converted to PLY here.

Usage:
  python tools/pbrt_reference.py --build-scene
  pbrt --sppm ... (see the generated file's header for the command)
"""
import argparse
import os
import struct
import subprocess


# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

ROOT = _ROOT
GEO = f"{ROOT}/out/mitsuba"
OUT = f"{ROOT}/out/pbrt"
PBRT = f"{ROOT}/third_party/pbrt-v4/build/Release/pbrt.exe"
SUN = (0.80, 0.42, -0.43)


def read_obj(path):
    verts, faces = [], []
    for line in open(path):
        if line.startswith("v "):
            _, x, y, z = line.split()[:4]
            verts.append((float(x), float(y), float(z)))
        elif line.startswith("f "):
            idx = [int(t.split("/")[0]) - 1 for t in line.split()[1:]]
            for i in range(1, len(idx) - 1):      # fan-triangulate
                faces.append((idx[0], idx[i], idx[i + 1]))
    return verts, faces


def write_ply(src, dst):
    verts, faces = read_obj(src)
    with open(dst, "w") as f:
        f.write("ply\nformat ascii 1.0\n")
        f.write(f"element vertex {len(verts)}\n")
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write(f"element face {len(faces)}\n")
        f.write("property list uchar int vertex_indices\nend_header\n")
        for v in verts:
            f.write(f"{v[0]:.8f} {v[1]:.8f} {v[2]:.8f}\n")
        for fc in faces:
            f.write(f"3 {fc[0]} {fc[1]} {fc[2]}\n")
    return len(verts), len(faces)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-scene", action="store_true")
    ap.add_argument("--res", type=int, default=512)
    ap.add_argument("--spp", type=int, default=512)
    ap.add_argument("--integrator", default="sppm")
    ap.add_argument("--photons", type=int, default=500000)
    ap.add_argument("--radius", type=float, default=0.008)
    ap.add_argument("--hide-optics", action="store_true")
    ap.add_argument("--eta-water", type=float, default=1.33468,
                    help="water index for this render (measured central-channel value, Daimon & Masumura 2007)")
    ap.add_argument("--eta-glass", type=float, default=1.52514,
                    help="glass index for this render (measured central-channel value, Rubin 1985)")
    ap.add_argument("--out", default=f"{OUT}/pbrt_caustic.exr")
    # geometry source: an animation exports one directory per wave phase
    ap.add_argument("--geo", default=None,
                    help="dir holding glass/water/table .obj (default: out/mitsuba)")
    # perspective camera matching tools/blender_scene.py (else top-down ortho)
    ap.add_argument("--persp", action="store_true",
                    help="match the Blender perspective camera instead of the "
                         "top-down orthographic view")
    ap.add_argument("--az", type=float, default=110.0)
    ap.add_argument("--elev", type=float, default=38.0)
    ap.add_argument("--dist", type=float, default=0.62)
    ap.add_argument("--lens", type=float, default=50.0)
    ap.add_argument("--w", type=int, default=None, help="image width (with --persp)")
    ap.add_argument("--h", type=int, default=None, help="image height (with --persp)")
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    geo = args.geo or GEO
    for name in ("glass", "water", "table"):
        nv, nf = write_ply(f"{geo}/{name}.obj", f"{OUT}/{name}.ply")
        print(f"  {name}.ply  {nv} verts, {nf} tris")

    optics = ("" if args.hide_optics else f"""AttributeBegin
  NamedMaterial "glass"
  Shape "plymesh" "string filename" "{OUT}/glass.ply"
AttributeEnd
AttributeBegin
  NamedMaterial "water"
  Shape "plymesh" "string filename" "{OUT}/water.ply"
AttributeEnd""")
    lx, ly, lz = (-SUN[0] * 2.0, -SUN[1] * 2.0, -SUN[2] * 2.0)
    # orthographic, straight down, framing exactly the 0.32 m patch the solver
    # bakes. PBRT's transform is row-major world-to-camera and the camera looks
    # along +z in camera space, so the world's -z view direction maps to +z.
    if args.persp:
        import math
        # Blender camera reconstruction (see the module docstring)
        fanx, fany = SUN[0], SUN[1]
        fn = math.hypot(fanx, fany)
        fanx, fany = fanx / fn, fany / fn
        tx, ty, tz = fanx * 0.055, fany * 0.055, 0.090 * 0.30
        a, e = math.radians(args.az), math.radians(args.elev)
        vx = math.cos(e) * math.cos(a)
        vy = math.cos(e) * math.sin(a)
        vz = math.sin(e)
        ex, ey, ez = tx + vx * args.dist, ty + vy * args.dist, tz + vz * args.dist
        w = args.w or (args.res * 16 // 9)
        h = args.h or args.res
        sensor = 36.0 * h / w            # AUTO sensor fit -> larger dim
        fov = 2 * math.degrees(math.atan((sensor / 2.0) / args.lens))
        lookat = f"LookAt {ex:.6f} {ey:.6f} {ez:.6f}   {tx:.6f} {ty:.6f} {tz:.6f}   0 0 1"
        camera = (f'Camera "perspective" "float fov" [{fov:.4f}]\n'
                  f'       "float frameaspectratio" [{w / h:.6f}]\n'
                  f'       "float shutteropen" [0.0] "float shutterclose" [1.0]')
        film = (f'Film "rgb" "string filename" "{args.out}"\n'
                f'     "integer xresolution" [{w}] "integer yresolution" [{h}]')
        print(f"  perspective camera: eye ({ex:.3f}, {ey:.3f}, {ez:.3f}) "
              f"-> ({tx:.3f}, {ty:.3f}, {tz:.3f})  fov {fov:.2f} deg  {w}x{h}")
    else:
        lookat = "LookAt 0 0 1   0 0 0   0 1 0"
        camera = ('Camera "orthographic" "float screenwindow" [-0.16 0.16 -0.16 0.16]\n'
                  '       "float frameaspectratio" [1.0]\n'
                  '       "float shutteropen" [0.0] "float shutterclose" [1.0]')
        film = (f'Film "rgb" "string filename" "{args.out}"\n'
                f'     "integer xresolution" [{args.res}] "integer yresolution" [{args.res}]')

    scene = f"""# generated by tools/pbrt_reference.py
# run:  pbrt --sppm <this file>   or   pbrt --bdpt <this file>

{lookat}
{camera}
{film}
# SPPM runs one photon iteration per sample, so this IS the iteration count
Sampler "halton" "integer pixelsamples" [{args.spp}]

# SPPM: the whole reason for building this. A path tracer cannot converge this
# caustic; photon mapping can.
#
# pbrt v4's SPPM takes maxdepth / photonsperiteration / radius, and - this is the
# trap - its ITERATION COUNT IS THE SAMPLER'S SAMPLES PER PIXEL, not an
# "niterations" parameter. There is also no "imagefile" parameter; passing either
# of those is a hard error.
Integrator "sppm" "integer maxdepth" [8]
           "integer photonsperiteration" [{args.photons}]
           "float radius" [{args.radius}]

WorldBegin

# a small sun-equivalent: a distant disc with the right angular size
LightSource "distant" "point3 from" [{lx:.6f} {ly:.6f} {lz:.6f}]
            "point3 to" [0 0 0] "rgb L" [8.0 8.0 8.0]

MakeNamedMaterial "glass" "string type" "dielectric" "float eta" [{args.eta_glass}]
MakeNamedMaterial "water" "string type" "dielectric" "float eta" [{args.eta_water}]
MakeNamedMaterial "table" "string type" "diffuse" "rgb reflectance" [0.8 0.8 0.8]

AttributeBegin
  NamedMaterial "table"
  Shape "plymesh" "string filename" "{OUT}/table.ply"
AttributeEnd
{optics}

# WorldEnd omitted: pbrt v4 only swallows it when its formatting flag is set
"""
    path = os.path.splitext(args.out)[0] + ".pbrt"
    with open(path, "w") as f:
        f.write(scene)
    print(f"wrote {path}")
    print(f"integrator requested: {args.integrator}")

    if os.path.exists(PBRT):
        # The integrator is set in the scene file: `pbrt --sppm file` is a hard
        # error in v4 (it prints usage and renders nothing). Only --nthreads and
        # friends are accepted here.
        cmd = [PBRT, "--nthreads", "20", path]
        print("running:", " ".join(cmd))
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
        print(r.stdout[-1500:] or r.stderr[-1500:])
    else:
        print(f"pbrt not built yet at {PBRT}")
        print("build with: cmake --build third_party/pbrt-v4/build --config Release -j 16")


if __name__ == "__main__":
    main()
