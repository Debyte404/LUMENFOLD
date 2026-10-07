"""caustic_field_validation.py — independent check that our baked caustic field
is physically right, by comparing it against Cycles' path-traced caustic.

Both images cover exactly the patch the solver bakes (-0.16..+0.16 m) and use
the same geometry and sun, so they are the same picture. The caustic is isolated
by differencing two renders of the SAME scene that differ only in whether Cycles
traces caustic paths:

    Cycles caustics ON - Cycles caustics OFF = the caustic alone

That is the only differential that works. Subtracting a no-glass render does NOT
isolate the caustic: the caustic sits inside the glass's shadow, so the
difference is dominated by the shadow and the caustic cancels out of it. Doing
it that way first gave a correlation of ~0 and nearly produced a false negative.

Spatial convention used everywhere below: an image of K x K tiles covers the
0.32 m patch, tile (row, col) centre is
    x = ((col + 0.5) / K - 0.5) * 320 mm      (right = +x)
    y = (0.5 - (row + 0.5) / K) * 320 mm      (up = +y)

Run:  python tools/caustic_field_validation.py
"""
import numpy as np
from PIL import Image

OUT = "D:/ValueProjects/caustics/out"


def srgb_to_linear(a):
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def load_render(p):
    return srgb_to_linear(
        np.asarray(Image.open(p).convert("RGB")).astype(np.float32) / 255.0
    ).mean(axis=2)


def load_field(p, shape):
    a = np.asarray(Image.open(p)).astype(np.float32)
    if a.ndim == 3:
        a = a[:, :, :3].mean(axis=2)
    a = a / 65535.0 * 16.0        # the bake is written as value/16 in 16 bits
    return np.asarray(Image.fromarray(a.astype(np.float32), mode="F")
                      .resize(shape[::-1], Image.BOX))


def tiles(a, k):
    """Downsample to EXACTLY k x k tiles.

    (An earlier version used k as the tile size in pixels, so tiles(a, 16)
    silently returned a 32x32 grid and every downstream coordinate was scaled
    wrong. k is always the number of tiles.)
    """
    h, w = a.shape
    bh, bw = h // k, w // k
    return a[: bh * k, : bw * k].reshape(k, bh, k, bw).mean(axis=(1, 3))


def corr(a, b):
    a = a - a.mean()
    b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else 0.0


def peak_mm(a, k=32):
    t = tiles(a, k)
    i = np.unravel_index(np.argmax(t), t.shape)
    x = ((i[1] + 0.5) / t.shape[1] - 0.5) * 320.0
    y = (0.5 - (i[0] + 0.5) / t.shape[0]) * 320.0
    return x, y


def com_mm(a, k):
    """Centre of mass of the map above its own median, in patch mm."""
    t = tiles(a, k).astype(np.float64)
    t = t - np.median(t)
    t = np.clip(t, 0, None)
    tot = t.sum()
    if tot <= 0:
        return 0.0, 0.0
    rr, cc = np.mgrid[0:t.shape[0], 0:t.shape[1]]
    x = ((cc * t).sum() / tot + 0.5) / t.shape[1] * 320.0 - 160.0
    y = 160.0 - ((rr * t).sum() / tot + 0.5) / t.shape[0] * 320.0
    return x, y


def show(a, title, k=16):
    t = tiles(a, k)
    lo, hi = np.percentile(t, 2), np.percentile(t, 99)
    chars = " .:-=+*#%@"
    print(f"  {title}   (k={k} tiles, so one tile = {320/k:.0f} mm)")
    for r in range(k):
        v = (t[r] - lo) / max(hi - lo, 1e-9)
        print("    " + "".join(chars[min(9, max(0, int(x * 9.99)))] for x in v))


def main():
    on = load_render(f"{OUT}/ortho_glass.png")
    off = load_render(f"{OUT}/ortho_nocaustic.png")
    caustic = np.clip(on - off, 0, None)
    field = load_field(f"{OUT}/caustic_wavy.png", on.shape)

    print(f"caustic = Cycles(caustics ON) - Cycles(caustics OFF)   "
          f"mean {caustic.mean():+.5f}  max {caustic.max():.4f}")
    print(f"our baked field                                        "
          f"mean {field.mean():.4f}  max {field.max():.3f}")
    print()
    print("Pearson correlation (k x k tiles):")
    for k in (8, 16, 32, 64):
        print(f"   k={k:>3}   {corr(tiles(caustic, k), tiles(field, k)):+.3f}")
    print()
    for name, a in (("Cycles", caustic), ("ours", field)):
        x, y = peak_mm(a)
        gx, gy = com_mm(a, 32)
        print(f"   {name:7s} peak ({x:+7.1f}, {y:+7.1f}) mm   "
              f"azimuth {np.degrees(np.arctan2(y, x)):+6.1f} deg   |r| {np.hypot(x,y):5.1f} mm"
              f"   centroid ({gx:+6.1f}, {gy:+6.1f}) mm")
    print(f"   (the sun travels toward azimuth "
          f"{np.degrees(np.arctan2(0.42, 0.80)):+.1f} deg)")
    print()
    show(caustic, "CYCLES path-traced caustic")
    print()
    show(field, "OUR wave-corrected baked field")


if __name__ == "__main__":
    main()
