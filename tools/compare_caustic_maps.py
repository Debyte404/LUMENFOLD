"""compare_caustic_maps.py — coarse-scale comparison of our baked field against
the caustic Cycles computed for the same scene.

Per-pixel correlation is dominated by noise when the caustic is only a few
pixels wide, so both maps are blurred to a coarse grid first and printed as
ASCII, which is the only way to "look" at them in this environment.

Run:  python tools/compare_caustic_maps.py
"""
import numpy as np
from PIL import Image

OUT = "D:/ValueProjects/caustics/out"


def srgb_to_linear(a):
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def load_rgb(p):
    return srgb_to_linear(np.asarray(Image.open(p).convert("RGB")).astype(np.float32) / 255.0).mean(axis=2)


def box(a, n):
    H, W = a.shape
    return a[: H // n * n, : W // n * n].reshape(H // n, n, W // n, n).mean(axis=(1, 3))


def corr(a, b):
    a = a - a.mean()
    b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else 0.0


def show(a, title, n=16):
    q = box(a, a.shape[0] // n)
    lo, hi = np.percentile(q, 2), np.percentile(q, 99)
    chars = " .:-=+*#%@"
    print(f"  {title}")
    for r in range(q.shape[0]):
        v = (q[r] - lo) / max(hi - lo, 1e-9)
        print("    " + "".join(chars[min(9, max(0, int(x * 9.99)))] for x in v))


A = load_rgb(f"{OUT}/ortho_glass.png")
B = load_rgb(f"{OUT}/ortho_noglass.png")
d = A - B
pos = np.clip(d, 0, None)

f = np.asarray(Image.open(f"{OUT}/caustic_wavy.png")).astype(np.float32)
if f.ndim == 3:
    f = f[:, :, :3].mean(axis=2)
f = f / 65535.0 * 16.0
f = np.asarray(Image.fromarray(f.astype(np.float32), mode="F").resize(A.shape[::-1], Image.BOX))

print(f"render {A.shape}, field {f.shape}")
print(f"added light: mean {pos.mean():.5f} max {pos.max():.4f} "
      f"p99 {np.percentile(pos,99):.5f}")
print(f"our field  : mean {f.mean():.4f} max {f.max():.3f} p99 {np.percentile(f,99):.4f}")
print()

for n in (8, 16, 32, 64):
    cp = corr(box(pos, pos.shape[0] // n), box(f, f.shape[0] // n))
    print(f"  correlation at {n}x{n}: {cp:+.3f}")

print()


def peak_angle(a, n=32):
    q = box(a, a.shape[0] // n)
    q = q - np.median(q)
    i = np.unravel_index(np.argmax(q), q.shape)
    # image -> patch mm, +y up
    x = (i[1] / (q.shape[1] - 1) - 0.5) * 0.32
    y = (0.5 - i[0] / (q.shape[0] - 1)) * 0.32
    ang = np.degrees(np.arctan2(y, x))
    return x * 1000, y * 1000, ang


for name, a in (("rendered caustic", pos), ("our baked field", f)):
    x, y, ang = peak_angle(a)
    print(f"  {name:17s} peak at ({x:+7.1f}, {y:+7.1f}) mm  ->  {ang:+7.1f} deg "
          f"from +x   (|r| = {np.hypot(x,y):.1f} mm)")
print(f"  the sun travels toward azimuth {np.degrees(np.arctan2(0.42, 0.80)):+.1f} deg")
print()
show(pos, "RENDERED caustic (glass minus no-glass, positive part)", 16)
print()
show(f, "OUR baked field", 16)
