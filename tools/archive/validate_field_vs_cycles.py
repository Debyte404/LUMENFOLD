"""validate_field_vs_cycles.py — does our baked caustic field actually match the
caustic an independent renderer computes for the same scene?

The scene is built at exactly the geometry and sun our solver assumes, and the
camera is orthographic and top-down over the same 0.32 m patch our field covers,
so the rendered image and the baked field are the same picture.

Two renders are made:
  A  glass + water present, Cycles computes the caustic itself (injection OFF)
  B  same scene with the glass hidden
A - B isolates what the glass did to the light: positive where it concentrated
light (the caustic), negative where it shadowed. Our field should match the
positive part.

The Pearson correlation is computed for all four orientations, so a convention
mismatch is detected rather than assumed away.

Run:  python tools/archive/validate_field_vs_cycles.py
"""
import os
import subprocess
import sys

import numpy as np
from PIL import Image


# Repo root, derived rather than hardcoded.
import os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
ROOT = _ROOT
BLENDER = "C:/Program Files/Blender Foundation/Blender 4.2/blender.exe"
SCENE = f"{ROOT}/tools/blender_scene.py"
OUT = f"{ROOT}/out"
RES = 512


def render(path, hide_glass):
    cmd = [BLENDER, "--background", "--factory-startup", "--python", SCENE, "--",
           "--caustic", f"{OUT}/caustic_wavy.png", "--out", path,
           "--samples", "2048", "--w", str(RES), "--h", str(RES),
           "--sun", "8", "--world", "0.34", "--world-color", "0.45,0.55,0.80",
           "--sun-color", "0.98,0.98,1.00", "--gain", "0.0",
           "--sun-angle", "2.4", "--ortho", "--no-caustic", "--cycles-caustics"]
    if hide_glass:
        cmd.append("--hide-glass")
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if not os.path.exists(path):
        raise RuntimeError(p.stderr[-600:])
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32) / 255.0


def srgb_to_linear(a):
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def load_field(path, N):
    """Our bake: 16-bit PNG, linear, written as value/16, row 0 = +Y."""
    a = np.asarray(Image.open(path)).astype(np.float32)
    if a.ndim == 3:
        a = a[:, :, :3].mean(axis=2)
    f = a / 65535.0 * 16.0
    if f.shape[0] != N:
        img = Image.fromarray(f.astype(np.float32), mode="F").resize((N, N), Image.BOX)
        f = np.asarray(img)
    return f


def corr(a, b):
    a = a - a.mean()
    b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else 0.0


def main():
    print("rendering A (glass present, Cycles caustics on)...")
    A = srgb_to_linear(render(f"{OUT}/ortho_glass.png", False)).mean(axis=2)
    print("rendering B (glass hidden)...")
    B = srgb_to_linear(render(f"{OUT}/ortho_noglass.png", True)).mean(axis=2)

    diff = A - B
    pos = np.clip(diff, 0, None)          # where the glass ADDED light
    neg = np.clip(-diff, 0, None)         # where it shadowed
    print(f"differential: added-light mean {pos.mean():.4f} "
          f"(max {pos.max():.4f}), shadow mean {neg.mean():.4f} "
          f"(max {neg.max():.4f})")

    field = load_field(f"{OUT}/caustic_wavy.png", RES)
    # our field is zero where no refracted ray lands; the render's positive part
    # is the caustic. compare shape, not absolute level.
    if field.shape != pos.shape:
        field = np.asarray(Image.fromarray(field.astype(np.float32), mode="F")
                           .resize((pos.shape[1], pos.shape[0]), Image.BOX))

    print()
    print("Pearson correlation between our baked field and the rendered caustic:")
    best = None
    for name, f in (("identity", field), ("flip x", np.fliplr(field)),
                    ("flip y", np.flipud(field)),
                    ("flip both", np.flipud(np.fliplr(field)))):
        c = corr(f, pos)
        print(f"   {name:10s} {c:+.3f}")
        if best is None or abs(c) > abs(best[1]):
            best = (name, c)

    print()
    # where is each field's brightest region, in the patch's own units?
    ext = 0.16
    def peak(f):
        i = np.unravel_index(np.argmax(f), f.shape)
        x = (i[1] / (f.shape[1] - 1) - 0.5) * 2 * ext
        y = (0.5 - i[0] / (f.shape[0] - 1)) * 2 * ext
        return x, y
    px, py = peak(pos)
    fx, fy = peak(field)
    print(f"brightest point: render ({px*1000:+.1f}, {py*1000:+.1f}) mm, "
          f"our field ({fx*1000:+.1f}, {fy*1000:+.1f}) mm, "
          f"offset {1000*np.hypot(px-fx, py-fy):.1f} mm")
    # centre of mass of the caustic light: robust to a single noisy pixel
    def com(f):
        f = f - f.min()
        t = f.sum()
        yy, xx = np.mgrid[0:f.shape[0], 0:f.shape[1]]
        cx = (f * xx).sum() / t / (f.shape[1] - 1) * 2 * ext - ext
        cy = ext - (f * yy).sum() / t / (f.shape[0] - 1) * 2 * ext
        return cx, cy
    cx1, cy1 = com(pos)
    cx2, cy2 = com(field)
    print(f"light centroid : render ({cx1*1000:+.1f}, {cy1*1000:+.1f}) mm, "
          f"our field ({cx2*1000:+.1f}, {cy2*1000:+.1f}) mm, "
          f"offset {1000*np.hypot(cx1-cx2, cy1-cy2):.1f} mm")
    print()
    print(f"VERDICT best orientation '{best[0]}' with r = {best[1]:+.3f}")


if __name__ == "__main__":
    sys.exit(main())
