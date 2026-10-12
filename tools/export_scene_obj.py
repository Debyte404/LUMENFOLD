"""export_scene_obj.py — write the scene geometry to OBJ for the reference solver.

For a comparison against an external renderer to mean anything, that renderer has
to have the SAME object. Re-deriving the meshes inside Mitsuba from the same
formulas risks a silent difference; exporting the exact vertices removes the
question.

Geometry is generated with the same parameters as tools/blender_scene.py:
glass tube (outer 35 mm, wall 3.5 mm, height 90 mm), rippled water surface at
z = 59.4 mm displaced by the same wave field, table 0.32 m square at z = 0.

Run:  python tools/export_scene_obj.py [--wave-t T] [--out-dir DIR]

--wave-t displaces the water surface at that phase (t*(1+i), the same
convention the solver, the tracer and the Blender scene use), and --out-dir
lets an animation write a different geometry per frame.
"""
import argparse
import math
import os


# Repo root, derived rather than hardcoded: this file lives one level down.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

OUT = _ROOT + "/out/mitsuba"
R_OUT, R_IN, H, BOT = 0.035, 0.0315, 0.090, 0.0035
WATER_TOP = 0.0594
EXT = 0.16
SEG, NR = 128, 40

AMP = (0.00065, 0.00040, 0.00025, 0.00015)
LAM = (0.042, 0.027, 0.017, 0.011)
DX = (1.0, 0.35, -0.75, 0.6)
DY = (0.25, 1.0, 0.55, -0.9)


def wave_h(x, y, t=0.0):
    h = 0.0
    for i in range(4):
        n = math.hypot(DX[i], DY[i])
        k = 2 * math.pi / LAM[i]
        h += AMP[i] * math.sin(k * ((DX[i] / n) * x + (DY[i] / n) * y) + t * (1 + i))
    return h


class Obj:
    def __init__(self):
        self.v, self.f = [], []

    def add(self, verts, faces):
        o = len(self.v)
        self.v += list(verts)
        self.f += [tuple(i + o + 1 for i in face) for face in faces]

    def write(self, path, name):
        with open(path, "w") as fh:
            fh.write(f"# {name}\n")
            for v in self.v:
                fh.write(f"v {v[0]:.8f} {v[1]:.8f} {v[2]:.8f}\n")
            for f in self.f:
                fh.write("f " + " ".join(str(i) for i in f) + "\n")
        return len(self.v), len(self.f)


def tube(r, z0, z1, seg=SEG, outward=True):
    v, f = [], []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        v.append((r * math.cos(a), r * math.sin(a), z0))
        v.append((r * math.cos(a), r * math.sin(a), z1))
    for i in range(seg):
        a0, a1 = 2 * i, 2 * ((i + 1) % seg)
        b0, b1 = a0 + 1, a1 + 1
        f.append((a0, a1, b1) if outward else (a0, b1, a1))
        f.append((a0, b1, b0) if outward else (a0, b0, b1))
    return v, f


def disc(r, z, flip=False, seg=SEG):
    v = [(0.0, 0.0, z)]
    for i in range(seg):
        a = 2 * math.pi * i / seg
        v.append((r * math.cos(a), r * math.sin(a), z))
    f = []
    for i in range(seg):
        a0, a1 = 1 + i, 1 + ((i + 1) % seg)
        f.append((0, a1, a0) if flip else (0, a0, a1))
    return v, f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wave-t", type=float, default=0.0)
    ap.add_argument("--out-dir", default=OUT)
    args = ap.parse_args()
    out = args.out_dir
    t = args.wave_t
    os.makedirs(out, exist_ok=True)

    glass = Obj()
    glass.add(*tube(R_OUT, BOT, H, outward=True))
    glass.add(*tube(R_IN, BOT, H, outward=False))
    glass.add(*disc(R_OUT, BOT, flip=True))
    glass.add(*disc(R_IN, BOT))
    glass.add(*disc(R_OUT, H))
    glass.add(*disc(R_IN, H, flip=True))

    water = Obj()
    water.add(*tube(R_IN - 0.0001, BOT, WATER_TOP, outward=True))
    # rippled top surface, radial grid, same wave field as the renderer
    v = [(0.0, 0.0, WATER_TOP + wave_h(0.0, 0.0, t))]
    for i in range(1, NR + 1):
        rr = (R_IN - 0.0001) * i / NR
        for j in range(SEG):
            a = 2 * math.pi * j / SEG
            x, y = rr * math.cos(a), rr * math.sin(a)
            v.append((x, y, WATER_TOP + wave_h(x, y, t)))
    ring = lambda i, j: 1 + (i - 1) * SEG + (j % SEG) if i > 0 else 0
    f = []
    for j in range(SEG):
        f.append((0, ring(0, j), ring(0, j + 1)))
    for i in range(1, NR):
        for j in range(SEG):
            f.append((ring(i, j), ring(i, j + 1), ring(i + 1, j + 1), ring(i + 1, j)))
    water.add(v, f)
    water.add(*disc(R_IN - 0.0001, BOT, flip=True))

    table = Obj()
    table.add([(-EXT, -EXT, 0.0), (EXT, -EXT, 0.0), (EXT, EXT, 0.0), (-EXT, EXT, 0.0)],
              [(0, 1, 2, 3)])

    for name, ob in (("glass", glass), ("water", water), ("table", table)):
        nv, nf = ob.write(f"{out}/{name}.obj", name)
        print(f"  {name}.obj  {nv} verts, {nf} faces")
    print(f"written to {out}  (wave-t {t:.4f})")


if __name__ == "__main__":
    main()
